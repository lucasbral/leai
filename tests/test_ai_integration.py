from __future__ import annotations
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from leai.ai.anthropic_client import AnthropicClient
from leai.ai.base import BaseLLMClient
from leai.ai.factory import get_llm_client
from leai.ai.gemini_client import GeminiClient
from leai.ai.openai_client import OpenAICompatibleClient
from leai.annotations import load_annotation, save_annotation
from leai.config import AIConfig, AIProviderConfig, LeaiConfig
from leai.enrich import (
    enrich_code_object_annotation,
    enrich_schema_annotations,
    enrich_table_annotation,
)
from leai.models import (
    CodeObjectMeta,
    ColumnMeta,
    ForeignKeyMeta,
    ObjectAnnotation,
    SchemaMetadata,
    TableMeta,
)


class MockLLMClient(BaseLLMClient):
    def __init__(self, json_response: dict | None = None, text_response: str = "Resposta do mock"):
        super().__init__(api_key="mock", model="mock-model")
        self.json_response = json_response or {}
        self.text_response = text_response

    def generate_text(self, prompt: str, system_prompt: str | None = None) -> str:
        return self.text_response

    def generate_json(self, prompt: str, system_prompt: str | None = None) -> dict:
        return self.json_response

    def generate_chat(self, messages: list[dict[str, str]], system_prompt: str | None = None) -> str:
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
                },
            ),
        )

        client_default = get_llm_client(cfg)
        self.assertIsInstance(client_default, OpenAICompatibleClient)
        self.assertEqual(client_default.model, "gpt-4o")

        client_gemini = get_llm_client(cfg, provider_override="gemini")
        self.assertIsInstance(client_gemini, GeminiClient)
        self.assertEqual(client_gemini.model, "gemini-1.5-pro")

        client_claude = get_llm_client(cfg, provider_override="anthropic")
        self.assertIsInstance(client_claude, AnthropicClient)
        self.assertEqual(client_claude.model, "claude-3-5-sonnet")

        client_deepseek = get_llm_client(cfg, provider_override="deepseek")
        self.assertIsInstance(client_deepseek, OpenAICompatibleClient)
        self.assertEqual(client_deepseek.base_url, "https://api.deepseek.com/v1")

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

        # Deve manter a descrição manual
        self.assertEqual(enriched.description, "Descrição humana manual existente")
        # Deve manter a coluna existente
        self.assertEqual(enriched.columns["ID"], "Identificador do cliente mantido manualmente")
        # Deve preencher a coluna faltante
        self.assertEqual(enriched.columns["EMAIL"], "Endereço eletrônico do cliente")
        # Deve adicionar regras e tags
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


if __name__ == "__main__":
    unittest.main()
