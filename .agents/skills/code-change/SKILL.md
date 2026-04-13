---
name: code-change
description: Investigar, alterar e validar codigo com a menor mudanca correta e com evidencias antes de encerrar. Usar esta skill quando o pedido envolver corrigir bug, ajustar comportamento, implementar melhoria pequena ou media, refatorar com impacto local, adaptar testes, mexer em configuracoes do projeto ou responder com uma mudanca concreta de codigo; especialmente depois que o projeto e o workspace ja estiverem claros via project-discovery e workspace-context.
---

# Code Change

## Overview

Transformar um pedido de alteracao em uma mudanca pequena, coerente e verificavel. Entender o comportamento atual antes de editar, escolher a superficie minima de mudanca, validar com o melhor sinal disponivel e reportar o que ficou comprovado, o que ficou assumido e qual risco residual permanece.

## Workflow

### 1. Fixar a intencao da mudanca

Antes de editar, esclarecer:

- qual comportamento atual parece errado ou insuficiente
- qual resultado o usuario espera
- qual area do sistema provavelmente participa do fluxo
- se a tarefa e bugfix, ajuste local, refactor ou extensao pequena

Se o projeto ou o contexto ainda estiverem nebulosos, voltar para `project-discovery` ou `workspace-context` em vez de improvisar.

### 2. Reconstituir o fluxo atual antes de tocar no arquivo

Ler o suficiente para entender o caminho real da mudanca:

- ponto de entrada da funcionalidade
- modulo ou funcao que implementa o comportamento
- contratos, tipos, schemas ou interfaces envolvidos
- testes existentes ou casos parecidos
- configuracoes ou flags que possam alterar o fluxo

Priorizar o caminho de execucao provavel, nao o arquivo que apenas "parece o certo" pelo nome.

### 3. Escolher a superficie minima de edicao

Restringir a mudanca ao menor conjunto de arquivos que resolva o problema sem esconder causas.

Usar [references/edit-surface.md](./references/edit-surface.md) para decidir:

- onde a mudanca deve acontecer
- quando manter a alteracao local
- quando expandir para testes, tipos, docs ou configs

Se houver mais de uma abordagem plausivel, preferir a que:

- preserva comportamento adjacente
- exige menos efeitos colaterais
- se encaixa no padrao do repo
- facilita validacao objetiva

### 4. Editar com disciplina

Ao editar:

- manter escopo pequeno
- nao misturar cleanup opcional com correcao principal
- preservar estilo e convencoes do repo
- adicionar comentario apenas quando a logica ficar realmente dificil de inferir
- atualizar testes, tipos, configs ou chamadas acopladas quando a mudanca exigir

Evitar "consertos" por suposicao. Se um valor, condicao ou contrato nao ficou claro, verificar mais contexto antes de mexer.

### 5. Validar em camadas

Escolher a melhor validacao disponivel para o risco da mudanca.

Usar [references/validation-ladder.md](./references/validation-ladder.md) para subir de nivel conforme necessario:

- leitura e checagem estatica
- teste focado
- suite relacionada
- build, lint ou typecheck
- verificacao manual guiada

Quando nao der para executar validacao real, dizer explicitamente o que impedir e qual seria o proximo comando mais confiavel.

### 6. Revisar por regressao local

Antes de fechar:

- confirmar se os chamadores continuam coerentes
- verificar se nomes, imports, tipos ou schemas ficaram consistentes
- checar se a mudanca quebra fluxos vizinhos obvios
- confirmar se a validacao executada realmente cobre o problema pedido

Nao assumir que "rodou um teste" significa que o bug foi coberto.

### 7. Encerrar com evidencias

Explicar de forma curta:

- o que mudou
- por que mudou ali
- como validou
- o que ainda nao foi provado

## Output

Responder de forma curta e orientada a entrega.

Usar este formato base:

```text
Mudanca aplicada: <resumo curto>
Arquivos principais: <arquivos alterados ou area>
Racional: <por que essa foi a superficie correta>
Validacao: <comandos, testes ou checagens executadas>
Risco residual: <nenhum ou o que ainda nao foi provado>
```

Se a mudanca nao puder ser concluida com seguranca, dizer por que a investigacao travou e qual evidencia faltou.

## Guardrails

Nao editar antes de entender o fluxo minimo envolvido.

Nao espalhar a mudanca por muitos arquivos sem justificativa.

Nao aproveitar a tarefa para fazer refactor cosmetico, renomeacao ampla ou cleanup oportunista.

Nao declarar sucesso sem evidencias de validacao proporcionais ao impacto.

Nao confiar apenas no nome do arquivo, no comentario do codigo ou no README se o fluxo observado disser outra coisa.

Nao deixar testes quebrados, imports invalidos ou tipos inconsistentes como "trabalho futuro" silencioso.

## Examples

Pedido:

`corrige esse bug de timeout no envio de audio`

Boa execucao:

- localizar o fluxo de timeout real
- entender se o problema nasce em config, fila, request ou chamada externa
- editar a menor superficie correta
- validar com teste focado ou reproducao guiada

Pedido:

`ajusta esse endpoint para aceitar mais um campo`

Boa execucao:

- localizar schema, handler e chamadores afetados
- editar contrato e implementacao juntos
- atualizar testes e validacoes relacionadas
- checar se tipos e serializacao continuam coerentes

## References

Ler estes arquivos somente quando fizer sentido:

- [references/edit-surface.md](./references/edit-surface.md): como escolher a menor superficie correta de mudanca
- [references/validation-ladder.md](./references/validation-ladder.md): como escalar validacao conforme risco, acoplamento e impacto
