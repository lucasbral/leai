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

# 6. AI Settings (LLMs for Auto-Enrichment, Chat, and Subagents)
ai:
  default_provider: "openai"      # openai | gemini | anthropic | deepseek | qwen | kimi | grok | ollama
  temperature: 0.2
  providers:
    openai:
      api_key: "${OPENAI_API_KEY}"
      model: "gpt-4o-mini"
    gemini:
      api_key: "${GEMINI_API_KEY}"
      model: "gemini-2.0-flash"
    anthropic:
      api_key: "${ANTHROPIC_API_KEY}"
      model: "claude-3-5-sonnet-20241022"
    ollama:
      base_url: "http://localhost:11434/v1"
      model: "qwen2.5-coder:latest"

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
