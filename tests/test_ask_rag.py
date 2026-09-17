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

        # Plain text questions without @ return empty list (letting tools handle discovery)
        q1 = "Quais views ou procedures consultam a tabela funcionarios e o que ela faz?"
        found1 = extract_entities_from_question(q1, objects)
        self.assertEqual(found1, [])

        # Questions with explicit @ return the referenced objects
        q2 = "Como a @PKG_FOLHA se relaciona com a tabela @DEPARTAMENTOS?"
        found2 = extract_entities_from_question(q2, objects)
        self.assertIn("PKG_FOLHA", found2)
        self.assertIn("DEPARTAMENTOS", found2)

        q3 = "Qual a data do último backup do banco?"
        found3 = extract_entities_from_question(q3, objects)
        self.assertEqual(found3, [])

    def test_extract_entities_strict_at_mention(self):
        objects = {"FUNCIONARIOS", "DEPARTAMENTOS", "TABELA", "DATA", "RECADASTRAMENTO"}
        top_objects = {"FUNCIONARIOS", "DEPARTAMENTOS"}

        # When @ is used, return exclusively the @ mentioned object and ignore plain text words
        q = "Na tabela @FUNCIONARIOS existe alguma coluna com a data de recadastramento ?"
        found = extract_entities_from_question(q, objects, top_level_objects=top_objects)
        self.assertEqual(found, ["FUNCIONARIOS"])

    def test_disambiguation_table_vs_package_subprogram(self):
        # Create a package that also contains a subprogram named FUNCIONARIOS and a procedure named TABELA
        from leai.models import SubprogramMeta

        pck_complex = CodeObjectMeta(
            name="PCK_EP__BEFORE_CERG",
            object_type="PACKAGE",
            subprograms=[
                SubprogramMeta(name="FUNCIONARIOS", package_name="PCK_EP__BEFORE_CERG", subprogram_type="PROCEDURE"),
                SubprogramMeta(name="TABELA", package_name="PCK_EP__BEFORE_CERG", subprogram_type="PROCEDURE"),
            ],
            source=(
                "PACKAGE BODY PCK_EP__BEFORE_CERG IS PROCEDURE FUNCIONARIOS IS BEGIN NULL; END; PROCEDURE TABELA IS BEGIN NULL; END; END;"
            ),
        )

        schema_with_pck = SchemaMetadata(
            schema_name="HR",
            tables=[self.func_table, self.dep_table],
            views=[self.vw_folha],
            triggers=[self.trg_audit],
            code_objects=[self.pkg_folha, pck_complex],
        )

        question = "Na tabela @FUNCIONARIOS existe alguma coluna com a data de recadastramento ?"
        context, entities = build_rag_context(question, [schema_with_pck], self.cfg, include_catalog=False)

        # Must focus strictly on Table FUNCIONARIOS
        self.assertEqual(entities, ["FUNCIONARIOS"])
        self.assertIn("--- START OF FOCAL DOSSIER: FUNCIONARIOS ---", context)
        # Must NOT inject the package as a focal dossier or focal subprogram
        self.assertNotIn("--- START OF FOCAL DOSSIER: PCK_EP__BEFORE_CERG ---", context)
        self.assertNotIn("FOCAL PL/SQL SUBPROGRAM:", context)


if __name__ == "__main__":
    unittest.main()
