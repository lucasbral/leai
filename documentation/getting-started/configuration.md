# Configuração (`leai.yml`)

O arquivo de configuração `leai.yml` controla todos os aspectos de extração, filtragem, armazenamento, versionamento Git e integração com IA do LEAI.

---

## 📄 Exemplo Completo Comentado

```yaml
# ==============================================================================
# Configuração do LEAI
# ==============================================================================

# 1. Conexão com o Oracle (DSN)
# Suporta interpolação de variáveis de ambiente com ${VARIAVEL}
dsn: "oracle://${DB_USER}:${DB_PASS}@${DB_HOST}:1521/${DB_SERVICE}"

# 2. Schemas a Extrair
# Pode ser uma lista de schemas ou "ALL" (requer permissão de DBA/SELECT ANY DICTIONARY)
schemas:
  - RH
  - FINANCEIRO

# 3. Diretórios do Pipeline
rawPath: "./raw"                  # Snapshots técnicos em JSON
annotationsPath: "./annotations"  # Camada de anotações em YAML
docPath: "./docs"                  # Documentação final em Markdown

# 4. Filtros de Inclusão e Exclusão (Padrão SQL LIKE)
include:
  - FUNCIONARIOS
  - VENDAS_%
exclude:
  - BIN$%                         # Tabelas da lixeira do Oracle
  - SYS_%

# 5. Categorias de Objetos
object_types:
  - tables
  - views
  - mviews
  - procedures
  - functions
  - packages
  - triggers
  - synonyms

# 6. Configurações de IA (LLMs para Auto-Enriquecimento, Chat e Subagentes)
ai:
  default_provider: "ollama"      # ollama | local | openai | gemini | anthropic | deepseek | qwen | kimi | grok
  temperature: 0.2                # Temperatura padrão global (0.0 a 1.0)
  timeout: 300.0                  # Timeout padrão global em segundos
  max_history_turns: 15           # Janela de turnos mantidos na memória do chat
  max_agent_iterations: 10        # Limite máximo de ferramentas executadas por turno do agente
  max_subagent_iterations: 5      # Limite de iterações para subagentes especialistas
  providers:
    ollama:
      base_url: "http://localhost:11434/v1"
      model: "qwen2.5-coder:latest"
      temperature: 0.1
      timeout: 300.0
    local:
      base_url: "http://localhost:1234/v1" # Exemplo: LM Studio, vLLM, LocalAI
      model: "qwen2.5"
      temperature: 0.1
    openai:
      api_key: "${OPENAI_API_KEY}"
      model: "gpt-4o-mini"
      temperature: 0.2
      timeout: 120.0
    gemini:
      api_key: "${GEMINI_API_KEY}"
      model: "gemini-2.5-flash"
    anthropic:
      api_key: "${ANTHROPIC_API_KEY}"
      model: "claude-3-5-sonnet-20241022"

# 7. Sincronização com Git / GitLab / GitHub (GitOps)
git:
  enabled: false                                 # Ativa comandos leai git e /git
  remote_url: "${GIT_REMOTE_URL}"                # URL do repositório remoto
  branch: "main"                                 # Branch de rastreamento
  author_name: "LEAI Bot"                        # Nome do autor nos commits
  author_email: "leai@empresa.com"               # E-mail do autor nos commits
  auto_sync: false                               # Push automático após extract/compile
  tracked_paths:
    - "annotations"
    - "docs"
    - "raw"
    - "leai.yml"

# 8. Armazenamento Distribuído / Object Storage (SeaweedFS / S3)
storage:
  seaweedfs:
    enabled: false                                 # Se true, usa S3 sem precisar da flag --seaweed
    endpoint_url: "http://localhost:8333"          # Gateway S3 do SeaweedFS ou MinIO
    bucket: "leai"                                 # Nome do bucket S3
    access_key: "${SEAWEEDFS_ACCESS_KEY}"
    secret_key: "${SEAWEEDFS_SECRET_KEY}"
    region_name: "us-east-1"
    raw_prefix: "raw"                              # Prefixo dos snapshots JSON
    annotations_prefix: "annotations"              # Prefixo das anotações YAML
    auto_create_bucket: true                       # Cria o bucket caso não exista
    no_cache: false                                # Se true, opera em modo 100% remoto
    incremental: true                              # Deduplicação SHA-256

# 9. Idioma da Interface & Localização
language: "pt-BR"                                  # "en-US" (padrão canônico) ou "pt-BR"

# 10. Checagem Automática de Atualizações
update_check: true                                 # true (padrão) ou false
```

