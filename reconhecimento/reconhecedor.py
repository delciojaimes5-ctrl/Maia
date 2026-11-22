
from pathlib import Path

import cv2
import numpy as np


class ReconhecedorFacial:

    def __init__(self):

        # Caminho da pasta principal do projeto
        raiz = Path(__file__).resolve().parent.parent

        caminho_yunet = (
            raiz / "modelos" /
            "face_detection_yunet_2023mar.onnx"
        )

        caminho_sface = (
            raiz / "modelos" /
            "face_recognition_sface_2021dec.onnx"
        )

        # Verificar se os modelos existem
        if not caminho_yunet.exists():
            raise FileNotFoundError(
                "Modelo YuNet não encontrado."
            )

        if not caminho_sface.exists():
            raise FileNotFoundError(
                "Modelo SFace não encontrado."
            )

        # Carregar modelo de deteção
        self.detetor = cv2.FaceDetectorYN_create(
            str(caminho_yunet),
            "",
            (320, 320),
            0.9,
            0.3,
            5000
        )

        # Carregar modelo de reconhecimento
        self.reconhecedor = cv2.FaceRecognizerSF_create(
            str(caminho_sface),
            ""
        )

    def identificar(self, imagem, limiar=0.40):

        from banco.embeddings import listar_embeddings

        try:
            embedding_atual = self.extrair_embedding(imagem)

        except ValueError as erro:

            return {
                "identificado": False,
                "rosto_detectado": False,
                "mensagem": str(erro)
            }

        registos = listar_embeddings()

        if not registos:
            return {
                "identificado": False,
                "rosto_detectado": True,
                "mensagem": "Não existem utilizadores registados."
            }

        melhor_resultado = None
        maior_similaridade = -1.0

        for registo in registos:

            embedding_guardado = registo["embedding"]

            similaridade = self.reconhecedor.match(
                embedding_atual.reshape(1, -1),
                embedding_guardado.reshape(1, -1),
                cv2.FaceRecognizerSF_FR_COSINE
            )

            similaridade = float(similaridade)

            if similaridade > maior_similaridade:
                maior_similaridade = similaridade
                melhor_resultado = registo

        if maior_similaridade < limiar:
            return {
                "identificado": False,
                "rosto_detectado": True,
                "mensagem": "Pessoa desconhecida.",
                "similaridade": maior_similaridade
            }

        return {
            "identificado": True,
            "rosto_detectado": True,
            "mensagem": "Pessoa identificada.",
            "similaridade": maior_similaridade,
            "usuario": {
                "id": melhor_resultado["usuario_id"],
                "nome": melhor_resultado["nome"],
                "username": melhor_resultado["username"],
                "papel": melhor_resultado["papel"],
                "estado": melhor_resultado["estado"]
            }
        }

    def extrair_embedding(self, imagem):

        if imagem is None or imagem.ndim != 3:
            raise ValueError("Imagem inválida.")

        altura, largura = imagem.shape[:2]

        # Ajustar o tamanho de entrada do detetor
        self.detetor.setInputSize((largura, altura))

        # Detetar rostos
        _, rostos = self.detetor.detect(imagem)

        if rostos is None or len(rostos) == 0:
            raise ValueError("Nenhum rosto encontrado.")

        if len(rostos) > 1:
            raise ValueError(
                "Foi encontrado mais de um rosto."
            )

        # Alinhar o rosto
        rosto_alinhado = self.reconhecedor.alignCrop(
            imagem,
            rostos[0]
        )

        # Extrair embedding facial
        embedding = self.reconhecedor.feature(
            rosto_alinhado
        )

        return np.asarray(
            embedding,
            dtype=np.float32
        ).reshape(-1)
