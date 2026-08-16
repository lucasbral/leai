# LEAI — Oracle Database Intelligence & Documentation Engine

**LEAI**  (Lê - Aí in PT ) is a reverse engineering, impact analysis, and documentation engine for **Oracle Database**, specifically designed to power **Retrieval-Augmented Generation (RAG)**, **LLMs**, and software engineers maintaining complex enterprise database ecosystems.

> [!IMPORTANT]
> 🔒 **Security & Data Privacy Guarantee:**
>
> **LEAI NEVER accesses, reads, or extracts business data (table records or rows) stored in the database.**
> It strictly reads **data dictionary metadata and DDL definitions**: tables, column types, primary/foreign keys, views, materialized views, stored procedures, packages, triggers, indexes, and synonyms.
>
> 💡 **A database user with metadata-only / audit permissions (such as `SELECT ANY DICTIONARY` or read access to `ALL_*` catalog views) is 100% sufficient.** This ensures full enterprise security and compliance (LGPD / GDPR / SOC2) with zero risk of exposing confidential or sensitive business data.

---

## 📌 What Is It?

Enterprise Oracle databases accumulate years of business rules scattered across hundreds of tables, views, triggers, and massive PL/SQL packages (3,000 to 10,000+ lines of code).

Enabling developers or AI assistants to reliably understand such environments is challenging due to three main issues:
1. **Token Inefficiency & Hallucinations:** Sending entire monolithic packages into an LLM context is expensive, slow, and triggers attention degradation ("Lost in the Middle").
2. **Hidden Dependencies:** Altering a single column can silently break triggers, views, and procedures across multiple schemas.
3. **Synonyms and Aliases:** Stored procedures frequently access tables via private or public synonyms (`PUBLIC SYNONYM`), creating the false impression that referenced objects do not exist or belong elsewhere.

LEAI solves this by extracting the Oracle data dictionary, constructing a cross-schema dependency graph, and formatting the technical context specifically for humans and LLMs.

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
- **Transparent Synonym & Dblink Resolution:**
  Resolves `ALL_SYNONYMS` and `PUBLIC SYNONYMS` directly to their underlying physical target objects, including remote database links (`@dblink`).
- **PL/SQL Semantic Compression:**
  When querying a specific procedure (`TEST_PROC`) inside a 10,000-line package, LEAI surgically extracts only the requested subprogram body and produces a lightweight signature skeleton of the rest of the package, **reducing token consumption by up to 95%**.
- **Dynamic Contextual RAG (`ask` & `chat`):**
  Automatically detects database entities mentioned in user prompts, executes on-the-fly dependency tracing, and delivers a surgical, noise-free context payload to the LLM.
- **Native Multi-Provider AI Support:**
  Direct HTTPS REST integration with **OpenAI (ChatGPT)**, **Google Gemini**, **Anthropic Claude**, **DeepSeek**, **Qwen**, **Kimi**, and **Ollama (local & free)** without heavy external dependencies.

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

Create a working directory for your database documentation and enter it:

```bash
mkdir my-database-docs
cd my-database-docs
```

Create a `leai.yml` file in that folder:

```yaml
# Oracle connection string (supports environment variables ${VAR})
dsn: "oracle://${DB_USER}:${DB_PASS}@${DB_HOST}:1521/${DB_SERVICE}"

# Schemas integrated into your ecosystem graph
schemas:
  - HR
  - FINANCE
  - CORE

# Output directories
rawPath: "./raw"                  # Raw JSON technical snapshots
annotationsPath: "./annotations"  # Business annotations in YAML
docPath: "./docs"                  # Final Markdown docs for RAG

# AI Provider Configuration (Optional - for enrich, ask, and chat)
ai:
  default_provider: "openai"      # openai, gemini, anthropic, deepseek, qwen, kimi, ollama
  temperature: 0.2
  providers:
    openai:
      api_key: "${OPENAI_API_KEY}"
      model: "gpt-4o-mini"
    gemini:
      api_key: "${GEMINI_API_KEY}"
      model: "gemini-1.5-flash"
    anthropic:
      api_key: "${ANTHROPIC_API_KEY}"
      model: "claude-3-5-sonnet-20241022"
    ollama:
      base_url: "http://localhost:11434/v1"
      model: "llama3.1"
```

---

### Step 3: Run and Explore!

That's it! You can now run LEAI commands directly in your folder:

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

