# Utilities, Diagnostics & Governance

This section covers commands for environment health diagnostics, repository initialization, and database schema change auditing.

---

## 1. `leai init`

Initializes a workspace directory by generating a starter `leai.yml` configuration template.

```bash
# Standard initialization (English default):
leai init

# Initialize starter config with Portuguese comments and examples:
leai init --lang pt-BR

# Overwrite existing file:
leai init -f --lang en-US
```

### Parameters and Flags:

| Parameter / Flag | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `-L`, `--lang LOCALE` | Option | `en-US` | Template language for generated config (`en-US` or `pt-BR`). |
| `-f`, `--force` | Flag | `False` | Overwrites existing `leai.yml` without prompt. |
| `-o`, `--output PATH` | Option | `leai.yml` | Target configuration file path. |

---

## 2. `leai doctor`

Runs automated pre-flight health checks to ensure overall environment integrity.

```bash
leai doctor
```

### Parameters & Options:

| Parameter / Flag | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `-c`, `--config PATH` | Option | `leai.yml` | Path to `leai.yml`. |

### What `doctor` validates:
* **Connectivity:** Establishes connection to Oracle Database listener and checks version from `v$version`.
* **Catalog Privileges:** Validates read access on `ALL_TABLES`, `ALL_TAB_COLUMNS`, `ALL_CONSTRAINTS`, `ALL_SOURCE`, and `ALL_SYNONYMS`.
* **Pipeline Directories:** Verifies existence and write permissions for `rawPath`, `annotationsPath`, `docPath`, and `updates_log_path`.
* **S3 Storage:** Tests SeaweedFS S3 connectivity and bucket when configured, providing troubleshooting tips on failure.
* **AI Models:** Checks active AI provider credentials and verifies the model is ready.
* **GitOps:** Validates active branch and remote Git synchronization status.

> [!TIP]
> Diagnostics can also be run directly inside the interactive copilot session (`leai chat`) by typing `/doctor`.

---

## 3. `leai changes`

Audits and lists recently created or altered database objects using Oracle's `LAST_DDL_TIME` timestamp.

```bash
leai changes --days 15
leai changes --days 30 -u HR
```

### Parameters and Flags:

| Parameter / Flag | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `-d`, `--days INT` | Option | `7` | Number of trailing days to audit. |
| `-u`, `--user TEXT` | Option | `None` | Filters by specific modifying user or schema. |
| `-c`, `--config PATH` | Option | `leai.yml` | Path to `leai.yml`. |
| `--seaweed` | Flag | `False` | Audits snapshots stored in remote S3 bucket. |
| `--no-cache` | Flag | `False` | Avoids writing snapshots to local disk. |
