# Utilities, Diagnostics & Governance

This section covers commands for environment health diagnostics, repository initialization, and database schema change auditing.

---

## 1. `leai init`

Initializes a workspace directory by generating a starter `leai.yml` configuration template.

```bash
leai init
# Generate fully commented reference template:
leai init --example
```

### Parameters and Flags:

| Parameter / Flag | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `-f`, `--force` | Flag | `False` | Overwrites existing `leai.yml` without prompt. |
| `-e`, `--example` | Flag | `False` | Generates fully commented `leai.example.yml`. |
| `-c`, `--config PATH` | Option | `leai.yml` | Target configuration path. |

---

## 2. `leai doctor` (or `leai check`)

Runs automated pre-flight diagnostics to ensure your environment is fully operational for LEAI.

```bash
leai doctor
```

### Parameters and Flags:

| Parameter / Flag | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `-c`, `--config PATH` | Option | `leai.yml` | Path to `leai.yml`. |

### What `doctor` checks:
* **Network Connectivity:** Validates TCP and database listener connectivity to the configured Oracle host and port.
* **Catalog Permissions:** Tests read access across Oracle system views: `ALL_TABLES`, `ALL_TAB_COLUMNS`, `ALL_CONSTRAINTS`, `ALL_SOURCE`, and `ALL_SYNONYMS`.
* **Workspace Permissions:** Checks read and write access for `rawPath`, `annotationsPath`, and `docPath`.
* **S3 Object Storage:** Verifies connection and bucket health for SeaweedFS if enabled.
* **AI API Keys:** Verifies the availability and readiness of configured LLM credentials.

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
