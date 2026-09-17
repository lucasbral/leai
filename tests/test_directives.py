from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from leai.ai.base import BaseLLMClient
from leai.ai.directives import parse_prompt_tokens, process_inline_directives
from leai.chat_session import ChatSession
from leai.config import LeaiConfig
from leai.glossary import add_or_update_term
from leai.models import CodeObjectMeta, ColumnMeta, GlossaryTerm, SchemaMetadata, TableMeta


class MockDirectiveLLMClient(BaseLLMClient):
    def __init__(self):
        super().__init__(api_key="mock", model="mock-directive")
        self.last_messages = []
        self.last_system_prompt = None

    def generate_text(self, prompt: str, system_prompt: str | None = None) -> str:
        return "Mock text reply"

    def generate_json(self, prompt: str, system_prompt: str | None = None) -> dict:
        return {}

    def generate_chat(self, messages: list[dict[str, str]], system_prompt: str | None = None) -> str:
        self.last_messages = list(messages)
        self.last_system_prompt = system_prompt
        last_user = messages[-1]["content"] if messages else ""
        return f"Resposta para: {last_user}"


class DirectivesEngineTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ann_path = Path(self.temp_dir.name) / "annotations"
        self.ann_path.mkdir(parents=True, exist_ok=True)

        t1 = TableMeta(
            name="TGOVPE_EPB__VANTAGENS",
            columns=[
                ColumnMeta(name="ID_VANTAGEM", data_type="NUMBER", nullable=False),
                ColumnMeta(name="VALOR", data_type="NUMBER", nullable=False),
                ColumnMeta(name="DTINI", data_type="DATE", nullable=False),
            ],
            comment="Tabela de vantagens previdenciárias de servidores",
        )
        c1 = CodeObjectMeta(
            name="PKG_PREVIDENCIA",
            object_type="PACKAGE BODY",
            source="CREATE OR REPLACE PACKAGE BODY PKG_PREVIDENCIA IS PROCEDURE CALCULA IS BEGIN SELECT * FROM TGOVPE_EPB__VANTAGENS; END; END;",
        )
        self.schema = SchemaMetadata(schema_name="GOV", tables=[t1], code_objects=[c1])
        self.cfg = LeaiConfig(
            dsn="",
            schemas=["GOV"],
            annotationsPath=self.ann_path,
        )
        self.client = MockDirectiveLLMClient()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_parse_prompt_tokens_extraction(self):
        prompt = "me explique @TGOVPE_EPB__VANTAGENS /trace e verifique #REGRA_PREVIDENCIARIA com /plsql"
        tokens = parse_prompt_tokens(prompt)

        self.assertEqual(tokens.objects, ["TGOVPE_EPB__VANTAGENS"])
        self.assertEqual(tokens.rules, ["REGRA_PREVIDENCIARIA"])
        self.assertEqual(tokens.directives, ["trace", "plsql"])

    def test_process_inline_directives_trace(self):
        prompt = "me explique @TGOVPE_EPB__VANTAGENS /trace"
        proc = process_inline_directives(prompt, [self.schema], self.cfg, client=self.client)

        self.assertEqual(proc.detected_objects, ["TGOVPE_EPB__VANTAGENS"])
        self.assertIn("trace", proc.detected_directives)
        self.assertIn("DETERMINISTIC LINEAGE TRACE FOR @TGOVPE_EPB__VANTAGENS", proc.precomputed_context)
        self.assertIn("Change Risk Level:", proc.precomputed_context)
        self.assertIn("Mermaid diagram", proc.system_overlay)
        self.assertTrue(any("/trace" in b for b in proc.action_badges))

    def test_process_inline_directives_tune_sql(self):
        prompt = "Como otimizar /tune SELECT * FROM TGOVPE_EPB__VANTAGENS WHERE TRUNC(DTINI) = SYSDATE"
        proc = process_inline_directives(prompt, [self.schema], self.cfg, client=self.client)

        self.assertIn("tune", proc.detected_directives)
        self.assertIn("DETERMINISTIC SQL TUNING DIAGNOSTIC", proc.precomputed_context)
        self.assertIn("Anti-patterns Detected:", proc.precomputed_context)
        self.assertIn("DIRECTIVE OVERLAY: SQL TUNING", proc.system_overlay)

    def test_process_inline_directives_rules_and_glossary(self):
        # Save a glossary term
        term = GlossaryTerm(
            term="REGRA_VANTAGENS",
            definition="Regra de concessão e validação de vantagens previdenciárias",
            primary_table="TGOVPE_EPB__VANTAGENS",
            canonical_filter="VALOR > 0",
        )
        add_or_update_term(self.ann_path, term)

        prompt = "avalie os registros aplicando #REGRA_VANTAGENS /rule"
        proc = process_inline_directives(prompt, [self.schema], self.cfg, client=self.client)

        self.assertIn("REGRA_VANTAGENS", proc.detected_rules)
        self.assertIn("CANONICAL BUSINESS RULES & GLOSSARY", proc.precomputed_context)
        self.assertIn("VALOR > 0", proc.precomputed_context)

    def test_process_inline_directives_specialist_personas(self):
        prompt = "analise o código /plsql e gere documentação /doc"
        proc = process_inline_directives(prompt, [self.schema], self.cfg, client=self.client)

        self.assertIn("SPECIALIST PERSONA: PL/SQL ANALYST", proc.system_overlay)
        self.assertIn("SPECIALIST PERSONA: DOCUMENTATION ANNOTATOR", proc.system_overlay)

    def test_chat_session_integration_with_inline_trace(self):
        session = ChatSession(schemas=[self.schema], config=self.cfg, client=self.client)
        reply, detected = session.send("me explique @TGOVPE_EPB__VANTAGENS /trace")

        self.assertIn("TGOVPE_EPB__VANTAGENS", detected)
        self.assertIn("TGOVPE_EPB__VANTAGENS", session.active_entities)
        self.assertIn("DETERMINISTIC LINEAGE TRACE FOR @TGOVPE_EPB__VANTAGENS", self.client.last_system_prompt)
        self.assertIn("Mermaid diagram", self.client.last_system_prompt)
        self.assertTrue(any("/trace" in b for b in session.last_action_badges))
        self.assertIn("Resposta para: me explique @TGOVPE_EPB__VANTAGENS /trace", reply)
