from __future__ import annotations

import json
import time
from typing import Any, Callable

from leai.ai.base import BaseLLMClient
from leai.ai.tools import DATABASE_TOOLS_DEFINITIONS, execute_tool_call, summarize_tool_result
from leai.audit import ToolExecutionAudit
from leai.config import LeaiConfig
from leai.models import SchemaMetadata

# ==============================================================================
# AGENT SAFETY AND EXECUTION CONFIGURATION
# ==============================================================================
# Maximum number of tool iterations the agent can perform per turn.
# Adjust this constant depending on desired depth of reasoning.
MAX_AGENT_ITERATIONS: int = 10
# ==============================================================================


AGENT_SYSTEM_PROMPT = """You are the LEAI Autonomous Oracle Database Architect and DBA Copilot.
You have access to specialized tools to inspect the real Oracle database schema, view definitions, PL/SQL subprogram code, dependency lineage, code occurrences, and business documentation / YAML annotations.

CORE OPERATING PRINCIPLES:
1. ALWAYS use tools to verify facts before answering questions about database objects, column names, constraints, or PL/SQL logic.
2. CRITICAL ZERO-PREAMBLE RULE DURING TOOL EXECUTION:
   - When investigating or calling tools, output ZERO conversational text.
   - NEVER output preambles, plans, or promises such as "I will search...", "Let's follow the dual-discovery protocol...", or numbered investigation steps.
   - NEVER output tool call JSON specifications in markdown code blocks or conversational text.
   - Invoke tools EXCLUSIVELY via the native function-calling API channel.
   - Conversational text is ONLY permitted after all necessary tools have completed execution and you are synthesizing your final verified answer.
3. BUSINESS GLOSSARY & DOMAIN RULES PROTOCOL: When the user asks about business concepts, operational definitions, status filters, indicators, or calculation rules:
   - Call `lookup_business_term(query=...)` to check the global business glossary (`annotations/glossary.yml`).
   - If a canonical SQL filter is defined (`canonical_filter`), you MUST adopt that exact condition in your explanation and SQL queries.
4. MANDATORY DUAL-DISCOVERY PROTOCOL: When the user asks where specific data, columns, or business entities are located:
   - Execute BOTH discovery tools in your first investigation turn:
     a) `search_column_comments(query=...)` to scan all native Oracle column comments and column names.
     b) `search_business_documentation(query=...)` to scan compiled Markdown docs, YAML annotations, and business rules.
   - Once candidate tables or views are identified, call `get_table_schema(table_name=...)` on the top candidates to verify the complete schema and column comments before concluding.
5. EXPLAINING PROCEDURES, FUNCTIONS & PACKAGES: When asked to explain or understand a procedure, function, trigger, or package:
   - Call `get_subprogram_source` to read the exact PL/SQL source code and subprogram blocks.
   - Call `trace_object_lineage` to identify upstream tables/objects consumed and downstream callers/active consumers.
   - If the code modifies or queries tables with important constraints, call `get_table_schema` to verify columns and data types.
   - Structure your explanation clearly:
     • 🎯 **Functional Objective and Business Rules**
     • 📥 **Parameters and Signature**
     • 🗄️ **Tables and DML Operations**
     • 🛡️ **Logical Flow and Exception Handling**
     • 🔍 **Database Impact and Connections**
6. MODIFYING / REFACTORING PL/SQL CODE: When asked to modify, optimize, or fix a procedure or package:
   - Call `get_subprogram_source` to get the original code.
   - Call `trace_object_lineage` and `grep_plsql_code` to check other routines that call it or use the same signature, avoiding breaking changes.
   - Call `get_table_schema` for all tables impacted by the modification.
   - Deliver complete, production-grade PL/SQL code with:
     • Production-ready compilable code (`CREATE OR REPLACE PROCEDURE/PACKAGE BODY ...`).
     • Robust exception handling (`NO_DATA_FOUND`, `TOO_MANY_ROWS`, `OTHERS` with `SQLERRM`).
     • Clear explanation of what changed (diff or bullet points).
     • Anonymous unit test block (`DECLARE ... BEGIN ... END;`) for validation.
7. SYNONYMS RESOLUTION: In Oracle, procedures, packages, tables, and views are frequently exposed via SYNONYMS across schemas. If an object is a SYNONYM, identify its base target object and inspect the underlying business routine or table.
8. STRICT GROUNDING & ANTI-FABRICATION PROTOCOL:
   - NEVER fabricate, invent, or guess database object names, column names, constraints, or PL/SQL code that did not appear in tool results.
   - If a tool returns empty results or an error (e.g. table not found), you MUST explicitly tell the user that the object/column was not found in the loaded schemas.
   - ONLY cite table names, column names, data types, and code that were explicitly returned and verified by the tools in this turn.
9. IN-CONTEXT INVESTIGATION EXAMPLES:
   [CORRECT BEHAVIOR]
   User: "Which table stores sensitive customer data?"
   Assistant: [Calls search_column_comments(query='cpf, cnpj, rg, senha') and search_business_documentation(query='dados sensiveis') with ZERO conversational text]
   (After receiving tool outputs):
   Assistant: [Synthesizes final answer listing verified tables, columns, and security recommendations]

   [PROHIBITED BEHAVIOR - STRICTLY FORBIDDEN]
   User: "Which table stores sensitive customer data?"
   Assistant: "To find sensitive tables, let's follow the dual-discovery protocol: {"name": "search_column_comments"...}"
   [FAILURE! Never narrate what you will do. Never output tool JSON in text.]
"""


