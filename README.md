# LEAI — Oracle Database Intelligence & Documentation Engine

**LEAI** (*Lê - Aí* in PT-BR) is an enterprise reverse engineering, impact analysis, and autonomous AI copilot engine for **Oracle Database**, specifically designed to power **Retrieval-Augmented Generation (RAG)**, **LLMs**, and software engineers maintaining complex database ecosystems.

> [!IMPORTANT]
> 🔒 **Security & Data Privacy Guarantee:**
>
> **LEAI NEVER accesses, reads, or extracts business data (table records or rows) stored in the database.**
> It strictly reads **data dictionary metadata and DDL definitions**: tables, column types, primary/foreign keys, views, materialized views, stored procedures, packages, triggers, indexes, and synonyms.
>
> 💡 **A database user with metadata-only / audit permissions (such as `SELECT ANY DICTIONARY` or read access to `ALL_*` catalog views) is 100% sufficient.** This ensures full enterprise security and compliance (LGPD / GDPR / SOC2) with zero risk of exposing confidential or sensitive business data.

---

## 📑 Table of Contents / Índice

- [📌 What Is It?](#-what-is-it)
- [⚙️ How It Works (Pipeline)](#️-how-it-works)
- [🤖 Autonomous Agent & Tool Calling Engine](#-autonomous-agent--tool-calling-engine)
- [🔗 Transparent Synonym Resolution](#-transparent-synonym-resolution)
- [🚀 Quickstart: Using LEAI in Any Project](#-quickstart-using-leai-in-any-project)
  - [Step 1: Install LEAI](#step-1-install-leai-via-pip-or-uv)
  - [Step 2: Initialize Configuration](#step-2-initialize-your-project-directory)
  - [Step 3: Run and Explore](#step-3-run-and-explore)
- [📖 CLI Command Reference](#-cli-command-reference)
  - [1. `leai` (or `leai generate`)](#1-leai-or-leai-generate)
  - [2. `leai extract`](#2-leai-extract)
  - [3. `leai annotate`](#3-leai-annotate)
  - [4. `leai compile`](#4-leai-compile)
  - [5. `leai trace <OBJECT>`](#5-leai-trace-object)
  - [6. `leai enrich`](#6-leai-enrich)
  - [7. `leai ask <QUESTION>`](#7-leai-ask-question)
  - [8. `leai chat`](#8-leai-chat)
  - [9. `leai models`](#9-leai-models)
  - [10. `leai changes`](#10-leai-changes)
  - [11. `leai init`](#11-leai-init)
  - [12. `leai check` (or `doctor`)](#12-leai-check-or-doctor)
- [📁 Directory Structure](#-directory-structure)
- [🧪 Automated Testing](#-automated-testing)

---

## 📌 What Is It?

Enterprise Oracle databases accumulate years of business rules scattered across hundreds of tables, views, triggers, and massive PL/SQL packages (3,000 to 10,000+ lines of code).

Enabling developers or AI assistants to reliably understand such environments is challenging due to three main issues:
1. **Token Inefficiency & Hallucinations:** Sending entire monolithic packages into an LLM context is expensive, slow, and triggers attention degradation ("Lost in the Middle").
2. **Hidden Dependencies:** Altering a single column can silently break triggers, views, and procedures across multiple schemas.
3. **Synonyms and Aliases:** Stored procedures frequently access tables via private or public synonyms (`PUBLIC SYNONYM`), creating the false impression that referenced objects do not exist or belong elsewhere.

LEAI solves this by extracting the Oracle data dictionary, constructing a cross-schema dependency graph, and providing an autonomous multi-step reasoning agent with offline database tools.

---

## ⚙️ How It Works

LEAI operates via a **3-stage decoupled pipeline**:

```
 [Oracle Database]
       │
       ▼ (leai extract)
 ┌─────────────┐
 │ 1. RAW JSON │ ──> Pure technical dictionary snapshot (DDL, columns, types, PKs, FKs, Synonyms).
 └─────────────┘
       │
       ▼ (leai annotate / leai enrich)
 ┌─────────────┐
 │ 2. YAML     │ ──> Editable business annotations (descriptions, rules, tags). Preserves human
 └─────────────┘     documentation and allows AI to fill missing stubs without overwriting.
       │
       ▼ (leai compile / leai trace)
 ┌─────────────┐
 │ 3. DOCS     │ ──> Markdown with YAML Frontmatter + Mermaid.js lineage diagrams + structured
 └─────────────┘     chunks for Vector DBs (pgvector, Chroma, Qdrant).
```

### Core Technologies & Internal Mechanics:

- **Multi-Level Lineage Tracing (`trace`):**
  Identifies upstream dependencies and downstream consumers with configurable depth (`--depth N`), automatically computing change risk levels (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`).
- **Transparent Synonym Dereferencing:**
  Resolves `ALL_SYNONYMS` and `PUBLIC SYNONYMS` directly to their underlying physical target objects, procedures, and remote database links (`@dblink`).
- **PL/SQL Semantic Compression:**
  When querying a specific procedure inside a 10,000-line package, LEAI surgically extracts only the requested subprogram body and produces a lightweight signature skeleton of the rest of the package, **reducing token consumption by up to 95%**.
- **Dynamic Contextual RAG (`ask` & `chat`):**
  Automatically detects database entities mentioned in user prompts, executes on-the-fly dependency tracing, and delivers a surgical, noise-free context payload to the LLM.
- **Native Multi-Provider AI Support:**
  Direct HTTPS REST integration with **OpenAI (ChatGPT)**, **Google Gemini**, **Anthropic Claude**, **DeepSeek**, **Qwen**, **Kimi**, and **Ollama (local & free)** without heavy external dependencies.

---

## 🤖 Autonomous Agent & Tool Calling Engine

When running `leai chat` or `leai ask`, the assistant uses an autonomous **Tool-Calling Reasoning Loop** (`AgentExecutionEngine`) with up to 10 iterations per turn. Instead of guessing or hallucinating, the model invokes specialized in-memory database tools to inspect real metadata:

| Tool Name | Parameters | Purpose |
| :--- | :--- | :--- |
| **`search_database_objects`** | `query`, `object_type` | Global catalog search across tables, views, packages, procedures, functions, triggers, and synonyms. |
| **`get_table_schema`** | `table_name` | Deep structural inspection: column names, data types, nullability, PK flags, descriptions, and foreign keys. |
| **`get_subprogram_source`** | `subprogram_name`, `package_name` | Extracts exact PL/SQL source code of procedures, functions, or package routines. |
| **`trace_object_lineage`** | `object_name`, `depth` | Multi-level X-ray of upstream consumed tables/packages, downstream children, and PL/SQL callers. |
| **`grep_plsql_code`** | `pattern`, `max_results` | Global regex and text occurrence scanner across all PL/SQL packages, procedures, and trigger bodies. |

> [!NOTE]
> All agent tools operate **100% offline in-memory** on top of the extracted `raw/` snapshot. This ensures sub-millisecond responses with zero network latency and zero load on the production Oracle database.

---

## 🔗 Transparent Synonym Resolution

In Oracle enterprise environments, procedures, packages, tables, and views are heavily shared across schemas via Synonyms. LEAI transparently dereferences synonyms throughout all tools:

```text
User asks: "Explain the procedure TGOVPE_RMS_ENVIA_ARQ_CREDITO"
  │
  ├──> LEAI detects object is a SYNONYM pointing to HADES.TGOVPE_RMS_ENVIA_ARQ_CREDITO
  ├──> get_subprogram_source automatically dereferences to the HADES schema
  └──> Extracts real PL/SQL code (8,000+ chars) and synthesizes business explanation
```

---

## 🚀 Quickstart: Using LEAI in Any Project

You don't need to clone the repository. You can use LEAI as a standalone CLI tool in any folder in 3 simple steps:

### Step 1: Install LEAI via `pip` or `uv`

```bash
# Using standard pip
pip install leai

# Or using uv tool (isolated global CLI)
uv tool install leai
```

---

### Step 2: Initialize your project directory

```bash
mkdir my-database-docs
cd my-database-docs
leai init
```

Configure your `leai.yml` file:

```yaml
# Oracle connection string (supports environment variables ${VAR})
dsn: "oracle://${DB_USER}:${DB_PASS}@${DB_HOST}:1521/${DB_SERVICE}"

# Schemas integrated into your ecosystem graph (or schemas: "ALL")
schemas:
  - HR
  - FINANCE
  - CORE

# Output directories
rawPath: "./raw"                  # Raw JSON technical snapshots
annotationsPath: "./annotations"  # Business annotations in YAML
docPath: "./docs"                  # Final Markdown docs for RAG

# AI Provider Configuration
ai:
  default_provider: "openai"      # openai, gemini, anthropic, grok, deepseek, qwen, kimi, ollama
  temperature: 0.2
  providers:
    openai:
      api_key: "${OPENAI_API_KEY}"
      model: "gpt-4o-mini"
    gemini:
      api_key: "${GEMINI_API_KEY}"
      model: "gemini-2.5-flash"
    anthropic:
      api_key: "${ANTHROPIC_API_KEY}"
      model: "claude-3-5-sonnet-20241022"
    grok:
      api_key: "${GROK_API_KEY}"
      base_url: "https://api.x.ai/v1"
      model: "grok-2-latest"
    ollama:
      base_url: "http://localhost:11434/v1"
      model: "llama3.1"
```

---

### Step 3: Run and Explore!

```bash
# 1. Extract technical metadata from Oracle into raw/
leai extract

# 2. Start an interactive AI Copilot chat session about your database
leai chat

# 3. Analyze impact and trace a specific table with Mermaid diagrams
leai trace EMPLOYEES --depth 2

# 4. Auto-enrich business rules using AI without overwriting manual notes
leai enrich

# 5. Compile everything into clean Markdown files in docs/
leai compile
```

---

## 📖 CLI Command Reference

### 1. `leai` (Unified Interactive Studio)
Launches the interactive terminal copilot by default with real-time autocompletion for commands (`/doc`, `/extract`, `/compile`, `/annotate`, `/enrich`, `/serve`, `/trace`) and `@OBJECT` mentions.

```bash
# Launch the interactive terminal
leai

# Target specific schema and AI provider
leai -s HR -p gemini -m gemini-2.5-flash
```

---

### 2. `leai doc [OBJECT]`
Opens the interactive in-terminal documentation editor for an object (table, view, package, etc.), allowing you to edit business descriptions, column comments, and business rules, saving directly to YAML and offering 1-click Markdown recompile.

```bash
# Document a specific table or package directly
leai doc EMPLOYEES
leai doc PKG_FINANCEIRO
```

---

### 3. `leai generate`
Executes the full automated pipeline: extracts technical snapshots from Oracle, synchronizes business annotation stubs, and compiles final Markdown docs.

| Parameter / Flag | Type | Description |
| :--- | :--- | :--- |
| `-c`, `--config PATH` | Option | Path to configuration file (Default: `leai.yml`). |
| `-s`, `--schema TEXT` | Option | Target schema(s) to process. |
| `-t`, `--object-type TEXT` | Option | Filter specific object types (e.g., `-t tables -t views -t packages`). |
| `--with-traces / --no-traces` | Flag | Include dependency lineage, risk analysis and Mermaid graph (Default: `True`). |
| `--rag-json`, `--rag` | Flag | Also exports structured JSON chunks to `docs/chunks/` for Vector DB ingestion. |
| `-d`, `--depth INT` | Option | Max graph traversal depth for lineage mapping (Default: `1`). |
| `-v`, `--version` | Flag | Show LEAI version and exit. |

```bash
leai generate
leai generate -s HR -t tables -t packages --depth 2
```

---

### 4. `leai extract`
Connects to Oracle and extracts raw JSON technical snapshots into the `raw/` directory. Supports **incremental extraction** via `--days` to extract only objects modified in the last N days and merge them directly into the local snapshot.

| Parameter / Flag | Type | Description |
| :--- | :--- | :--- |
| `-c`, `--config PATH` | Option | Path to `leai.yml`. |
| `-s`, `--schema TEXT` | Option | Extract only specific schema(s). |
| `-t`, `--object-type TEXT` | Option | Filter object types to extract (e.g. `-t tables -t packages`). |
| `-d`, `--days INT` | Option | **Incremental Extraction:** Extract only objects modified in the last N days based on `LAST_DDL_TIME`. |

```bash
# Full extraction
leai extract

# Incremental extraction (objects modified in the last 30 days)
leai extract --days 30
leai extract -s HR -d 7

# In TUI session
/extract 30
/extract HR 30
```

---

### 3. `leai annotate`
Reads JSON snapshots from `raw/` and generates/synchronizes YAML stubs in `annotations/`, preserving existing manual documentation (Offline Mode).

| Parameter / Flag | Type | Description |
| :--- | :--- | :--- |
| `-c`, `--config PATH` | Option | Path to `leai.yml`. |
| `-s`, `--schema TEXT` | Option | Synchronize specific schema(s). |
| `-t`, `--object-type TEXT` | Option | Synchronize only specific object types. |

```bash
leai annotate
leai annotate -t tables
```

---

### 4. `leai compile`
Recompiles the unified Markdown documentation in `docs/` (including dependency lineage, risk analysis, Mermaid.js diagrams, and `docs/INDEX.md`) by merging `raw/` and `annotations/` without connecting to the database.

| Parameter / Flag | Type | Description |
| :--- | :--- | :--- |
| `-c`, `--config PATH` | Option | Path to `leai.yml`. |
| `-s`, `--schema TEXT` | Option | Compile specific schema(s). |
| `-t`, `--object-type TEXT` | Option | Compile only specific object types. |
| `--with-traces / --no-traces` | Flag | Include dependency lineage, risk analysis and Mermaid graph (Default: `True`). |
| `--rag-json`, `--rag` | Flag | Also exports structured JSON chunks to `docs/chunks/` for Vector DB ingestion. |
| `-d`, `--depth INT` | Option | Max graph traversal depth for lineage mapping (Default: `1`). |

```bash
leai compile
leai compile --rag-json --depth 2
```

---

### 5. `leai trace <OBJECT>`
Generates deep impact analysis, terminal hierarchical trees, change risk calculations, and Mermaid.js lineage dossiers.

| Parameter / Flag | Type | Description |
| :--- | :--- | :--- |
| `OBJECT` | **Required Argument** | Name of the table, view, procedure, package, or synonym to trace. |
| `-d`, `--depth INT` | Option | Max graph traversal depth (Default: `1` for direct, `2+` for multi-level). |
| `--rag-json`, `--rag` | Flag | Also exports structured JSON chunks for Vector DB ingestion. |
| `--offline` | Flag | Resolves dependencies locally from `raw/` snapshots without connecting to Oracle. |
| `-s`, `--schema TEXT` | Option | Schema of target object (searches all configured schemas if omitted). |
| `-o`, `--output PATH` | Option | Custom file path for the generated Markdown dossier. |
| `-c`, `--config PATH` | Option | Path to `leai.yml`. |

```bash
leai trace EMPLOYEES --depth 2
leai trace TGOVPE_RMS_ENVIA_ARQ_CREDITO --offline --depth 2
```

---

### 6. `leai enrich`
Uses AI (LLMs) to analyze DDLs and PL/SQL code, automatically generating business rules and column descriptions in `annotations/` with real-time progress bars.

| Parameter / Flag | Type | Description |
| :--- | :--- | :--- |
| `-c`, `--config PATH` | Option | Path to `leai.yml`. |
| `-p`, `--provider TEXT` | Option | AI provider (`openai`, `gemini`, `anthropic`, `grok`, `xai`, `deepseek`, `qwen`, `kimi`, `ollama`). |
| `-m`, `--model TEXT` | Option | Model identifier (e.g., `gpt-4o-mini`, `gemini-2.5-flash`, `claude-3-5-sonnet-20241022`). |
| `-w`, `--overwrite` | Flag | Forces regeneration of existing descriptions and comments. |
| `-s`, `--schema TEXT` | Option | Filter by specific schema. |
| `-t`, `--object-type TEXT` | Option | Filter object types to enrich (e.g., `-t tables -t packages`). |
| `-o`, `--object-name TEXT` | Option | Specific object name to enrich (e.g., `-o EMPLOYEES`). |

```bash
leai enrich
leai enrich -p gemini -m gemini-2.5-flash
leai enrich -o EMPLOYEES --overwrite
```

---

### 7. `leai ask <QUESTION>`
Asks one-off natural language questions answered with dynamic RAG context and agent tool execution directly in your terminal.

| Parameter / Flag | Type | Description |
| :--- | :--- | :--- |
| `QUESTION` | **Required Argument** | The question regarding database structure, dependencies, or business rules. |
| `-p`, `--provider TEXT` | Option | AI provider to use. |
| `-m`, `--model TEXT` | Option | Model identifier to use. |
| `-c`, `--config PATH` | Option | Path to `leai.yml`. |

```bash
leai ask "Which views or stored procedures query the EMPLOYEES table?"
leai ask "How does the payroll calculation workflow operate?" -p gemini
```

---

### 8. `leai chat`
Launches an interactive multi-turn terminal chat session with persistent conversation memory, cumulative graph context, and live tool calling.

| Parameter / Flag | Type | Description |
| :--- | :--- | :--- |
| `-p`, `--provider TEXT` | Option | AI provider to use. |
| `-m`, `--model TEXT` | Option | Model identifier to use. |
| `-c`, `--config PATH` | Option | Path to `leai.yml`. |
| `-w`, `--web` | Flag | Launch and open the interactive Web Chat Studio in browser (`http://localhost:8000/chat`). |

```bash
# Interactive TUI Copilot in terminal
leai chat
leai chat -p gemini -m gemini-2.5-flash
leai chat -p ollama -m qwen2.5-coder:14b

# Interactive Web Chat Studio in browser
leai chat --web
leai serve --chat
```

#### 🎮 Interactive In-Session Features (OpenCode Style):
- **🎨 Catppuccin Mocha Visual Theme:** Clean borderless cards, status indicators, and syntax highlighting for SQL, PL/SQL, JSON and Diffs.
- **⚡ Live Reasoning & Tool Call Timeline:** Step-by-step progress tracking with animated spinners, execution durations, and compact result summaries.
- **📋 Seamless One-Click Code Copy:** Clean selection without vertical box bars (`│`), plus `/copy`, `/copy 1`, `/copy sql` commands to copy directly to OS clipboard.
- **🌐 Interactive Web Chat Studio:** Rich web interface with chat threads, SSE real-time streaming, 1-click code copying, and `@mention` autocomplete.
- **⌨️ Smart Autocomplete & Multiline:**
  - Type `/` to browse and autocomplete slash commands with inline descriptions.
  - Type `@` to autocomplete database objects (`@EMPLOYEES`) with type badges (`[TABLE]`, `[VIEW]`, `[PACKAGE]`, `[PROCEDURE]`).
  - Press `Alt+Enter` or `Escape+Enter` to insert newlines for multiline prompts, and `Enter` to send.
  - Search command history with `Ctrl+R` or arrow keys.

#### 📋 Complete In-Session Slash Commands:
| Command | Category | Description |
| :--- | :--- | :--- |
| `/copy [all\|code\|N]` | Clipboard | Copy last AI response or specific code block directly to OS clipboard. |
| `/doc [obj]` | Documentation | Interactive in-terminal YAML annotation & documentation editor. |
| `/enrich [obj]` | AI Studio | Auto-enrich business descriptions & rules with LLM. |
| `/compile [obj]` | Pipeline | Compile final Markdown docs in `docs/` (supports single object). |
| `/annotate` | Pipeline | Synchronize YAML annotation stubs in `annotations/`. |
| `/extract [s\|ALL]` | Pipeline | Connect to Oracle and extract fresh raw metadata snapshot. |
| `/serve [port\|stop]`| Web Studio | Launch interactive Web Studio with in-browser editor & real-time sync. |
| `/trace <obj>` | Lineage | Perform inline dependency lineage & impact X-ray with Mermaid. |
| `/tables` | Inspection | List all tables with column counts and primary keys. |
| `/schema [s]` | Inspection | Show comprehensive overview of all catalog objects. |
| `/changes [d]` | Inspection | Inspect database objects modified in last N days (Default: `7`). |
| `/models [p]` | AI Config | List all available AI models returned by provider API with selection. |
| `/model <p> [m]` | AI Config | Switch AI provider (`openai`, `gemini`, `anthropic`, `grok`, etc.) and model. |
| `/audit [last\|session\|export]` | Audit & Logs | Inspect AI tool call trace, latency & session audit log. |
| `/tools` | Audit & Logs | Quick viewer for last turn's tool execution inputs/outputs. |
| `/save [file.md]` | Session | Export current conversation transcript to Markdown. |
| `/check` | Diagnostics | Verify Oracle connection, metadata snapshots, docs and AI status. |
| `/init` | Setup | Check or initialize `leai.yml` configuration file. |
| `/clear` | Session | Clear conversation memory and reset terminal screen. |
| `/help` | Reference | Display interactive commands reference. |
| `/exit`, `/quit` | Session | Exit LEAI interactive copilot. |

---

### 9. `leai models`
Queries the AI provider API and displays a formatted table of all available models for the configured API key.

| Parameter / Flag | Type | Description |
| :--- | :--- | :--- |
| `-p`, `--provider TEXT` | Option | AI provider to query (`openai`, `gemini`, `anthropic`, `grok`, `xai`, `deepseek`, `qwen`, `kimi`, `ollama`). |
| `-c`, `--config PATH` | Option | Path to `leai.yml`. |

```bash
leai models -p gemini
leai models -p openai
leai models -p ollama
```

---

### 10. `leai changes`
Audits and lists recently created or modified database objects (via Oracle's `LAST_DDL_TIME`).

| Parameter / Flag | Type | Description |
| :--- | :--- | :--- |
| `-d`, `--days INT` | Option | Number of trailing days to audit (Default: `7`). |
| `-u`, `--user TEXT` | Option | Filter by modifying user / schema (e.g., `-u HR`). |
| `-s`, `--schema TEXT` | Option | Target schema. |
| `-t`, `--object-type TEXT` | Option | Filter object types. |
| `-c`, `--config PATH` | Option | Path to `leai.yml`. |

```bash
leai changes -d 15
leai changes -d 30 -u HR
```

---

### 11. `leai init`
Creates a clean initial `leai.yml` template in the current directory.

| Parameter / Flag | Type | Description |
| :--- | :--- | :--- |
| `-f`, `--force` | Flag | Overwrites existing `leai.yml` without confirmation. |
| `-e`, `--example` | Flag | Generates fully commented `leai.example.yml`. |
| `-c`, `--config PATH` | Option | Custom configuration file path. |

```bash
leai init
leai init --example
```

---

### 12. `leai check` (or `doctor`)
Performs a comprehensive diagnostic healthcheck of the Oracle connection, credentials, privileges, directories, and configured AI models.

| Parameter / Flag | Type | Description |
| :--- | :--- | :--- |
| `-c`, `--config PATH` | Option | Path to `leai.yml`. |

```bash
leai check
leai doctor
```

---

## 📁 Directory Structure

```text
my_project/
├── leai.yml
├── raw/                      <-- Raw JSON snapshots extracted from Oracle
│   └── HR/
│       ├── tables/
│       ├── views/
│       ├── synonyms/
│       └── code_objects/
├── annotations/              <-- YAML business rules & annotations (editable)
│   └── HR/
│       ├── tables/
│       └── code_objects/
└── docs/                     <-- Final compiled Markdown for LLMs, RAG, and humans
    └── HR/
        ├── INDEX.md          <-- Master navigation catalog
        ├── tables/
        ├── dossiers/         <-- Impact dossiers generated by leai trace
        └── code_objects/
```

---

## 🧪 Automated Testing

To run the complete automated test suite:

```bash
pytest
```
