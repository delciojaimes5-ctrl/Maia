
import cv2
import numpy as np


class FaceDetector:

    def __init__(self):

        caminho = (
            cv2.data.haarcascades
            + "haarcascade_frontalface_default.xml"
        )

        self.modelo = cv2.CascadeClassifier(caminho)

        if self.modelo.empty():
            raise RuntimeError(
                "Não foi possível carregar o modelo facial."
            )

    def detectar(self, imagem):

        if not isinstance(imagem, np.ndarray):
            raise TypeError("A imagem deve ser um array NumPy.")

        if imagem.size == 0:
            raise ValueError("A imagem está vazia.")

        if imagem.ndim != 3 or imagem.shape[2] != 3:
            raise ValueError("A imagem deve possuir três canais BGR.")

        cinzento = cv2.cvtColor(
            imagem,
            cv2.COLOR_BGR2GRAY
        )

        rostos = self.modelo.detectMultiScale(
            cinzento,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(60, 60)
        )

        resultados = []

        for (x, y, largura, altura) in rostos:

            resultados.append({
                "x": int(x),
                "y": int(y),
                "largura": int(largura),
                "altura": int(altura)
            })

        return resultados
