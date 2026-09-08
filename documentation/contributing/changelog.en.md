# Changelog

All notable changes to the **LEAI** project are documented here.

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
