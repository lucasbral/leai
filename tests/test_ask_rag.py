from __future__ import annotations

import unittest

from leai.ask_rag import build_rag_context, extract_entities_from_question
from leai.config import LeaiConfig
from leai.models import (
    CodeObjectMeta,
    ColumnMeta,
    ForeignKeyMeta,
    SchemaMetadata,
    TableMeta,
    TriggerMeta,
    ViewMeta,
)


class AskRAGTests(unittest.TestCase):
    def setUp(self):
        self.dep_table = TableMeta(
            name="DEPARTAMENTOS",
            columns=[
                ColumnMeta(name="ID", data_type="NUMBER", nullable=False),
                ColumnMeta(name="NOME", data_type="VARCHAR2", nullable=False),
            ],
        )

        self.func_table = TableMeta(
            name="FUNCIONARIOS",
            columns=[
                ColumnMeta(name="ID", data_type="NUMBER", nullable=False),
                ColumnMeta(name="DEP_ID", data_type="NUMBER", nullable=False),
                ColumnMeta(name="SALARIO", data_type="NUMBER", nullable=False),
            ],
            foreign_keys=[
                ForeignKeyMeta(name="FK_FUNC_DEP", column="DEP_ID", referenced_table="DEPARTAMENTOS", referenced_column="ID"),
            ],
        )

        self.vw_folha = ViewMeta(
            name="VW_FOLHA",
            text="SELECT ID, SALARIO FROM FUNCIONARIOS WHERE SALARIO > 0",
        )

        self.trg_audit = TriggerMeta(
            name="TRG_FUNC_AUDIT",
            table_name="FUNCIONARIOS",
            trigger_type="AFTER INSERT",
            triggering_event="INSERT",
        )

        self.pkg_folha = CodeObjectMeta(
            name="PKG_FOLHA",
            object_type="PACKAGE",
            source="PACKAGE BODY PKG_FOLHA IS PROCEDURE CALCULA IS BEGIN UPDATE FUNCIONARIOS SET SALARIO = 1000; END; END;",
        )

        self.schema = SchemaMetadata(
            schema_name="HR",
            tables=[self.dep_table, self.func_table],
            views=[self.vw_folha],
            triggers=[self.trg_audit],
            code_objects=[self.pkg_folha],
        )

        self.cfg = LeaiConfig(dsn="", schemas=["HR"])

    def test_extract_entities_from_question(self):
        objects = {"FUNCIONARIOS", "DEPARTAMENTOS", "VW_FOLHA", "PKG_FOLHA"}

        q1 = "Quais views ou procedures consultam a tabela funcionarios e o que ela faz?"
        found1 = extract_entities_from_question(q1, objects)
        self.assertIn("FUNCIONARIOS", found1)

        q2 = "Como a PKG_FOLHA se relaciona com a tabela DEPARTAMENTOS?"
        found2 = extract_entities_from_question(q2, objects)
        self.assertIn("PKG_FOLHA", found2)
        self.assertIn("DEPARTAMENTOS", found2)

        q3 = "Qual a data do último backup do banco?"
        found3 = extract_entities_from_question(q3, objects)
        self.assertEqual(found3, [])

    def test_build_rag_context_with_focal_entity(self):
        question = "Como funciona o fluxo da tabela FUNCIONARIOS e quem consome ela?"
        context, entities = build_rag_context(question, [self.schema], self.cfg)

        self.assertIn("FUNCIONARIOS", entities)
        self.assertIn("### [RAG CONTEXT] TECHNICAL IMPACT & LINEAGE DOSSIER OF FOCAL ENTITIES:", context)
        self.assertIn("--- START OF FOCAL DOSSIER: FUNCIONARIOS ---", context)
        self.assertIn("rag_metadata:", context)
        self.assertIn("VW_FOLHA", context)
        self.assertIn("TRG_FUNC_AUDIT", context)
        self.assertIn("DEPARTAMENTOS", context)

    def test_build_rag_context_fallback_general_schema(self):
        question = "Me dê um panorama geral do banco de dados"
        context, entities = build_rag_context(question, [self.schema], self.cfg)

        self.assertEqual(entities, [])
        self.assertNotIn("--- START OF FOCAL DOSSIER:", context)
        self.assertIn("### [COMPACT SCHEMA CATALOG]", context)
        self.assertIn("FUNCIONARIOS", context)
        self.assertIn("DEPARTAMENTOS", context)


if __name__ == "__main__":
    unittest.main()
