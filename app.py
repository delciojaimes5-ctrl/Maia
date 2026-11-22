
import os
from pathlib import Path

import cv2
import numpy as np
from dispositivos.arduino import Arduino
from dotenv import load_dotenv
from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    session,
    redirect,
    url_for,
    send_from_directory
)
from werkzeug.security import generate_password_hash

from banco.conexao import obter_conexao
from banco.embeddings import guardar_embedding
from reconhecimento.reconhecedor import ReconhecedorFacial

from assistente.maiia import cumprimentar, processar_audio


# =========================================================
# CONFIGURAÇÃO
# =========================================================

load_dotenv()

app = Flask(__name__)

app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY")
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

if not app.config["SECRET_KEY"]:
    raise RuntimeError(
        "FLASK_SECRET_KEY não está definida no ficheiro .env"
    )

reconhecedor = ReconhecedorFacial()
arduino = Arduino()
RAIZ = Path(__file__).resolve().parent
PASTA_AUDIO = RAIZ / "static" / "audio"
PASTA_AUDIO.mkdir(parents=True, exist_ok=True)

# Histórico temporário da Maiia.
# Será perdido quando o servidor reiniciar.
HISTORICOS = {}
PENDENTES_LAMPADAS = {}

# =========================================================
# FUNÇÕES AUXILIARES
# =========================================================

def obter_imagem_recebida(nome_campo="imagem"):
    """
    Recebe uma imagem enviada pelo frontend e converte-a
    para o formato OpenCV.
    """

    if nome_campo not in request.files:
        raise ValueError("Nenhuma imagem foi recebida.")

    ficheiro = request.files[nome_campo]

    if ficheiro.filename == "":
        raise ValueError("Nenhum ficheiro foi selecionado.")

    dados = np.frombuffer(ficheiro.read(), dtype=np.uint8)
    imagem = cv2.imdecode(dados, cv2.IMREAD_COLOR)

    if imagem is None:
        raise ValueError("A imagem recebida é inválida.")

    return imagem


