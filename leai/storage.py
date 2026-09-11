from __future__ import annotations

import hashlib
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

import yaml

from leai.config import SeaweedFSConfig
from leai.models import BusinessGlossary, ObjectAnnotation, SchemaMetadata
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
        self._cached_annotations_indexes: dict[str, dict[str, Any]] = {}

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
        is_delta: bool = False,
        progress_callback: Any = None,
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
                for idx, f in enumerate(as_completed(futures), 1):
                    uploaded_keys.append(f.result())
                    if progress_callback:
                        progress_callback(idx, len(tasks_to_upload))

        # If any object changed or force or first run with changes, update _schema.json snapshot and _manifest.json
        if tasks_to_upload or not existing_manifest or force:
            snapshot_key = f"{schema_path}/_schema.json"
            if is_delta:
                try:
                    resp = self.client.get_object(Bucket=bucket, Key=snapshot_key)
                    existing_data = json.loads(resp["Body"].read().decode("utf-8"))
                    base_meta = _construct_schema_metadata(existing_data, schema_name=schema_name)
                    from leai.raw import merge_schema_metadata

                    full_schema = merge_schema_metadata(base_meta, schema)
                    snapshot_body, _ = self._compute_canonical_hash(full_schema.model_dump())
                except Exception:
                    snapshot_body, _ = self._compute_canonical_hash(schema.model_dump())
            else:
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

        def _fetch_schema(schema_name: str) -> tuple[str, SchemaMetadata | None]:
            snapshot_key = f"{prefix}{schema_name}/_schema.json"
            try:
                resp = self.client.get_object(Bucket=bucket, Key=snapshot_key)
                content = resp["Body"].read().decode("utf-8")
                data = json.loads(content)
                meta = _construct_schema_metadata(data, schema_name=schema_name)
                return schema_name, meta
            except Exception as exc:
                logger.warning(f"Could not load snapshot '{snapshot_key}' from SeaweedFS: {exc}")
                return schema_name, None

        schemas_to_load = sorted(detected_schemas)
        max_workers = min(12, max(2, len(schemas_to_load))) if schemas_to_load else 1
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(_fetch_schema, s_name) for s_name in schemas_to_load]
            for f in as_completed(futures):
                s_name, meta = f.result()
                if meta:
                    results[s_name] = meta

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

        # Update cache in memory if populated
        if hasattr(self, "_cached_annotated_objects") and self._cached_annotated_objects is not None:
            self._cached_annotated_objects.add((schema_name.upper(), obj_folder.lower(), obj_name.upper()))
            self._cached_annotated_objects.add(("", obj_folder.lower(), obj_name.upper()))

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

    def list_annotated_objects(self, force_refresh: bool = False) -> set[tuple[str, str, str]]:
        """Lists all annotated objects from SeaweedFS S3 with local in-memory caching.

        Returns a set of (schema_name, obj_folder, obj_name) in uppercase/normalized format.
        """
        if not force_refresh and hasattr(self, "_cached_annotated_objects") and self._cached_annotated_objects is not None:
            return self._cached_annotated_objects

        self.ensure_bucket_exists()
        bucket = self.config.bucket
        prefix = self.config.annotations_prefix.strip("/")
        pfx = f"{prefix}/" if prefix else ""

        paginator = self.client.get_paginator("list_objects_v2")
        annotated: set[tuple[str, str, str]] = set()

        try:
            for page in paginator.paginate(Bucket=bucket, Prefix=pfx):
                for item in page.get("Contents", []):
                    key = item.get("Key", "")
                    rel = key.removeprefix(pfx).strip("/")
                    # Ignore glossary and other special files
                    if rel.lower().endswith("glossary.yml") or rel.lower().endswith("glossary.yaml"):
                        continue
                    if not rel.lower().endswith((".yml", ".yaml")):
                        continue

                    parts = rel.split("/")
                    if len(parts) >= 3:
                        # schema_name / obj_folder / obj_name.yml
                        s_name = parts[0].upper()
                        folder = parts[1].lower()
                        obj_name = parts[2].rsplit(".", 1)[0].upper()
                        annotated.add((s_name, folder, obj_name))
                        annotated.add(("", folder, obj_name))
                    elif len(parts) == 2:
                        # obj_folder / obj_name.yml
                        folder = parts[0].lower()
                        obj_name = parts[1].rsplit(".", 1)[0].upper()
                        annotated.add(("", folder, obj_name))
        except Exception as exc:
            logger.warning(f"Failed to list annotated objects from SeaweedFS: {exc}")

        self._cached_annotated_objects = annotated
        return annotated

    # -------------------------------------------------------------------------
    # ANNOTATIONS INDEX MANAGEMENT
    # -------------------------------------------------------------------------

    def get_annotations_index_key(self, schema_name: str = "") -> str:
        """Returns the SeaweedFS S3 object key for annotations_index.json."""
        prefix = self.config.annotations_prefix.strip("/")
        s_name = schema_name.upper() if schema_name else ""
        if prefix and s_name:
            return f"{prefix}/{s_name}/annotations_index.json"
        elif prefix:
            return f"{prefix}/annotations_index.json"
        elif s_name:
            return f"{s_name}/annotations_index.json"
        return "annotations_index.json"

    def load_annotations_index(self, schema_name: str = "", force_refresh: bool = False) -> dict[str, Any]:
        """Loads the annotations_index.json from SeaweedFS S3 with local in-memory caching."""
        s_name = schema_name.upper() if schema_name else ""
        if not force_refresh and hasattr(self, "_cached_annotations_indexes") and s_name in self._cached_annotations_indexes:
            return self._cached_annotations_indexes[s_name]

        if not hasattr(self, "_cached_annotations_indexes"):
            self._cached_annotations_indexes = {}

        self.ensure_bucket_exists()
        bucket = self.config.bucket
        key = self.get_annotations_index_key(schema_name)
        try:
            resp = self.client.get_object(Bucket=bucket, Key=key)
            content = resp["Body"].read().decode("utf-8")
            data = json.loads(content)
            if isinstance(data, dict):
                self._cached_annotations_indexes[s_name] = data
                return data
        except Exception:
            pass

        default_index: dict[str, Any] = {
            "schema": s_name,
            "enriched_count": 0,
            "objects": {},
        }
        self._cached_annotations_indexes[s_name] = default_index
        return default_index

    def save_annotations_index(self, schema_name: str = "", index_data: dict[str, Any] | None = None) -> str:
        """Saves the annotations_index.json to SeaweedFS S3."""
        self.ensure_bucket_exists()
        bucket = self.config.bucket
        key = self.get_annotations_index_key(schema_name)
        s_name = schema_name.upper() if schema_name else ""

        if index_data is None:
            index_data = self.load_annotations_index(schema_name)

        objs = index_data.get("objects", {})
        total_count = sum(len(items) for items in objs.values() if isinstance(items, dict))
        index_data["enriched_count"] = total_count

        body = json.dumps(index_data, indent=2, ensure_ascii=False)
        self.client.put_object(
            Bucket=bucket,
            Key=key,
            Body=body.encode("utf-8"),
            ContentType="application/json",
        )
        if not hasattr(self, "_cached_annotations_indexes"):
            self._cached_annotations_indexes = {}
        self._cached_annotations_indexes[s_name] = index_data
        return key

    def update_object_in_index(
        self,
        schema_name: str,
        obj_folder: str,
        obj_name: str,
        annotation: ObjectAnnotation,
        db_comment: str | None = None,
    ) -> None:
        """Updates an individual object in annotations_index.json based on whether it is enriched."""
        from leai.annotations import is_annotation_enriched

        folder = obj_folder.lower()
        name = obj_name.upper()

        index_data = self.load_annotations_index(schema_name)
        objects = index_data.setdefault("objects", {})
        folder_dict = objects.setdefault(folder, {})

        if is_annotation_enriched(annotation, db_comment=db_comment):
            clean_entry: dict[str, Any] = {}
            if annotation.description and annotation.description.strip():
                clean_entry["description"] = annotation.description.strip()
            if annotation.tags:
                clean_entry["tags"] = annotation.tags
            if annotation.business_rules:
                clean_entry["business_rules"] = annotation.business_rules
            if annotation.use_cases:
                clean_entry["use_cases"] = annotation.use_cases
            if annotation.warnings:
                clean_entry["warnings"] = annotation.warnings
            if annotation.related_objects:
                clean_entry["related_objects"] = annotation.related_objects
            clean_cols = {col: comm for col, comm in annotation.columns.items() if comm and comm.strip()}
            if clean_cols:
                clean_entry["columns"] = clean_cols

            folder_dict[name] = clean_entry
        else:
            if name in folder_dict:
                del folder_dict[name]

        self.save_annotations_index(schema_name, index_data)

    def delete_annotation(self, schema_name: str, obj_folder: str, obj_name: str) -> bool:
        """Deletes an annotation YAML from SeaweedFS S3 and updates caches."""
        self.ensure_bucket_exists()
        bucket = self.config.bucket
        prefix = self.config.annotations_prefix.strip("/")
        key = f"{prefix}/{schema_name}/{obj_folder}/{obj_name}.yml" if prefix else f"{schema_name}/{obj_folder}/{obj_name}.yml"
        try:
            self.client.delete_object(Bucket=bucket, Key=key)
            s_name = schema_name.upper() if schema_name else ""
            folder = obj_folder.lower()
            name = obj_name.upper()
            if hasattr(self, "_cached_annotated_objects") and self._cached_annotated_objects is not None:
                self._cached_annotated_objects.discard((s_name, folder, name))
                self._cached_annotated_objects.discard(("", folder, name))
            index_data = self.load_annotations_index(schema_name)
            if name in index_data.get("objects", {}).get(folder, {}):
                del index_data["objects"][folder][name]
                self.save_annotations_index(schema_name, index_data)
            return True
        except Exception:
            return False

    # -------------------------------------------------------------------------
    # GLOSSARY MANAGEMENT
    # -------------------------------------------------------------------------

    def get_glossary_key(self) -> str:
        """Returns the SeaweedFS S3 object key for the business glossary."""
        prefix = self.config.annotations_prefix.strip("/")
        return f"{prefix}/glossary.yml" if prefix else "glossary.yml"

    def save_glossary(self, glossary: BusinessGlossary) -> str:
        """Saves the business glossary YAML to SeaweedFS S3."""
        from leai.glossary import dump_glossary_yaml

        self.ensure_bucket_exists()
        bucket = self.config.bucket
        key = self.get_glossary_key()
        body = dump_glossary_yaml(glossary)

        self.client.put_object(
            Bucket=bucket,
            Key=key,
            Body=body.encode("utf-8"),
            ContentType="text/yaml",
        )
        return key

    def load_glossary(self) -> BusinessGlossary:
        """Loads the business glossary YAML from SeaweedFS S3."""
        from leai.glossary import load_glossary as parse_glossary

        self.ensure_bucket_exists()
        bucket = self.config.bucket
        key = self.get_glossary_key()
        try:
            resp = self.client.get_object(Bucket=bucket, Key=key)
            content = resp["Body"].read().decode("utf-8")
            return parse_glossary(content=content)
        except Exception:
            return BusinessGlossary()

    def sync_glossary(
        self,
        local_annotations_path: Path | str | None,
        no_cache: bool = False,
    ) -> BusinessGlossary:
        """Synchronizes business glossary between SeaweedFS and local annotations directory.

        Loads remote and local versions, performs a non-destructive merge, saves the result
        to SeaweedFS, and writes back locally (unless no_cache=True).
        """
        from leai.glossary import load_glossary as parse_glossary
        from leai.glossary import merge_glossaries, save_glossary

        remote_glossary = self.load_glossary()
        local_glossary = parse_glossary(annotations_path=local_annotations_path) if local_annotations_path else BusinessGlossary()

        # Remote is base (preserves central definitions), local is delta
        merged = merge_glossaries(base=remote_glossary, delta=local_glossary)

        # Save to remote S3
        self.save_glossary(merged)

        # Save to local disk if caching is enabled
        if not no_cache and local_annotations_path:
            save_glossary(local_annotations_path, merged)

        return merged

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

    def save_update_log(
        self,
        manifest: dict[str, Any],
        markdown_content: str,
        timestamp_slug: str | None = None,
    ) -> dict[str, str]:
        """Saves update logs (JSON and Markdown) to SeaweedFS S3 under logs/updates/."""
        from datetime import datetime, timezone

        self.ensure_bucket_exists()
        bucket = self.config.bucket

        if not timestamp_slug:
            dt = datetime.now(timezone.utc)
            timestamp_slug = dt.strftime("%Y%m%d_%H%M%S")

        prefix = "logs/updates"
        json_key = f"{prefix}/update_{timestamp_slug}.json"
        md_key = f"{prefix}/update_{timestamp_slug}.md"
        latest_json_key = f"{prefix}/latest.json"
        latest_md_key = f"{prefix}/latest.md"

        json_bytes = json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8")
        md_bytes = markdown_content.encode("utf-8")

        # Upload timestamped files
        self.client.put_object(Bucket=bucket, Key=json_key, Body=json_bytes, ContentType="application/json")
        self.client.put_object(Bucket=bucket, Key=md_key, Body=md_bytes, ContentType="text/markdown; charset=utf-8")

        # Upload pointer files (latest)
        self.client.put_object(Bucket=bucket, Key=latest_json_key, Body=json_bytes, ContentType="application/json")
        self.client.put_object(Bucket=bucket, Key=latest_md_key, Body=md_bytes, ContentType="text/markdown; charset=utf-8")

        return {
            "json": json_key,
            "markdown": md_key,
            "latest_json": latest_json_key,
            "latest_markdown": latest_md_key,
        }

    def load_latest_update_log(self) -> dict[str, Any] | None:
        """Loads the most recent update manifest (latest.json) from SeaweedFS S3."""
        bucket = self.config.bucket
        key = "logs/updates/latest.json"
        try:
            resp = self.client.get_object(Bucket=bucket, Key=key)
            return json.loads(resp["Body"].read().decode("utf-8"))
        except Exception:
            return None
