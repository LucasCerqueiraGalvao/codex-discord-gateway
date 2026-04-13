# Confidence Rubric

Usar esta rubrica para decidir se vale seguir direto ou se e melhor confirmar com o usuario.

## Alta confianca

Seguir sem confirmar quando houver:

- match forte de alias ou nome parcial
- dominio e stack coerentes
- README, manifest ou entrypoint confirmando o objetivo do projeto
- ausencia de candidato rival com evidencias parecidas

Resposta esperada:

- escolher o projeto
- explicar em 1 ou 2 frases por que ele venceu
- sugerir o proximo ponto de leitura ou acao

## Media confianca

Confirmar com pergunta curta quando houver:

- 2 candidatos plausiveis
- match razoavel de nome, mas dominio ainda ambigua
- contexto recente ajudando, mas sem evidencia documental suficiente

Resposta esperada:

- mostrar no maximo 2 ou 3 candidatos
- destacar a diferenca util entre eles
- pedir confirmacao fechada

## Baixa confianca

Nao agir no projeto ainda quando houver:

- muitos candidatos fracos
- nome vago sem pistas de dominio, stack ou historico
- repositorios sem README ou com sinais insuficientes

Resposta esperada:

- dizer que a confianca esta baixa
- mostrar os melhores palpites com reservas
- pedir uma pista adicional curta, como stack, cliente, pasta ou objetivo

## Regra de seguranca

Mesmo com alta confianca, confirmar antes de:

- deploy
- envios externos
- alteracoes destrutivas
- operacoes em projeto de producao ou cliente sensivel
