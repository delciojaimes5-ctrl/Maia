"""
Compreensão dos comandos de voz da Maiia.

Este módulo é determinístico de propósito: interpreta a frase e devolve
o que deve ser executado. Nunca fala com o Arduino nem com o LLM — quem
executa é o `maiia.py`, quem conversa é o `conversar.py`.

Corrige os casos que falhavam na versão anterior:
  - sinónimos, imperativos formais e particípios ("ligue", "acesa",
    "quero a primeira ligada", "bota a primeira acesa");
  - frases com mais do que uma lâmpada ou mais do que uma acção
    ("liga a primeira e a segunda");
  - "todas menos a primeira" calcula as restantes em vez de ligar tudo,
    mesmo quando a exclusão vem noutra cláusula ("liga todas, menos a
    primeira");
  - a negação vale por cláusula, não pela frase inteira
    ("não sei, liga a primeira" executa);
  - frases educadas em forma de pergunta ("podes ligar a primeira?")
    executam, mas perguntas sobre o estado ("está tudo ligado?") não.

Vocabulário explícito, sem tolerância por distância de edição: num
sistema que mexe em hardware um falso positivo (acender sem ninguém ter
pedido) custa muito mais do que um falso negativo ("diz de outra
forma"). Erros de transcrição conhecidos entram à mão nas listas, por
exemplo:
  - "ascende" / "ascender" / "ascendem" → acender;
  - "ligues" / "desligues" / "acendas" / "apagues" → formas do conjuntivo
    que o reconhecedor devolve em vez do imperativo.
Cada erro novo que apareça nos registos deve ser acrescentado aqui, com
o comentário do que era suposto dizer.
"""

import re
import unicodedata


# =========================================================
# VOCABULÁRIO
# =========================================================

# Imperativo e infinitivo: pedem uma acção.
VERBOS_LIGAR = {
    "liga", "ligar", "ligue", "liguem", "ligues", "liguemos",
    "ligo", "ligam", "ligasses",
    "acende", "acender", "acenda", "acendam", "acendas", "acendamos",
    "acendo", "acendesses",
    # erro de transcrição observado nos registos: "ascende" por "acende"
    "ascende", "ascender", "ascenda", "ascendam", "ascendas", "ascendem",
    "ativa", "ativar", "ative", "ativem", "atives",
    "bota", "botar", "poe", "poem",
    "abre", "abrir",
}

VERBOS_DESLIGAR = {
    "desliga", "desligar", "desligue", "desliguem", "desligues",
    "desligo", "desliguemos", "desligasses",
    "apaga", "apagar", "apague", "apaguem", "apagues", "apaguemos",
    "apago", "apagasses",
    "desativa", "desativar", "desative", "desativem", "desatives",
    "corta", "cortar", "corte", "cortem", "cortes",
    "fecha", "fechar", "feche",
}

PARTICIPIOS_LIGAR = {
    "ligada", "ligado", "ligadas", "ligados",
    "acesa", "aceso", "acesas", "acesos",
}

PARTICIPIOS_DESLIGAR = {
    "desligada", "desligado", "desligadas", "desligados",
    "apagada", "apagado", "apagadas", "apagados",
}

# A interpretação da acção aceita as duas formas; a detecção de pergunta
# só conta com o imperativo/infinitivo.
ACOES_LIGAR = VERBOS_LIGAR | PARTICIPIOS_LIGAR
ACOES_DESLIGAR = VERBOS_DESLIGAR | PARTICIPIOS_DESLIGAR
VERBOS_ORDEM = VERBOS_LIGAR | VERBOS_DESLIGAR

NEGACOES = {"nao", "nunca", "jamais", "nem"}

CONFIRMACOES = {
    "sim", "pode", "podes", "podia", "ok", "okay", "isso",
    "certo", "claro", "confirma", "confirmo", "aceito",
    "aceita", "vamos", "ya", "forca", "exato", "exacto",
}

# Inícios de frase que são confirmação e não pergunta
# ("está bem, liga a primeira").
CONFIRMACOES_INICIAIS = {
    "esta bem", "esta bom", "esta certo", "esta otimo", "esta optimo",
}

