---
name: workspace-context
description: Montar um contexto operacional curto e acionavel para um projeto ou workspace ja escolhido. Usar esta skill quando o Codex precisar entender rapidamente objetivo do repo, stack, entrypoints, apps ou pacotes relevantes, comandos de execucao e teste, configuracoes, logs, superficies provaveis de edicao e proximas leituras antes de debugar, alterar codigo, investigar logs, responder perguntas sobre o repo ou preparar deploy. Se o projeto ainda nao estiver claro, usar project-discovery antes.
---

# Workspace Context

## Overview

Transformar um repositorio escolhido em um mapa de trabalho curto, confiavel e util para a tarefa seguinte. Priorizar sinais de alto valor, evitar leitura excessiva e entregar um handoff que ajude outra skill ou o fluxo principal a agir no lugar certo.

## Workflow

### 1. Confirmar o alvo de trabalho

Partir de um workspace, projeto ou subpasta ja identificada.

Se o pedido ainda estiver ambiguo sobre qual projeto usar, interromper este fluxo e voltar para `project-discovery`.

Antes de ler arquivos, esclarecer mentalmente:

- qual e o caminho alvo
- se o pedido mira o repo inteiro ou uma area especifica
- se ha indicio de monorepo, multi-app ou pasta de runtime separada

### 2. Ler somente fontes de alto sinal

Comecar pelo minimo necessario para entender o projeto:

- README principal
- manifest principal, como `package.json`, `pyproject.toml`, `requirements.txt`, `go.mod`, `Cargo.toml`
- scripts e comandos declarados
- pastas de entrada, apps ou servicos principais
- configuracoes de ambiente, build, teste e logs quando forem relevantes para a tarefa

Usar [references/source-priority.md](./references/source-priority.md) para decidir a ordem de leitura e o que procurar em cada tipo de arquivo.

Nao abrir muitas pastas genericamente. Ler primeiro o que ajuda a responder:

- o que este projeto faz
- como ele roda
- onde a tarefa provavelmente mora

### 3. Delimitar o contexto ativo

Se for monorepo, identificar o app, pacote ou servico mais provavel para o pedido atual.

Evitar resumir o monorepo inteiro quando a tarefa parece focada em:

- um app web especifico
- um servico de backend
- um worker, crawler ou job
- um pacote compartilhado
- uma area operacional, como logs, deploy ou config

Usar nome de pasta, scripts, dependencias, README e arquivos de entrada para apontar o alvo mais provavel.

### 4. Montar o mapa operacional

Gerar um contexto curto, mas suficiente para a proxima acao. Incluir:

- objetivo do projeto em 1 frase
- stack principal
- alvo ativo mais provavel
- caminhos importantes
- comandos uteis de rodar, testar, buildar ou debugar
- configuracoes e variaveis relevantes
- local provavel de logs
- superficies provaveis de edicao para a tarefa atual

Usar [references/context-checklist.md](./references/context-checklist.md) para nao esquecer campos importantes.

### 5. Sugerir a proxima leitura, nao tudo de uma vez

Encerrar apontando o proximo ponto de contexto mais valioso para a tarefa:

- arquivo de entrada
- modulo principal
- pasta do app relevante
- configuracao especifica
- log ou trace mais promissor

Entregar caminho e motivo. Isso reduz exploracao cega na etapa seguinte.

## Output

Responder de forma curta e orientada a trabalho.

Usar este formato base:

```text
Workspace identificado: <nome ou caminho>
Objetivo: <1 frase>
Stack: <linguagens/frameworks/infra>
Alvo ativo: <app, pacote, servico ou area>
Comandos uteis: <run/test/build/dev, se conhecidos>
Caminhos-chave: <2 a 5 caminhos>
Config e logs: <envs, arquivos, pasta de logs, se relevantes>
Superficies provaveis de edicao: <arquivos/pastas ou modulos>
Proxima leitura sugerida: <arquivo ou pasta> - <motivo>
```

Se houver incerteza material, dizer explicitamente o que falta. Exemplo:

`Alvo ativo ainda incerto entre api/ e worker/; a proxima leitura deve ser package.json e README de cada pasta.`

## Guardrails

Nao resumir o repositorio inteiro so porque ele e grande.

Nao listar dezenas de arquivos ou pastas sem hierarquia.

Nao assumir comando de execucao ou teste sem evidencias em scripts, manifests, docs ou convencoes fortes.

Nao ignorar `docker-compose`, `Makefile`, `Procfile`, `turbo.json`, `nx.json`, `compose.yaml`, arquivos de env ou scripts equivalentes quando eles forem claramente centrais.

Nao tratar README desatualizado como verdade absoluta se manifests e estrutura do repo contradisserem a documentacao.

Nao escolher um alvo ativo arbitrario em monorepo sensivel; se dois apps forem plausiveis, apontar isso e reduzir a ambiguidade antes de editar.

## Examples

Pedido:

`entra nesse repo e me contextualiza rapido antes da gente mexer no audio`

Boa execucao:

- ler README, manifests e qualquer configuracao de audio ou anexos
- identificar o servico ou modulo que processa audio
- resumir stack, comandos, caminhos-chave e logs relevantes
- sugerir a proxima leitura mais promissora para o bug

Pedido:

`qual e a parte desse monorepo que provavelmente cuida do deploy do dashboard?`

Boa execucao:

- localizar apps e scripts de deploy
- identificar o app do dashboard e a trilha de build/deploy ligada a ele
- evitar resumir outros apps nao relacionados

## References

Ler estes arquivos somente quando fizer sentido:

- [references/source-priority.md](./references/source-priority.md): ordem recomendada de leitura por tipo de repo e sinais que valem mais
- [references/context-checklist.md](./references/context-checklist.md): checklist curta do que um bom contexto de workspace deve entregar
