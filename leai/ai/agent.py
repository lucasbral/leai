from __future__ import annotations

import json
from typing import Any, Callable

from leai.ai.base import BaseLLMClient
from leai.ai.tools import DATABASE_TOOLS_DEFINITIONS, execute_tool_call
from leai.config import LeaiConfig
from leai.models import SchemaMetadata

# ==============================================================================
# CONFIGURAÇÃO DE SEGURANÇA E EXECUÇÃO DO AGENTE
# ==============================================================================
# Número máximo de iterações/investigações que o agente pode realizar por turno.
# Altere esta constante conforme a necessidade de profundidade do raciocínio.
MAX_AGENT_ITERATIONS: int = 10
# ==============================================================================


AGENT_SYSTEM_PROMPT = """You are the LEAI Autonomous Oracle Database Architect and DBA Copilot.
You have access to specialized tools to inspect the real Oracle database schema, view definitions, PL/SQL subprogram code, dependency lineage, and code occurrences.

CORE OPERATING PRINCIPLES:
1. Always use tools to verify facts before answering questions about database objects, column names, constraints, or PL/SQL logic.
2. For SQL generation, inspect the relevant table schemas first (`get_table_schema`) to use exact column names and verify primary/foreign keys.
3. For PL/SQL questions, extract the exact routine source code (`get_subprogram_source`) or trace dependencies (`trace_object_lineage`).
4. If searching for a constant, keyword, error message, or column usage across routines, use `grep_plsql_code`.
5. SYNONYMS RESOLUTION: In Oracle, procedures, packages, tables, and views are frequently exposed via SYNONYMS across schemas. If an object is a SYNONYM, explain what it is an alias for, identify its base target object, and use `get_subprogram_source` or `get_table_schema` to inspect and explain the underlying business routine or table.
6. Once you have gathered sufficient information from the tools, synthesize a clear, comprehensive, and well-structured response in Portuguese (unless the user asks in another language).
"""


class AgentExecutionEngine:
    """Autonomous multi-step Tool-Calling Execution Engine for LEAI."""

    def __init__(
        self,
        schemas: list[SchemaMetadata],
        config: LeaiConfig,
        client: BaseLLMClient,
        max_iterations: int = MAX_AGENT_ITERATIONS,
    ):
        self.schemas = schemas
        self.config = config
        self.client = client
        self.max_iterations = max_iterations

    def run(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str | None = None,
        on_tool_start: Callable[[str, dict[str, Any]], None] | None = None,
        on_tool_end: Callable[[str, str], None] | None = None,
    ) -> str:
        """Executes the autonomous agent reasoning loop with tool calling up to MAX_AGENT_ITERATIONS."""
        sys_prompt = (system_prompt or AGENT_SYSTEM_PROMPT).strip()
        working_messages = list(messages)

        for iteration in range(1, self.max_iterations + 1):
            # Call LLM with tool definitions
            content, tool_calls = self.client.generate_chat_with_tools(
                working_messages,
                tools=DATABASE_TOOLS_DEFINITIONS,
                system_prompt=sys_prompt,
            )

            # If no tool calls were requested, we reached the final synthesis
            if not tool_calls:
                return content or "Não foi possível obter uma resposta do modelo."

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
                            "arguments": json.dumps(tc["arguments"], ensure_ascii=False) if isinstance(tc["arguments"], dict) else str(tc["arguments"]),
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

                if on_tool_start:
                    on_tool_start(t_name, t_args)

                # Execute tool against in-memory schemas and raw dependencies
                tool_output = execute_tool_call(
                    tool_name=t_name,
                    arguments=t_args,
                    schemas=self.schemas,
                    config=self.config,
                )

                if on_tool_end:
                    on_tool_end(t_name, tool_output)

                working_messages.append({
                    "role": "tool",
                    "tool_call_id": t_id,
                    "name": t_name,
                    "content": tool_output,
                })

        # If max iterations reached, do a final direct synthesis call without tools
        final_synth = self.client.generate_chat(
            working_messages,
            system_prompt=sys_prompt + "\n\nResuma e conclua a resposta final com base nas informações coletadas pelas ferramentas.",
        )
        return final_synth
