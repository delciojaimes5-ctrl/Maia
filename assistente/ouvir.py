
import os

from dotenv import load_dotenv
from groq import Groq

load_dotenv()

MODELO = "whisper-large-v3-turbo"

_cliente = None


def obter_cliente():
    """
    Cria o cliente Groq à primeira utilização.

    Mantém a aplicação arrancável sem a GROQ_API_KEY configurada.
    """

    global _cliente

    if _cliente is None:

        chave = os.getenv("GROQ_API_KEY")

        if not chave:
            raise RuntimeError("GROQ_API_KEY não encontrada.")

        _cliente = Groq(api_key=chave)

    return _cliente


def transcrever_audio(arquivo):

    if arquivo is None:
        raise ValueError("Nenhum ficheiro de áudio foi recebido.")

    nome = arquivo.filename or "audio.webm"

    extensao = os.path.splitext(nome)[1].lower()

    extensoes_validas = {
        ".webm", ".ogg", ".wav", ".mp3",
        ".m4a", ".mp4", ".mpeg", ".mpga", ".flac"
    }

    if extensao not in extensoes_validas:
        raise ValueError(
            f"Formato de áudio não suportado: {extensao}"
        )

    audio = arquivo.read()

    if not audio:
        raise ValueError("O ficheiro de áudio está vazio.")

    try:
        transcricao = obter_cliente().audio.transcriptions.create(
            file=(nome, audio),
            model=MODELO,
            language="pt",
            response_format="json"
        )

        return transcricao.text.strip()

    except Exception as erro:
        raise RuntimeError(
            f"Erro ao transcrever o áudio: {erro}"
        ) from erro
