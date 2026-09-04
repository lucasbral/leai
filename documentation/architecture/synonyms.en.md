# Transparent Synonym Resolution

In enterprise Oracle environments, private and public synonyms (`PUBLIC SYNONYM`) are pervasive. They abstract actual schema names, simplify database migrations, and facilitate remote object access over Database Links (`@dblink`).

However, for LLMs and static documentation tools, synonyms create a severe blind spot: PL/SQL subprograms invoke names that appear missing from the target schema, causing hallucinations and broken lineage.

---

## 🧩 The Challenge

Consider a procedure in the `SALES_APP` schema:

```sql
PROCEDURE PROCESS_ORDER IS
BEGIN
    INSERT INTO CUSTOMERS (ID, NAME) VALUES (1, 'Acme Corp');
END;
```

If `SALES_APP` does not own a physical table called `CUSTOMERS`, standard AI assistants assume the table is missing or invent phantom structures.

In reality, Oracle has a synonym:
```sql
CREATE PUBLIC SYNONYM CUSTOMERS FOR MASTER_DATA.CORP_CUSTOMERS_TB@DBL_HQ;
```

---

## ⚡ How LEAI Solves It

During the extraction phase, LEAI snapshots all synonym definitions (`ALL_SYNONYMS`) and builds a recursive dereferencing resolver:

```mermaid
flowchart LR
    A[Code Reference:<br/>CUSTOMERS] -->|Resolve Synonym| B[MASTER_DATA.CORP_CUSTOMERS_TB]
    B -->|Detect DB Link| C[@DBL_HQ]
    C -->|Unified Metadata| D[Injected into LLM Context]
```

1. **Automatic Dereferencing:** When inspecting PL/SQL code or executing `leai ask` / `chat`, synonym references immediately resolve to their underlying physical targets.
2. **Database Link Awareness:** LEAI flags when an object points across network boundaries via `@dblink`.
3. **Zero Hallucination:** The LLM receives the authentic column types and constraints of the true physical entity, even if the user or code uses an alias.
