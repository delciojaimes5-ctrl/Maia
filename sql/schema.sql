-- =========================================================
-- SmartAccess / Maiia — esquema da base de dados
-- MySQL 8.0+
--   mysql -u root -p < sql/schema.sql
-- =========================================================

CREATE DATABASE IF NOT EXISTS smartaccess
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE smartaccess;

-- ---------------------------------------------------------
-- Utilizadores
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS usuarios (
    id                      INT UNSIGNED NOT NULL AUTO_INCREMENT,
    nome                    VARCHAR(120) NOT NULL,
    username                VARCHAR(60)  NOT NULL,
    email                   VARCHAR(180) NOT NULL,
    password_hash           VARCHAR(255) NOT NULL,
    papel                   ENUM('usuario', 'administrador') NOT NULL DEFAULT 'usuario',
    estado                  ENUM('ativo', 'bloqueado') NOT NULL DEFAULT 'ativo',
    consentimento_biometrico TINYINT(1)  NOT NULL DEFAULT 0,
    consentimento_em        DATETIME     NULL,
    criado_em               DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    UNIQUE KEY uq_usuarios_username (username),
    UNIQUE KEY uq_usuarios_email (email)
) ENGINE=InnoDB;

-- ---------------------------------------------------------
-- Embeddings faciais (SFace, vetor float32 de 128 dimensões)
-- Guardado como bytes crus: np.float32(128).tobytes()
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS embeddings_faciais (
    id          INT UNSIGNED NOT NULL AUTO_INCREMENT,
    usuario_id  INT UNSIGNED NOT NULL,
    modelo      VARCHAR(40)  NOT NULL DEFAULT 'SFace-2021dec',
    dimensao    SMALLINT UNSIGNED NOT NULL DEFAULT 128,
    embedding   BLOB         NOT NULL,
    criado_em   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    KEY idx_embeddings_usuario (usuario_id),
    KEY idx_embeddings_modelo (modelo),
    CONSTRAINT fk_embeddings_usuario
        FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
        ON DELETE CASCADE
) ENGINE=InnoDB;
