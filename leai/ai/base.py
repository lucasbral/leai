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
        self.last_prompt_tokens: int = 0
        self.last_completion_tokens: int = 0
        self.last_total_tokens: int = 0
        self.total_tokens: int = 0

    def record_usage(self, prompt_tokens: int = 0, completion_tokens: int = 0, total_tokens: int | None = None) -> None:
        """Records token usage from API responses or estimation heuristics."""
        self.last_prompt_tokens = max(0, prompt_tokens)
        self.last_completion_tokens = max(0, completion_tokens)
        tot = total_tokens if total_tokens is not None else (self.last_prompt_tokens + self.last_completion_tokens)
        self.last_total_tokens = max(0, tot)
        self.total_tokens += self.last_total_tokens

    @abstractmethod
    def generate_text(self, prompt: str, system_prompt: str | None = None) -> str:
        """Generates plain text response from the given prompt."""

    @abstractmethod
    def generate_json(self, prompt: str, system_prompt: str | None = None) -> dict[str, Any]:
        """Generates and returns a structured JSON object from the given prompt."""

    @abstractmethod
    def generate_chat(self, messages: list[dict[str, str]], system_prompt: str | None = None) -> str:
        """Generates a response considering the full multi-turn message history."""

    def stream_chat(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str | None = None,
        on_chunk: Any = None,
    ) -> str:
        """Streams a chat response token-by-token. Default fallback invokes generate_chat."""
        res = self.generate_chat(messages, system_prompt=system_prompt)
        if on_chunk and callable(on_chunk) and res:
            on_chunk(res)
        return res

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