### 1. `leai` (or `leai generate`)
Executes the full pipeline: extracts technical snapshots from Oracle, synchronizes business annotation stubs, and compiles final Markdown docs.

| Parameter / Flag | Type | Description |
| :--- | :--- | :--- |
| `-c`, `--config PATH` | Option | Path to the configuration file (Default: `leai.yml`). |
| `-t`, `--object-type TEXT` | Option | Filter specific object types (e.g., `-t tables -t views -t packages`). |

```bash
leai
leai generate -t tables -t packages --config prod.yml
```

---

### 2. `leai extract`
Connects to Oracle and extracts raw JSON technical snapshots into the `raw/` directory.

| Parameter / Flag | Type | Description |
| :--- | :--- | :--- |
| `-s`, `--schema TEXT` | Option | Extract only a specific schema. |
| `-t`, `--object-type TEXT` | Option | Filter object types to extract. |
| `-c`, `--config PATH` | Option | Path to `leai.yml`. |

```bash
leai extract
leai extract -s HR -t tables -t views
```

---

### 3. `leai annotate`
Reads JSON snapshots from `raw/` and generates/synchronizes YAML stubs in `annotations/`, preserving existing manual documentation (Offline Mode).

| Parameter / Flag | Type | Description |
| :--- | :--- | :--- |
| `-t`, `--object-type TEXT` | Option | Synchronize only specific object types. |
| `-c`, `--config PATH` | Option | Path to `leai.yml`. |

```bash
leai annotate
leai annotate -t tables
```

#### 📝 Annotation Schema Layout (`annotations/tables/EMPLOYEES.yml`):
```yaml
description: "Core employees and contractors table."
tags:
  - HR
  - Payroll
business_rules:
  - "Rule 1: Salary cannot be negative."
  - "Rule 2: Status 'A' indicates active employee, 'I' inactive."
use_cases:
  - "Active employees payroll query:"
  - |
    SELECT id, name, salary 
    FROM employees 
    WHERE status = 'A' AND salary > 0;
related_objects:
  - DEPARTMENTS
warnings:
  - "Modifying employee status triggers TRG_AUDIT_EMP."
columns:
  ID: "Primary key identifier."
  NAME: "Full legal name."
```

---

### 4. `leai compile`
Recompiles the unified Markdown documentation in `docs/` (including dependency lineage, risk analysis, Mermaid.js diagrams, and `docs/INDEX.md`) by merging `raw/` and `annotations/` without connecting to the database.

| Parameter / Flag | Type | Description |
| :--- | :--- | :--- |
| `-t`, `--object-type TEXT` | Option | Compile only specific object types. |
| `--with-traces / --no-traces` | Flag | Include dependency lineage, risk analysis and Mermaid graph (Default: `True`). |
| `--rag-json`, `--rag` | Flag | Also exports structured JSON chunks to `docs/chunks/` for Vector DB ingestion. |
| `-d`, `--depth INT` | Option | Max graph traversal depth for lineage mapping (Default: `1`). |
| `-c`, `--config PATH` | Option | Path to `leai.yml`. |

```bash
# Standard unified compilation (includes Mermaid graphs, risk analysis, and INDEX.md)
leai compile

# Compile and export all RAG chunks for Vector DB in one step
leai compile --rag-json --depth 2
```

---

### 5. `leai trace <OBJECT>`
Generates deep impact analysis, terminal hierarchical trees, change risk calculations, and Mermaid.js lineage dossiers.

| Parameter / Flag | Type | Description |
| :--- | :--- | :--- |
| `OBJECT` | **Required Argument** | Name of the table, view, procedure, or synonym to trace (e.g., `EMPLOYEES`). |
| `-d`, `--depth INT` | Option | Max graph traversal depth (Default: `1` for direct, `2+` for multi-level). |
| `--rag-json`, `--rag` | Flag | Also exports structured JSON chunks for Vector DB ingestion. |
| `--offline` | Flag | Resolves dependencies locally from `raw/` snapshots without connecting to Oracle. |
| `-s`, `--schema TEXT` | Option | Schema of target object (searches all configured schemas if omitted). |
| `-o`, `--output PATH` | Option | Custom file path for the generated Markdown dossier. |
| `-c`, `--config PATH` | Option | Path to `leai.yml`. |

```bash
# Multi-level lineage trace (Depth 2)
leai trace EMPLOYEES --depth 2

# Offline mode with RAG JSON chunk export
leai trace EMPLOYEES --offline --depth 2 --rag-json
```

---

