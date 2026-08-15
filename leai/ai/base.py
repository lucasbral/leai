from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any


class BaseLLMClient(ABC):
    """Interface abstrata padronizada para clientes LLM no LEAI."""

    def __init__(self, api_key: str | None = None, model: str | None = None, base_url: str | None = None, temperature: float = 0.2):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.temperature = temperature

    @abstractmethod
    def generate_text(self, prompt: str, system_prompt: str | None = None) -> str:
        """Gera resposta em texto plano a partir do prompt."""
        pass

    @abstractmethod
    def generate_json(self, prompt: str, system_prompt: str | None = None) -> dict[str, Any]:
        """Gera e retorna um objeto JSON estruturado a partir do prompt."""
        pass

    @abstractmethod
    def generate_chat(self, messages: list[dict[str, str]], system_prompt: str | None = None) -> str:
        """Gera resposta considerando todo o histórico de mensagens multi-turno."""
        pass

