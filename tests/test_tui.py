from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document

from leai.config import LeaiConfig
from leai.models import (
    CodeObjectMeta,
    ColumnMeta,
    SchemaMetadata,
    TableMeta,
    ViewMeta,
)
from leai.tui.completer import LeaiCompleter
from leai.tui.session import InteractiveTUISession


class TuiUnitTests(unittest.TestCase):
    def setUp(self):
        self.schema = SchemaMetadata(
            schema_name="HR",
            tables=[
                TableMeta(
                    name="EMPLOYEES",
                    columns=[
                        ColumnMeta(name="ID", data_type="NUMBER", nullable=False),
                        ColumnMeta(name="NAME", data_type="VARCHAR2(100)", nullable=False),
                    ],
                    primary_keys=["ID"],
                    comment="Table of employees",
                ),
                TableMeta(
                    name="DEPARTMENTS",
                    columns=[ColumnMeta(name="ID", data_type="NUMBER", nullable=False)],
                    primary_keys=["ID"],
                ),
            ],
            views=[
                ViewMeta(name="V_EMPLOYEES_SUMMARY", columns=[ColumnMeta(name="ID", data_type="NUMBER", nullable=False)])
            ],
            code_objects=[
                CodeObjectMeta(name="PKG_PAYROLL", object_type="PACKAGE", source="PACKAGE BODY PKG_PAYROLL IS ... END;")
            ],
        )
        self.config = LeaiConfig(
            schemas=["HR"],
            rawPath=Path("./raw"),
            annotationsPath=Path("./annotations"),
            docPath=Path("./docs"),
        )
        self.mock_client = MagicMock()
        self.mock_client.model = "gpt-4o"
        self.mock_client.generate_text.return_value = "Test response from AI."

    def test_completer_slash_commands(self):
        completer = LeaiCompleter([self.schema])
        doc = Document(text="/tr", cursor_position=3)
        completions = list(completer.get_completions(doc, CompleteEvent()))
        texts = [c.text for c in completions]
        self.assertIn("/trace", texts)

    def test_completer_trace_argument(self):
        completer = LeaiCompleter([self.schema])
        doc = Document(text="/trace EMP", cursor_position=10)
        completions = list(completer.get_completions(doc, CompleteEvent()))
        texts = [c.text for c in completions]
        self.assertIn("EMPLOYEES", texts)

    def test_completer_model_argument(self):
        completer = LeaiCompleter([self.schema])
        doc = Document(text="/model gem", cursor_position=10)
        completions = list(completer.get_completions(doc, CompleteEvent()))
        texts = [c.text for c in completions]
        self.assertIn("gemini", texts)

    def test_completer_at_mentions(self):
        completer = LeaiCompleter([self.schema])
        doc = Document(text="Tell me about @DEP", cursor_position=18)
        completions = list(completer.get_completions(doc, CompleteEvent()))
        texts = [c.text for c in completions]
        self.assertIn("@DEPARTMENTS", texts)

    def test_session_toolbar_rendering(self):
        session = InteractiveTUISession([self.schema], self.config, self.mock_client, provider_name="openai")
        toolbar = session._get_bottom_toolbar()
        self.assertIn("LEAI Copilot", toolbar.value)
        self.assertIn("HR", toolbar.value)
        self.assertIn("gpt-4o", toolbar.value)

    def test_session_slash_help(self):
        session = InteractiveTUISession([self.schema], self.config, self.mock_client)
        res = session.handle_slash_command("/help")
        self.assertTrue(res)

    def test_session_slash_tables(self):
        session = InteractiveTUISession([self.schema], self.config, self.mock_client)
        res = session.handle_slash_command("/tables")
        self.assertTrue(res)

    def test_session_slash_schema(self):
        session = InteractiveTUISession([self.schema], self.config, self.mock_client)
        res = session.handle_slash_command("/schema")
        self.assertTrue(res)

    def test_session_slash_changes(self):
        session = InteractiveTUISession([self.schema], self.config, self.mock_client)
        res = session.handle_slash_command("/changes 7")
        self.assertTrue(res)

    def test_session_slash_clear(self):
        session = InteractiveTUISession([self.schema], self.config, self.mock_client)
        session.session.messages.append({"role": "user", "content": "hello"})
        res = session.handle_slash_command("/clear")
        self.assertTrue(res)
        self.assertEqual(len(session.session.messages), 0)

    def test_session_slash_trace(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.config.docPath = Path(tmpdir) / "docs"
            self.config.annotationsPath = Path(tmpdir) / "annotations"
            session = InteractiveTUISession([self.schema], self.config, self.mock_client)
            res = session.handle_slash_command("/trace EMPLOYEES")
            self.assertTrue(res)
            self.assertTrue((self.config.docPath / "dossiers" / "EMPLOYEES.md").exists())

    def test_session_slash_save(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            save_file = Path(tmpdir) / "transcript.md"
            session = InteractiveTUISession([self.schema], self.config, self.mock_client)
            session.session.messages.append({"role": "user", "content": "What is EMPLOYEES?"})
            session.session.messages.append({"role": "assistant", "content": "EMPLOYEES is a table."})
            res = session.handle_slash_command(f"/save {save_file}")
            self.assertTrue(res)
            self.assertTrue(save_file.exists())

    @patch("leai.tui.session.get_llm_client")
    def test_session_slash_model(self, mock_get_client):
        mock_gemini = MagicMock()
        mock_gemini.model = "gemini-1.5-flash"
        mock_get_client.return_value = mock_gemini

        session = InteractiveTUISession([self.schema], self.config, self.mock_client, provider_name="openai")
        res = session.handle_slash_command("/model gemini gemini-1.5-flash")
        self.assertTrue(res)
        self.assertEqual(session.provider_name, "gemini")
        self.assertEqual(session.client.model, "gemini-1.5-flash")

    def test_session_slash_exit(self):
        session = InteractiveTUISession([self.schema], self.config, self.mock_client)
        res = session.handle_slash_command("/exit")
        self.assertFalse(res)


if __name__ == "__main__":
    unittest.main()
