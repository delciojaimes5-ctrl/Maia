
import numpy as np

from banco.conexao import obter_conexao


MODELO_FACIAL = "SFace-2021dec"


def guardar_embedding(usuario_id, embedding):

    vetor = np.asarray(embedding, dtype=np.float32).reshape(-1)

    if vetor.size != 128:
        raise ValueError("Dimensão do embedding inválida.")

    if not np.isfinite(vetor).all():
        raise ValueError("O embedding contém valores inválidos.")

    conexao = obter_conexao()
    cursor = conexao.cursor(dictionary=True)

    try:
        # Confirmar o consentimento biométrico
        cursor.execute(
            """
            SELECT consentimento_biometrico
            FROM usuarios
            WHERE id = %s
            """,
            (usuario_id,)
        )

        usuario = cursor.fetchone()

        if usuario is None:
            raise ValueError("Utilizador não encontrado.")

        if not usuario["consentimento_biometrico"]:
            raise PermissionError(
                "O utilizador não autorizou o registo biométrico."
            )

        # Converter o vetor NumPy para bytes
        dados_embedding = vetor.tobytes()

        cursor.execute(
            """
            INSERT INTO embeddings_faciais
                (usuario_id, modelo, dimensao, embedding)
            VALUES (%s, %s, %s, %s)
            """,
            (
                usuario_id,
                MODELO_FACIAL,
                vetor.size,
                dados_embedding
            )
        )

        conexao.commit()

        return cursor.lastrowid

    except Exception:
        conexao.rollback()
        raise

    finally:
        cursor.close()
        conexao.close()


def listar_embeddings():

    conexao = obter_conexao()
    cursor = conexao.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                e.id,
                e.usuario_id,
                e.modelo,
                e.dimensao,
                e.embedding,
                u.nome,
                u.username,
                u.papel,
                u.estado,
                u.consentimento_biometrico
            FROM embeddings_faciais e
            INNER JOIN usuarios u
                ON e.usuario_id = u.id
            WHERE e.modelo = %s
            """,
            (MODELO_FACIAL,)
        )

        registos = cursor.fetchall()
        resultados = []

        for registo in registos:

            # Ignorar utilizadores sem consentimento biométrico
            if not registo["consentimento_biometrico"]:
                continue

            # Confirmar a dimensão esperada pelo SFace
            if registo["dimensao"] != 128:
                continue

            vetor = np.frombuffer(
                registo["embedding"],
                dtype=np.float32
            )

            if vetor.size != 128:
                continue

            if not np.isfinite(vetor).all():
                continue

            registo["embedding"] = vetor
            resultados.append(registo)

        return resultados

    finally:
        cursor.close()
        conexao.close()
