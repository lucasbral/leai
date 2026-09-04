from __future__ import annotations

import hashlib
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

import yaml

from leai.config import SeaweedFSConfig
from leai.models import ObjectAnnotation, SchemaMetadata
from leai.raw import _construct_schema_metadata

logger = logging.getLogger(__name__)


class StorageError(Exception):
    """Base exception for SeaweedFS / Storage operations."""

    pass


class SaveResult(list):
    """Result of saving a raw schema to SeaweedFS, inheriting from list for backwards compatibility."""

    def __init__(self, keys: list[str], uploaded: int = 0, skipped: int = 0, total: int = 0):
        super().__init__(keys)
        self.uploaded = uploaded
        self.skipped = skipped
        self.total = total

    def __repr__(self) -> str:
        return f"<SaveResult uploaded={self.uploaded} skipped={self.skipped} total={self.total} keys={len(self)}>"


class SeaweedFSStorage:
    """Manages raw schemas and annotations stored in a SeaweedFS S3-compatible bucket."""

    def __init__(self, config: SeaweedFSConfig):
        self.config = config
        self._s3_client = None

    @property
    def client(self):
        if self._s3_client is None:
            try:
                import boto3
                from botocore.config import Config
            except ImportError as err:
                raise StorageError(
                    "boto3 is required for SeaweedFS integration. Install it via 'pip install boto3' or 'uv add boto3'."
                ) from err

            endpoint = self.config.endpoint_url.strip() if self.config.endpoint_url else None
            if not endpoint:
                raise StorageError("SeaweedFS endpoint_url must be provided in configuration (e.g. https://s3-sad.pe.gov.br).")

            if not endpoint.startswith(("http://", "https://")):
                endpoint = f"https://{endpoint}"

            client_kwargs: dict[str, Any] = {
                "service_name": "s3",
                "endpoint_url": endpoint,
                "region_name": self.config.region_name or "us-east-1",
                "config": Config(
                    signature_version="s3v4",
                    s3={"addressing_style": "path"},
                    retries={"max_attempts": 3, "mode": "standard"},
                    connect_timeout=10,
                    read_timeout=30,
                ),
            }

            if self.config.access_key and self.config.secret_key:
                client_kwargs["aws_access_key_id"] = self.config.access_key
                client_kwargs["aws_secret_access_key"] = self.config.secret_key

            self._s3_client = boto3.client(**client_kwargs)
        return self._s3_client

    def ensure_bucket_exists(self) -> None:
        """Verifies if the configured bucket exists, and creates it if auto_create_bucket is True."""
        bucket = self.config.bucket
        try:
            self.client.head_bucket(Bucket=bucket)
        except Exception:
            if self.config.auto_create_bucket:
                try:
                    self.client.create_bucket(Bucket=bucket)
                except Exception as exc:
                    raise StorageError(f"Failed to automatically create SeaweedFS bucket '{bucket}': {exc}") from exc
            else:
                raise StorageError(f"Bucket '{bucket}' does not exist on SeaweedFS and auto_create_bucket is disabled.")

    def test_connection(self) -> dict[str, Any]:
        """Tests the connection to SeaweedFS and returns status information."""
        try:
            self.ensure_bucket_exists()
            response = self.client.list_objects_v2(Bucket=self.config.bucket, MaxKeys=5)
            key_count = response.get("KeyCount", 0)
            return {
                "success": True,
                "endpoint": self.config.endpoint_url,
                "bucket": self.config.bucket,
                "objects_found": key_count,
                "message": "Connection to SeaweedFS S3 is operational.",
            }
        except Exception as exc:
            return {
                "success": False,
                "endpoint": self.config.endpoint_url,
                "bucket": self.config.bucket,
                "error": str(exc),
                "message": f"Connection failed: {exc}",
            }

    # -------------------------------------------------------------------------
    # RAW METADATA MANAGEMENT & INCREMENTAL VERSIONING
    # -------------------------------------------------------------------------

    @staticmethod
    def _compute_canonical_hash(data: dict) -> tuple[str, str]:
        """Returns canonical formatted JSON content and its SHA-256 hex digest."""
        canonical = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return canonical, digest

    def load_manifest(self, schema_name: str, multi_schema: bool = True) -> dict[str, str]:
        """Loads existing object hashes from {schema_path}/_manifest.json in SeaweedFS.
        Returns a mapping of relative object paths (e.g. 'tables/USERS.json') to their SHA-256 hashes."""
        self.ensure_bucket_exists()
        bucket = self.config.bucket
        prefix = self.config.raw_prefix.strip("/")
        schema_path = f"{prefix}/{schema_name}" if (multi_schema and schema_name) else prefix
        manifest_key = f"{schema_path}/_manifest.json"

        try:
            resp = self.client.get_object(Bucket=bucket, Key=manifest_key)
            raw_data = json.loads(resp["Body"].read().decode("utf-8"))
            if isinstance(raw_data, dict):
                hashes = raw_data.get("hashes", raw_data)
                if isinstance(hashes, dict):
                    return hashes
            return {}
        except Exception:
            return {}

    def save_manifest(self, schema_name: str, hashes: dict[str, str], multi_schema: bool = True) -> str:
        """Saves updated object hashes manifest to {schema_path}/_manifest.json in SeaweedFS."""
        from datetime import datetime, timezone

        self.ensure_bucket_exists()
        bucket = self.config.bucket
        prefix = self.config.raw_prefix.strip("/")
        schema_path = f"{prefix}/{schema_name}" if (multi_schema and schema_name) else prefix
        manifest_key = f"{schema_path}/_manifest.json"

        manifest_body = {
            "version": 1,
            "schema_name": schema_name,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "hashes": hashes,
        }
        self.client.put_object(
            Bucket=bucket,
            Key=manifest_key,
            Body=json.dumps(manifest_body, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8"),
            ContentType="application/json",
        )
        return manifest_key

    def save_raw_schema(
        self,
        schema: SchemaMetadata,
        multi_schema: bool = True,
        max_workers: int = 8,
        force: bool = False,
    ) -> SaveResult:
        """Uploads granular JSON objects and consolidated snapshot to SeaweedFS.
        When incremental=True and force=False, skips objects whose SHA-256 content
        hash matches the existing remote manifest, preventing redundant S3 versions."""
        self.ensure_bucket_exists()
        bucket = self.config.bucket
        prefix = self.config.raw_prefix.strip("/")
        schema_name = schema.schema_name or ""
        schema_path = f"{prefix}/{schema_name}" if (multi_schema and schema_name) else prefix

        is_incremental = self.config.incremental and not force
        existing_manifest = self.load_manifest(schema_name, multi_schema=multi_schema) if is_incremental else {}
        new_manifest: dict[str, str] = dict(existing_manifest)

        candidate_items: list[tuple[str, dict]] = []

        def _add_candidate(category: str, name: str, data: dict):
            rel_key = f"{category}/{name}.json"
            candidate_items.append((rel_key, data))

        for table in schema.tables:
            _add_candidate("tables", table.name, table.model_dump())
        for view in schema.views:
            _add_candidate("views", view.name, view.model_dump())
        for mview in schema.mviews:
            _add_candidate("mviews", mview.name, mview.model_dump())
        for code_obj in schema.code_objects:
            folder = code_obj.object_type.lower().replace(" ", "_") + "s"
            _add_candidate(folder, code_obj.name, code_obj.model_dump())
        for trigger in schema.triggers:
            _add_candidate("triggers", trigger.name, trigger.model_dump())
        for sequence in schema.sequences:
            _add_candidate("sequences", sequence.name, sequence.model_dump())
        for index in schema.indexes:
            _add_candidate("indexes", index.name, index.model_dump())
        for synonym in schema.synonyms:
            _add_candidate("synonyms", synonym.name, synonym.model_dump())

        total_objects = len(candidate_items)
        tasks_to_upload: list[tuple[str, str]] = []  # (s3_full_key, canonical_body)
        skipped_count = 0

        for rel_key, data in candidate_items:
            canonical_body, content_hash = self._compute_canonical_hash(data)
            full_key = f"{schema_path}/{rel_key}"

            if is_incremental and existing_manifest.get(rel_key) == content_hash:
                skipped_count += 1
            else:
                tasks_to_upload.append((full_key, canonical_body))
                new_manifest[rel_key] = content_hash

        uploaded_keys: list[str] = []

        def _upload_item(item: tuple[str, str]) -> str:
            key, body = item
            self.client.put_object(
                Bucket=bucket,
                Key=key,
                Body=body.encode("utf-8"),
                ContentType="application/json",
            )
            return key

        if tasks_to_upload:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(_upload_item, t) for t in tasks_to_upload]
                for f in as_completed(futures):
                    uploaded_keys.append(f.result())

        # If any object changed or force or first run with changes, update _schema.json snapshot and _manifest.json
        if tasks_to_upload or not existing_manifest or force:
            snapshot_key = f"{schema_path}/_schema.json"
            snapshot_body, _ = self._compute_canonical_hash(schema.model_dump())
            _upload_item((snapshot_key, snapshot_body))
            uploaded_keys.append(snapshot_key)

            if is_incremental:
                manifest_key = self.save_manifest(schema_name, new_manifest, multi_schema=multi_schema)
                uploaded_keys.append(manifest_key)

        result = SaveResult(
            keys=uploaded_keys,
            uploaded=len(tasks_to_upload),
            skipped=skipped_count,
            total=total_objects,
        )
        self.last_save_result = result
        return result

    def load_raw_schemas(self, target_schemas: list[str] | None = None) -> dict[str, SchemaMetadata]:
        """Loads schema metadata snapshots from SeaweedFS S3."""
        self.ensure_bucket_exists()
        bucket = self.config.bucket
        raw_prefix = self.config.raw_prefix.strip("/")
        prefix = f"{raw_prefix}/" if raw_prefix else ""

        # Identify schema directories in S3
        paginator = self.client.get_paginator("list_objects_v2")
        detected_schemas: set[str] = set()

        for page in paginator.paginate(Bucket=bucket, Prefix=prefix, Delimiter="/"):
            common_prefixes = page.get("CommonPrefixes", [])
            for cp in common_prefixes:
                # e.g., 'raw/ERGON/' -> 'ERGON'
                sub = cp.get("Prefix", "").removeprefix(prefix).strip("/")
                if sub and not sub.startswith("_"):
                    detected_schemas.add(sub)

        # If target_schemas specified, filter
        if target_schemas:
            target_upper = {s.upper() for s in target_schemas}
            detected_schemas = {s for s in detected_schemas if s.upper() in target_upper}

        results: dict[str, SchemaMetadata] = {}

        # If no schema subfolders found, check if root raw_prefix itself has _schema.json
        if not detected_schemas:
            root_snapshot = f"{raw_prefix}/_schema.json" if raw_prefix else "_schema.json"
            try:
                resp = self.client.get_object(Bucket=bucket, Key=root_snapshot)
                content = resp["Body"].read().decode("utf-8")
                data = json.loads(content)
                meta = _construct_schema_metadata(data, schema_name=data.get("schema_name", "DEFAULT"))
                return {meta.schema_name: meta}
            except Exception:
                return {}

        for schema_name in sorted(detected_schemas):
            snapshot_key = f"{prefix}{schema_name}/_schema.json"
            try:
                resp = self.client.get_object(Bucket=bucket, Key=snapshot_key)
                content = resp["Body"].read().decode("utf-8")
                data = json.loads(content)
                meta = _construct_schema_metadata(data, schema_name=schema_name)
                results[schema_name] = meta
            except Exception as exc:
                logger.warning(f"Could not load snapshot '{snapshot_key}' from SeaweedFS: {exc}")

        return results

    # -------------------------------------------------------------------------
    # ANNOTATIONS MANAGEMENT
    # -------------------------------------------------------------------------

    def save_annotation(self, schema_name: str, obj_folder: str, obj_name: str, annotation: ObjectAnnotation) -> str:
        """Saves a single annotation YAML to SeaweedFS S3."""
        self.ensure_bucket_exists()
        bucket = self.config.bucket
        prefix = self.config.annotations_prefix.strip("/")
        key = f"{prefix}/{schema_name}/{obj_folder}/{obj_name}.yml" if prefix else f"{schema_name}/{obj_folder}/{obj_name}.yml"

        data = annotation.model_dump(exclude_defaults=False, exclude_none=False)
        clean_data = {
            "description": data.get("description") or "",
            "tags": data.get("tags") or [],
            "business_rules": data.get("business_rules") or [],
            "use_cases": data.get("use_cases") or [],
            "related_objects": data.get("related_objects") or [],
            "warnings": data.get("warnings") or [],
            "columns": data.get("columns") or {},
        }
        yaml_content = yaml.safe_dump(clean_data, sort_keys=False, allow_unicode=True)

        self.client.put_object(
            Bucket=bucket,
            Key=key,
            Body=yaml_content.encode("utf-8"),
            ContentType="text/yaml",
        )
        return key

    def load_annotation(self, schema_name: str, obj_folder: str, obj_name: str) -> ObjectAnnotation:
        """Loads an annotation YAML from SeaweedFS S3."""
        self.ensure_bucket_exists()
        bucket = self.config.bucket
        prefix = self.config.annotations_prefix.strip("/")
        key = f"{prefix}/{schema_name}/{obj_folder}/{obj_name}.yml" if prefix else f"{schema_name}/{obj_folder}/{obj_name}.yml"

        try:
            resp = self.client.get_object(Bucket=bucket, Key=key)
            content = resp["Body"].read().decode("utf-8")
            raw = yaml.safe_load(content)
            if isinstance(raw, dict):
                return ObjectAnnotation.model_validate(raw)
        except Exception:
            pass
        return ObjectAnnotation()

    # -------------------------------------------------------------------------
    # SYNCHRONIZATION (LOCAL <-> REMOTE)
    # -------------------------------------------------------------------------

    def push_local_to_remote(
        self,
        local_raw_path: Path,
        local_annotations_path: Path,
        callback: Callable[[str, str], None] | None = None,
    ) -> dict[str, int]:
        """Uploads local raw and annotations directories to SeaweedFS S3."""
        self.ensure_bucket_exists()
        bucket = self.config.bucket
        counts = {"raw": 0, "annotations": 0}

        # 1. Push RAW
        if local_raw_path.exists():
            raw_prefix = self.config.raw_prefix.strip("/")
            for file_path in local_raw_path.rglob("*.json"):
                rel = file_path.relative_to(local_raw_path).as_posix()
                key = f"{raw_prefix}/{rel}" if raw_prefix else rel
                self.client.upload_file(str(file_path), bucket, key)
                counts["raw"] += 1
                if callback:
                    callback("raw", rel)

        # 2. Push ANNOTATIONS
        if local_annotations_path.exists():
            ann_prefix = self.config.annotations_prefix.strip("/")
            for file_path in local_annotations_path.rglob("*.yml"):
                rel = file_path.relative_to(local_annotations_path).as_posix()
                key = f"{ann_prefix}/{rel}" if ann_prefix else rel
                self.client.upload_file(str(file_path), bucket, key)
                counts["annotations"] += 1
                if callback:
                    callback("annotations", rel)

        return counts

    def pull_remote_to_local(
        self,
        local_raw_path: Path,
        local_annotations_path: Path,
        callback: Callable[[str, str], None] | None = None,
    ) -> dict[str, int]:
        """Downloads all raw and annotations objects from SeaweedFS S3 to local directories."""
        self.ensure_bucket_exists()
        bucket = self.config.bucket
        counts = {"raw": 0, "annotations": 0}
        paginator = self.client.get_paginator("list_objects_v2")

        # 1. Pull RAW
        raw_prefix = self.config.raw_prefix.strip("/")
        pfx_raw = f"{raw_prefix}/" if raw_prefix else ""
        for page in paginator.paginate(Bucket=bucket, Prefix=pfx_raw):
            for item in page.get("Contents", []):
                key = item["Key"]
                rel = key.removeprefix(pfx_raw)
                dest = local_raw_path / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                self.client.download_file(bucket, key, str(dest))
                counts["raw"] += 1
                if callback:
                    callback("raw", rel)

        # 2. Pull ANNOTATIONS
        ann_prefix = self.config.annotations_prefix.strip("/")
        pfx_ann = f"{ann_prefix}/" if ann_prefix else ""
        for page in paginator.paginate(Bucket=bucket, Prefix=pfx_ann):
            for item in page.get("Contents", []):
                key = item["Key"]
                rel = key.removeprefix(pfx_ann)
                dest = local_annotations_path / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                self.client.download_file(bucket, key, str(dest))
                counts["annotations"] += 1
                if callback:
                    callback("annotations", rel)

        return counts
