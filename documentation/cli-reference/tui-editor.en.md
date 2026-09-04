# Interactive In-Terminal Documentation Studio (`leai doc`)

The `leai doc` command launches a **rich Terminal User Interface (TUI)** built with `prompt_toolkit` and `rich`. It allows software engineers and DBAs to document tables, columns, routines, and business rules without leaving the shell or manually editing raw YAML files.

---

## ⚡ Launching the TUI Editor

You can launch the editor in two distinct modes:

### Mode 1: Interactive Paged Catalog
```bash
leai doc
```
Presents all database entities in a paginated catalog with live visual progress bars reflecting documentation completeness.

### Mode 2: Direct Object Target
```bash
leai doc CUSTOMERS_TB
# or with an explicit schema:
leai doc FINANCE.PKG_PAYROLL
```

You can also trigger it from within an interactive chat session (`leai chat`):
```text
/doc CUSTOMERS_TB
```

---

## 📋 The Paginated Objects Catalog

When launched without arguments, LEAI presents the catalog overview:

```text
✦ Database Objects Catalog (142 objects) • Page 1/12
┌────┬────────────┬─────────┬──────────────────────┬──────────────────────┬──────────────────┐
│  # │ Schema     │ Type    │ Object Name          │ Technical Details    │ Doc Status       │
├────┼────────────┼─────────┼──────────────────────┼──────────────────────┼──────────────────┤
│  1 │ FINANCE    │ TABLE   │ CONTRACTS_TB         │ 18 cols (PK: ID)     │ ██████████ 100%  │
│  2 │ FINANCE    │ TABLE   │ ENTRIES_TB           │ 12 cols (PK: ID)     │ ████░░░░░░  40%  │
│  3 │ HR         │ PACKAGE │ PKG_PAYROLL          │ 14 routines          │ ░░░░░░░░░░   0%  │
└────┴────────────┴─────────┴──────────────────────┴──────────────────────┴──────────────────┘
```

### Catalog Controls:
* **Enter item number (`1`, `2`, ...):** Instantly opens the editor for that item.
* **Enter object name (`CONTRACTS_TB`):** Searches and opens directly.
* **Page Navigation:** Type `n` (*next page*) or `p` (*previous page*).
* **Search & Status Filters:**
  * Type `pending`: filters for 0% documented items.
  * Type `partial`: filters for in-progress items.
  * Type `done`: filters for 100% completed items.
  * Type any text (e.g. `hr`, `payroll`): filters across schemas and names.
* **Exit:** Type `0` or `q`.

---

## 📊 Documentation Completeness Algorithm

LEAI computes an automated completeness score (0% to 100%) for every catalog item:

| Component | Weight | Criteria |
| :--- | :--- | :--- |
| **Object Description** | **35%** | Textual explanation of functional purpose. |
| **Columns / Routines** | **35%** | Percentage of columns/subprograms with comments. |
| **Business Rules** | **20%** | At least one codified bullet point rule. |
| **Tags / Domain** | **10%** | Functional domain tags (e.g. `billing`, `compliance`). |

---

## 🛠️ Main Form Navigation

When an entity is selected, LEAI renders technical Oracle metadata (Primary Keys, Foreign Keys, `LAST_DDL_TIME`) alongside the editing menu:

```text
✦ LEAI Documentation Studio • FINANCE.CONTRACTS_TB [TABLE]
┌──────────────────┬────────────────────────────────────────────────────────┐
│ Context Badges   │ SCHEMA: FINANCE   TYPE: TABLE   OBJECT: CONTRACTS_TB   │
│ Doc Completeness │ ██████████ 100%                                        │
│ Primary Keys     │ ID_CONTRACT                                            │
│ Foreign Keys     │ 2 FK constraints                                       │
│ Description      │ Primary repository for client contracts and renewals   │
│ Columns Done     │ 18 / 18                                                │
│ Business Rules   │ 3 rules registered                                     │
│ Tags / Domain    │ sales, compliance                                      │
└──────────────────┴────────────────────────────────────────────────────────┘

Select an action to edit:
  1 • 📝 Edit Main Object Description
  2 • 📊 Edit Column / Routine Comments
  3 • 📌 Edit Business Rules (Bullet Points)
  4 • 🏷️  Edit Tags & Functional Domain
  5 • ⚠️  Edit Technical Warnings / Alerts
  6 • 🔗 Edit Related Objects Lineage
  7 • 💾 Preview YAML & Save Changes
  0 • ❌ Cancel & Back
```

---

## ⌨️ Section-by-Section Workflow

### 1. Object Description (`Option 1`)
Opens a multiline editor with existing notes pre-populated for quick editing.

### 2. Column / Subprogram Comments (`Option 2`)
Displays a numbered column roster with color-coded completeness indicators:
* `[green]✓[/green]`: Documented column.
* `[red]✕[/red]`: Undocumented column.
* Enter column number to edit or update its description.

### 3. Business Rules (`Option 3`)
Manages bullet point business rules:
* Press `a` to append a new rule.
* Enter rule number to edit or delete existing entries.

### 4. Domain Tags (`Option 4`)
Enter comma-separated tags for semantic classification (e.g. `finance, audit, pii`).

---

## ⚡ 1-Click Instant Save & Markdown Recompile

Upon choosing **Option 7** (or typing `s` / `save`):

1. **Non-Destructive Local Disk Persistence:** Writes updated YAML directly to `./annotations/<SCHEMA>/tables/<OBJECT>.yml`, allowing safe local verification and diffing before syncing to remote storage or Git.
2. **Colorized YAML Preview:** Renders formatted YAML in the console for confirmation.
3. **Instant Recompile Prompt:**
   ```text
   Recompile Markdown doc for CONTRACTS_TB now? [Y/n]:
   ```
   Pressing **`Enter`** or typing **`y`** immediately recompiles **only that specific Markdown document** (`./docs/<SCHEMA>/tables/CONTRACTS_TB.md`), refreshing frontmatter, Mermaid diagrams, and column tables in under 1 second without a full project rebuild!
