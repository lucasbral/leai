# CLI Overview

LEAI provides a comprehensive command-line interface built with Typer and styled with Rich for formatted tables, hierarchical trees, and animated progress spinners.

---

## 🧭 Complete Command Matrix

| Command | Group | Brief Description |
| :--- | :--- | :--- |
| **`leai`** (or `generate`) | Pipeline | Runs the complete 3-step pipeline: `extract`, `annotate`, and `compile`. |
| **`leai extract`** | Pipeline | Connects to Oracle and dumps metadata into raw JSON snapshots. |
| **`leai annotate`** | Pipeline | Generates/updates business YAML stubs without overwriting existing notes. |
| **`leai compile`** | Pipeline | Compiles metadata and annotations into Markdown and Mermaid diagrams. |
| **`leai doc <OBJ>`** | Documentation | Opens the in-terminal interactive editor to document a specific object. |
| **`leai trace <OBJ>`** | Analysis | Traces multi-level upstream dependencies and downstream consumers. |
| **`leai enrich`** | AI / LLM | Uses an LLM to automatically populate empty business descriptions. |
| **`leai ask <QUERY>`** | AI / LLM | Answers natural language questions about your schemas from the CLI. |
| **`leai chat`** | AI / LLM | Launches an interactive conversation with the autonomous agent and tools. |
| **`leai models`** | AI / LLM | Lists, benchmarks, and checks connectivity for configured AI providers. |
| **`leai serve`** | Web Studio | Launches the local LEAI Web Documentation & Annotation Studio server. |
| **`leai agent`** | Subagents | Manages specialized subagent personas (`list`, `run`). |
| **`leai workflow`** | Automation | Executes multi-step engineering pipelines (`impact-analysis`, `safe-refactor`). |
| **`leai rule`** | Business Rules | Manages glossary terms and canonical SQL predicate rules (`list`, `add`, `show`). |
| **`leai git`** | Versioning | GitOps operations to synchronize database documentation (`status`, `pull`, `sync`). |
| **`leai seaweed`** | Storage | Manages remote persistence in SeaweedFS/S3 Object Storage (`status`, `push`, `pull`, `sync`). |
| **`leai changes`** | Governance | Detects schema alterations and drift via Oracle's `LAST_DDL_TIME`. |
| **`leai doctor`** (or `check`) | Diagnostics | Validates Oracle connectivity, catalog permissions, and AI dependencies. |
| **`leai init`** | Setup | Generates a starter `leai.yml` configuration file. |

---

## ⚙️ Common Global Options

* `-c`, `--config PATH`: Targets a custom configuration file (Default: `leai.yml`).
* `--seaweed`: Routes snapshot and annotation operations through SeaweedFS/S3 Object Storage.
* `--no-cache`: Operates in 100% remote mode without saving snapshots to local disk.
* `--help`: Displays detailed usage instructions and flags for any command.
* `--version`: Displays the installed LEAI version.
