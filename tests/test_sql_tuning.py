from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from leai.ai.tools import explain_and_tune_sql
from leai.models import ColumnMeta, ForeignKeyMeta, SchemaMetadata, TableMeta


class TestSQLTuning(unittest.TestCase):
    def setUp(self):
        col_id = ColumnMeta(name="ID", data_type="NUMBER", nullable=False)
        col_nome = ColumnMeta(name="NOME", data_type="VARCHAR2(100)", nullable=False)
        col_dept = ColumnMeta(name="DEPT_ID", data_type="NUMBER", nullable=True)
        col_dt = ColumnMeta(name="DATA_ADMISSAO", data_type="DATE", nullable=True)
        col_sal = ColumnMeta(name="SALARIO", data_type="NUMBER(10,2)", nullable=True)

        self.table_emp = TableMeta(
            name="EMPLOYEES",
            columns=[col_id, col_nome, col_dept, col_dt, col_sal],
            primary_keys=["ID"],
            foreign_keys=[
                ForeignKeyMeta(
                    name="FK_EMP_DEPT",
                    column="DEPT_ID",
                    referenced_table="DEPARTMENTS",
                    referenced_column="ID",
                )
            ],
        )
        self.table_dept = TableMeta(
            name="DEPARTMENTS",
            columns=[
                ColumnMeta(name="ID", data_type="NUMBER", nullable=False),
                ColumnMeta(name="NAME", data_type="VARCHAR2(50)", nullable=False),
            ],
            primary_keys=["ID"],
        )
        self.schemas = [SchemaMetadata(schema_name="HR", tables=[self.table_emp, self.table_dept])]

    def test_trunc_non_sargable_predicate(self):
        query = "SELECT * FROM EMPLOYEES WHERE TRUNC(DATA_ADMISSAO) = DATE '2025-01-01'"
        res = explain_and_tune_sql(self.schemas, query)
        self.assertGreaterEqual(res["anti_patterns_count"], 1)
        ap_types = [ap["type"] for ap in res["anti_patterns"]]
        self.assertIn("NON_SARGABLE_PREDICATE", ap_types)
        self.assertIn("Function TRUNC()", res["anti_patterns"][0]["impact"])

    def test_upper_lower_function_on_column(self):
        query = "SELECT * FROM EMPLOYEES WHERE UPPER(NOME) LIKE 'MARIA%'"
        res = explain_and_tune_sql(self.schemas, query)
        ap_types = [ap["type"] for ap in res["anti_patterns"]]
        self.assertIn("FUNCTION_ON_INDEXED_COLUMN", ap_types)

    def test_nvl_predicate_wrapper(self):
        query = "SELECT * FROM EMPLOYEES WHERE NVL(SALARIO, 0) > 5000"
        res = explain_and_tune_sql(self.schemas, query)
        ap_types = [ap["type"] for ap in res["anti_patterns"]]
        self.assertIn("NULL_WRAPPER_PREDICATE", ap_types)

    def test_leading_wildcard_like(self):
        query = "SELECT * FROM EMPLOYEES WHERE NOME LIKE '%SILVA'"
        res = explain_and_tune_sql(self.schemas, query)
        ap_types = [ap["type"] for ap in res["anti_patterns"]]
        self.assertIn("LEADING_WILDCARD_LIKE", ap_types)

    def test_not_in_subquery_null_risk_and_rewrite(self):
        query = "SELECT * FROM EMPLOYEES WHERE DEPT_ID NOT IN (SELECT ID FROM DEPARTMENTS WHERE NAME = 'TI')"
        res = explain_and_tune_sql(self.schemas, query)
        ap_types = [ap["type"] for ap in res["anti_patterns"]]
        self.assertIn("NOT_IN_SUBQUERY_NULL_RISK", ap_types)
        self.assertIsNotNone(res["rewritten_query"])
        self.assertIn("NOT EXISTS", res["rewritten_query"])

    def test_correlated_scalar_subquery(self):
        query = "SELECT e.ID, (SELECT d.NAME FROM DEPARTMENTS d WHERE d.ID = e.DEPT_ID) AS dept_name FROM EMPLOYEES e"
        res = explain_and_tune_sql(self.schemas, query)
        ap_types = [ap["type"] for ap in res["anti_patterns"]]
        self.assertIn("CORRELATED_SCALAR_SUBQUERY", ap_types)

    def test_fts_warning_and_compound_index_recommendation(self):
        query = "SELECT * FROM EMPLOYEES WHERE NOME = 'JOAO' AND SALARIO > 3000"
        res = explain_and_tune_sql(self.schemas, query)
        self.assertGreaterEqual(len(res["fts_warnings"]), 1)
        self.assertEqual(res["fts_warnings"][0]["table"], "EMPLOYEES")
        self.assertGreaterEqual(len(res["index_recommendations"]), 1)
        rec = res["index_recommendations"][0]
        self.assertEqual(rec["table"], "EMPLOYEES")
        # Equality column NOME must be ordered before range column SALARIO
        self.assertIn("NOME, SALARIO", rec["suggested_index"])

    def test_ai_tuning_proposal_with_mock_client(self):
        mock_client = MagicMock()
        mock_client.generate_text.return_value = "Optimized SQL: SELECT e.ID FROM EMPLOYEES e WHERE e.DEPT_ID = 10"
        query = "SELECT * FROM EMPLOYEES WHERE TRUNC(DATA_ADMISSAO) = SYSDATE"
        res = explain_and_tune_sql(self.schemas, query, client=mock_client)
        self.assertIsNotNone(res["ai_tuning_proposal"])
        self.assertIn("Optimized SQL", res["ai_tuning_proposal"])


if __name__ == "__main__":
    unittest.main()
