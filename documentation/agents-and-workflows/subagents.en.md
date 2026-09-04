# Specialized Subagents (`leai agent`)

LEAI implements a **Specialized Subagents** architecture where complex database tasks are delegated to isolated technical personas equipped with targeted toolsets rather than a one-size-fits-all prompt.

---

## ⚡ Agent Group Commands

### 1. `leai agent list`
Lists all registered subagents, their specialist titles, scopes, and permitted database tools.

```bash
leai agent list
```

---

### 2. `leai agent run <ROLE> <TASK>`
Launches a specialized subagent in a clean, isolated context with real-time reasoning streaming in the terminal.

| Parameter / Flag | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `ROLE` | Argument | Yes | Specialist identifier (e.g. `plsql_analyst`, `lineage_auditor`). |
| `TASK` | Argument | Yes | Clear instruction, question, or objective for the specialist. |
| `-c`, `--config PATH` | Option | No | Path to `leai.yml` (Default: `leai.yml`). |
| `-p`, `--provider TEXT` | Option | No | AI provider override. |
| `-m`, `--model TEXT` | Option | No | Specific AI model override. |

#### Usage Examples:

```bash
# Deep dive into complex PL/SQL routine
leai agent run plsql_analyst "Explain the interest calculation algorithm in PKG_BILLING"

# Lineage audit prior to schema migration
leai agent run lineage_auditor "Which downstream consumers break if column BALANCE in ACCOUNTS_TB is altered?"

# Generate a safe schema migration patch
leai agent run patch_generator "Produce a zero-downtime DDL script to add LAST_SYNC column to CUSTOMERS"
```

---

## 👥 Available Specialists

| Role / ID | Specialist Name | Scope & Purpose | Permitted Tools |
| :--- | :--- | :--- | :--- |
| **`catalog_researcher`** | Catalog Researcher | Catalog discovery, resolving synonyms, constraints, foreign keys, and column types. | `search_database_objects`, `view_object_definition`, `get_glossary_terms` |
| **`plsql_analyst`** | PL/SQL Analyst | Static analysis and decompilation of business rules in procedures, packages, and triggers with token compression. | `view_object_definition`, `search_database_objects` |
| **`lineage_auditor`** | Lineage & Impact Auditor | Cascading dependency mapping and risk rating for planned schema refactors. | `trace_object_lineage`, `search_database_objects` |
| **`patch_generator`** | Patch & Refactor Engineer | Generates safe DDL migrations, rollback scripts, and semantic code updates. | `view_object_definition`, `trace_object_lineage` |
| **`doc_annotator`** | Documentation Annotator | Generates domain-aligned business documentation and glossary terminology. | `view_object_definition`, `get_glossary_terms` |
