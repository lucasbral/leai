from __future__ import annotations

import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from leai.cli import app
from leai.config import SeaweedFSConfig, load_config
from leai.models import ColumnMeta, ObjectAnnotation, SchemaMetadata, TableMeta
from leai.storage import SeaweedFSStorage, StorageError


class TestStorage(unittest.TestCase):
    def setUp(self) -> None:
        self.mock_s3_client = MagicMock()
        self.sample_schema = SchemaMetadata(
            schema_name="TEST_SCHEMA",
            tables=[
                TableMeta(
                    name="USERS",
                    comment="Users table",
                    columns=[
                        ColumnMeta(name="ID", data_type="NUMBER", nullable=False),
                        ColumnMeta(name="NAME", data_type="VARCHAR2(100)", nullable=True),
                    ],
                )
            ],
        )

    def test_seaweedfs_config_defaults(self) -> None:
        cfg = SeaweedFSConfig()
        self.assertFalse(cfg.enabled)
        self.assertEqual(cfg.endpoint_url, "")
        self.assertEqual(cfg.bucket, "leai")
        self.assertEqual(cfg.raw_prefix, "raw")
        self.assertEqual(cfg.annotations_prefix, "annotations")
        self.assertTrue(cfg.auto_create_bucket)

    def test_load_config_with_storage_and_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_file = Path(tmp_dir) / "leai.yml"
            config_file.write_text(
                """
schemas:
  - TEST_SCHEMA
storage:
  seaweedfs:
    enabled: false
    endpoint_url: "http://localhost:8333"
    bucket: "custom-bucket"
""",
                encoding="utf-8",
            )

            env_vars = {
                "LEAI_SEAWEED_ENABLED": "true",
                "LEAI_SEAWEED_ENDPOINT": "http://env-host:8333",
                "LEAI_SEAWEED_BUCKET": "env-bucket",
                "LEAI_SEAWEED_ACCESS_KEY": "env-access",
                "LEAI_SEAWEED_SECRET_KEY": "env-secret",
            }
            with patch.dict(os.environ, env_vars):
                loaded = load_config(config_file)
                self.assertTrue(loaded.storage.seaweedfs.enabled)
                self.assertEqual(loaded.storage.seaweedfs.endpoint_url, "http://env-host:8333")
                self.assertEqual(loaded.storage.seaweedfs.bucket, "env-bucket")
                self.assertEqual(loaded.storage.seaweedfs.access_key, "env-access")
                self.assertEqual(loaded.storage.seaweedfs.secret_key, "env-secret")

    def test_seaweedfs_storage_missing_endpoint(self) -> None:
        cfg = SeaweedFSConfig(endpoint_url="")
        storage = SeaweedFSStorage(cfg)
        with self.assertRaises(StorageError):
            _ = storage.client

    def test_seaweedfs_storage_ensure_bucket_exists(self) -> None:
        cfg = SeaweedFSConfig(endpoint_url="http://localhost:8333", bucket="leai-test", auto_create_bucket=True)
        storage = SeaweedFSStorage(cfg)
        storage._s3_client = self.mock_s3_client

        # Case 1: Bucket already exists
        storage.ensure_bucket_exists()
        self.mock_s3_client.head_bucket.assert_called_with(Bucket="leai-test")
        self.assertEqual(self.mock_s3_client.create_bucket.call_count, 0)

        # Case 2: Bucket does not exist -> create_bucket is called
        self.mock_s3_client.head_bucket.side_effect = Exception("NoSuchBucket")
        storage.ensure_bucket_exists()
        self.mock_s3_client.create_bucket.assert_called_with(Bucket="leai-test")

    def test_seaweedfs_storage_test_connection_success(self) -> None:
        cfg = SeaweedFSConfig(endpoint_url="http://localhost:8333", bucket="leai-test")
        storage = SeaweedFSStorage(cfg)
        storage._s3_client = self.mock_s3_client
        self.mock_s3_client.list_objects_v2.return_value = {"KeyCount": 42}

        res = storage.test_connection()
        self.assertTrue(res["success"])
        self.assertEqual(res["objects_found"], 42)
        self.assertIn("operational", res["message"].lower())

    def test_seaweedfs_storage_test_connection_failure(self) -> None:
        cfg = SeaweedFSConfig(endpoint_url="http://localhost:8333", bucket="leai-test")
        storage = SeaweedFSStorage(cfg)
        storage._s3_client = self.mock_s3_client
        self.mock_s3_client.head_bucket.side_effect = Exception("Connection refused")
        self.mock_s3_client.create_bucket.side_effect = Exception("Connection refused")

        res = storage.test_connection()
        self.assertFalse(res["success"])
        self.assertIn("connection failed", res["message"].lower())

    def test_save_raw_schema_to_seaweed(self) -> None:
        cfg = SeaweedFSConfig(endpoint_url="http://localhost:8333", bucket="leai-test", raw_prefix="raw")
        storage = SeaweedFSStorage(cfg)
        storage._s3_client = self.mock_s3_client

        uploaded = storage.save_raw_schema(self.sample_schema, multi_schema=True)

        self.assertIn("raw/TEST_SCHEMA/_schema.json", uploaded)
        self.assertIn("raw/TEST_SCHEMA/tables/USERS.json", uploaded)

        # Verify put_object calls
        put_keys = [call.kwargs["Key"] for call in self.mock_s3_client.put_object.call_args_list]
        self.assertIn("raw/TEST_SCHEMA/_schema.json", put_keys)
        self.assertIn("raw/TEST_SCHEMA/tables/USERS.json", put_keys)

    def test_load_raw_schemas_from_seaweed(self) -> None:
        cfg = SeaweedFSConfig(endpoint_url="http://localhost:8333", bucket="leai-test", raw_prefix="raw")
        storage = SeaweedFSStorage(cfg)
        storage._s3_client = self.mock_s3_client

        # Mock list_objects_v2 paginator
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [{"CommonPrefixes": [{"Prefix": "raw/TEST_SCHEMA/"}]}]
        self.mock_s3_client.get_paginator.return_value = mock_paginator

        # Mock get_object for _schema.json
        schema_json = json.dumps(self.sample_schema.model_dump())
        mock_body = MagicMock()
        mock_body.read.return_value = schema_json.encode("utf-8")
        self.mock_s3_client.get_object.return_value = {"Body": mock_body}

        loaded = storage.load_raw_schemas()
        self.assertIn("TEST_SCHEMA", loaded)
        meta = loaded["TEST_SCHEMA"]
        self.assertEqual(meta.schema_name, "TEST_SCHEMA")
        self.assertEqual(len(meta.tables), 1)
        self.assertEqual(meta.tables[0].name, "USERS")

    def test_save_and_load_annotation_seaweed(self) -> None:
        cfg = SeaweedFSConfig(endpoint_url="http://localhost:8333", bucket="leai-test", annotations_prefix="annotations")
        storage = SeaweedFSStorage(cfg)
        storage._s3_client = self.mock_s3_client

        ann = ObjectAnnotation(
            description="Users business entity",
            business_rules=["Only active users can authenticate"],
            columns={"ID": "Primary user ID"},
        )

        key = storage.save_annotation("TEST_SCHEMA", "tables", "USERS", ann)
        self.assertEqual(key, "annotations/TEST_SCHEMA/tables/USERS.yml")

        # Mock loading back
        yaml_content = b"""
description: "Users business entity"
tags: []
business_rules:
  - "Only active users can authenticate"
use_cases: []
related_objects: []
warnings: []
columns:
  ID: "Primary user ID"
"""
        mock_body = MagicMock()
        mock_body.read.return_value = yaml_content
        self.mock_s3_client.get_object.return_value = {"Body": mock_body}

        loaded_ann = storage.load_annotation("TEST_SCHEMA", "tables", "USERS")
        self.assertEqual(loaded_ann.description, "Users business entity")
        self.assertEqual(loaded_ann.business_rules, ["Only active users can authenticate"])
        self.assertEqual(loaded_ann.columns.get("ID"), "Primary user ID")

    def test_push_and_pull_local_and_remote(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            cfg = SeaweedFSConfig(endpoint_url="http://localhost:8333", bucket="leai-test")
            storage = SeaweedFSStorage(cfg)
            storage._s3_client = self.mock_s3_client

            raw_dir = tmp_path / "raw"
            raw_dir.mkdir()
            (raw_dir / "test.json").write_text("{}", encoding="utf-8")

            ann_dir = tmp_path / "annotations"
            ann_dir.mkdir()
            (ann_dir / "test.yml").write_text("description: test", encoding="utf-8")

            push_counts = storage.push_local_to_remote(raw_dir, ann_dir)
            self.assertEqual(push_counts["raw"], 1)
            self.assertEqual(push_counts["annotations"], 1)
            self.assertEqual(self.mock_s3_client.upload_file.call_count, 2)

    def test_cli_seaweed_status_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            runner = CliRunner()
            config_file = tmp_path / "leai.yml"
            config_file.write_text(
                """
schemas: [TEST]
storage:
  seaweedfs:
    endpoint_url: "http://localhost:8333"
    bucket: "leai-test"
""",
                encoding="utf-8",
            )

            with patch("leai.storage.SeaweedFSStorage.test_connection") as mock_test:
                mock_test.return_value = {
                    "success": True,
                    "endpoint": "http://localhost:8333",
                    "bucket": "leai-test",
                    "objects_found": 10,
                    "message": "Connection operational",
                }
                result = runner.invoke(app, ["seaweed", "status", "--config", str(config_file)], color=False)
                self.assertEqual(result.exit_code, 0)
                clean_output = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", result.output)
                self.assertIn("SeaweedFS S3 Storage Status", clean_output)
                self.assertIn("OPERATIONAL", clean_output)

    def test_cli_seaweed_push_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            runner = CliRunner()
            config_file = tmp_path / "leai.yml"
            config_file.write_text(
                """
schemas: [TEST]
storage:
  seaweedfs:
    endpoint_url: "http://localhost:8333"
    bucket: "leai-test"
""",
                encoding="utf-8",
            )

            with patch("leai.storage.SeaweedFSStorage.push_local_to_remote") as mock_push:
                mock_push.return_value = {"raw": 5, "annotations": 3}
                result = runner.invoke(app, ["seaweed", "push", "--config", str(config_file)], color=False)
                self.assertEqual(result.exit_code, 0)
                clean_output = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", result.output)
                self.assertIn("5 RAW JSON files uploaded", clean_output)
                self.assertIn("3 YAML annotation files uploaded", clean_output)

    def test_cli_extract_with_seaweed_flag_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(app, ["extract", "--help"], color=False)
        self.assertEqual(result.exit_code, 0)
        clean_output = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", result.output)
        self.assertIn("--seaweed", clean_output)
        self.assertIn("-W", clean_output)
        self.assertIn("--no-cache", clean_output)

    def test_save_raw_schema_no_cache(self) -> None:
        from leai.raw import save_raw_schema

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            storage = MagicMock()
            raw_path = tmp_path / "raw"

            saved = save_raw_schema(self.sample_schema, raw_path, multi_schema=True, storage=storage, local_cache=False)
            self.assertEqual(len(saved), 0)
            self.assertFalse(raw_path.exists())
            storage.save_raw_schema.assert_called_once_with(self.sample_schema, multi_schema=True, force=False)

    def test_load_raw_schemas_no_cache(self) -> None:
        from leai.raw import load_raw_schemas

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            storage = MagicMock()
            storage.load_raw_schemas.return_value = {"TEST_SCHEMA": self.sample_schema}
            raw_path = tmp_path / "raw"

            loaded = load_raw_schemas(raw_path, target_schemas=["TEST_SCHEMA"], storage=storage, local_cache=False)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].schema_name, "TEST_SCHEMA")
            self.assertFalse(raw_path.exists())

    def test_cli_extract_no_cache_requires_seaweed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            runner = CliRunner()
            config_file = tmp_path / "leai.yml"
            config_file.write_text(
                """
schemas: [TEST]
storage:
  seaweedfs:
    enabled: false
""",
                encoding="utf-8",
            )
            result = runner.invoke(app, ["extract", "--config", str(config_file), "--no-cache"], color=False)
            self.assertEqual(result.exit_code, 1)
            clean_output = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", result.output)
            self.assertIn("--no-cache requires SeaweedFS to be enabled", clean_output)

    def test_canonical_hash_determinism(self) -> None:
        data_a = {"name": "USERS", "columns": [{"name": "ID", "type": "NUMBER"}, {"name": "NAME", "type": "VARCHAR2"}]}
        # Same content, different key insertion order
        data_b = {"columns": [{"type": "NUMBER", "name": "ID"}, {"name": "NAME", "type": "VARCHAR2"}], "name": "USERS"}

        _, hash_a = SeaweedFSStorage._compute_canonical_hash(data_a)
        _, hash_b = SeaweedFSStorage._compute_canonical_hash(data_b)
        self.assertEqual(hash_a, hash_b)

    def test_manifest_load_and_save(self) -> None:
        cfg = SeaweedFSConfig(endpoint_url="http://localhost:8333", bucket="leai-test", raw_prefix="raw")
        storage = SeaweedFSStorage(cfg)
        storage._s3_client = self.mock_s3_client

        # 1. Save manifest
        hashes = {"tables/USERS.json": "abc123hash"}
        manifest_key = storage.save_manifest("TEST_SCHEMA", hashes)
        self.assertEqual(manifest_key, "raw/TEST_SCHEMA/_manifest.json")

        # Verify put_object call
        self.mock_s3_client.put_object.assert_called_once()
        call_kwargs = self.mock_s3_client.put_object.call_args.kwargs
        self.assertEqual(call_kwargs["Key"], "raw/TEST_SCHEMA/_manifest.json")
        saved_body = json.loads(call_kwargs["Body"].decode("utf-8"))
        self.assertEqual(saved_body["hashes"], hashes)

        # 2. Load manifest
        mock_body = MagicMock()
        mock_body.read.return_value = json.dumps(saved_body).encode("utf-8")
        self.mock_s3_client.get_object.return_value = {"Body": mock_body}

        loaded_hashes = storage.load_manifest("TEST_SCHEMA")
        self.assertEqual(loaded_hashes, hashes)

    def test_save_raw_schema_incremental_skip_unmodified(self) -> None:
        cfg = SeaweedFSConfig(endpoint_url="http://localhost:8333", bucket="leai-test", raw_prefix="raw", incremental=True)
        storage = SeaweedFSStorage(cfg)
        storage._s3_client = self.mock_s3_client

        # Compute expected hash for sample_schema's table
        _, table_hash = SeaweedFSStorage._compute_canonical_hash(self.sample_schema.tables[0].model_dump())

        # Pre-populate manifest in mock S3 with the exact same hash
        mock_manifest = {"version": 1, "hashes": {"tables/USERS.json": table_hash}}
        mock_body = MagicMock()
        mock_body.read.return_value = json.dumps(mock_manifest).encode("utf-8")
        self.mock_s3_client.get_object.return_value = {"Body": mock_body}

        # Save schema with incremental=True -> should skip USERS.json
        res = storage.save_raw_schema(self.sample_schema, multi_schema=True)

        self.assertEqual(res.total, 1)
        self.assertEqual(res.skipped, 1)
        self.assertEqual(res.uploaded, 0)
        # put_object should NOT be called for tables/USERS.json
        put_keys = [call.kwargs["Key"] for call in self.mock_s3_client.put_object.call_args_list]
        self.assertNotIn("raw/TEST_SCHEMA/tables/USERS.json", put_keys)

    def test_save_raw_schema_incremental_modified_object(self) -> None:
        cfg = SeaweedFSConfig(endpoint_url="http://localhost:8333", bucket="leai-test", raw_prefix="raw", incremental=True)
        storage = SeaweedFSStorage(cfg)
        storage._s3_client = self.mock_s3_client

        # Manifest has an OLD / outdated hash
        mock_manifest = {"version": 1, "hashes": {"tables/USERS.json": "old_different_hash"}}
        mock_body = MagicMock()
        mock_body.read.return_value = json.dumps(mock_manifest).encode("utf-8")
        self.mock_s3_client.get_object.return_value = {"Body": mock_body}

        # Save schema -> should detect modification and upload
        res = storage.save_raw_schema(self.sample_schema, multi_schema=True)

        self.assertEqual(res.total, 1)
        self.assertEqual(res.skipped, 0)
        self.assertEqual(res.uploaded, 1)
        put_keys = [call.kwargs["Key"] for call in self.mock_s3_client.put_object.call_args_list]
        self.assertIn("raw/TEST_SCHEMA/tables/USERS.json", put_keys)
        self.assertIn("raw/TEST_SCHEMA/_manifest.json", put_keys)
        self.assertIn("raw/TEST_SCHEMA/_schema.json", put_keys)

    def test_save_raw_schema_force_upload(self) -> None:
        cfg = SeaweedFSConfig(endpoint_url="http://localhost:8333", bucket="leai-test", raw_prefix="raw", incremental=True)
        storage = SeaweedFSStorage(cfg)
        storage._s3_client = self.mock_s3_client

        # Pre-populate manifest with matching hash
        _, table_hash = SeaweedFSStorage._compute_canonical_hash(self.sample_schema.tables[0].model_dump())
        mock_manifest = {"version": 1, "hashes": {"tables/USERS.json": table_hash}}
        mock_body = MagicMock()
        mock_body.read.return_value = json.dumps(mock_manifest).encode("utf-8")
        self.mock_s3_client.get_object.return_value = {"Body": mock_body}

        # Save with force=True -> should bypass manifest check and upload everything
        res = storage.save_raw_schema(self.sample_schema, multi_schema=True, force=True)

        self.assertEqual(res.total, 1)
        self.assertEqual(res.uploaded, 1)
        self.assertEqual(res.skipped, 0)
        put_keys = [call.kwargs["Key"] for call in self.mock_s3_client.put_object.call_args_list]
        self.assertIn("raw/TEST_SCHEMA/tables/USERS.json", put_keys)

    def test_cli_extract_with_force_upload_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(app, ["extract", "--help"], color=False)
        self.assertEqual(result.exit_code, 0)
        clean_output = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", result.output)
        self.assertIn("--force-upload", clean_output)
        self.assertIn("-F", clean_output)


if __name__ == "__main__":
    unittest.main()
