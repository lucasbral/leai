from __future__ import annotations
import unittest
from leai.ask_rag import build_rag_context
from leai.config import LeaiConfig
from leai.models import ColumnMeta, SchemaMetadata, SynonymMeta, TableMeta
from leai.raw import trace_raw_dependencies


class SynonymTests(unittest.TestCase):
    def setUp(self):
        # Schema CADASTRO com a tabela física TB_FUNCIONARIOS
        self.func_table = TableMeta(
            name="TB_FUNCIONARIOS",
            columns=[
                ColumnMeta(name="ID", data_type="NUMBER", nullable=False),
                ColumnMeta(name="NOME", data_type="VARCHAR2", nullable=False),
            ],
            primary_keys=["ID"],
        )
        self.schema_cadastro = SchemaMetadata(
            schema_name="CADASTRO",
            tables=[self.func_table],
        )

        # Schema FOLHA com um sinônimo apontando para CADASTRO.TB_FUNCIONARIOS
        self.syn_func = SynonymMeta(
            name="FUNCIONARIOS",
            table_owner="CADASTRO",
            table_name="TB_FUNCIONARIOS",
        )
        self.syn_remoto = SynonymMeta(
            name="CLIENTES_LEGADO",
            table_owner="CRM",
            table_name="CLIENTES",
            db_link="DBLINK_LEGADO",
        )
        self.schema_folha = SchemaMetadata(
            schema_name="FOLHA",
            synonyms=[self.syn_func, self.syn_remoto],
        )

        self.cfg = LeaiConfig(dsn="", schemas=["CADASTRO", "FOLHA"])

    def test_trace_resolves_synonym_to_real_target(self):
        # Executar trace no sinônimo FUNCIONARIOS
        trace_res = trace_raw_dependencies([self.schema_cadastro, self.schema_folha], "FUNCIONARIOS", max_depth=2)

        self.assertEqual(trace_res.focal_type, "SYNONYM")
        self.assertTrue(any(dep.relation_type == "SYNONYM_FOR" and dep.target_name == "TB_FUNCIONARIOS" for dep in trace_res.dependencies))

    def test_trace_synonym_with_dblink(self):
        trace_res = trace_raw_dependencies([self.schema_folha], "CLIENTES_LEGADO", max_depth=1)
        self.assertEqual(trace_res.focal_type, "SYNONYM")
        self.assertTrue(any("DBLINK_LEGADO" in (dep.details or "") for dep in trace_res.dependencies))

    def test_rag_identifies_and_resolves_synonym_in_question(self):
        q = "Qual a estrutura de colunas do sinônimo FUNCIONARIOS?"
        context, detected = build_rag_context(q, [self.schema_cadastro, self.schema_folha], self.cfg)

        self.assertIn("FUNCIONARIOS", detected)
        self.assertIn("TB_FUNCIONARIOS", context)


if __name__ == "__main__":
    unittest.main()
