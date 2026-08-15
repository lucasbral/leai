from __future__ import annotations
import json
import re
import urllib.error
import urllib.request
from typing import Any

from leai.ai.base import BaseLLMClient


class GeminiClient(BaseLLMClient):
    """Direct client for the Google Gemini REST API."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        temperature: float = 0.2,
    ):
        super().__init__(
            api_key=api_key or "",
            model=model or "gemini-1.5-flash",
            base_url=(base_url or "https://generativelanguage.googleapis.com/v1beta").rstrip("/"),
            temperature=temperature,
        )

    def _send_request(self, prompt: str, system_prompt: str | None = None, response_mime_type: str = "text/plain") -> str:
        if not self.api_key:
            raise ValueError("Gemini API key (GEMINI_API_KEY) is not configured.")

        url = f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}"
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "LEAI-CLI",
        }

        payload: dict[str, Any] = {
            "contents": [
                {
                    "parts": [{"text": prompt}],
                }
            ],
            "generationConfig": {
                "temperature": self.temperature,
                "responseMimeType": response_mime_type,
            },
        }

        if system_prompt:
            payload["systemInstruction"] = {
                "parts": [{"text": system_prompt}],
            }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                candidates = resp_data.get("candidates", [])
                if not candidates:
                    raise RuntimeError(f"Gemini API returned response with no candidates: {resp_data}")
                return candidates[0]["content"]["parts"][0]["text"]
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Gemini API error (HTTP {exc.code}): {err_body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Connection error with Gemini: {exc.reason}") from exc

    def generate_text(self, prompt: str, system_prompt: str | None = None) -> str:
        return self._send_request(prompt, system_prompt=system_prompt, response_mime_type="text/plain")

    def generate_json(self, prompt: str, system_prompt: str | None = None) -> dict[str, Any]:
        sys = (system_prompt or "") + "\nIMPORTANT: Respond ONLY with a valid JSON object."
        raw_output = self._send_request(prompt, system_prompt=sys.strip(), response_mime_type="application/json")
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
            raise ValueError(f"Could not parse Gemini response as JSON: {cleaned[:200]}") from exc

    def generate_chat(self, messages: list[dict[str, str]], system_prompt: str | None = None) -> str:
        if not self.api_key:
            raise ValueError("Gemini API key (GEMINI_API_KEY) is not configured.")

        url = f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}"
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "LEAI-CLI",
        }

        gemini_contents = []
        for m in messages:
            role = "user" if m.get("role") == "user" else "model"
            gemini_contents.append({
                "role": role,
                "parts": [{"text": m.get("content", "")}],
            })

        payload: dict[str, Any] = {
            "contents": gemini_contents,
            "generationConfig": {
                "temperature": self.temperature,
                "responseMimeType": "text/plain",
            },
        }

        if system_prompt:
            payload["systemInstruction"] = {
                "parts": [{"text": system_prompt}],
            }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                candidates = resp_data.get("candidates", [])
                if not candidates:
                    raise RuntimeError(f"Gemini API returned response with no candidates: {resp_data}")
                return candidates[0]["content"]["parts"][0]["text"]
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Gemini API error (HTTP {exc.code}): {err_body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Connection error with Gemini: {exc.reason}") from exc

