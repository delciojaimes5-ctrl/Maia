
import re
from pathlib import Path
from uuid import uuid4

from assistente.ouvir import transcrever_audio
from assistente.conversar import gerar_resposta
from assistente.falar import gerar_audio
from assistente.comandos import (
    normalizar_palavras,
    planear_comandos,
    CONFIRMACOES,
    CANCELAMENTOS,
)


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


# A interpretação das frases vive em assistente/comandos.py:
# normalizar_palavras, identificar_acao_lampada, identificar_alvo_lampada,
# identificar_comando_lampada e planear_comandos.


SEM_CONTROLO = (
    "Não consigo controlar as lâmpadas neste momento."
)

FALHA_LIGACAO = (
    "Não consegui comunicar com o Arduino. "
    "Verifica a ligação."
)

FALHA_EXECUCAO = (
    "Ocorreu um erro ao tentar controlar as lâmpadas."
)

MENSAGENS_FALHA = {SEM_CONTROLO, FALHA_LIGACAO, FALHA_EXECUCAO}

RESPOSTAS_COMANDO = {
    "LAMP1_ON": "A primeira lâmpada está ligada.",
    "LAMP1_OFF": "A primeira lâmpada está desligada.",
    "LAMP2_ON": "A segunda lâmpada está ligada.",
    "LAMP2_OFF": "A segunda lâmpada está desligada.",
    "LAMP3_ON": "A terceira lâmpada está ligada.",
    "LAMP3_OFF": "A terceira lâmpada está desligada.",
    "ALL_ON": "Todas as lâmpadas estão ligadas.",
    "ALL_OFF": "Todas as lâmpadas estão desligadas.",
}


def executar_comando_lampada(comando, executar_comando):
    """Executa o comando e valida a confirmação do Arduino."""

    if executar_comando is None:
        return SEM_CONTROLO

    try:
        executar_comando(comando)

        return RESPOSTAS_COMANDO[comando]

    except (ConnectionError, TimeoutError, OSError) as erro:
        print(f"Erro de comunicação com Arduino: {erro}")

        return FALHA_LIGACAO

    except Exception as erro:
        print(f"Erro ao executar comando: {erro}")

        return FALHA_EXECUCAO


def executar_comandos(comandos, executar_comando):
    """
    Executa uma lista de comandos e agrega o resultado sem perder nenhum.

    Se alguns comandos falharem, a resposta diz o que foi feito e o que
    não foi — nunca apresenta como concluído o que não foi confirmado.
    """

    respostas = []
    falhas = 0

    for comando in comandos:

        mensagem = executar_comando_lampada(comando, executar_comando)

        if mensagem in MENSAGENS_FALHA:
            falhas += 1
        else:
            respostas.append(mensagem)

    if not respostas:
        return (
            "Não consegui comunicar com o Arduino. "
            "Verifica a ligação."
        )

    texto = " ".join(respostas)

    if falhas:
        texto += (
            " Quanto ao resto, não consegui confirmar com o Arduino."
        )

    return texto



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

    # 3. Interpretar a frase (determinístico; o LLM nunca executa nada)
    plano = planear_comandos(texto_usuario)

    print("[MAIIA] Plano:", plano)

    palavras = set(normalizar_palavras(texto_usuario))

    confirmou = bool(palavras & CONFIRMACOES)
    cancelou = bool(palavras & CANCELAMENTOS) or "nao" in palavras

    # 4. Pergunta sobre o estado: responder, nunca executar
    if plano["pergunta"]:
        resposta = gerar_resposta(mensagens)
        pendente = None

    # 5. Frase contraditória: não adivinhar
    elif plano["ambiguo"]:
        resposta = (
            "Fiquei com dúvidas no que pediste. "
            "Diz de outra forma, por favor."
        )
        pendente = None

    # 6. Comando completo: uma lâmpada, várias, ou todas
    elif plano["comandos"]:
        resposta = executar_comandos(
            plano["comandos"],
            executar_comando
        )
        pendente = None

    # 7. Resposta à pergunta anterior da Maiia ("a segunda")
    elif pendente and plano["alvos"]:
        resposta = executar_comandos(
            [f"{alvo}_{pendente}" for alvo in plano["alvos"]],
            executar_comando
        )
        pendente = None

    # 8. Cancelamento explícito
    elif pendente and cancelou:
        resposta = "Está bem. Cancelei o comando."
        pendente = None

    # 9. Havia um comando à espera: repetir a pergunta em vez de dar erro
    elif pendente:
        if plano["pendente"]:
            pendente = plano["pendente"]

        acao_texto = "ligar" if pendente == "ON" else "desligar"

        resposta = (
            "Ainda não sei qual é a lâmpada. "
            f"Diz primeira, segunda, terceira ou todas, "
            f"para eu {acao_texto}."
        )

    # 10. Acção sem lâmpada
    elif plano["pendente"]:
        pendente = plano["pendente"]

        acao_texto = "ligar" if pendente == "ON" else "desligar"

        resposta = (
            f"Qual lâmpada queres {acao_texto}? "
            "Primeira, segunda, terceira ou todas?"
        )

    # 11. Conversa normal com a inteligência artificial
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
