from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from leai.ai.base import BaseLLMClient
from leai.ai.tools import DATABASE_TOOLS_DEFINITIONS, execute_tool_call, summarize_tool_result
from leai.audit import ToolExecutionAudit
from leai.config import LeaiConfig
from leai.models import SchemaMetadata


@dataclass
class SubagentConfig:
    """Configuration and personality definition for a specialized subagent."""

    role: str
    name: str
    description: str
    system_prompt: str
    allowed_tool_names: list[str] = field(default_factory=list)
    max_iterations: int = 5


# ==============================================================================
# SUBAGENT SPECIALIST SYSTEM PROMPTS
# ==============================================================================

CATALOG_RESEARCHER_PROMPT = """You are the LEAI Database Catalog Researcher Specialist.
Your primary role is to rapidly discover, locate, and map database objects, column comments (ALL_COL_COMMENTS), data types, constraints, and synonyms in the Oracle schema.

OPERATING RULES:
1. Use `search_column_comments`, `search_database_objects`, and `get_table_schema` to locate the exact objects.
2. If given a synonym name, dereference it and inspect the base table or view.
3. Deliver a concise, factual summary listing the exact table names, column names, data types, and primary/foreign key relationships found.
4. NEVER guess or invent table or column names that did not appear in tool results.
"""

PLSQL_ANALYST_PROMPT = """You are the LEAI PL/SQL & Subprogram Logic Analyst Specialist.
Your primary role is deep reverse engineering, understanding business rules, and inspecting PL/SQL procedures, functions, packages, and triggers.

OPERATING RULES:
1. Always retrieve the original code with `get_subprogram_source` and inspect occurrences with `grep_plsql_code`.
2. Inspect target table schemas using `get_table_schema` to verify columns and data types manipulated by DML operations.
3. Structure your output clearly:
   - 🎯 **Functional Objective & Business Rules**
   - 📥 **Parameters and Signatures (`IN`, `OUT`, `IN OUT`)**
   - 🗄️ **Tables and DML Operations (`SELECT`, `INSERT`, `UPDATE`, `DELETE`)**
   - 🛡️ **Logical Flow, Cursors & Exception Handling**
4. Deliver clear, precise, and well-structured technical analysis.
"""

LINEAGE_AUDITOR_PROMPT = """You are the LEAI Lineage & Dependency Auditor Specialist.
Your primary role is to map the relational and programmatic dependency graph of database objects and assess technical risk.

OPERATING RULES:
1. Always run `trace_object_lineage` to uncover upstream parents, downstream children, foreign key references, and active consumers.
2. If the target is a SYNONYM, identify its target object and owner.
3. Synthesize the findings into:
   - 🌐 **Direct Dependencies (Upstream Tables & Packages Consumed)**
   - 👥 **Callers and Active Consumers (Downstream Packages & Triggers Affected)**
   - ⚠️ **Impact & Risk Assessment (HIGH / MEDIUM / LOW)**
4. Provide a clear recommendation on precautions before modifying the target object.
"""

PATCH_GENERATOR_PROMPT = """You are the LEAI Safe SQL & PL/SQL Patch Writer Specialist.
Your primary role is to generate production-grade, compilable, and robust SQL/PLSQL code modifications, refactorings, and unit test blocks.

OPERATING RULES:
1. Inspect the original code with `get_subprogram_source` and impacted table schemas with `get_table_schema`.
2. Always deliver complete, production-ready code with `CREATE OR REPLACE ...`.
3. Include defensive exception handling (`NO_DATA_FOUND`, `TOO_MANY_ROWS`, `WHEN OTHERS THEN ...`).
4. Include an anonymous unit test block (`DECLARE ... BEGIN ... END;`) to safely validate execution.
5. Provide a rollback script or explanation.
"""

DOC_ANNOTATOR_PROMPT = """You are the LEAI Semantic Documentation & Business Rules Specialist.
Your primary role is to extract business context, domain tags, functional rules, and human annotations for database objects.

OPERATING RULES:
1. Consult existing documentation via `search_business_documentation` and schema metadata with `get_table_schema`.
2. Synthesize clear business-level explanations of what the table or routine accomplishes in the organization.
3. Extract up to 3 inferred business rules, practical use cases, and domain classification tags.
"""


