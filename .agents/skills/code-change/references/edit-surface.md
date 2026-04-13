# Edit Surface

Usar este guia para decidir onde a mudanca deve acontecer e evitar alterar o lugar errado.

## Ordem de preferencia

1. Corrigir na origem real do comportamento.
2. Corrigir no menor ponto compartilhado que resolve o problema.
3. Expandir para contratos, testes ou configs somente quando a mudanca exigir.

## Perguntas chave

- O bug nasce na entrada, na regra, na integracao ou na saida?
- Existe funcao, modulo ou helper central que varios chamadores usam?
- A mudanca deve ficar local ou precisa propagar contrato?
- Ha teste existente no mesmo nivel de responsabilidade?

## Sinais de boa superficie

- resolve a causa, nao apenas o sintoma visivel
- exige poucas adaptacoes laterais
- conversa com o padrao do repo
- permite validacao objetiva

## Sinais de ma superficie

- patch em camada errada so porque e mais facil
- condicao especial adicionada longe da causa
- duplicacao de logica ja existente
- alteracao grande para resolver efeito pequeno

## Regra pratica

Se a mudanca esta espalhando rapido, parar e verificar se existe um ponto mais central e mais limpo para corrigi-la.
