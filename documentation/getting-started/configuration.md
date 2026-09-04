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
  default_provider: "openai"      # openai | gemini | anthropic | deepseek | qwen | kimi | grok | ollama
  temperature: 0.2
  providers:
    openai:
      api_key: "${OPENAI_API_KEY}"
      model: "gpt-4o-mini"
    gemini:
      api_key: "${GEMINI_API_KEY}"
      model: "gemini-2.0-flash"
    anthropic:
      api_key: "${ANTHROPIC_API_KEY}"
      model: "claude-3-5-sonnet-20241022"
    ollama:
      base_url: "http://localhost:11434/v1"
      model: "qwen2.5-coder:latest"

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
