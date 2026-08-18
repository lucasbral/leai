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
# CONFIGURAÇÃO DE SEGURANÇA E EXECUÇÃO DO AGENTE
# ==============================================================================
# Número máximo de iterações/investigações que o agente pode realizar por turno.
# Altere esta constante conforme a necessidade de profundidade do raciocínio.
MAX_AGENT_ITERATIONS: int = 10
# ==============================================================================


AGENT_SYSTEM_PROMPT = """You are the LEAI Autonomous Oracle Database Architect and DBA Copilot.
You have access to specialized tools to inspect the real Oracle database schema, view definitions, PL/SQL subprogram code, dependency lineage, code occurrences, and business documentation / YAML annotations.

CORE OPERATING PRINCIPLES:
1. ALWAYS use tools to verify facts before answering questions about database objects, column names, constraints, or PL/SQL logic.
2. MANDATORY DUAL-DISCOVERY PROTOCOL: When the user asks where specific data, columns, or business dates are located (e.g. 'qual tabela tem a data de recadastramento?', 'onde fica o CPF do dependente?', 'qual campo guarda o saldo de férias?'):
   - You MUST execute BOTH tools to ensure comprehensive discovery:
     a) `search_column_comments(query=...)` to scan all native Oracle column comments (`ALL_COL_COMMENTS`) and column names.
     b) `search_business_documentation(query=...)` to scan compiled Markdown docs, YAML annotations, and business rules.
   - Execute both tools in your first investigation step (in parallel or sequence).
   - Once candidate tables or views are identified (e.g. `FUNCIONARIOS`, `VINCULOS`), call `get_table_schema(table_name=...)` on the top candidates to verify the complete schema and column comments before concluding.
3. EXPLAINING PROCEDURES, FUNCTIONS & PACKAGES: When asked to explain or understand a procedure, function, trigger, or package:
   - Call `get_subprogram_source` to read the exact PL/SQL source code and subprogram blocks.
   - Call `trace_object_lineage` to identify upstream tables/objects consumed and downstream callers/active consumers.
   - If the code modifies or queries tables with important constraints, call `get_table_schema` to verify columns and data types.
   - Structure your explanation clearly:
     • 🎯 **Objetivo Funcional e Regras de Negócio**: Explicação clara do propósito da rotina.
     • 📥 **Parâmetros e Assinatura**: Detalhamento de parâmetros `IN`, `OUT`, `IN OUT` e tipos.
     • 🗄️ **Tabelas e Operações DML**: Tabelas consultadas (`SELECT`) ou modificadas (`INSERT/UPDATE/DELETE`).
     • 🛡️ **Fluxo Lógico e Tratamento de Exceções**: Validações, loops, commits e tratamento de erros.
     • 🔍 **Impacto e Conexões no Banco**: Quem consome ou depende dessa rotina.
4. MODIFYING / REFACTORING PL/SQL CODE: When asked to modify, optimize, or fix a procedure or package:
   - Call `get_subprogram_source` to get the original code.
   - Call `trace_object_lineage` and `grep_plsql_code` to check other routines that call it or use the same signature, avoiding breaking changes.
   - Call `get_table_schema` for all tables impacted by the modification.
   - Deliver complete, production-grade PL/SQL code with:
     • Código compilável pronto para execução (`CREATE OR REPLACE PROCEDURE/PACKAGE BODY ...`).
     • Tratamento robusto de exceções (`NO_DATA_FOUND`, `TOO_MANY_ROWS`, `OTHERS` com `SQLERRM`).
     • Explicação clara do que mudou (diff ou tópicos).
     • Bloco anônimo de teste unitário (`DECLARE ... BEGIN ... END;`) para validação.
5. STRICT AUTONOMOUS COMPLETION & NO META-TOOL COMMENTARY:
   - NEVER tell the user *"vou verificar o esquema..."*, *"posso usar a ferramenta get_table_schema para obter mais detalhes..."*, or *"deixe-me consultar a documentação..."* in your final response!
   - If any tool would provide useful details, CALL IT IMMEDIATELY during the reasoning loop.
   - Do NOT mention tool names to the user in your final text. Present the complete, verified answer cleanly.
6. SYNONYMS RESOLUTION: In Oracle, procedures, packages, tables, and views are frequently exposed via SYNONYMS across schemas. If an object is a SYNONYM, explain what it is an alias for, identify its base target object, and use `get_subprogram_source` or `get_table_schema` to inspect and explain the underlying business routine or table.
7. Once you have gathered sufficient information from all necessary tools, synthesize a clear, comprehensive, and well-structured response in Portuguese (unless the user asks in another language).
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
        self.last_tool_audits: list[ToolExecutionAudit] = []

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
            # Call LLM with tool definitions
            content, tool_calls = self.client.generate_chat_with_tools(
                working_messages,
                tools=DATABASE_TOOLS_DEFINITIONS,
                system_prompt=sys_prompt,
            )

            # If no tool calls were requested, we reached the final synthesis
            if not tool_calls:
                # If tools ran previously and content is empty/brief, or for direct response
                if not tools_ran and not content:
                    # Try streaming chat directly
                    if hasattr(self.client, "stream_chat") and callable(self.client.stream_chat):
                        content = self.client.stream_chat(working_messages, system_prompt=sys_prompt, on_chunk=on_token)
                elif on_token and callable(on_token) and content:
                    on_token(content)
                return content or "Não foi possível obter uma resposta do modelo."

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

        # If tools ran or max iterations reached, synthesize final answer with streaming
        synth_prompt = sys_prompt + "\n\nResuma e conclua a resposta final com base nas informações coletadas pelas ferramentas."
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
        return final_synth
