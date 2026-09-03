from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from typer.testing import CliRunner

from leai.cli import app
from leai.git_ops import (
    get_git_status,
    git_pull,
    git_sync,
    is_git_installed,
    is_git_repository,
)


class TestGitOps(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo_path = Path(self.temp_dir.name)
        self.runner = CliRunner()

    def tearDown(self):
        self.temp_dir.cleanup()

    def _init_repo(self) -> None:
        """Helper to initialize a real git repo in temp dir."""
        subprocess.run(["git", "init"], cwd=str(self.repo_path), stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        subprocess.run(["git", "config", "user.name", "LEAI Tester"], cwd=str(self.repo_path), check=True)
        subprocess.run(["git", "config", "user.email", "tester@leai.dev"], cwd=str(self.repo_path), check=True)

    def test_is_git_repository(self):
        if not is_git_installed():
            self.skipTest("git binary not found")

        # Non-repo initially
        self.assertFalse(is_git_repository(cwd=self.repo_path))

        # After git init
        self._init_repo()
        self.assertTrue(is_git_repository(cwd=self.repo_path))

    def test_get_git_status_clean_and_modified(self):
        if not is_git_installed():
            self.skipTest("git binary not found")

        self._init_repo()

        # Initial commit
        dummy_file = self.repo_path / "README.md"
        dummy_file.write_text("# Test Repo\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=str(self.repo_path), check=True)
        subprocess.run(["git", "commit", "-m", "initial commit"], cwd=str(self.repo_path), check=True)

        # Status should be clean
        status_clean = get_git_status(cwd=self.repo_path, fetch=False)
        self.assertTrue(status_clean.is_repo)
        self.assertFalse(status_clean.has_uncommitted)
        self.assertEqual(len(status_clean.modified_files), 0)

        # Create untracked file and modify existing
        dummy_file.write_text("# Test Repo - Modified\n", encoding="utf-8")
        untracked = self.repo_path / "annotations.yml"
        untracked.write_text("terms: []\n", encoding="utf-8")

        status_dirty = get_git_status(cwd=self.repo_path, fetch=False)
        self.assertTrue(status_dirty.has_uncommitted)
        self.assertIn("README.md", status_dirty.modified_files)
        self.assertIn("annotations.yml", status_dirty.untracked_files)

    def test_gitlab_platform_detection(self):
        if not is_git_installed():
            self.skipTest("git binary not found")

        self._init_repo()
        subprocess.run(
            ["git", "remote", "add", "origin", "https://gitlab.empresa.gov.br/dados/leai-catalog.git"],
            cwd=str(self.repo_path),
            check=True,
        )

        status = get_git_status(cwd=self.repo_path, fetch=False)
        self.assertTrue(status.is_gitlab)
        self.assertEqual(status.platform_name, "GitLab")
        self.assertIn("gitlab", (status.remote_url or "").lower())

    def test_git_sync_flow(self):
        if not is_git_installed():
            self.skipTest("git binary not found")

        self._init_repo()

        # Initial commit
        f1 = self.repo_path / "leai.yml"
        f1.write_text("schemas: ['TEST']\n", encoding="utf-8")
        subprocess.run(["git", "add", "leai.yml"], cwd=str(self.repo_path), check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=str(self.repo_path), check=True)

        # Add docs file
        docs_dir = self.repo_path / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        doc_file = docs_dir / "INDEX.md"
        doc_file.write_text("# Schema Docs\n", encoding="utf-8")

        # Sync should stage and commit
        # (Push will fail without remote upstream, but commit should succeed)
        ok, msg = git_sync(cwd=self.repo_path, message="docs: update index")
        self.assertFalse(ok)
        self.assertIn("push", msg.lower())

        # Verify that the commit was actually created in git log
        res = subprocess.run(["git", "log", "-n", "1", "--oneline"], cwd=str(self.repo_path), stdout=subprocess.PIPE, text=True)
        self.assertIn("docs: update index", res.stdout)

    def test_git_pull_flow(self):
        if not is_git_installed():
            self.skipTest("git binary not found")

        self._init_repo()
        # Without remote, pull returns failure message gracefully
        ok, msg = git_pull(cwd=self.repo_path)
        self.assertFalse(ok)
        self.assertTrue(len(msg) > 0)

    def test_cli_git_commands(self):
        if not is_git_installed():
            self.skipTest("git binary not found")

        # Run git status on the current repo
        res = self.runner.invoke(app, ["git", "status", "--no-fetch"])
        self.assertEqual(res.exit_code, 0)
        self.assertIn("Platform", res.output)
        self.assertIn("Active Branch", res.output)
