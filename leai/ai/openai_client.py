from __future__ import annotations
import json
import re
import urllib.error
import urllib.request
from typing import Any

from leai.ai.base import BaseLLMClient


class OpenAICompatibleClient(BaseLLMClient):
    """Cliente universal compatível com o endpoint /chat/completions da OpenAI.
    Suporta: OpenAI (ChatGPT), DeepSeek, Qwen (DashScope), Kimi (Moonshot), Ollama, vLLM, LM Studio.
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
            # A maioria das APIs OpenAI-compatible suporta type: json_object
            payload["response_format"] = {"type": "json_object"}

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                return resp_data["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Erro na API de IA ({self.base_url} HTTP {exc.code}): {err_body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Erro de conexão com o provedor de IA ({self.base_url}): {exc.reason}") from exc

    def generate_text(self, prompt: str, system_prompt: str | None = None) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return self._send_request(messages, response_format_json=False)

    def generate_json(self, prompt: str, system_prompt: str | None = None) -> dict[str, Any]:
        sys = (system_prompt or "") + "\nIMPORTANTE: Responda APENAS com um objeto JSON válido, sem tags markdown ou comentários."
        messages = []
        if sys.strip():
            messages.append({"role": "system", "content": sys.strip()})
        messages.append({"role": "user", "content": prompt})

        raw_output = self._send_request(messages, response_format_json=True)
        # Limpar possíveis blocos ```json ... ```
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
            # Fallback para regex de primeiro bloco JSON
            match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
            if match:
                return json.loads(match.group(1))
            raise ValueError(f"Não foi possível converter a resposta do LLM para JSON: {cleaned[:200]}") from exc

    def generate_chat(self, messages: list[dict[str, str]], system_prompt: str | None = None) -> str:
        all_msgs = []
        if system_prompt:
            all_msgs.append({"role": "system", "content": system_prompt})
        all_msgs.extend(messages)
        return self._send_request(all_msgs, response_format_json=False)

