from __future__ import annotations

import unittest

from leai.ai.tools import validate_oracle_sql
from leai.models import ColumnMeta, SchemaMetadata, TableMeta


class TestOracleSQLValidation(unittest.TestCase):
    def setUp(self):
        col_id = ColumnMeta(name="ID", data_type="NUMBER", nullable=False)
        col_nome = ColumnMeta(name="NAME", data_type="VARCHAR2(100)", nullable=False)
        table = TableMeta(name="EMPLOYEES", columns=[col_id, col_nome], primary_keys=["ID"])
        self.schemas = [SchemaMetadata(schema_name="HR", tables=[table])]

    def test_valid_oracle_sql(self):
        sql = "SELECT ID, NAME FROM EMPLOYEES WHERE ID = 100 ORDER BY ID FETCH FIRST 10 ROWS ONLY"
        res = validate_oracle_sql(self.schemas, sql)
        self.assertTrue(res["valid"])
        self.assertEqual(res["total_issues"], 0)
        self.assertEqual(len(res["dialect_issues"]), 0)

    def test_limit_clause_rejection_and_rewrite(self):
        sql = "SELECT ID, NAME FROM EMPLOYEES ORDER BY ID LIMIT 25"
        res = validate_oracle_sql(self.schemas, sql)
        self.assertFalse(res["valid"])
        self.assertEqual(res["dialect_issues"][0]["rule"], "LIMIT_OFFSET_CLAUSE")
        self.assertIn("FETCH FIRST 25 ROWS ONLY", res["suggested_oracle_sql"])

    def test_boolean_data_type_rejection(self):
        sql = "CREATE TABLE USERS (ID NUMBER, IS_ACTIVE BOOLEAN)"
        res = validate_oracle_sql(self.schemas, sql)
        self.assertFalse(res["valid"])
        rules = [i["rule"] for i in res["dialect_issues"]]
        self.assertIn("BOOLEAN_DATA_TYPE", rules)

    def test_ilike_operator_rejection(self):
        sql = "SELECT * FROM EMPLOYEES WHERE NAME ILIKE '%SILVA%'"
        res = validate_oracle_sql(self.schemas, sql)
        self.assertFalse(res["valid"])
        rules = [i["rule"] for i in res["dialect_issues"]]
        self.assertIn("ILIKE_OPERATOR", rules)
        self.assertIn("REGEXP_LIKE", res["suggested_oracle_sql"])

    def test_ifnull_function_rejection(self):
        sql = "SELECT ID, IFNULL(NAME, 'N/A') FROM EMPLOYEES"
        res = validate_oracle_sql(self.schemas, sql)
        self.assertFalse(res["valid"])
        rules = [i["rule"] for i in res["dialect_issues"]]
        self.assertIn("NON_ORACLE_NULL_FUNCTION", rules)
        self.assertIn("NVL(NAME, 'N/A')", res["suggested_oracle_sql"])

    def test_date_math_rejection(self):
        sql = "SELECT * FROM EMPLOYEES WHERE DATEADD(day, 7, CREATED_AT) > GETDATE()"
        res = validate_oracle_sql(self.schemas, sql)
        self.assertFalse(res["valid"])
        rules = [i["rule"] for i in res["dialect_issues"]]
        self.assertIn("NON_ORACLE_DATE_MATH", rules)
        self.assertIn("NON_ORACLE_CURRENT_DATE", rules)

    def test_auto_increment_and_text_rejection(self):
        sql = "CREATE TABLE LOGS (ID SERIAL, MSG TEXT, TS TIMESTAMP)"
        res = validate_oracle_sql(self.schemas, sql)
        self.assertFalse(res["valid"])
        rules = [i["rule"] for i in res["dialect_issues"]]
        self.assertIn("AUTO_INCREMENT_KEYWORD", rules)
        self.assertIn("NON_ORACLE_TEXT_TYPE", rules)

    def test_plus_string_concatenation(self):
        sql = "SELECT 'Nome: ' + NAME FROM EMPLOYEES"
        res = validate_oracle_sql(self.schemas, sql)
        self.assertFalse(res["valid"])
        rules = [i["rule"] for i in res["dialect_issues"]]
        self.assertIn("PLUS_STRING_CONCATENATION", rules)

    def test_backtick_identifiers(self):
        sql = "SELECT `ID`, `NAME` FROM `EMPLOYEES`"
        res = validate_oracle_sql(self.schemas, sql)
        self.assertFalse(res["valid"])
        rules = [i["rule"] for i in res["dialect_issues"]]
        self.assertIn("BACKTICK_QUOTED_IDENTIFIER", rules)
        self.assertNotIn("`", res["suggested_oracle_sql"])

    def test_select_top_clause(self):
        sql = "SELECT TOP 50 ID, NAME FROM EMPLOYEES"
        res = validate_oracle_sql(self.schemas, sql)
        self.assertFalse(res["valid"])
        rules = [i["rule"] for i in res["dialect_issues"]]
        self.assertIn("SELECT_TOP_CLAUSE", rules)
        self.assertIn("FETCH FIRST 50 ROWS ONLY", res["suggested_oracle_sql"])

    def test_schema_cross_validation_warning_on_unknown_column(self):
        sql = "SELECT EMPLOYEES.NON_EXISTENT_COL FROM EMPLOYEES"
        res = validate_oracle_sql(self.schemas, sql)
        self.assertGreaterEqual(len(res["schema_warnings"]), 1)
        self.assertIn("NON_EXISTENT_COL", res["schema_warnings"][0])


if __name__ == "__main__":
    unittest.main()
