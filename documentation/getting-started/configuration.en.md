# Configuration (`leai.yml`)

The `leai.yml` configuration file controls all aspects of extraction, filtering, storage paths, GitOps version control, and AI integrations for LEAI.

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

# 3. Pipeline Paths & Logs
rawPath: "./raw"                  # Technical snapshots in JSON
annotationsPath: "./annotations"  # Business annotations in YAML
docPath: "./docs"                  # Final Markdown documents
updates_log_path: "./logs/updates" # Update audit logs and manifests (latest.json, latest.md)
generate_update_log: true         # Whether to generate update audit logs in leai update

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

# 6. AI Settings (LLMs for Auto-Enrichment, Chat, and Subagents)
ai:
  default_provider: "ollama"      # ollama | local | openai | gemini | anthropic | deepseek | qwen | kimi | grok
  temperature: 0.2                # Global default temperature (0.0 to 1.0)
  timeout: 300.0                  # Global default request timeout in seconds
  max_history_turns: 15           # History context memory window in chat turns
  max_agent_iterations: 10        # Maximum reasoning tool iterations per turn
  max_subagent_iterations: 5      # Maximum iterations for specialized subagents
  providers:
    ollama:
      base_url: "http://localhost:11434/v1"
      model: "qwen2.5-coder:latest"
      temperature: 0.1
      timeout: 300.0
    local:
      base_url: "http://localhost:1234/v1" # e.g. LM Studio, vLLM, LocalAI
      model: "qwen2.5"
      temperature: 0.1
    openai:
      api_key: "${OPENAI_API_KEY}"
      model: "gpt-4o-mini"
      temperature: 0.2
      timeout: 120.0
    gemini:
      api_key: "${GEMINI_API_KEY}"
      model: "gemini-2.5-flash"
    anthropic:
      api_key: "${ANTHROPIC_API_KEY}"
      model: "claude-3-5-sonnet-20241022"

# 7. Git / GitLab / GitHub Synchronization (GitOps)
git:
  enabled: false                                 # Enables leai git commands and /git
  remote_url: "${GIT_REMOTE_URL}"                # Remote repository URL
  branch: "main"                                 # Tracking branch
  author_name: "LEAI Bot"                        # Commit author name
  author_email: "leai@company.com"               # Commit author email
  auto_sync: false                               # Automatic push after extract/compile
  tracked_paths:
    - "annotations"
    - "docs"
    - "raw"
    - "leai.yml"

# 8. Distributed Storage / Object Storage (SeaweedFS / S3)
storage:
  seaweedfs:
    enabled: false                                 # Automatically routes operations to S3
    endpoint_url: "http://localhost:8333"          # SeaweedFS or MinIO S3 gateway
    bucket: "leai"                                 # S3 bucket name
    access_key: "${SEAWEEDFS_ACCESS_KEY}"
    secret_key: "${SEAWEEDFS_SECRET_KEY}"
    region_name: "us-east-1"
    raw_prefix: "raw"                              # Folder prefix for JSON snapshots
    annotations_prefix: "annotations"              # Folder prefix for YAML annotations
    auto_create_bucket: true                       # Creates bucket if missing
    no_cache: false                                # Local disk cache or pure remote
    incremental: true                              # SHA-256 hash deduplication

# 9. Interface Language & Localization
language: "en-US"                                  # "en-US" (canonical default) or "pt-BR"

# 10. Automatic PyPI Update Check
update_check: true                                 # true (default) or false
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

---

## 🌐 Internationalization & Language (`language`)

LEAI provides a built-in native internationalization engine (`leai/i18n`) with English as canonical default and parity bilingual catalogs (`en-US` and `pt-BR`):

```yaml
language: "en-US" # or "pt-BR" (default: "en-US")
```

### What the Language Setting Affects:
1. **Terminal & CLI:** Formatted status panels, tabular outputs, progress spinners, and pipeline execution summaries.
2. **Interactive TUI Session:** Command responses (`/git status`, `/help`, `/rule`, `/copy`, `/model`).
3. **AI Prompts & Responses:** When configured to `pt-BR`, the system prompt instructs the LLM to enrich empty column descriptions and business rules in Brazilian Portuguese (while preserving technical SQL identifiers). In `en-US`, generation is performed strictly in English.
4. **Compiled Markdown Documentation:** Documents generated under `docs/` use localized headers (`## Overview`, `## Columns`, `## Business Rules` vs. `## Visão Geral`, `## Colunas`, `## Regras de Negócio`).
5. **Web Studio:** Web user interface labels, modals, loading spinners, and real-time language switching via REST API (`/api/config`).

### Resolution Precedence
LEAI determines the active locale according to the following strict priority:
1. **CLI Flag:** `--lang <locale>` or `-L <locale>` (e.g. `leai --lang en-US ask "what are the main sales tables?"`)
2. **Environment Variable:** `LEAI_LANG` or `LEAI_LANGUAGE` (e.g. `export LEAI_LANG=en-US`)
3. **Configuration File:** `language:` key in `leai.yml`
4. **Canonical Fallback:** `en-US`

### Quick Initialization with Language
To generate a `leai.yml` pre-configured and documented in Portuguese:
```bash
leai init --lang pt-BR
```
Or in English (default):
```bash
leai init --lang en-US
```

---

## 🔄 Automatic Update Check (`update_check`)

By default, LEAI performs a lightweight non-blocking query to PyPI on startup to verify whether a newer release is available.

```yaml
update_check: true # true (default) or false
```

### How to Disable Update Checking:
1. **In `leai.yml`:** Set `update_check: false`.
2. **Via Environment Variable:** Export `LEAI_NO_UPDATE_CHECK=1` or `LEAI_NO_UPDATE_CHECK=true`.
3. **Via Command Line (Global Flag):** Pass `--no-update-check` to any command:
   ```bash
   leai --no-update-check extract
   leai --no-update-check chat
   ```

---

## 📋 Update Audit Logs (`updates_log_path` & `generate_update_log`)

When running `leai update`, LEAI can automatically record a manifest and report of all objects extracted and modified in Oracle:

```yaml
updates_log_path: "./logs/updates" # Output directory for log files (Default: ./logs/updates)
generate_update_log: true         # Generates JSON and Markdown audit logs (Default: true)
```

### Generated Files per Run:
- **`update_YYYYMMDD_HHMMSS.json` & `latest.json`:** Structured manifest with UTC timestamp, search window, modifier (`last_modified_by`), Oracle timestamp (`last_ddl_time`), and sync counts.
- **`update_YYYYMMDD_HHMMSS.md` & `latest.md`:** Readable report with formatted tables for VS Code or GitHub.
- **SeaweedFS / S3 Synchronization:** If `--seaweed` or S3 storage is enabled, files are automatically synced to the bucket under `logs/updates/`.
