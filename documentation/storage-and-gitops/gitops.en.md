# GitOps & Version Control (`leai git`)

LEAI provides native version control operations to treat database documentation as first-class code (**Docs-as-Code**).

With built-in Git/GitLab/GitHub synchronization, all alterations to business annotations, catalog snapshots, and generated markdown are versioned, traceable, and team-collaborative.

---

## ⚡ Git Group Commands

### 1. `leai git status`
Checks local repository status across paths tracked by LEAI (`annotations/`, `docs/`, `raw/`, `leai.yml`).

```bash
leai git status
# or fetching upstream changes:
leai git status --fetch
```

---

### 2. `leai git pull`
Pulls recent documentation updates contributed by other team members from the remote Git repository.

```bash
leai git pull
```

---

### 3. `leai git sync`
Stages all modified annotations and generated documentation, creates a commit, and pushes to the configured remote branch.

| Parameter / Flag | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `-m`, `--message TEXT` | Option | Auto-generated | Custom message for the Git commit. |

```bash
leai git sync --message "docs(billing): codify tax calculation business rules"
```

---

## ⚙️ Configuration in `leai.yml`

```yaml
git:
  enabled: true                                  # Enables leai git commands and /git slash command
  remote_url: "https://gitlab.internal/docs/db-oracle.git"
  branch: "main"                                 # Tracking branch
  author_name: "LEAI Bot"                        # Commit author name
  author_email: "leai-bot@internal"              # Commit author email
  auto_sync: false                               # Automatic push after extract/compile
  tracked_paths:                                 # Paths tracked by version control
    - "annotations"
    - "docs"
    - "raw"
    - "leai.yml"
```
