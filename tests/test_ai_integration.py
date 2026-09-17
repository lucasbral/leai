from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from leai.ai.anthropic_client import AnthropicClient
from leai.ai.base import BaseLLMClient
from leai.ai.factory import get_llm_client
from leai.ai.gemini_client import GeminiClient
from leai.ai.openai_client import OpenAICompatibleClient
from leai.annotations import load_annotation
from leai.config import AIConfig, AIProviderConfig, LeaiConfig
from leai.enrich import (
    enrich_schema_annotations,
    enrich_table_annotation,
)
from leai.models import (
    ColumnMeta,
    ObjectAnnotation,
    SchemaMetadata,
    TableMeta,
)


class MockLLMClient(BaseLLMClient):
    def __init__(self, json_response: dict | None = None, text_response: str = "Resposta do mock"):
        super().__init__(api_key="mock", model="mock-model")
        self.json_response = json_response or {}
        self.text_response = text_response
        self.last_system_prompt: str | None = None

    def generate_text(self, prompt: str, system_prompt: str | None = None) -> str:
        self.last_system_prompt = system_prompt
        return self.text_response

    def generate_json(self, prompt: str, system_prompt: str | None = None) -> dict:
        self.last_system_prompt = system_prompt
        return self.json_response

    def generate_chat(self, messages: list[dict[str, str]], system_prompt: str | None = None) -> str:
        self.last_system_prompt = system_prompt
        return self.text_response


