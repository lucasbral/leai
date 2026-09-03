from __future__ import annotations

import json
import socket
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from leai.config import AIConfig, AIProviderConfig, LeaiConfig
from leai.models import SchemaMetadata, TableMeta
from leai.web.server import start_server


class MockChatLLMClient:
    def __init__(self):
        self.model = "test-model-v1"

    def generate_chat_with_tools(self, messages, tools=None, system_prompt=None, tool_choice_mode="auto"):
        return "Hello from Web Copilot! Here is your SQL:\n```sql\nSELECT * FROM EMPLOYEES;\n```", []

    def generate_chat(self, messages, system_prompt=None):
        return "Specialist synthesis completed."


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class WebChatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = _find_free_port()
        cls.config = LeaiConfig(
            ai=AIConfig(
                default_provider="openai",
                providers={
                    "openai": AIProviderConfig(model="gpt-4o", api_key="sk-fake"),
                    "gemini": AIProviderConfig(model="gemini-2.5-flash", api_key="sk-fake2"),
                },
            )
        )
        cls.schemas = [
            SchemaMetadata(
                schema_name="HR",
                tables=[
                    TableMeta(name="EMPLOYEES", comment="Employee records"),
                    TableMeta(name="DEPARTMENTS", comment="Department records"),
                ],
            )
        ]
        cls.mock_client = MockChatLLMClient()
        cls.server, cls.url = start_server(
            config=cls.config,
            schemas=cls.schemas,
            client=cls.mock_client,
            provider_name="openai",
            host="127.0.0.1",
            port=cls.port,
            open_browser=False,
            in_background=True,
        )

    @classmethod
    def tearDownClass(cls):
        try:
            cls.server.shutdown()
            cls.server.server_close()
        except Exception:
            pass

    def test_chat_html_removed_returns_404(self):
        req = urllib.request.Request(f"{self.url}/chat")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 404)

    def test_api_chat_models(self):
        req = urllib.request.Request(f"{self.url}/api/chat/models")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("success"))
            self.assertEqual(data.get("default_provider"), "openai")
            self.assertIn("openai", data.get("providers", {}))
            self.assertIn("gemini", data.get("providers", {}))

    def test_api_catalog_format(self):
        req = urllib.request.Request(f"{self.url}/api/catalog")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("schemas", data)
            self.assertEqual(len(data["schemas"]), 1)
            self.assertEqual(data["schemas"][0]["schema_name"], "HR")
            self.assertEqual(len(data["schemas"][0]["tables"]), 2)

    @patch("leai.web.server.get_llm_client")
    def test_api_chat_stream_sse(self, mock_get_client):
        mock_get_client.return_value = self.mock_client

        req = urllib.request.Request(
            f"{self.url}/api/chat/stream",
            data=json.dumps({"prompt": "List employees", "history": []}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("text/event-stream", resp.headers.get("Content-Type", ""))
            chunks = []
            while True:
                line = resp.readline().decode("utf-8")
                if not line:
                    break
                chunks.append(line)
                if "[DONE]" in line:
                    break
            body = "".join(chunks)
            self.assertIn("data: ", body)
            self.assertIn("[DONE]", body)
            self.assertIn("Hello from Web Copilot!", body)

    @patch("leai.web.server.get_llm_client")
    def test_api_chat_stream_sse_with_history(self, mock_get_client):
        mock_get_client.return_value = self.mock_client

        payload = {
            "prompt": "And what about departments?",
            "history": [
                {"role": "user", "content": "Tell me about employees."},
                {"role": "assistant", "content": "Employees table has EMP_ID and NAME."},
            ],
        }
        req = urllib.request.Request(
            f"{self.url}/api/chat/stream",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("text/event-stream", resp.headers.get("Content-Type", ""))
            body = resp.read().decode("utf-8")
            self.assertIn("Hello from Web Copilot!", body)
            self.assertIn("[DONE]", body)

    @patch("leai.web.server.get_llm_client")
    def test_api_chat_stream_workflow_command(self, mock_get_client):
        mock_get_client.return_value = self.mock_client

        req = urllib.request.Request(
            f"{self.url}/api/chat/stream",
            data=json.dumps({"prompt": "/workflow impact EMPLOYEES"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            self.assertEqual(resp.status, 200)
            body = resp.read().decode("utf-8")
            self.assertIn("data: ", body)
            self.assertIn("[DONE]", body)
            self.assertIn("tool_start", body)
            self.assertIn("tool_end", body)

    @patch("leai.web.server.get_llm_client")
    def test_api_chat_stream_specialist_command(self, mock_get_client):
        mock_get_client.return_value = self.mock_client

        req = urllib.request.Request(
            f"{self.url}/api/chat/stream",
            data=json.dumps({"prompt": "@catalog_researcher Find all tables with employees"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            self.assertEqual(resp.status, 200)
            body = resp.read().decode("utf-8")
            self.assertIn("data: ", body)
            self.assertIn("[DONE]", body)
            self.assertIn("Hello from Web Copilot!", body)


if __name__ == "__main__":
    unittest.main()
