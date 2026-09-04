# AI Commands (ask, chat, models)

LEAI transforms your Oracle database catalog into an interactive knowledge base capable of answering complex engineering and business logic questions directly from your terminal.

---

## 1. `leai ask <QUESTION>`

Answers one-off natural language queries about database architecture, tables, procedures, and business rules with surgical context injection.

```bash
leai ask "What is the business rule inside CALC_TERMINATION and which tables does it query?" -p gemini
```

### Parameters and Flags:

| Parameter / Flag | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `QUESTION` | Argument | **Required** | Natural language question regarding database logic or schema. |
| `-p`, `--provider TEXT` | Option | From config | AI provider (`openai`, `gemini`, `claude`, `deepseek`, `ollama`, etc.). |
| `-m`, `--model TEXT` | Option | From config | Target model identifier. |
| `-c`, `--config PATH` | Option | `leai.yml` | Path to `leai.yml`. |
| `--seaweed` | Flag | `False` | Resolves metadata from remote S3 bucket. |
| `--no-cache` | Flag | `False` | Operates in 100% remote mode without local files. |

---

## 2. `leai chat`

Launches an interactive, stateful terminal console styled with Catppuccin Mocha themes, persistent memory, smart autocompletion, and live tool calling.

```bash
# Terminal interactive copilot:
leai chat -p gemini -m gemini-2.0-flash

# Launch and open Web Chat Studio directly in browser:
leai chat --web
```

### Parameters and Flags:

| Parameter / Flag | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `-p`, `--provider TEXT` | Option | From config | Active AI provider. |
| `-m`, `--model TEXT` | Option | From config | Target AI model identifier. |
| `-c`, `--config PATH` | Option | `leai.yml` | Path to configuration file. |
| `-w`, `--web` | Flag | `False` | Launches Web Studio server and opens chat in browser. |
| `--seaweed` | Flag | `False` | Resolves metadata from remote S3 storage. |
| `--no-cache` | Flag | `False` | Runs purely in memory. |

### 📋 In-Session Slash Commands:

| Command | Category | Description |
| :--- | :--- | :--- |
| `/copy [all\|code\|N]` | Clipboard | Copy last AI response or specific code block directly to OS clipboard. |
| `/doc [obj]` | Documentation | Open interactive in-terminal YAML annotation & documentation editor. |
| `/rule [list\|add\|find]` | Glossary | Manage global business rules and canonical domain filters. |
| `/enrich [obj]` | AI Studio | Auto-enrich business descriptions & rules with LLM. |
| `/compile [obj]` | Pipeline | Compile final Markdown docs in `docs/` (supports single object). |
| `/annotate [-W]` | Pipeline | Synchronize YAML annotation stubs in `annotations/` and/or SeaweedFS. |
| `/extract [s\|d\|-W]` | Pipeline | Connect to Oracle and extract fresh raw metadata snapshot. |
| `/seaweed [status\|push\|pull\|sync]` | SeaweedFS | Check SeaweedFS S3 status, push, pull, or bi-directional sync. |
| `/serve [port\|stop]` | Web Studio | Launch interactive Web Studio with in-browser editor & real-time sync. |
| `/git [status\|pull\|sync]` | GitOps | Check Git commit status, pull updates, or sync metadata with remote. |
| `/trace <obj>` | Lineage | Perform inline dependency lineage & impact X-ray with Mermaid. |
| `/tables` | Inspection | List all tables with column counts and primary keys. |
| `/schema [s]` | Inspection | Show comprehensive overview of all catalog objects. |
| `/changes [d]` | Inspection | Inspect database objects modified in last N days (Default: 7). |
| `/agent <role> <task>` | Multi-Agent | Execute specialized subagents (`catalog`, `plsql`, `lineage`, `patch`, `doc`). |
| `/workflow <name> <obj>` | Workflows | Execute autonomous pipelines (`impact`, `refactor`). |
| `/models [p]` | AI Config | List all available AI models returned by provider API. |
| `/model <p> [m]` | AI Config | Switch AI provider and model at runtime. |
| `/audit [last\|session\|export]`| Audit & Logs | Inspect AI tool call trace, latency & session audit log. |
| `/tools` | Audit & Logs | Quick viewer for last turn's tool execution inputs/outputs. |
| `/save [file.md]` | Session | Export current conversation transcript to Markdown. |
| `/doctor` (or `/check`) | Diagnostics | Run pre-flight health checks across Oracle, AI, Storage, and Git. |
| `/init` | Setup | Initialize or update the `leai.yml` configuration file. |
| `/clear` | Session | Clear conversation memory and reset terminal screen. |
| `/exit`, `/quit` | Session | Exit LEAI interactive copilot. |

---

## 3. `leai models`

Tests credentials, lists available models returned by provider APIs, and benchmarks roundtrip REST latency.

```bash
leai models -p gemini
leai models -p openai
```

| Parameter / Flag | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `-p`, `--provider TEXT` | Option | All | Filters by specific provider. |
| `-c`, `--config PATH` | Option | `leai.yml` | Path to `leai.yml`. |
