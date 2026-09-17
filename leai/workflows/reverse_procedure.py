from __future__ import annotations

import re
import time
from typing import Callable

from leai.ai.base import BaseLLMClient
from leai.ai.tools import get_subprogram_source, trace_object_lineage
from leai.config import LeaiConfig
from leai.models import SchemaMetadata
from leai.workflows.base import BaseWorkflow, WorkflowResult, WorkflowStep


class ReverseProcedureWorkflow(BaseWorkflow):
    """Executes an end-to-end reverse-engineering workflow for PL/SQL procedures, functions, and packages."""

    def __init__(
        self,
        schemas: list[SchemaMetadata],
        config: LeaiConfig,
        client: BaseLLMClient,
    ):
        super().__init__(
            name="reverse-procedure",
            description="Decompiles and specifies PL/SQL procedures: extracts source, maps CRUD tables, traces outgoing calls, identifies business rules, and generates Mermaid flowcharts.",
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
        target_clean = target.strip().upper().lstrip("@")
        self.steps = []

        # ======================================================================
        # STEP 1: Source Code Extraction & Header Parsing
        # ======================================================================
        s1 = WorkflowStep(
            step_number=1,
            name="Source Code Extraction",
            description=f"Extract PL/SQL source code and parameter signatures for '{target_clean}'",
        )
        self.steps.append(s1)
        if on_step_start:
            on_step_start(s1)
        t_s1 = time.perf_counter()

        package_name = None
        subprogram_name = target_clean
        if "." in target_clean:
            parts = target_clean.split(".", 1)
            package_name = parts[0]
            subprogram_name = parts[1]

        source_data = get_subprogram_source(
            self.schemas,
            package_name=package_name,
            subprogram_name=subprogram_name,
        )
        s1.duration_seconds = round(time.perf_counter() - t_s1, 3)

        source_code = ""
        object_type = "PROCEDURE"
        subprograms_list = []
        if isinstance(source_data, dict) and ("source_code" in source_data or "source" in source_data):
            source_code = source_data.get("source_code") or source_data.get("source") or ""
            object_type = source_data.get("subprogram_type") or source_data.get("object_type", "PROCEDURE")
            subprograms_list = source_data.get("subprograms", [])
        elif isinstance(source_data, dict) and "error" in source_data:
            for s in self.schemas:
                for co in s.code_objects:
                    if co.name.upper() == target_clean:
                        source_code = co.source or ""
                        object_type = co.object_type
                        break
                if source_code:
                    break

        line_count = len(source_code.splitlines()) if source_code else 0
        s1.status = "COMPLETED" if source_code else "FAILED"
        s1.output_summary = (
            f"{line_count} lines of PL/SQL extracted ({object_type})" if source_code else f"Object '{target_clean}' not found"
        )
        s1.details = {
            "object_name": target_clean,
            "object_type": object_type,
            "line_count": line_count,
            "subprograms": subprograms_list,
        }
        if on_step_end:
            on_step_end(s1)

        if not source_code:
            dur = round(time.perf_counter() - start_time, 3)
            return WorkflowResult(
                workflow_name=self.name,
                target=target_clean,
                success=False,
                total_duration_seconds=dur,
                steps=self.steps,
                summary=f"Failed to reverse engineer '{target_clean}': Source code not found in schemas.",
                report_markdown=f"# Reverse Engineering: {target_clean}\n\n❌ **Error:** Source code for `{target_clean}` was not found in loaded schemas.",
            )

        # ======================================================================
        # STEP 2: CRUD & Table I/O Analysis (Read vs Write Tables)
        # ======================================================================
        s2 = WorkflowStep(
            step_number=2,
            name="CRUD & Table I/O Analysis",
            description=f"Map tables accessed for reading (SELECT) and modification (INSERT, UPDATE, DELETE, MERGE) in '{target_clean}'",
        )
        self.steps.append(s2)
        if on_step_start:
            on_step_start(s2)
        t_s2 = time.perf_counter()

        read_tables: set[str] = set()
        insert_tables: set[str] = set()
        update_tables: set[str] = set()
        delete_tables: set[str] = set()
        merge_tables: set[str] = set()

        for match in re.finditer(r"\b(?:FROM|JOIN)\s+([a-zA-Z0-9_$#\.]+)", source_code, re.IGNORECASE):
            tbl = match.group(1).strip().split(".")[-1].upper()
            if not tbl.startswith("(") and tbl not in ("DUAL", "TABLE"):
                read_tables.add(tbl)

        for match in re.finditer(r"\bINSERT\s+INTO\s+([a-zA-Z0-9_$#\.]+)", source_code, re.IGNORECASE):
            tbl = match.group(1).strip().split(".")[-1].upper()
            insert_tables.add(tbl)
            read_tables.discard(tbl)

        for match in re.finditer(r"\bUPDATE\s+([a-zA-Z0-9_$#\.]+)\s+SET\b", source_code, re.IGNORECASE):
            tbl = match.group(1).strip().split(".")[-1].upper()
            update_tables.add(tbl)
            read_tables.discard(tbl)

        for match in re.finditer(r"\bDELETE\s+(?:FROM\s+)?([a-zA-Z0-9_$#\.]+)", source_code, re.IGNORECASE):
            tbl = match.group(1).strip().split(".")[-1].upper()
            delete_tables.add(tbl)
            read_tables.discard(tbl)

        for match in re.finditer(r"\bMERGE\s+INTO\s+([a-zA-Z0-9_$#\.]+)", source_code, re.IGNORECASE):
            tbl = match.group(1).strip().split(".")[-1].upper()
            merge_tables.add(tbl)
            read_tables.discard(tbl)

        s2.duration_seconds = round(time.perf_counter() - t_s2, 3)
        s2.status = "COMPLETED"
        all_writes = insert_tables | update_tables | delete_tables | merge_tables
        s2.output_summary = f"{len(read_tables)} read tables, {len(all_writes)} write tables"
        s2.details = {
            "read_tables": sorted(read_tables),
            "insert_tables": sorted(insert_tables),
            "update_tables": sorted(update_tables),
            "delete_tables": sorted(delete_tables),
            "merge_tables": sorted(merge_tables),
        }
        if on_step_end:
            on_step_end(s2)

        # ======================================================================
        # STEP 3: Outgoing Routine Calls & Dependencies
        # ======================================================================
        s3 = WorkflowStep(
            step_number=3,
            name="Call Graph & Outgoing Dependencies",
            description=f"Identify invocations to packages, procedures, functions, and system utilities in '{target_clean}'",
        )
        self.steps.append(s3)
        if on_step_start:
            on_step_start(s3)
        t_s3 = time.perf_counter()

        called_routines: set[str] = set()
        system_packages: set[str] = set()

        call_matches = re.finditer(r"\b([a-zA-Z0-9_$#]+)\.([a-zA-Z0-9_$#]+)\s*\(", source_code, re.IGNORECASE)
        for cm in call_matches:
            pkg = cm.group(1).upper()
            proc = cm.group(2).upper()
            if pkg in (
                "DBMS_OUTPUT",
                "DBMS_SQL",
                "DBMS_LOB",
                "DBMS_LOCK",
                "DBMS_JOB",
                "DBMS_SCHEDULER",
                "UTL_FILE",
                "UTL_HTTP",
                "UTL_RAW",
                "UTL_MAIL",
            ):
                system_packages.add(f"{pkg}.{proc}")
            else:
                called_routines.add(f"{pkg}.{proc}")

        lineage_meta = trace_object_lineage(self.schemas, target_clean, depth=1)
        if isinstance(lineage_meta, dict):
            for dep in lineage_meta.get("dependencies", []):
                obj_n = dep.get("object_name", "")
                if dep.get("object_type") in ("PACKAGE", "PACKAGE BODY", "PROCEDURE", "FUNCTION"):
                    called_routines.add(obj_n)

        s3.duration_seconds = round(time.perf_counter() - t_s3, 3)
        s3.status = "COMPLETED"
        s3.output_summary = f"{len(called_routines)} external routines, {len(system_packages)} system packages"
        s3.details = {
            "called_routines": sorted(called_routines),
            "system_packages": sorted(system_packages),
        }
        if on_step_end:
            on_step_end(s3)

        # ======================================================================
        # STEP 4: Business Rules & Execution Flow Synthesis (AI-Powered)
        # ======================================================================
        s4 = WorkflowStep(
            step_number=4,
            name="Business Rules & Logic Decomposition",
            description=f"Deconstruct conditional branches, validations, and functional logic of '{target_clean}'",
        )
        self.steps.append(s4)
        if on_step_start:
            on_step_start(s4)
        t_s4 = time.perf_counter()

        ai_synthesis = ""
        lang = getattr(self.config, "language", "en-US") if self.config else "en-US"
        from leai.ai.prompts import build_language_directive

        truncated_code = source_code
        if len(truncated_code) > 20000:
            truncated_code = truncated_code[:20000] + "\n\n-- [TRUNCATED FOR CONTEXT LIMIT]"

        writes_desc = ", ".join(sorted(all_writes)) if all_writes else "None (Read-only)"
        prompt = f"""You are a Lead Oracle Database Reverse-Engineering Specialist and Enterprise Architect.
Reverse-engineer the following PL/SQL routine '{target_clean}':

### [PL/SQL SOURCE CODE]
```sql
{truncated_code}
```

### [IDENTIFIED METADATA]
- Read Tables: {", ".join(sorted(read_tables)) or "None"}
- Write Tables: {writes_desc}
- Called Routines: {", ".join(sorted(called_routines)) or "None"}
- System Packages: {", ".join(sorted(system_packages)) or "None"}

### [REQUIRED REVERSE-ENGINEERING DELIVERABLES]
1. **Executive Functional Purpose**: High-level explanation of what this procedure achieves in business terms.
2. **Parameters & Interface**: Table with parameter names, mode (IN/OUT/IN OUT), data type, default values, and functional business purpose.
3. **Identified Business Rules**: Numbered list of all business validation rules, constraints, calculation formulas, and state transitions.
4. **CRUD & Data State Impact**: Table mapping each affected entity and the nature of modifications (Insert, Update, Delete).
5. **Exception Handling & Rollback Strategy**: Error scenarios handled, custom exceptions raised, and transaction control (COMMIT/ROLLBACK/SAVEPOINT).
6. **Mermaid Flowchart Diagram**: A valid `mermaid` flowchart (`flowchart TD`) showing the step-by-step decision flow, loops, and external calls.

{build_language_directive(lang)}
"""
        if self.client and hasattr(self.client, "generate_text") and callable(self.client.generate_text):
            try:
                ai_synthesis = self.client.generate_text(
                    prompt,
                    system_prompt="You are a Principal Oracle PL/SQL Reverse Engineering and Database Architecture Specialist.",
                )
            except Exception as exc:
                ai_synthesis = f"*(AI synthesis unavailable: {exc})*"
        else:
            ai_synthesis = "reverse-procedure analysis completed."

        s4.duration_seconds = round(time.perf_counter() - t_s4, 3)
        s4.status = "COMPLETED"
        s4.output_summary = "Functional rules, parameters, and Mermaid flowchart synthesized"
        s4.details = {"synthesis_length": len(ai_synthesis)}
        if on_step_end:
            on_step_end(s4)

        # ======================================================================
        # STEP 5: Assembly of Complete Functional Markdown Specification
        # ======================================================================
        total_duration = round(time.perf_counter() - start_time, 3)

        report_lines = [
            f"# Reverse Engineering Specification: `{target_clean}`",
            "",
            f"- **Object Type:** {object_type}",
            f"- **Lines of Code:** {line_count}",
            f"- **Read Tables (SELECT):** {', '.join(sorted(read_tables)) if read_tables else 'None'}",
            f"- **Write Tables (DML):** {', '.join(sorted(all_writes)) if all_writes else 'None (Read-only)'}",
            f"- **External Routine Dependencies:** {', '.join(sorted(called_routines)) if called_routines else 'None'}",
            f"- **Analysis Duration:** {total_duration}s",
            "",
            "---",
            "",
            "## 📋 Technical CRUD Matrix",
            "",
            "| Table Name | Operation | Detail |",
            "|---|---|---|",
        ]

        for t in sorted(read_tables):
            report_lines.append(f"| `{t}` | `READ (SELECT)` | Query / Lookup |")
        for t in sorted(insert_tables):
            report_lines.append(f"| `{t}` | `CREATE (INSERT)` | New record insertion |")
        for t in sorted(update_tables):
            report_lines.append(f"| `{t}` | `UPDATE` | Field mutation / State transition |")
        for t in sorted(delete_tables):
            report_lines.append(f"| `{t}` | `DELETE` | Record purge |")
        for t in sorted(merge_tables):
            report_lines.append(f"| `{t}` | `MERGE` | Upsert conditional operation |")

        if not read_tables and not all_writes:
            report_lines.append("| *(None)* | *(None)* | Pure computation / utility routine |")

        report_lines.append("")
        report_lines.append("---")
        report_lines.append("")
        report_lines.append("## 🔍 Functional Specification & Business Logic")
        report_lines.append("")
        report_lines.append(ai_synthesis)

        final_report = "\n".join(report_lines)
        if on_token and callable(on_token):
            on_token(final_report)

        return WorkflowResult(
            workflow_name=self.name,
            target=target_clean,
            success=True,
            total_duration_seconds=total_duration,
            steps=self.steps,
            summary=(
                f"Reverse engineering of '{target_clean}' completed in {total_duration}s. "
                f"Mapped {len(read_tables)} read table(s), {len(all_writes)} write table(s), and {len(called_routines)} external call(s)."
            ),
            report_markdown=final_report,
        )
