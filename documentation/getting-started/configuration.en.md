# Configuration (`leai.yml`)

The `leai.yml` configuration file controls all aspects of extraction, filtering, storage paths, and AI integrations for LEAI.

---

## 📄 Complete Annotated Example

```yaml
# ==============================================================================
# LEAI Configuration
# ==============================================================================

# 1. Oracle Connection (DSN)
# Supports environment variable interpolation via ${VARIABLE}
dsn: "oracle://${DB_USER}:${DB_PASS}@${DB_HOST}:1521/${DB_SERVICE}"

# 2. Target Schemas
# Can be a list of schema names or "ALL" (requires DBA / SELECT ANY DICTIONARY)
schemas:
  - HR
  - SALES

# 3. Pipeline Paths
rawPath: "./raw"                  # Technical snapshots in JSON
annotationsPath: "./annotations"  # Business annotations in YAML
docPath: "./docs"                  # Final Markdown documents

# 4. Inclusion & Exclusion Filters (SQL LIKE Wildcards)
include:
  - EMPLOYEES
  - ORDERS_%
exclude:
  - BIN$%                         # Oracle Recycle Bin tables
  - SYS_%

# 5. Object Categories
object_types:
  - tables
  - views
  - mviews
  - procedures
  - functions
  - packages
  - triggers
  - synonyms

# 6. AI Settings (Optional - for leai ask, leai chat, and leai enrich)
ai:
  provider: "openai"              # openai | gemini | claude | deepseek | qwen | ollama
  model: "gpt-4o"
  temperature: 0.2
  max_iterations: 10              # Max turns in the autonomous tool-calling loop
```

---

## 🔑 Supported DSN Formats

LEAI supports various ways to declare connection strings:

### URL Syntax (Standard)
```yaml
dsn: "oracle://user:password@host:1521/service_name"
```

### EZCONNECT Syntax (Native Oracle)
```yaml
dsn: "user/password@host:1521/service_name"
```

### Full TNS Descriptor (for TCPS, Wallets, or Oracle Cloud / Autonomous DB)
```yaml
dsn: "user/password@(DESCRIPTION=(ADDRESS=(PROTOCOL=TCPS)(HOST=db.example.com)(PORT=1522))(CONNECT_DATA=(SERVICE_NAME=my_service)))"
```

---

## 🎯 Object Filtering

You can use the `include` and `exclude` filters to selectively target database entities:

* `%`: Matches zero or more characters (e.g. `TB_%` matches any object starting with `TB_`).
* `_`: Matches exactly one character.

> [!TIP]
> If `include` is left empty, LEAI will extract **all** objects matching `object_types` that are not explicitly matched by `exclude`.
