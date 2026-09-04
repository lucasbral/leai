# Utilities, Diagnostics & Governance

This section covers commands for environment health diagnostics, repository initialization, and database schema change auditing.

---

## 1. `leai init`

Initializes a workspace directory by generating a starter `leai.yml` configuration template.

```bash
leai init
```

* If a `leai.yml` file already exists, it issues a warning and prevents accidental overwrites.
* Provides connection examples, object type filters, and AI provider templates.

---

## 2. `leai doctor` (or `leai check`)

Runs automated pre-flight diagnostics to ensure your environment is fully operational for LEAI.

```bash
leai doctor
```

### What `doctor` checks:
* **Network Connectivity:** Validates TCP and database listener connectivity to the configured Oracle host and port.
* **Catalog Permissions:** Tests read access across Oracle system views: `ALL_TABLES`, `ALL_TAB_COLUMNS`, `ALL_CONSTRAINTS`, `ALL_SOURCE`, and `ALL_SYNONYMS`.
* **Workspace Permissions:** Checks read and write access for `rawPath`, `annotationsPath`, and `docPath`.
* **AI API Keys:** Verifies the availability and readiness of configured LLM credentials.

---

## 3. `leai changes`

Audits schema evolution and detects *schema drift* by comparing the active snapshot against previous extractions in `./raw/`.

```bash
leai changes
```

### Change Audit Report:
* **New:** Tables, columns, or views added to the schema.
* **Dropped:** Tables, columns, or constraints that have been removed.
* **Altered:** Column type or nullability modifications (e.g. `VARCHAR2(50)` expanded to `VARCHAR2(100)`).
* **Source Updates:** PL/SQL package bodies or triggers with altered code implementations.
