
from pathlib import Path

import edge_tts


VOZ = "pt-PT-RaquelNeural"


async def gerar_audio(texto, caminho_saida="static/audio/maiia.mp3"):

    if not texto or not texto.strip():
        raise ValueError("Não existe texto para converter em áudio.")

    destino = Path(caminho_saida)
    destino.parent.mkdir(parents=True, exist_ok=True)

    try:
        comunicador = edge_tts.Communicate(
            text=texto,
            voice=VOZ
        )

        await comunicador.save(str(destino))

        return destino

    except Exception as erro:
        raise RuntimeError(
            f"Erro ao gerar áudio: {erro}"
        ) from erro
