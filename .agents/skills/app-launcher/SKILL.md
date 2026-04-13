---
name: app-launcher
description: Resolver pedidos informais para abrir aplicativos, jogos, launchers, sites registrados ou ferramentas locais e acionar o alvo correto com seguranca. Usar esta skill quando o usuario pedir algo como abrir programa, jogo, launcher, app do trabalho, navegador com perfil conhecido ou atalho pessoal; especialmente quando ele usar apelidos, nomes vagos, referencias afetivas ou memoria incompleta, como "meu lolzinho", "o app da firma" ou "abre o Discord ai".
---

# App Launcher

## Overview

Traduzir um pedido natural de abertura em um alvo de execucao confiavel. Resolver aliases, escolher app ou perfil correto, aplicar politica de confirmacao e entregar uma execucao segura ou uma pergunta curta quando a ambiguidade ou o risco forem relevantes.

## Workflow

### 1. Extrair a intencao de abertura

Antes de lancar qualquer coisa, identificar:

- qual app, jogo, launcher ou site registrado o usuario provavelmente quis dizer
- se ele quer apenas abrir o programa ou abrir com perfil, conta, argumento ou destino especifico
- se o pedido cita contexto temporal, como "estou chegando em casa", "abre rapidinho" ou "deixa preparado"
- se ha sinais de que o pedido envolve algo sensivel, como conta corporativa, admin, terminal ou acesso remoto

Reescrever mentalmente o pedido como uma consulta estruturada. Exemplo:

- "abre meu lolzinho" -> alias afetivo, categoria: jogo, alvo provavel: League of Legends ou Riot Client
- "abre o Chrome da firma" -> app: navegador, contexto: perfil corporativo

### 2. Resolver pelo catalogo primeiro

Priorizar apps registrados em catalogo local, aliases conhecidos e perfis explicitamente configurados.

Ler [references/catalog-format.md](./references/catalog-format.md) se precisar entender ou consumir o formato esperado do catalogo.

Usar sinais nesta ordem:

1. alias exato ou muito forte
2. nome principal do app
3. categoria e contexto de uso
4. perfil, conta ou ambiente padrao associado
5. historico recente da conversa, se ajudar a desempatar

Nao sair procurando executaveis pelo disco inteiro como estrategia principal. Se nao houver alvo registrado ou descoberta segura, pedir registro ou confirmacao curta em vez de adivinhar.

### 3. Escolher o alvo e a forma de abertura

Depois de resolver o app, decidir como abrir:

- executavel local
- launcher intermediario
- atalho registrado
- URL ou protocolo customizado
- perfil predefinido, se houver

Preservar os argumentos e perfis conhecidos do catalogo. Nao inventar flags nem tentar "melhorar" o comando sem evidencia.

### 4. Aplicar politica de seguranca

Usar [references/launch-policy.md](./references/launch-policy.md) para decidir se deve:

- abrir direto
- confirmar com pergunta curta
- recusar por falta de seguranca ou por alvo nao registrado

Pedir confirmacao quando houver:

- multiplos apps plausiveis
- mais de um perfil ou conta possivel
- app sensivel ou operacional
- argumentos com impacto relevante
- alvo nao registrado, mas parcialmente inferido

### 5. Entregar ou executar com clareza

Se a confianca for alta e a politica permitir, seguir com o alvo mais seguro registrado.

Se a confianca for media ou baixa, mostrar no maximo 2 candidatos e perguntar de forma fechada.

Se o pedido depender de cadastro inexistente, dizer exatamente o que falta, por exemplo alias, executavel, perfil ou URL registrada.

## Output

Responder de forma curta e operacional.

Quando a confianca for alta e a abertura for permitida:

```text
App identificado: <nome>
Alvo de execucao: <executavel, launcher, atalho ou URL>
Perfil/modo: <padrao ou perfil especifico>
Confianca: alta
Motivo: <1 ou 2 evidencias curtas>
```

Quando precisar confirmar:

```text
Apps mais provaveis:
1. <nome 1> - <motivo curto>
2. <nome 2> - <motivo curto>

Confirmacao necessaria: <pergunta curta e objetiva>
```

Quando faltar cadastro ou politica:

```text
Nao consegui abrir com seguranca.
Falta: <app registrado, alias, perfil, path ou politica>
Proximo passo: <o que precisa ser cadastrado ou confirmado>
```

## Guardrails

Nao adivinhar executavel ou path so porque o nome do app parece familiar.

Nao abrir app sensivel, administrativo ou com perfil ambiguo sem confirmacao.

Nao usar argumentos nao registrados ou potencialmente destrutivos.

Nao trocar perfil pessoal por corporativo, ou vice-versa, sem evidencia.

Nao assumir que o mesmo apelido sempre aponta para o mesmo app se o catalogo mostrar mais de um candidato plausivel.

Nao tratar browser generico como suficiente quando o pedido implicar perfil ou conta especifica.

## Examples

Pedido:

`cara abre o meu lolzinho que eu to chegando em casa`

Boa execucao:

- resolver alias para o jogo ou launcher registrado
- escolher o alvo padrao associado ao alias
- abrir sem confirmacao se houver cadastro forte e risco baixo

Pedido:

`abre o Chrome da firma no e-mail`

Boa execucao:

- localizar o navegador e o perfil corporativo registrados
- abrir o perfil correto
- confirmar se houver mais de um perfil corporativo ou mais de uma URL plausivel

Pedido:

`abre aquele terminal admin`

Boa execucao:

- reconhecer alto risco
- exigir confirmacao explicita antes de qualquer execucao

## References

Ler estes arquivos somente quando fizer sentido:

- [references/catalog-format.md](./references/catalog-format.md): formato recomendado para registrar apps, aliases, perfis e destinos de abertura
- [references/launch-policy.md](./references/launch-policy.md): regras de confirmacao, bloqueio e abertura automatica por nivel de risco
