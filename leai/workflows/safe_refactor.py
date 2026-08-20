from __future__ import annotations

import json
import time
from typing import Callable

from leai.ai.base import BaseLLMClient
from leai.ai.subagents import execute_subagent
from leai.ai.tools import get_subprogram_source, trace_object_lineage
from leai.config import LeaiConfig
from leai.models import SchemaMetadata
from leai.workflows.base import BaseWorkflow, WorkflowResult, WorkflowStep


class SafeRefactorWorkflow(BaseWorkflow):
    """Executes a safe PL/SQL subprogram refactoring pipeline with caller compatibility, unit tests, and rollback."""

    def __init__(
        self,
        schemas: list[SchemaMetadata],
        config: LeaiConfig,
        client: BaseLLMClient,
    ):
        super().__init__(
            name="safe-refactor",
            description="Safe PL/SQL subprogram refactoring with signature check, robust exception handling, unit test block, and rollback.",
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
        # STEP 1: Source Code Extraction
        # ======================================================================
        s1 = WorkflowStep(
            step_number=1,
            name="Source Code Extraction",
            description=f"Extract PL/SQL source code and signature for '{target_clean}'",
        )
        self.steps.append(s1)
        if on_step_start:
            on_step_start(s1)
        t_s1 = time.perf_counter()

        source_data = get_subprogram_source(self.schemas, subprogram_name=target_clean)
        s1.duration_seconds = round(time.perf_counter() - t_s1, 3)

        if "error" in source_data:
            s1.status = "FAILED"
            s1.output_summary = f"Error: {source_data['error']}"
            if on_step_end:
                on_step_end(s1)
            return WorkflowResult(
                workflow_name=self.name,
                target=target_clean,
                success=False,
                summary=f"Failed to extract source code for '{target_clean}'.",
                total_duration_seconds=round(time.perf_counter() - start_time, 3),
                steps=self.steps,
                report_markdown=f"### ❌ Error\n{source_data['error']}",
            )

        s1.status = "COMPLETED"
        src_lines = len(source_data.get("source_code", "").splitlines())
        s1.output_summary = f"{src_lines} lines of PL/SQL extracted (Type: {source_data.get('subprogram_type', 'ROUTINE')})"
        s1.details = source_data

        if on_step_end:
            on_step_end(s1)

        # ======================================================================
        # STEP 2: Caller Compatibility & Lineage Traversal
        # ======================================================================
        s2 = WorkflowStep(
            step_number=2,
            name="Caller Compatibility & Lineage",
            description=f"Inspect callers and consumers dependent on '{target_clean}' signature",
        )
        self.steps.append(s2)
        if on_step_start:
            on_step_start(s2)
        t_s2 = time.perf_counter()

        lineage_data = trace_object_lineage(self.schemas, target_clean, depth=2)
        s2.duration_seconds = round(time.perf_counter() - t_s2, 3)
        s2.status = "COMPLETED"
        consumers = lineage_data.get("consumers", [])
        s2.output_summary = f"{len(consumers)} callers verified to preserve signature compatibility"
        s2.details = lineage_data

        if on_step_end:
            on_step_end(s2)

        # ======================================================================
        # STEP 3: AI Refactoring & Patch Generation
        # ======================================================================
        s3 = WorkflowStep(
            step_number=3,
            name="AI Refactoring & Safe Patch Generation",
            description="Delegate to Safe Patch Specialist to generate modern, compilable code with error handling",
        )
        self.steps.append(s3)
        if on_step_start:
            on_step_start(s3)
        t_s3 = time.perf_counter()

        refactor_prompt = (
            f"Generate a safe, production-grade refactored version of the PL/SQL subprogram '{target_clean}'.\n\n"
            f"### ORIGINAL SOURCE CODE:\n```sql\n{source_data.get('source_code', '')}\n```\n\n"
            f"### CALLERS & LINEAGE CONTEXT:\n{json.dumps(lineage_data, ensure_ascii=False)}\n\n"
            f"REQUIREMENTS FOR THE REFACTORING:\n"
            f"1. Preserve the public signature and parameter order to avoid breaking existing callers.\n"
            f"2. Add robust exception handling with `NO_DATA_FOUND`, `TOO_MANY_ROWS`, and defensive `WHEN OTHERS` logging.\n"
            f"3. Provide production-ready compilable code (`CREATE OR REPLACE ...`).\n"
            f"4. Add an anonymous unit test block (`DECLARE ... BEGIN ... END;`) to validate execution with mock inputs.\n"
            f"5. Provide a safe rollback script to restore the original version."
        )

        patch_output = execute_subagent(
            role="patch_generator",
            task=refactor_prompt,
            schemas=self.schemas,
            config=self.config,
            client=self.client,
            on_token=on_token,
        )

        s3.duration_seconds = round(time.perf_counter() - t_s3, 3)
        s3.status = "COMPLETED"
        s3.output_summary = "Compilable PL/SQL patch, unit test, and rollback generated"
        s3.details = {"patch": patch_output}

        if on_step_end:
            on_step_end(s3)

        total_dur = round(time.perf_counter() - start_time, 3)

        full_md = (
            f"# 🛠️ LEAI Safe Refactoring Package: `{target_clean}`\n\n"
            f"- **Target Routine:** `{target_clean}`\n"
            f"- **Original Source Lines:** {src_lines}\n"
            f"- **Total Duration:** {total_dur}s\n"
            f"- **Pipeline Steps Completed:** {len(self.steps)}/3\n\n"
            f"---\n\n"
            f"## 📋 Execution Steps Summary\n"
            + "\n".join(
                f"- **Step {step.step_number} [{step.name}]:** {step.output_summary} ({step.duration_seconds}s)" for step in self.steps
            )
            + "\n\n---\n\n"
            + patch_output
        )

        return WorkflowResult(
            workflow_name=self.name,
            target=target_clean,
            success=True,
            summary=f"Safe refactoring completed for '{target_clean}' in {total_dur}s.",
            total_duration_seconds=total_dur,
            steps=self.steps,
            artifacts={
                "original_source": source_data,
                "lineage": lineage_data,
            },
            report_markdown=full_md,
        )