CANCELAMENTOS = {
    "cancela", "cancelar", "cancelo",
    "desiste", "desistir",
    "esquece", "esquecer",
    "nenhuma", "nenhum",
    "anula", "anular", "aborta", "abortar",
}

EXCLUSOES = {"menos", "excepto", "exceto", "tirando", "fora"}

ALVOS_TODOS = {"todas", "todos", "tudo", "luzes", "lampadas"}

PALAVRAS_PERGUNTA = {
    "esta", "estao", "qual", "quais", "como", "onde", "quando",
    "porque", "quanto", "quantas", "quantos", "quem", "estado",
}

# Ordinais valem sozinhos: "liga a primeira".
ORDINAIS = {
    "primeira": "LAMP1", "primeiro": "LAMP1",
    "primeiras": "LAMP1", "primeiros": "LAMP1",

    "segunda": "LAMP2", "segundo": "LAMP2",
    "segundas": "LAMP2",
    # "segundos" (plural) fica de fora: é a unidade de tempo de
    # "liga a primeira por dois segundos", não uma lâmpada.

    "terceira": "LAMP3", "terceiro": "LAMP3",
    "terceiras": "LAMP3", "terceiros": "LAMP3",
}

# Cardinais contam como lâmpada só logo a seguir a uma destas palavras:
# "acende a luz número dois", "liga a lâmpada 3". Sozinhos seriam
# "bota uma música" ou "liga a primeira por dois segundos".
CARDINAIS = {
    "um": "LAMP1", "uma": "LAMP1", "1": "LAMP1",
    "dois": "LAMP2", "duas": "LAMP2", "2": "LAMP2",
    "tres": "LAMP3", "3": "LAMP3",
}

MARCADORES_CARDINAL = {"lampada", "lampadas", "luz", "luzes", "numero"}

TODAS_AS_LAMPADAS = ("LAMP1", "LAMP2", "LAMP3")

# Separa a frase em cláusulas: "liga a primeira e a segunda".
SEPARADOR_CLAUSULAS = re.compile(
    r"\s*[,;]\s*"
    r"|\s+e\s+"
    r"|\s+mas\s+"
    r"|\s+depois\s+"
    r"|\s+entao\s+"
    r"|\s*\.\s+"
)


# =========================================================
# NORMALIZAÇÃO
# =========================================================

def normalizar_palavras(texto):
    """Minúsculas, sem acentos, sem pontuação, sem o nome da assistente."""

    texto = texto.lower().strip()
    texto = unicodedata.normalize("NFD", texto)

    texto = "".join(
        caractere
        for caractere in texto
        if unicodedata.category(caractere) != "Mn"
    )

    texto = re.sub(r"[^\w\s]", " ", texto)

    palavras = texto.split()

    return [
        palavra
        for palavra in palavras
        if palavra not in {"maia", "maiia"}
    ]


def pertence(palavra, conjunto):
    """Igualdade exacta. Sem tolerância por distância de edição."""

    return palavra in conjunto


def _detetar(palavras, conjunto):

    return any(
        pertence(palavra, conjunto)
        for palavra in palavras
    )


def _detetar_alvos(palavras):
    """Todas as lâmpadas nomeadas, por ordem, sem repetições."""

    alvos = []

    for indice, palavra in enumerate(palavras):

        alvo = ORDINAIS.get(palavra)

        if alvo is None and palavra in CARDINAIS:
            anterior = palavras[indice - 1] if indice else None

            if anterior in MARCADORES_CARDINAL:
                alvo = CARDINAIS[palavra]

        if alvo and alvo not in alvos:
            alvos.append(alvo)

    return alvos


def _detetar_acao(palavras):
    """Acção da cláusula, ou None se não houver ou for contraditória."""

    ligar = _detetar(palavras, ACOES_LIGAR)
    desligar = _detetar(palavras, ACOES_DESLIGAR)

    if ligar == desligar:
        return None

    return "ON" if ligar else "OFF"


