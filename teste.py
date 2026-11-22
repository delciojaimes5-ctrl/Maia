from dispositivos.arduino import Arduino
import time

arduino = Arduino()

comandos = [
    "LAMP1_ON",
    "LAMP1_OFF",
    "LAMP2_ON",
    "LAMP2_OFF",
    "LAMP3_ON",
    "LAMP3_OFF",
    "ALL_ON",
    "ALL_OFF"
]

try:
    for comando in comandos:
        resposta = arduino.enviar_comando(comando)

        print(f"{comando} -> {resposta}")

        time.sleep(1)

finally:
    arduino.fechar()