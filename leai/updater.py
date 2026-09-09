from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rich.console import Console

PYPI_URL = "https://pypi.org/pypi/leai/json"
CHANGELOG_URL = "https://raw.githubusercontent.com/lucasbral/leai/main/documentation/contributing/changelog.md"


@dataclass
class UpdateInfo:
    latest_version: str
    current_version: str
    release_notes: str | None
    pypi_url: str


def parse_version(v_str: str) -> tuple[int, ...]:
    """Parses a version string into a comparable tuple of integers."""
    clean_str = v_str.strip().lstrip("vV")
    parts = [int(n) for n in re.findall(r"\d+", clean_str)]
    return tuple(parts) if parts else (0,)


def is_newer_version(remote: str, local: str) -> bool:
    """Returns True if the remote version is strictly newer than local."""
    return parse_version(remote) > parse_version(local)


def check_for_updates(current_version: str, timeout: float = 2.0) -> UpdateInfo | None:
    """Queries PyPI API to check if a newer version of LEAI is available.

    Fails silently and returns None in case of offline mode, timeout, or errors.
    """
    try:
        req = urllib.request.Request(
            PYPI_URL,
            headers={"User-Agent": f"leai-cli/{current_version}"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status != 200:
                return None
            data = json.loads(response.read().decode("utf-8"))

        info = data.get("info", {})
        latest_version = info.get("version")
        if not latest_version:
            return None

        if not is_newer_version(latest_version, current_version):
            return None

        release_notes = _fetch_release_notes(latest_version, timeout=1.5)

        return UpdateInfo(
            latest_version=latest_version,
            current_version=current_version,
            release_notes=release_notes,
            pypi_url=info.get("package_url") or f"https://pypi.org/project/leai/{latest_version}/",
        )
    except Exception:
        return None


def _fetch_release_notes(version: str, timeout: float = 1.5) -> str | None:
    """Attempts to fetch release notes from the changelog."""
    try:
        req = urllib.request.Request(
            CHANGELOG_URL,
            headers={"User-Agent": "leai-cli-updater"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content = resp.read().decode("utf-8")
        escaped_v = re.escape(version)
        pattern = rf"##\s*\[{escaped_v}\][^\n]*\n(.*?)(?=\n##\s*\[|\Z)"
        match = re.search(pattern, content, re.DOTALL)
        if match:
            lines = [line.strip() for line in match.group(1).strip().splitlines() if line.strip()]
            return "\n".join(lines[:6])
    except Exception:
        pass
    return None


def detect_install_method() -> str:
    """Detects whether LEAI is installed via 'uv_tool', 'pip', or 'editable'."""
    try:
        root_repo = Path(__file__).resolve().parent.parent
        if (root_repo / ".git").is_dir() and (root_repo / "pyproject.toml").is_file():
            # Running inside local clone
            return "editable"
    except Exception:
        pass

    try:
        import importlib.metadata

        dist = importlib.metadata.distribution("leai")
        direct_url = dist.read_text("direct_url.json")
        if direct_url and '"editable": true' in direct_url:
            return "editable"
    except Exception:
        pass

    # Check if running in uv tool environment
    prefix_str = sys.prefix.lower()
    exec_str = sys.executable.lower()
    if "uv" in prefix_str and "tools" in prefix_str:
        return "uv_tool"
    if "uv" in exec_str and "tools" in exec_str:
        return "uv_tool"

    # If uv is available in PATH and leai exists in uv tool list
    uv_bin = shutil.which("uv")
    if uv_bin:
        try:
            res = subprocess.run([uv_bin, "tool", "list"], capture_output=True, text=True, timeout=2.0)
            if "leai" in res.stdout:
                return "uv_tool"
        except Exception:
            pass

    return "pip"


def run_upgrade(method: str | None = None) -> tuple[bool, str]:
    """Runs the upgrade command based on the detected install method.

    Returns (success, output_or_error_message).
    """
    if method is None:
        method = detect_install_method()

    if method == "editable":
        return False, "Modo de desenvolvimento editável detectado. Para atualizar, execute 'git pull' no repositório."

    if method == "uv_tool":
        uv_bin = shutil.which("uv") or "uv"
        cmd = [uv_bin, "tool", "upgrade", "leai"]
    else:
        cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "leai"]

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=120.0)
        if res.returncode == 0:
            return True, res.stdout or "Atualização concluída com sucesso."
        return False, res.stderr or res.stdout or f"Comando falhou com código {res.returncode}"
    except Exception as exc:
        return False, str(exc)


def prompt_and_update(current_version: str, console: Console | None = None) -> bool:
    """Checks for updates and interactively prompts the user to upgrade.

    Returns True if an update was successfully applied and restarted, False otherwise.
    """
    if os.environ.get("LEAI_NO_UPDATE_CHECK", "").strip().lower() in ("1", "true", "yes"):
        return False

    update_info = check_for_updates(current_version)
    if not update_info:
        return False

    if console is None:
        from rich.console import Console

        console = Console(legacy_windows=False)

    from rich.panel import Panel

    notes_text = ""
    if update_info.release_notes:
        notes_text = f"\n\n[bold yellow]Destaques da Versao:[/bold yellow]\n{update_info.release_notes}"

    msg = (
        f"[bold white]Uma nova versao do [cyan]LEAI[/cyan] esta disponivel![/bold white]\n\n"
        f"  Versao Atual:   [bold red]{update_info.current_version}[/bold red]\n"
        f"  Nova Versao:    [bold green]{update_info.latest_version}[/bold green]"
        f"{notes_text}\n\n"
        f"[dim]Changelog: https://github.com/lucasbral/leai/releases[/dim]"
    )

    console.print()
    console.print(
        Panel(
            msg,
            title="[bold yellow][UPDATE] Atualizacao Disponivel[/bold yellow]",
            border_style="yellow",
            expand=False,
        )
    )

    # Prompt user with Y/N (defaults to Yes)
    try:
        response = console.input("[bold cyan]Deseja atualizar o LEAI agora? [Y/n]: [/bold cyan]").strip().lower()
    except (KeyboardInterrupt, EOFError):
        console.print()
        return False

    if response not in ("", "y", "yes", "s", "sim"):
        console.print("[dim]Atualizacao postergada. Prosseguindo...[/dim]\n")
        return False

    method = detect_install_method()
    if method == "editable":
        console.print("[yellow][!] Modo de desenvolvimento editavel detectado. Execute 'git pull' para atualizar o repositorio.[/yellow]\n")
        return False

    console.print()
    with console.status("[bold cyan]Baixando e instalando nova versao do LEAI...[/bold cyan]"):
        success, output = run_upgrade(method)

    if success:
        console.print(f"[bold green][OK] LEAI atualizado com sucesso para v{update_info.latest_version}![/bold green]")
        console.print("[cyan]Reiniciando o LEAI com a nova versao...[/cyan]\n")
        cmd = [sys.executable, "-m", "leai"] + sys.argv[1:]
        env = dict(os.environ, LEAI_NO_UPDATE_CHECK="1")
        if sys.platform == "win32":
            try:
                ret = subprocess.call(cmd, env=env)
                sys.exit(ret)
            except KeyboardInterrupt:
                sys.exit(0)
            except Exception:
                return True
        else:
            try:
                os.environ["LEAI_NO_UPDATE_CHECK"] = "1"
                os.execv(sys.executable, cmd)
            except Exception:
                ret = subprocess.call(cmd, env=env)
                sys.exit(ret)
        return True
    else:
        console.print(f"[bold red][ERROR] Falha na atualizacao automatica:[/bold red] {output}")
        console.print("[dim]Prosseguindo com a versao atual...[/dim]\n")
        return False
