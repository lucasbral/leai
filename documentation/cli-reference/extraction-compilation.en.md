# Extraction, Compilation & Lineage Commands

This section details the primary commands responsible for reverse engineering, documentation generation, and impact analysis in LEAI.

---

## 1. `leai` (or `leai generate`)

Executes the end-to-end pipeline: Oracle metadata extraction, business annotation stub creation, and final Markdown compilation.

```bash
leai
# or with a custom configuration file:
leai --config ./my-leai.yml
```

---

## 2. `leai extract`

Connects to the Oracle database configured in `dsn` and extracts data dictionary catalog definitions into raw JSON files.

```bash
leai extract
```

### Options:
* `--schema <NAME>`: Extracts only a specific schema, overriding the list in `leai.yml`.
* `--types <LIST>`: Selects specific object types (e.g., `--types tables,views`).

Output snapshots are stored in `./raw/<SCHEMA>.json`.

---

## 3. `leai annotate`

Generates or synchronizes business annotation YAML files under `./annotations/<SCHEMA>.yml`.

```bash
leai annotate
```

> [!NOTE]
> This command is completely non-destructive. It merges new schema entities into existing YAML files while strictly preserving previously written manual descriptions.

---

## 4. `leai enrich`

Invokes the configured LLM provider to draft contextual descriptions for undocumented tables and columns.

```bash
leai enrich
# or for an isolated schema:
leai enrich --schema HR
```

---

## 5. `leai compile`

Combines `./raw/` data with `./annotations/` notes to generate clean, production Markdown documents under `docPath` (default: `./docs/<SCHEMA>/`).

```bash
leai compile
```

Each generated file features:
* **YAML Frontmatter:** Machine-readable metadata headers for vector indexing.
* **Column Specifications:** Types, nullability, default expressions, and business descriptions.
* **Mermaid.js Diagrams:** Entity relationships and foreign key linkages.

---

## 6. `leai trace <OBJECT>`

Performs multi-level lineage tracing and automated risk evaluation on any database entity.

```bash
leai trace OBJECT_NAME
```

### Options:
* `--depth <N>`: Maximum exploration depth in the dependency graph (default: `2`).
* `--schema <NAME>`: Targets a specific schema when resolving ambiguous names.
* `--format <text|mermaid|json>`: Output presentation style in the terminal.

#### Example:
```bash
leai trace ORDERS_TB --depth 3 --format mermaid
```
