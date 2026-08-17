from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseLLMClient(ABC):
    """Standardized abstract interface for LLM clients in LEAI."""

    def __init__(self, api_key: str | None = None, model: str | None = None, base_url: str | None = None, temperature: float = 0.2):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.temperature = temperature

    @abstractmethod
    def generate_text(self, prompt: str, system_prompt: str | None = None) -> str:
        """Generates plain text response from the given prompt."""

    @abstractmethod
    def generate_json(self, prompt: str, system_prompt: str | None = None) -> dict[str, Any]:
        """Generates and returns a structured JSON object from the given prompt."""

    @abstractmethod
    def generate_chat(self, messages: list[dict[str, str]], system_prompt: str | None = None) -> str:
        """Generates a response considering the full multi-turn message history."""

    def generate_chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        system_prompt: str | None = None,
    ) -> tuple[str | None, list[dict[str, Any]]]:
        """Generates a chat turn supporting tool calls (Function Calling). Default fallback invokes generate_chat."""
        res = self.generate_chat(messages, system_prompt=system_prompt)
        return res, []

    def list_models(self) -> list[dict[str, str]]:
        """Queries the provider API and returns the list of available models for the configured API key."""
        return [{"id": self.model or "default", "name": self.model or "default"}]

