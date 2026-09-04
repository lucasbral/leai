# CLI Overview

LEAI provides a powerful, intuitive command-line interface built with Typer and styled with Rich for formatted tables, progress indicators, and terminal syntax highlighting.

---

## 🧭 Command Summary

| Command | Group | Brief Description |
| :--- | :--- | :--- |
| **`leai`** (or `generate`) | Pipeline | Runs the complete 3-step pipeline: `extract`, `annotate`, and `compile`. |
| **`leai extract`** | Pipeline | Connects to Oracle and dumps metadata into raw JSON snapshots. |
| **`leai annotate`** | Pipeline | Generates/updates business YAML stubs without overwriting existing notes. |
| **`leai compile`** | Pipeline | Compiles metadata and annotations into Markdown and Mermaid diagrams. |
| **`leai trace <OBJ>`** | Analysis | Traces multi-level upstream dependencies and downstream consumers. |
| **`leai enrich`** | AI / LLM | Uses an LLM to automatically populate empty business descriptions. |
| **`leai ask <QUERY>`** | AI / LLM | Answers natural language questions about your schemas from the CLI. |
| **`leai chat`** | AI / LLM | Launches an interactive conversation with the autonomous agent and tools. |
| **`leai models`** | AI / LLM | Lists, benchmarks, and checks connectivity for configured AI providers. |
| **`leai changes`** | Governance | Detects schema drift by comparing current extraction against prior snapshots. |
| **`leai doctor`** (or `check`) | Diagnostics | Validates Oracle connectivity, catalog permissions, and AI dependencies. |
| **`leai init`** | Setup | Generates a starter `leai.yml` configuration file. |

---

## ⚙️ Global Options

* `--help`: Displays detailed usage instructions and flags for any command.
* `--version`: Displays the installed LEAI version.
