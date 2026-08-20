from __future__ import annotations

import unittest

from leai.ai.base import BaseLLMClient
from leai.ai.subagents import (
    SUBAGENT_REGISTRY,
    SubagentRunner,
    execute_subagent,
    list_registered_subagents,
)
from leai.ai.tools import execute_tool_call
from leai.config import LeaiConfig
from leai.models import ColumnMeta, SchemaMetadata, TableMeta


class MockSubagentLLMClient(BaseLLMClient):
    def __init__(self):
        super().__init__(api_key="mock", model="mock-model")
        self.calls = []

    def generate_text(self, prompt: str, system_prompt: str | None = None) -> str:
        return "mock text"

    def generate_json(self, prompt: str, system_prompt: str | None = None) -> dict:
        return {}

    def generate_chat(self, messages: list[dict], system_prompt: str | None = None) -> str:
        return "Specialist synthesized output."

    def generate_chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        system_prompt: str | None = None,
        tool_choice_mode: str = "auto",
    ) -> tuple[str | None, list[dict]]:
        self.calls.append({"tools": [t.get("function", {}).get("name") for t in (tools or [])], "mode": tool_choice_mode})
        # Simulate immediate final response without tools
        return "Specialist analysis complete.", []


class TestSubagents(unittest.TestCase):
    def setUp(self):
        t1 = TableMeta(
            name="VINCULOS",
            columns=[ColumnMeta(name="NUMFUNC", data_type="NUMBER", nullable=False, is_primary_key=True)],
        )
        self.schema = SchemaMetadata(schema_name="RH", tables=[t1])
        self.cfg = LeaiConfig()
        self.client = MockSubagentLLMClient()

    def test_list_registered_subagents(self):
        agents = list_registered_subagents()
        self.assertEqual(len(agents), 5)
        roles = [a["role"] for a in agents]
        self.assertIn("catalog_researcher", roles)
        self.assertIn("plsql_analyst", roles)
        self.assertIn("lineage_auditor", roles)
        self.assertIn("patch_generator", roles)
        self.assertIn("doc_annotator", roles)

    def test_subagent_tool_filtering(self):
        cfg_researcher = SUBAGENT_REGISTRY["catalog_researcher"]
        runner = SubagentRunner(config_obj=cfg_researcher, schemas=[self.schema], config=self.cfg, client=self.client)
        filtered = runner.filter_tools()
        names = [t["function"]["name"] for t in filtered]
        self.assertIn("search_database_objects", names)
        self.assertIn("search_column_comments", names)
        self.assertIn("get_table_schema", names)
        self.assertNotIn("grep_plsql_code", names)
        self.assertNotIn("get_subprogram_source", names)

    def test_execute_subagent(self):
        out = execute_subagent(
            role="catalog_researcher",
            task="Find column NUMFUNC",
            schemas=[self.schema],
            config=self.cfg,
            client=self.client,
        )
        self.assertIn("Specialist analysis complete", out)
        self.assertEqual(len(self.client.calls), 1)
        self.assertEqual(self.client.calls[0]["mode"], "required")

    def test_execute_unknown_subagent(self):
        out = execute_subagent(
            role="non_existent_role",
            task="Some task",
            schemas=[self.schema],
            config=self.cfg,
            client=self.client,
        )
        self.assertIn("Unknown subagent role", out)

    def test_delegate_to_specialist_tool_dispatch(self):
        res_str = execute_tool_call(
            tool_name="delegate_to_specialist",
            arguments={"specialist_role": "catalog_researcher", "task": "Find NUMFUNC"},
            schemas=[self.schema],
            config=self.cfg,
            client=self.client,
        )
        self.assertIn("Specialist analysis complete", res_str)


if __name__ == "__main__":
    unittest.main()
