# Installation

**LEAI** is distributed as a standard Python package and can be installed in several ways depending on your workflow.

---

## 📋 Prerequisites

* **Python:** Version 3.10 or higher (`3.10`, `3.11`, `3.12`, `3.13`).
* **Oracle Client:** LEAI uses the official `oracledb` driver in Thin Mode by default (no heavy Oracle Instant Client installation required). For advanced connections involving wallets or Kerberos/TCPS authentication, Thick Mode is supported.
* **Operating System:** Linux, macOS, or Windows.

---

## 📦 Installation Methods

### Option 1: Via `pip` (Recommended for Standard Usage)

```bash
pip install leai
```

### Option 2: Via `uv` (Ultra Fast)

If you use the modern Python package manager [uv](https://github.com/astral-sh/uv):

```bash
# As an isolated global tool:
uv tool install leai

# Or add it to an existing project:
uv add leai
```

### Option 3: Via `pipx` (Isolated CLI App)

If you want to run LEAI as an isolated system-wide command-line application:

```bash
pipx install leai
```

---

## 🔍 Verifying the Installation

After installation, verify that LEAI is available:

```bash
leai --help
```

You should see the complete list of available commands and global options:

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

### Environment Diagnostics with `leai doctor`

To verify database connectivity, catalog permissions, and optional AI dependencies:

```bash
leai doctor
```
