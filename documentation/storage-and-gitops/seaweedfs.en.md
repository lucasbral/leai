# SeaweedFS & S3 Object Storage (`leai seaweed`)

LEAI provides enterprise-grade support for persisting and sharing database metadata across teams using **AWS S3-compatible Object Storage**, with first-class optimization for **SeaweedFS**.

This enables software engineering and data teams to share unified metadata catalogs without requiring developers to maintain direct connection credentials to production Oracle databases.

---

## 🏗️ Distributed Storage Topology

```mermaid
flowchart TD
    subgraph Local [Developer Machine / CI-CD Pipeline]
        CLI[LEAI CLI]
    end

    subgraph Remote [SeaweedFS / MinIO / AWS S3]
        BUCKET[(S3 Bucket: leai)]
        RAW_REMOTE[raw/*.json]
        ANN_REMOTE[annotations/*.yml]
        BUCKET --> RAW_REMOTE & ANN_REMOTE
    end

    CLI -->|leai seaweed push| BUCKET
    BUCKET -->|leai seaweed pull| CLI
    CLI <-->|leai seaweed sync<br/>(SHA-256 Deduplication)| BUCKET
```

### Key Highlights:
* **Zero-Cache Remote Mode (`no_cache: true` / `--no-cache`):** Run LEAI completely in memory or streaming directly from S3 without saving snapshots to local disk.
* **SHA-256 Incremental Deduplication:** Only objects with altered hash footprints are transmitted across the wire.
* **Secure Collaboration:** Team members can query schemas, run `leai ask`, and inspect lineage locally without accessing the production database listener.

---

## ⚡ Seaweed Group Commands

### 1. `leai seaweed status`
Tests TCP connectivity to the S3 gateway, validates credentials, and reports snapshot tallies in the remote bucket.

```bash
leai seaweed status
```

---

### 2. `leai seaweed push`
Uploads local technical snapshots (`raw/`) and business annotations (`annotations/`) into the remote S3 bucket.

```bash
leai seaweed push
```

---

### 3. `leai seaweed pull`
Downloads the latest snapshots and annotations from the remote S3 bucket into local directories.

```bash
leai seaweed pull
```

---

### 4. `leai seaweed sync`
Executes an intelligent bi-directional sync: computes SHA-256 hashes for all entities and synchronizes only differing files.

```bash
leai seaweed sync
```

---

## 🚩 Global Seaweed Flags on Standard Commands

You can interact with remote S3 storage directly during regular CLI operations using these flags:

* `--seaweed`: Activates remote object storage for the command invocation.
* `--no-cache`: Operates in pure remote mode without touching local disk paths.
* `--force-upload`: Forces re-upload of all entities to the bucket, bypassing SHA-256 cache checks.

```bash
# Extract from Oracle and upload directly to S3
leai extract --seaweed

# Trace lineage directly from S3 without local files
leai trace BILLING_TB --seaweed --no-cache
```

---

## 🌐 Real-Time Synchronization in Web Studio (`leai serve`)

When SeaweedFS storage is enabled in `leai.yml`, the **LEAI Web Studio** (`leai serve` or `/serve`) integrates seamlessly with Object Storage:

* **Direct S3 Write-Through on Save:** When editing table descriptions, business rules, or column notes in the web UI, the `POST /api/annotations` endpoint persists the changes locally and immediately uploads the updated YAML to the remote S3 bucket under the `annotations/` prefix.
* **Automatic Remote Fallback on Read:** When viewing an object via `GET /api/object`, if the YAML annotation does not yet exist on local disk, Web Studio dynamically downloads it from SeaweedFS and hydrates the local cache transparently.
* **Visual Status Indicators:** The Web Studio header displays a connection badge (`☁️ S3: <bucket>`), and toast notifications confirm successful uploads to the remote storage.

---

## 💬 Interactive Copilot Commands (`/annotate`, `/update`, `/rule`)

Within an interactive copilot session (`leai chat`):

