import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from rich.console import Console
from typer.testing import CliRunner

from leai.cli import app
from leai.config import LeaiConfig, SeaweedFSConfig, StorageConfig
from leai.doctor import _troubleshoot_ai, _troubleshoot_oracle, _troubleshoot_seaweedfs, run_diagnostics


class DoctorTests(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()
        self.console = Console(record=True, width=120)

    def test_troubleshoot_helpers(self):
        # Oracle troubleshooting
        tips_auth = _troubleshoot_oracle("ORA-01017: invalid username/password; logon denied")
        self.assertTrue(any("credenciais" in t for t in tips_auth))

        tips_timeout = _troubleshoot_oracle("ORA-12170: TNS:Connect timeout occurred")
        self.assertTrue(any("1521" in t for t in tips_timeout))

        tips_listener = _troubleshoot_oracle("ORA-12541: TNS:no listener")
        self.assertTrue(any("Listener" in t for t in tips_listener))

        tips_service = _troubleshoot_oracle("ORA-12514: TNS:listener does not currently know of service")
        self.assertTrue(any("serviço Oracle" in t for t in tips_service))

        # SeaweedFS troubleshooting
        tips_sw_conn = _troubleshoot_seaweedfs("Could not connect to endpoint URL", "https://s3.local:8333", "test-bucket")
        self.assertTrue(any("http://" in t for t in tips_sw_conn))

        tips_sw_auth = _troubleshoot_seaweedfs("AccessDenied: Access Denied", "http://s3.local", "test-bucket")
        self.assertTrue(any("access_key" in t for t in tips_sw_auth))

        tips_sw_nobucket = _troubleshoot_seaweedfs("NoSuchBucket: The specified bucket does not exist", "http://s3.local", "test-bucket")
        self.assertTrue(any("auto_create_bucket" in t for t in tips_sw_nobucket))

        # AI troubleshooting
        tips_ai_ollama = _troubleshoot_ai("Connection refused", "ollama")
        self.assertTrue(any("ollama serve" in t for t in tips_ai_ollama))

        tips_ai_openai = _troubleshoot_ai("Invalid API Key", "openai")
        self.assertTrue(any("OPENAI_API_KEY" in t for t in tips_ai_openai))

    @patch("oracledb.connect")
    @patch("leai.ai.get_llm_client")
    @patch("leai.git_ops.get_git_status")
    def test_run_diagnostics_all_success(self, mock_git, mock_ai, mock_oracle):
        # Setup mocks
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = ["Oracle Database 19c Enterprise Edition"]
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_oracle.return_value = mock_conn

        mock_client = MagicMock()
        mock_client.model = "gpt-4o-mini"
        mock_ai.return_value = mock_client

        mock_git_info = MagicMock()
        mock_git_info.is_repo = True
        mock_git_info.platform_name = "GitHub"
        mock_git_info.branch = "main"
        mock_git_info.behind = 0
        mock_git_info.modified_files = []
        mock_git.return_value = mock_git_info

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = LeaiConfig(
                dsn="oracle://user:pass@localhost:1521/X",
                schemas=["HR"],
                rawPath=root / "raw",
                annotationsPath=root / "annotations",
                docPath=root / "docs",
                updates_log_path=root / "logs" / "updates",
            )
            cfg.rawPath.mkdir(parents=True)
            cfg.annotationsPath.mkdir(parents=True)
            cfg.docPath.mkdir(parents=True)
            cfg.updates_log_path.mkdir(parents=True)

            (cfg.rawPath / "table.json").write_text("{}", encoding="utf-8")
            (cfg.annotationsPath / "table.yml").write_text("description: test", encoding="utf-8")
            (cfg.docPath / "table.md").write_text("# Doc", encoding="utf-8")

            success = run_diagnostics(cfg, console=self.console)
            output = self.console.export_text()

            self.assertTrue(success)
            self.assertIn("Diagnóstico de Ambiente LEAI", output)
            self.assertIn("Oracle Database 19c", output)
            self.assertIn("gpt-4o-mini", output)
            self.assertIn("GitHub", output)
            self.assertIn("1 arquivos JSON", output)

    def test_run_diagnostics_invalid_config_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            invalid_path = Path(tmp) / "invalid_not_found.yml"
            success = run_diagnostics(invalid_path, console=self.console)
            self.assertFalse(success)

    @patch("oracledb.connect", side_effect=Exception("ORA-01017: invalid username/password"))
    @patch("leai.ai.get_llm_client")
    def test_run_diagnostics_oracle_failure(self, mock_ai, mock_oracle):
        mock_client = MagicMock()
        mock_client.model = "qwen2.5-coder"
        mock_ai.return_value = mock_client

        cfg = LeaiConfig(
            dsn="oracle://wrong:wrong@localhost:1521/X",
            schemas=["HR"],
        )
        success = run_diagnostics(cfg, console=self.console)
        output = self.console.export_text()

        self.assertFalse(success)
        self.assertIn("Falha na conexão", output)
        self.assertIn("ORA-01017", output)
        self.assertIn("Verifique as credenciais", output)

    @patch(
        "leai.storage.SeaweedFSStorage.test_connection",
        return_value={"success": False, "error": "Could not connect to endpoint URL: https://s3.corp:8333"},
    )
    def test_run_diagnostics_seaweedfs_failure(self, mock_sw):
        cfg = LeaiConfig(
            schemas=["HR"],
            storage=StorageConfig(
                seaweedfs=SeaweedFSConfig(
                    enabled=True,
                    endpoint_url="https://s3.corp:8333",
                    bucket="leai-test",
                )
            ),
        )
        success = run_diagnostics(cfg, console=self.console)
        output = self.console.export_text()

        self.assertFalse(success)
        self.assertIn("Armazenamento S3 (SeaweedFS)", output)
        self.assertIn("Could not connect to endpoint", output)
        self.assertIn("http://", output)

    @patch("leai.doctor.run_diagnostics", return_value=True)
    def test_cli_doctor_command_success(self, mock_diag):
        result = self.runner.invoke(app, ["doctor"])
        self.assertEqual(result.exit_code, 0)
        mock_diag.assert_called_once()

    @patch("leai.doctor.run_diagnostics", return_value=False)
    def test_cli_doctor_command_failure_exits_1(self, mock_diag):
        result = self.runner.invoke(app, ["doctor"])
        self.assertEqual(result.exit_code, 1)
