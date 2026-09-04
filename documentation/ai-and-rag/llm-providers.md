# Provedores de LLM Suportados

O LEAI possui um cliente HTTP REST nativo e ultraleve, dispensando SDKs externos pesados para se comunicar com as principais APIs de Inteligência Artificial do mercado.

---

## 🌐 Provedores Suportados e Variáveis de Ambiente

| Provedor | Parâmetro em `leai.yml` | Variável de Ambiente | Modelos Recomendados |
| :--- | :--- | :--- | :--- |
| **OpenAI** | `openai` | `OPENAI_API_KEY` | `gpt-4o`, `gpt-4o-mini`, `o3-mini` |
| **Google Gemini** | `gemini` | `GEMINI_API_KEY` | `gemini-1.5-pro`, `gemini-1.5-flash`, `gemini-2.0-flash` |
| **Anthropic Claude** | `claude` | `ANTHROPIC_API_KEY` | `claude-3-5-sonnet-20241022`, `claude-3-5-haiku-20241022` |
| **DeepSeek** | `deepseek` | `DEEPSEEK_API_KEY` | `deepseek-chat`, `deepseek-reasoner` |
| **Qwen (Alibaba)** | `qwen` | `DASHSCOPE_API_KEY` | `qwen-plus`, `qwen-max`, `qwen-turbo` |
| **Moonshot Kimi** | `kimi` | `MOONSHOT_API_KEY` | `moonshot-v1-8k`, `moonshot-v1-32k` |
| **Ollama (Local / Grátis)** | `ollama` | Nenhuma (requer Ollama rodando localmente) | `qwen2.5-coder`, `llama3.1`, `mistral` |
| **AWS Bedrock** | `bedrock` | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION` | `anthropic.claude-3-5-sonnet-20240620-v1:0` |

---

## ⚙️ Exemplos de Configuração no `leai.yml`

### Usando Google Gemini (Excelente Custo-Benefício)
```yaml
ai:
  provider: "gemini"
  model: "gemini-2.0-flash"
  temperature: 0.1
```

### Usando OpenAI
```yaml
ai:
  provider: "openai"
  model: "gpt-4o-mini"
  temperature: 0.2
```

### Usando Ollama Localmente (100% Offline e Seguro)
Para ambientes corporativos restritos onde nenhum dado pode sair da rede interna:

```yaml
ai:
  provider: "ollama"
  model: "qwen2.5-coder:14b"
  base_url: "http://localhost:11434"
```

---

## 🧪 Validando Conexões com `leai models`

Execute o comando a seguir para testar suas chaves e medir os tempos de resposta:

```bash
leai models
```