* **/update [hours|days] [--seaweed|-W] [--compile|-C]:** Incrementally extracts recently modified objects from Oracle, updates annotations, merges consolidated catalog schemas, syncs `glossary.yml`, and pushes deltas to SeaweedFS.
* **/annotate [--seaweed|-W] [--no-cache]:** Generates documentation stubs for all schema tables and views, synchronizes `glossary.yml`, and synchronously uploads them to SeaweedFS. With `--no-cache`, stubs are created in remote storage without local disk persistence.
* **/rule [list|add|del|find]:** Manages corporate glossary rules and synchronizes directly with the SeaweedFS bucket.
* **/doc &lt;OBJECT&gt;:** Opens the terminal TUI editor for rapid annotation. Changes are saved strictly to local disk (`annotations/`), enabling local review and diffing before pushing via `leai seaweed push` or Web Studio.

---

## 📖 Continuous Glossary Synchronization (`annotations/glossary.yml`)

LEAI treats the business glossary (`annotations/glossary.yml`) as an integral part of the centralized SeaweedFS knowledge base:

* **Real-time Persistence**: Every addition (`leai rule add` or `/rule add`) and deletion (`leai rule del` or `/rule del`) is synchronously uploaded to `annotations/glossary.yml` in the S3 bucket when storage is operational.
* **Smart Non-Destructive Merging**: During `leai update` or `leai annotate`, LEAI combines local terms with the remote bucket:
  * **Central Authority on Conflicts**: If a term is defined in both places with differing descriptions, the centralized SeaweedFS definition is prioritized to protect institutional domain rules against accidental overwrites.
  * **Metadata Union**: Tags, related tables, and code examples are deduplicated and merged together.
* **AI Tool Resilience**: In containerized or `--no-cache` setups, the glossary lookup tool (`lookup_business_term`) seamlessly queries the SeaweedFS bucket directly when local files are absent.

---

## 🧹 S3 Lifecycle Rules for `annotations/`

In AWS S3 and SeaweedFS, bucket versioning is enabled at the **bucket level**. It cannot be turned off for an individual subfolder or prefix.

Because business annotations in `annotations/*.yml` undergo frequent edits through the Web Studio or terminal editor, keeping dozens of historical non-current versions can consume unnecessary storage in SeaweedFS — especially when the definitive version history is already tracked through Git (`leai git`).

### How to Configure Automatic Version Purging in SeaweedFS

The recommended S3-native approach is to apply a **Lifecycle Configuration** using the `NoncurrentVersionExpiration` rule scoped to the `annotations/` prefix. This instructs SeaweedFS to automatically delete older non-current versions after a defined number of days (e.g., 1 day).

#### 1. Create the `lifecycle-annotations.json` policy file:

```json
{
  "Rules": [
    {
      "ID": "PurgeOldAnnotationVersions",
      "Status": "Enabled",
      "Filter": {
        "Prefix": "annotations/"
      },
      "NoncurrentVersionExpiration": {
        "NoncurrentDays": 1
      }
    }
  ]
}
```

#### 2. Apply the lifecycle rule via AWS CLI:

```bash
aws s3api put-bucket-lifecycle-configuration \
  --endpoint-url http://storage.internal:8333 \
  --bucket leai-metadata \
  --lifecycle-configuration file://lifecycle-annotations.json
```

#### 3. Verify active lifecycle rules:

```bash
aws s3api get-bucket-lifecycle-configuration \
  --endpoint-url http://storage.internal:8333 \
  --bucket leai-metadata
```

With this policy active, SeaweedFS retains the latest active annotation version for Web Studio and terminal access, while purging superseded historical versions automatically.

---

## ⚙️ Configuration in `leai.yml`

```yaml
storage:
  seaweedfs:
    enabled: true                                  # Automatically routes operations to S3
    endpoint_url: "http://storage.internal:8333"  # S3 gateway endpoint
    bucket: "leai-metadata"                        # Bucket name
    access_key: "${SEAWEEDFS_ACCESS_KEY}"
    secret_key: "${SEAWEEDFS_SECRET_KEY}"
    region_name: "us-east-1"
    raw_prefix: "raw"                              # Folder prefix for JSON snapshots
    annotations_prefix: "annotations"              # Folder prefix for YAML annotations
    auto_create_bucket: true                       # Creates bucket if missing
    no_cache: false                                # Local disk cache or pure remote
    incremental: true                              # SHA-256 hash deduplication
```
