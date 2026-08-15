from __future__ import annotations

import datetime
from pathlib import Path

from leai.ai.base import BaseLLMClient
from leai.ai.prompts import ASK_SYSTEM_PROMPT
from leai.ask_rag import build_rag_context
from leai.config import LeaiConfig
from leai.models import SchemaMetadata


class ChatSession:
    """Interactive multi-turn conversation session manager with contextual RAG."""

    def __init__(
        self,
        schemas: list[SchemaMetadata],
        config: LeaiConfig,
        client: BaseLLMClient,
        max_history_turns: int = 15,
    ):
        self.schemas = schemas
        self.config = config
        self.client = client
        self.max_history_turns = max_history_turns
        self.messages: list[dict[str, str]] = []
        self.active_entities: set[str] = set()

    def add_user_message(self, content: str) -> None:
        self.messages.append({"role": "user", "content": content})
        # Limit history to prevent context window overflow
        if len(self.messages) > self.max_history_turns * 2:
            self.messages = self.messages[-(self.max_history_turns * 2):]

    def add_assistant_message(self, content: str) -> None:
        self.messages.append({"role": "assistant", "content": content})

    def clear(self) -> None:
        """Clears session history and memory."""
        self.messages.clear()
        self.active_entities.clear()

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
            role = "👤 **User**" if msg["role"] == "user" else "🤖 **LEAI Assistant**"
            lines.append(f"### {role}")
            lines.append(msg["content"])
            lines.append("")

        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text("\n".join(lines), encoding="utf-8")
        return target_path

    def send(self, user_input: str) -> tuple[str, list[str]]:
        """Processes user input, updates RAG context, and retrieves AI response."""
        # 1. Update RAG context with the new question
        rag_context, detected = build_rag_context(user_input, self.schemas, self.config)
        for entity in detected:
            self.active_entities.add(entity)

        # 2. Assemble System Prompt with accumulated RAG memory
        combined_sys = (
            f"{ASK_SYSTEM_PROMPT}\n\n"
            f"### [CONVERSATION MEMORY & ACCUMULATED RAG]\n"
            f"Active entities in conversation: {', '.join(self.active_entities) if self.active_entities else 'None'}\n\n"
            f"Oracle Database Context:\n{rag_context}"
        )

        # 3. Add user message
        self.add_user_message(user_input)

        # 4. Generate multi-turn response
        reply = self.client.generate_chat(self.messages, system_prompt=combined_sys)
        self.add_assistant_message(reply)

        return reply, detected
