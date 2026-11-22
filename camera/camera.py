
import cv2


def main():
    camera = cv2.VideoCapture(0)

    if not camera.isOpened():
        print("Não foi possível abrir a câmara.")
        return

    while True:
        sucesso, frame = camera.read()

        if not sucesso:
            print("Erro ao capturar imagem.")
            break

        cv2.imshow("SmartAccess - Camera", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    camera.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
