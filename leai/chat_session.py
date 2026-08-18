from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any, Callable

from leai.ai.agent import AGENT_SYSTEM_PROMPT, AgentExecutionEngine
from leai.ai.base import BaseLLMClient
from leai.ai.prompts import ASK_SYSTEM_PROMPT
from leai.ask_rag import build_rag_context
from leai.config import LeaiConfig
from leai.models import SchemaMetadata


class ChatSession:
    """Interactive multi-turn conversation session manager with Agentic Tool-Calling & Contextual RAG."""

    def __init__(
        self,
        schemas: list[SchemaMetadata],
        config: LeaiConfig,
        client: BaseLLMClient,
        max_history_turns: int = 15,
    ):
        self.schemas = schemas
        self.config = config
        self._client = client
        self.max_history_turns = max_history_turns
        self.messages: list[dict[str, Any]] = []
        self.active_entities: set[str] = set()
        self.last_turn_tokens: int | None = None
        self.total_tokens: int = 0
        self.agent_engine = AgentExecutionEngine(
            schemas=schemas,
            config=config,
            client=client,
        )

    @property
    def client(self) -> BaseLLMClient:
        return self._client

    @client.setter
    def client(self, new_client: BaseLLMClient) -> None:
        self._client = new_client
        if hasattr(self, "agent_engine") and self.agent_engine:
            self.agent_engine.client = new_client

    def add_user_message(self, content: str) -> None:
        self.messages.append({"role": "user", "content": content})
        # Limit history to prevent context window overflow
        if len(self.messages) > self.max_history_turns * 2:
            self.messages = self.messages[-(self.max_history_turns * 2) :]

    def add_assistant_message(self, content: str) -> None:
        self.messages.append({"role": "assistant", "content": content})

    def update_schemas(self, schemas: list[SchemaMetadata]) -> None:
        """Updates internal schemas metadata and engine without erasing conversation history."""
        self.schemas = schemas
        if hasattr(self, "agent_engine") and self.agent_engine:
            self.agent_engine.schemas = schemas

    def clear(self) -> None:
        """Clears session history and memory while preserving accumulated token counts."""
        self.messages.clear()
        self.active_entities.clear()
        self.last_turn_tokens = None

    def save_transcript(self, output_file: Path | None = None) -> Path:
        """Exports the conversation history formatted in Markdown."""
        now = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        target_path = output_file or Path(f"leai_chat_{now}.md")

        lines = [
            f"# LEAI Chat Session Transcript - {now}",
            f"- **Provider:** {self.client.__class__.__name__} ({self.client.model})",
            f"- **Mapped Entities:** {', '.join(self.active_entities) if self.active_entities else 'None'}",
            "",
            "---",
            "",
        ]

        for msg in self.messages:
            if msg.get("role") == "tool":
                continue
            role = "👤 **User**" if msg["role"] == "user" else "🤖 **LEAI Assistant**"
            content = msg.get("content", "")
            if content:
                lines.append(f"### {role}")
                lines.append(content)
                lines.append("")

        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text("\n".join(lines), encoding="utf-8")
        return target_path

    def send(
        self,
        user_input: str,
        on_tool_start: Callable[[str, dict[str, Any]], None] | None = None,
        on_tool_end: Callable[[str, str], None] | None = None,
        on_token: Callable[[str], None] | None = None,
    ) -> tuple[str, list[str]]:
        """Processes user input, runs agent tool execution loop, and retrieves AI response."""
        # 1. Update RAG context with the new question
        rag_context, detected = build_rag_context(user_input, self.schemas, self.config)
        for entity in detected:
            self.active_entities.add(entity)

        # 2. Assemble System Prompt with tools instruction + accumulated RAG memory
        combined_sys = (
            f"{AGENT_SYSTEM_PROMPT}\n\n"
            f"{ASK_SYSTEM_PROMPT}\n\n"
            f"### [CONVERSATION MEMORY & INITIAL SCHEMA CONTEXT]\n"
            f"Active entities in conversation: {', '.join(self.active_entities) if self.active_entities else 'None'}\n\n"
            f"Database Context Overview:\n{rag_context}"
        )

        # 3. Add user message
        self.add_user_message(user_input)

        # 4. Generate multi-turn response using the autonomous Agent Execution Engine
        tokens_before = self.client.total_tokens if (self.client and isinstance(getattr(self.client, "total_tokens", None), int)) else 0
        reply = self.agent_engine.run(
            self.messages,
            system_prompt=combined_sys,
            on_tool_start=on_tool_start,
            on_tool_end=on_tool_end,
            on_token=on_token,
        )
        self.add_assistant_message(reply)

        tokens_after = self.client.total_tokens if (self.client and isinstance(getattr(self.client, "total_tokens", None), int)) else 0
        diff = tokens_after - tokens_before
        if diff <= 0:
            # Fallback estimation heuristic if client did not return usage tokens
            est_prompt = (len(combined_sys) + sum(len(m.get("content", "")) for m in self.messages)) // 4
            est_reply = len(reply) // 4
            diff = max(1, est_prompt + est_reply)
            if self.client and hasattr(self.client, "record_usage") and callable(self.client.record_usage):
                self.client.record_usage(prompt_tokens=est_prompt, completion_tokens=est_reply, total_tokens=diff)

        self.last_turn_tokens = diff
        self.total_tokens += diff
        self.last_tool_audits = list(self.agent_engine.last_tool_audits)

        return reply, detected
