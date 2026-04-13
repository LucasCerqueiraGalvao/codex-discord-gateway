# Triage and Correlation

Usar este guia para encontrar sinal util sem se perder em volume.

## Ordem de triagem

1. Comecar pelo sintoma reportado e pelo horario aproximado.
2. Escolher a fonte de log mais perto do fluxo afetado.
3. Procurar eventos imediatamente antes, durante e depois do sintoma.
4. Correlacionar por timestamp, request_id, job_id, user_id, canal, arquivo ou processo.
5. Expandir a janela somente se a primeira leitura nao bastar.

## Bons alvos iniciais

- stack trace do momento da falha
- logs com `error`, `warn`, `timeout`, `retry`, `failed`, `exception`
- output do processo principal
- logs do worker ou fila ligada ao sintoma
- arquivos e streams mencionados pelo workspace-context

## Pistas fortes

- timeout seguido de retry ou cancelamento
- warning recorrente antes do erro fatal
- mismatch de contrato ou parse error
- queda de dependencia externa
- fila crescendo sem consumo
- inicio de fluxo sem evento de conclusao correspondente

## Pistas fracas

- mensagens genéricas sem relacao temporal
- log de bootstrap sem conexao com o sintoma
- erro antigo fora da janela investigada

## Regra pratica

Nao colecionar logs. Monte uma narrativa curta:

`evento de entrada -> processamento -> degradacao -> falha ou ausencia de conclusao`
