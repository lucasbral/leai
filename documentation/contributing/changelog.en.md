# Changelog

All notable changes to the **LEAI** project are documented here.

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