class AgentExecutionEngine:
    """Autonomous multi-step Tool-Calling Execution Engine for LEAI."""

    def __init__(
        self,
        schemas: list[SchemaMetadata],
        config: LeaiConfig,
        client: BaseLLMClient,
        max_iterations: int | None = None,
    ):
        self.schemas = schemas
        self.config = config
        self.client = client
        if max_iterations is not None:
            self.max_iterations = max_iterations
        elif config and getattr(getattr(config, "ai", None), "max_agent_iterations", None):
            self.max_iterations = config.ai.max_agent_iterations
        else:
            self.max_iterations = MAX_AGENT_ITERATIONS
        self.last_tool_audits: list[ToolExecutionAudit] = []
        self.last_working_messages: list[dict[str, Any]] = []

    def run(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str | None = None,
        on_tool_start: Callable[[str, dict[str, Any], int], None] | None = None,
        on_tool_end: Callable[[str, str, str, float], None] | None = None,
        on_token: Callable[[str], None] | None = None,
    ) -> str:
        """Executes the autonomous agent reasoning loop with tool calling up to MAX_AGENT_ITERATIONS."""
        sys_prompt = (system_prompt or AGENT_SYSTEM_PROMPT).strip()
        working_messages = list(messages)
        self.last_tool_audits = []
        tools_ran = False

        for iteration in range(1, self.max_iterations + 1):
            # Enforce tool execution on the first iteration to eliminate unverified head-answers
            tool_mode = "required" if iteration == 1 else "auto"

            # Call LLM with tool definitions
            content, tool_calls = self.client.generate_chat_with_tools(
                working_messages,
                tools=DATABASE_TOOLS_DEFINITIONS,
                system_prompt=sys_prompt,
                tool_choice_mode=tool_mode,
            )

            # If no tool calls were requested, check if model hallucinated meta-commentary on turn 1
            if not tool_calls:
                if iteration == 1 and not tools_ran and content:
                    lower_c = content.lower()
                    meta_signals = [
                        '{"name":',
                        "<tool_call>",
                        "search_column_comments",
                        "search_business_documentation",
                        "get_table_schema",
                        "lookup_business_term",
                        "get_subprogram_source",
                        "trace_object_lineage",
                        "grep_plsql_code",
                        "vou pesquisar",
                        "vamos pesquisar",
                        "vou consultar",
                        "vamos consultar",
                        "i will search",
                        "let me check",
                        "i will check",
                    ]
                    if any(sig in lower_c for sig in meta_signals):
                        # Self-correction critique reprompt: force the model to execute the tool
                        working_messages.append({"role": "assistant", "content": content})
                        working_messages.append(
                            {
                                "role": "user",
                                "content": (
                                    "EXECUTION PROTOCOL ERROR: You replied with conversational text or promised to execute tools "
                                    "instead of actually calling them via the tools API. "
                                    "Do NOT explain your plan or output JSON as text. "
                                    "CALL the appropriate tool immediately via the function-calling channel."
                                ),
                            }
                        )
                        continue

                # Normal termination: synthesize final answer
                if not tools_ran and not content:
                    # Try streaming chat directly
                    if hasattr(self.client, "stream_chat") and callable(self.client.stream_chat):
                        content = self.client.stream_chat(working_messages, system_prompt=sys_prompt, on_chunk=on_token)
                elif on_token and callable(on_token) and content:
                    on_token(content)
                res = content or "Could not obtain a response from the model."
                if content:
                    working_messages.append({"role": "assistant", "content": content})
                self.last_working_messages = list(working_messages)
                return res

            tools_ran = True
            # If tool calls were returned, process them
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

            # Execute each requested tool
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

                # Execute tool against in-memory schemas and raw dependencies
                tool_output = execute_tool_call(
                    tool_name=t_name,
                    arguments=t_args,
                    schemas=self.schemas,
                    config=self.config,
                    client=self.client,
                )
                t_dur = time.perf_counter() - t_start
                summary = summarize_tool_result(t_name, t_args, tool_output)

                parsed_out = None
                try:
                    parsed_out = json.loads(tool_output)
                except Exception:
                    parsed_out = None

                audit_rec = ToolExecutionAudit(
                    step=step_idx,
                    tool_name=t_name,
                    arguments=t_args,
                    model_thought=content or None,
                    output_data=parsed_out,
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

        # If tools ran or max iterations reached, synthesize final answer with streaming and strict grounding
        synth_prompt = (
            sys_prompt
            + "\n\n## SYNTHESIS INSTRUCTIONS & GROUNDING RULES:\n"
            + "Synthesize the final response based strictly on the information gathered by the tools above.\n"
            + "1. ONLY cite tables, columns, routines, and rules that were confirmed by the tool results.\n"
            + "2. If a requested object or column was not found by the tools, state clearly that it was not found in the schemas.\n"
            + "3. NEVER invent or assume database structures not present in the tool outputs.\n"
            + "4. Respond in the same language as the user's query."
        )
        if hasattr(self.client, "stream_chat") and callable(self.client.stream_chat):
            final_synth = self.client.stream_chat(
                working_messages,
                system_prompt=synth_prompt,
                on_chunk=on_token,
            )
        else:
            final_synth = self.client.generate_chat(
                working_messages,
                system_prompt=synth_prompt,
            )
            if on_token and callable(on_token) and final_synth:
                on_token(final_synth)
        if final_synth:
            working_messages.append({"role": "assistant", "content": final_synth})
        self.last_working_messages = list(working_messages)
        return final_synth
