from __future__ import annotations

import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

from leai.config import LeaiConfig, load_config
from leai.updater import (
    UpdateInfo,
    check_for_updates,
    detect_install_method,
    is_newer_version,
    parse_version,
    prompt_and_update,
    run_upgrade,
)


class TestUpdater(unittest.TestCase):
    def test_parse_version(self):
        self.assertEqual(parse_version("0.2.21"), (0, 2, 21))
        self.assertEqual(parse_version("v1.0.4"), (1, 0, 4))
        self.assertEqual(parse_version("0.2.22-rc1"), (0, 2, 22, 1))
        self.assertEqual(parse_version("3"), (3,))
        self.assertEqual(parse_version(""), (0,))

    def test_is_newer_version(self):
        self.assertTrue(is_newer_version("0.2.22", "0.2.21"))
        self.assertTrue(is_newer_version("1.0.0", "0.9.9"))
        self.assertFalse(is_newer_version("0.2.21", "0.2.21"))
        self.assertFalse(is_newer_version("0.2.20", "0.2.21"))
        self.assertFalse(is_newer_version("0.1.0", "0.2.0"))

    @patch("urllib.request.urlopen")
    def test_check_for_updates_available(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.status = 200
        pypi_payload = {
            "info": {
                "version": "0.3.0",
                "package_url": "https://pypi.org/project/leai/0.3.0/",
            }
        }
        mock_response.read.return_value = json.dumps(pypi_payload).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        info = check_for_updates(current_version="0.2.21", timeout=1.0)
        self.assertIsNotNone(info)
        assert info is not None
        self.assertEqual(info.latest_version, "0.3.0")
        self.assertEqual(info.current_version, "0.2.21")

    @patch("urllib.request.urlopen")
    def test_check_for_updates_up_to_date(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.status = 200
        pypi_payload = {
            "info": {
                "version": "0.2.21",
                "package_url": "https://pypi.org/project/leai/0.2.21/",
            }
        }
        mock_response.read.return_value = json.dumps(pypi_payload).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        info = check_for_updates(current_version="0.2.21", timeout=1.0)
        self.assertIsNone(info)

    @patch("urllib.request.urlopen")
    def test_check_for_updates_network_error(self, mock_urlopen):
        mock_urlopen.side_effect = TimeoutError("Connection timed out")
        info = check_for_updates(current_version="0.2.21", timeout=1.0)
        self.assertIsNone(info)

    def test_detect_install_method(self):
        method = detect_install_method()
        self.assertIn(method, ("uv_tool", "pip", "editable"))

    @patch("subprocess.run")
    def test_run_upgrade_uv_tool(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="Upgrade completed", stderr="")
        success, msg = run_upgrade(method="uv_tool")
        self.assertTrue(success)
        self.assertIn("Upgrade completed", msg)

    @patch("subprocess.run")
    def test_run_upgrade_pip(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="Successfully installed", stderr="")
        success, msg = run_upgrade(method="pip")
        self.assertTrue(success)
        self.assertIn("Successfully installed", msg)

    def test_run_upgrade_editable(self):
        success, msg = run_upgrade(method="editable")
        self.assertFalse(success)
        self.assertIn("Editable", msg)

    @patch.dict(os.environ, {"LEAI_NO_UPDATE_CHECK": "1"}, clear=False)
    def test_prompt_and_update_disabled_via_env(self):
        res = prompt_and_update(current_version="0.2.21")
        self.assertFalse(res)

    @patch("leai.updater.check_for_updates")
    def test_prompt_and_update_user_declines(self, mock_check):
        mock_check.return_value = UpdateInfo(
            latest_version="0.3.0",
            current_version="0.2.21",
            release_notes=None,
            pypi_url="https://pypi.org/project/leai/0.3.0/",
        )
        fake_console = MagicMock()
        fake_console.input.return_value = "n"

        with patch.dict(os.environ, {}, clear=True):
            res = prompt_and_update(current_version="0.2.21", console=fake_console)
            self.assertFalse(res)

    @patch("os.execv")
    @patch("subprocess.call")
    @patch("leai.updater.run_upgrade")
    @patch("leai.updater.detect_install_method")
    @patch("leai.updater.check_for_updates")
    def test_prompt_and_update_user_accepts_restart_windows(
        self, mock_check, mock_detect, mock_upgrade, mock_subproc_call, mock_execv
    ):
        mock_check.return_value = UpdateInfo(
            latest_version="0.3.0",
            current_version="0.2.21",
            release_notes=None,
            pypi_url="https://pypi.org/project/leai/0.3.0/",
        )
        mock_detect.return_value = "uv_tool"
        mock_upgrade.return_value = (True, "Upgraded successfully")
        mock_subproc_call.return_value = 0

        fake_console = MagicMock()
        fake_console.input.return_value = "y"

        with patch.dict(os.environ, {}, clear=True), patch("sys.platform", "win32"), patch.object(
            sys, "argv", ["leai", "discover", "tests", "--verbose"]
        ):
            with self.assertRaises(SystemExit) as ctx:
                prompt_and_update(current_version="0.2.21", console=fake_console)
            self.assertEqual(ctx.exception.code, 0)
            mock_subproc_call.assert_called_once()
            call_args, _ = mock_subproc_call.call_args
            cmd = call_args[0]
            self.assertIn("-m", cmd)
            self.assertIn("leai", cmd)
            self.assertNotIn("discover", cmd)
            self.assertIn("--verbose", cmd)
            mock_execv.assert_not_called()

    @patch("os.execv")
    @patch("subprocess.call")
    @patch("leai.updater.run_upgrade")
    @patch("leai.updater.detect_install_method")
    @patch("leai.updater.check_for_updates")
    def test_prompt_and_update_user_accepts_restart_unix(
        self, mock_check, mock_detect, mock_upgrade, mock_subproc_call, mock_execv
    ):
        mock_check.return_value = UpdateInfo(
            latest_version="0.3.0",
            current_version="0.2.21",
            release_notes=None,
            pypi_url="https://pypi.org/project/leai/0.3.0/",
        )
        mock_detect.return_value = "uv_tool"
        mock_upgrade.return_value = (True, "Upgraded successfully")

        fake_console = MagicMock()
        fake_console.input.return_value = "y"

        with patch.dict(os.environ, {}, clear=True), patch("sys.platform", "linux"), patch.object(
            sys, "argv", ["leai", "discover", "tests", "chat"]
        ):
            with self.assertRaises(SystemExit) as ctx:
                prompt_and_update(current_version="0.2.21", console=fake_console)
            self.assertEqual(ctx.exception.code, 0)
            mock_execv.assert_called_once()
            execv_args, _ = mock_execv.call_args
            self.assertEqual(execv_args[0], sys.executable)
            cmd = execv_args[1]
            self.assertIn("-m", cmd)
            self.assertIn("leai", cmd)
            self.assertNotIn("discover", cmd)
            self.assertIn("chat", cmd)
            mock_subproc_call.assert_not_called()

    def test_config_update_check_field(self, tmp_path_factory=None):
        cfg = LeaiConfig()
        self.assertTrue(cfg.update_check)

        with patch.dict(os.environ, {"LEAI_NO_UPDATE_CHECK": "true"}, clear=False):
            from pathlib import Path

            p = Path("leai.yml")
            if p.exists():
                loaded = load_config(p)
                self.assertFalse(loaded.update_check)

    @patch("shutil.which", return_value="uv")
    @patch("subprocess.run")
    def test_run_upgrade_windows_entrypoint_lock_handled(self, mock_run, mock_which):
        mock_fail = MagicMock()
        mock_fail.returncode = 1
        mock_fail.stdout = "Updated leai v0.2.28 -> v0.2.29\n - leai==0.2.28\n + leai==0.2.29"
        mock_fail.stderr = (
            "error: Failed to upgrade leai\n"
            "  Caused by: Failed to install entrypoint\n"
            "  Caused by: failed to copy file ... os error 32"
        )

        mock_chk = MagicMock()
        mock_chk.returncode = 0
        mock_chk.stdout = "0.2.29\n"

        # First call is uv upgrade (fails on entrypoint), second call is version check (succeeds)
        mock_run.side_effect = [mock_fail, mock_chk]

        with patch("sys.platform", "win32"):
            success, msg = run_upgrade(method="uv_tool", target_version="0.2.29")

        self.assertTrue(success)


if __name__ == "__main__":
    unittest.main()