# ==============================================================================
# SUBAGENT REGISTRY
# ==============================================================================

SUBAGENT_REGISTRY: dict[str, SubagentConfig] = {
    "catalog_researcher": SubagentConfig(
        role="catalog_researcher",
        name="Catalog & Schema Researcher",
        description="Fast discovery of tables, columns, comments, constraints, and synonyms.",
        system_prompt=CATALOG_RESEARCHER_PROMPT,
        allowed_tool_names=["search_database_objects", "search_column_comments", "get_table_schema"],
        max_iterations=5,
    ),
    "plsql_analyst": SubagentConfig(
        role="plsql_analyst",
        name="PL/SQL & Logic Analyst",
        description="Deep analysis and reverse engineering of procedures, functions, packages, and triggers.",
        system_prompt=PLSQL_ANALYST_PROMPT,
        allowed_tool_names=["get_subprogram_source", "grep_plsql_code", "get_table_schema"],
        max_iterations=6,
    ),
    "lineage_auditor": SubagentConfig(
        role="lineage_auditor",
        name="Lineage & Impact Auditor",
        description="Maps technical dependencies, consumers, and assesses modification risk.",
        system_prompt=LINEAGE_AUDITOR_PROMPT,
        allowed_tool_names=["trace_object_lineage", "search_database_objects"],
        max_iterations=4,
    ),
    "patch_generator": SubagentConfig(
        role="patch_generator",
        name="Safe Patch & Code Generator",
        description="Generates compilable PL/SQL routines, exception handling, unit tests, and rollback scripts.",
        system_prompt=PATCH_GENERATOR_PROMPT,
        allowed_tool_names=["get_table_schema", "get_subprogram_source", "grep_plsql_code"],
        max_iterations=5,
    ),
    "doc_annotator": SubagentConfig(
        role="doc_annotator",
        name="Semantic Documentation Annotator",
        description="Synthesizes business descriptions, functional rules, and use cases.",
        system_prompt=DOC_ANNOTATOR_PROMPT,
        allowed_tool_names=["search_business_documentation", "get_table_schema"],
        max_iterations=4,
    ),
}


def list_registered_subagents() -> list[dict[str, Any]]:
    """Returns a serializable list of all registered subagents and their metadata."""
    return [
        {
            "role": cfg.role,
            "name": cfg.name,
            "description": cfg.description,
            "allowed_tools": list(cfg.allowed_tool_names),
            "max_iterations": cfg.max_iterations,
        }
        for cfg in SUBAGENT_REGISTRY.values()
    ]


