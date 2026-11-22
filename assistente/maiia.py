
import re
import unicodedata
from pathlib import Path
from uuid import uuid4

from assistente.ouvir import transcrever_audio
from assistente.conversar import gerar_resposta
from assistente.falar import gerar_audio


RAIZ = Path(__file__).resolve().parent.parent
PASTA_AUDIO = RAIZ / "static" / "audio"

LIMITE_PALAVRAS = 100


def criar_caminho_audio():
    """Cria um nome único para cada ficheiro de áudio."""

    PASTA_AUDIO.mkdir(parents=True, exist_ok=True)

    nome = f"maiia_{uuid4().hex}.mp3"

    return PASTA_AUDIO / nome


def preparar_texto_para_falar(texto):
    """Prepara o texto para uma leitura natural pelo Edge TTS."""

    texto = re.sub(r"\([^)]*\)", "", texto)
    texto = re.sub(r"\[[^\]]*\]", "", texto)
    texto = re.sub(r"[*_`#]", "", texto)
    texto = re.sub(r"\s+", " ", texto)

    return texto.strip()


def limitar_resposta(texto, limite=LIMITE_PALAVRAS):
    """Limita o tamanho do texto falado sem cortar palavras."""

    palavras = texto.split()

    if len(palavras) <= limite:
        return texto

    texto_limitado = " ".join(palavras[:limite])

    return texto_limitado.rstrip(" ,;:-") + "."


async def cumprimentar(nome=None, conhecido=False):

    if conhecido and nome:
        frase = (
            f"Olá, {nome}! Como estás? "
            "Em que posso ajudar?"
        )
    else:
        frase = (
            "Olá! Ainda não estás registado no SmartAccess. "
            "Por favor, realiza o teu cadastro para poderes "
            "utilizar o sistema."
        )

    caminho = criar_caminho_audio()

    await gerar_audio(frase, str(caminho))

    return {
        "mensagem": frase,
        "audio": str(caminho),
        "ficheiro": caminho.name
    }


def normalizar_palavras(texto):
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


def identificar_acao_lampada(texto):
    palavras = normalizar_palavras(texto)

    if any(
        palavra in {"nao", "nunca", "jamais"}
        for palavra in palavras
    ):
        return None

    ligar = {
        "liga", "ligar", "acende", "acender",
        "ativa", "ativar"
    }

    desligar = {
        "desliga", "desligar", "apaga", "apagar",
        "desativa", "desativar"
    }

    encontrou_ligar = any(p in ligar for p in palavras)
    encontrou_desligar = any(p in desligar for p in palavras)

    if encontrou_ligar == encontrou_desligar:
        return None

    return "ON" if encontrou_ligar else "OFF"


def identificar_alvo_lampada(texto):
    palavras = normalizar_palavras(texto)

    if any(
        palavra in {"todas", "todos", "tudo", "luzes"}
        for palavra in palavras
    ):
        return "ALL"

    numeros = {
        "primeira": "LAMP1",
        "primeiro": "LAMP1",
        "um": "LAMP1",
        "uma": "LAMP1",
        "1": "LAMP1",

        "segunda": "LAMP2",
        "segundo": "LAMP2",
        "dois": "LAMP2",
        "duas": "LAMP2",
        "2": "LAMP2",

        "terceira": "LAMP3",
        "terceiro": "LAMP3",
        "tres": "LAMP3",
        "3": "LAMP3"
    }

    for palavra in palavras:
        if palavra in numeros:
            return numeros[palavra]

    return None

def executar_comando_lampada(comando, executar_comando):
    """Executa o comando e valida a confirmação do Arduino."""

    respostas = {
        "LAMP1_ON": "A primeira lâmpada está ligada.",
        "LAMP1_OFF": "A primeira lâmpada está desligada.",
        "LAMP2_ON": "A segunda lâmpada está ligada.",
        "LAMP2_OFF": "A segunda lâmpada está desligada.",
        "LAMP3_ON": "A terceira lâmpada está ligada.",
        "LAMP3_OFF": "A terceira lâmpada está desligada.",
        "ALL_ON": "Todas as lâmpadas estão ligadas.",
        "ALL_OFF": "Todas as lâmpadas estão desligadas."
    }

    if executar_comando is None:
        return "Não consigo controlar as lâmpadas neste momento."

    try:
        executar_comando(comando)

        return respostas[comando]

    except (ConnectionError, TimeoutError, OSError) as erro:
        print(f"Erro de comunicação com Arduino: {erro}")

        return (
            "Não consegui comunicar com o Arduino. "
            "Verifica a ligação."
        )

    except Exception as erro:
        print(f"Erro ao executar comando: {erro}")

        return (
            "Ocorreu um erro ao tentar controlar as lâmpadas."
        )

