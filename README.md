# LEAI — Oracle Database Intelligence & Documentation Engine

**LEAI** is a reverse engineering, impact analysis, and documentation engine for **Oracle Database**, specifically designed to power **Retrieval-Augmented Generation (RAG)**, **LLMs**, and software engineers maintaining complex enterprise database ecosystems.

---

## 📌 What Is It?

Enterprise Oracle databases accumulate years of business rules scattered across hundreds of tables, views, triggers, and massive PL/SQL packages (3,000 to 10,000+ lines of code).

Enabling developers or AI assistants to reliably understand such environments is challenging due to three main issues:
1. **Token Inefficiency & Hallucinations:** Sending entire monolithic packages into an LLM context is expensive, slow, and triggers the "Lost in the Middle" attention degradation.
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

## 🚀 Getting Started

### 1. Installation

We recommend using **`uv`** for fast and isolated execution:

```bash
# Clone the repository and navigate to the directory
cd leai

# Synchronize dependencies and virtual environment
uv sync
```

*(Or using standard pip: `pip install -e .`)*

---

### 2. Configuration (`leai.yml`)

Create a `leai.yml` file in the root of your project:

```yaml
# Oracle connection string (supports environment variables ${VAR})
dsn: "oracle://${DB_USER}:${DB_PASS}@${DB_HOST}:1521/${DB_SERVICE}"

# Schemas integrated into your ecosystem graph
schemas:
  - HR
  - FINANCE
  - CORE

# Pipeline output directories
rawPath: "./raw"                  # Raw technical snapshots (JSON)
annotationsPath: "./annotations"  # Business annotations (YAML)
docPath: "./docs"                  # Final compiled documentation (Markdown)

# AI Provider Configuration for enrich, ask, and chat
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

## 📖 CLI Command Reference

### 1. `uv run leai` (or `leai generate`)
Executes the full pipeline: extracts technical snapshots from Oracle, synchronizes business annotation stubs, and compiles final Markdown docs.

| Parameter / Flag | Type | Description |
| :--- | :--- | :--- |
| `-c`, `--config PATH` | Option | Path to the configuration file (Default: `leai.yml`). |
| `-t`, `--object-type TEXT` | Option | Filter specific object types (e.g., `-t tables -t views -t packages`). |

```bash
uv run leai
uv run leai generate -t tables -t packages --config prod.yml
```

---

### 2. `uv run leai extract`
Connects to Oracle and extracts raw JSON technical snapshots into the `raw/` directory.

| Parameter / Flag | Type | Description |
| :--- | :--- | :--- |
| `-s`, `--schema TEXT` | Option | Extract only a specific schema. |
| `-t`, `--object-type TEXT` | Option | Filter object types to extract. |
| `-c`, `--config PATH` | Option | Path to `leai.yml`. |

```bash
uv run leai extract
uv run leai extract -s HR -t tables -t views
```

---

### 3. `uv run leai annotate`
Reads JSON snapshots from `raw/` and generates/synchronizes YAML stubs in `annotations/`, preserving existing manual documentation (Offline Mode).

| Parameter / Flag | Type | Description |
| :--- | :--- | :--- |
| `-t`, `--object-type TEXT` | Option | Synchronize only specific object types. |
| `-c`, `--config PATH` | Option | Path to `leai.yml`. |

```bash
uv run leai annotate
uv run leai annotate -t tables
```

---

### 4. `uv run leai compile`
Recompiles the entire Markdown documentation in `docs/` by merging `raw/` and `annotations/` without connecting to the database.

| Parameter / Flag | Type | Description |
| :--- | :--- | :--- |
| `-t`, `--object-type TEXT` | Option | Compile only specific object types. |
| `-c`, `--config PATH` | Option | Path to `leai.yml`. |

```bash
uv run leai compile
uv run leai compile -t views
```

---

### 5. `uv run leai trace <OBJECT>`
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
uv run leai trace EMPLOYEES --depth 2

# Offline mode with RAG JSON chunk export
uv run leai trace EMPLOYEES --offline --depth 2 --rag-json
```

---

### 6. `uv run leai enrich`
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
uv run leai enrich

# Enrich using Google Gemini or Anthropic Claude
uv run leai enrich --provider gemini --model gemini-1.5-flash
uv run leai enrich --provider anthropic --model claude-3-5-sonnet-20241022

# Enrich a single table with forced overwrite
uv run leai enrich -o EMPLOYEES --overwrite
```

---

### 7. `uv run leai ask <QUESTION>`
Asks one-off natural language questions answered with dynamic RAG context directly in your terminal.

| Parameter / Flag | Type | Description |
| :--- | :--- | :--- |
| `QUESTION` | **Required Argument** | The question regarding database structure, dependencies, or business rules. |
| `-p`, `--provider TEXT` | Option | AI provider to use. |
| `-m`, `--model TEXT` | Option | Model identifier to use. |
| `-c`, `--config PATH` | Option | Path to `leai.yml`. |

```bash
uv run leai ask "Which views or stored procedures query the EMPLOYEES table?"
uv run leai ask "How does the payroll calculation workflow operate?" --provider gemini
```

---

### 8. `uv run leai chat`
Launches an interactive multi-turn terminal chat session with persistent conversation memory and cumulative graph context.

| Parameter / Flag | Type | Description |
| :--- | :--- | :--- |
| `-p`, `--provider TEXT` | Option | AI provider to use. |
| `-m`, `--model TEXT` | Option | Model identifier to use. |
| `-c`, `--config PATH` | Option | Path to `leai.yml`. |

```bash
uv run leai chat
uv run leai chat --provider anthropic --model claude-3-5-sonnet-20241022
uv run leai chat --provider ollama --model llama3.1
```

#### 🎮 Interactive In-Session Commands:
- `/clear`: Clears conversation history and active entity memory.
- `/save [file.md]`: Exports the complete transcript and generated scripts into a Markdown file.
- `/help`: Displays available commands.
- `/exit` or `/quit`: Closes the chat session.

---

### 9. `uv run leai changes`
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
uv run leai changes -d 15

# Filter by schema
uv run leai changes -d 30 -u HR
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
uv run python -m unittest discover tests
```
