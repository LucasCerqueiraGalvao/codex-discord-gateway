---
name: project-discovery
description: Inferir qual projeto local o usuario quis dizer quando ele falar de forma informal, ambigua ou por apelido. Usar esta skill quando o pedido depender de escolher o repositorio ou workspace correto antes de procurar arquivos, ler logs, editar codigo, abrir um projeto, rodar comandos ou preparar deploys; especialmente quando o usuario citar dominio de negocio, stack, cliente, funcionalidade, pasta parcial, apelido pessoal ou memoria incompleta em vez do nome exato do repositorio.
---

# Project Discovery

## Overview

Inferir o projeto mais provavel a partir de pistas incompletas e transferir um contexto de trabalho objetivo para a proxima etapa. Priorizar evidencias observaveis em vez de palpites, comparar candidatos antes de decidir e pedir confirmacao curta somente quando a ambiguidade continuar relevante.

## Workflow

### 1. Extrair pistas do pedido

Identificar o maximo de sinais concretos antes de procurar diretorios:

- apelidos ou nomes parciais do projeto
- dominio do problema ou negocio
- stack citada ou inferida
- tecnologias, servicos ou vendors mencionados
- verbos que indicam a tarefa seguinte, como editar, debugar, logar ou deployar
- qualquer referencia temporal ou de historico recente

Reescrever mentalmente o pedido como uma consulta estruturada. Exemplo:

- "o scrapper dos armadores" -> dominio: shipping/logistica, intencao: scraper, apelido: armadores
- "aquele bot do Discord" -> dominio: Discord, tipo de projeto: bot, possivel runtime: Python ou Node

### 2. Montar o espaco de busca

Buscar candidatos nesta ordem:

1. Catalogos de projetos ja mantidos pelo usuario, se existirem.
2. Workspaces e repositorios recentes mencionados na conversa atual.
3. Diretorios de projetos conhecidos do usuario.
4. Repositorios cujos nomes, README, manifests ou scripts combinem com as pistas.

Ler [references/catalog-format.md](./references/catalog-format.md) se houver um catalogo local disponivel ou se for preciso entender o formato esperado.

Nao assumir que o nome da pasta basta. Um apelido informal pode apontar para um repositorio com nome tecnico, nome de cliente, codinome interno ou um monorepo.

### 3. Ranqueiar candidatos antes de abrir arquivos demais

Gerar pelo menos 3 candidatos quando o espaco de busca permitir. Ordenar por combinacao de sinais:

- match direto de alias ou nome parcial
- match de dominio no README ou descricao
- match de stack, framework ou servicos mencionados
- presenca de arquivos-chave coerentes com a tarefa
- proximidade com conversas ou sessoes recentes

Evitar consumir contexto com leitura ampla demais. Primeiro ranquear; depois aprofundar apenas nos melhores candidatos.

### 4. Inspecionar os melhores candidatos

Para os 3 melhores:

- ler README, manifest principal ou arquivo de entrada
- identificar objetivo do projeto em 1 frase
- anotar 2 ou 3 evidencias objetivas
- descartar rapido candidatos que so batem pelo nome, mas nao pelo dominio

Ler [references/confidence-rubric.md](./references/confidence-rubric.md) para decidir quando seguir sozinho e quando confirmar.

### 5. Decidir com confianca graduada

Seguir sem perguntar quando houver alta confianca e evidencias convergentes.

Pedir confirmacao curta quando:

- houver 2 candidatos plausiveis com sinais proximos
- o pedido seguinte puder causar alteracao relevante no lugar errado
- a pista principal vier de memoria vaga, sem alias forte

Fazer pergunta fechada e objetiva. Exemplo:

`Voce quis dizer o projeto X (scraper maritimo em Python) ou o projeto Y (dashboard de armadores em Next.js)?`

Nao despejar uma lista longa de pastas. Mostrar so os 2 ou 3 candidatos mais provaveis, com diferencas uteis.

### 6. Entregar handoff claro para a proxima skill ou tarefa

Depois de escolher o projeto, registrar um resumo curto com:

- caminho do projeto
- nome do projeto escolhido
- por que ele foi escolhido
- grau de confianca
- proximas fontes de contexto recomendadas, como README, manifests, logs ou entrypoints

## Output

Responder de forma curta e orientada a acao.

Quando a confianca for alta, usar este formato:

```text
Projeto identificado: <nome>
Caminho: <path>
Confianca: alta
Evidencias: <2 ou 3 evidencias curtas>
Proximo contexto sugerido: <README, entrypoint, logs, etc.>
```

Quando a confianca for media ou baixa, usar este formato:

```text
Projetos mais provaveis:
1. <nome 1> - <motivo curto>
2. <nome 2> - <motivo curto>

Confirmacao necessaria: <pergunta curta e objetiva>
```

## Guardrails

Nao escolher projeto apenas porque o nome da pasta "parece certo".

Nao pedir confirmacao cedo demais. Primeiro procurar evidencias em nome, README, manifests e contexto recente.

Nao pedir uma pergunta aberta do tipo "qual deles?" sem resumir diferencas relevantes.

Nao continuar para mudancas destrutivas ou deploy em confianca baixa.

Nao tratar monorepo como resposta suficiente; identificar tambem o pacote, app ou subpasta mais provavel quando isso importar para a tarefa seguinte.

## Examples

Pedido:

`fala meu codex amigo, ta ligado o projeto do scrapper dos armadores?`

Boa execucao:

- procurar aliases e projetos relacionados a shipping/logistica/scraping
- comparar README e manifests dos top candidatos
- escolher direto se um deles tiver scraper maritimo explicito
- confirmar apenas se houver outro projeto de armadores com sinais proximos

Pedido:

`abre aquele projeto do gateway do Discord e ve por que o audio nao sobe`

Boa execucao:

- priorizar projetos com Discord, gateway, bot ou transcricao de audio
- escolher o repo com pipeline de anexos/audio coerente
- sugerir leitura imediata de README, configuracao de audio e logs

## References

Ler estes arquivos somente quando fizer sentido:

- [references/catalog-format.md](./references/catalog-format.md): formato recomendado para catalogos de projetos, aliases e sinais de descoberta
- [references/confidence-rubric.md](./references/confidence-rubric.md): criterios praticos para classificar confianca e decidir se deve confirmar
