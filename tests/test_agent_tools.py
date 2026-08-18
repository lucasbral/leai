from __future__ import annotations

import json
import unittest

from leai.ai.agent import MAX_AGENT_ITERATIONS, AgentExecutionEngine
from leai.ai.base import BaseLLMClient
from leai.ai.tools import (
    execute_tool_call,
    get_subprogram_source,
    get_table_schema,
    grep_plsql_code,
    search_database_objects,
    trace_object_lineage,
)
from leai.config import LeaiConfig
from leai.models import (
    CodeObjectMeta,
    ColumnMeta,
    ForeignKeyMeta,
    SchemaMetadata,
    SubprogramMeta,
    SynonymMeta,
    TableMeta,
    TriggerMeta,
)


class MockLLMClient(BaseLLMClient):
    def __init__(self, turns_sequence: list[tuple[str | None, list[dict]]]):
        super().__init__(api_key="mock", model="mock-model")
        self.turns_sequence = turns_sequence
        self.call_count = 0

    def generate_text(self, prompt: str, system_prompt: str | None = None) -> str:
        return "Mock plain text"

    def generate_json(self, prompt: str, system_prompt: str | None = None) -> dict:
        return {"mock": True}

    def generate_chat(self, messages: list[dict], system_prompt: str | None = None) -> str:
        return "Mock final synthesis"

    def generate_chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        system_prompt: str | None = None,
    ) -> tuple[str | None, list[dict]]:
        if self.call_count < len(self.turns_sequence):
            res = self.turns_sequence[self.call_count]
            self.call_count += 1
            return res
        return "Default end reply", []


