# SmartAccess / Maiia

Sistema de controlo de acesso por reconhecimento facial (Flask + OpenCV YuNet/SFace),
com base de dados MySQL, assistente de voz em português (Groq + edge-tts) e
controlo de lâmpadas por Arduino.

## Requisitos

- Python 3.11 ou superior
- MySQL 8.0 ou superior
- (opcional) Arduino ligado por USB para as lâmpadas

## Instalação

```bash
# 1. Ambiente virtual
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 2. Dependências
pip install -r requirements.txt

# 3. Base de dados
mysql -u root -p < sql/schema.sql

# 4. Configuração
cp .env.example .env
# edita o .env e preenche FLASK_SECRET_KEY, DB_* e GROQ_API_KEY
```

Gerar a chave de sessão:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

## Correr

```bash
python app.py
```

Abre em <http://127.0.0.1:5000>. A rota `/` redirecciona para `/cadastro`.

## Rotas

| Rota | Método | O que faz |
|---|---|---|
| `/` | GET | Redirecciona para o cadastro |
| `/login` | GET | Página de login facial |
| `/api/analisar` | POST | Identifica o rosto e autoriza/recusa o acesso |
| `/cadastro` | GET/POST | Registo de utilizador |
| `/registo-facial` | GET | Página de captura do rosto |
| `/api/registar-rosto` | POST | Extrai e guarda o embedding facial |
| `/sucesso` | GET | Página de acesso concedido |
| `/api/maiia/cumprimentar` | POST | Saudação falada da Maiia |
| `/api/maiia/conversar` | POST | Conversa por áudio com a Maiia |
| `/api/maiia/audio/<f>` | GET | Serve o áudio gerado |
| `/api/lampadas` | POST | Liga/desliga lâmpadas pelo Arduino |
| `/api/logout` | POST | Termina a sessão |

## Testes

Os comandos de voz têm uma bateria própria, sem servidor nem base de dados:

```bash
python testes/teste_comandos.py
```

## Estrutura

```
app.py                  rotas Flask e lógica de sessão
banco/                  conexão MySQL e embeddings faciais
reconhecimento/         deteção (YuNet) e reconhecimento (SFace)
assistente/             Maiia: comandos, transcrição, LLM (Groq) e voz (edge-tts)
testes/                 testes dos comandos de voz
dispositivos/           Arduino por série (LAMP1_ON … ALL_OFF)
camera/                 captura pela webcam
modelos/                modelos ONNX do OpenCV
sql/schema.sql          esquema da base de dados
templates/, static/     interface
```

## Notas

- Os modelos ONNX (YuNet e SFace) já estão em `modelos/`; sem eles a aplicação
  não arranca.
- O Arduino só é contactado quando se usa `/api/lampadas`. Sem hardware ligado,
  essa rota responde 503 e o resto da aplicação funciona normalmente.
- O assistente de voz precisa de `GROQ_API_KEY`. Sem ela, as páginas abrem mas
  as rotas da Maiia devolvem erro com a causa indicada.
- `static/audio/` guarda os mp3 gerados pela Maiia e não é limpo
  automaticamente.
