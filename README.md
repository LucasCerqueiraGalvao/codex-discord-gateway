# Discord Codex Gateway

Bot Discord local que funciona como ponte para o Codex rodando no seu PC.

## O que ele faz hoje

- Escuta mensagens no canal configurado.
- Aceita mensagens apenas do seu `DISCORD_ALLOWED_USER_ID`.
- Qualquer mensagem normal no canal vira prompt para o Codex.
- Comandos disponiveis:
  - `!ping`
  - `!codex <texto>` (opcional)
  - `!help`
  - `!baixo`, `!medio`, `!alto`, `!altissimo` (trocam o nivel de raciocinio)
  - `!status` (mostra configuracao atual)
  - `!timeout <segundos>` (altera timeout e salva no `.env`)
  - `!reiniciar` (reinicia o processo do bot)
  - `!comandos` (lista de exemplos prontos)
- Processa anexos da mensagem (ex: `txt`, `py`, `pdf`, `csv`, imagens):
  - imagens sao enviadas via `--image` para o Codex
  - arquivos sao baixados localmente e repassados por caminho
- Roda em segundo plano via tray app (icone na bandeja do Windows).
- Salva logs locais:
  - `logs/bot.log` (bot)
  - `logs/history.jsonl` (historico)
  - `logs/tray.log` (launcher de bandeja)

## Estrutura

```text
.
|-- assets/
|   `-- codex-gateway-icon-final.png
|-- src/
|   |-- attachments.py
|   |-- bot.py
|   |-- codex_bridge.py
|   |-- config.py
|   |-- history_log.py
|   |-- text_utils.py
|   `-- tray_app.py
|-- scripts/
|   |-- install-startup-task.ps1
|   |-- remove-startup-task.ps1
|   |-- run-tray.ps1
|   |-- run.ps1
|   |-- setup.ps1
|   `-- stop-tray.ps1
|-- .env.example
|-- .gitignore
|-- README.md
`-- requirements.txt
```

## Setup

```powershell
cd C:\Users\lucas\Documents\Projects\personal\codex-discord-gateway
.\scripts\setup.ps1
```

Depois, edite `.env`.

## Variaveis importantes do .env

- `DISCORD_BOT_TOKEN`
- `DISCORD_ALLOWED_USER_ID`
- `DISCORD_ALLOWED_CHANNEL_ID`
- `CODEX_CMD`
- `CODEX_TIMEOUT_SECONDS`
- `CODEX_WORKDIR`
- `ATTACHMENTS_TEMP_DIR` (pasta temporaria dos anexos)
- `ATTACHMENTS_MAX_MB` (limite por anexo)
- `ATTACHMENTS_KEEP_FILES` (`true/false`, manter ou limpar anexos apos resposta)

Recomendacao de `CODEX_CMD`:

```text
codex exec --skip-git-repo-check --json --sandbox danger-full-access -c model_reasoning_effort="medium"
```

## Rodar em segundo plano (bandeja)

Iniciar agora:

```powershell
.\scripts\run-tray.ps1
```

Parar tray + bot:

```powershell
.\scripts\stop-tray.ps1
```

## Iniciar automaticamente com o Windows

Instalar tarefa de logon (abre o tray app):

```powershell
.\scripts\install-startup-task.ps1
```

Remover a tarefa:

```powershell
.\scripts\remove-startup-task.ps1
```

## Teste rapido

1. Envie `!ping`.
2. Envie mensagem normal sem comando, por exemplo `responda apenas com OK`.
3. Envie `!help` para listar comandos.
4. Troque nivel com `!medio` (ou `!baixo`, `!alto`, `!altissimo`).
5. Veja status com `!status`.
6. Ajuste timeout com `!timeout 300`.
7. Teste anexos: envie uma imagem ou arquivo junto da mensagem.
