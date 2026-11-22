
import os

import mysql.connector
from dotenv import load_dotenv

# Carregar as variáveis do ficheiro .env
load_dotenv()


def obter_conexao():

    conexao = mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT")),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD")
    )

    return conexao