# =========================================================
# PLANEAMENTO
# =========================================================

def _e_confirmacao_inicial(palavras):
    """'está bem', 'sim', 'ok' — confirmação, não pergunta."""

    if not palavras:
        return False

    if palavras[0] in {"sim", "ok", "okay", "ya"}:
        return True

    return " ".join(palavras[:2]) in CONFIRMACOES_INICIAIS


def _e_pergunta(texto, palavras):
    """
    Distingue "está tudo ligado?" de "liga tudo".

    Sem isto, uma pergunta sobre o estado executava o comando contrário.

    Só é pergunta quando não há verbo no imperativo nem no infinitivo:
    "podes ligar a primeira?" e "consegues desligar tudo?" são pedidos
    educados e executam; "está tudo ligado?" só tem particípio e é
    pergunta.
    """

    if not palavras:
        return False

    if _detetar(palavras, VERBOS_ORDEM):
        return False

    if _e_confirmacao_inicial(palavras):
        return False

    if "?" in texto:
        return True

    if palavras[0] in PALAVRAS_PERGUNTA:
        return True

    return "estado" in palavras


def _apenas_alvos(item):
    """Cláusula que só nomeia lâmpadas ("a segunda", "e a terceira")."""

    return (
        bool(item["alvos"])
        and item["acao"] is None
        and not item["negacao"]
        and not item["todas"]
        and not item["exclusao"]
    )


def _deduplicar(comandos):
    """Remove repetidos e o que já está implícito em ALL_ON/ALL_OFF."""

    unicos = []

    for comando in comandos:
        if comando not in unicos:
            unicos.append(comando)

    for todos in ("ALL_ON", "ALL_OFF"):
        if todos in unicos:
            acao = todos.split("_")[-1]

            unicos = [
                comando
                for comando in unicos
                if comando == todos or not comando.endswith(f"_{acao}")
            ]

    return unicos


def _ha_contradicao(comandos):
    """'liga a primeira e desliga a primeira' — não adivinhar."""

    por_alvo = {}

    for comando in comandos:
        alvo, acao = comando.rsplit("_", 1)
        anterior = por_alvo.get(alvo)

        if anterior and anterior != acao:
            return True

        por_alvo[alvo] = acao

    return False


