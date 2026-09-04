# Supported LLM Providers

LEAI features a native, lightweight REST HTTP client, eliminating heavy external dependencies while connecting directly to industry-standard AI platforms.

---

## 🌐 Supported Providers & Environment Variables

| Provider | `provider` in `leai.yml` | Environment Variable | Recommended Models |
| :--- | :--- | :--- | :--- |
| **OpenAI** | `openai` | `OPENAI_API_KEY` | `gpt-4o`, `gpt-4o-mini`, `o3-mini` |
| **Google Gemini** | `gemini` | `GEMINI_API_KEY` | `gemini-1.5-pro`, `gemini-1.5-flash`, `gemini-2.0-flash` |
| **Anthropic Claude** | `claude` | `ANTHROPIC_API_KEY` | `claude-3-5-sonnet-20241022`, `claude-3-5-haiku-20241022` |
| **DeepSeek** | `deepseek` | `DEEPSEEK_API_KEY` | `deepseek-chat`, `deepseek-reasoner` |
| **Qwen (Alibaba)** | `qwen` | `DASHSCOPE_API_KEY` | `qwen-plus`, `qwen-max`, `qwen-turbo` |
| **Moonshot Kimi** | `kimi` | `MOONSHOT_API_KEY` | `moonshot-v1-8k`, `moonshot-v1-32k` |
| **Ollama (Local / Free)** | `ollama` | None (requires local Ollama server) | `qwen2.5-coder`, `llama3.1`, `mistral` |
| **AWS Bedrock** | `bedrock` | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION` | `anthropic.claude-3-5-sonnet-20240620-v1:0` |

---

## ⚙️ Configuration Examples in `leai.yml`

### Using Google Gemini (High Speed & Value)
```yaml
ai:
  provider: "gemini"
  model: "gemini-2.0-flash"
  temperature: 0.1
```

### Using OpenAI
```yaml
ai:
  provider: "openai"
  model: "gpt-4o-mini"
  temperature: 0.2
```

### Using Local Ollama (100% Offline & Air-Gapped)
Ideal for restricted enterprise environments where metadata must remain on premises:

```yaml
ai:
  provider: "ollama"
  model: "qwen2.5-coder:14b"
  base_url: "http://localhost:11434"
```

---

## 🧪 Validating Connections with `leai models`

Run the diagnostic command to test API keys and verify roundtrip response latencies:

```bash
leai models
```
