from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

from leai.ai.base import BaseLLMClient


def extract_embedded_tool_calls(content: str, tools: list[dict[str, Any]] | None = None) -> tuple[str | None, list[dict[str, Any]]]:
    """Extracts tool calls embedded inside conversational text, markdown fences, or XML tags.

    Supports:
    1. <tool_call>...</tool_call> tags (Qwen / Ollama / Hermes format).
    2. Markdown code fences (```json ... ```).
    3. Free-form conversational text with embedded JSON tool call objects.
    """
    if not content:
        return content, []

    valid_names = set()
    if tools:
        for t in tools:
            if isinstance(t, dict):
                if "function" in t and isinstance(t["function"], dict) and "name" in t["function"]:
                    valid_names.add(t["function"]["name"])
                elif "name" in t:
                    valid_names.add(t["name"])

    extracted: list[dict[str, Any]] = []

    # 1. Look for <tool_call>...</tool_call> tags
    tag_matches = re.findall(r"<tool_call>(.*?)</tool_call>", content, re.DOTALL)
    for tm in tag_matches:
        try:
            parsed = json.loads(tm.strip())
            if isinstance(parsed, dict) and "name" in parsed:
                extracted.append(parsed)
            elif isinstance(parsed, list):
                extracted.extend([x for x in parsed if isinstance(x, dict) and "name" in x])
        except Exception:
            pass

    # 2. Look for markdown fenced blocks ```json ... ```
    if not extracted:
        block_matches = re.findall(r"```(?:json)?\s*(.*?)\s*```", content, re.DOTALL)
        for bm in block_matches:
            try:
                parsed = json.loads(bm.strip())
                if isinstance(parsed, dict) and "name" in parsed:
                    extracted.append(parsed)
                elif isinstance(parsed, list):
                    extracted.extend([x for x in parsed if isinstance(x, dict) and "name" in x])
            except Exception:
                pass

    # 3. Direct/embedded JSON objects search using raw_decode
    if not extracted:
        idx = 0
        decoder = json.JSONDecoder()
        while idx < len(content):
            brace_pos = content.find("{", idx)
            if brace_pos == -1:
                break
            try:
                obj, end_pos = decoder.raw_decode(content[brace_pos:])
                if isinstance(obj, dict) and "name" in obj and ("arguments" in obj or "parameters" in obj):
                    extracted.append(obj)
                    idx = brace_pos + end_pos
                    continue
            except Exception:
                pass
            idx = brace_pos + 1

    # Filter to valid tool names if tools list is provided
    if valid_names and extracted:
        extracted = [x for x in extracted if x.get("name") in valid_names]

    if not extracted:
        return content, []

    tool_calls: list[dict[str, Any]] = []
    for i, item in enumerate(extracted):
        fn_name = item.get("name", "")
        raw_args = item.get("arguments") or item.get("parameters") or {}
        if isinstance(raw_args, str):
            try:
                raw_args = json.loads(raw_args)
            except Exception:
                raw_args = {}
        tool_calls.append(
            {
                "id": f"call_{fn_name}_{i}",
                "name": fn_name,
                "arguments": raw_args,
            }
        )

    # When tool calls are extracted, suppress the intermediate meta-commentary
    return None, tool_calls


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
        timeout: float = 300.0,
        num_ctx: int | None = None,
        max_tokens: int | None = None,
        top_p: float | None = None,
        keep_alive: str | None = None,
        options: dict[str, Any] | None = None,
    ):
        super().__init__(
            api_key=api_key or "",
            model=model or "gpt-4o-mini",
            base_url=(base_url or "https://api.openai.com/v1").rstrip("/"),
            temperature=temperature,
            timeout=timeout,
            num_ctx=num_ctx,
            max_tokens=max_tokens,
            top_p=top_p,
            keep_alive=keep_alive,
            options=options,
        )

    def _build_payload(
        self,
        messages: list[dict[str, Any]],
        stream: bool = False,
        response_format_json: bool = False,
        tools: list[dict[str, Any]] | None = None,
        tool_choice_mode: str = "auto",
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
        }
        if self.max_tokens is not None:
            payload["max_tokens"] = self.max_tokens
        if self.top_p is not None:
            payload["top_p"] = self.top_p

        is_ollama = "ollama" in (self.base_url or "").lower() or (self.base_url or "").startswith("http://localhost:11434")

        # Injetar opções específicas para Ollama / vLLM / backends locais
        local_options = dict(self.options) if self.options else {}
        if self.num_ctx is not None:
            local_options["num_ctx"] = self.num_ctx
        if self.top_p is not None and "top_p" not in local_options:
            local_options["top_p"] = self.top_p
        if self.temperature is not None and "temperature" not in local_options:
            local_options["temperature"] = self.temperature

        if local_options:
            payload["options"] = local_options

        if self.keep_alive is not None:
            payload["keep_alive"] = self.keep_alive

        if response_format_json and not is_ollama:
            payload["response_format"] = {"type": "json_object"}

        if stream:
            payload["stream"] = True
            payload["stream_options"] = {"include_usage": True}

        if tools:
            payload["tools"] = tools
            if tool_choice_mode == "required":
                payload["tool_choice"] = "required"
            elif tool_choice_mode == "none":
                payload["tool_choice"] = "none"

        return payload

    def _send_request(self, messages: list[dict[str, str]], response_format_json: bool = False) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "LEAI-CLI",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = self._build_payload(messages, response_format_json=response_format_json)

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                usage = resp_data.get("usage", {})
                self.record_usage(
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                    total_tokens=usage.get("total_tokens"),
                )
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

    def stream_chat(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str | None = None,
        on_chunk: Any = None,
    ) -> str:
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

        payload = self._build_payload(all_msgs, stream=True)

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        collected_text = []
        usage_found = False

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                for raw_line in resp:
                    line = raw_line.decode("utf-8").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk_json = json.loads(data_str)
                        # Check usage
                        if "usage" in chunk_json and chunk_json["usage"]:
                            u = chunk_json["usage"]
                            self.record_usage(
                                prompt_tokens=u.get("prompt_tokens", 0),
                                completion_tokens=u.get("completion_tokens", 0),
                                total_tokens=u.get("total_tokens"),
                            )
                            usage_found = True
                        choices = chunk_json.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            delta_content = delta.get("content") or ""
                            if delta_content:
                                collected_text.append(delta_content)
                                if on_chunk and callable(on_chunk):
                                    on_chunk(delta_content)
                    except Exception:
                        continue
        except Exception:
            # If streaming fails (e.g. proxy/provider doesn't support SSE stream_options), fallback to standard
            if not collected_text:
                full_res = self.generate_chat(messages, system_prompt=system_prompt)
                if on_chunk and callable(on_chunk) and full_res:
                    on_chunk(full_res)
                return full_res

        full_output = "".join(collected_text)
        if not usage_found and full_output:
            est_prompt = (len(system_prompt or "") + sum(len(m.get("content", "")) for m in messages)) // 4
            est_comp = len(full_output) // 4
            self.record_usage(prompt_tokens=est_prompt, completion_tokens=est_comp, total_tokens=est_prompt + est_comp)
        return full_output

    def generate_chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        system_prompt: str | None = None,
        tool_choice_mode: str = "auto",
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

        payload = self._build_payload(all_msgs, tools=tools, tool_choice_mode=tool_choice_mode)

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                usage = resp_data.get("usage", {})
                self.record_usage(
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                    total_tokens=usage.get("total_tokens"),
                )
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

                    tool_calls.append(
                        {
                            "id": tc.get("id", f"call_{fn_name}"),
                            "name": fn_name,
                            "arguments": parsed_args,
                        }
                    )

                # Fallback: some local models (e.g. Ollama with Qwen/Llama) output tool calls
                # as a JSON string inside content, wrapped in markdown/tags, or mixed with conversational text
                if not tool_calls and content and tools:
                    content, tool_calls = extract_embedded_tool_calls(content, tools=tools)

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

    def stream_chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        system_prompt: str | None = None,
        tool_choice_mode: str = "auto",
        on_token: Any = None,
        on_thought: Any = None,
    ) -> tuple[str | None, list[dict[str, Any]]]:
        """Streams chat completions processing SSE events with live tool calling and thought/reasoning deltas."""
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

        payload = self._build_payload(all_msgs, stream=True, tools=tools, tool_choice_mode=tool_choice_mode)
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        collected_text: list[str] = []
        collected_reasoning: list[str] = []
        accumulated_tcs: dict[int, dict[str, Any]] = {}
        usage_found = False

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                for raw_line in resp:
                    line = raw_line.decode("utf-8").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk_json = json.loads(data_str)
                        # Check usage
                        if "usage" in chunk_json and chunk_json["usage"]:
                            u = chunk_json["usage"]
                            self.record_usage(
                                prompt_tokens=u.get("prompt_tokens", 0),
                                completion_tokens=u.get("completion_tokens", 0),
                                total_tokens=u.get("total_tokens"),
                            )
                            usage_found = True

                        choices = chunk_json.get("choices", [])
                        if not choices:
                            continue

                        delta = choices[0].get("delta", {})

                        # 1. Process reasoning/thought tokens (e.g. DeepSeek-R1, Qwen Reasoning)
                        r_content = delta.get("reasoning_content") or delta.get("reasoning") or ""
                        if r_content:
                            collected_reasoning.append(r_content)
                            if on_thought and callable(on_thought):
                                on_thought(r_content)
                            elif on_token and callable(on_token):
                                on_token(r_content)

                        # 2. Process regular content
                        c_content = delta.get("content") or ""
                        if c_content:
                            collected_text.append(c_content)
                            if on_token and callable(on_token):
                                on_token(c_content)

                        # 3. Process incremental tool call deltas
                        raw_tcs = delta.get("tool_calls", [])
                        for tc_delta in raw_tcs:
                            idx = tc_delta.get("index", 0)
                            if idx not in accumulated_tcs:
                                accumulated_tcs[idx] = {
                                    "id": tc_delta.get("id") or f"call_{idx}",
                                    "name": "",
                                    "arguments": "",
                                }
                            if tc_delta.get("id"):
                                accumulated_tcs[idx]["id"] = tc_delta["id"]
                            fn_chunk = tc_delta.get("function", {})
                            if fn_chunk.get("name"):
                                accumulated_tcs[idx]["name"] += fn_chunk["name"]
                            if fn_chunk.get("arguments"):
                                accumulated_tcs[idx]["arguments"] += fn_chunk["arguments"]
                    except Exception:
                        continue
        except Exception:
            # Fallback to standard synchronous generate_chat_with_tools if stream fails
            if not collected_text and not accumulated_tcs:
                return self.generate_chat_with_tools(messages, tools=tools, system_prompt=system_prompt, tool_choice_mode=tool_choice_mode)

        # Consolidate parsed tool calls
        final_tool_calls: list[dict[str, Any]] = []
        for idx in sorted(accumulated_tcs.keys()):
            tc_data = accumulated_tcs[idx]
            raw_args = tc_data.get("arguments", "{}")
            try:
                parsed_args = json.loads(raw_args) if isinstance(raw_args, str) and raw_args.strip() else {}
            except Exception:
                parsed_args = {}
            fn_name = tc_data.get("name", "").strip()
            if fn_name:
                final_tool_calls.append(
                    {
                        "id": tc_data.get("id", f"call_{fn_name}"),
                        "name": fn_name,
                        "arguments": parsed_args,
                    }
                )

        full_content = "".join(collected_text).strip() if collected_text else None

        # Fallback for models outputting embedded tool calls in text during streaming
        if not final_tool_calls and full_content and tools:
            full_content, final_tool_calls = extract_embedded_tool_calls(full_content, tools=tools)

        if not usage_found and full_content:
            est_prompt = (len(system_prompt or "") + sum(len(m.get("content", "")) for m in messages)) // 4
            est_comp = len(full_content) // 4
            self.record_usage(prompt_tokens=est_prompt, completion_tokens=est_comp, total_tokens=est_prompt + est_comp)

        return full_content, final_tool_calls

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
