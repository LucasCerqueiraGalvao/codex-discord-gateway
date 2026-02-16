# Discord Codex Gateway

Bot Discord local que funciona como ponte para interagir com o Codex rodando no seu PC.

## Objetivo

Projeto incremental para:
- receber comandos no Discord;
- validar usuario/canal autorizados;
- encaminhar `!codex <texto>` para o Codex local via CLI;
- responder no mesmo canal.

## Estrutura

```text
.
|-- src/
|   |-- bot.py
|   |-- codex_bridge.py
|   `-- config.py
|-- scripts/
|   `-- run.ps1
|-- .env.example
|-- .gitignore
|-- README.md
`-- requirements.txt
```

## Pre requisitos

- Python 3.10+
- Bot criado no Discord Developer Portal
- `MESSAGE CONTENT INTENT` habilitado para o bot
- Codex CLI instalado no PC

## Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edite o `.env`:
- `DISCORD_BOT_TOKEN`: token do bot
- `DISCORD_ALLOWED_USER_ID`: seu user id do Discord
- `DISCORD_ALLOWED_CHANNEL_ID`: canal permitido (recomendado)
- `CODEX_CMD`: comando para chamar Codex (padrao: `codex exec --skip-git-repo-check --json`)
- `CODEX_TIMEOUT_SECONDS`: timeout da chamada do Codex
- `CODEX_WORKDIR`: diretorio onde o Codex sera executado (vazio usa o diretorio atual)

## Rodar

```powershell
python -m src.bot
```

ou:

```powershell
.\scripts\run.ps1
```

## Comandos

- `!ping` -> responde `pong`
- `!codex <texto>` -> envia o texto para o Codex local e devolve a resposta
