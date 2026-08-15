from __future__ import annotations
import tempfile
import unittest
from pathlib import Path

from leai.ai.base import BaseLLMClient
from leai.chat_session import ChatSession
from leai.config import LeaiConfig
from leai.models import ColumnMeta, SchemaMetadata, TableMeta


class MockChatLLMClient(BaseLLMClient):
    def __init__(self):
        super().__init__(api_key="mock", model="mock-chat")
        self.last_messages = []
        self.last_system_prompt = None

    def generate_text(self, prompt: str, system_prompt: str | None = None) -> str:
        return "Mock text reply"

    def generate_json(self, prompt: str, system_prompt: str | None = None) -> dict:
        return {}

    def generate_chat(self, messages: list[dict[str, str]], system_prompt: str | None = None) -> str:
        self.last_messages = list(messages)
        self.last_system_prompt = system_prompt
        last_user = messages[-1]["content"] if messages else ""
        return f"Resposta simulada para: {last_user}"


class ChatSessionTests(unittest.TestCase):
    def setUp(self):
        t1 = TableMeta(
            name="FUNCIONARIOS",
            columns=[
                ColumnMeta(name="ID", data_type="NUMBER", nullable=False),
                ColumnMeta(name="SALARIO", data_type="NUMBER", nullable=False),
            ],
        )
        self.schema = SchemaMetadata(schema_name="HR", tables=[t1])
        self.cfg = LeaiConfig(dsn="", schemas=["HR"])
        self.client = MockChatLLMClient()
        self.session = ChatSession(schemas=[self.schema], config=self.cfg, client=self.client)

    def test_chat_multi_turn_conversation_and_memory(self):
        # Turno 1
        reply1, detected1 = self.session.send("Explique a tabela FUNCIONARIOS")
        self.assertIn("FUNCIONARIOS", detected1)
        self.assertIn("FUNCIONARIOS", self.session.active_entities)
        self.assertEqual(len(self.session.messages), 2)
        self.assertEqual(self.session.messages[0]["role"], "user")
        self.assertEqual(self.session.messages[1]["role"], "assistant")
        self.assertIn("Resposta simulada para: Explique a tabela FUNCIONARIOS", reply1)

        # Turno 2
        reply2, detected2 = self.session.send("E como calcular o salário?")
        self.assertEqual(len(self.session.messages), 4)
        self.assertIn("FUNCIONARIOS", self.session.active_entities)
        self.assertEqual(len(self.client.last_messages), 3)  # user1, asst1, user2

    def test_chat_clear_memory(self):
        self.session.send("Pergunta 1 sobre FUNCIONARIOS")
        self.assertTrue(len(self.session.messages) > 0)
        self.assertTrue(len(self.session.active_entities) > 0)

        self.session.clear()
        self.assertEqual(len(self.session.messages), 0)
        self.assertEqual(len(self.session.active_entities), 0)

    def test_chat_save_transcript(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_file = Path(tmp) / "chat_export.md"
            self.session.send("Primeira pergunta do chat")
            self.session.send("Segunda pergunta do chat")

            saved = self.session.save_transcript(out_file)
            self.assertTrue(saved.exists())

            content = saved.read_text(encoding="utf-8")
            self.assertIn("# LEAI Chat Session Transcript", content)
            self.assertIn("Primeira pergunta do chat", content)
            self.assertIn("Segunda pergunta do chat", content)


if __name__ == "__main__":
    unittest.main()
