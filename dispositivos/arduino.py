
import serial
import threading
import time


class Arduino:
    def __init__(
        self,
        porta="/dev/ttyACM0",
        baudrate=9600,
        timeout=3
    ):
        self.porta = porta
        self.baudrate = baudrate
        self.timeout = timeout

        self.conexao = None
        self.lock = threading.Lock()

        self.comandos_permitidos = {
            "LAMP1_ON",
            "LAMP1_OFF",
            "LAMP2_ON",
            "LAMP2_OFF",
            "LAMP3_ON",
            "LAMP3_OFF",
            "ALL_ON",
            "ALL_OFF"
        }

    def conectar(self):
        if self.conexao and self.conexao.is_open:
            return

        self.conexao = serial.Serial(
            port=self.porta,
            baudrate=self.baudrate,
            timeout=self.timeout,
            write_timeout=self.timeout
        )

        # O Arduino pode reiniciar quando a porta abre.
        time.sleep(2)

        self.conexao.reset_input_buffer()

    def enviar_comando(self, comando):

        if comando not in self.comandos_permitidos:
            raise ValueError("Comando Arduino inválido.")

        with self.lock:
            try:
                self.conectar()

                mensagem = (comando + "\n").encode("utf-8")
                self.conexao.write(mensagem)

                if comando == "ALL_ON":
                    esperadas = [
                        "LAMP1:ON",
                        "LAMP2:ON",
                        "LAMP3:ON"
                    ]

                elif comando == "ALL_OFF":
                    esperadas = [
                        "LAMP1:OFF",
                        "LAMP2:OFF",
                        "LAMP3:OFF"
                    ]

                else:
                    lampada, estado = comando.split("_")
                    esperadas = [
                        f"{lampada}:{estado}"
                    ]

                respostas = []

                for _ in esperadas:
                    resposta = self.conexao.readline().decode(
                        "utf-8"
                    ).strip()

                    if not resposta:
                        raise TimeoutError(
                            "O Arduino não respondeu ao comando."
                        )

                    respostas.append(resposta)

                if respostas != esperadas:
                    raise ConnectionError(
                        f"Resposta inesperada do Arduino: {respostas}"
                    )

                return respostas

            except (serial.SerialException, OSError) as erro:
                self.fechar()

                raise ConnectionError(
                    f"Erro de comunicação com o Arduino: {erro}"
                ) from erro

    def fechar(self):
        if self.conexao and self.conexao.is_open:
            self.conexao.close()
