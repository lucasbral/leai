# leai

CLI em Python para documentar Oracle Database em Markdown, com foco em consumo por RAG/IA.

## Instalação

```bash
pip install -e .
```

## Configuração (`leai.yml`)

```yaml
dsn: "localhost:1521/ORCLPDB1"
schema: "SEU_SCHEMA"
docPath: "./docs"

include:
  - EVENTO_FUNC
  - FUNCIONARIOS
exclude:
  - BIN$%
```


## Uso

```bash
leai
# ou
leai generate --config leai.yml
```

A geração preserva a seção manual entre os marcadores `<!-- LEAI:MANUAL:START -->` e `<!-- LEAI:MANUAL:END -->` em arquivos já existentes.
