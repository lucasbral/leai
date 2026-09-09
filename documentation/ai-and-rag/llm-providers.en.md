# Supported LLM Providers

LEAI features a native, lightweight REST HTTP client, eliminating heavy external dependencies while connecting directly to industry-standard AI platforms.

---

## 🌐 Supported Providers & Environment Variables

| Provider | `provider` in `leai.yml` | Environment Variable | Recommended Models |
| :--- | :--- | :--- | :--- |
| **Ollama (Local / Free)** | `ollama` | None (requires local Ollama server) | `qwen2.5-coder:latest`, `llama3.1`, `mistral` |
| **Local (LM Studio / vLLM)** | `local` or `custom` | None (requires local running server) | `qwen2.5`, `meta-llama-3.1-8b-instruct` |
| **Google Gemini** | `gemini` | `GEMINI_API_KEY` | `gemini-2.5-flash`, `gemini-1.5-pro` |
| **OpenAI** | `openai` | `OPENAI_API_KEY` | `gpt-4o`, `gpt-4o-mini`, `o3-mini` |
| **Anthropic Claude** | `claude` / `anthropic` | `ANTHROPIC_API_KEY` | `claude-3-5-sonnet-20241022`, `claude-3-5-haiku-20241022` |
| **DeepSeek** | `deepseek` | `DEEPSEEK_API_KEY` | `deepseek-chat`, `deepseek-reasoner` |
| **Qwen (Alibaba)** | `qwen` | `DASHSCOPE_API_KEY` | `qwen-plus`, `qwen-max`, `qwen-turbo` |
| **Moonshot Kimi** | `kimi` | `MOONSHOT_API_KEY` | `moonshot-v1-8k`, `moonshot-v1-32k` |
| **Grok / xAI** | `grok` or `xai` | `GROK_API_KEY` / `XAI_API_KEY` | `grok-2-latest` |

---

## ⚙️ Configuration Examples in `leai.yml`

LEAI supports global defaults alongside granular per-provider overrides:

```yaml
ai:
  default_provider: "ollama"      # Default active provider
  temperature: 0.2                # Global temperature (0.0 to 1.0)
  timeout: 300.0                  # Global timeout in seconds
  max_history_turns: 15           # History context memory window (turns)
  max_agent_iterations: 10        # Max tool calling steps per agent turn
  max_subagent_iterations: 5      # Max iterations for specialist subagents

  providers:
    # 1. Local Ollama
    ollama:
      base_url: "http://localhost:11434/v1"
      model: "qwen2.5-coder:latest"
      temperature: 0.1
      timeout: 300.0

    # 2. Local OpenAI-compatible server (LM Studio, vLLM, LocalAI)
    local:
      base_url: "http://localhost:1234/v1"
      model: "qwen2.5"
      temperature: 0.1

    # 3. Google Gemini
    gemini:
      api_key: "${GEMINI_API_KEY}"
      model: "gemini-2.5-flash"

    # 4. OpenAI
    openai:
      api_key: "${OPENAI_API_KEY}"
      model: "gpt-4o-mini"
      temperature: 0.2
      timeout: 120.0
```

---

## 🧪 Validating Models with `leai models`

Run the diagnostic command to test API connectivity and view available models:

```bash
# List models for the default configured provider
leai models

# List models for a specific provider
leai models -p gemini
leai models -p ollama
