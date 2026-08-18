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
                usage = resp_data.get("usage", {})
                self.record_usage(
                    prompt_tokens=usage.get("input_tokens", 0),
                    completion_tokens=usage.get("output_tokens", 0),
                )
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
        cleaned = cleaned.removesuffix("```")
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
                usage = resp_data.get("usage", {})
                self.record_usage(
                    prompt_tokens=usage.get("input_tokens", 0),
                    completion_tokens=usage.get("output_tokens", 0),
                )
                contents = resp_data.get("content", [])
                if not contents:
                    raise RuntimeError(f"Anthropic API retornou resposta sem conteúdo: {resp_data}")
                return contents[0]["text"]
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Erro na API da Anthropic (HTTP {exc.code}): {err_body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Erro de conexão com a Anthropic: {exc.reason}") from exc

    def stream_chat(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str | None = None,
        on_chunk: Any = None,
    ) -> str:
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
            "stream": True,
        }

        if system_prompt:
            payload["system"] = system_prompt

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        collected_text = []
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                for raw_line in resp:
                    line = raw_line.decode("utf-8").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    try:
                        chunk_json = json.loads(data_str)
                        ev_type = chunk_json.get("type", "")
                        if ev_type == "message_start":
                            msg_usage = chunk_json.get("message", {}).get("usage", {})
                            self.record_usage(
                                prompt_tokens=msg_usage.get("input_tokens", 0),
                                completion_tokens=msg_usage.get("output_tokens", 0),
                            )
                        elif ev_type == "content_block_delta":
                            delta = chunk_json.get("delta", {})
                            txt = delta.get("text", "")
                            if txt:
                                collected_text.append(txt)
                                if on_chunk and callable(on_chunk):
                                    on_chunk(txt)
                        elif ev_type == "message_delta":
                            d_usage = chunk_json.get("usage", {})
                            if d_usage:
                                self.record_usage(
                                    completion_tokens=d_usage.get("output_tokens", 0),
                                )
                    except Exception:
                        continue
        except Exception:
            if not collected_text:
                full_res = self.generate_chat(messages, system_prompt=system_prompt)
                if on_chunk and callable(on_chunk) and full_res:
                    on_chunk(full_res)
                return full_res

        return "".join(collected_text)

    def list_models(self) -> list[dict[str, str]]:
        if not self.api_key:
            return [
                {
                    "id": "claude-3-5-sonnet-20241022",
                    "name": "Claude 3.5 Sonnet (Latest)",
                    "description": "State of the art intelligence & coding",
                },
                {"id": "claude-3-5-haiku-20241022", "name": "Claude 3.5 Haiku", "description": "High speed and low latency"},
                {"id": "claude-3-opus-20240229", "name": "Claude 3 Opus", "description": "Deep complex analysis"},
            ]

        url = f"{self.base_url}/models"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "User-Agent": "LEAI-CLI",
        }
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                models = []
                for item in resp_data.get("data", []):
                    m_id = item.get("id", "")
                    if m_id:
                        models.append(
                            {
                                "id": m_id,
                                "name": item.get("display_name", m_id),
                                "description": f"Created: {item.get('created_at', '')[:10]}" if item.get("created_at") else "",
                            }
                        )
                if models:
                    models.sort(key=lambda x: x["id"])
                    return models
        except Exception:
            pass

        return [
            {
                "id": "claude-3-5-sonnet-20241022",
                "name": "Claude 3.5 Sonnet (Latest)",
                "description": "State of the art intelligence & coding",
            },
            {"id": "claude-3-5-haiku-20241022", "name": "Claude 3.5 Haiku", "description": "High speed and low latency"},
            {"id": "claude-3-opus-20240229", "name": "Claude 3 Opus", "description": "Deep complex analysis"},
        ]
