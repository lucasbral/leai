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

### 3. `leai rule del <TERM>` (or `delete`)
Removes a business term or rule from the local glossary and the SeaweedFS bucket.

```bash
leai rule del ACTIVE_CUSTOMER
```

---

### 4. `leai rule show <TERM>`
Displays the comprehensive specification sheet of a codified rule, including linked tables and exact canonical SQL clauses.

```bash
leai rule show ACTIVE_CUSTOMER
```

---

## ☁️ Continuous SeaweedFS (S3) Synchronization

When SeaweedFS is configured in `leai.yml` (or via `-W` / `--seaweed`), the corporate glossary is automatically managed in the cloud:

- **Immediate Persistence**: Every addition (`leai rule add`) or deletion (`leai rule del`) writes locally and immediately pushes to `annotations/glossary.yml` in the S3 bucket.
- **Automated Pipelines (`annotate` and `update`)**: Both `leai annotate` and `leai update` perform **non-destructive merges** between local and remote glossaries. If there is a definition conflict, the centralized SeaweedFS definition is prioritized to protect institutional knowledge, while tags and examples are unified.
- **Offline / `--no-cache` Resilience**: AI agents and tools seamlessly fall back to loading the glossary directly from SeaweedFS when local cache files are absent.

---

## 💻 In-Terminal Interactive Commands (TUI Copilot)

Inside interactive copilot sessions (`leai chat`), manage domain rules directly:

| Command | Description |
| :--- | :--- |
| `/rule list` | Display rich visual formatted table with all active glossary terms and rules. |
| `/rule add [term]` | Guided prompt wizard to register term, definition, primary table, and SQL filters. |
| `/rule del <term>` | Delete specified rule from local disk and SeaweedFS bucket. |
| `/rule find <term>` | Search glossary terms by keyword relevance and semantic similarity. |

---

## 🎯 Impact on AI & RAG Precision

When running `leai ask` or interactive `leai chat`, the agent queries the codified rules catalog before formulating answers or composing queries.

* **User Prompt:** *"Which customers qualify as active in the system?"*
* **Agent Behavior:** Rather than guessing status codes, the agent queries the glossary tool and cites the verified canonical filter `RECORD_STATUS = 'A' AND IS_LOCKED = 0`.
