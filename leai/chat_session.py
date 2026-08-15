from __future__ import annotations
import datetime
from pathlib import Path
from leai.ai.base import BaseLLMClient
from leai.ai.prompts import ASK_SYSTEM_PROMPT
from leai.ask_rag import build_rag_context
from leai.config import LeaiConfig
from leai.models import SchemaMetadata


class ChatSession:
    """Gerenciador de sessão de conversa interativa multi-turno com RAG contextual."""

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
        # Limitar histórico para não estourar janela de contexto
        if len(self.messages) > self.max_history_turns * 2:
            self.messages = self.messages[-(self.max_history_turns * 2):]

    def add_assistant_message(self, content: str) -> None:
        self.messages.append({"role": "assistant", "content": content})

    def clear(self) -> None:
        """Limpa o histórico e a memória da sessão."""
        self.messages.clear()
        self.active_entities.clear()

    def save_transcript(self, output_file: Path | None = None) -> Path:
        """Exporta o histórico da conversa formatado em Markdown."""
        now = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        target_path = output_file or Path(f"leai_chat_{now}.md")

        lines = [
            f"# LEAI Chat Session Transcript - {now}",
            f"- **Provedor:** {self.client.__class__.__name__} ({self.client.model})",
            f"- **Entidades Mapeadas:** {', '.join(self.active_entities) if self.active_entities else 'Nenhuma'}",
            "",
            "---",
            "",
        ]

        for msg in self.messages:
            role = "👤 **Você**" if msg["role"] == "user" else "🤖 **Assistente LEAI**"
            lines.append(f"### {role}")
            lines.append(msg["content"])
            lines.append("")

        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text("\n".join(lines), encoding="utf-8")
        return target_path

    def send(self, user_input: str) -> tuple[str, list[str]]:
        """Processa a entrada do usuário, atualiza o contexto RAG e obtém a resposta da IA."""
        # 1. Atualizar contexto RAG com a nova pergunta
        rag_context, detected = build_rag_context(user_input, self.schemas, self.config)
        for entity in detected:
            self.active_entities.add(entity)

        # 2. Montar System Prompt com RAG acumulado
        combined_sys = (
            f"{ASK_SYSTEM_PROMPT}\n\n"
            f"### [MEMÓRIA DE CONVERSA E RAG ACUMULADO]\n"
            f"Entidades ativas na conversa: {', '.join(self.active_entities) if self.active_entities else 'Nenhuma'}\n\n"
            f"Contexto do Banco de Dados Oracle:\n{rag_context}"
        )

        # 3. Adicionar mensagem do usuário
        self.add_user_message(user_input)

        # 4. Gerar resposta com histórico multi-turno
        reply = self.client.generate_chat(self.messages, system_prompt=combined_sys)
        self.add_assistant_message(reply)

        return reply, detected
