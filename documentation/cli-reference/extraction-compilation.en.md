# Extraction, Compilation & Lineage Commands

This section details the primary commands responsible for reverse engineering, impact analysis, and Markdown documentation generation in LEAI.

---

## 1. `leai` (or `leai generate`)

Executes the end-to-end pipeline: Oracle metadata extraction, business annotation synchronization, and final Markdown compilation.

```bash
leai
# or with specific flags:
leai -s HR -t tables -t packages --depth 2 --rag-json
```

### Parameters and Flags:

| Parameter / Flag | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `-c`, `--config PATH` | Option | `leai.yml` | Path to configuration file. |
| `-s`, `--schemas TEXT` | Option | From config | Specific schema(s) to process. |
| `-t`, `--object-types TEXT` | Option | From config | Object types to include (e.g., `tables`, `packages`). |
| `--with-traces / --no-traces` | Flag | `True` | Include Mermaid lineage and risk graphs. |
| `--rag-json / --rag` | Flag | `False` | Also exports structured JSON chunks for Vector DBs. |
| `-d`, `--depth INT` | Option | `1` | Max graph traversal depth for lineage mapping. |
| `--seaweed` | Flag | `False` | Uses remote SeaweedFS/S3 Object Storage. |
| `--no-cache` | Flag | `False` | 100% remote mode: prevents saving snapshots to local disk. |
| `--force-upload` | Flag | `False` | Forces re-upload to storage, bypassing SHA-256 cache. |

---

## 2. `leai extract`

Connects to the Oracle database configured in `dsn` and extracts data dictionary catalog definitions into raw JSON files.

```bash
leai extract
# Incremental extraction of objects modified in the last 30 days:
leai extract --days 30
```

### Parameters and Flags:

| Parameter / Flag | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `-c`, `--config PATH` | Option | `leai.yml` | Path to `leai.yml`. |
| `-s`, `--schemas TEXT` | Option | From config | Extracts only specific schema(s). |
| `-t`, `--object-types TEXT` | Option | From config | Filters object types (e.g. `-t tables -t views`). |
| `-d`, `--days INT` | Option | `None` | **Incremental Extraction:** Extracts only objects modified in the last N days via `LAST_DDL_TIME`. |
| `--seaweed` | Flag | `False` | Pushes JSON snapshots directly to remote S3 bucket. |
| `--no-cache` | Flag | `False` | Does not persist snapshots into local `rawPath`. |
| `--force-upload` | Flag | `False` | Forces upload of all files to storage. |

---

## 3. `leai annotate`

Generates or synchronizes business annotation YAML files under `./annotations/<SCHEMA>.yml`.

```bash
leai annotate
```

> [!NOTE]
> This command is strictly non-destructive. It combines newly discovered technical schemas with existing annotations, guaranteeing that previously written human descriptions are never overwritten.

### Parameters and Flags:

| Parameter / Flag | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `-c`, `--config PATH` | Option | `leai.yml` | Path to `leai.yml`. |
| `-s`, `--schemas TEXT` | Option | From config | Synchronizes target schemas. |
| `-t`, `--object-types TEXT` | Option | From config | Filters object types to synchronize. |
| `--seaweed` | Flag | `False` | Reads and syncs annotations directly against remote S3. |
| `--no-cache` | Flag | `False` | Operates in pure remote mode without local files. |

> [!TIP]
> You can also run `/annotate` directly from an interactive copilot session (`leai chat`), with support for `/annotate --seaweed` (or `-W`) and `/annotate --no-cache` modifiers to synchronize stubs without leaving your terminal workflow.

---

## 4. `leai doc <OBJECT>`

Opens the interactive documentation editor right in your terminal for a specific object (table, view, package, etc.).

```bash
leai doc EMPLOYEES
leai doc PKG_BILLING
```

Allows developers and DBAs to update business descriptions and column notes with keyboard navigation, saving directly to local YAML and offering 1-click Markdown recompile. Can also be invoked inside the interactive chat via `/doc <OBJECT>`.

---

## 5. `leai enrich`

Invokes the configured LLM to inspect DDLs and PL/SQL code, drafting automated business descriptions for undocumented entities.

```bash
leai enrich
# Force regeneration for a specific object:
leai enrich -o CUSTOMERS_TB --overwrite -p gemini
```

### Parameters and Flags:

| Parameter / Flag | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `-o`, `--object-name TEXT` | Option | `None` | Target object name to enrich. |
| `-w`, `--overwrite` | Flag | `False` | Forces replacement of existing descriptions. |
| `-p`, `--provider TEXT` | Option | From config | AI provider override. |
| `-m`, `--model TEXT` | Option | From config | Specific AI model identifier. |
| `-s`, `--schemas TEXT` | Option | From config | Filter by schemas. |
| `-t`, `--object-types TEXT` | Option | From config | Filter by object categories. |
| `--seaweed` | Flag | `False` | Loads and persists annotations directly to S3. |
| `--no-cache` | Flag | `False` | Avoids writing local files. |

---

## 6. `leai compile`

Merges `./raw/` snapshots with `./annotations/` notes to generate clean Markdown documents under `docPath`.

```bash
leai compile --depth 2 --rag-json
```

### Parameters and Flags:

| Parameter / Flag | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `-c`, `--config PATH` | Option | `leai.yml` | Path to `leai.yml`. |
| `-o`, `--object-name TEXT` | Option | `None` | Recompiles an isolated individual entity. |
| `-s`, `--schemas TEXT` | Option | From config | Target schemas. |
| `-t`, `--object-types TEXT` | Option | From config | Target object categories. |
| `--with-traces / --no-traces` | Flag | `True` | Includes Mermaid lineage graphs. |
| `--rag-json / --rag` | Flag | `False` | Exports JSON chunks for vector ingestion. |
| `-d`, `--depth INT` | Option | `1` | Traversal depth for dependency tree. |
| `--seaweed` | Flag | `False` | Uses remote S3 snapshots. |
| `--no-cache` | Flag | `False` | Does not save files locally. |

---

## 7. `leai trace <OBJECT>`

Executes multi-level lineage tracing and automated risk evaluation on any database entity.

```bash
leai trace CONTRACTS_TB --depth 3 --offline --output ./dossier.md
```

### Parameters and Flags:

| Parameter / Flag | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `OBJECT` | Argument | **Required** | Name of the entity to trace. |
| `-d`, `--depth INT` | Option | `1` | Max dependency exploration depth. |
| `-s`, `--schema TEXT` | Option | `None` | Target schema when resolving ambiguous names. |
| `--offline` | Flag | `False` | **Offline Mode:** Resolves dependencies locally from `raw/` without connecting to Oracle. |
| `-o`, `--output PATH` | Option | `None` | Saves the generated Markdown dossier to custom path. |
| `--rag-json / --rag` | Flag | `False` | Exports structured JSON chunks for RAG. |
| `--seaweed` | Flag | `False` | Resolves metadata from remote S3. |
| `--no-cache` | Flag | `False` | Operates completely in memory. |
