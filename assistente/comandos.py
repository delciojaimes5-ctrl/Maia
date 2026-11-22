"""
Compreensão dos comandos de voz da Maiia.

Este módulo é determinístico de propósito: interpreta a frase e devolve
o que deve ser executado. Nunca fala com o Arduino nem com o LLM — quem
executa é o `maiia.py`, quem conversa é o `conversar.py`.

Corrige os casos que falhavam na versão anterior:
  - sinónimos, imperativos formais e particípios ("ligue", "acesa",
    "quero a primeira ligada", "bota a primeira acesa");
  - tolerância a erros de transcrição ("ascende" → "acende");
  - frases com mais do que uma lâmpada ou mais do que uma acção
    ("liga a primeira e a segunda");
  - "todas menos a primeira" calcula as restantes em vez de ligar tudo;
  - a negação vale por cláusula, não pela frase inteira
    ("não sei, liga a primeira" executa).
"""

import re
import unicodedata


# =========================================================
# VOCABULÁRIO
# =========================================================

ACOES_LIGAR = {
    "liga", "ligar", "ligue", "liguem", "ligo", "ligam",
    "acende", "acender", "acende", "acendam", "acendo",
    "ascende", "ascender", "ascendem",
    "ativa", "ativar", "ative",
    "bota", "botar", "poe",
    "abre", "abrir",
    "ligada", "ligado", "ligadas", "ligados",
    "acesa", "aceso", "acesas", "acesos",
}

ACOES_DESLIGAR = {
    "desliga", "desligar", "desligue", "desliguem", "desligo",
    "apaga", "apagar", "apaguem", "apago",
    "desativa", "desativar", "desative",
    "corta", "cortar", "corte",
    "fecha", "fechar",
    "desligada", "desligado", "desligadas", "desligados",
    "apagada", "apagado", "apagadas", "apagados",
}

NEGACOES = {"nao", "nunca", "jamais", "nem"}

CONFIRMACOES = {
    "sim", "pode", "podes", "podia", "ok", "okay", "isso",
    "certo", "claro", "confirma", "confirmo", "aceito",
    "aceita", "vamos", "ya", "forca", "exato", "exacto",
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

NUMEROS = {
    "primeira": "LAMP1", "primeiro": "LAMP1",
    "primeiras": "LAMP1", "primeiros": "LAMP1",
    "um": "LAMP1", "uma": "LAMP1", "1": "LAMP1",

    "segunda": "LAMP2", "segundo": "LAMP2",
    "segundas": "LAMP2", "segundos": "LAMP2",
    "dois": "LAMP2", "duas": "LAMP2", "2": "LAMP2",

    "terceira": "LAMP3", "terceiro": "LAMP3",
    "terceiras": "LAMP3", "terceiros": "LAMP3",
    "tres": "LAMP3", "3": "LAMP3",
}

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
# NORMALIZAÇÃO E TOLERÂNCIA
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


def distancia_edicao(a, b):
    """Distância de Levenshtein entre duas palavras."""

    if a == b:
        return 0

    if abs(len(a) - len(b)) > 2:
        return 3

    anterior = list(range(len(b) + 1))

    for i, letra_a in enumerate(a, 1):

        atual = [i]

        for j, letra_b in enumerate(b, 1):
            atual.append(
                min(
                    anterior[j] + 1,
                    atual[j - 1] + 1,
                    anterior[j - 1] + (letra_a != letra_b)
                )
            )

        anterior = atual

    return anterior[len(b)]


def pertence(palavra, conjunto):
    """
    Igualdade exacta ou, para palavras longas, erro de transcrição na
    ordem de uma letra ("ascende" → "acende", "ligue" → "liga").

    Palavras curtas exigem igualdade exacta: a tolerância em "liga",
    "por" ou "nao" criaria falsos positivos.
    """

    if palavra in conjunto:
        return True

    if len(palavra) >= 8:
        limite = 2
    elif len(palavra) >= 5:
        limite = 1
    else:
        return False

    return any(
        distancia_edicao(palavra, candidata) <= limite
        for candidata in conjunto
    )


def _detetar(palavras, conjunto):

    return any(
        pertence(palavra, conjunto)
        for palavra in palavras
    )


def _detetar_alvos(palavras):
    """Todas as lâmpadas nomeadas, por ordem, sem repetições."""

    alvos = []

    for palavra in palavras:
        alvo = NUMEROS.get(palavra)

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

def _e_pergunta(texto, palavras):
    """
    Distingue "está tudo ligado?" de "liga tudo".

    Sem isto, uma pergunta sobre o estado executava o comando contrário.
    """

    if "?" in texto:
        return True

    if palavras and palavras[0] in PALAVRAS_PERGUNTA:
        return True

    return "estado" in palavras


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

    clausulas = [
        clausula
        for clausula in SEPARADOR_CLAUSULAS.split(texto)
        if clausula and clausula.strip()
    ]

    if not clausulas:
        return resultado

    acao_anterior = None
    acoes_sem_alvo = []

    for clausula in clausulas:

        palavras = normalizar_palavras(clausula)

        if not palavras:
            continue

        negacao = _detetar(palavras, NEGACOES)
        acao = _detetar_acao(palavras)
        alvos = _detetar_alvos(palavras)
        # Correspondência exacta: a tolerância faria "lâmpada" (singular)
        # passar por "lâmpadas" (todas).
        todas = any(palavra in ALVOS_TODOS for palavra in palavras)
        exclusao = _detetar(palavras, EXCLUSOES)

        # "não ligues a primeira" — não adivinhar o que ele quer.
        if negacao and acao:
            resultado["ambiguo"] = True
            continue

        # "não sei", "mas não" — a cláusula não pede nada.
        if negacao:
            continue

        if acao:
            acao_anterior = acao

        # "desliga todas menos a primeira" → as outras duas.
        if acao and todas:

            if not exclusao:
                resultado["comandos"].append(f"ALL_{acao}")
                continue

            restantes = [
                lampada
                for lampada in TODAS_AS_LAMPADAS
                if lampada not in alvos
            ]

            if not restantes:
                resultado["ambiguo"] = True
                continue

            for lampada in restantes:
                resultado["comandos"].append(f"{lampada}_{acao}")

            continue

        if alvos:

            acao_a_usar = acao or acao_anterior

            if acao_a_usar is None:
                # Lâmpada sem acção: pode ser resposta à pergunta anterior.
                for alvo in alvos:
                    if alvo not in resultado["alvos"]:
                        resultado["alvos"].append(alvo)
                continue

            for alvo in alvos:
                resultado["comandos"].append(f"{alvo}_{acao_a_usar}")

            continue

        if acao:
            acoes_sem_alvo.append(acao)

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
