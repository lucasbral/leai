# Autonomous Workflows (`leai workflow`)

Workflows are pre-packaged, multi-stage engineering pipelines that orchestrate end-to-end tasks, generating production-ready audit dossiers and migration patches.

---

## ⚡ Workflow Group Commands

### 1. `leai workflow list`
Lists all available workflows, descriptions, and command aliases.

```bash
leai workflow list
```

---

### 2. `leai workflow run <NAME> <TARGET>`
Executes an orchestrated workflow pipeline on a database object.

| Parameter / Flag | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `NAME` | Argument | Yes | Workflow name or alias (e.g. `impact-analysis`, `safe-refactor`). |
| `TARGET` | Argument | Yes | Target database object (table, view, package, etc.). |
| `-c`, `--config PATH` | Option | No | Path to `leai.yml`. |
| `-p`, `--provider TEXT` | Option | No | AI provider override. |
| `-o`, `--output PATH` | Option | No | Output file path for the generated Markdown report. |

---

## 🚀 Built-in Workflows

### 1. `impact-analysis` (Alias: `impact`)
Performs a rigorous pre-migration impact assessment:
1. **Lineage Mapping:** Uncovers all upstream providers and downstream consumers.
2. **Risk Scoring:** Computes risk ratings (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`).
3. **Semantic Code Inspection:** Reads dependent package bodies to determine exact usage patterns.
4. **Consolidated Dossier:** Outputs an executive Markdown report with Mermaid diagrams and mitigation strategies.

```bash
leai workflow run impact CUSTOMERS_TB --output ./customers_impact_report.md
```

---

### 2. `safe-refactor` (Alias: `refactor`, `patch`)
Coordinates a safe, phased schema or package refactor:
1. Audits existing constraints, indexes, and subprograms.
2. Flags breaking call sites across dependent packages.
3. Formulates a phased migration strategy (expand/contract pattern).
4. Generates verified DDL migration scripts and safety rollback blocks.

```bash
leai workflow run refactor PKG_BILLING -p claude
```

---

### 3. `reverse-procedure` (Alias: `reverse`, `decomp`)
Performs automated reverse engineering and generates complete functional specifications for PL/SQL routines (procedures, functions, and packages):
1. **Source Code Extraction:** Extracts authentic PL/SQL definitions and parses parameter interfaces (types and IN/OUT modes).
2. **Technical CRUD Matrix:** Classifies entities accessed for queries (`SELECT`) vs data modifications (`INSERT`, `UPDATE`, `DELETE`, `MERGE`).
3. **Call Tree & Package Lineage:** Traces outgoing system packages (`DBMS_OUTPUT`, `UTL_FILE`, etc.) and external business procedures.
4. **Business Logic Decomposition:** Deconstructs validation rules, branches, calculations, exception handlers, and outputs a Mermaid flowchart (`flowchart TD`).
5. **Specification Dossier:** Assembles a structured Markdown specification ready for documentation, audit, or service migration.

```bash
leai workflow run reverse-procedure PRC_UPDATE_SALARY --output ./docs/salary_proc_spec.md
```