def buscar_usuario_por_id(usuario_id):
    """
    Procura um utilizador na base de dados pelo ID.
    """

    conexao = obter_conexao()
    cursor = conexao.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                id,
                nome,
                username,
                email,
                papel,
                estado,
                consentimento_biometrico
            FROM usuarios
            WHERE id = %s
            """,
            (usuario_id,)
        )

        return cursor.fetchone()

    finally:
        cursor.close()
        conexao.close()


def limpar_autenticacao_facial():
    """
    Remove os dados de autenticação facial da sessão.
    """

    session.pop("usuario_id", None)
    session.pop("autenticado_facial", None)


# =========================================================
# PÁGINA INICIAL
# =========================================================

@app.route("/")
def inicio():
    return redirect(url_for("cadastro"))


# =========================================================
# LOGIN FACIAL
# =========================================================

@app.route("/login")
def login():
    return render_template("index.html")


@app.route("/api/analisar", methods=["POST"])
def analisar():

    try:
        imagem = obter_imagem_recebida()

        resultado = reconhecedor.identificar(imagem)

        # ---------------------------------------------
        # NENHUMA PESSOA IDENTIFICADA
        # ---------------------------------------------

        if not resultado["identificado"]:

            mensagem = resultado.get("mensagem", "")

            # Distinguir ausência de rosto de vários rostos.
            if mensagem == "Nenhum rosto encontrado.":

                session["ultimo_reconhecimento"] = "sem_rosto"
                session.pop("ultimo_reconhecido_id", None)
                limpar_autenticacao_facial()

                resultado["situacao"] = "sem_rosto"

            elif mensagem == "Foi encontrado mais de um rosto.":

                session["ultimo_reconhecimento"] = "multiplos_rostos"
                session.pop("ultimo_reconhecido_id", None)
                limpar_autenticacao_facial()

                resultado["situacao"] = "multiplos_rostos"

            else:
                # Exemplo: pessoa desconhecida.
                session["ultimo_reconhecimento"] = "desconhecido"
                session.pop("ultimo_reconhecido_id", None)
                limpar_autenticacao_facial()

                resultado["situacao"] = "desconhecido"

            return jsonify(resultado), 200

        # ---------------------------------------------
        # PESSOA IDENTIFICADA
        # ---------------------------------------------

        usuario = resultado["usuario"]

        usuario_id = usuario["id"]
        autorizado = usuario["estado"] == "ativo"

        session["ultimo_reconhecimento"] = "conhecido"
        session["ultimo_reconhecido_id"] = usuario_id

        if autorizado:
            session["usuario_id"] = usuario_id
            session["autenticado_facial"] = True
        else:
            limpar_autenticacao_facial()

        return jsonify({
            "identificado": True,
            "autorizado": autorizado,
            "situacao": "conhecido",
            "mensagem": (
                "Acesso autorizado."
                if autorizado
                else "Acesso recusado: utilizador bloqueado."
            ),
            "similaridade": resultado["similaridade"],
            "usuario": usuario
        }), 200

    except ValueError as erro:
        return jsonify({
            "erro": str(erro)
        }), 400

    except Exception:
        app.logger.exception(
            "Erro durante o reconhecimento facial."
        )

        return jsonify({
            "erro": (
                "Ocorreu um erro interno durante "
                "o reconhecimento facial."
            )
        }), 500


# =========================================================
# CADASTRO DE UTILIZADORES
# =========================================================

@app.route("/cadastro", methods=["GET", "POST"])
def cadastro():

    if request.method == "GET":
        return render_template("cadastro.html")

    nome = request.form.get("nome", "").strip()
    username = request.form.get("username", "").strip()
    email = request.form.get("email", "").strip()
    senha = request.form.get("password", "")
    confirmar_senha = request.form.get("confirmar_password", "")

    if not all([nome, username, email, senha, confirmar_senha]):
        return render_template(
            "cadastro.html",
            erro="Preenche todos os campos."
        )

    if senha != confirmar_senha:
        return render_template(
            "cadastro.html",
            erro="As palavras-passe não coincidem."
        )

    if len(senha) < 8:
        return render_template(
            "cadastro.html",
            erro="A palavra-passe deve ter pelo menos 8 caracteres."
        )

    password_hash = generate_password_hash(senha)

    conexao = obter_conexao()
    cursor = conexao.cursor()

    try:
        # Verificar se o username ou email já existem.
        cursor.execute(
            """
            SELECT id
            FROM usuarios
            WHERE username = %s OR email = %s
            """,
            (username, email)
        )

        existente = cursor.fetchone()

        if existente:
            return render_template(
                "cadastro.html",
                erro="Este nome de utilizador ou email já está registado."
            )

        cursor.execute(
            """
            INSERT INTO usuarios (
                nome,
                username,
                email,
                password_hash,
                papel,
                estado,
                consentimento_biometrico
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                nome,
                username,
                email,
                password_hash,
                "usuario",
                "ativo",
                0
            )
        )

        usuario_id = cursor.lastrowid
        conexao.commit()

        session.clear()
        session["usuario_id"] = usuario_id
        session["nome"] = nome

        return redirect(url_for("registo_facial"))

    except Exception:
        conexao.rollback()
        app.logger.exception("Erro durante o cadastro.")

        return render_template(
            "cadastro.html",
            erro="Não foi possível concluir o cadastro."
        )

    finally:
        cursor.close()
        conexao.close()


# =========================================================
# PÁGINA DE REGISTO FACIAL
# =========================================================

@app.route("/registo-facial")
def registo_facial():

    if "usuario_id" not in session:
        return redirect(url_for("cadastro"))

    return render_template(
        "registo_facial.html",
        nome=session.get("nome")
    )


# =========================================================
# REGISTAR ROSTO
# =========================================================

