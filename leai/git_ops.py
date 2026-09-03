from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class GitStatusInfo:
    is_repo: bool = False
    branch: str | None = None
    remote_name: str = "origin"
    remote_url: str | None = None
    is_gitlab: bool = False
    ahead: int = 0
    behind: int = 0
    modified_files: list[str] = field(default_factory=list)
    untracked_files: list[str] = field(default_factory=list)
    has_uncommitted: bool = False
    error: str | None = None

    @property
    def platform_name(self) -> str:
        if self.is_gitlab:
            return "GitLab"
        if self.remote_url and "github" in self.remote_url.lower():
            return "GitHub"
        return "Git"


def is_git_installed() -> bool:
    """Checks if git binary is available on the system PATH."""
    return shutil.which("git") is not None


def run_git_command(args: list[str], cwd: Path | None = None, timeout: float = 10.0) -> tuple[int, str, str]:
    """Safely runs a git command with timeout and graceful error handling."""
    if not is_git_installed():
        return 127, "", "Git binary not found in PATH."

    target_dir = str(cwd) if cwd else None
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=target_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except subprocess.TimeoutExpired:
        return 124, "", f"Git command timed out after {timeout}s."
    except Exception as exc:
        return 1, "", str(exc)


def is_git_repository(cwd: Path | None = None) -> bool:
    """Checks if the given directory is inside a Git working tree."""
    code, out, _ = run_git_command(["rev-parse", "--is-inside-work-tree"], cwd=cwd, timeout=3.0)
    return code == 0 and out == "true"


def get_git_status(cwd: Path | None = None, fetch: bool = False, timeout: float = 3.0) -> GitStatusInfo:
    """Collects repository status, branch, remote sync info, and working tree changes."""
    if not is_git_repository(cwd=cwd):
        return GitStatusInfo(is_repo=False)

    info = GitStatusInfo(is_repo=True)

    # 1. Current Branch
    code, branch, _ = run_git_command(["branch", "--show-current"], cwd=cwd, timeout=timeout)
    if code == 0 and branch:
        info.branch = branch
    else:
        # Detached HEAD check
        code_head, head_rev, _ = run_git_command(["rev-parse", "--short", "HEAD"], cwd=cwd, timeout=timeout)
        info.branch = head_rev if code_head == 0 else "unknown"

    # 2. Remote URL and Platform Detection
    code, remote_url, _ = run_git_command(["config", "--get", f"remote.{info.remote_name}.url"], cwd=cwd, timeout=timeout)
    if code == 0 and remote_url:
        info.remote_url = remote_url
        if "gitlab" in remote_url.lower():
            info.is_gitlab = True

    # 3. Optional remote fetch to detect behind/ahead commits
    if fetch:
        run_git_command(["fetch", "-q", info.remote_name], cwd=cwd, timeout=timeout)

    # 4. Ahead / Behind calculation against upstream
    code, counts, _ = run_git_command(["rev-list", "--left-right", "--count", "HEAD...@{u}"], cwd=cwd, timeout=timeout)
    if code == 0 and counts:
        parts = counts.split()
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            info.ahead = int(parts[0])
            info.behind = int(parts[1])

    # 5. Modified and untracked files
    code, status_out, _ = run_git_command(["status", "--porcelain"], cwd=cwd, timeout=timeout)
    if code == 0 and status_out:
        for line in status_out.splitlines():
            if not line or len(line) < 3:
                continue
            status_code = line[:2].strip()
            filename = line[2:].strip()
            if status_code == "??":
                info.untracked_files.append(filename)
            else:
                info.modified_files.append(filename)
        info.has_uncommitted = bool(info.modified_files or info.untracked_files)

    return info


def git_pull(cwd: Path | None = None, remote: str = "origin", branch: str | None = None) -> tuple[bool, str]:
    """Runs git pull to fetch and integrate remote changes."""
    args = ["pull"]
    if remote:
        args.append(remote)
    if branch:
        args.append(branch)

    code, out, err = run_git_command(args, cwd=cwd, timeout=20.0)
    if code == 0:
        return True, out or "Already up to date."
    return False, err or out or "Git pull failed."


def git_sync(
    cwd: Path | None = None,
    message: str | None = None,
    paths: list[str] | None = None,
) -> tuple[bool, str]:
    """Stages metadata files, commits them, and pushes to remote repository."""
    if not is_git_repository(cwd=cwd):
        return False, "Not inside a Git repository."

    target_paths = paths or ["annotations", "docs", "raw", "leai.yml"]
    existing_paths = []
    base_dir = cwd or Path.cwd()

    for p in target_paths:
        if (base_dir / p).exists():
            existing_paths.append(p)

    if not existing_paths:
        existing_paths = ["."]

    # 1. Stage target files
    add_code, add_out, add_err = run_git_command(["add", *existing_paths], cwd=cwd, timeout=10.0)
    if add_code != 0:
        return False, f"Failed to stage files: {add_err or add_out}"

    # 2. Check if anything is staged
    diff_code, diff_out, _ = run_git_command(["diff", "--cached", "--name-only"], cwd=cwd, timeout=5.0)
    if diff_code == 0 and not diff_out.strip():
        return True, "No local metadata changes to commit."

    # 3. Commit
    commit_msg = message or "docs(leai): sync database metadata, annotations and glossary [skip ci]"
    commit_code, commit_out, commit_err = run_git_command(["commit", "-m", commit_msg], cwd=cwd, timeout=10.0)
    if commit_code != 0:
        return False, f"Git commit failed: {commit_err or commit_out}"

    # 4. Push to remote
    push_code, push_out, push_err = run_git_command(["push"], cwd=cwd, timeout=25.0)
    if push_code != 0:
        return False, f"Git push failed: {push_err or push_out}"

    return True, commit_out or "Changes successfully pushed to remote repository."
