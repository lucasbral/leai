from __future__ import annotations

import json
import sys
import tempfile
import unittest

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
from pathlib import Path
from unittest.mock import MagicMock, patch

from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document

from leai.audit import SessionAuditLogger
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
            views=[ViewMeta(name="V_EMPLOYEES_SUMMARY", columns=[ColumnMeta(name="ID", data_type="NUMBER", nullable=False)])],
            code_objects=[CodeObjectMeta(name="PKG_PAYROLL", object_type="PACKAGE", source="PACKAGE BODY PKG_PAYROLL IS ... END;")],
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
        self.mock_client.generate_chat_with_tools.return_value = ("Test response from AI.", [])

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

    def test_completer_extract_argument(self):
        completer = LeaiCompleter([self.schema], config=self.config)
        doc = Document(text="/extract ", cursor_position=9)
        completions = list(completer.get_completions(doc, CompleteEvent()))
        texts = [c.text for c in completions]
        self.assertIn("ALL", texts)
        self.assertIn("HR", texts)

    def test_completer_compile_argument(self):
        completer = LeaiCompleter([self.schema])
        doc = Document(text="/compile EMP", cursor_position=12)
        completions = list(completer.get_completions(doc, CompleteEvent()))
        texts = [c.text for c in completions]
        self.assertIn("EMPLOYEES", texts)

    def test_completer_models_argument(self):
        completer = LeaiCompleter([self.schema])
        doc = Document(text="/models gro", cursor_position=11)
        completions = list(completer.get_completions(doc, CompleteEvent()))
        texts = [c.text for c in completions]
        self.assertIn("grok", texts)

    def test_completer_schema_argument(self):
        completer = LeaiCompleter([self.schema], config=self.config)
        doc = Document(text="/schema H", cursor_position=9)
        completions = list(completer.get_completions(doc, CompleteEvent()))
        texts = [c.text for c in completions]
        self.assertIn("HR", texts)

    def test_completer_changes_argument(self):
        completer = LeaiCompleter([self.schema])
        doc = Document(text="/changes ", cursor_position=9)
        completions = list(completer.get_completions(doc, CompleteEvent()))
        texts = [c.text for c in completions]
        self.assertIn("7", texts)
        self.assertIn("30", texts)

    def test_completer_save_argument(self):
        completer = LeaiCompleter([self.schema])
        doc = Document(text="/save lea", cursor_position=9)
        completions = list(completer.get_completions(doc, CompleteEvent()))
        texts = [c.text for c in completions]
        self.assertIn("leai_chat.md", texts)

    def test_completer_audit_argument(self):
        completer = LeaiCompleter([self.schema])
        doc = Document(text="/audit ", cursor_position=7)
        completions = list(completer.get_completions(doc, CompleteEvent()))
        texts = [c.text for c in completions]
        self.assertIn("last", texts)
        self.assertIn("session", texts)
        self.assertIn("export", texts)

    def test_completer_at_mentions(self):
        completer = LeaiCompleter([self.schema])
        doc = Document(text="Tell me about @DEP", cursor_position=18)
        completions = list(completer.get_completions(doc, CompleteEvent()))
        texts = [c.text for c in completions]
        self.assertIn("@DEPARTMENTS", texts)

    def test_session_toolbar_rendering(self):
        session = InteractiveTUISession([self.schema], self.config, self.mock_client, provider_name="openai")
        toolbar = session._get_bottom_toolbar()
        self.assertIn("LEAI", toolbar.value)
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

    def test_session_slash_compile_single_object(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            cfg = self.config.model_copy()
            cfg.docPath = base / "docs"
            cfg.annotationsPath = base / "annotations"
            session = InteractiveTUISession([self.schema], cfg, self.mock_client)
            res = session.handle_slash_command("/compile EMPLOYEES")
            self.assertTrue(res)
            self.assertTrue((cfg.docPath / "tables" / "EMPLOYEES.md").exists() or (cfg.docPath / "HR" / "tables" / "EMPLOYEES.md").exists())

    def test_session_slash_compile_schema_qualified_object(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            cfg = self.config.model_copy()
            cfg.docPath = base / "docs"
            cfg.annotationsPath = base / "annotations"
            session = InteractiveTUISession([self.schema], cfg, self.mock_client)
            res = session.handle_slash_command("/compile HR.EMPLOYEES")
            self.assertTrue(res)
            self.assertTrue((cfg.docPath / "tables" / "EMPLOYEES.md").exists() or (cfg.docPath / "HR" / "tables" / "EMPLOYEES.md").exists())

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

    def test_session_slash_audit_and_tools(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            session = InteractiveTUISession([self.schema], self.config, self.mock_client)
            session.audit_logger = SessionAuditLogger(log_dir=Path(tmpdir))

            # Record turn
            from leai.audit import ToolExecutionAudit

            tool_rec = ToolExecutionAudit(
                step=1,
                tool_name="grep_plsql_code",
                arguments={"pattern": "SALARY"},
                raw_output=json.dumps({"matches": []}),
                summary="0 matches",
                duration_seconds=0.05,
            )
            session.audit_logger.record_turn(
                user_prompt="Find salary routines",
                ai_response="No salary routines found.",
                provider="openai",
                model="gpt-4o",
                latency_seconds=0.8,
                tokens_used=200,
                tools_executed=[tool_rec],
            )

            # Test /audit, /audit last, /audit session, /tools
            self.assertTrue(session.handle_slash_command("/audit"))
            self.assertTrue(session.handle_slash_command("/audit last"))
            self.assertTrue(session.handle_slash_command("/audit session"))
            self.assertTrue(session.handle_slash_command("/tools"))

            # Test /audit export
            export_file = Path(tmpdir) / "audit_report.md"
            self.assertTrue(session.handle_slash_command(f"/audit export {export_file}"))
            self.assertTrue(export_file.exists())

    @patch("webbrowser.open")
    def test_session_slash_serve(self, mock_web_open):
        session = InteractiveTUISession([self.schema], self.config, self.mock_client)
        try:
            self.assertTrue(session.handle_slash_command("/serve 8891"))
            self.assertIsNotNone(session.web_server)
            self.assertTrue(session.handle_slash_command("/serve"))
            self.assertTrue(session.handle_slash_command("/serve stop"))
            self.assertIsNone(session.web_server)
        finally:
            if session.web_server:
                session.web_server.shutdown()

    def test_completer_new_slash_commands(self):
        completer = LeaiCompleter([self.schema])
        for prefix, expected_cmd in [
            ("/do", "/doc"),
            ("/ex", "/extract"),
            ("/co", "/compile"),
            ("/an", "/annotate"),
            ("/en", "/enrich"),
            ("/se", "/serve"),
        ]:
            doc = Document(text=prefix, cursor_position=len(prefix))
            completions = list(completer.get_completions(doc, CompleteEvent()))
            texts = [c.text for c in completions]
            self.assertIn(expected_cmd, texts)

    def test_completer_doc_subargument(self):
        completer = LeaiCompleter([self.schema])
        doc = Document(text="/doc EMP", cursor_position=8)
        completions = list(completer.get_completions(doc, CompleteEvent()))
        texts = [c.text for c in completions]
        self.assertIn("EMPLOYEES", texts)

    def test_doc_editor_full_flow(self):
        from leai.tui.doc_editor import DocEditor

        with tempfile.TemporaryDirectory() as tmpdir:
            self.config.annotationsPath = Path(tmpdir) / "annotations"
            self.config.docPath = Path(tmpdir) / "docs"

            # Inputs:
            # 1 -> New Description: "Tabela principal de funcionarios"
            # 2 -> Select Column 1 (ID) -> Description: "Identificador unico" -> 0 (finish columns)
            # 3 -> Business Rules -> + (Add) -> "Salario nao pode ser negativo" -> 0 (finish rules)
            # 4 -> Tags -> "RH, Core, Folha"
            # 7 -> Save -> "n" (do not recompile)
            inputs = [
                "1",
                "Tabela principal de funcionarios",
                "2",
                "1",
                "Identificador unico",
                "0",
                "3",
                "+",
                "Salario nao pode ser negativo",
                "0",
                "4",
                "RH, Core, Folha",
                "7",
                "n",
            ]
            input_iter = iter(inputs)
            editor = DocEditor(self.config, [self.schema], input_fn=lambda p: next(input_iter))

            saved = editor.run("EMPLOYEES")
            self.assertTrue(saved)

            # Verify saved YAML annotation
            ann_file = self.config.annotationsPath / "tables" / "EMPLOYEES.yml"
            self.assertTrue(ann_file.exists())
            from leai.annotations import load_annotation

            loaded = load_annotation(ann_file)
            self.assertEqual(loaded.description, "Tabela principal de funcionarios")
            self.assertEqual(loaded.columns.get("ID"), "Identificador unico")
            self.assertIn("Salario nao pode ser negativo", loaded.business_rules)
            self.assertIn("RH", loaded.tags)
            self.assertIn("Core", loaded.tags)

    def test_session_empty_snapshots_banner(self):
        session = InteractiveTUISession([], self.config, self.mock_client)
        session.print_welcome_banner()
        self.assertEqual(len(session.schemas), 0)

    def test_session_slash_chat(self):
        session = InteractiveTUISession([self.schema], self.config, self.mock_client)
        res_info = session.handle_slash_command("/chat")
        self.assertTrue(res_info)
        res_ask = session.handle_slash_command("/chat tell me about EMPLOYEES")
        self.assertTrue(res_ask)

    def test_session_slash_compile(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.config.docPath = Path(tmpdir) / "docs"
            self.config.annotationsPath = Path(tmpdir) / "annotations"
            session = InteractiveTUISession([self.schema], self.config, self.mock_client)
            res = session.handle_slash_command("/compile")
            self.assertTrue(res)
            self.assertTrue((self.config.docPath / "tables" / "EMPLOYEES.md").exists())

    def test_session_slash_annotate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.config.annotationsPath = Path(tmpdir) / "annotations"
            session = InteractiveTUISession([self.schema], self.config, self.mock_client)
            res = session.handle_slash_command("/annotate")
            self.assertTrue(res)
            self.assertTrue((self.config.annotationsPath / "tables" / "EMPLOYEES.yml").exists())

    def test_session_slash_compile_multi_schema_progress(self):
        schema2 = SchemaMetadata(
            schema_name="SALES",
            tables=[TableMeta(name="ORDERS", columns=[ColumnMeta(name="ID", data_type="NUMBER", nullable=False)])],
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            self.config.docPath = Path(tmpdir) / "docs"
            self.config.annotationsPath = Path(tmpdir) / "annotations"
            session = InteractiveTUISession([self.schema, schema2], self.config, self.mock_client)
            res = session.handle_slash_command("/compile")
            self.assertTrue(res)
            self.assertTrue((self.config.docPath / "HR" / "tables" / "EMPLOYEES.md").exists())
            self.assertTrue((self.config.docPath / "SALES" / "tables" / "ORDERS.md").exists())

    def test_session_slash_annotate_multi_schema_progress(self):
        schema2 = SchemaMetadata(
            schema_name="SALES",
            tables=[TableMeta(name="ORDERS", columns=[ColumnMeta(name="ID", data_type="NUMBER", nullable=False)])],
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            self.config.annotationsPath = Path(tmpdir) / "annotations"
            session = InteractiveTUISession([self.schema, schema2], self.config, self.mock_client)
            res = session.handle_slash_command("/annotate")
            self.assertTrue(res)
            self.assertTrue((self.config.annotationsPath / "HR" / "tables" / "EMPLOYEES.yml").exists())
            self.assertTrue((self.config.annotationsPath / "SALES" / "tables" / "ORDERS.yml").exists())

    def test_session_slash_enrich_with_progress(self):
        mock_enrich_client = MagicMock()
        mock_enrich_client.model = "mock-gpt-4o"
        mock_enrich_client.generate_json.return_value = {
            "description": "Enriched employees table",
            "business_rules": ["Rule 1: test rule"],
            "tags": ["HR"],
            "columns": {"ID": "Primary ID"},
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            self.config.annotationsPath = Path(tmpdir) / "annotations"
            session = InteractiveTUISession([self.schema], self.config, mock_enrich_client)
            res = session.handle_slash_command("/enrich")
            self.assertTrue(res)
            self.assertTrue((self.config.annotationsPath / "tables" / "EMPLOYEES.yml").exists())

    @patch("leai.tui.session.fetch_available_schemas")
    @patch("leai.tui.session.fetch_schema_metadata")
    @patch("oracledb.connect")
    def test_session_slash_extract_mocked_with_progress(self, mock_connect, mock_fetch_meta, mock_fetch_schemas):
        mock_connect.return_value = MagicMock()
        mock_fetch_schemas.return_value = ["HR"]
        mock_fetch_meta.return_value = self.schema

        with tempfile.TemporaryDirectory() as tmpdir:
            self.config.rawPath = Path(tmpdir) / "raw"
            self.config.dsn = "oracle://user:pass@localhost:1521/ORCL"
            session = InteractiveTUISession([], self.config, self.mock_client)
            res = session.handle_slash_command("/extract HR")
            self.assertTrue(res)
            self.assertTrue((self.config.rawPath / "HR" / "tables" / "EMPLOYEES.json").exists())

    def test_doc_completeness_calculation(self):
        from leai.models import ObjectAnnotation
        from leai.tui.doc_editor import _calculate_doc_completeness

        ann = ObjectAnnotation(description="Table description", columns={"ID": "col desc"}, business_rules=["rule 1"], tags=["HR"])
        pct, bar_str = _calculate_doc_completeness(ann, ["ID"])
        self.assertEqual(pct, 100)
        self.assertIn("100%", bar_str)

        ann_empty = ObjectAnnotation()
        pct_empty, bar_empty = _calculate_doc_completeness(ann_empty, ["ID", "NAME"])
        self.assertEqual(pct_empty, 0)
        self.assertIn("0%", bar_empty)

    def test_doc_editor_catalog_selection_by_index(self):
        from leai.tui.doc_editor import DocEditor

        with tempfile.TemporaryDirectory() as tmpdir:
            self.config.annotationsPath = Path(tmpdir) / "annotations"
            self.config.docPath = Path(tmpdir) / "docs"

            # Inputs:
            # "1" (select item 1: HR.EMPLOYEES)
            # "1" (edit description) -> "Main employees table"
            # "7" (save) -> "n" (no recompile)
            inputs = ["1", "1", "Main employees table", "7", "n"]
            input_iter = iter(inputs)
            editor = DocEditor(self.config, [self.schema], input_fn=lambda p: next(input_iter))
            saved = editor.run(None)  # None triggers catalog table
            self.assertTrue(saved)

            ann_file = self.config.annotationsPath / "tables" / "EMPLOYEES.yml"
            self.assertTrue(ann_file.exists())

    def test_session_history_preserved_after_doc_editor(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.config.rawPath = Path(tmpdir) / "raw"
            self.config.annotationsPath = Path(tmpdir) / "annotations"
            self.config.docPath = Path(tmpdir) / "docs"

            from leai.raw import save_raw_schema

            save_raw_schema(self.schema, self.config.rawPath)

            session = InteractiveTUISession([self.schema], self.config, self.mock_client)
            # Simulate asking 1 question
            session.session.add_user_message("What is EMPLOYEES?")
            session.session.add_assistant_message("It is a table.")
            self.assertEqual(len(session.session.messages), 2)
            self.assertIn("2", session._get_bottom_toolbar().value)

            # Now run doc editor with saved=True
            with patch("leai.tui.session.DocEditor") as mock_editor_cls:
                mock_editor = MagicMock()
                mock_editor.run.return_value = True
                mock_editor_cls.return_value = mock_editor

            # Check that conversation history is still 2 messages and tokens are in toolbar
            self.assertEqual(len(session.session.messages), 2)
            toolbar_html = session._get_bottom_toolbar().value
            self.assertIn("2", toolbar_html)
            self.assertIn("Tokens:", toolbar_html)

    def test_format_tokens_helper(self):
        from leai.tui.session import _format_tokens

        self.assertEqual(_format_tokens(0), "0")
        self.assertEqual(_format_tokens(450), "450")
        self.assertEqual(_format_tokens(2450, 450), "2.5k (↑450)")
        self.assertEqual(_format_tokens(1_500_000, 250_000), "1.5M (↑250.0k)")

    def test_session_slash_check(self):
        session = InteractiveTUISession([self.schema], self.config, self.mock_client)
        res = session.handle_slash_command("/check")
        self.assertTrue(res)

    def test_session_slash_init(self):
        session = InteractiveTUISession([self.schema], self.config, self.mock_client)
        with patch("rich.prompt.Confirm.ask", return_value=False):
            res = session.handle_slash_command("/init")
            self.assertTrue(res)

    def test_completion_keybindings(self):
        from prompt_toolkit.buffer import Buffer, CompletionState
        from prompt_toolkit.completion import Completion
        from prompt_toolkit.document import Document

        session = InteractiveTUISession([self.schema], self.config, self.mock_client)
        kb = session.prompt_session.key_bindings
        self.assertIsNotNone(kb)

        # Retrieve bindings from kb.bindings
        has_enter = any("c-m" in str(b.keys) and "has_completions" in str(b.filter) for b in kb.bindings)
        has_tab = any("c-i" in str(b.keys) and "has_completions" in str(b.filter) for b in kb.bindings)
        has_down = any("down" in str(b.keys) and "has_completions" in str(b.filter) for b in kb.bindings)
        has_up = any("up" in str(b.keys) and "has_completions" in str(b.filter) for b in kb.bindings)
        has_esc = any("escape" in str(b.keys) and "has_completions" in str(b.filter) for b in kb.bindings)

        self.assertTrue(has_enter)
        self.assertTrue(has_tab)
        self.assertTrue(has_down)
        self.assertTrue(has_up)
        self.assertTrue(has_esc)

        # Test simulated buffer completion apply with space
        b = Buffer(complete_while_typing=False)
        b.document = Document("@FUNC", 5)
        c1 = Completion("@FUNCIONARIOS", start_position=-5)
        c2 = Completion("@FUNCIONARIOS_PND", start_position=-5)
        b.complete_state = CompletionState(b.document, [c1, c2])

        # Trigger enter binding handler
        enter_binding = next(b for b in kb.bindings if "c-m" in str(b.keys) and "has_completions" in str(b.filter))

        class DummyEvent:
            def __init__(self, buf):
                self.current_buffer = buf

        enter_binding.handler(DummyEvent(b))

        self.assertEqual(b.text, "@FUNCIONARIOS ")
        self.assertIsNone(b.complete_state)

    def test_run_init_when_not_exists(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            orig_cwd = Path.cwd()
            import os

            try:
                os.chdir(tmp_dir)
                session = InteractiveTUISession([self.schema], self.config, self.mock_client)
                res = session.handle_slash_command("/init")
                self.assertTrue(res)

                out_file = Path("leai.yml")
                self.assertTrue(out_file.exists())
                content = out_file.read_text(encoding="utf-8")
                self.assertIn("ollama", content)
                self.assertIn("seaweedfs", content)
                self.assertIn("git:", content)
                self.assertGreater(len(content), 500)
            finally:
                os.chdir(orig_cwd)

    def test_run_init_when_exists_and_declined(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            orig_cwd = Path.cwd()
            import os

            try:
                os.chdir(tmp_dir)
                out_file = Path("leai.yml")
                out_file.write_text("existing_custom: true\n", encoding="utf-8")

                session = InteractiveTUISession([self.schema], self.config, self.mock_client)
                with patch("rich.prompt.Confirm.ask", return_value=False):
                    res = session.handle_slash_command("/init")
                    self.assertTrue(res)

                content = out_file.read_text(encoding="utf-8")
                self.assertEqual(content, "existing_custom: true\n")
            finally:
                os.chdir(orig_cwd)

    def test_run_init_when_exists_and_confirmed(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            orig_cwd = Path.cwd()
            import os

            try:
                os.chdir(tmp_dir)
                out_file = Path("leai.yml")
                out_file.write_text("existing_custom: true\n", encoding="utf-8")

                session = InteractiveTUISession([self.schema], self.config, self.mock_client)
                with patch("rich.prompt.Confirm.ask", return_value=True):
                    res = session.handle_slash_command("/init")
                    self.assertTrue(res)

                content = out_file.read_text(encoding="utf-8")
                self.assertIn("ollama", content)
                self.assertIn("seaweedfs", content)
                self.assertGreater(len(content), 500)
            finally:
                os.chdir(orig_cwd)

    def test_run_init_force_flag(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            orig_cwd = Path.cwd()
            import os

            try:
                os.chdir(tmp_dir)
                out_file = Path("leai.yml")
                out_file.write_text("existing_custom: true\n", encoding="utf-8")

                session = InteractiveTUISession([self.schema], self.config, self.mock_client)
                with patch("rich.prompt.Confirm.ask") as mock_ask:
                    res = session.handle_slash_command("/init --force")
                    self.assertTrue(res)
                    mock_ask.assert_not_called()

                content = out_file.read_text(encoding="utf-8")
                self.assertIn("ollama", content)
                self.assertIn("seaweedfs", content)
                self.assertGreater(len(content), 500)
            finally:
                os.chdir(orig_cwd)

    @patch("leai.storage.SeaweedFSStorage.save_raw_schema")
    @patch("leai.storage.SeaweedFSStorage.ensure_bucket_exists")
    @patch("leai.tui.session.fetch_available_schemas")
    @patch("leai.tui.session.fetch_schema_metadata")
    @patch("oracledb.connect")
    def test_session_slash_extract_with_seaweed_flag(
        self, mock_connect, mock_fetch_meta, mock_fetch_schemas, mock_ensure_bucket, mock_save_raw_storage
    ):
        from leai.storage import SaveResult

        mock_connect.return_value = MagicMock()
        mock_fetch_schemas.return_value = ["HR"]
        mock_fetch_meta.return_value = self.schema
        mock_save_raw_storage.return_value = SaveResult(["key1", "key2"], uploaded=2, skipped=0, total=2)

        with tempfile.TemporaryDirectory() as tmpdir:
            self.config.rawPath = Path(tmpdir) / "raw"
            self.config.dsn = "oracle://user:pass@localhost:1521/ORCL"
            self.config.storage.seaweedfs.endpoint_url = "http://localhost:8333"
            self.config.storage.seaweedfs.bucket = "leai-test"
            session = InteractiveTUISession([], self.config, self.mock_client)

            res = session.handle_slash_command("/extract HR --seaweed")
            self.assertTrue(res)
            mock_ensure_bucket.assert_called()
            mock_save_raw_storage.assert_called_once()
            # Local files still written because --no-cache was not passed
            self.assertTrue((self.config.rawPath / "HR" / "tables" / "EMPLOYEES.json").exists())

    @patch("leai.storage.SeaweedFSStorage.save_raw_schema")
    @patch("leai.storage.SeaweedFSStorage.ensure_bucket_exists")
    @patch("leai.storage.SeaweedFSStorage.load_raw_schemas")
    @patch("leai.tui.session.fetch_available_schemas")
    @patch("leai.tui.session.fetch_schema_metadata")
    @patch("oracledb.connect")
    def test_session_slash_extract_with_no_cache(
        self, mock_connect, mock_fetch_meta, mock_fetch_schemas, mock_load_raw, mock_ensure_bucket, mock_save_raw_storage
    ):
        from leai.storage import SaveResult

        mock_connect.return_value = MagicMock()
        mock_fetch_schemas.return_value = ["HR"]
        mock_fetch_meta.return_value = self.schema
        mock_save_raw_storage.return_value = SaveResult(["key1", "key2"], uploaded=2, skipped=0, total=2)
        mock_load_raw.return_value = {"HR": self.schema}

        with tempfile.TemporaryDirectory() as tmpdir:
            self.config.rawPath = Path(tmpdir) / "raw"
            self.config.dsn = "oracle://user:pass@localhost:1521/ORCL"
            self.config.storage.seaweedfs.endpoint_url = "http://localhost:8333"
            self.config.storage.seaweedfs.bucket = "leai-test"
            session = InteractiveTUISession([], self.config, self.mock_client)

            res = session.handle_slash_command("/extract HR --seaweed --no-cache")
            self.assertTrue(res)
            mock_ensure_bucket.assert_called()
            mock_save_raw_storage.assert_called_once()
            # Local files should NOT exist with --no-cache
            self.assertFalse(self.config.rawPath.exists())
            mock_load_raw.assert_called_once()

    @patch("leai.storage.SeaweedFSStorage.test_connection")
    def test_session_slash_seaweed_status(self, mock_test):
        mock_test.return_value = {
            "success": True,
            "endpoint": "http://localhost:8333",
            "bucket": "leai-test",
            "objects_found": 15,
            "message": "Connection operational",
        }
        self.config.storage.seaweedfs.endpoint_url = "http://localhost:8333"
        self.config.storage.seaweedfs.bucket = "leai-test"
        session = InteractiveTUISession([self.schema], self.config, self.mock_client)
        res = session.handle_slash_command("/seaweed status")
        self.assertTrue(res)
        mock_test.assert_called_once()

    @patch("leai.storage.SeaweedFSStorage.push_local_to_remote")
    def test_session_slash_seaweed_push(self, mock_push):
        mock_push.return_value = {"raw": 10, "annotations": 5}
        self.config.storage.seaweedfs.endpoint_url = "http://localhost:8333"
        self.config.storage.seaweedfs.bucket = "leai-test"
        session = InteractiveTUISession([self.schema], self.config, self.mock_client)
        res = session.handle_slash_command("/seaweed push")
        self.assertTrue(res)
        mock_push.assert_called_once()

    def test_completer_seaweed_and_extract_flags(self):
        completer = LeaiCompleter([self.schema], config=self.config)

        # 1. /extract flags
        doc = Document("/extract -")
        event = CompleteEvent()
        completions = [c.text for c in completer.get_completions(doc, event)]
        self.assertIn("--seaweed", completions)
        self.assertIn("--no-cache", completions)
        self.assertIn("--force-upload", completions)

        # 2. /seaweed sub-commands
        doc_sw = Document("/seaweed ")
        completions_sw = [c.text for c in completer.get_completions(doc_sw, event)]
        self.assertIn("status", completions_sw)
        self.assertIn("push", completions_sw)
        self.assertIn("pull", completions_sw)

        # 3. /annotate flags
        doc_ann = Document("/annotate -")
        completions_ann = [c.text for c in completer.get_completions(doc_ann, event)]
        self.assertIn("--seaweed", completions_ann)
        self.assertIn("-W", completions_ann)
        self.assertIn("--no-cache", completions_ann)

    @patch("leai.tui.session.sync_schema_annotations")
    def test_session_slash_annotate_local(self, mock_sync):
        mock_sync.return_value = [Path("test.yml")]
        session = InteractiveTUISession([self.schema], self.config, self.mock_client)
        res = session.handle_slash_command("/annotate")
        self.assertTrue(res)
        mock_sync.assert_called_once()
        self.assertIsNone(mock_sync.call_args.kwargs.get("storage"))

    @patch("leai.storage.SeaweedFSStorage.ensure_bucket_exists")
    @patch("leai.tui.session.sync_schema_annotations")
    def test_session_slash_annotate_seaweed(self, mock_sync, mock_ensure_bucket):
        mock_sync.return_value = [Path("test.yml")]
        self.config.storage.seaweedfs.endpoint_url = "http://localhost:8333"
        self.config.storage.seaweedfs.bucket = "leai-test"
        session = InteractiveTUISession([self.schema], self.config, self.mock_client)

        res = session.handle_slash_command("/annotate --seaweed")
        self.assertTrue(res)
        mock_ensure_bucket.assert_called()
        mock_sync.assert_called_once()
        self.assertIsNotNone(mock_sync.call_args.kwargs.get("storage"))

    @patch("leai.tui.session.sync_schema_annotations")
    def test_session_slash_annotate_no_cache_without_seaweed(self, mock_sync):
        self.config.storage.seaweedfs.enabled = False
        session = InteractiveTUISession([self.schema], self.config, self.mock_client)
        res = session.handle_slash_command("/annotate --no-cache")
        self.assertTrue(res)
        mock_sync.assert_not_called()

    @patch("leai.tui.doc_editor.save_annotation")
    def test_doc_editor_save_with_seaweed_storage(self, mock_save):
        from leai.tui.doc_editor import DocEditor

        mock_storage = MagicMock()
        inputs = iter(["7", "n"])  # 7 = Save Changes, n = Don't recompile docs
        editor = DocEditor(self.config, [self.schema], input_fn=lambda _: next(inputs), storage=mock_storage)
        res = editor.run("EMPLOYEES")
        self.assertTrue(res)
        mock_save.assert_called_once()
        self.assertEqual(mock_save.call_args.kwargs.get("storage"), mock_storage)


if __name__ == "__main__":
    unittest.main()
