# Project Catalog Format

Usar este guia quando houver um catalogo local de projetos ou quando for preciso criar um formato previsivel para discovery. O objetivo do catalogo e reduzir ambiguidade, nao substituir a leitura do repositorio.

## Campos recomendados por projeto

- `id`: identificador estavel
- `name`: nome principal do projeto
- `path`: caminho absoluto do workspace
- `aliases`: apelidos, nomes informais, nomes incompletos e variacoes comuns
- `domains`: negocio, cliente, area ou problema que o projeto atende
- `stack`: linguagens, frameworks, cloud e bancos relevantes
- `keywords`: palavras soltas que costumam aparecer nas conversas
- `entrypoints`: arquivos ou pastas que ajudam a validar rapidamente o contexto
- `summary`: resumo curto em 1 frase
- `signals`: pistas fortes que diferenciam este projeto de outros parecidos

## Exemplo de estrutura

```json
[
  {
    "id": "shipping-scraper",
    "name": "shipping-scraper",
    "path": "C:/Users/lucas/Documents/Projects/client/shipping-scraper",
    "aliases": ["scrapper dos armadores", "scraper maritimo", "projeto dos armadores"],
    "domains": ["shipping", "logistica", "armadores"],
    "stack": ["python", "playwright", "postgres"],
    "keywords": ["crawler", "manifesto", "porto", "schedule"],
    "entrypoints": ["README.md", "src/main.py", "src/spiders/"],
    "summary": "Coleta e normaliza dados de armadores e escalas maritimas.",
    "signals": ["tem spiders", "usa playwright", "fala de shipping lines no README"]
  }
]
```

## Ordem de uso

1. Usar aliases e domains para montar candidatos iniciais.
2. Usar stack e keywords para desempatar.
3. Usar entrypoints e summary para validacao rapida.
4. Abrir README ou arquivo-chave apenas dos melhores candidatos.

## Boas praticas

- Registrar como alias exatamente o jeito que o usuario fala.
- Incluir nomes vagos e imperfeitos, nao so o nome oficial do repositorio.
- Atualizar o catalogo quando um projeto novo passar a ser citado com frequencia.
- Preferir `signals` que ajudem a diferenciar projetos parecidos.
