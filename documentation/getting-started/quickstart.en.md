# Quickstart Guide

This hands-on guide walks you through setting up and running LEAI from scratch on any Oracle database environment.

---

## ⚡ 3-Minute Step-by-Step

### Step 1: Initialize Your Project Directory

Create a working directory for your project documentation and run `init`:

```bash
mkdir my-database-doc
cd my-database-doc
leai init
```

This generates a starter `leai.yml` configuration file with documented connection strings and filter options.

---

### Step 2: Configure Your Oracle Connection

Open the generated `leai.yml` file. You can safely reference environment variables to avoid hardcoding secrets:

```yaml
# leai.yml
dsn: "oracle://${DB_USER}:${DB_PASS}@${DB_HOST}:1521/${DB_SERVICE}"

# Schemas to extract:
schemas:
  - HR
  - SALES

# Pipeline directories:
rawPath: "./raw"
annotationsPath: "./annotations"
docPath: "./docs"

# Categories of objects to process:
object_types:
  - tables
  - views
  - mviews
  - procedures
  - functions
  - packages
  - triggers
  - synonyms
```

Set the environment variables in your terminal:

=== "Linux / macOS"
    ```bash
    export DB_USER="metadata_reader"
    export DB_PASS="secret_pass"
    export DB_HOST="db.company.internal"
    export DB_SERVICE="ORCLPDB1"
    ```

=== "Windows PowerShell"
    ```powershell
    $env:DB_USER="metadata_reader"
    $env:DB_PASS="secret_pass"
    $env:DB_HOST="db.company.internal"
    $env:DB_SERVICE="ORCLPDB1"
    ```

---

### Step 3: Run the Complete Pipeline

To execute the entire reverse-engineering and compilation pipeline in a single command:

```bash
leai
# or explicitly:
leai generate
```

LEAI will process the three stages sequentially:
1. **Extraction:** Connects to Oracle and saves pure technical snapshots to `./raw/*.json`.
2. **Annotation:** Generates editable business stubs in `./annotations/*.yml` (safely preserving existing descriptions).
3. **Compilation:** Compiles production Markdown docs into `./docs/*.md` with embedded Mermaid.js diagrams and YAML frontmatter.

---

### Step 4: Explore and Interact

#### Inspect object lineage and impact
```bash
leai trace EMPLOYEES --depth 2
```

#### Ask natural language questions with AI
```bash
export OPENAI_API_KEY="sk-..."
leai ask "Which table stores salary history and what triggers react on insert?"
```

#### Launch an interactive terminal chat with AI tools
```bash
leai chat
```
