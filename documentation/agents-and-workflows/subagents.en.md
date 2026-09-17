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
| **`catalog_researcher`** | Catalog Researcher | Catalog discovery, resolving synonyms, constraints, foreign keys, and column types. | `get_table_schema`, `search_catalog`, `lookup_business_term` |
| **`plsql_analyst`** | PL/SQL Analyst | Static analysis, reverse engineering routines, sargability diagnostics, Oracle dialect validation, and SQL tuning. | `get_subprogram_source`, `grep_plsql_code`, `get_table_schema`, `explain_and_tune_sql`, `validate_oracle_sql` |
| **`lineage_auditor`** | Lineage & Impact Auditor | Cascading dependency mapping and risk rating for planned schema refactors. | `trace_object_lineage`, `search_catalog`, `get_table_schema` |
| **`patch_generator`** | Patch & Refactor Engineer | Generates safe DDL migrations, Oracle dialect checks, rollback scripts, and semantic code updates. | `get_table_schema`, `get_subprogram_source`, `grep_plsql_code`, `validate_oracle_sql`, `explain_and_tune_sql` |
| **`doc_annotator`** | Documentation Annotator | Generates domain-aligned business documentation and glossary terminology. | `get_table_schema`, `get_subprogram_source`, `lookup_business_term` |