class TestAgentTools(unittest.TestCase):
    def setUp(self):
        self.cfg = LeaiConfig()
        self.table_func = TableMeta(
            name="EVENTO_FUNC",
            columns=[
                ColumnMeta(name="NUMFUNC", data_type="NUMBER", nullable=False),
                ColumnMeta(name="SETOR", data_type="VARCHAR2(2000)", nullable=True),
                ColumnMeta(name="EMP_CODIGO", data_type="VARCHAR2(20)", nullable=True),
            ],
            primary_keys=["NUMFUNC"],
            comment="Tabela de historico de eventos dos funcionarios",
        )
        self.table_vinc = TableMeta(
            name="VINCULOS",
            columns=[
                ColumnMeta(name="NUMFUNC", data_type="NUMBER", nullable=False),
                ColumnMeta(name="NUMERO", data_type="NUMBER", nullable=False),
                ColumnMeta(name="DTVAC", data_type="DATE", nullable=True, comment="Data de vacancia"),
            ],
            primary_keys=["NUMFUNC", "NUMERO"],
            foreign_keys=[
                ForeignKeyMeta(
                    name="FK_VINC_EV",
                    column="NUMFUNC",
                    referenced_table="EVENTO_FUNC",
                    referenced_column="NUMFUNC",
                )
            ],
        )

        sub_code = """FUNCTION get_setor_func (p_numfunc IN NUMBER, p_numvinc IN NUMBER) RETURN VARCHAR2 IS
  v_setor VARCHAR2(2000);
BEGIN
  IF v_setor = PACK_ERGON.C_RETORNA_NULO THEN
    RETURN NULL;
  END IF;
  RETURN v_setor;
END;"""
        self.pkg = CodeObjectMeta(
            name="PACK_ERGON",
            object_type="PACKAGE BODY",
            source="PACKAGE BODY PACK_ERGON IS\n" + sub_code + "\nEND PACK_ERGON;",
            subprograms=[
                SubprogramMeta(
                    package_name="PACK_ERGON",
                    name="GET_SETOR_FUNC",
                    subprogram_type="FUNCTION",
                    source=sub_code,
                )
            ],
        )

        self.trg = TriggerMeta(
            name="TRG_AUDIT_VINC",
            table_name="VINCULOS",
            trigger_type="BEFORE EACH ROW",
            triggering_event="INSERT OR UPDATE",
            trigger_body="BEGIN\n  IF :NEW.DTVAC IS NOT NULL THEN\n    NULL;\n  END IF;\nEND;",
        )

        self.proc_standalone = CodeObjectMeta(
            name="TGOVPE_RMS_ENVIA_ARQ_CREDITO",
            object_type="PROCEDURE",
            source="PROCEDURE TGOVPE_RMS_ENVIA_ARQ_CREDITO IS BEGIN DBMS_OUTPUT.PUT_LINE('ENVIO'); END;",
        )

        self.syn_proc = SynonymMeta(
            name="SYN_ENVIA_CREDITO",
            schema_name="C_ERGON",
            table_owner="HADES",
            table_name="TGOVPE_RMS_ENVIA_ARQ_CREDITO",
        )

        self.syn_tbl = SynonymMeta(
            name="SYN_EVENTO",
            schema_name="C_ERGON",
            table_owner="C_ERGON",
            table_name="EVENTO_FUNC",
        )

        self.schema = SchemaMetadata(
            schema_name="C_ERGON",
            tables=[self.table_func, self.table_vinc],
            code_objects=[self.pkg, self.proc_standalone],
            triggers=[self.trg],
            synonyms=[self.syn_proc, self.syn_tbl],
        )
        self.schemas = [self.schema]

    def test_synonym_resolution_in_tools(self):
        # 1. Search database objects includes synonym target
        res = search_database_objects(self.schemas, query="SYN_ENVIA_CREDITO")
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["type"], "SYNONYM")
        self.assertIn("HADES.TGOVPE_RMS_ENVIA_ARQ_CREDITO (PROCEDURE)", res[0]["points_to"])

        # 2. Lineage tracing on synonym gives explicit points_to target and guidance
        lineage = trace_object_lineage(self.schemas, object_name="SYN_ENVIA_CREDITO")
        self.assertTrue(lineage.get("is_synonym"))
        self.assertEqual(lineage["points_to"]["owner"], "HADES")
        self.assertEqual(lineage["points_to"]["target_object"], "TGOVPE_RMS_ENVIA_ARQ_CREDITO")
        self.assertEqual(lineage["points_to"]["target_type"], "PROCEDURE")

        # 3. get_subprogram_source transparently dereferences synonym to target procedure
        src = get_subprogram_source(self.schemas, subprogram_name="SYN_ENVIA_CREDITO")
        self.assertEqual(src.get("accessed_via_synonym"), "SYN_ENVIA_CREDITO")
        self.assertIn("DBMS_OUTPUT.PUT_LINE('ENVIO')", src["source_code"])

        # 4. get_table_schema transparently dereferences synonym to target table
        tbl_res = get_table_schema(self.schemas, self.cfg, "SYN_EVENTO")
        self.assertEqual(tbl_res.get("accessed_via_synonym"), "SYN_EVENTO")
        self.assertEqual(tbl_res["table_name"], "EVENTO_FUNC")
        self.assertEqual(len(tbl_res["columns"]), 3)

    def test_search_database_objects(self):
        # Exact/partial search
        res = search_database_objects(self.schemas, query="evento")
        self.assertTrue(any(r["name"] == "EVENTO_FUNC" for r in res))

        # Search package subprogram
        res_sub = search_database_objects(self.schemas, query="get_setor")
        self.assertTrue(any("GET_SETOR_FUNC" in r["name"] for r in res_sub))

        # Filter by object type
        res_trg = search_database_objects(self.schemas, query="audit", object_type="trigger")
        self.assertEqual(len(res_trg), 1)
        self.assertEqual(res_trg[0]["name"], "TRG_AUDIT_VINC")

    def test_get_table_schema(self):
        res = get_table_schema(self.schemas, self.cfg, "VINCULOS")
        self.assertEqual(res["table_name"], "VINCULOS")
        self.assertEqual(res["schema"], "C_ERGON")
        self.assertEqual(len(res["columns"]), 3)
        self.assertTrue(any(c["name"] == "DTVAC" for c in res["columns"]))
        self.assertEqual(len(res["foreign_keys"]), 1)
        self.assertEqual(res["foreign_keys"][0]["references_table"], "EVENTO_FUNC")

        # Unknown table
        err_res = get_table_schema(self.schemas, self.cfg, "NON_EXISTENT")
        self.assertIn("error", err_res)

    def test_get_subprogram_source(self):
        res = get_subprogram_source(self.schemas, package_name="PACK_ERGON", subprogram_name="GET_SETOR_FUNC")
        self.assertEqual(res["package_name"], "PACK_ERGON")
        self.assertEqual(res["subprogram_name"], "GET_SETOR_FUNC")
        self.assertIn("C_RETORNA_NULO", res["source_code"])

        # Unknown subprogram
        err_res = get_subprogram_source(self.schemas, package_name="PACK_ERGON", subprogram_name="FOO_BAR")
        self.assertIn("error", err_res)

    def test_trace_object_lineage(self):
        res = trace_object_lineage(self.schemas, object_name="VINCULOS", depth=1)
        self.assertEqual(res["focal_object"], "VINCULOS")
        self.assertIn("EVENTO_FUNC", res["upstream_parents"])

    def test_grep_plsql_code(self):
        # Search constant in package source
        matches = grep_plsql_code(self.schemas, pattern="C_RETORNA_NULO")
        self.assertGreaterEqual(len(matches), 1)
        self.assertEqual(matches[0]["object_name"], "PACK_ERGON")

        # Search in trigger body
        trg_matches = grep_plsql_code(self.schemas, pattern="NEW.DTVAC")
        self.assertEqual(len(trg_matches), 1)
        self.assertEqual(trg_matches[0]["object_name"], "TRG_AUDIT_VINC")

    def test_execute_tool_call_dispatcher(self):
        raw_json = execute_tool_call(
            tool_name="search_database_objects",
            arguments={"query": "VINCULOS"},
            schemas=self.schemas,
            config=self.cfg,
        )
        parsed = json.loads(raw_json)
        self.assertIsInstance(parsed, list)
        self.assertEqual(parsed[0]["name"], "VINCULOS")

    def test_search_business_documentation_accents_and_rules(self):
        import tempfile
        from pathlib import Path
        from leai.ai.tools import search_business_documentation
        from leai.annotations import save_annotation
        from leai.models import ObjectAnnotation

        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = LeaiConfig()
            cfg.annotationsPath = Path(tmpdir) / "annotations"
            ann_file = cfg.annotationsPath / "tables" / "TGOVPE_FREQ_LIC_AFAST.yml"
            ann = ObjectAnnotation(
                description="Tabela com histórico de licenças, afastamentos e férias de servidores públicos.",
                columns={"DT_INICIO": "Data de início do gozo de férias"},
                business_rules=["Servidor não pode acumular mais de 2 períodos aquisitivos."],
                tags=["RH", "Férias", "Frequência"],
            )
            save_annotation(ann_file, ann)

            # Test 1: Search unaccented "ferias" should find "férias" in description
            matches = search_business_documentation(self.schemas, cfg, query="ferias")
            self.assertGreaterEqual(len(matches), 1)
            self.assertEqual(matches[0]["object_name"], "TGOVPE_FREQ_LIC_AFAST")
            self.assertIn("description", matches[0]["matched_fields"])

            # Test 2: Search "periodos aquisitivos" in business rules
            matches_rule = search_business_documentation(self.schemas, cfg, query="aquisitivos")
            self.assertGreaterEqual(len(matches_rule), 1)
            self.assertEqual(matches_rule[0]["object_name"], "TGOVPE_FREQ_LIC_AFAST")

            # Test 3: Search column field only
            matches_col = search_business_documentation(self.schemas, cfg, query="gozo", search_fields="columns")
            self.assertGreaterEqual(len(matches_col), 1)
            self.assertEqual(matches_col[0]["object_name"], "TGOVPE_FREQ_LIC_AFAST")

            # Test 4: Dispatcher via execute_tool_call
            raw_res = execute_tool_call(
                tool_name="search_business_documentation",
                arguments={"query": "licenca"},
                schemas=self.schemas,
                config=cfg,
            )
            parsed = json.loads(raw_res)
            self.assertIsInstance(parsed, list)
            self.assertEqual(parsed[0]["object_name"], "TGOVPE_FREQ_LIC_AFAST")


    def test_agent_execution_engine_multi_turn(self):
        self.assertEqual(MAX_AGENT_ITERATIONS, 10)

        # Mock sequence: Turn 1 -> Tool Call (get_table_schema), Turn 2 -> Final synthesis
        tool_call_turn = (
            None,
            [
                {
                    "id": "call_1",
                    "name": "get_table_schema",
                    "arguments": {"table_name": "VINCULOS"},
                }
            ],
        )
        final_turn = ("A tabela VINCULOS armazena os vínculos dos servidores e contém o campo DTVAC.", [])

        client = MockLLMClient([tool_call_turn, final_turn])
        engine = AgentExecutionEngine(schemas=self.schemas, config=self.cfg, client=client)

        tools_invoked = []

        def on_tool_start(t_name, t_args):
            tools_invoked.append(t_name)

        reply = engine.run(
            messages=[{"role": "user", "content": "Explique a tabela VINCULOS"}],
            on_tool_start=on_tool_start,
        )

        self.assertEqual(tools_invoked, ["get_table_schema"])
        self.assertIn("VINCULOS", reply)
        self.assertEqual(client.call_count, 2)


if __name__ == "__main__":
    unittest.main()