class AIIntegrationTests(unittest.TestCase):
    def test_llm_factory_instantiates_correct_clients(self):
        cfg = LeaiConfig(
            dsn="",
            schemas=["TEST"],
            ai=AIConfig(
                default_provider="openai",
                providers={
                    "openai": AIProviderConfig(api_key="sk-test", model="gpt-4o"),
                    "gemini": AIProviderConfig(api_key="gem-test", model="gemini-1.5-pro"),
                    "anthropic": AIProviderConfig(api_key="ant-test", model="claude-3-5-sonnet"),
                    "deepseek": AIProviderConfig(api_key="ds-test", base_url="https://api.deepseek.com/v1", model="deepseek-chat"),
                    "grok": AIProviderConfig(api_key="xai-test", base_url="https://api.x.ai/v1", model="grok-2-latest"),
                },
            ),
        )

        client_default = get_llm_client(cfg)
        self.assertIsInstance(client_default, OpenAICompatibleClient)
        self.assertEqual(client_default.model, "gpt-4o")
        self.assertEqual(client_default.timeout, 300.0)

        client_gemini = get_llm_client(cfg, provider_override="gemini")
        self.assertIsInstance(client_gemini, GeminiClient)
        self.assertEqual(client_gemini.model, "gemini-1.5-pro")
        self.assertEqual(client_gemini.timeout, 300.0)

        client_claude = get_llm_client(cfg, provider_override="anthropic")
        self.assertIsInstance(client_claude, AnthropicClient)
        self.assertEqual(client_claude.model, "claude-3-5-sonnet")
        self.assertEqual(client_claude.timeout, 300.0)

        client_deepseek = get_llm_client(cfg, provider_override="deepseek")
        self.assertIsInstance(client_deepseek, OpenAICompatibleClient)
        self.assertEqual(client_deepseek.base_url, "https://api.deepseek.com/v1")

        client_grok = get_llm_client(cfg, provider_override="grok")
        self.assertIsInstance(client_grok, OpenAICompatibleClient)
        self.assertEqual(client_grok.base_url, "https://api.x.ai/v1")
        self.assertEqual(client_grok.model, "grok-2-latest")

    def test_llm_factory_resolves_provider_temperature_and_timeout(self):
        cfg = LeaiConfig(
            dsn="",
            schemas=["TEST"],
            ai=AIConfig(
                default_provider="openai",
                temperature=0.2,
                timeout=300.0,
                providers={
                    "openai": AIProviderConfig(api_key="sk-test", temperature=0.7, timeout=60.0),
                    "gemini": AIProviderConfig(api_key="gem-test", temperature=0.0),
                },
            ),
        )

        client_openai = get_llm_client(cfg, provider_override="openai")
        self.assertEqual(client_openai.temperature, 0.7)
        self.assertEqual(client_openai.timeout, 60.0)

        client_gemini = get_llm_client(cfg, provider_override="gemini")
        self.assertEqual(client_gemini.temperature, 0.0)
        self.assertEqual(client_gemini.timeout, 300.0)  # Herdou do global

    def test_llm_factory_local_and_ollama_defaults(self):
        cfg = LeaiConfig(dsn="", schemas=["TEST"], ai=AIConfig())

        client_ollama = get_llm_client(cfg, provider_override="ollama")
        self.assertEqual(client_ollama.model, "qwen2.5-coder:latest")
        self.assertEqual(client_ollama.base_url, "http://localhost:11434/v1")
        self.assertEqual(client_ollama.num_ctx, 16384)

        client_local = get_llm_client(cfg, provider_override="local")
        self.assertEqual(client_local.model, "qwen2.5")
        self.assertEqual(client_local.base_url, "http://localhost:1234/v1")
        self.assertEqual(client_local.num_ctx, 16384)

    def test_llm_factory_resolves_inference_options_and_overrides(self):
        cfg = LeaiConfig(
            dsn="",
            schemas=["TEST"],
            ai=AIConfig(
                default_provider="ollama",
                num_ctx=8192,
                max_tokens=2048,
                top_p=0.9,
                keep_alive="10m",
                providers={
                    "ollama": AIProviderConfig(
                        num_ctx=32768,
                        keep_alive="30m",
                        options={"repeat_penalty": 1.15, "top_k": 40},
                    ),
                    "gemini": AIProviderConfig(
                        api_key="test-gem",
                        max_tokens=8192,
                        top_p=0.95,
                    ),
                    "anthropic": AIProviderConfig(
                        api_key="test-ant",
                        max_tokens=4096,
                    ),
                },
            ),
        )

        client_ollama = get_llm_client(cfg, provider_override="ollama")
        self.assertEqual(client_ollama.num_ctx, 32768)
        self.assertEqual(client_ollama.keep_alive, "30m")
        self.assertEqual(client_ollama.max_tokens, 2048)  # Herdou do global
        self.assertEqual(client_ollama.top_p, 0.9)  # Herdou do global
        self.assertEqual(client_ollama.options.get("repeat_penalty"), 1.15)
        self.assertEqual(client_ollama.options.get("top_k"), 40)

        # Verificar montagem do payload HTTP do Ollama
        payload = client_ollama._build_payload([{"role": "user", "content": "Olá"}])
        self.assertEqual(payload["max_tokens"], 2048)
        self.assertEqual(payload["top_p"], 0.9)
        self.assertEqual(payload["keep_alive"], "30m")
        self.assertIn("options", payload)
        self.assertEqual(payload["options"]["num_ctx"], 32768)
        self.assertEqual(payload["options"]["repeat_penalty"], 1.15)
        self.assertEqual(payload["options"]["top_k"], 40)

        # Verificar Gemini
        client_gem = get_llm_client(cfg, provider_override="gemini")
        self.assertEqual(client_gem.max_tokens, 8192)
        self.assertEqual(client_gem.top_p, 0.95)
        gem_cfg = client_gem._build_generation_config(response_mime_type="application/json")
        self.assertEqual(gem_cfg["maxOutputTokens"], 8192)
        self.assertEqual(gem_cfg["topP"], 0.95)
        self.assertEqual(gem_cfg["responseMimeType"], "application/json")

        # Verificar Anthropic
        client_ant = get_llm_client(cfg, provider_override="anthropic")
        self.assertEqual(client_ant.max_tokens, 4096)
        self.assertEqual(client_ant.top_p, 0.9)  # Herdou do global

    def test_enrich_table_preserves_existing_when_not_overwrite(self):
        table = TableMeta(
            name="CLIENTES",
            columns=[
                ColumnMeta(name="ID", data_type="NUMBER", nullable=False),
                ColumnMeta(name="EMAIL", data_type="VARCHAR2", nullable=False),
            ],
        )

        ann = ObjectAnnotation(
            description="Descrição humana manual existente",
            columns={"ID": "Identificador do cliente mantido manualmente"},
        )

        mock_response = {
            "description": "Descrição da IA que NÃO deve sobrescrever",
            "business_rules": ["Email deve ser único"],
            "tags": ["crm", "clientes"],
            "columns": {
                "ID": "ID pela IA",
                "EMAIL": "Endereço eletrônico do cliente",
            },
        }
        client = MockLLMClient(json_response=mock_response)

        enriched = enrich_table_annotation(table, ann, client, overwrite=False)

        # Must keep manual description
        self.assertEqual(enriched.description, "Descrição humana manual existente")
        # Must keep existing column comment
        self.assertEqual(enriched.columns["ID"], "Identificador do cliente mantido manualmente")
        # Must populate missing column
        self.assertEqual(enriched.columns["EMAIL"], "Endereço eletrônico do cliente")
        # Must add rules and tags
        self.assertIn("Email deve ser único", enriched.business_rules)
        self.assertIn("crm", enriched.tags)

    def test_enrich_table_overwrites_when_flag_is_true(self):
        table = TableMeta(
            name="CLIENTES",
            columns=[
                ColumnMeta(name="ID", data_type="NUMBER", nullable=False),
            ],
        )

        ann = ObjectAnnotation(
            description="Descrição antiga",
            columns={"ID": "Comentário antigo"},
        )

        mock_response = {
            "description": "Nova descrição gerada por IA",
            "columns": {"ID": "Novo comentário IA"},
        }
        client = MockLLMClient(json_response=mock_response)

        enriched = enrich_table_annotation(table, ann, client, overwrite=True)

        self.assertEqual(enriched.description, "Nova descrição gerada por IA")
        self.assertEqual(enriched.columns["ID"], "Novo comentário IA")

    def test_enrich_table_annotation_respects_language(self):
        table = TableMeta(name="DEPARTMENTS", columns=[ColumnMeta(name="ID", data_type="NUMBER", nullable=False)])
        ann = ObjectAnnotation(description="", columns={})
        client = MockLLMClient(json_response={"description": "Tabela de departamentos", "columns": {"ID": "ID único"}})

        enrich_table_annotation(table, ann, client, overwrite=True, lang="pt-BR")
        self.assertIsNotNone(client.last_system_prompt)
        self.assertIn("You are an Expert Oracle Data Engineer", client.last_system_prompt)
        self.assertIn("Portuguese (pt-BR)", client.last_system_prompt)

        enrich_table_annotation(table, ann, client, overwrite=True, lang="en-US")
        self.assertIsNotNone(client.last_system_prompt)
        self.assertIn("You are an Expert Oracle Data Engineer", client.last_system_prompt)
        self.assertIn("English (en-US)", client.last_system_prompt)

    def test_enrich_schema_annotations_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ann_dir = root / "annotations"
            raw_dir = root / "raw"

            cfg = LeaiConfig(
                dsn="",
                schemas=["HR"],
                annotationsPath=ann_dir,
                rawPath=raw_dir,
            )

            table = TableMeta(name="CARGOS", columns=[ColumnMeta(name="CODIGO", data_type="VARCHAR2", nullable=False)])
            schema = SchemaMetadata(schema_name="HR", tables=[table])

            mock_response = {
                "description": "Tabela de cargos e funções",
                "columns": {"CODIGO": "Código identificador do cargo"},
            }
            client = MockLLMClient(json_response=mock_response)

            tables_count, code_count = enrich_schema_annotations([schema], cfg, client, overwrite=False)
            self.assertEqual(tables_count, 1)
            self.assertEqual(code_count, 0)

            saved_ann_file = ann_dir / "tables" / "CARGOS.yml"
            self.assertTrue(saved_ann_file.exists())
            loaded = load_annotation(saved_ann_file)
            self.assertEqual(loaded.description, "Tabela de cargos e funções")
            self.assertEqual(loaded.columns.get("CODIGO"), "Código identificador do cargo")

    def test_openai_stream_chat_with_tools_and_reasoning(self):
        from unittest.mock import MagicMock, patch

        client = OpenAICompatibleClient(api_key="test-key", model="qwen-2.5")

        import json

        # Mock SSE response stream from OpenAI / Ollama compatible endpoint
        sse_lines = [
            b"data: " + json.dumps({"choices": [{"delta": {"reasoning_content": "Pensando na consulta...\n"}}]}).encode("utf-8") + b"\n\n",
            b"data: "
            + json.dumps(
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "call_123",
                                        "type": "function",
                                        "function": {"name": "get_table_schema", "arguments": '{"table'},
                                    }
                                ]
                            }
                        }
                    ]
                }
            ).encode("utf-8")
            + b"\n\n",
            b"data: "
            + json.dumps(
                {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": '_name": "RH.FUNCIONARIOS"}'}}]}}]}
            ).encode("utf-8")
            + b"\n\n",
            b"data: [DONE]\n\n",
        ]

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__.return_value = sse_lines

        captured_thoughts = []
        captured_tokens = []

        with patch("urllib.request.urlopen", return_value=mock_resp):
            content, tool_calls = client.stream_chat_with_tools(
                messages=[{"role": "user", "content": "Mostre RH.FUNCIONARIOS"}],
                on_thought=lambda th: captured_thoughts.append(th),
                on_token=lambda tok: captured_tokens.append(tok),
            )

        self.assertEqual("".join(captured_thoughts), "Pensando na consulta...\n")
        self.assertEqual(len(tool_calls), 1)
        self.assertEqual(tool_calls[0]["name"], "get_table_schema")
        self.assertEqual(tool_calls[0]["arguments"], {"table_name": "RH.FUNCIONARIOS"})

    def test_gemini_stream_chat_with_tools_and_thought(self):
        from unittest.mock import MagicMock, patch

        client = GeminiClient(api_key="test-key", model="gemini-2.0-flash")

        # Mock SSE response from Gemini streamGenerateContent?alt=sse
        sse_lines = [
            b'data: {"candidates": [{"content": {"parts": [{"thought": true, "text": "Analyzing schema structure..."}]}}]}\n\n',
            b'data: {"candidates": [{"content": {"parts": [{"functionCall": {"name": "search_column_comments", "args": {"query": "CPF"}}}]}}]}\n\n',
        ]

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__.return_value = sse_lines

        captured_thoughts = []

        with patch("urllib.request.urlopen", return_value=mock_resp):
            content, tool_calls = client.stream_chat_with_tools(
                messages=[{"role": "user", "content": "Busque colunas de CPF"}],
                on_thought=lambda th: captured_thoughts.append(th),
            )

        self.assertEqual("".join(captured_thoughts), "Analyzing schema structure...")
        self.assertEqual(len(tool_calls), 1)
        self.assertEqual(tool_calls[0]["name"], "search_column_comments")
        self.assertEqual(tool_calls[0]["arguments"], {"query": "CPF"})

    def test_anthropic_stream_chat_with_tools_and_thinking(self):
        from unittest.mock import MagicMock, patch

        client = AnthropicClient(api_key="test-key", model="claude-3-7-sonnet")

        # Mock SSE response from Anthropic stream
        sse_lines = [
            b'data: {"type": "content_block_start", "index": 0, "content_block": {"type": "thinking"}}\n\n',
            b'data: {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "Investigating dependencies..."}}\n\n',
            b'data: {"type": "content_block_stop", "index": 0}\n\n',
            b'data: {"type": "content_block_start", "index": 1, "content_block": {"type": "tool_use", "id": "toolu_abc", "name": "trace_object_lineage"}}\n\n',
            b'data: {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": "{\\"object_name\\": \\"PACK_FOLHA\\"}"}}\n\n',
            b'data: {"type": "content_block_stop", "index": 1}\n\n',
            b'data: {"type": "message_stop"}\n\n',
        ]

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__.return_value = sse_lines

        captured_thoughts = []

        with patch("urllib.request.urlopen", return_value=mock_resp):
            content, tool_calls = client.stream_chat_with_tools(
                messages=[{"role": "user", "content": "Verifique PACK_FOLHA"}],
                on_thought=lambda th: captured_thoughts.append(th),
            )

        self.assertEqual("".join(captured_thoughts), "Investigating dependencies...")
        self.assertEqual(len(tool_calls), 1)
        self.assertEqual(tool_calls[0]["name"], "trace_object_lineage")
        self.assertEqual(tool_calls[0]["arguments"], {"object_name": "PACK_FOLHA"})

    def test_iter_sse_lines_with_split_multibyte_utf8(self):
        from leai.ai.base import iter_sse_lines

        # Simulate raw byte chunks split across Portuguese accented characters and emojis
        full_text = 'data: {"choices":[{"delta":{"content":"🎯 1. Regras de Negócio e PADRÃO para substituição com aspas duplas `<TABLE>`"}}\n\n'
        raw_bytes = full_text.encode("utf-8")

        # Split bytes into tiny 7-byte chunks (which will bisect multi-byte sequences)
        chunks = [raw_bytes[i : i + 7] for i in range(0, len(raw_bytes), 7)]

        class MockByteStream:
            def __init__(self, data_chunks):
                self.chunks = list(data_chunks)

            def read(self, size=4096):
                if not self.chunks:
                    return b""
                return self.chunks.pop(0)

        stream = MockByteStream(chunks)
        lines = list(iter_sse_lines(stream))

        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("data:"))
        self.assertIn("🎯 1. Regras de Negócio e PADRÃO para substituição com aspas duplas `<TABLE>`", lines[0])


if __name__ == "__main__":
    unittest.main()