@app.route("/api/registar-rosto", methods=["POST"])
def registar_rosto():

    usuario_id = session.get("usuario_id")

    if not usuario_id:
        return jsonify({
            "sucesso": False,
            "mensagem": "Sessão inválida. Realiza o cadastro novamente."
        }), 401

    consentimento = request.form.get("consentimento")

    if consentimento != "sim":
        return jsonify({
            "sucesso": False,
            "mensagem": (
                "É necessário consentir o registo "
                "dos dados biométricos."
            )
        }), 400

    conexao = obter_conexao()
    cursor = conexao.cursor()

    try:
        imagem = obter_imagem_recebida()

        # Extrair o embedding facial.
        embedding = reconhecedor.extrair_embedding(imagem)

        # Guardar o embedding na tabela de embeddings.
        guardar_embedding(usuario_id, embedding)

        # Atualizar o consentimento biométrico.
        cursor.execute(
            """
            UPDATE usuarios
            SET
                consentimento_biometrico = 1,
                consentimento_em = NOW()
            WHERE id = %s
            """,
            (usuario_id,)
        )

        conexao.commit()

        session["registo_facial_concluido"] = True

        return jsonify({
            "sucesso": True,
            "mensagem": "Rosto registado com sucesso.",
            "redirect": url_for("sucesso")
        }), 200

    except ValueError as erro:
        conexao.rollback()

        return jsonify({
            "sucesso": False,
            "mensagem": str(erro)
        }), 400

    except Exception:
        conexao.rollback()
        app.logger.exception("Erro durante o registo facial.")

        return jsonify({
            "sucesso": False,
            "mensagem": "Não foi possível registar o rosto."
        }), 500

    finally:
        cursor.close()
        conexao.close()


# =========================================================
# PÁGINA DE SUCESSO
# =========================================================