class SubagentRunner:
    """Executes a specialized subagent in clean, isolated context."""

    def __init__(
        self,
        config_obj: SubagentConfig,
        schemas: list[SchemaMetadata],
        config: LeaiConfig,
        client: BaseLLMClient,
    ):
        self.config_obj = config_obj
        self.schemas = schemas
        self.config = config
        self.client = client
        self.last_tool_audits: list[ToolExecutionAudit] = []

    def filter_tools(self) -> list[dict[str, Any]]:
        """Filters the global tool definitions to include only tools allowed for this specialist."""
        allowed_set = set(self.config_obj.allowed_tool_names)
        return [t for t in DATABASE_TOOLS_DEFINITIONS if t.get("function", {}).get("name") in allowed_set]

    def run(
        self,
        task: str,
        on_token: Callable[[str], None] | None = None,
        on_tool_start: Callable[[str, dict[str, Any], int], None] | None = None,
        on_tool_end: Callable[[str, str, str, float], None] | None = None,
    ) -> str:
        """Runs the subagent loop on the isolated task."""
        tools = self.filter_tools()
        sys_prompt = self.config_obj.system_prompt.strip()
        working_messages: list[dict[str, Any]] = [{"role": "user", "content": task}]
        self.last_tool_audits = []
        tools_ran = False

        for iteration in range(1, self.config_obj.max_iterations + 1):
            tool_mode = "required" if iteration == 1 and tools else "auto"

            content, tool_calls = self.client.generate_chat_with_tools(
                working_messages,
                tools=tools,
                system_prompt=sys_prompt,
                tool_choice_mode=tool_mode,
            )

            if not tool_calls:
                if not tools_ran and not content:
                    if hasattr(self.client, "stream_chat") and callable(self.client.stream_chat):
                        content = self.client.stream_chat(working_messages, system_prompt=sys_prompt, on_chunk=on_token)
                elif on_token and callable(on_token) and content:
                    on_token(content)
                return content or "No response from specialist."

            tools_ran = True
            assistant_msg: dict[str, Any] = {
                "role": "assistant",
                "content": content or "",
                "tool_calls": [
                    {
                        "id": tc.get("id", f"call_{i}"),
                        "type": "function",
                        "thought_signature": tc.get("thought_signature"),
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc["arguments"], ensure_ascii=False)
                            if isinstance(tc["arguments"], dict)
                            else str(tc["arguments"]),
                            "thought_signature": tc.get("thought_signature"),
                        },
                    }
                    for i, tc in enumerate(tool_calls)
                ],
            }
            working_messages.append(assistant_msg)

            for tc in tool_calls:
                t_name = tc.get("name", "")
                t_args = tc.get("arguments", {})
                t_id = tc.get("id", f"call_{t_name}")
                step_idx = len(self.last_tool_audits) + 1

                t_start = time.perf_counter()
                if on_tool_start:
                    try:
                        on_tool_start(t_name, t_args, step_idx)
                    except TypeError:
                        on_tool_start(t_name, t_args)

                tool_output = execute_tool_call(
                    tool_name=t_name,
                    arguments=t_args,
                    schemas=self.schemas,
                    config=self.config,
                )
                t_dur = time.perf_counter() - t_start
                summary = summarize_tool_result(t_name, t_args, tool_output)

                audit_rec = ToolExecutionAudit(
                    step=step_idx,
                    tool_name=t_name,
                    arguments=t_args,
                    raw_output=tool_output,
                    summary=summary,
                    duration_seconds=round(t_dur, 4),
                )
                self.last_tool_audits.append(audit_rec)

                if on_tool_end:
                    try:
                        on_tool_end(t_name, tool_output, summary, t_dur)
                    except TypeError:
                        on_tool_end(t_name, tool_output)

                working_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": t_id,
                        "name": t_name,
                        "content": tool_output,
                    }
                )

        # Final synthesis
        synth_prompt = (
            sys_prompt
            + "\n\nSynthesize your final specialized answer based on the tool results above. Be precise, structured, and factual."
        )
        if hasattr(self.client, "stream_chat") and callable(self.client.stream_chat):
            final_res = self.client.stream_chat(working_messages, system_prompt=synth_prompt, on_chunk=on_token)
        else:
            final_res = self.client.generate_chat(working_messages, system_prompt=synth_prompt)
            if on_token and callable(on_token) and final_res:
                on_token(final_res)
        return final_res


def execute_subagent(
    role: str,
    task: str,
    schemas: list[SchemaMetadata],
    config: LeaiConfig,
    client: BaseLLMClient,
    on_token: Callable[[str], None] | None = None,
    on_tool_start: Callable[[str, dict[str, Any], int], None] | None = None,
    on_tool_end: Callable[[str, str, str, float], None] | None = None,
) -> str:
    """Dispatches a task to the requested subagent specialist and returns the output."""
    cfg = SUBAGENT_REGISTRY.get(role)
    if not cfg:
        available = ", ".join(SUBAGENT_REGISTRY.keys())
        return f"Unknown subagent role '{role}'. Available specialists: {available}"

    runner = SubagentRunner(config_obj=cfg, schemas=schemas, config=config, client=client)
    return runner.run(task=task, on_token=on_token, on_tool_start=on_tool_start, on_tool_end=on_tool_end)
