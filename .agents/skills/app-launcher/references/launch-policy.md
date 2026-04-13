# Launch Policy

Usar esta politica para decidir quando abrir direto, quando confirmar e quando bloquear.

## Pode abrir direto

Abrir sem confirmacao quando houver:

- alias forte ou nome exato
- alvo registrado e estavel
- risco baixo
- nenhum perfil, conta ou argumento ambiguo

Exemplos comuns:

- jogos e launchers pessoais registrados
- Discord, Spotify, VS Code, navegador padrao sem perfil especial

## Deve confirmar

Confirmar com pergunta curta quando houver:

- dois apps plausiveis para o mesmo apelido
- mais de um perfil ou conta possivel
- URL ou destino ambiguo
- `risk_level` medio
- app de trabalho, banco, VPN, acesso remoto ou operacao sensivel

Pergunta boa:

`Voce quis abrir o Chrome pessoal ou o Chrome da firma?`

## Deve bloquear ate ter cadastro ou aprovacao

Nao abrir automaticamente quando houver:

- alvo nao registrado
- comando administrativo
- terminal elevado
- argumentos customizados nao cadastrados
- `risk_level` alto com impacto relevante

Nesses casos, dizer o que falta e pedir confirmacao explicita ou cadastro do alvo.

## Regra de seguranca

Se o pedido misturar app + acao externa sensivel, como enviar algo, autenticar ou operar conta, a skill deve parar na abertura segura do app. A automacao posterior pertence a outra skill ou fluxo.
