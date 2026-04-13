---
name: log-investigation
description: Investigar logs e traces para localizar o sinal mais relevante, correlacionar eventos com o sintoma reportado e explicar a hipotese mais forte com evidencias. Usar esta skill quando o pedido envolver erro, travamento, falha intermitente, timeout, regressao, comportamento estranho em runtime, alerta operacional, stack trace, arquivos de log, output de terminal ou telemetria local; especialmente depois que o projeto e o workspace ja estiverem claros via project-discovery e workspace-context.
---

# Log Investigation

## Overview

Transformar ruido operacional em um quadro objetivo do problema. Encontrar a fonte de log mais promissora, limitar a leitura a uma janela temporal util, separar sintoma de causa provavel e encerrar com evidencias, incertezas e proximo passo recomendado.

## Workflow

### 1. Fixar o sintoma e a janela de investigacao

Antes de ler logs, esclarecer:

- qual foi o sintoma observado
- quando ele aconteceu ou em que sequencia de acoes
- se ha request, job, usuario, canal, arquivo ou processo associado
- se o problema parece unico, recorrente ou intermitente

Se o pedido nao trouxer tempo exato, inferir uma janela curta e ajusta-la conforme as evidencias. Nao sair lendo log inteiro por padrao.

### 2. Escolher a fonte de log mais promissora

Partir do contexto do workspace para localizar:

- logs da aplicacao
- logs do processo ou terminal
- arquivos de erro
- stack traces
- logs de worker, fila, scheduler ou crawler
- observabilidade local relevante, se existir

Usar [references/triage-and-correlation.md](./references/triage-and-correlation.md) para priorizar onde procurar primeiro e como estreitar o foco.

Se houver varias fontes plausiveis, priorizar a que:

- esta mais perto do fluxo afetado
- tem timestamps confiaveis
- mostra falha, retry, excecao, timeout ou mismatch de contrato

### 3. Correlacionar eventos, nao linhas soltas

Ao investigar, procurar:

- primeiro sinal do sintoma
- evento imediatamente anterior
- erro, warning ou timeout relacionado
- retries, quedas de conexao, filas travadas ou falhas de parse
- divergencia entre inicio do fluxo e resultado final

Montar uma sequencia curta de eventos em vez de listar trechos desconexos.

### 4. Classificar a forca da evidencia

Separar:

- sintoma observado
- causa provavel
- suposicoes ainda nao comprovadas

Usar [references/evidence-grading.md](./references/evidence-grading.md) para graduar a confianca da analise.

Nao chamar de causa raiz aquilo que ainda e apenas correlacao fraca.

### 5. Entregar a leitura operacional

Encerrar com:

- o que os logs mostram com clareza
- qual hipotese e mais forte
- qual evidencia sustenta essa hipotese
- o que ainda falta provar
- proximo passo recomendado

Se o proximo passo for mudanca de codigo, entregar um handoff claro para `code-change`. Se o problema for de configuracao, ambiente ou operacao, dizer isso explicitamente.

## Output

Responder de forma curta e orientada a diagnostico.

Usar este formato base:

```text
Sintoma: <o que ocorreu>
Fonte analisada: <arquivo, comando, processo ou stream>
Janela relevante: <tempo, request, job ou trecho>
Sequencia observada: <2 a 5 eventos em ordem>
Hipotese mais forte: <causa provavel>
Evidencias: <2 ou 3 evidencias objetivas>
Confianca: <alta, media ou baixa>
Proximo passo: <leitura, validacao, config ou mudanca de codigo>
```

Se a confianca for baixa, dizer o que falta para aumentar a certeza:

`Confianca: baixa. Falta correlacionar com o log do worker e confirmar o request_id que dispara o timeout.`

## Guardrails

Nao ler log inteiro quando uma janela menor basta.

Nao confundir ausencia de erro explicito com ausencia de problema.

Nao declarar causa raiz sem correlacao temporal, contextual ou estrutural suficiente.

Nao listar dezenas de linhas de log sem resumir a sequencia relevante.

Nao partir para mudanca de codigo enquanto os logs ainda apontarem mais para ambiente, config, credencial, rede, fila ou processo.

Nao ignorar warnings ou retries apenas porque nao sao excecoes fatais; eles podem ser o sinal certo.

## Examples

Pedido:

`ve nesses logs por que o audio nao sobe`

Boa execucao:

- localizar logs do pipeline de upload/transcricao
- restringir ao horario da tentativa
- correlacionar recebimento do anexo, transcricao, envio e eventual timeout
- concluir se o gargalo esta em I/O, transcricao, limite, API ou timeout interno

Pedido:

`o worker travou de novo, acha o motivo`

Boa execucao:

- localizar log do worker e eventos imediatamente anteriores ao travamento
- procurar retry infinito, fila parada, excecao intermitente ou deadlock operacional
- separar claramente sintoma, hipotese forte e o que ainda precisa ser confirmado

## References

Ler estes arquivos somente quando fizer sentido:

- [references/triage-and-correlation.md](./references/triage-and-correlation.md): como escolher a fonte certa, limitar a janela e montar a sequencia relevante
- [references/evidence-grading.md](./references/evidence-grading.md): como graduar confianca e diferenciar evidencia forte de suposicao
