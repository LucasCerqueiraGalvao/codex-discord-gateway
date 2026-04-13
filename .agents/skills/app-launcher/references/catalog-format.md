# App Catalog Format

Usar este guia quando houver um catalogo local de apps ou quando for preciso criar um formato previsivel para a skill.

## Campos recomendados por app

- `id`: identificador estavel
- `name`: nome principal do app
- `aliases`: apelidos, variacoes e nomes informais
- `category`: jogo, navegador, chat, trabalho, media, utilitario, admin
- `launch_kind`: `executable`, `shortcut`, `uri`, `launcher`
- `target`: path do executavel, nome do atalho, URI ou launcher registrado
- `args`: argumentos padrao permitidos
- `cwd`: diretorio de trabalho, se precisar
- `profiles`: perfis conhecidos, contas ou modos permitidos
- `risk_level`: `low`, `medium`, `high`
- `confirm_required`: `true` ou `false`
- `signals`: pistas que ajudam a diferenciar o app de outros parecidos
- `summary`: descricao curta

## Exemplo de estrutura

```json
[
  {
    "id": "riot-league",
    "name": "League of Legends",
    "aliases": ["lol", "lolzinho", "league", "meu lolzinho"],
    "category": "game",
    "launch_kind": "launcher",
    "target": "riot-client",
    "args": [],
    "cwd": "C:/Riot Games/Riot Client",
    "profiles": ["default"],
    "risk_level": "low",
    "confirm_required": false,
    "signals": ["jogo", "riot", "league"],
    "summary": "Abre o Riot Client ou o fluxo padrao para League of Legends."
  }
]
```

## Boas praticas

- Registrar exatamente o jeito informal que o usuario fala.
- Separar perfis pessoais e corporativos quando isso importar.
- Nao cadastrar caminhos temporarios ou ambiguos.
- Preferir um alvo de execucao testado e estavel por app.
- Marcar apps sensiveis com `risk_level` alto e `confirm_required` verdadeiro.
