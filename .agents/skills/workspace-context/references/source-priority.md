# Source Priority

Usar esta ordem para montar contexto rapido sem gastar leitura demais.

## Ordem base

1. `README*`
2. manifest principal do ecossistema
3. scripts e comandos declarados
4. entrypoints, apps ou servicos principais
5. configuracoes centrais
6. logs e traces, se a tarefa pedir investigacao

## Manifestos e sinais por ecossistema

- Node/TS:
  - `package.json`
  - `pnpm-workspace.yaml`, `turbo.json`, `nx.json`
  - `tsconfig.json`
  - `vite.config.*`, `next.config.*`
- Python:
  - `pyproject.toml`
  - `requirements.txt`
  - `poetry.lock`, `uv.lock`
  - `src/`, `app/`, `main.py`
- Go:
  - `go.mod`
  - `cmd/`
  - `internal/`
- Rust:
  - `Cargo.toml`
  - `src/main.rs`, `src/lib.rs`
- Containers and ops:
  - `docker-compose*.yml`, `compose.yaml`
  - `Dockerfile*`
  - `Makefile`
  - CI files

## Sinais de alto valor

- scripts nomeados com `dev`, `start`, `test`, `build`, `deploy`, `lint`
- arquivos de entrada claros
- docs ou manifests dentro de apps de monorepo
- arquivos de env exemplo
- configuracoes de observabilidade, filas, storage ou integracoes

## Sinais de alerta

- README genérico ou desatualizado
- multiplos manifests em paralelo
- pasta `apps/` ou `services/` sem app alvo obvio
- comandos conflitantes entre docs e scripts

Nesses casos, priorizar evidencias observaveis no repo em vez de confiar apenas na documentacao.
