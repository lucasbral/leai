from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

from leai.ai.base import BaseLLMClient


class OpenAICompatibleClient(BaseLLMClient):
    """Universal client compatible with OpenAI's /chat/completions endpoint.
    Supports: OpenAI (ChatGPT), DeepSeek, Qwen (DashScope), Kimi (Moonshot), Ollama, vLLM, LM Studio.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        temperature: float = 0.2,
    ):
        super().__init__(
            api_key=api_key or "",
            model=model or "gpt-4o-mini",
            base_url=(base_url or "https://api.openai.com/v1").rstrip("/"),
            temperature=temperature,
        )

    def _send_request(self, messages: list[dict[str, str]], response_format_json: bool = False) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "LEAI-CLI",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
        }

        if response_format_json and "ollama" not in (self.base_url or "").lower():
            # Most OpenAI-compatible APIs support response_format type: json_object
            payload["response_format"] = {"type": "json_object"}

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                return resp_data["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"AI API error ({self.base_url} HTTP {exc.code}): {err_body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Connection error with AI provider ({self.base_url}): {exc.reason}") from exc

    def generate_text(self, prompt: str, system_prompt: str | None = None) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return self._send_request(messages, response_format_json=False)

    def generate_json(self, prompt: str, system_prompt: str | None = None) -> dict[str, Any]:
        sys = (system_prompt or "") + "\nIMPORTANT: Respond ONLY with a valid JSON object, without markdown tags or comments."
        messages = []
        if sys.strip():
            messages.append({"role": "system", "content": sys.strip()})
        messages.append({"role": "user", "content": prompt})

        raw_output = self._send_request(messages, response_format_json=True)
        # Clean potential ```json ... ``` code blocks
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
            # Fallback to regex for first valid JSON block
            match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
            if match:
                return json.loads(match.group(1))
            raise ValueError(f"Could not parse LLM response as JSON: {cleaned[:200]}") from exc

    def generate_chat(self, messages: list[dict[str, str]], system_prompt: str | None = None) -> str:
        all_msgs = []
        if system_prompt:
            all_msgs.append({"role": "system", "content": system_prompt})
        all_msgs.extend(messages)
        return self._send_request(all_msgs, response_format_json=False)

    def generate_chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        system_prompt: str | None = None,
    ) -> tuple[str | None, list[dict[str, Any]]]:
        all_msgs = []
        if system_prompt:
            all_msgs.append({"role": "system", "content": system_prompt})
        all_msgs.extend(messages)

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "LEAI-CLI",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": all_msgs,
            "temperature": self.temperature,
        }
        if tools:
            payload["tools"] = tools

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                choice_msg = resp_data["choices"][0]["message"]
                content = choice_msg.get("content")
                raw_tcs = choice_msg.get("tool_calls", [])

                tool_calls = []
                for tc in raw_tcs:
                    fn = tc.get("function", {})
                    fn_name = fn.get("name", "")
                    raw_args = fn.get("arguments", "{}")
                    if isinstance(raw_args, str):
                        try:
                            parsed_args = json.loads(raw_args)
                        except Exception:
                            parsed_args = {}
                    else:
                        parsed_args = raw_args or {}

                    tool_calls.append({
                        "id": tc.get("id", f"call_{fn_name}"),
                        "name": fn_name,
                        "arguments": parsed_args,
                    })

                return content, tool_calls
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            # If provider doesn't support tools, fallback to standard chat
            if exc.code in (400, 404, 422) and tools:
                fallback_res = self.generate_chat(messages, system_prompt=system_prompt)
                return fallback_res, []
            raise RuntimeError(f"AI API error ({self.base_url} HTTP {exc.code}): {err_body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Connection error with AI provider ({self.base_url}): {exc.reason}") from exc

    def list_models(self) -> list[dict[str, str]]:
        url = f"{self.base_url}/models"
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "LEAI-CLI",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                models = []
                data = resp_data.get("data", resp_data.get("models", []))
                for item in data:
                    if isinstance(item, dict):
                        m_id = item.get("id", item.get("name", ""))
                        if m_id:
                            models.append({"id": m_id, "name": m_id})
                    elif isinstance(item, str):
                        models.append({"id": item, "name": item})
                models.sort(key=lambda x: x["id"])
                return models or [{"id": self.model, "name": self.model}]
        except Exception as exc:
            return [{"id": self.model, "name": self.model, "note": f"Error: {exc}"}]

