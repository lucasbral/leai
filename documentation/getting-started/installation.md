# Instalação

O **LEAI** é distribuído como pacote Python e pode ser instalado de diversas formas, dependendo do seu fluxo de trabalho.

---

## 📋 Requisitos Prévios

* **Python:** Versão 3.10 ou superior (`3.10`, `3.11`, `3.12`, `3.13`).
* **Oracle Client:** O LEAI utiliza o driver oficial `oracledb` em modo Thin por padrão (não requer a instalação pesada do Oracle Instant Client). Para conexões avançadas com wallets ou autenticação Kerberos/TCPS, o modo Thick é suportado.
* **Sistema Operacional:** Linux, macOS ou Windows.

---

## 📦 Métodos de Instalação

### Opção 1: Via `pip` (Recomendado para Usuários)

```bash
pip install leai
```

### Opção 2: Via `uv` (Ultra Rápido)

Se você utiliza o gerenciador de pacotes moderno [uv](https://github.com/astral-sh/uv):

```bash
# Como ferramenta global isolada:
uv tool install leai

# Ou adicionar a um projeto existente:
uv add leai
```

### Opção 3: Via `pipx` (Executável Isolado no Sistema)

Se você deseja rodar o LEAI como CLI global sem poluir o ambiente Python do sistema operacional:

```bash
pipx install leai
```

---

## 🔍 Verificando a Instalação

Após instalar, execute:

```bash
leai --help
```

Você verá a lista completa de comandos e opções disponíveis:

```text
Usage: leai [OPTIONS] COMMAND [ARGS]...

  LEAI — Oracle Database Intelligence & Documentation Engine.

Options:
  --version  Show the version and exit.
  --help     Show this message and exit.

Commands:
  extract   Extract technical DDL and metadata from Oracle into raw JSON.
  annotate  Generate or update editable YAML business annotations.
  compile   Compile metadata and annotations into Markdown and Mermaid.
  trace     Inspect multi-level lineage dependencies for an object.
  enrich    AI-assisted automated enrichment of business descriptions.
  ask       Ask natural language questions about your database schema.
  chat      Start an interactive terminal conversation with AI tools.
  models    List, test and benchmark supported LLM providers.
  changes   Inspect schema drift and detect modifications.
  doctor    Diagnose database connectivity, permissions, and environment.
  init      Generate a starter configuration file (leai.yml).
```

### Diagnóstico de Ambiente com `leai doctor`

Para verificar se o seu ambiente possui todas as dependências e ferramentas necessárias:

```bash
leai doctor
```
