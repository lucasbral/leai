from __future__ import annotations

import os

from leai.ai.anthropic_client import AnthropicClient
from leai.ai.base import BaseLLMClient
from leai.ai.gemini_client import GeminiClient
from leai.ai.openai_client import OpenAICompatibleClient
from leai.config import LeaiConfig

PROVIDER_DEFAULTS = {
    "openai": {
        "env_key": "OPENAI_API_KEY",
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
    },
    "gemini": {
        "env_key": "GEMINI_API_KEY",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "default_model": "gemini-1.5-flash",
    },
    "anthropic": {
        "env_key": "ANTHROPIC_API_KEY",
        "base_url": "https://api.anthropic.com/v1",
        "default_model": "claude-3-5-sonnet-20241022",
    },
    "deepseek": {
        "env_key": "DEEPSEEK_API_KEY",
        "base_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat",
    },
    "qwen": {
        "env_key": "DASHSCOPE_API_KEY",
        "base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "default_model": "qwen-plus",
    },
    "kimi": {
        "env_key": "MOONSHOT_API_KEY",
        "base_url": "https://api.moonshot.cn/v1",
        "default_model": "moonshot-v1-8k",
    },
    "ollama": {
        "env_key": None,
        "base_url": "http://localhost:11434/v1",
        "default_model": "llama3.1",
    },
}


def get_llm_client(
    config: LeaiConfig,
    provider_override: str | None = None,
    model_override: str | None = None,
) -> BaseLLMClient:
    """Instantiates and returns the appropriate LLM client based on configuration or overrides."""
    provider_name = (provider_override or config.ai.default_provider or "openai").lower()
    p_cfg = config.ai.providers.get(provider_name)
    defaults = PROVIDER_DEFAULTS.get(provider_name, {})

    env_var = defaults.get("env_key")
    api_key = (p_cfg and p_cfg.api_key) or (os.getenv(env_var) if env_var else None) or os.getenv(f"{provider_name.upper()}_API_KEY")
    base_url = (p_cfg and p_cfg.base_url) or defaults.get("base_url")
    model = model_override or (p_cfg and p_cfg.model) or defaults.get("default_model") or "gpt-4o-mini"
    temp = config.ai.temperature

    if provider_name == "gemini":
        return GeminiClient(api_key=api_key, model=model, base_url=base_url, temperature=temp)
    elif provider_name in ("anthropic", "claude"):
        return AnthropicClient(api_key=api_key, model=model, base_url=base_url, temperature=temp)
    else:
        # Default OpenAI-compatible client (handles OpenAI, DeepSeek, Qwen, Kimi, Ollama, etc.)
        return OpenAICompatibleClient(api_key=api_key, model=model, base_url=base_url, temperature=temp)