def identificar_comando_lampada(texto):
    acao = identificar_acao_lampada(texto)

    if not acao:
        return None

    alvo = identificar_alvo_lampada(texto)

    if not alvo:
        return None

    if alvo == "ALL":
        return f"ALL_{acao}"

    return f"{alvo}_{acao}"


async def processar_audio(
    arquivo,
    historico=None,
    executar_comando=None,
    comando_pendente=None
):
    if arquivo is None:
        raise ValueError("Nenhum áudio foi recebido.")

    # 1. Transcrever o áudio
    texto_usuario = transcrever_audio(arquivo)

    print("[MAIIA] Transcrição:", repr(texto_usuario))
    print("[MAIIA] Comando pendente recebido:", repr(comando_pendente))

    if not texto_usuario:
        raise ValueError("Não foi possível compreender o áudio.")

    # 2. Preparar histórico
    mensagens = list(historico or [])

    mensagens.append({
        "role": "user",
        "content": texto_usuario
    })

    pendente = comando_pendente

    # 3. Verificar se o utilizador deu um comando completo
    comando = identificar_comando_lampada(texto_usuario)

    print("[MAIIA] Comando identificado:", repr(comando))

    if comando:
        resposta = executar_comando_lampada(
            comando,
            executar_comando
        )

        pendente = None

    # 4. Verificar se existe um comando à espera de confirmação
    elif pendente:

        palavras = set(normalizar_palavras(texto_usuario))

        cancelamentos = {
            "nao",
            "cancela",
            "cancelar",
            "desiste",
            "desistir",
            "esquece",
            "esquecer",
            "nenhuma"
        }

        if palavras.intersection(cancelamentos):
            resposta = "Está bem. Cancelei o comando."
            pendente = None

        else:
            alvo = identificar_alvo_lampada(texto_usuario)

            print("[MAIIA] Alvo identificado:", repr(alvo))

            if alvo:
                if alvo == "ALL":
                    comando = f"ALL_{pendente}"
                else:
                    comando = f"{alvo}_{pendente}"

                print("[MAIIA] Comando enviado:", repr(comando))

                resposta = executar_comando_lampada(
                    comando,
                    executar_comando
                )

                pendente = None

            else:
                nova_acao = identificar_acao_lampada(texto_usuario)

                if nova_acao:
                    pendente = nova_acao

                    resposta = (
                        "Compreendi a nova ação. "
                        "Qual lâmpada pretendes controlar? "
                        "Primeira, segunda, terceira ou todas?"
                    )
                else:
                    resposta = (
                        "Não consegui identificar a lâmpada. "
                        "Diz primeira, segunda, terceira ou todas. "
                        "Também podes dizer cancela."
                    )

    # 5. Verificar se foi dada uma ação sem indicar a lâmpada
    elif identificar_acao_lampada(texto_usuario):

        pendente = identificar_acao_lampada(texto_usuario)

        acao_texto = (
            "ligar"
            if pendente == "ON"
            else "desligar"
        )

        resposta = (
            f"Qual lâmpada queres {acao_texto}? "
            "Primeira, segunda, terceira ou todas?"
        )

    # 6. Conversa normal com a inteligência artificial
    else:
        resposta = gerar_resposta(mensagens)

    mensagens.append({
        "role": "assistant",
        "content": resposta
    })

    # 7. Preparar texto para a voz
    texto_para_falar = preparar_texto_para_falar(resposta)
    texto_para_falar = limitar_resposta(texto_para_falar)

    if not texto_para_falar:
        raise ValueError(
            "Não existe texto válido para gerar áudio."
        )

    # 8. Gerar áudio
    caminho = criar_caminho_audio()

    await gerar_audio(texto_para_falar, str(caminho))

    return {
        "texto_usuario": texto_usuario,
        "resposta": resposta,
        "texto_para_falar": texto_para_falar,
        "audio": str(caminho),
        "ficheiro": caminho.name,
        "historico": mensagens,
        "comando_pendente": pendente
    }
