from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from typer.testing import CliRunner

from leai.ai.tools import execute_tool_call, lookup_business_term
from leai.cli import app
from leai.config import LeaiConfig
from leai.docs import write_glossary_doc
from leai.glossary import (
    add_or_update_term,
    load_glossary,
    save_glossary,
    search_glossary,
)
from leai.models import BusinessGlossary, GlossaryTerm


class TestBusinessGlossary(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ann_path = Path(self.temp_dir.name) / "annotations"
        self.ann_path.mkdir(parents=True, exist_ok=True)
        self.doc_path = Path(self.temp_dir.name) / "docs"
        self.doc_path.mkdir(parents=True, exist_ok=True)
        self.config = LeaiConfig(annotationsPath=self.ann_path, docPath=self.doc_path)
        self.runner = CliRunner()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_save_and_load_glossary(self):
        term1 = GlossaryTerm(
            term="Usuário Ativo",
            definition="Usuário apto a logar e realizar operações.",
            primary_table="USUARIOS",
            canonical_filter="USUARIOS.STATUS = 'A' AND (USUARIOS.DT_EXPIRACAO IS NULL OR USUARIOS.DT_EXPIRACAO > SYSDATE)",
            tags=["seguranca", "acesso"],
        )
        term2 = GlossaryTerm(
            term="Vacanciados no Ano",
            definition="Servidores efetivos que desocuparam o cargo no exercício corrente.",
            primary_table="VINCULOS",
            canonical_filter="VINCULOS.TIPO_DESLIG = 'VAC' AND VINCULOS.DT_DESLIG >= TRUNC(SYSDATE, 'YYYY')",
            related_tables=["SERVIDORES", "CARGOS"],
            tags=["rh", "vacancia"],
        )

        glossary = BusinessGlossary(terms=[term1, term2])
        save_glossary(self.ann_path, glossary)

        loaded = load_glossary(self.ann_path)
        self.assertEqual(len(loaded.terms), 2)
        terms_map = {t.term: t for t in loaded.terms}
        self.assertIn("Usuário Ativo", terms_map)
        self.assertIn("Vacanciados no Ano", terms_map)
        self.assertEqual(terms_map["Usuário Ativo"].primary_table, "USUARIOS")
        self.assertIn("USUARIOS.STATUS = 'A'", terms_map["Usuário Ativo"].canonical_filter)

    def test_add_or_update_term(self):
        t1 = GlossaryTerm(term="Regra Teste", definition="Definição 1")
        add_or_update_term(self.ann_path, t1)

        loaded1 = load_glossary(self.ann_path)
        self.assertEqual(len(loaded1.terms), 1)
        self.assertEqual(loaded1.terms[0].definition, "Definição 1")

        # Update existing
        t1_updated = GlossaryTerm(term="Regra Teste", definition="Definição Atualizada")
        add_or_update_term(self.ann_path, t1_updated)

        loaded2 = load_glossary(self.ann_path)
        self.assertEqual(len(loaded2.terms), 1)
        self.assertEqual(loaded2.terms[0].definition, "Definição Atualizada")

    def test_search_glossary(self):
        t1 = GlossaryTerm(
            term="Usuário Ativo",
            definition="Conta ativa no sistema.",
            primary_table="USUARIOS",
            canonical_filter="STATUS = 'A'",
        )
        t2 = GlossaryTerm(
            term="Vacanciados no Ano",
            definition="Desocupação de cargo público.",
            primary_table="VINCULOS",
            canonical_filter="TIPO_DESLIG = 'VAC'",
        )
        glossary = BusinessGlossary(terms=[t1, t2])

        # Test exact match
        matches = search_glossary(glossary, "usuario ativo")
        self.assertTrue(len(matches) >= 1)
        self.assertEqual(matches[0][0].term, "Usuário Ativo")

        # Test accent-insensitive search
        matches_accent = search_glossary(glossary, "vacanciados")
        self.assertTrue(len(matches_accent) >= 1)
        self.assertEqual(matches_accent[0][0].term, "Vacanciados no Ano")

    def test_lookup_business_term_tool(self):
        t1 = GlossaryTerm(
            term="Folha Suplementar",
            definition="Folha de pagamento extra para retroativos e ajustes.",
            primary_table="FOLHA_PAGTO",
            canonical_filter="TIPO_FOLHA = 'SUP'",
            tags=["rh", "folha"],
        )
        add_or_update_term(self.ann_path, t1)

        # Direct function call
        res = lookup_business_term(self.config, query="folha suplementar")
        self.assertEqual(res["total_matches"], 1)
        self.assertEqual(res["results"][0]["term"], "Folha Suplementar")
        self.assertEqual(res["results"][0]["canonical_filter"], "TIPO_FOLHA = 'SUP'")

        # Tool execution via execute_tool_call
        raw_json = execute_tool_call(
            "lookup_business_term",
            {"query": "suplementar"},
            schemas=[],
            config=self.config,
        )
        self.assertIn("Folha Suplementar", raw_json)
        self.assertIn("TIPO_FOLHA = 'SUP'", raw_json)

    def test_write_glossary_doc(self):
        t1 = GlossaryTerm(
            term="Usuário Ativo",
            definition="Contas ativas e operacionais.",
            primary_table="USUARIOS",
            canonical_filter="STATUS = 'A'",
            tags=["seguranca"],
        )
        add_or_update_term(self.ann_path, t1)

        doc_file = write_glossary_doc(self.ann_path, self.doc_path)
        self.assertIsNotNone(doc_file)
        self.assertTrue(doc_file.exists())
        content = doc_file.read_text(encoding="utf-8")
        self.assertIn("# Business Glossary & Canonical Domain Rules", content)
        self.assertIn("Usuário Ativo", content)
        self.assertIn("`STATUS = 'A'`", content)

    def test_cli_rule_commands(self):
        cfg_file = Path(self.temp_dir.name) / "leai.yml"
        cfg_file.write_text(f"annotationsPath: '{self.ann_path}'\n", encoding="utf-8")

        # 1. Add rule via CLI
        res_add = self.runner.invoke(
            app,
            [
                "rule",
                "add",
                "Estágio Probatório",
                "--definition",
                "Servidores em avaliação nos 3 primeiros anos.",
                "--table",
                "SERVIDORES",
                "--filter",
                "TEMPO_SERVICO < 1095",
                "--tags",
                "rh,estagio",
                "--config",
                str(cfg_file),
            ],
        )
        self.assertEqual(res_add.exit_code, 0)
        self.assertIn("Estágio Probatório", res_add.output)

        # 2. List rules via CLI
        res_list = self.runner.invoke(app, ["rule", "list", "--config", str(cfg_file)])
        self.assertEqual(res_list.exit_code, 0)
        self.assertIn("Estágio Probatório", res_list.output)
        self.assertIn("SERVIDORES", res_list.output)

        # 3. Show rule via CLI
        res_show = self.runner.invoke(app, ["rule", "show", "Estágio", "--config", str(cfg_file)])
        self.assertEqual(res_show.exit_code, 0)
        self.assertIn("Estágio Probatório", res_show.output)
        self.assertIn("TEMPO_SERVICO < 1095", res_show.output)