def planear_comandos(texto):
    """
    Interpreta a frase e devolve:

      comandos  — lista de comandos prontos a executar ("LAMP1_ON", …)
      pendente  — "ON"/"OFF" quando o utilizador disse a acção mas não
                  disse a lâmpada
      alvos     — lâmpadas nomeadas sem acção (resposta a uma pergunta
                  anterior da Maiia)
      ambiguo   — True quando não se deve executar nada e é melhor
                  pedir esclarecimento
      pergunta  — True quando a frase é uma pergunta e não um comando
    """

    resultado = {
        "comandos": [],
        "pendente": None,
        "alvos": [],
        "ambiguo": False,
        "pergunta": False,
    }

    palavras_frase = normalizar_palavras(texto)

    if _e_pergunta(texto, palavras_frase):
        resultado["pergunta"] = True
        return resultado

    # Uma cláusula que começa por palavra de exclusão pertence à
    # anterior: "liga todas, menos a primeira".
    clausulas = []

    for bruta in SEPARADOR_CLAUSULAS.split(texto):

        if not bruta or not bruta.strip():
            continue

        palavras = normalizar_palavras(bruta)

        if not palavras:
            continue

        if clausulas and palavras[0] in EXCLUSOES:
            clausulas[-1] = f"{clausulas[-1]} {bruta.strip()}"
        else:
            clausulas.append(bruta.strip())

    if not clausulas:
        return resultado

    processadas = []

    for clausula in clausulas:

        palavras = normalizar_palavras(clausula)

        if not palavras:
            continue

        processadas.append({
            "palavras": palavras,
            "negacao": _detetar(palavras, NEGACOES),
            "acao": _detetar_acao(palavras),
            "alvos": _detetar_alvos(palavras),
            # Correspondência exacta: a tolerância faria "lâmpada"
            # (singular) passar por "lâmpadas" (todas).
            "todas": any(palavra in ALVOS_TODOS for palavra in palavras),
            "exclusao": _detetar(palavras, EXCLUSOES),
        })

    acao_anterior = None
    acoes_sem_alvo = []
    indice = 0

    while indice < len(processadas):

        item = processadas[indice]
        indice += 1

        # "não ligues a primeira" — não adivinhar o que ele quer.
        if item["negacao"] and item["acao"]:
            resultado["ambiguo"] = True
            continue

        # "não sei", "mas não" — a cláusula não pede nada.
        if item["negacao"]:
            continue

        if item["acao"]:
            acao_anterior = item["acao"]

        # "desliga todas menos a primeira" → as outras duas.
        if item["acao"] and item["todas"]:

            if not item["exclusao"]:
                resultado["comandos"].append(f"ALL_{item['acao']}")
                continue

            excluidos = list(item["alvos"])

            # "desliga todas menos a primeira e a segunda": as cláusulas
            # seguintes que só nomeiam lâmpadas alargam a exclusão em vez
            # de herdar a acção.
            while indice < len(processadas) and _apenas_alvos(
                processadas[indice]
            ):
                for alvo in processadas[indice]["alvos"]:
                    if alvo not in excluidos:
                        excluidos.append(alvo)

                indice += 1

            restantes = [
                lampada
                for lampada in TODAS_AS_LAMPADAS
                if lampada not in excluidos
            ]

            if not restantes:
                resultado["ambiguo"] = True
                continue

            for lampada in restantes:
                resultado["comandos"].append(f"{lampada}_{item['acao']}")

            continue

        if item["alvos"]:

            acao_a_usar = item["acao"] or acao_anterior

            if acao_a_usar is None:
                # Lâmpada sem acção: pode ser resposta à pergunta anterior.
                for alvo in item["alvos"]:
                    if alvo not in resultado["alvos"]:
                        resultado["alvos"].append(alvo)
                continue

            for alvo in item["alvos"]:
                resultado["comandos"].append(f"{alvo}_{acao_a_usar}")

            continue

        if item["acao"]:
            acoes_sem_alvo.append(item["acao"])

    # Acção sem lâmpada: perguntar qual.
    if acoes_sem_alvo:

        distintas = set(acoes_sem_alvo)

        if len(distintas) > 1:
            resultado["ambiguo"] = True
            resultado["pendente"] = None

        elif resultado["comandos"]:
            # "liga a primeira e desliga" — a frase tem partes que não
            # sabemos completar; não executar metade em silêncio.
            resultado["ambiguo"] = True
            resultado["pendente"] = None

        else:
            resultado["pendente"] = acoes_sem_alvo[-1]

    resultado["comandos"] = _deduplicar(resultado["comandos"])

    if _ha_contradicao(resultado["comandos"]):
        resultado["ambiguo"] = True

    # Ambiguidade nunca convive com comandos: quem chama não pode
    # executar metade da frase por engano.
    if resultado["ambiguo"]:
        resultado["comandos"] = []
        resultado["pendente"] = None

    return resultado


# =========================================================
# COMPATIBILIDADE
# =========================================================

def identificar_acao_lampada(texto):
    """Acção pedida na frase, ignorando cláusulas negativas."""

    plano = planear_comandos(texto)

    if plano["comandos"]:
        return plano["comandos"][0].split("_")[-1]

    return plano["pendente"]


def identificar_alvo_lampada(texto):
    """Lâmpada pedida na frase (ou "ALL"), ou None."""

    palavras = normalizar_palavras(texto)

    if any(palavra in ALVOS_TODOS for palavra in palavras):
        return "ALL"

    alvos = _detetar_alvos(palavras)

    return alvos[0] if alvos else None


def identificar_comando_lampada(texto):
    """Primeiro comando da frase, ou None. Mantido por compatibilidade."""

    plano = planear_comandos(texto)

    if plano["comandos"]:
        return plano["comandos"][0]

    return None
