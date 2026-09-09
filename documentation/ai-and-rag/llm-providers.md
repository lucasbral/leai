# Provedores de LLM Suportados

O LEAI possui um cliente HTTP REST nativo e ultraleve, dispensando SDKs externos pesados para se comunicar com as principais APIs de Inteligência Artificial do mercado.

---

## 🌐 Provedores Suportados e Variáveis de Ambiente

| Provedor | Parâmetro em `leai.yml` | Variável de Ambiente | Modelos Recomendados |
| :--- | :--- | :--- | :--- |
| **Ollama (Local / Grátis)** | `ollama` | Nenhuma (requer Ollama local) | `qwen2.5-coder:latest`, `llama3.1`, `mistral` |
| **Local (LM Studio / vLLM)** | `local` ou `custom` | Nenhuma (requer servidor local ativo) | `qwen2.5`, `meta-llama-3.1-8b-instruct` |
| **Google Gemini** | `gemini` | `GEMINI_API_KEY` | `gemini-2.5-flash`, `gemini-1.5-pro` |
| **OpenAI** | `openai` | `OPENAI_API_KEY` | `gpt-4o`, `gpt-4o-mini`, `o3-mini` |
| **Anthropic Claude** | `claude` / `anthropic` | `ANTHROPIC_API_KEY` | `claude-3-5-sonnet-20241022`, `claude-3-5-haiku-20241022` |
| **DeepSeek** | `deepseek` | `DEEPSEEK_API_KEY` | `deepseek-chat`, `deepseek-reasoner` |
| **Qwen (Alibaba)** | `qwen` | `DASHSCOPE_API_KEY` | `qwen-plus`, `qwen-max`, `qwen-turbo` |
| **Moonshot Kimi** | `kimi` | `MOONSHOT_API_KEY` | `moonshot-v1-8k`, `moonshot-v1-32k` |
| **Grok / xAI** | `grok` ou `xai` | `GROK_API_KEY` / `XAI_API_KEY` | `grok-2-latest` |

---

## ⚙️ Exemplos de Configuração no `leai.yml`

O LEAI suporta configurações globais e sobrescritas granulares por provedor:

```yaml
ai:
  default_provider: "ollama"      # Provedor ativo padrão
  temperature: 0.2                # Temperatura global (0.0 a 1.0)
  timeout: 300.0                  # Timeout global em segundos
  max_history_turns: 15           # Janela de memória do chat (turnos)
  max_agent_iterations: 10        # Limite máximo de chamadas de tools do agente
  max_subagent_iterations: 5      # Limite de iterações de subagentes especialistas

  providers:
    # 1. Ollama local
    ollama:
      base_url: "http://localhost:11434/v1"
      model: "qwen2.5-coder:latest"
      temperature: 0.1
      timeout: 300.0

    # 2. Servidor local OpenAI-compatível (LM Studio, vLLM, LocalAI)
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

## 🧪 Validando Modelos com `leai models`

Execute o comando a seguir para listar os modelos disponíveis:

```bash
# Listar modelos do provedor configurado como padrão
leai models

# Listar modelos de um provedor específico
leai models -p gemini
leai models -p ollama