### 6. `leai enrich`
Uses AI (LLMs) to analyze DDLs and PL/SQL code, automatically generating business rules and column descriptions in `annotations/` with real-time progress bars.

| Parameter / Flag | Type | Description |
| :--- | :--- | :--- |
| `-o`, `--object-name TEXT` | Option | Specific object name to enrich (e.g., `-o EMPLOYEES`). |
| `-p`, `--provider TEXT` | Option | AI provider (`openai`, `gemini`, `anthropic`, `deepseek`, `qwen`, `kimi`, `ollama`). |
| `-m`, `--model TEXT` | Option | Model identifier (e.g., `gpt-4o-mini`, `gemini-1.5-flash`, `claude-3-5-sonnet-20241022`). |
| `--overwrite` | Flag | Forces regeneration of existing descriptions and comments. |
| `-t`, `--object-type TEXT` | Option | Filter object types to enrich (e.g., `-t tables -t packages`). |
| `-c`, `--config PATH` | Option | Path to `leai.yml`. |

```bash
# Enrich using default provider
leai enrich

# Enrich using Google Gemini or Anthropic Claude
leai enrich --provider gemini --model gemini-1.5-flash
leai enrich --provider anthropic --model claude-3-5-sonnet-20241022

# Enrich a single table with forced overwrite
leai enrich -o EMPLOYEES --overwrite
```

---

### 7. `leai ask <QUESTION>`
Asks one-off natural language questions answered with dynamic RAG context directly in your terminal.

| Parameter / Flag | Type | Description |
| :--- | :--- | :--- |
| `QUESTION` | **Required Argument** | The question regarding database structure, dependencies, or business rules. |
| `-p`, `--provider TEXT` | Option | AI provider to use. |
| `-m`, `--model TEXT` | Option | Model identifier to use. |
| `-c`, `--config PATH` | Option | Path to `leai.yml`. |

```bash
leai ask "Which views or stored procedures query the EMPLOYEES table?"
leai ask "How does the payroll calculation workflow operate?" --provider gemini
```

---

### 8. `leai chat`
Launches an interactive multi-turn terminal chat session with persistent conversation memory and cumulative graph context.

| Parameter / Flag | Type | Description |
| :--- | :--- | :--- |
| `-p`, `--provider TEXT` | Option | AI provider to use. |
| `-m`, `--model TEXT` | Option | Model identifier to use. |
| `-c`, `--config PATH` | Option | Path to `leai.yml`. |

```bash
leai chat
leai chat --provider anthropic --model claude-3-5-sonnet-20241022
leai chat --provider ollama --model llama3.1
```

#### 🎮 Interactive In-Session Features (OpenCode Style):
- **Smart Autocomplete:** Type `/` to browse slash commands or `@` to autocomplete database tables, views, and procedures (`@EMPLOYEES`).
- `/trace <obj>`: Generates instant inline dependency lineage & Mermaid graph directly inside chat.
- `/tables`: Renders formatted table list with column counts and primary keys.
- `/schema`: Shows catalog overview and object counts.
- `/changes [days]`: Audits recent database modifications without leaving chat.
- `/model <provider> [model]`: Switches AI provider (OpenAI, Gemini, Claude, DeepSeek, Ollama) on the fly.
- `/save [file.md]`: Exports the complete transcript into a Markdown file.
- `/clear`: Clears conversation history, context memory, and resets the terminal screen.
- `/help`: Displays interactive command guide.
- `/exit` or `/quit`: Closes the chat session.

---

### 9. `leai changes`
Audits and lists recently created or modified database objects (via Oracle's `LAST_DDL_TIME`).

| Parameter / Flag | Type | Description |
| :--- | :--- | :--- |
| `-d`, `--days INT` | Option | Number of trailing days to audit (Default: `7`). |
| `-u`, `--user TEXT` | Option | Filter by modifying user / schema (e.g., `-u HR`). |
| `-s`, `--schema TEXT` | Option | Target schema. |
| `-t`, `--object-type TEXT` | Option | Filter object types. |
| `-c`, `--config PATH` | Option | Path to `leai.yml`. |

```bash
# Objects altered in the last 15 days
leai changes -d 15

# Filter by schema
leai changes -d 30 -u HR
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
        ├── tables/
        ├── dossiers/         <-- Impact dossiers generated by leai trace
        └── code_objects/
```

---

## 🧪 Automated Testing

To run the complete automated test suite:

```bash
python -m unittest discover tests
```
