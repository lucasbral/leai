from __future__ import annotations

import json
import time
from typing import Callable

from leai.ai.base import BaseLLMClient
from leai.ai.subagents import execute_subagent
from leai.ai.tools import get_table_schema, grep_plsql_code, trace_object_lineage
from leai.config import LeaiConfig
from leai.models import SchemaMetadata
from leai.workflows.base import BaseWorkflow, WorkflowResult, WorkflowStep


class ImpactAnalysisWorkflow(BaseWorkflow):
    """Executes an end-to-end impact analysis pipeline for schema objects or PL/SQL routines."""

    def __init__(
        self,
        schemas: list[SchemaMetadata],
        config: LeaiConfig,
        client: BaseLLMClient,
    ):
        super().__init__(
            name="impact-analysis",
            description="Comprehensive change impact assessment: constraints, lineage traversal, PL/SQL code scanning, and risk matrix.",
            schemas=schemas,
            config=config,
            client=client,
        )

    def run(
        self,
        target: str,
        on_step_start: Callable[[WorkflowStep], None] | None = None,
        on_step_end: Callable[[WorkflowStep], None] | None = None,
        on_token: Callable[[str], None] | None = None,
    ) -> WorkflowResult:
        start_time = time.perf_counter()
        target_clean = target.strip().upper()
        self.steps = []

        # ======================================================================
        # STEP 1: Schema & Constraints Discovery
        # ======================================================================
        s1 = WorkflowStep(
            step_number=1,
            name="Schema & Constraints Discovery",
            description=f"Inspect columns, primary/foreign keys, and annotations for '{target_clean}'",
        )
        self.steps.append(s1)
        if on_step_start:
            on_step_start(s1)
        t_s1 = time.perf_counter()

        schema_data = get_table_schema(self.schemas, self.config, target_clean)
        s1.duration_seconds = round(time.perf_counter() - t_s1, 3)
        if "error" not in schema_data:
            s1.status = "COMPLETED"
            cols_count = len(schema_data.get("columns", []))
            fks_count = len(schema_data.get("foreign_keys", []))
            s1.output_summary = f"{cols_count} columns, {fks_count} foreign keys identified"
            s1.details = schema_data
        else:
            s1.status = "COMPLETED"
            s1.output_summary = f"Object '{target_clean}' inspected (non-table or synonym)"
            s1.details = schema_data

        if on_step_end:
            on_step_end(s1)

        # ======================================================================
        # STEP 2: Lineage & Dependency Graph Traversal
        # ======================================================================
        s2 = WorkflowStep(
            step_number=2,
            name="Dependency & Lineage Traversal",
            description=f"Trace upstream tables and downstream consumers of '{target_clean}'",
        )
        self.steps.append(s2)
        if on_step_start:
            on_step_start(s2)
        t_s2 = time.perf_counter()

        lineage_data = trace_object_lineage(self.schemas, target_clean, depth=2)
        s2.duration_seconds = round(time.perf_counter() - t_s2, 3)
        s2.status = "COMPLETED"
        deps_count = len(lineage_data.get("dependencies", []))
        consumers_count = len(lineage_data.get("consumers", []))
        s2.output_summary = f"{deps_count} total dependencies, {consumers_count} downstream consumers"
        s2.details = lineage_data

        if on_step_end:
            on_step_end(s2)

        # ======================================================================
        # STEP 3: PL/SQL Code Pattern Scanning
        # ======================================================================
        s3 = WorkflowStep(
            step_number=3,
            name="PL/SQL Code Pattern Scanning",
            description=f"Scan all packages and triggers for code occurrences of '{target_clean}'",
        )
        self.steps.append(s3)
        if on_step_start:
            on_step_start(s3)
        t_s3 = time.perf_counter()

        grep_results = grep_plsql_code(self.schemas, pattern=target_clean, max_results=15)
        s3.duration_seconds = round(time.perf_counter() - t_s3, 3)
        s3.status = "COMPLETED"
        s3.output_summary = f"{len(grep_results)} code occurrences identified in packages/triggers"
        s3.details = {"matches": grep_results}

        if on_step_end:
            on_step_end(s3)

        # ======================================================================
        # STEP 4: AI Risk Assessment & Mitigation Synthesis
        # ======================================================================
        s4 = WorkflowStep(
            step_number=4,
            name="AI Risk Assessment & Report Synthesis",
            description="Delegate to Lineage Auditor Specialist to synthesize the technical impact report",
        )
        self.steps.append(s4)
        if on_step_start:
            on_step_start(s4)
        t_s4 = time.perf_counter()

        ai_prompt = (
            f"Generate a comprehensive Impact Assessment & Risk Report for modifying database object '{target_clean}'.\n\n"
            f"### TECHNICAL FINDINGS COLLECTED:\n"
            f"- Schema & Metadata: {json.dumps(schema_data, ensure_ascii=False)}\n"
            f"- Lineage & Consumers: {json.dumps(lineage_data, ensure_ascii=False)}\n"
            f"- Code Matches: {json.dumps(grep_results, ensure_ascii=False)}\n\n"
            f"STRUCTURE YOUR REPORT WITH:\n"
            f"1. Executive Summary & Modification Objective\n"
            f"2. Risk Level (LOW / MEDIUM / HIGH / CRITICAL) with justification\n"
            f"3. Impacted Downstream Objects (Views, Triggers, Packages, Web/Batch routines)\n"
            f"4. Code Modification Checklist & Precautions\n"
            f"5. Recommended Rollback Strategy\n"
            f"Include a valid Mermaid diagram visualizing the dependencies."
        )

        ai_report = execute_subagent(
            role="lineage_auditor",
            task=ai_prompt,
            schemas=self.schemas,
            config=self.config,
            client=self.client,
            on_token=on_token,
        )

        s4.duration_seconds = round(time.perf_counter() - t_s4, 3)
        s4.status = "COMPLETED"
        s4.output_summary = "Technical impact & risk assessment generated successfully"
        s4.details = {"report": ai_report}

        if on_step_end:
            on_step_end(s4)

        total_dur = round(time.perf_counter() - start_time, 3)

        # Build full Markdown document
        full_md = (
            f"# 🛡️ LEAI Impact Assessment Report: `{target_clean}`\n\n"
            f"- **Target Object:** `{target_clean}`\n"
            f"- **Total Duration:** {total_dur}s\n"
            f"- **Pipeline Steps Completed:** {len(self.steps)}/4\n\n"
            f"---\n\n"
            f"## 📋 Execution Steps Summary\n"
            + "\n".join(
                f"- **Step {step.step_number} [{step.name}]:** {step.output_summary} ({step.duration_seconds}s)" for step in self.steps
            )
            + "\n\n---\n\n"
            + ai_report
        )

        return WorkflowResult(
            workflow_name=self.name,
            target=target_clean,
            success=True,
            summary=f"Impact analysis completed for '{target_clean}' in {total_dur}s.",
            total_duration_seconds=total_dur,
            steps=self.steps,
            artifacts={
                "schema": schema_data,
                "lineage": lineage_data,
                "code_occurrences": grep_results,
            },
            report_markdown=full_md,
        )
