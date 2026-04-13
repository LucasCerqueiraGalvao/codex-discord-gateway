# Discord Codex Gateway

Bot Discord local que funciona como ponte para o Codex rodando no seu PC.

## O que ele faz hoje

- Escuta mensagens no canal configurado.
- Aceita mensagens apenas do seu `DISCORD_ALLOWED_USER_ID`.
- Qualquer mensagem normal no canal vira prompt para o Codex.
- Mantem uma sessao persistente do Codex por canal.
- Ainda guarda contexto curto local por canal como fallback auxiliar.
- Aceita audio/voice message como prompt (transcricao local e privada).
- Comandos disponiveis:
  - `!ping`
  - `!codex <texto>` (opcional)
  - `!help`
  - `!baixo`, `!medio`, `!alto`, `!altissimo` (trocam o nivel de raciocinio)
  - `!status` (mostra configuracao atual + metricas locais e metricas oficiais do Codex/VSCode)
- `!timeout <segundos>` (altera timeout e salva no `.env`)
- `!reiniciar` (reinicia o processo do bot)
- `!reset` / `!newchat` (desvincula a sessao atual e inicia uma nova conversa no proximo prompt)
- `!acoes` / `!actions` (lista as acoes padronizadas)
- `!comandos` (lista de exemplos prontos)
- Tenta executar acao padronizada primeiro (`find_file`, `upload_file`, `create_script`, `stable`) e usa Codex quando nao houver acao registrada.
- Processa anexos da mensagem (ex: `txt`, `py`, `pdf`, `csv`, imagens):
  - imagens sao enviadas via `--image` para o Codex
  - arquivos sao baixados localmente e repassados por caminho
- Processa anexos de audio (`ogg`, `mp3`, `wav`, `m4a`, `webm` etc.):
  - transcreve localmente com `faster-whisper`
  - publica a transcricao no canal
  - envia a transcricao para o pipeline normal de prompt -> Codex
- Roda em segundo plano via tray app (icone na bandeja do Windows).
- Salva logs locais:
  - `logs/bot.log` (bot)
  - `logs/history.jsonl` (historico)
  - `logs/tray.log` (launcher de bandeja)
- Cria um workspace local por canal em `runtime/channel_workspaces/`:
  - cada canal recebe um `conversation.md` com historico em Markdown
  - o `cwd` das sessoes do Discord passa a ser a raiz `runtime/channel_workspaces/`
  - cada canal fica vinculado a um `session_id` persistente salvo localmente
  - o bot indexa a thread no catalogo do Codex e normaliza os metadados internos para ela aparecer no app desktop
- Garante instancia unica para o bot/tray no Windows para evitar duplicidade acidental.
- Mantem um estado estavel por canal para reaproveitar prompts do fluxo `!stable`.

## Estrutura

```text
.
|-- .agents/
|   `-- skills/
|-- assets/
|   `-- codex-gateway-icon-final.png
|-- src/
|   |-- actions.py
|   |-- attachments.py
|   |-- audio_transcriber.py
|   |-- bot.py
|   |-- channel_sessions.py
|   |-- channel_workspace.py
|   |-- codex_bridge.py
|   |-- codex_official_status.py
|   |-- codex_session_catalog.py
|   |-- codex_thread_normalizer.py
|   |-- config.py
|   |-- history_log.py
|   |-- single_instance.py
|   |-- stable_state.py
|   |-- text_utils.py
|   `-- tray_app.py
|-- tests/
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
cd C:\caminho\para\codex-discord-gateway
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
- `AGENT_SCRIPTS_ROOT` (opcional, destino do `create_script`)
- `STABLE_AUTO_IMAGE_SCRIPT_PATH` (opcional, script usado pelo `!stable`)
- `ATTACHMENTS_TEMP_DIR` (pasta temporaria dos anexos)
- `ATTACHMENTS_MAX_MB` (limite por anexo)
- `ATTACHMENTS_KEEP_FILES` (`true/false`, manter ou limpar anexos apos resposta)
- `AUDIO_TRANSCRIPTION_ENABLED` (`true/false`, habilita STT local)
- `AUDIO_STT_MODEL` (ex.: `small`, `medium`; default `small`)
- `AUDIO_STT_LANGUAGE` (default `pt`; vazio = autodetect)
- `AUDIO_STT_DEVICE` (default `cpu`)
- `AUDIO_STT_COMPUTE_TYPE` (default `int8`)
- `AUDIO_MAX_DURATION_SECONDS` (limite por audio; default `60`)
- `AUDIO_RATE_LIMIT_PER_MINUTE` (limite de transcricoes por minuto; default `4`)
- `AUDIO_MAX_FILES_PER_MESSAGE` (maximo de audios por mensagem; default `3`)
- `TOKEN_BUDGET_TOTAL` (opcional, total de tokens para calcular restante/% no `!status`)
- `MESSAGE_BUDGET_TOTAL` (opcional, total de mensagens para calcular restante/% no `!status`)
- `CONTEXT_WINDOW_TOKENS` (opcional, tamanho da janela de contexto em tokens para mostrar % de uso)

