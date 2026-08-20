from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from leai.ai.base import BaseLLMClient
from leai.config import LeaiConfig
from leai.models import (
    CodeObjectMeta,
    ColumnMeta,
    SchemaMetadata,
    SubprogramMeta,
    TableMeta,
)
from leai.workflows import get_workflow, list_workflows
from leai.workflows.impact_analysis import ImpactAnalysisWorkflow
from leai.workflows.safe_refactor import SafeRefactorWorkflow


class MockWorkflowLLMClient(BaseLLMClient):
    def __init__(self):
        super().__init__(api_key="mock", model="mock-wf")

    def generate_text(self, prompt: str, system_prompt: str | None = None) -> str:
        return "Workflow synthesized text"

    def generate_json(self, prompt: str, system_prompt: str | None = None) -> dict:
        return {}

    def generate_chat(self, messages: list[dict], system_prompt: str | None = None) -> str:
        return "AI Analysis Report Body with recommendations."

    def generate_chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        system_prompt: str | None = None,
        tool_choice_mode: str = "auto",
    ) -> tuple[str | None, list[dict]]:
        return "Specialist completed analysis report for workflow.", []


class TestWorkflows(unittest.TestCase):
    def setUp(self):
        col = ColumnMeta(name="ID", data_type="NUMBER", nullable=False, is_primary_key=True)
        tbl = TableMeta(name="SERVIDORES", schema_name="RH", columns=[col])
        subp = SubprogramMeta(
            package_name="PACK_RH",
            name="CALCULA_FERIAS",
            subprogram_type="PROCEDURE",
            source="PROCEDURE CALCULA_FERIAS(p_id IN NUMBER) IS BEGIN NULL; END;",
        )
        pkg = CodeObjectMeta(
            name="PACK_RH",
            object_type="PACKAGE",
            schema_name="RH",
            subprograms=[subp],
            source="PACKAGE BODY PACK_RH IS PROCEDURE CALCULA_FERIAS(p_id IN NUMBER) IS BEGIN NULL; END; END PACK_RH;",
        )
        self.schema = SchemaMetadata(schema_name="RH", tables=[tbl], code_objects=[pkg])
        self.cfg = LeaiConfig()
        self.client = MockWorkflowLLMClient()

    def test_list_workflows(self):
        wfs = list_workflows()
        self.assertGreaterEqual(len(wfs), 2)
        names = [w["name"] for w in wfs]
        self.assertIn("impact-analysis", names)
        self.assertIn("safe-refactor", names)

    def test_get_workflow(self):
        wf_impact = get_workflow("impact", schemas=[self.schema], config=self.cfg, client=self.client)
        self.assertIsInstance(wf_impact, ImpactAnalysisWorkflow)

        wf_refactor = get_workflow("refactor", schemas=[self.schema], config=self.cfg, client=self.client)
        self.assertIsInstance(wf_refactor, SafeRefactorWorkflow)

        wf_none = get_workflow("unknown_wf", schemas=[self.schema], config=self.cfg, client=self.client)
        self.assertIsNone(wf_none)

    def test_impact_analysis_workflow_run(self):
        wf = ImpactAnalysisWorkflow(schemas=[self.schema], config=self.cfg, client=self.client)
        steps_started = []

        def _on_start(step):
            steps_started.append(step.name)

        result = wf.run(target="SERVIDORES", on_step_start=_on_start)
        self.assertTrue(result.success)
        self.assertEqual(len(result.steps), 4)
        self.assertEqual(len(steps_started), 4)
        self.assertIn("Impact Assessment Report", result.report_markdown)

        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "impact_report.md"
            saved = result.export_report(out_file)
            self.assertTrue(saved.exists())
            self.assertIn("SERVIDORES", saved.read_text(encoding="utf-8"))

    def test_safe_refactor_workflow_run(self):
        wf = SafeRefactorWorkflow(schemas=[self.schema], config=self.cfg, client=self.client)
        result = wf.run(target="PACK_RH.CALCULA_FERIAS")
        self.assertTrue(result.success)
        self.assertEqual(len(result.steps), 3)
        self.assertIn("Safe Refactoring Package", result.report_markdown)


if __name__ == "__main__":
    unittest.main()
