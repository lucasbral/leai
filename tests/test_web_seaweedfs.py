from __future__ import annotations

import json
import tempfile
import urllib.request
from pathlib import Path
from unittest.mock import MagicMock

from leai.config import LeaiConfig, SeaweedFSConfig
from leai.models import ColumnMeta, ObjectAnnotation, SchemaMetadata, TableMeta
from leai.storage import SeaweedFSStorage
from leai.web.server import start_server


def test_storage_list_annotated_objects():
    cfg = SeaweedFSConfig(enabled=True, bucket="test-bucket", endpoint_url="http://localhost:8333")
    storage = SeaweedFSStorage(cfg)

    mock_client = MagicMock()
    mock_paginator = MagicMock()
    mock_paginator.paginate.return_value = [
        {
            "Contents": [
                {"Key": "annotations/HR/tables/EMPLOYEES.yml"},
                {"Key": "annotations/HR/views/V_EMP.yaml"},
                {"Key": "annotations/glossary.yml"},
                {"Key": "annotations/readme.txt"},
            ]
        }
    ]
    mock_client.get_paginator.return_value = mock_paginator
    storage._s3_client = mock_client
    storage.ensure_bucket_exists = MagicMock()

    annotated = storage.list_annotated_objects()
    assert ("HR", "tables", "EMPLOYEES") in annotated
    assert ("HR", "views", "V_EMP") in annotated
    assert ("", "tables", "EMPLOYEES") in annotated
    # Glossary should not be counted as an annotated schema object
    assert not any(item[2] == "GLOSSARY" for item in annotated)


def test_web_server_seaweedfs_fallback():
    """Test that when schemas is empty and local disk has no files, the web server
    loads schemas and annotations from SeaweedFS.
    """
    table = TableMeta(
        name="CLIENTES",
        comment="Tabela de clientes no bucket",
        columns=[ColumnMeta(name="ID", data_type="NUMBER", nullable=False)],
    )
    schema_remote = SchemaMetadata(schema_name="VENDAS", tables=[table])

    mock_storage = MagicMock()
    mock_storage.load_raw_schemas.return_value = {"VENDAS": schema_remote}
    mock_storage.list_annotated_objects.return_value = {("VENDAS", "tables", "CLIENTES")}
    mock_storage.load_annotation.return_value = ObjectAnnotation(description="Descrição remota de CLIENTES vinda do bucket SeaweedFS")

    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        cfg = LeaiConfig()
        cfg.rawPath = base / "raw"
        cfg.annotationsPath = base / "annotations"
        cfg.docPath = base / "docs"
        cfg.storage.seaweedfs.enabled = True
        cfg.storage.seaweedfs.no_cache = True  # don't write to disk

        # Local directory has 0 files
        assert not cfg.rawPath.exists()

        server, url = start_server(
            config=cfg,
            schemas=[],  # empty schemas passed
            storage=mock_storage,
            open_browser=False,
            in_background=True,
            port=8123,
        )

        try:
            # 1. Test /api/status
            req = urllib.request.Request(f"{url}/api/status")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                assert data["status"] == "online"
                assert data["schemas_count"] == 1
                assert data["seaweedfs"]["connected"] is True

            # 2. Test /api/catalog
            req = urllib.request.Request(f"{url}/api/catalog")
            with urllib.request.urlopen(req, timeout=5) as resp:
                cat_data = json.loads(resp.read().decode("utf-8"))
                schemas = cat_data.get("schemas", [])
                assert len(schemas) == 1
                assert schemas[0]["schema_name"] == "VENDAS"
                tbl = schemas[0]["tables"][0]
                assert tbl["name"] == "CLIENTES"
                assert tbl["is_annotated"] is True

            # 3. Test /api/object
            req = urllib.request.Request(f"{url}/api/object?schema=VENDAS&name=CLIENTES")
            with urllib.request.urlopen(req, timeout=5) as resp:
                obj_data = json.loads(resp.read().decode("utf-8"))
                assert obj_data["object_name"] == "CLIENTES"
                assert "Descrição remota de CLIENTES" in obj_data["annotations"]["description"]

            # 4. Test /api/glossary (directly from SeaweedFS S3)
            from leai.models import BusinessGlossary, GlossaryTerm

            mock_storage.load_glossary.return_value = BusinessGlossary(
                terms=[GlossaryTerm(term="REGRA_S3", definition="Regra persistida no bucket S3", canonical_filter="VAL > 0")]
            )
            req = urllib.request.Request(f"{url}/api/glossary")
            with urllib.request.urlopen(req, timeout=5) as resp:
                gloss_data = json.loads(resp.read().decode("utf-8"))
                assert gloss_data["success"] is True
                assert len(gloss_data["terms"]) == 1
                assert gloss_data["terms"][0]["term"] == "REGRA_S3"

        finally:
            server.shutdown()