Se esses 3 valores estiverem vazios, o `!status` ainda mostra os totais absolutos do gateway, mas sem percentuais/restante.
Para metricas de token por resposta, use `CODEX_CMD` com `--json` (recomendado).

Obs: o `!status` tambem consulta as metricas oficiais via `codex app-server` (ex.: limite de uso restante).

Recomendacao de `CODEX_CMD`:

```text
codex exec --skip-git-repo-check --json --sandbox danger-full-access -c model_reasoning_effort="medium"
```

Se `AGENT_SCRIPTS_ROOT` estiver vazio, o bot usa por padrao uma pasta `agent_scripts` na raiz de `Projects`.
Se `STABLE_AUTO_IMAGE_SCRIPT_PATH` estiver vazio, o bot tenta usar o script irmao em `../stable-diffusion/generate_auto_image.py`.

## Workspaces por canal

- O bot sempre cria uma pasta por canal em `runtime/channel_workspaces/`.
- O `cwd` das sessoes do Discord passa a apontar para a raiz `runtime/channel_workspaces/`.
- Dentro dela, o bot grava:
  - uma subpasta por canal com `README.md`
  - uma subpasta por canal com `conversation.md`
- Como o app do Codex costuma agrupar o historico pelo `cwd`, essas threads do Discord podem aparecer vinculadas ao workspace compartilhado de runtime em vez de ao repo raiz.

Isso ajuda a:

- manter um lugar estavel para historico local;
- consultar conversas antigas sem depender so do `.codex`;
- fazer as conversas do Discord pertencerem ao mesmo workspace visivel no app do Codex.

## Sessoes persistentes por canal

- A primeira mensagem de um canal cria uma nova sessao do Codex.
- As mensagens seguintes usam `codex exec resume <session_id>` para continuar a mesma thread.
- O mapeamento `canal -> session_id` fica salvo em `runtime/channel_sessions.json`.
- A cada resposta, o bot atualiza `%USERPROFILE%\.codex\session_index.jsonl` e normaliza a thread em `%USERPROFILE%\.codex\state_5.sqlite` e no rollout `.jsonl`.
- Essa normalizacao ajusta `source` para `vscode` e grava o `cwd` no formato canonico do Windows (`\\?\C:\...`) para a thread aparecer no app desktop.

Observacao importante:

- isso nao substitui as sessoes oficiais do Codex em `%USERPROFILE%\.codex`;
- depende de formatos internos do Codex, entao essa parte de indexacao nao e uma integracao oficial documentada;
- e tambem nao muda automaticamente o projeto real do seu codigo.
- Se voce quiser forcar uma thread nova no canal, use `!reset` ou `!newchat`.

## Skills locais no app do Codex

- Skills expostas a partir de `.agents/skills` podem aparecer na UI do Codex com o nome do projeto como origem.
- Esse rotulo de origem vem do caminho/repositorio onde a skill mora; ele nao e lido do texto da `SKILL.md`.
- Se a UI mostrar algo como `codex discord gateway` perto de uma skill local, isso normalmente significa apenas que a skill foi descoberta dentro deste repositorio.

## Audio (voice message)

- O bot baixa o anexo de audio no `runtime/attachments/<request_id>/`.
- Faz transcricao local com `faster-whisper` (sem abrir porta publica).
- Responde no canal com `Transcricao de audio: ...`.
- Em seguida envia essa transcricao para o mesmo fluxo atual do Codex.
- Se o audio passar do limite de duracao/tamanho, responde erro claro no canal.
- Se houver muitas transcricoes seguidas, aplica rate limit e pede para aguardar.

Observacao:
- Na primeira transcricao, o modelo pode ser baixado automaticamente e demorar mais.

## Acoes padronizadas

Voce pode chamar acoes de 3 jeitos:

- Mensagem normal: `find_file name="README.md" root="C:/caminho/para/projetos"`
- Com `!`: `!upload_file path="C:/caminho/para/relatorio.pdf"`
- Chamada explicita: `acao create_script name="merge_excels" language="python"`

Acoes atuais:

- `find_file`:
  - obrigatorio: `name`
  - opcionais: `root`, `max_results`
- `upload_file`:
  - obrigatorio: `path`
  - opcional: `caption`
- `create_script`:
  - obrigatorio: `name`
  - opcionais: `language` (`python`, `powershell`, `batch`), `content`, `filename`
  - regra fixa: sempre cria uma **nova pasta** em `AGENT_SCRIPTS_ROOT` (ou no padrao local do workspace)
- `stable`:
  - usa o ultimo bundle de prompts salvo para o canal
  - reaproveita `face_prompt`, `negative_prompt` e `face_negative_prompt`
  - exige `STABLE_AUTO_IMAGE_SCRIPT_PATH` valido (ou o fallback local padrao)

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
5. Liste as acoes com `!acoes`.
6. Teste `find_file name="README.md"`.
7. Teste `create_script name="teste_gateway" language="python"`.
8. Veja status com `!status`.
9. Ajuste timeout com `!timeout 300`.
10. Teste anexos: envie uma imagem ou arquivo junto da mensagem.
11. Teste voice message: envie um audio curto no canal.
12. Force uma nova thread com `!reset` ou `!newchat`.
