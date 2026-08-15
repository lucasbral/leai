from __future__ import annotations
import unittest
from leai.compression import (
    compact_schema_notation,
    extract_package_skeleton,
    extract_subprogram_block,
    minify_plsql_source,
)
from leai.models import ColumnMeta, ForeignKeyMeta, SchemaMetadata, TableMeta


class CompressionTests(unittest.TestCase):
    def test_minify_plsql_source(self):
        source = """
        /*
         * Copyright (c) 2026 Empresa XYZ
         * Author: Desenvolvedor Senior
         * Version: 2.1.0
         * History:
         * 2026-01-01 - Criacao
         */
        
        -- =======================================================
        -- Bloco de validacao
        -- =======================================================
        
        
        PROCEDURE CALCULA_VALOR IS
        BEGIN
            -- regra: se valor for negativo, zera
            NULL;
        END CALCULA_VALOR;
        """

        minified = minify_plsql_source(source)
        self.assertNotIn("Copyright", minified)
        self.assertNotIn("Author:", minified)
        self.assertNotIn("=======================================================", minified)
        self.assertIn("PROCEDURE CALCULA_VALOR IS", minified)
        self.assertIn("-- regra: se valor for negativo, zera", minified)

    def test_minify_preserves_oracle_hints(self):
        source = """
        SELECT /*+ INDEX(t emp_idx) */ id, nome
        FROM funcionarios t
        WHERE id = 10;
        """
        minified = minify_plsql_source(source)
        self.assertIn("/*+ INDEX(t emp_idx) */", minified)

    def test_extract_subprogram_block(self):
        huge_package = """
        PACKAGE BODY PKG_COMPLEXA IS
        
            PROCEDURE OUTRA_PROC IS
            BEGIN
                NULL;
            END OUTRA_PROC;
            
            PROCEDURE TESTE(p_id NUMBER, p_nome VARCHAR2) IS
                v_aux NUMBER;
            BEGIN
                v_aux := 10;
                UPDATE FUNCIONARIOS SET SALARIO = v_aux WHERE ID = p_id;
            END TESTE;
            
            FUNCTION MAIS_UMA RETURN NUMBER IS
            BEGIN
                RETURN 1;
            END MAIS_UMA;
            
        END PKG_COMPLEXA;
        """

        block = extract_subprogram_block(huge_package, "TESTE")
        self.assertIsNotNone(block)
        self.assertIn("PROCEDURE TESTE(p_id NUMBER, p_nome VARCHAR2) IS", block)
        self.assertIn("UPDATE FUNCIONARIOS SET SALARIO = v_aux WHERE ID = p_id;", block)
        self.assertNotIn("OUTRA_PROC", block)
        self.assertNotIn("MAIS_UMA", block)

    def test_extract_package_skeleton(self):
        pkg = """
        PACKAGE BODY PKG_EXEMPLO IS
            PROCEDURE P1(x NUMBER);
            FUNCTION F1(y VARCHAR2) RETURN BOOLEAN;
        END PKG_EXEMPLO;
        """
        skeleton = extract_package_skeleton(pkg)
        self.assertIn("PROCEDURE P1(x NUMBER);", skeleton)
        self.assertIn("FUNCTION F1(y VARCHAR2) RETURN BOOLEAN;", skeleton)

    def test_compact_schema_notation(self):
        t1 = TableMeta(
            name="FUNCIONARIOS",
            columns=[
                ColumnMeta(name="ID", data_type="NUMBER", nullable=False),
                ColumnMeta(name="DEP_ID", data_type="NUMBER", nullable=False),
                ColumnMeta(name="NOME", data_type="VARCHAR2", nullable=False),
            ],
            primary_keys=["ID"],
            foreign_keys=[
                ForeignKeyMeta(name="FK_F_D", column="DEP_ID", referenced_table="DEPARTAMENTOS", referenced_column="ID")
            ],
        )

        schema = SchemaMetadata(schema_name="HR", tables=[t1])
        compact = compact_schema_notation(schema)

        self.assertIn("Schema 'HR':", compact)
        self.assertIn("FUNCIONARIOS(ID*, DEP_ID->DEPARTAMENTOS, NOME)", compact)


if __name__ == "__main__":
    unittest.main()
