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
        # Turn 1
        reply1, detected1 = self.session.send("Explique a tabela FUNCIONARIOS")
        self.assertIn("FUNCIONARIOS", detected1)
        self.assertIn("FUNCIONARIOS", self.session.active_entities)
        self.assertEqual(len(self.session.messages), 2)
        self.assertEqual(self.session.messages[0]["role"], "user")
        self.assertEqual(self.session.messages[1]["role"], "assistant")
        self.assertIn("Resposta simulada para: Explique a tabela FUNCIONARIOS", reply1)

        # Turn 2
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

    def test_chat_token_accumulation_and_clear(self):
        self.assertEqual(self.session.total_tokens, 0)
        self.assertIsNone(self.session.last_turn_tokens)

        # Turn 1
        self.session.send("Pergunta 1 sobre FUNCIONARIOS")
        self.assertGreater(self.session.total_tokens, 0)
        self.assertIsNotNone(self.session.last_turn_tokens)
        first_total = self.session.total_tokens

        # Turn 2
        self.session.send("Pergunta 2")
        self.assertGreater(self.session.total_tokens, first_total)
        second_total = self.session.total_tokens

        # Clear should reset messages and last_turn_tokens, but KEEP total_tokens
        self.session.clear()
        self.assertEqual(len(self.session.messages), 0)
        self.assertIsNone(self.session.last_turn_tokens)
        self.assertEqual(self.session.total_tokens, second_total)

    def test_chat_streaming_callback(self):
        chunks = []

        def _on_token(tok: str):
            chunks.append(tok)

        reply, _ = self.session.send("Teste de streaming", on_token=_on_token)
        self.assertTrue(len(chunks) > 0)
        self.assertEqual("".join(chunks), reply)

    def test_chat_safe_truncation(self):
        # Create session with max_history_turns = 2 (max 4 messages)
        short_session = ChatSession(
            schemas=[self.schema],
            config=self.cfg,
            client=self.client,
            max_history_turns=2,
        )
        # Add 6 turns (12 messages)
        for i in range(1, 7):
            short_session.add_user_message(f"User msg {i}")
            short_session.add_assistant_message(f"Asst msg {i}")

        # The message list should be bounded and start with a user message
        self.assertLessEqual(len(short_session.messages), 4)
        self.assertEqual(short_session.messages[0]["role"], "user")
        self.assertEqual(short_session.messages[-1]["role"], "assistant")
        self.assertEqual(short_session.messages[-1]["content"], "Asst msg 6")

    def test_session_audit_context_and_structured_output(self):
        import json

        from leai.audit import SessionAuditLogger, ToolExecutionAudit

        # 1. Send query to populate ChatSession context fields
        reply, detected = self.session.send("Explique a tabela FUNCIONARIOS")
        self.assertTrue(len(self.session.last_system_prompt) > 0)
        self.assertIn("HR", self.session.last_system_prompt)
        self.assertTrue(len(self.session.last_working_messages) > 0)

        # 2. Test ToolExecutionAudit structured output_data and model_thought
        tool_json_str = json.dumps([{"col": "ID", "type": "NUMBER"}, {"col": "NAME", "type": "VARCHAR2"}])
        audit_tool = ToolExecutionAudit(
            step=1,
            tool_name="get_table_columns",
            arguments={"table_name": "FUNCIONARIOS"},
            model_thought="Preciso checar as colunas da tabela primeiro.",
            output_data=json.loads(tool_json_str),
            raw_output=tool_json_str,
            summary="2 columns found",
            duration_seconds=0.05,
        )
        self.assertIsInstance(audit_tool.output_data, list)
        self.assertEqual(audit_tool.model_thought, "Preciso checar as colunas da tabela primeiro.")

        # 3. Test SessionAuditLogger with new context fields
        with tempfile.TemporaryDirectory() as tmp_dir:
            logger = SessionAuditLogger(log_dir=Path(tmp_dir))
            turn = logger.record_turn(
                user_prompt="Explique a tabela FUNCIONARIOS",
                ai_response=reply,
                provider="mock",
                model="mock-chat",
                latency_seconds=1.23,
                tokens_used=450,
                rag_entities=detected,
                tools_executed=[audit_tool],
                system_prompt=self.session.last_system_prompt,
                rag_context=self.session.last_rag_context,
                messages=self.session.last_working_messages,
            )

            # Check TurnAuditRecord fields
            self.assertEqual(turn.system_prompt, self.session.last_system_prompt)
            self.assertEqual(turn.rag_context, self.session.last_rag_context)
            self.assertEqual(turn.messages, self.session.last_working_messages)
            self.assertEqual(turn.tools_executed[0].output_data[0]["col"], "ID")

            # Check JSON serialization on disk
            self.assertTrue(logger.log_file.exists())
            saved_json = json.loads(logger.log_file.read_text(encoding="utf-8"))
            saved_turn = saved_json["turns"][0]
            self.assertIn("system_prompt", saved_turn)
            self.assertIn("rag_context", saved_turn)
            self.assertIn("messages", saved_turn)
            self.assertIsInstance(saved_turn["tools_executed"][0]["output_data"], list)
            self.assertEqual(saved_turn["tools_executed"][0]["model_thought"], "Preciso checar as colunas da tabela primeiro.")


if __name__ == "__main__":
    unittest.main()
