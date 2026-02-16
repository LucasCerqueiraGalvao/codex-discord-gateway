# Discord Codex Gateway

Bot Discord local que funciona como ponte para o Codex rodando no seu PC.

## O que ele faz hoje

- Escuta comandos apenas no canal configurado.
- Aceita comandos apenas do seu `DISCORD_ALLOWED_USER_ID`.
- Comandos disponiveis:
  - `!ping`
  - `!codex <texto>`
- Executa o Codex local via CLI (`subprocess`), sem abrir porta e sem ngrok.
- Divide respostas longas em blocos para respeitar limite do Discord.
- Salva logs locais:
  - `logs/bot.log` (log tecnico)
  - `logs/history.jsonl` (historico de requests/responses)

## Estrutura

```text
.
|-- src/
|   |-- bot.py
|   |-- codex_bridge.py
|   |-- config.py
|   |-- history_log.py
|   `-- text_utils.py
|-- scripts/
|   |-- run.ps1
|   `-- setup.ps1
|-- .env.example
|-- .gitignore
|-- README.md
`-- requirements.txt
```

## Pre requisitos

- Windows + PowerShell
- Python 3.10+
- Bot criado no Discord Developer Portal
- `MESSAGE CONTENT INTENT` habilitado no bot
- Codex CLI instalado na maquina

## Setup

```powershell
cd C:\Users\lucas\Documents\Projects\personal\codex-discord-gateway
.\scripts\setup.ps1
```

Depois, edite `.env`.

## Variaveis do .env

Use `.env.example` como base.

- `DISCORD_BOT_TOKEN`: token do bot
- `DISCORD_ALLOWED_USER_ID`: seu user id
- `DISCORD_ALLOWED_CHANNEL_ID`: canal permitido
- `CODEX_CMD`: opcional; comando exato do Codex (se vazio, tenta fallback automatico)
- `CODEX_TIMEOUT_SECONDS`: timeout da chamada do Codex
- `CODEX_WORKDIR`: diretorio de execucao do Codex (vazio = diretorio atual)
- `DISCORD_CHUNK_SIZE`: tamanho maximo por mensagem (100 a 2000, recomendado 1900)
- `LOG_LEVEL`: nivel de log (`INFO`, `DEBUG`, etc)
- `LOG_DIR`: pasta dos logs

## Como o comando do Codex e detectado

Se `CODEX_CMD` estiver vazio, o bot tenta nesta ordem:

1. `codex exec --skip-git-repo-check --json`
2. `codex exec --json`
3. `codex exec --skip-git-repo-check`
4. `codex exec`

No primeiro que funcionar, ele reutiliza esse comando nas proximas chamadas.

## Rodar

```powershell
.\scripts\run.ps1
```

## Teste incremental

1. Teste conectividade:
   - envie `!ping`
   - esperado: `pong`
2. Teste ponte com Codex:
   - envie `!codex responda apenas com OK`
   - esperado: resposta com `OK`

## Seguranca

- Nao abre portas locais e nao expoe endpoint publico.
- Ignora comandos de qualquer usuario diferente do configurado.
- Pode restringir tambem por canal com `DISCORD_ALLOWED_CHANNEL_ID`.
- `.env` esta no `.gitignore`.