---

## 🔑 Formatos Suportados de DSN

O LEAI suporta diversas formas de declarar a string de conexão:

### Sintaxe de URL (Padrão)
```yaml
dsn: "oracle://usuario:senha@host:1521/nome_servico"
```

### Sintaxe EZCONNECT (Oracle)
```yaml
dsn: "usuario/senha@host:1521/nome_servico"
```

### TNS / Descriptor Completo (para TCPS, Wallets ou Oracle Cloud / Autonomous DB)
```yaml
dsn: "usuario/senha@(DESCRIPTION=(ADDRESS=(PROTOCOL=TCPS)(HOST=db.exemplo.com)(PORT=1522))(CONNECT_DATA=(SERVICE_NAME=meu_servico)))"
```

---

## 🎯 Filtros de Objetos

Você pode usar os filtros `include` e `exclude` para focar estritamente nas tabelas de interesse do seu domínio:

* `%`: Corresponde a zero ou mais caracteres (ex: `TB_%` inclui todas as tabelas iniciadas por `TB_`).
* `_`: Corresponde a exatamente um caractere.

> [!TIP]
> Se a lista `include` estiver vazia, o LEAI processará **todos** os objetos do schema que correspondam aos `object_types`, exceto aqueles listados em `exclude`.

---

## 🌐 Internacionalização e Idioma (`language`)

O LEAI possui subsistema nativo de internacionalização (`leai/i18n`) com fallback canônico em inglês e catálogos bilíngues paritários:

```yaml
language: "pt-BR" # ou "en-US" (padrão)
```

### O que o idioma afeta:
1. **Terminal & CLI:** Mensagens informativas, tabelas formatadas, spinners de progresso e resumos de pipeline.
2. **Sessão TUI Interativa:** Respostas dos comandos de barra (`/git status`, `/help`, `/rule`, `/copy`, `/model`).
3. **Prompts e Respostas de IA:** Quando configurado em `pt-BR`, o system prompt instrui o modelo LLM a preencher descrições de colunas e regras de negócio em Português (mantendo termos técnicos SQL intactos). Em `en-US`, a geração ocorre integralmente em Inglês.
4. **Cabeçalhos de Documentação Markdown:** Os arquivos gerados em `docs/` utilizam seções no idioma configurado (`## Visão Geral`, `## Colunas`, `## Regras de Negócio` vs. `## Overview`, `## Columns`, `## Business Rules`).
5. **Web Studio:** Textos da interface web, modais, mensagens de loading e seletor dinâmico em tempo de execução via API REST (`/api/config`).

### Precedência de Resolução
O LEAI determina o idioma ativo seguindo a seguinte ordem de prioridade estrita:
1. **Flag CLI:** `--lang <locale>` ou `-L <locale>` (ex: `leai --lang pt-BR ask "quais são as tabelas de vendas?"`)
2. **Variável de Ambiente:** `LEAI_LANG` ou `LEAI_LANGUAGE` (ex: `export LEAI_LANG=pt-BR`)
3. **Arquivo de Configuração:** Chave `language:` no `leai.yml`
4. **Padrão Canônico:** `en-US`

### Inicialização Rápida com Idioma
Para gerar o arquivo `leai.yml` pré-configurado e documentado em Português:
```bash
leai init --lang pt-BR
```
Ou em Inglês:
```bash
leai init --lang en-US
```

---

## 🔄 Checagem Automática de Atualizações (`update_check`)

Por padrão, ao iniciar qualquer comando, o LEAI consulta o repositório PyPI em segundo plano de forma não bloqueante para verificar se existe uma versão mais recente disponível.

```yaml
update_check: true # true (padrão) ou false
```

### Como Desativar a Verificação:
1. **No arquivo `leai.yml`:** Defina `update_check: false`.
2. **Via Variável de Ambiente:** Exporte `LEAI_NO_UPDATE_CHECK=1` ou `LEAI_NO_UPDATE_CHECK=true`.
3. **Via Linha de Comando (Flag Global):** Utilize `--no-update-check` em qualquer comando:
   ```bash
   leai --no-update-check extract
   leai --no-update-check chat
   ```

