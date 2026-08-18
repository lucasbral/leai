from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

from leai.ai.base import BaseLLMClient


def _convert_schema_to_gemini(schema: dict[str, Any]) -> dict[str, Any]:
    """Recursively converts standard JSON Schema type names to Gemini uppercase type names."""
    res = dict(schema)
    if "type" in res and isinstance(res["type"], str):
        res["type"] = res["type"].upper()
    if "properties" in res and isinstance(res["properties"], dict):
        res["properties"] = {k: _convert_schema_to_gemini(v) for k, v in res["properties"].items()}
    if "items" in res and isinstance(res["items"], dict):
        res["items"] = _convert_schema_to_gemini(res["items"])
    return res


def _convert_tools_to_gemini(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Converts standard OpenAI-format tool definitions to Gemini functionDeclarations."""
    fn_decls = []
    for td in tools:
        fn = td.get("function", td)
        fn_decls.append(
            {
                "name": fn["name"],
                "description": fn.get("description", ""),
                "parameters": _convert_schema_to_gemini(fn.get("parameters", {})),
            }
        )
    return [{"functionDeclarations": fn_decls}]


class GeminiClient(BaseLLMClient):
    """Direct client for the Google Gemini REST API with native Function Calling support."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        temperature: float = 0.2,
    ):
        super().__init__(
            api_key=api_key or "",
            model=model or "gemini-2.5-flash",
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
                usage = resp_data.get("usageMetadata", {})
                self.record_usage(
                    prompt_tokens=usage.get("promptTokenCount", 0),
                    completion_tokens=usage.get("candidatesTokenCount", 0),
                    total_tokens=usage.get("totalTokenCount"),
                )
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
        cleaned = cleaned.removesuffix("```")
        cleaned = cleaned.strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
            if match:
                return json.loads(match.group(1))
            raise ValueError(f"Could not parse Gemini response as JSON: {cleaned[:200]}") from exc

    def generate_chat(self, messages: list[dict[str, str]], system_prompt: str | None = None) -> str:
        content, _ = self.generate_chat_with_tools(messages, tools=None, system_prompt=system_prompt)
        return content or ""

    def stream_chat(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str | None = None,
        on_chunk: Any = None,
    ) -> str:
        if not self.api_key:
            raise ValueError("Gemini API key (GEMINI_API_KEY) is not configured.")

        url = f"{self.base_url}/models/{self.model}:streamGenerateContent?alt=sse&key={self.api_key}"
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "LEAI-CLI",
        }

        gemini_contents = []
        for m in messages:
            role = m.get("role")
            if role == "user":
                txt = (m.get("content") or "").strip()
                if txt:
                    gemini_contents.append(
                        {
                            "role": "user",
                            "parts": [{"text": txt}],
                        }
                    )
            elif role == "assistant":
                parts = []
                if m.get("content"):
                    parts.append({"text": m["content"]})
                if parts:
                    gemini_contents.append(
                        {
                            "role": "model",
                            "parts": parts,
                        }
                    )

        payload: dict[str, Any] = {
            "contents": gemini_contents,
            "generationConfig": {
                "temperature": self.temperature,
            },
        }
        if system_prompt:
            payload["systemInstruction"] = {
                "parts": [{"text": system_prompt}],
            }

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
                        usage = chunk_json.get("usageMetadata", {})
                        if usage:
                            self.record_usage(
                                prompt_tokens=usage.get("promptTokenCount", 0),
                                completion_tokens=usage.get("candidatesTokenCount", 0),
                                total_tokens=usage.get("totalTokenCount"),
                            )
                        candidates = chunk_json.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            for part in parts:
                                txt = part.get("text", "")
                                if txt:
                                    collected_text.append(txt)
                                    if on_chunk and callable(on_chunk):
                                        on_chunk(txt)
                    except Exception:
                        continue
        except Exception:
            if not collected_text:
                full_res = self.generate_chat(messages, system_prompt=system_prompt)
                if on_chunk and callable(on_chunk) and full_res:
                    on_chunk(full_res)
                return full_res

        return "".join(collected_text)

    def generate_chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        system_prompt: str | None = None,
    ) -> tuple[str | None, list[dict[str, Any]]]:
        if not self.api_key:
            raise ValueError("Gemini API key (GEMINI_API_KEY) is not configured.")

        url = f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}"
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "LEAI-CLI",
        }

        gemini_contents = []
        for m in messages:
            role = m.get("role")
            if role == "user":
                txt = (m.get("content") or "").strip()
                if txt:
                    gemini_contents.append(
                        {
                            "role": "user",
                            "parts": [{"text": txt}],
                        }
                    )
            elif role == "assistant":
                parts = []
                if m.get("content"):
                    parts.append({"text": m["content"]})
                if m.get("tool_calls"):
                    for tc in m["tool_calls"]:
                        fn = tc.get("function", {})
                        args = fn.get("arguments", {})
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except Exception:
                                args = {}
                        fc_part: dict[str, Any] = {
                            "functionCall": {
                                "name": fn.get("name") or tc.get("name"),
                                "args": args,
                            }
                        }
                        ts = tc.get("thought_signature") or fn.get("thought_signature")
                        if ts:
                            fc_part["thoughtSignature"] = ts
                        parts.append(fc_part)
                if parts:
                    gemini_contents.append(
                        {
                            "role": "model",
                            "parts": parts,
                        }
                    )
            elif role == "tool":
                raw_c = m.get("content", "")
                try:
                    resp_obj = json.loads(raw_c) if isinstance(raw_c, str) else raw_c
                except Exception:
                    resp_obj = {"output": raw_c}
                gemini_contents.append(
                    {
                        "role": "function",
                        "parts": [
                            {
                                "functionResponse": {
                                    "name": m.get("name", "tool"),
                                    "response": {"output": resp_obj},
                                }
                            }
                        ],
                    }
                )

        payload: dict[str, Any] = {
            "contents": gemini_contents,
            "generationConfig": {
                "temperature": self.temperature,
            },
        }

        if tools:
            payload["tools"] = _convert_tools_to_gemini(tools)

        if system_prompt:
            payload["systemInstruction"] = {
                "parts": [{"text": system_prompt}],
            }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                usage = resp_data.get("usageMetadata", {})
                self.record_usage(
                    prompt_tokens=usage.get("promptTokenCount", 0),
                    completion_tokens=usage.get("candidatesTokenCount", 0),
                    total_tokens=usage.get("totalTokenCount"),
                )
                candidates = resp_data.get("candidates", [])
                if not candidates:
                    raise RuntimeError(f"Gemini API returned response with no candidates: {resp_data}")

                cand_content = candidates[0].get("content", {})
                parts = cand_content.get("parts", [])

                text_parts = []
                tool_calls = []

                for p in parts:
                    if "text" in p:
                        text_parts.append(p["text"])
                    if "functionCall" in p:
                        fc = p["functionCall"]
                        tc_dict = {
                            "id": f"call_{fc.get('name', 'fn')}",
                            "name": fc.get("name", ""),
                            "arguments": fc.get("args", {}),
                        }
                        ts = p.get("thoughtSignature") or p.get("thought_signature")
                        if ts:
                            tc_dict["thought_signature"] = ts
                        tool_calls.append(tc_dict)

                combined_text = "\n".join(text_parts).strip() if text_parts else None
                return combined_text, tool_calls
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            # If function calling is not supported or errors, fallback to generate_chat without tools
            if exc.code in (400, 404, 422) and tools:
                fallback_res = self.generate_chat(messages, system_prompt=system_prompt)
                return fallback_res, []
            raise RuntimeError(f"Gemini API error (HTTP {exc.code}): {err_body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Connection error with Gemini: {exc.reason}") from exc

    def list_models(self) -> list[dict[str, str]]:
        if not self.api_key:
            return [{"id": self.model or "gemini-2.5-flash", "name": self.model or "gemini-2.5-flash", "note": "API key not configured"}]

        url = f"{self.base_url}/models?key={self.api_key}"
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "LEAI-CLI",
        }
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                models = []
                for item in resp_data.get("models", []):
                    m_name = item.get("name", "")
                    m_id = m_name.replace("models/", "")
                    display = item.get("displayName", m_id)
                    methods = item.get("supportedGenerationMethods", [])
                    if "generateContent" in methods:
                        desc = item.get("description", "")
                        if len(desc) > 80:
                            desc = desc[:77] + "..."
                        models.append(
                            {
                                "id": m_id,
                                "name": display,
                                "description": desc,
                            }
                        )
                models.sort(key=lambda x: x["id"])
                return models
        except Exception as exc:
            return [{"id": self.model or "gemini-2.5-flash", "name": self.model or "gemini-2.5-flash", "note": f"Error: {exc}"}]
