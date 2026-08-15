from __future__ import annotations
import json
import re
import urllib.error
import urllib.request
from typing import Any

from leai.ai.base import BaseLLMClient


class AnthropicClient(BaseLLMClient):
    """Direct client for the Anthropic Claude REST API."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        temperature: float = 0.2,
    ):
        super().__init__(
            api_key=api_key or "",
            model=model or "claude-3-5-sonnet-20241022",
            base_url=(base_url or "https://api.anthropic.com/v1").rstrip("/"),
            temperature=temperature,
        )

    def _send_request(self, prompt: str, system_prompt: str | None = None) -> str:
        if not self.api_key:
            raise ValueError("Anthropic API key (ANTHROPIC_API_KEY) is not configured.")

        url = f"{self.base_url}/messages"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "User-Agent": "LEAI-CLI",
        }

        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 4096,
            "temperature": self.temperature,
            "messages": [{"role": "user", "content": prompt}],
        }

        if system_prompt:
            payload["system"] = system_prompt

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                contents = resp_data.get("content", [])
                if not contents:
                    raise RuntimeError(f"Anthropic API returned empty response content: {resp_data}")
                return contents[0]["text"]
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Anthropic API error (HTTP {exc.code}): {err_body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Connection error with Anthropic: {exc.reason}") from exc

    def generate_text(self, prompt: str, system_prompt: str | None = None) -> str:
        return self._send_request(prompt, system_prompt=system_prompt)

    def generate_json(self, prompt: str, system_prompt: str | None = None) -> dict[str, Any]:
        sys = (system_prompt or "") + "\nIMPORTANT: Respond ONLY with a valid JSON object, without markdown tags or comments."
        raw_output = self._send_request(prompt, system_prompt=sys.strip())
        cleaned = raw_output.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
            if match:
                return json.loads(match.group(1))
            raise ValueError(f"Could not parse Anthropic response as JSON: {cleaned[:200]}") from exc

    def generate_chat(self, messages: list[dict[str, str]], system_prompt: str | None = None) -> str:
        if not self.api_key:
            raise ValueError("Anthropic API key (ANTHROPIC_API_KEY) is not configured.")

        url = f"{self.base_url}/messages"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "User-Agent": "LEAI-CLI",
        }

        anthropic_msgs = []
        for m in messages:
            role = "user" if m.get("role") == "user" else "assistant"
            anthropic_msgs.append({"role": role, "content": m.get("content", "")})

        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 4096,
            "temperature": self.temperature,
            "messages": anthropic_msgs,
        }

        if system_prompt:
            payload["system"] = system_prompt

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                contents = resp_data.get("content", [])
                if not contents:
                    raise RuntimeError(f"Anthropic API retornou resposta sem conteúdo: {resp_data}")
                return contents[0]["text"]
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Erro na API da Anthropic (HTTP {exc.code}): {err_body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Erro de conexão com a Anthropic: {exc.reason}") from exc