@app.route("/sucesso")
def sucesso():

    if not session.get("registo_facial_concluido"):
        return redirect(url_for("cadastro"))

    conexao = obter_conexao()
    cursor = conexao.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                id,
                nome,
                username,
                email,
                papel,
                estado
            FROM usuarios
            ORDER BY id DESC
            """
        )

        usuarios = cursor.fetchall()

        return render_template(
            "sucesso.html",
            usuarios=usuarios
        )

    finally:
        cursor.close()
        conexao.close()


# =========================================================
# MAIIA - CUMPRIMENTO AUTOMÁTICO
# =========================================================

@app.route("/api/maiia/cumprimentar", methods=["POST"])
async def api_maiia_cumprimentar():

    tipo = session.get("ultimo_reconhecimento")

    try:

        # ---------------------------------------------
        # PESSOA CONHECIDA
        # ---------------------------------------------

        if tipo == "conhecido":

            usuario_id = session.get("ultimo_reconhecido_id")

            if not usuario_id:
                return jsonify({
                    "erro": "Não foi possível identificar o utilizador."
                }), 400

            usuario = buscar_usuario_por_id(usuario_id)

            if not usuario:
                return jsonify({
                    "erro": "Utilizador não encontrado."
                }), 404

            resultado = await cumprimentar(
                nome=usuario["nome"],
                conhecido=True
            )

        # ---------------------------------------------
        # PESSOA DESCONHECIDA
        # ---------------------------------------------

        elif tipo == "desconhecido":

            resultado = await cumprimentar(
                nome=None,
                conhecido=False
            )

        else:
            return jsonify({
                "erro": "Não existe uma pessoa identificada para cumprimentar."
            }), 400

        return jsonify({
            "mensagem": resultado["mensagem"],
            "audio_url": url_for(
                "audio_maiia",
                ficheiro=resultado["ficheiro"]
            )
        }), 200

    except Exception:
        app.logger.exception(
            "Erro ao gerar cumprimento da Maiia."
        )

        return jsonify({
            "erro": "Não foi possível gerar o cumprimento."
        }), 500


# =========================================================
# MAIIA - CONVERSAÇÃO POR ÁUDIO
# =========================================================

@app.route("/api/maiia/conversar", methods=["POST"])
async def api_maiia_conversar():

    # Verificar autenticação facial
    if not session.get("autenticado_facial"):
        return jsonify({
            "erro": "É necessário autenticar-se através do rosto."
        }), 401

    usuario_id = session.get("usuario_id")

    if not usuario_id:
        limpar_autenticacao_facial()

        return jsonify({
            "erro": "Sessão inválida."
        }), 401

    try:
        # Confirmar estado do utilizador
        usuario = buscar_usuario_por_id(usuario_id)

        if not usuario or usuario["estado"] != "ativo":
            limpar_autenticacao_facial()

            return jsonify({
                "erro": "Utilizador não autorizado."
            }), 403

        # Receber áudio
        arquivo = request.files.get("audio")

        if arquivo is None:
            return jsonify({
                "erro": "Nenhum áudio foi enviado."
            }), 400

        # Recuperar histórico e comando pendente do utilizador
        historico = HISTORICOS.get(usuario_id, [])

        comando_pendente = PENDENTES_LAMPADAS.get(usuario_id)

        print(
            "[APP] Comando pendente recuperado:",
            repr(comando_pendente)
        )

        # Processar áudio
        resultado = await processar_audio(
            arquivo,
            historico=historico,
            executar_comando=arduino.enviar_comando,
            comando_pendente=comando_pendente
        )

        # Atualizar histórico
        HISTORICOS[usuario_id] = resultado["historico"]

        # Guardar ou remover comando pendente
        novo_pendente = resultado.get("comando_pendente")

        if novo_pendente:
            PENDENTES_LAMPADAS[usuario_id] = novo_pendente
        else:
            PENDENTES_LAMPADAS.pop(usuario_id, None)

        print(
            "[APP] Novo comando pendente:",
            repr(novo_pendente)
        )

        # Responder ao frontend
        return jsonify({
            "texto_usuario": resultado["texto_usuario"],
            "resposta": resultado["resposta"],
            "audio_url": url_for(
                "audio_maiia",
                ficheiro=resultado["ficheiro"]
            )
        }), 200

    except ValueError as erro:
        return jsonify({
            "erro": str(erro)
        }), 400

    except Exception:
        app.logger.exception(
            "Erro durante a conversação com a Maiia."
        )

        return jsonify({
            "erro": "Ocorreu um erro ao processar a conversa."
        }), 500

# =========================================================
# MAIIA - DISPONIBILIZAR ÁUDIO
# =========================================================

@app.route("/api/maiia/audio/<path:ficheiro>")
def audio_maiia(ficheiro):

    return send_from_directory(
        PASTA_AUDIO,
        ficheiro,
        mimetype="audio/mpeg"
    )


# =========================================================
# TERMINAR AUTENTICAÇÃO
# =========================================================

@app.route("/api/logout", methods=["POST"])
def logout():

    usuario_id = session.get("usuario_id")

    if usuario_id:
        HISTORICOS.pop(usuario_id, None)

    session.clear()

    return jsonify({
        "sucesso": True,
        "mensagem": "Sessão terminada."
    }), 200

@app.route("/api/lampadas", methods=["POST"])
def controlar_lampadas():

    # 1. Verificar autenticação facial
    if not session.get("autenticado_facial"):
        return jsonify({
            "sucesso": False,
            "mensagem": "Autenticação facial necessária."
        }), 401

    # 2. Confirmar que o utilizador continua ativo
    usuario_id = session.get("usuario_id")
    usuario = buscar_usuario_por_id(usuario_id)

    if not usuario or usuario["estado"] != "ativo":
        limpar_autenticacao_facial()

        return jsonify({
            "sucesso": False,
            "mensagem": "Utilizador não autorizado."
        }), 403

    # 3. Receber o comando
    dados = request.get_json(silent=True)

    if not isinstance(dados, dict):
        return jsonify({
            "sucesso": False,
            "mensagem": "Pedido inválido."
        }), 400

    comando = dados.get("comando")

    comandos_permitidos = {
        "LAMP1_ON", "LAMP1_OFF",
        "LAMP2_ON", "LAMP2_OFF",
        "LAMP3_ON", "LAMP3_OFF",
        "ALL_ON", "ALL_OFF"
    }

    if comando not in comandos_permitidos:
        return jsonify({
            "sucesso": False,
            "mensagem": "Comando inválido."
        }), 400

    # 4. Enviar comando ao Arduino
    try:
        resposta = arduino.enviar_comando(comando)

        return jsonify({
            "sucesso": True,
            "comando": comando,
            "resposta": resposta
        }), 200

    except (ConnectionError, TimeoutError) as erro:
        return jsonify({
            "sucesso": False,
            "mensagem": str(erro)
        }), 503

# =========================================================
# EXECUTAR A APLICAÇÃO
# =========================================================

if __name__ == "__main__":

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )
