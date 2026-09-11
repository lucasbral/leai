# Changelog

All notable changes to the **LEAI** project are documented here.

## [0.3.2] — 2026

### 🎨 UI Polish, Prompt Localization, and Updater Resilience
* **Update Prompt Localization:** The interactive update prompt now displays `[S/n]` when running in Portuguese (`pt-BR`) and `[Y/n]` in English (`en-US`), accepting both `s/sim` and `y/yes`.
* **Updater Timeout Extension & Resilience:** The PyPI version lookup timeout was increased from 2.0s to 5.0s, and GitHub changelog highlights lookup from 1.5s to 4.0s, preventing false negative timeouts on slow or high-latency networks.
* **Animated SeaweedFS Loading Spinner:** Connecting to SeaweedFS S3 and catalog synchronization now features an animated status spinner (`console.status`), brief success confirmation (`✓ Schema catalog synchronized with SeaweedFS S3 successfully!`), and automatic status cleanup, ensuring a seamless visual transition to the TUI and Web Studio.

---

## [0.3.1] — 2026

### 📋 Audit Log System & Object Manifest for `leai update`
* **Modified Objects Audit Trail:** The `leai update` command now formally tracks and records every Oracle database object modified within the specified time window (`tables`, `views`, `mviews`, packages, procedures, triggers, sequences, indexes, synonyms) along with timestamps (`last_ddl_time`), modifier (`last_modified_by`), and comments.
* **Dual Manifest Format (JSON + Markdown):** Automatic generation of structured JSON manifests (`update_YYYYMMDD_HHMMSS.json` and `latest.json`) for agent and pipeline consumption, alongside human-readable Markdown tables (`update_YYYYMMDD_HHMMSS.md` and `latest.md`).
* **Remote SeaweedFS S3 Persistence:** When remote storage is enabled, update reports and manifests are automatically replicated to the S3 bucket under `logs/updates/`.
* **Configuration & Command-Line Flags:** Supported `--log / --no-log` and `--log-dir` flags in `leai update`, plus `updates_log_path` and `generate_update_log` configuration options in `leai.yml`.

---

## [0.3.0] — 2026

### ⚡ Metadata Search Optimization & Network I/O Elimination via `annotations_index.json`
* **Elimination of N+1 Network Bottleneck in SeaweedFS / S3:** Assistant search tools (`search_database_objects`, `search_column_comments`, `get_table_schema`, and `search_business_documentation`) now leverage a centralized in-memory index (`annotations_index.json`). This eliminates hundreds of sequential HTTP network requests in remote modes (`--no-cache`), reducing search latency from ~150s to under 0.05s.
* **Preservation of Empty Stubs:** All `.yml` annotation files (including empty or default stubs) continue to exist as-is on disk and in S3. The `annotations_index.json` includes only enriched objects (with custom comments, business rules, or tags), accurately classified by `is_annotation_enriched`.
* **Automatic & Incremental Index Sync:** The `leai annotate` command automatically compiles the index, and dedicated methods in `SeaweedFSStorage` maintain the index updated on individual annotation writes and deletions.
* **Smart Table Direct Match in `search_column_comments`:** When querying directly for a known table name (e.g. `WEB_DADOS_FUNC`), the tool immediately isolates that entity and returns all its documented columns.
* **Code Quality & Ruff Linting:** Canonical formatting and linting fixes applied across the codebase according to project guidelines.

---

## [0.2.30] — 2026

### 🛡️ Windows Entrypoint File Lock Handling & CI Cross-Platform Compatibility
* **Graceful Windows Active Process Lock Handling (`os error 32`):** During interactive auto-updates via `uv tool` or `pip` on Windows, the active launcher `leai.exe` cannot be overwritten while executing. `leai/updater.py` now detects this file lock condition and verifies whether the Python package was successfully installed in the virtual environment (`sys.executable` or `uv tool list`), allowing the update to complete smoothly and restart without spurious errors.
* **CI Test Runner Isolation:** Mocked `shutil.which` in Windows entrypoint lock unit tests, preventing Linux/Ubuntu runners on GitHub Actions from erroneously attempting to invoke the Windows-only `_winapi` C module.

---

## [0.2.29] — 2026

### 🌐 Complete TUI Interface & Interactive Banner Localization
* **100% Dynamic TUI & Banner:** Welcome banner, database & AI status cards, quick action shortcuts, starter query suggestions, and bottom toolbar now instantly adapt to the active language (`pt-BR` or `en-US`).
* **Bilingual `/help` Guide & Inspection:** The 28-command interactive reference guide (`/help`) and catalog inspection tables (`/tables` and `/schema`) now feature localized column titles, categories, and descriptions.
* **Consistent Locale Propagation:** Locale initialization integrated directly into `InteractiveTUISession` and CLI root callback, guaranteeing proper inheritance in subcommands such as `leai chat` with `--lang` / `-L` flag support.
* **Parity Assurance & Testing:** New automated test `test_tui_localization_and_session` verifying that language settings in `leai.yml` or environment variables correctly propagate to the TUI.

---

## [0.2.28] — 2026

### 🛡️ Test Runner Execution & Cross-Platform Restart Fix
* **Restart Argument Sanitization:** Filter test runner keywords and flags (`discover`, `run`, `pytest`, `unittest`, `.py` files, `-m`, `--cov`) when rebuilding the restart command in `leai/updater.py`, preventing spurious arguments from being passed to the LEAI CLI.
* **`os.execv` Isolation in Unit Tests:** Mocked `os.execv` in `tests/test_updater.py`, eliminating accidental process replacement in Linux/CI (`ubuntu-latest`) environments and resolving `No such command 'discover'`.

---

## [0.2.27] — 2026

### 🌐 Full Localization Completion & Canonical Standardization
* **100% Canonical English Terminal by Default:** Comprehensive codebase scan and migration of all residual Portuguese terminal messages in CLI and TUI to the `leai/i18n` catalog, ensuring clean English output by default and seamless Portuguese when `language: "pt-BR"` is active.
* **Git Status Tables & TUI Indicators:** The `/git status` table (properties, columns, synchronization states, ahead/behind commit indicators), smart clipboard copy messages, and footer latency hints are 100% localized.
* **Bilingual Markdown Documentation Headers:** Documentation generators (`leai/docs.py`) now dynamically render sections and Markdown headings (`## Overview`, `## Columns`, `## Primary Key`, `## Foreign Keys`, `## Business Rules`) according to active locale (`## Visão Geral`, `## Colunas`, etc. in `pt-BR`).
* **Web Studio Fallbacks & Loading Screens:** Catalog synchronization loaders, SeaweedFS error messages, and Mermaid lineage rendering fallback controls are now fully integrated into the Web UI i18n dictionary.
* **Import Hygiene & Scope Collision Fixes:** Cleaned up redundant local `t` imports that could trigger `UnboundLocalError` and renamed iteration variables shadowing the `t` translator function.

---

## [0.2.26] — 2026

### 🌐 Complete Internationalization (i18n) Architecture (en-US / pt-BR)
* **Native i18n Subsystem (`leai/i18n`):** Lightweight, typed internationalization engine with zero external dependencies, featuring complete message catalogs for English (`en-US`, canonical default) and Brazilian Portuguese (`pt-BR`), with support for Rich markup styling and hierarchical fallback.
* **Flexible Resolution Precedence:** Active locale resolution follows: CLI flag (`--lang` / `-L`) > Environment variable (`LEAI_LANG` / `LEAI_LANGUAGE`) > Config file (`language:` in `leai.yml`) > Canonical default (`en-US`).
* **Standardized Terminal, TUI & Updater:** 100% migration of interactive updater messages, SeaweedFS/Git synchronization alerts, and TUI slash commands (`/copy`, `/rule`, `/git`, `/init`) to the i18n catalog, displaying English by default or Portuguese when configured.
* **Bilingual Configuration Templates:** `leai init --lang pt-BR` generates starter `leai.yml` with Brazilian Portuguese comments and examples, while `leai init` generates the default English version.
* **Studio Web Integration:** `/api/config` endpoints (GET & POST) synchronize the language setting in real time, and the Settings modal features a visual language selector with live UI re-rendering.
* **Bilingual AI System Prompts:** Table enrichment, code object enrichment (procedures/packages/triggers), and Copilot RAG/chat prompts dynamically adapt based on project language, generating business descriptions and rules in Portuguese when `language: "pt-BR"` is active while strictly preserving technical Oracle SQL identifiers.

---

## [0.2.25] — 2026

### 🛡️ Auto-Update Restart Fixes
* **Robust Module-Based Process Restart (`python -m leai`):** Replaced direct `sys.argv` script invocation with `[sys.executable, "-m", "leai"] + sys.argv[1:]`. This completely resolves Windows `[Errno 2] No such file or directory` where the binary executable launcher (`leai.exe` / `~/.local/bin/leai`) was erroneously passed to Python as a script path.
* **Synchronous Foreground Execution on Windows:** Used `subprocess.call` instead of `os.execv` on Windows so the terminal console session remains in the foreground without prematurely handing control back to PowerShell.

---

## [0.2.24] — 2026

### 🛡️ Fixes & Stability
* **Oracle Cursor Leak Prevention:** Added explicit `finally: cursor.close()` blocks in `fetch_schema_metadata`, `fetch_focal_trace`, and `fetch_available_schemas` within `leai/oracle.py`, ensuring deterministic cursor cleanup even on failures.
* **Clipboard Security & Reliability:** Removed `shell=True` on `clip.exe` calls and replaced PowerShell command string interpolation with direct `stdin` piping (`$input | Set-Clipboard`) to prevent quoting and injection issues.
* **Loop Variable Closure Fixes:** Resolved late-binding loop variable issues in async/UI progress callbacks across `leai/web/server.py`, `leai/cli.py`, and `leai/tui/session.py`.
* **Code Quality & Cleanups:** Fixed iteration variable reuse in `leai/ai/tools.py` and simplified dictionary iteration in `leai/workflows/__init__.py`.

---

## [0.2.23] — 2026

### 🌟 Added & Improved
* **Granular AI Configuration in `leai.yml`:** Support for `temperature` and `timeout` configured either globally or overridden per-provider under `ai.providers.<name>`.
* **Agent Operational Limits:** Added `max_history_turns` (chat memory window), `max_agent_iterations` (maximum reasoning tool iterations per turn), and `max_subagent_iterations` (maximum steps for specialized subagents).
* **Local Model Presets:** Native support for `local` (LM Studio, vLLM at `http://localhost:1234/v1` with `qwen2.5`) and `custom` (`http://localhost:8000/v1`), plus updated default model for `ollama` to `qwen2.5-coder:latest`.
* **Expanded Documentation:** Full updates to `leai.example.yml`, `README.md`, and MkDocs documentation covering local runtimes and AI configuration limits.

---

## [0.2.22] — 2026

### 🌟 Added
* **Interactive Auto-Update via PyPI:** The root `leai` command now automatically checks PyPI (`https://pypi.org/pypi/leai/json`) for newer releases using a fail-safe, 2-second timeout check that never blocks execution when offline.
* **Smart Installation Manager Detection:** Automatically distinguishes between `uv tool` (`uv tool upgrade leai`) and standard `pip` (`pip install --upgrade leai`), with protection for local git clones (`editable`).
* **Friendly Interactive Terminal Prompt:** Formatted Rich panel showing current vs latest version, release highlights, changelog link, an interactive `[Y/n]` prompt, and seamless automatic restart via `os.execv`.
* **Flexible Bypass Options:** `--no-update-check` CLI option, `LEAI_NO_UPDATE_CHECK=1` environment variable, and `update_check: false` configuration key in `leai.yml` for automated scripts and CI/CD pipelines.
* **Unified Windows Installer Script (`install.ps1`):** Complete one-liner installation script covering Astral `uv`, Ollama, `qwen2.5-coder` model, LEAI CLI, and automated user workspace configuration.

---

## [0.2.21] — 2026

### 🌟 Added
* **100% Remote AI & Subagent Operations via SeaweedFS S3:** All database inspection tools (`DATABASE_TOOLS_DEFINITIONS`), subagents, and autonomous workflows now operate directly against SeaweedFS S3 storage without requiring local snapshots or YAML files on disk (`raw/`, `annotations/`, `docs/`).
* **Remote Glossary Fallback in `lookup_business_term`:** Instant resolution of business rules, domain definitions, and canonical SQL filters directly from the remote S3 bucket (`annotations/glossary.yml`).
* **Remote Annotation Enrichment for Schemas and Columns:** `get_table_schema`, `search_column_comments`, and `search_database_objects` fetch business descriptions, rules, tags, and human column comments persisted in SeaweedFS for Tables, Views, and Materialized Views.
* **Remote Semantic Documentation Search:** `search_business_documentation` scans remote S3 annotation manifests via `list_annotated_objects()` when local files are absent.
* **Remote Dossiers and RAG:** `build_rag_context` accesses remote SeaweedFS annotations to assemble focal entity context dossiers.
* **Storage-Aware CLI Commands:** `leai agent run` and `leai workflow run` now support `--seaweed` (`-W`) and `--no-cache`, pulling technical snapshots seamlessly from SeaweedFS.

---

## [0.2.20] — 2026

### 🌟 Added
* **Direct Universal Rules Sync with SeaweedFS in Web Studio:** The Web Studio interface (`leai serve` / `/serve`) now directly queries, creates, and removes business rules and glossary terms against the remote SeaweedFS S3 bucket (`annotations/glossary.yml`).
* **Visual Sync Feedback in Web Studio:** Refresh button with dynamic rotation animation (`spin`) and instant toast notifications reporting synchronized rule counts.
* **Real-time Progress & Execution Timing in `leai update` and `/update`:** Step-by-step progress tracking for tables, views, packages, and S3 uploads with `[current/total]` counters and elapsed duration metrics per schema and in aggregate.
* **Native S3 Bucket Versioning on SeaweedFS:** Automated support and verification for S3 bucket versioning (`Status: Enabled`) ensuring revision history and rollback capabilities for annotations and metadata.

### ⚡ Fixes
* **Modified Objects Count Fix:** Resolved issue in `count_schema_objects` query that defaulted empty schemas to reporting 1 modified object (`max(1, total)` removed).
* **Glossary Test Rules Cleanup:** Eliminated hardcoded fallback rules ("Estágio Probatório") on server startup, preserving a clean workspace when no terms exist.

---

## [0.2.19] — 2026

### 🌟 Added
* **`leai update` CLI Command & `/update` in TUI:** Surgical incremental extraction of database objects modified within hours (`--hours`) or days (`--days`), merging technical schemas with consolidated snapshot and uploading deltas to SeaweedFS.
* **SeaweedFS Annotation Preservation & Merging:** Non-destructive merge logic preserving existing human descriptions, tags, business rules, and column comments in SeaweedFS without overwriting them with blank stubs.
* **Continuous `GLOSSARY.yml` Sync with SeaweedFS:** Automated synchronization and cloud persistence of corporate domain rules at `annotations/glossary.yml`.
* **`leai rule del` (CLI) and `/rule del` (TUI):** Removal of business terms with immediate synchronization against SeaweedFS bucket.
* **Non-destructive Rule Merging (`merge_glossaries`):** Prioritization of centralized SeaweedFS definitions during conflicts and union of domain tags and SQL filters.
* **TUI Autocompletion:** Enhanced autocompletion for `/update` and `/rule [list|add|del|find]`.

---

## [0.2.18] — 2026

### 🌟 Added
* **`leai doctor` CLI Command:** New command and official alias for `check`, providing end-to-end pre-flight health checks across Oracle Database (`v$version`), catalog permissions, pipeline directories, S3 bucket (SeaweedFS), AI model connectivity, and GitOps status.
* **`/doctor` and `/check` in TUI:** In-terminal pre-flight diagnostics runnable directly inside the interactive session (`leai chat`) with structured Rich table feedback.
* **Updated Documentation:** Expanded CLI and TUI slash command reference tables with `/doctor`, `/seaweed`, `/git`, `/rule`, `/agent`, and `/workflow`.

---

## [0.2.17] — 2026

### 🌟 Added
* **SeaweedFS S3 Synchronization in Web Studio (`/serve`):** Annotation edits made in the browser (`POST /api/annotations`) are synchronized directly to the S3 bucket in real time.
* **Remote Annotation Fallback in Web Studio:** The `GET /api/object` endpoint automatically fetches annotations from SeaweedFS if the local file does not exist, populating local cache transparently.
* **Visual S3 Feedback in Web UI:** Header status badge (`☁️ S3: <bucket>`) and sync confirmation message in the save toast notification.
* **`/seaweed sync` Subcommand in TUI:** Smart bi-directional synchronization (push + pull with SHA-256 deduplication) directly runnable from the interactive terminal.
* **Local Disk Isolation for `/doc`:** The in-terminal documentation editor saves exclusively to local disk, preventing unintended remote uploads.

### ⚡ Improvements
* Support and documentation for S3 Lifecycle Rules (`NoncurrentVersionExpiration`) targeting `annotations/` prefix to purge non-current version history.
* Terminal autocompletion updated with `/seaweed sync` and `--seaweed`, `-W`, and `--no-cache` flags for `/annotate`.

---

## [0.2.15] — 2026

### 🌟 Added
* **Official GitHub Pages Documentation:** Full bilingual documentation suite (English and Portuguese) using Material for MkDocs.
* **In-Memory Autonomous Agent:** Enhanced ReAct reasoning loop and PL/SQL subprogram compression inside `leai chat`.
* **Multi-Provider AI Architecture:** Native lightweight REST clients for OpenAI, Gemini, Claude, DeepSeek, Qwen, and local Ollama.

### ⚡ Improvements
* Multi-level dependency lineage tracing (`trace`) with automated risk calculations.
* Recursive dereferencing of public and private synonyms (`PUBLIC SYNONYM`) and database links (`@dblink`).
* Surgical skeletonization of PL/SQL packages delivering up to 95% token reduction.

---

## [0.2.0] — Initial Releases

* Technical data dictionary extraction to JSON.
* Non-destructive, human-editable YAML business annotations layer.
* Compilation to Markdown documents with YAML Frontmatter and Mermaid diagrams.
