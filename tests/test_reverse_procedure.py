from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from leai.config import LeaiConfig
from leai.models import CodeObjectMeta, SchemaMetadata, SubprogramMeta
from leai.workflows import get_workflow, list_workflows
from leai.workflows.reverse_procedure import ReverseProcedureWorkflow


class TestReverseProcedureWorkflow(unittest.TestCase):
    def setUp(self):
        self.cfg = LeaiConfig()
        sample_code = """
        PROCEDURE prc_atualiza_salario (
            p_numfunc IN NUMBER,
            p_novo_salario IN NUMBER,
            p_status OUT VARCHAR2
        ) IS
            v_valido NUMBER;
        BEGIN
            -- Validacao
            IF p_novo_salario <= 0 THEN
                p_status := 'SALARIO_INVALIDO';
                RETURN;
            END IF;

            -- Leitura
            SELECT COUNT(1) INTO v_valido
            FROM FUNCIONARIOS
            WHERE NUMFUNC = p_numfunc;

            IF v_valido > 0 THEN
                -- Escrita
                UPDATE VINCULOS
                SET SALARIO = p_novo_salario
                WHERE NUMFUNC = p_numfunc;

                INSERT INTO HISTORICO_SALARIAL (NUMFUNC, SALARIO, DATA)
                VALUES (p_numfunc, p_novo_salario, SYSDATE);

                -- Chamada externa
                PACK_FOLHA.NOTIFICA_ALTERACAO(p_numfunc);
                DBMS_OUTPUT.PUT_LINE('Salario atualizado com sucesso');

                p_status := 'SUCESSO';
            ELSE
                p_status := 'FUNCIONARIO_NAO_ENCONTRADO';
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                ROLLBACK;
                p_status := 'ERRO_FATAL';
        END prc_atualiza_salario;
        """

        code_obj = CodeObjectMeta(
            name="PRC_ATUALIZA_SALARIO",
            object_type="PROCEDURE",
            source=sample_code,
            subprograms=[SubprogramMeta(name="PRC_ATUALIZA_SALARIO", package_name="PRC_ATUALIZA_SALARIO", subprogram_type="PROCEDURE")],
        )

        self.schemas = [SchemaMetadata(schema_name="RH", code_objects=[code_obj])]

    def test_registry_contains_reverse_procedure(self):
        wf = get_workflow("reverse-procedure", self.schemas, self.cfg, client=None)
        self.assertIsNotNone(wf)
        self.assertIsInstance(wf, ReverseProcedureWorkflow)

        wf_alias = get_workflow("reverse", self.schemas, self.cfg, client=None)
        self.assertIsNotNone(wf_alias)
        self.assertIsInstance(wf_alias, ReverseProcedureWorkflow)

        wfs = list_workflows()
        names = [w["name"] for w in wfs]
        self.assertIn("reverse-procedure", names)

    def test_reverse_procedure_run_execution(self):
        mock_client = MagicMock()
        mock_client.generate_text.return_value = (
            "### Functional Purpose\nUpdates employee salary.\n\n```mermaid\nflowchart TD\nA[Start] --> B[Validate]\n```"
        )

        wf = ReverseProcedureWorkflow(schemas=self.schemas, config=self.cfg, client=mock_client)
        result = wf.run("PRC_ATUALIZA_SALARIO")

        self.assertTrue(result.success)
        self.assertEqual(len(result.steps), 4)

        # Step 1: Extraction
        s1 = result.steps[0]
        self.assertEqual(s1.status, "COMPLETED")
        self.assertGreater(s1.details["line_count"], 10)

        # Step 2: CRUD mapping
        s2 = result.steps[1]
        self.assertEqual(s2.status, "COMPLETED")
        self.assertIn("FUNCIONARIOS", s2.details["read_tables"])
        self.assertIn("VINCULOS", s2.details["update_tables"])
        self.assertIn("HISTORICO_SALARIAL", s2.details["insert_tables"])

        # Step 3: Outgoing calls
        s3 = result.steps[2]
        self.assertEqual(s3.status, "COMPLETED")
        self.assertIn("PACK_FOLHA.NOTIFICA_ALTERACAO", s3.details["called_routines"])
        self.assertIn("DBMS_OUTPUT.PUT_LINE", s3.details["system_packages"])

        # Step 4: AI Synthesis & Report
        self.assertIn("## 📋 Technical CRUD Matrix", result.report_markdown)
        self.assertIn("`FUNCIONARIOS`", result.report_markdown)
        self.assertIn("`VINCULOS`", result.report_markdown)
        self.assertIn("`HISTORICO_SALARIAL`", result.report_markdown)
        self.assertIn("PACK_FOLHA.NOTIFICA_ALTERACAO", result.report_markdown)

    def test_reverse_procedure_not_found(self):
        wf = ReverseProcedureWorkflow(schemas=self.schemas, config=self.cfg, client=None)
        result = wf.run("NON_EXISTENT_PROCEDURE")
        self.assertFalse(result.success)
        self.assertIn("not found", result.summary)


if __name__ == "__main__":
    unittest.main()
