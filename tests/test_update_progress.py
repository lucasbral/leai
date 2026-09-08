from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from leai.cli import app
from leai.config import LeaiConfig, SeaweedFSConfig
from leai.models import ColumnMeta, SchemaMetadata, TableMeta
from leai.storage import SeaweedFSStorage


class TestUpdateProgress(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()

    def test_storage_save_raw_schema_triggers_progress_callback(self):
        """Verify SeaweedFSStorage.save_raw_schema calls progress_callback on item uploads."""
        cfg = SeaweedFSConfig(
            enabled=True,
            endpoint_url="https://mock-s3.local",
            bucket="test-bucket",
            incremental=False,
        )
        storage = SeaweedFSStorage(cfg)
        storage._s3_client = MagicMock()
        storage.ensure_bucket_exists = MagicMock()

        schema = SchemaMetadata(
            schema_name="HR",
            tables=[
                TableMeta(
                    name=f"T_{i}",
                    columns=[ColumnMeta(name="ID", data_type="NUMBER", nullable=False)],
                )
                for i in range(5)
            ],
        )

        progress_calls = []

        def _progress_cb(done: int, total: int):
            progress_calls.append((done, total))

        result = storage.save_raw_schema(schema, multi_schema=True, progress_callback=_progress_cb)

        self.assertEqual(result.uploaded, 5)
        self.assertEqual(len(progress_calls), 5)
        # Should finish with (5, 5)
        self.assertEqual(progress_calls[-1], (5, 5))

    @patch("leai.cli.oracledb.connect")
    @patch("leai.cli.fetch_schema_metadata")
    def test_cli_update_passes_callback_and_displays_timing(self, mock_fetch_meta, mock_connect):
        """Verify CLI update command passes progress callback to fetch_schema_metadata and reports elapsed time."""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        delta_schema = SchemaMetadata(
            schema_name="HR",
            tables=[
                TableMeta(
                    name="T_DELTA",
                    columns=[ColumnMeta(name="ID", data_type="NUMBER", nullable=False)],
                )
            ],
        )

        def _fake_fetch(cfg, schema_name=None, callback=None, days=None, hours=None, connection=None):
            if callback:
                callback("Tables", 1, 1, 1)
            return delta_schema

        mock_fetch_meta.side_effect = _fake_fetch

        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            cfg_file = base / "leai.yml"
            cfg_file.write_text(
                f"""
dsn: "oracle://user:pass@localhost:1521/ORCL"
schemas:
  - HR
rawPath: "{(base / "raw").as_posix()}"
annotationsPath: "{(base / "annotations").as_posix()}"
docPath: "{(base / "docs").as_posix()}"
                """,
                encoding="utf-8",
            )

            result = self.runner.invoke(app, ["update", "-c", str(cfg_file), "--days", "2"])
            self.assertEqual(result.exit_code, 0, msg=result.output)
            self.assertIn("Schema HR", result.output)
            self.assertIn("modified object(s) found", result.output)
            self.assertIn("s)", result.output)

    @patch("oracledb.connect")
    @patch("leai.tui.session.fetch_schema_metadata")
    @patch("leai.tui.session.fetch_available_schemas")
    def test_tui_update_passes_callback_and_displays_timing(self, mock_fetch_schemas, mock_fetch_meta, mock_connect):
        """Verify TUI _run_update passes progress callback and reports elapsed duration."""
        from leai.tui.session import InteractiveTUISession

        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        mock_fetch_schemas.return_value = ["HR", "EMPTY_SCHEMA"]

        delta_schema = SchemaMetadata(
            schema_name="HR",
            tables=[
                TableMeta(
                    name="T_DELTA",
                    columns=[ColumnMeta(name="ID", data_type="NUMBER", nullable=False)],
                )
            ],
        )
        empty_schema = SchemaMetadata(schema_name="EMPTY_SCHEMA")

        def _fake_fetch(cfg, schema_name=None, callback=None, days=None, hours=None, connection=None):
            if callback:
                callback("Consultando alterações...", 0, 0, 1)
            if schema_name == "HR":
                return delta_schema
            return empty_schema

        mock_fetch_meta.side_effect = _fake_fetch

        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            cfg = LeaiConfig(
                dsn="oracle://user:pass@localhost:1521/ORCL",
                schemas=["HR", "EMPTY_SCHEMA"],
                rawPath=base / "raw",
                annotationsPath=base / "annotations",
                docPath=base / "docs",
            )
            mock_client = MagicMock()
            session = InteractiveTUISession(schemas=[], config=cfg, client=mock_client)
            with patch("leai.tui.session.console.print") as mock_print:
                session._run_update(["--days", "5"])
                printed_texts = " ".join(str(call[0][0]) for call in mock_print.call_args_list if call[0])
                self.assertIn("HR", printed_texts)
                self.assertIn("EMPTY_SCHEMA", printed_texts)
                self.assertIn("no modifications in last 5 days", printed_texts)
                self.assertIn("s)", printed_texts)
