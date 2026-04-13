# Validation Ladder

Usar esta escada para escolher validacao proporcional ao risco da mudanca.

## Nivel 1: Checagem estrutural

Usar quando a mudanca for pequena e local:

- leitura final do diff
- imports, nomes, tipos e chamadas coerentes
- formato e sintaxe plausiveis

## Nivel 2: Teste focado

Usar quando houver funcao, modulo ou caso reproduzivel claro:

- teste unitario especifico
- comando de teste em arquivo ou suite pequena
- reproducao local guiada do caso afetado

## Nivel 3: Validacao relacionada

Usar quando a mudanca tocar contratos, fronteiras ou mais de um modulo:

- suite relacionada
- lint
- typecheck
- build parcial ou total

## Nivel 4: Validacao operacional

Usar quando a mudanca tocar fluxo sensivel, integracao ou deploy:

- smoke test
- verificacao manual guiada
- logs
- ambiente de homologacao, se houver

## Regras

- Quanto maior o acoplamento, mais alto deve ser o nivel minimo.
- Quanto menos confiavel a evidencia, mais explicito deve ser o risco residual.
- Se nenhum teste puder rodar, dizer exatamente o que foi impedido e qual comando seria o melhor proximo passo.
