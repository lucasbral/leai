from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from leai.clipboard import copy_to_clipboard, extract_code_blocks
from leai.config import LeaiConfig
from leai.tui.session import InteractiveTUISession


class MockLLMClient:
    def __init__(self):
        self.model = "mock-model"

    def generate_chat_with_tools(self, messages, tools=None, system_prompt=None, tool_choice_mode="auto"):
        return (
            "Here is your SQL query:\n\n```sql\nSELECT * FROM EMPLOYEES WHERE SALARY > 5000;\n```\n\nAnd here is PL/SQL:\n```plsql\nBEGIN\n  NULL;\nEND;\n```",
            [],
        )


class TestClipboard(unittest.TestCase):
    def test_extract_code_blocks(self):
        md = (
            "Here is some text:\n\n"
            "```sql\n"
            "SELECT * FROM EMPLOYEES;\n"
            "```\n\n"
            "And another one:\n"
            "```python\n"
            "print('hello world')\n"
            "x = 10\n"
            "```\n"
        )
        blocks = extract_code_blocks(md)
        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[0]["index"], 1)
        self.assertEqual(blocks[0]["language"], "sql")
        self.assertEqual(blocks[0]["code"], "SELECT * FROM EMPLOYEES;")
        self.assertEqual(blocks[0]["lines"], 1)

        self.assertEqual(blocks[1]["index"], 2)
        self.assertEqual(blocks[1]["language"], "python")
        self.assertIn("print('hello world')", blocks[1]["code"])
        self.assertEqual(blocks[1]["lines"], 2)

    def test_extract_code_blocks_empty(self):
        self.assertEqual(extract_code_blocks(""), [])
        self.assertEqual(extract_code_blocks("Just plain text with no backticks."), [])

    @patch("subprocess.Popen")
    def test_copy_to_clipboard_fallback(self, mock_popen):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate.return_value = (b"", b"")
        mock_popen.return_value = mock_proc

        ok, msg = copy_to_clipboard("test text")
        self.assertTrue(ok)
        self.assertIn("Copied", msg)

    def test_copy_empty_text(self):
        ok, msg = copy_to_clipboard("")
        self.assertFalse(ok)
        self.assertIn("Nothing to copy", msg)

    @patch("leai.tui.session.copy_to_clipboard")
    def test_tui_copy_commands(self, mock_copy):
        mock_copy.return_value = (True, "Copied")
        session = InteractiveTUISession(schemas=[], config=LeaiConfig(), client=MockLLMClient())

        # Test before any reply
        session._run_copy([])
        mock_copy.assert_not_called()

        # Simulate receiving a reply with code blocks
        session.last_ai_reply = "Check this:\n```sql\nSELECT 1 FROM DUAL;\n```\n```python\npass\n```"
        session.last_code_blocks = extract_code_blocks(session.last_ai_reply)

        # 1. /copy (copies entire reply)
        session._run_copy([])
        mock_copy.assert_called_with(session.last_ai_reply)

        # 2. /copy 1 (copies block #1)
        mock_copy.reset_mock()
        session._run_copy(["1"])
        mock_copy.assert_called_with("SELECT 1 FROM DUAL;")

        # 3. /copy 2 (copies block #2)
        mock_copy.reset_mock()
        session._run_copy(["2"])
        mock_copy.assert_called_with("pass")

        # 4. /copy sql (copies first sql block)
        mock_copy.reset_mock()
        session._run_copy(["sql"])
        mock_copy.assert_called_with("SELECT 1 FROM DUAL;")

        # 5. /copy list (does not copy, lists blocks)
        mock_copy.reset_mock()
        session._run_copy(["list"])
        mock_copy.assert_not_called()


if __name__ == "__main__":
    unittest.main()
