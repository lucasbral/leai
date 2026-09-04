from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from leai.cli import app
from leai.config import SeaweedFSConfig, load_config
from leai.models import ColumnMeta, ObjectAnnotation, SchemaMetadata, TableMeta
from leai.storage import SeaweedFSStorage, StorageError


@pytest.fixture
def mock_s3_client():
    client = MagicMock()
    return client


@pytest.fixture
def sample_schema():
    return SchemaMetadata(
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


def test_seaweedfs_config_defaults():
    cfg = SeaweedFSConfig()
    assert cfg.enabled is False
    assert cfg.endpoint_url == ""
    assert cfg.bucket == "leai"
    assert cfg.raw_prefix == "raw"
    assert cfg.annotations_prefix == "annotations"
    assert cfg.auto_create_bucket is True


def test_load_config_with_storage_and_env(tmp_path: Path, monkeypatch):
    config_file = tmp_path / "leai.yml"
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

    monkeypatch.setenv("LEAI_SEAWEED_ENABLED", "true")
    monkeypatch.setenv("LEAI_SEAWEED_ENDPOINT", "http://env-host:8333")
    monkeypatch.setenv("LEAI_SEAWEED_BUCKET", "env-bucket")
    monkeypatch.setenv("LEAI_SEAWEED_ACCESS_KEY", "env-access")
    monkeypatch.setenv("LEAI_SEAWEED_SECRET_KEY", "env-secret")

    loaded = load_config(config_file)
    assert loaded.storage.seaweedfs.enabled is True
    assert loaded.storage.seaweedfs.endpoint_url == "http://env-host:8333"
    assert loaded.storage.seaweedfs.bucket == "env-bucket"
    assert loaded.storage.seaweedfs.access_key == "env-access"
    assert loaded.storage.seaweedfs.secret_key == "env-secret"


def test_seaweedfs_storage_missing_endpoint():
    cfg = SeaweedFSConfig(endpoint_url="")
    storage = SeaweedFSStorage(cfg)
    with pytest.raises(StorageError, match="endpoint_url must be provided"):
        _ = storage.client


def test_seaweedfs_storage_ensure_bucket_exists(mock_s3_client):
    cfg = SeaweedFSConfig(endpoint_url="http://localhost:8333", bucket="leai-test", auto_create_bucket=True)
    storage = SeaweedFSStorage(cfg)
    storage._s3_client = mock_s3_client

    # Case 1: Bucket already exists
    storage.ensure_bucket_exists()
    mock_s3_client.head_bucket.assert_called_with(Bucket="leai-test")
    assert mock_s3_client.create_bucket.call_count == 0

    # Case 2: Bucket does not exist -> create_bucket is called
    mock_s3_client.head_bucket.side_effect = Exception("NoSuchBucket")
    storage.ensure_bucket_exists()
    mock_s3_client.create_bucket.assert_called_with(Bucket="leai-test")


def test_seaweedfs_storage_test_connection_success(mock_s3_client):
    cfg = SeaweedFSConfig(endpoint_url="http://localhost:8333", bucket="leai-test")
    storage = SeaweedFSStorage(cfg)
    storage._s3_client = mock_s3_client
    mock_s3_client.list_objects_v2.return_value = {"KeyCount": 42}

    res = storage.test_connection()
    assert res["success"] is True
    assert res["objects_found"] == 42
    assert "operational" in res["message"].lower()


def test_seaweedfs_storage_test_connection_failure(mock_s3_client):
    cfg = SeaweedFSConfig(endpoint_url="http://localhost:8333", bucket="leai-test")
    storage = SeaweedFSStorage(cfg)
    storage._s3_client = mock_s3_client
    mock_s3_client.head_bucket.side_effect = Exception("Connection refused")
    mock_s3_client.create_bucket.side_effect = Exception("Connection refused")

    res = storage.test_connection()
    assert res["success"] is False
    assert "connection failed" in res["message"].lower()


def test_save_raw_schema_to_seaweed(mock_s3_client, sample_schema):
    cfg = SeaweedFSConfig(endpoint_url="http://localhost:8333", bucket="leai-test", raw_prefix="raw")
    storage = SeaweedFSStorage(cfg)
    storage._s3_client = mock_s3_client

    uploaded = storage.save_raw_schema(sample_schema, multi_schema=True)

    assert "raw/TEST_SCHEMA/_schema.json" in uploaded
    assert "raw/TEST_SCHEMA/tables/USERS.json" in uploaded

    # Verify put_object calls
    put_keys = [call.kwargs["Key"] for call in mock_s3_client.put_object.call_args_list]
    assert "raw/TEST_SCHEMA/_schema.json" in put_keys
    assert "raw/TEST_SCHEMA/tables/USERS.json" in put_keys


def test_load_raw_schemas_from_seaweed(mock_s3_client, sample_schema):
    cfg = SeaweedFSConfig(endpoint_url="http://localhost:8333", bucket="leai-test", raw_prefix="raw")
    storage = SeaweedFSStorage(cfg)
    storage._s3_client = mock_s3_client

    # Mock list_objects_v2 paginator
    mock_paginator = MagicMock()
    mock_paginator.paginate.return_value = [{"CommonPrefixes": [{"Prefix": "raw/TEST_SCHEMA/"}]}]
    mock_s3_client.get_paginator.return_value = mock_paginator

    # Mock get_object for _schema.json
    schema_json = json.dumps(sample_schema.model_dump())
    mock_body = MagicMock()
    mock_body.read.return_value = schema_json.encode("utf-8")
    mock_s3_client.get_object.return_value = {"Body": mock_body}

    loaded = storage.load_raw_schemas()
    assert "TEST_SCHEMA" in loaded
    meta = loaded["TEST_SCHEMA"]
    assert meta.schema_name == "TEST_SCHEMA"
    assert len(meta.tables) == 1
    assert meta.tables[0].name == "USERS"


def test_save_and_load_annotation_seaweed(mock_s3_client):
    cfg = SeaweedFSConfig(endpoint_url="http://localhost:8333", bucket="leai-test", annotations_prefix="annotations")
    storage = SeaweedFSStorage(cfg)
    storage._s3_client = mock_s3_client

    ann = ObjectAnnotation(
        description="Users business entity",
        business_rules=["Only active users can authenticate"],
        columns={"ID": "Primary user ID"},
    )

    key = storage.save_annotation("TEST_SCHEMA", "tables", "USERS", ann)
    assert key == "annotations/TEST_SCHEMA/tables/USERS.yml"

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
    mock_s3_client.get_object.return_value = {"Body": mock_body}

    loaded_ann = storage.load_annotation("TEST_SCHEMA", "tables", "USERS")
    assert loaded_ann.description == "Users business entity"
    assert loaded_ann.business_rules == ["Only active users can authenticate"]
    assert loaded_ann.columns.get("ID") == "Primary user ID"


def test_push_and_pull_local_and_remote(tmp_path: Path, mock_s3_client):
    cfg = SeaweedFSConfig(endpoint_url="http://localhost:8333", bucket="leai-test")
    storage = SeaweedFSStorage(cfg)
    storage._s3_client = mock_s3_client

    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "test.json").write_text("{}", encoding="utf-8")

    ann_dir = tmp_path / "annotations"
    ann_dir.mkdir()
    (ann_dir / "test.yml").write_text("description: test", encoding="utf-8")

    push_counts = storage.push_local_to_remote(raw_dir, ann_dir)
    assert push_counts["raw"] == 1
    assert push_counts["annotations"] == 1
    assert mock_s3_client.upload_file.call_count == 2


def test_cli_seaweed_status_command(tmp_path: Path):
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
        result = runner.invoke(app, ["seaweed", "status", "--config", str(config_file)])
        assert result.exit_code == 0
        assert "SeaweedFS S3 Storage Status" in result.output
        assert "OPERATIONAL" in result.output


def test_cli_seaweed_push_command(tmp_path: Path):
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
        result = runner.invoke(app, ["seaweed", "push", "--config", str(config_file)])
        assert result.exit_code == 0
        assert "5 RAW JSON files uploaded" in result.output
        assert "3 YAML annotation files uploaded" in result.output


def test_cli_extract_with_seaweed_flag_help():
    runner = CliRunner()
    result = runner.invoke(app, ["extract", "--help"])
    assert result.exit_code == 0
    assert "--seaweed" in result.output
    assert "-W" in result.output
