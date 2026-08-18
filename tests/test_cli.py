from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from leai.cli import app
from leai.models import ColumnMeta, SchemaMetadata, TableMeta
from leai.raw import save_raw_schema


class CliIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()

    def test_version_option(self):
        result = self.runner.invoke(app, ["--version"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("LEAI CLI version 0.2.6", result.output)

    def test_version_short_option(self):
        result = self.runner.invoke(app, ["-v"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("LEAI CLI version 0.2.6", result.output)

    def test_help_command(self):
        result = self.runner.invoke(app, ["--help"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("CLI for Oracle Database Intelligence & Documentation.", result.output)
        self.assertIn("init", result.output)
        self.assertIn("check", result.output)
        self.assertIn("extract", result.output)
        self.assertIn("annotate", result.output)
        self.assertIn("compile", result.output)
        self.assertIn("generate", result.output)
        self.assertIn("changes", result.output)
        self.assertIn("trace", result.output)
        self.assertIn("enrich", result.output)
        self.assertIn("ask", result.output)
        self.assertIn("chat", result.output)

    def test_init_command(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "leai.yml"
            # 1. Initial creation
            result = self.runner.invoke(app, ["init", "--output", str(out_file)])
            self.assertEqual(result.exit_code, 0)
            self.assertTrue(out_file.exists())
            self.assertIn("Configuration file created", result.output)

            # 2. Attempt without --force (must fail)
            result_again = self.runner.invoke(app, ["init", "--output", str(out_file)])
            self.assertEqual(result_again.exit_code, 1)
            self.assertIn("already exists", " ".join(result_again.output.split()))

            # 3. With --force (must overwrite)
            result_force = self.runner.invoke(app, ["init", "--output", str(out_file), "--force"])
            self.assertEqual(result_force.exit_code, 0)
            self.assertIn("Configuration file created", result_force.output)

    def test_check_command(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_file = Path(tmpdir) / "leai.yml"
            cfg_file.write_text(
                """
schemas:
  - HR
rawPath: "./raw"
annotationsPath: "./annotations"
docPath: "./docs"
ai:
  default_provider: "openai"
  providers:
    openai:
      api_key: "sk-test"
                """,
                encoding="utf-8",
            )
            result = self.runner.invoke(app, ["check", "--config", str(cfg_file)])
            self.assertEqual(result.exit_code, 0)
            self.assertIn("Valid configuration!", result.output)
            self.assertIn("DSN not configured", result.output)

    def test_annotate_and_compile_with_summary_panel(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            raw_dir = base / "raw"
            ann_dir = base / "annotations"
            doc_dir = base / "docs"

            schema = SchemaMetadata(
                schema_name="HR",
                tables=[
                    TableMeta(
                        name="EMPLOYEES",
                        comment="Employees table",
                        columns=[
                            ColumnMeta(name="ID", data_type="NUMBER", nullable=False),
                            ColumnMeta(name="NAME", data_type="VARCHAR2(100)", nullable=False),
                        ],
                        primary_keys=["ID"],
                    )
                ],
            )
            save_raw_schema(schema, raw_dir)

            cfg_file = base / "leai.yml"
            cfg_file.write_text(
                f"""
schemas:
  - HR
rawPath: "{raw_dir.as_posix()}"
annotationsPath: "{ann_dir.as_posix()}"
docPath: "{doc_dir.as_posix()}"
                """,
                encoding="utf-8",
            )

            # Test annotate (validates that _print_final_summary_panel executes safely)
            result_ann = self.runner.invoke(app, ["annotate", "--config", str(cfg_file)])
            self.assertEqual(result_ann.exit_code, 0, msg=result_ann.output)
            self.assertIn("Annotation Synchronization Completed", result_ann.output)
            self.assertTrue((ann_dir / "tables" / "EMPLOYEES.yml").exists())

            # Test compile (validates that _print_final_summary_panel executes safely)
            result_comp = self.runner.invoke(app, ["compile", "--config", str(cfg_file)])
            self.assertEqual(result_comp.exit_code, 0, msg=result_comp.output)
            self.assertIn("Markdown Compilation Completed", result_comp.output)
            self.assertTrue((doc_dir / "tables" / "EMPLOYEES.md").exists())

    def test_changes_command(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            raw_dir = base / "raw"
            from datetime import datetime

            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            schema = SchemaMetadata(
                schema_name="HR",
                tables=[
                    TableMeta(
                        name="EMPLOYEES",
                        last_ddl_time=now_str,
                        columns=[ColumnMeta(name="ID", data_type="NUMBER", nullable=False)],
                    ),
                    TableMeta(
                        name="OLD_TABLE",
                        last_ddl_time="2020-01-01 00:00:00",
                        columns=[ColumnMeta(name="ID", data_type="NUMBER", nullable=False)],
                    ),
                ],
            )
            save_raw_schema(schema, raw_dir)

            cfg_file = base / "leai.yml"
            cfg_file.write_text(
                f"""
schemas:
  - HR
rawPath: "{raw_dir.as_posix()}"
annotationsPath: "{(base / "annotations").as_posix()}"
docPath: "{(base / "docs").as_posix()}"
                """,
                encoding="utf-8",
            )

            # 1. Should find EMPLOYEES
            result = self.runner.invoke(app, ["changes", "--config", str(cfg_file), "--days", "7"])
            self.assertEqual(result.exit_code, 0)
            self.assertIn("EMPLOYEES", result.output)
            self.assertNotIn("OLD_TABLE", result.output)

            # 2. Filter days where nothing was modified
            result_empty = self.runner.invoke(app, ["changes", "--config", str(cfg_file), "--days", "0"])
            self.assertEqual(result_empty.exit_code, 0)
            self.assertIn("No database objects were modified", result_empty.output)

    def test_trace_offline_command(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            raw_dir = base / "raw"
            doc_dir = base / "docs"

            schema = SchemaMetadata(
                schema_name="HR",
                tables=[
                    TableMeta(
                        name="DEPARTMENTS",
                        columns=[ColumnMeta(name="ID", data_type="NUMBER", nullable=False)],
                        primary_keys=["ID"],
                    ),
                    TableMeta(
                        name="EMPLOYEES",
                        columns=[
                            ColumnMeta(name="ID", data_type="NUMBER", nullable=False),
                            ColumnMeta(name="DEP_ID", data_type="NUMBER", nullable=False),
                        ],
                        primary_keys=["ID"],
                    ),
                ],
            )
            save_raw_schema(schema, raw_dir)

            cfg_file = base / "leai.yml"
            cfg_file.write_text(
                f"""
schemas:
  - HR
rawPath: "{raw_dir.as_posix()}"
annotationsPath: "{(base / "annotations").as_posix()}"
docPath: "{doc_dir.as_posix()}"
                """,
                encoding="utf-8",
            )

            result = self.runner.invoke(
                app,
                ["trace", "EMPLOYEES", "--offline", "--config", str(cfg_file), "--rag-json"],
            )
            self.assertEqual(result.exit_code, 0, msg=result.output)
            self.assertIn("Impact X-Ray", result.output)
            self.assertTrue((doc_dir / "dossiers" / "EMPLOYEES.md").exists())
            self.assertTrue((doc_dir / "chunks" / "EMPLOYEES.json").exists())

    @patch("leai.cli.get_llm_client")
    def test_ask_command_mocked(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.model = "mock-gpt-4o"
        mock_client.generate_text.return_value = "The EMPLOYEES table stores employee records."
        mock_client.generate_chat.return_value = "The EMPLOYEES table stores employee records."
        mock_client.generate_chat_with_tools.return_value = ("The EMPLOYEES table stores employee records.", [])
        mock_get_client.return_value = mock_client

        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            raw_dir = base / "raw"
            schema = SchemaMetadata(
                schema_name="HR",
                tables=[
                    TableMeta(
                        name="EMPLOYEES",
                        comment="Employees table",
                        columns=[ColumnMeta(name="ID", data_type="NUMBER", nullable=False)],
                    )
                ],
            )
            save_raw_schema(schema, raw_dir)

            cfg_file = base / "leai.yml"
            cfg_file.write_text(
                f"""
schemas:
  - HR
rawPath: "{raw_dir.as_posix()}"
annotationsPath: "{(base / "annotations").as_posix()}"
docPath: "{(base / "docs").as_posix()}"
ai:
  default_provider: "openai"
                """,
                encoding="utf-8",
            )

            result = self.runner.invoke(
                app,
                ["ask", "What is the purpose of EMPLOYEES table?", "--config", str(cfg_file)],
            )
            self.assertEqual(result.exit_code, 0, msg=result.output)
            self.assertIn("LEAI Assistant", result.output)
            self.assertIn("EMPLOYEES", result.output)

    @patch("leai.cli.get_llm_client")
    def test_enrich_command_mocked(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.model = "mock-gpt-4o"
        mock_client.generate_json.return_value = {
            "description": "Company employees table",
            "business_rules": ["Rule 1: Every employee must have salary > 0"],
            "tags": ["HR", "Employees"],
            "columns": {"ID": "Unique identifier"},
        }
        mock_get_client.return_value = mock_client

        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            raw_dir = base / "raw"
            ann_dir = base / "annotations"

            schema = SchemaMetadata(
                schema_name="HR",
                tables=[
                    TableMeta(
                        name="EMPLOYEES",
                        columns=[ColumnMeta(name="ID", data_type="NUMBER", nullable=False)],
                    )
                ],
            )
            save_raw_schema(schema, raw_dir)

            cfg_file = base / "leai.yml"
            cfg_file.write_text(
                f"""
schemas:
  - HR
rawPath: "{raw_dir.as_posix()}"
annotationsPath: "{ann_dir.as_posix()}"
docPath: "{(base / "docs").as_posix()}"
ai:
  default_provider: "openai"
                """,
                encoding="utf-8",
            )

            result = self.runner.invoke(
                app,
                ["enrich", "--config", str(cfg_file), "--provider", "openai"],
            )
            self.assertEqual(result.exit_code, 0, msg=result.output)
            self.assertIn("Enrichment Summary Completed", result.output)
            self.assertTrue((ann_dir / "tables" / "EMPLOYEES.yml").exists())

    def test_check_command_invalid_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            non_existent = Path(tmpdir) / "does_not_exist.yml"
            result = self.runner.invoke(app, ["check", "--config", str(non_existent)])
            self.assertEqual(result.exit_code, 1)
            self.assertIn("Configuration error", result.output)

    @patch("leai.cli.oracledb.connect")
    @patch("leai.cli.fetch_available_schemas")
    @patch("leai.cli.fetch_schema_metadata")
    def test_extract_and_generate_mocked(self, mock_fetch_meta, mock_fetch_schemas, mock_connect):
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        mock_fetch_schemas.return_value = ["HR"]

        fake_schema = SchemaMetadata(
            schema_name="HR",
            tables=[
                TableMeta(
                    name="EMPLOYEES",
                    columns=[ColumnMeta(name="ID", data_type="NUMBER", nullable=False)],
                )
            ],
        )
        mock_fetch_meta.return_value = fake_schema

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

            # Test extract
            result_ext = self.runner.invoke(app, ["extract", "--config", str(cfg_file)])
            self.assertEqual(result_ext.exit_code, 0, msg=result_ext.output)
            self.assertIn("RAW Extraction Completed", result_ext.output)

            # Test generate (full pipeline and _print_final_summary_panel)
            result_gen = self.runner.invoke(app, ["generate", "--config", str(cfg_file)])
            self.assertEqual(result_gen.exit_code, 0, msg=result_gen.output)
            self.assertIn("Documentation Generation Completed", result_gen.output)

            # Test default invocation (calling bare `leai` without subcommand starts interactive studio)
            result_default = self.runner.invoke(app, ["--config", str(cfg_file)], input="/exit\n")
            self.assertEqual(result_default.exit_code, 0, msg=result_default.output)
            self.assertIn("Oracle Database Docs", result_default.output)
            self.assertIn("LEAI CLI", result_default.output)

            # Test doc command
            result_doc = self.runner.invoke(app, ["doc", "EMPLOYEES", "--config", str(cfg_file)], input="0\n")
            self.assertEqual(result_doc.exit_code, 0, msg=result_doc.output)
            self.assertIn("LEAI Documentation Studio", result_doc.output)

    @patch("leai.cli.oracledb.connect")
    @patch("leai.cli.fetch_available_schemas")
    @patch("leai.cli.fetch_schema_metadata")
    def test_schema_short_flag_and_subfolder_creation(self, mock_fetch_meta, mock_fetch_schemas, mock_connect):
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        mock_fetch_schemas.return_value = ["HADES"]

        fake_schema = SchemaMetadata(
            schema_name="HADES",
            tables=[
                TableMeta(
                    name="T_LOG",
                    columns=[ColumnMeta(name="ID", data_type="NUMBER", nullable=False)],
                )
            ],
        )
        mock_fetch_meta.return_value = fake_schema

        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            cfg_file = base / "leai.yml"
            cfg_file.write_text(
                f"""
dsn: "oracle://user:pass@localhost:1521/ORCL"
schemas:
  - C_ERGON
rawPath: "{(base / "raw").as_posix()}"
annotationsPath: "{(base / "annotations").as_posix()}"
docPath: "{(base / "docs").as_posix()}"
                """,
                encoding="utf-8",
            )

            # Test extract with -s HADES override
            result_ext = self.runner.invoke(app, ["extract", "-c", str(cfg_file), "-s", "HADES"])
            self.assertEqual(result_ext.exit_code, 0, msg=result_ext.output)
            self.assertTrue((base / "raw" / "HADES" / "tables" / "T_LOG.json").exists())

            # Test compile with -s HADES override
            result_comp = self.runner.invoke(app, ["compile", "-c", str(cfg_file), "-s", "HADES"])
            self.assertEqual(result_comp.exit_code, 0, msg=result_comp.output)
            self.assertTrue((base / "docs" / "HADES" / "tables" / "T_LOG.md").exists())
            self.assertTrue((base / "annotations" / "HADES" / "tables" / "T_LOG.yml").exists())

    @patch("leai.cli.oracledb.connect")
    @patch("leai.cli.fetch_schema_metadata")
    def test_extract_overrides_all_in_config(self, mock_fetch_meta, mock_connect):
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        fake_schema = SchemaMetadata(
            schema_name="HADES",
            tables=[
                TableMeta(
                    name="T_LOG",
                    columns=[ColumnMeta(name="ID", data_type="NUMBER", nullable=False)],
                )
            ],
        )
        mock_fetch_meta.return_value = fake_schema

        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            cfg_file = base / "leai.yml"
            cfg_file.write_text(
                f"""
dsn: "oracle://user:pass@localhost:1521/ORCL"
schemas: "ALL"
rawPath: "{(base / "raw").as_posix()}"
annotationsPath: "{(base / "annotations").as_posix()}"
docPath: "{(base / "docs").as_posix()}"
                """,
                encoding="utf-8",
            )

            # Test extract with -s HADES override when config has schemas: "ALL"
            result_ext = self.runner.invoke(app, ["extract", "-c", str(cfg_file), "-s", "HADES"])
            self.assertEqual(result_ext.exit_code, 0, msg=result_ext.output)
            # fetch_schema_metadata should only have been called for HADES
            mock_fetch_meta.assert_called_once()
            self.assertEqual(mock_fetch_meta.call_args[1]["schema_name"], "HADES")
            self.assertTrue((base / "raw" / "HADES" / "tables" / "T_LOG.json").exists())

    def test_compile_single_object_offline(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            raw_dir = base / "raw"
            schema = SchemaMetadata(
                schema_name="HR",
                tables=[
                    TableMeta(
                        name="EMPLOYEES",
                        columns=[ColumnMeta(name="ID", data_type="NUMBER", nullable=False)],
                    ),
                    TableMeta(
                        name="DEPARTMENTS",
                        columns=[ColumnMeta(name="ID", data_type="NUMBER", nullable=False)],
                    ),
                ],
            )
            save_raw_schema(schema, raw_dir)

            cfg_file = base / "leai.yml"
            cfg_file.write_text(
                f"""
schemas:
  - HR
rawPath: "{raw_dir.as_posix()}"
annotationsPath: "{(base / "annotations").as_posix()}"
docPath: "{(base / "docs").as_posix()}"
                """,
                encoding="utf-8",
            )

            # Compile ONLY EMPLOYEES
            result = self.runner.invoke(app, ["compile", "-c", str(cfg_file), "-o", "EMPLOYEES"])
            self.assertEqual(result.exit_code, 0, msg=result.output)
            self.assertTrue((base / "docs" / "tables" / "EMPLOYEES.md").exists())
            self.assertFalse((base / "docs" / "tables" / "DEPARTMENTS.md").exists())

    @patch("leai.web.start_server")
    def test_serve_command(self, mock_start_server):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            cfg_file = base / "leai.yml"
            cfg_file.write_text("schemas:\n  - HR\n", encoding="utf-8")

            result = self.runner.invoke(app, ["serve", "--config", str(cfg_file), "--port", "8899", "--no-open"])
            self.assertEqual(result.exit_code, 0, msg=result.output)
            self.assertIn("Web Studio Running", result.output)
            self.assertTrue(mock_start_server.called)


if __name__ == "__main__":
    unittest.main()
