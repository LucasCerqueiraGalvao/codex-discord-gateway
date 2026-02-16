# Discord Codex Gateway

Bot Discord local que funciona como ponte para interagir com o Codex rodando no seu PC.

## Objetivo desta etapa

Primeiro incremento (testável):
- projeto versionado e organizado;
- comando `!ping` funcionando;
- filtro por usuário e canal permitidos via `.env`.

## Estrutura

```text
.
├─ src/
│  ├─ bot.py
│  └─ config.py
├─ scripts/
│  └─ run.ps1
├─ .env.example
├─ .gitignore
└─ requirements.txt
```

## Pré-requisitos

- Python 3.10+
- Bot criado no Discord Developer Portal com `MESSAGE CONTENT INTENT` habilitado.

## Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edite o `.env` com:
- `DISCORD_BOT_TOKEN`
- `DISCORD_ALLOWED_USER_ID`
- `DISCORD_ALLOWED_CHANNEL_ID` (opcional, mas recomendado)

## Rodar

```powershell
python -m src.bot
```

ou:

```powershell
.\scripts\run.ps1
```

## Teste rápido

No canal permitido:

```text
!ping
```

Resposta esperada:

```text
pong
```

## Próximo incremento

Adicionar o comando `!codex <texto>` para encaminhar prompt ao Codex local e retornar a resposta no Discord.
