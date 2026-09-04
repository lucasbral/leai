# Glossary & Canonical Rules (`leai rule`)

In enterprise databases, crucial business rules frequently rely on tacit team knowledge or canonical SQL predicate conventions (e.g. `WHERE STATUS = 'A' AND DELETED = 0`).

The `leai rule` command suite allows engineering teams to codify, audit, and inject these canonical business definitions directly into the knowledge layer utilized by LLMs and LEAI subagents.

---

## ⚡ Rule Group Commands

### 1. `leai rule list`
Lists all codified business rules and glossary concepts registered in the project.

```bash
leai rule list
```

---

### 2. `leai rule add <TERM>`
Codifies or synchronizes a business concept or canonical SQL predicate rule.

| Parameter / Flag | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `TERM` | Argument | Yes | Identifying business keyword or phrase (e.g. `ACTIVE_CUSTOMER`). |
| `--definition` | Option | No | Plain-language functional definition. |
| `--table` | Option | No | Database table bound to this domain rule. |
| `--canonical-filter` | Option | No | Exact SQL predicate clause (e.g. `STATUS = 'A'`). |
| `--tags` | Option | No | Comma-separated domain labels (e.g. `sales,compliance`). |
| `-c`, `--config PATH` | Option | No | Path to `leai.yml`. |

#### Example:
```bash
leai rule add "ACTIVE_CUSTOMER" \
  --table "CUSTOMERS_TB" \
  --canonical-filter "RECORD_STATUS = 'A' AND IS_LOCKED = 0" \
  --definition "Customers eligible to place orders and receive billing invoices" \
  --tags "sales,billing"
```

---

### 3. `leai rule show <TERM>`
Displays the comprehensive specification sheet of a codified rule, including linked tables and exact canonical SQL clauses.

```bash
leai rule show ACTIVE_CUSTOMER
```

---

## 🎯 Impact on AI & RAG Precision

When running `leai ask` or interactive `leai chat`, the agent queries the codified rules catalog before formulating answers or composing queries.

* **User Prompt:** *"Which customers qualify as active in the system?"*
* **Agent Behavior:** Rather than guessing status codes, the agent queries the glossary tool and cites the verified canonical filter `RECORD_STATUS = 'A' AND IS_LOCKED = 0`.
