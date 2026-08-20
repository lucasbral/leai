from __future__ import annotations

import os
import re
import subprocess
import sys
from typing import Any


def extract_code_blocks(markdown_text: str) -> list[dict[str, Any]]:
    """Extracts all fenced code blocks from markdown text with language and line counts.

    Returns a list of dicts:
        [{"index": 1, "language": "sql", "code": "SELECT ...", "lines": 5}, ...]
    """
    if not markdown_text:
        return []

    # Matches ```lang\n...code...\n```
    pattern = re.compile(r"```([a-zA-Z0-9_\-+]*)\r?\n([\s\S]*?)```")
    matches = list(pattern.finditer(markdown_text))

    blocks: list[dict[str, Any]] = []
    for i, match in enumerate(matches, 1):
        lang = match.group(1).strip().lower() or "text"
        code = match.group(2).strip()
        lines = len(code.splitlines()) if code else 0
        blocks.append(
            {
                "index": i,
                "language": lang,
                "code": code,
                "lines": lines,
            }
        )
    return blocks


def copy_to_clipboard(text: str) -> tuple[bool, str]:
    """Copies the given text to the operating system clipboard using native commands or fallback.

    Returns:
        (success: bool, message: str)
    """
    if not text:
        return False, "Nothing to copy (text is empty)."

    # 1. Try pyperclip if installed
    try:
        import pyperclip  # type: ignore

        pyperclip.copy(text)
        return True, f"Copied {len(text)} characters to clipboard."
    except Exception:
        pass

    # 2. Windows (clip.exe or PowerShell)
    if sys.platform == "win32" or os.name == "nt":
        try:
            # clip.exe expects Windows-1252 or UTF-16
            proc = subprocess.Popen(["clip.exe"], stdin=subprocess.PIPE, shell=True)
            proc.communicate(input=text.encode("utf-16le"))
            if proc.returncode == 0:
                return True, f"Copied {len(text)} characters to clipboard (via clip.exe)."
        except Exception:
            pass

        try:
            # Fallback to PowerShell Set-Clipboard
            ps_cmd = f"Set-Clipboard -Value @'\n{text}\n'@"
            proc = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True)
            if proc.returncode == 0:
                return True, f"Copied {len(text)} characters to clipboard (via PowerShell)."
        except Exception as exc:
            return False, f"Failed to copy to clipboard on Windows: {exc}"

    # 3. macOS (pbcopy)
    elif sys.platform == "darwin":
        try:
            proc = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
            proc.communicate(input=text.encode("utf-8"))
            if proc.returncode == 0:
                return True, f"Copied {len(text)} characters to clipboard (via pbcopy)."
        except Exception as exc:
            return False, f"Failed to copy to clipboard on macOS: {exc}"

    # 4. Linux / Unix (wl-copy, xclip, xsel)
    else:
        # Try Wayland first
        try:
            proc = subprocess.Popen(["wl-copy"], stdin=subprocess.PIPE)
            proc.communicate(input=text.encode("utf-8"))
            if proc.returncode == 0:
                return True, f"Copied {len(text)} characters to clipboard (via wl-copy)."
        except Exception:
            pass

        # Try xclip (X11)
        try:
            proc = subprocess.Popen(["xclip", "-selection", "clipboard"], stdin=subprocess.PIPE)
            proc.communicate(input=text.encode("utf-8"))
            if proc.returncode == 0:
                return True, f"Copied {len(text)} characters to clipboard (via xclip)."
        except Exception:
            pass

        # Try xsel (X11)
        try:
            proc = subprocess.Popen(["xsel", "--clipboard", "--input"], stdin=subprocess.PIPE)
            proc.communicate(input=text.encode("utf-8"))
            if proc.returncode == 0:
                return True, f"Copied {len(text)} characters to clipboard (via xsel)."
        except Exception as exc:
            return False, f"Failed to copy to clipboard on Linux (install xclip or wl-copy): {exc}"

    return False, "No supported clipboard utility found on this operating system."
