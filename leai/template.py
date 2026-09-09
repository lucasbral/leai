"""Canonical default configuration templates for LEAI (English and Portuguese)."""

from pathlib import Path

DEFAULT_LEAI_CONFIG_TEMPLATE_EN = """# ==============================================================================
# Configuration File - LEAI (Oracle Database Documentation & AI Copilot)
# ==============================================================================

# ------------------------------------------------------------------------------
# 1. ORACLE DATABASE CONNECTION (DSN)
# ------------------------------------------------------------------------------
# Supports oracle:// URL syntax or native cx_Oracle/oracledb connection string.
# Supports environment variables in ${VARIABLE_NAME} or ${VAR:-default} format.
dsn: "oracle://${DB_USER}:${DB_PASS}@${DB_HOST}:1521/${DB_SERVICE}"

# Static example:
# dsn: "oracle://my_user:my_password@localhost:1521/ORCLPDB1"

# ------------------------------------------------------------------------------
# 2. TARGET SCHEMAS TO EXTRACT AND DOCUMENT
# ------------------------------------------------------------------------------
# Option A: Single schema
schemas:
  - HR

# Option B: Multiple specific schemas
# schemas:
#   - HR
#   - SALES
#   - FINANCE

# Option C: ALL database schemas (ignoring internal Oracle/SYS schemas)
# Requires SELECT ANY DICTIONARY privilege or DBA role.
# schemas: "ALL"

# ------------------------------------------------------------------------------
# 3. PIPELINE DIRECTORIES
# ------------------------------------------------------------------------------
rawPath: "./raw"                  # Technical snapshot in JSON format
annotationsPath: "./annotations"  # Business annotations layer in YAML
docPath: "./docs"                  # Final compiled Markdown documentation for RAG

# ------------------------------------------------------------------------------
# 4. OBJECT FILTERS (Include and Exclude)
# ------------------------------------------------------------------------------
# Supports Oracle LIKE wildcards (e.g. SALES_%, BIN$%)
include:
  - EMPLOYEES
  - SALES_%

exclude:
  - BIN$%
  - SYS_%

# ------------------------------------------------------------------------------
# 5. OBJECT TYPES TO PROCESS
# ------------------------------------------------------------------------------
# Uncomment only categories you wish to extract:
object_types:
  - tables
  - views
  - mviews
  - procedures
  - functions
  - packages
  - types
  - triggers
  - sequences
  - indexes
  - synonyms

# ------------------------------------------------------------------------------
# 6. AI CONFIGURATION (LLMs for Auto-Enrichment and Chat Copilot)
# ------------------------------------------------------------------------------
ai:
  default_provider: "ollama" # "ollama", "local", "openai", "gemini", "anthropic", "deepseek", "qwen", "kimi", "grok"
  temperature: 0.2
  timeout: 300.0
  max_history_turns: 15
  max_agent_iterations: 10
  max_subagent_iterations: 5
  providers:
    ollama:
      base_url: "http://localhost:11434/v1"
      model: "qwen2.5-coder:latest"
    local:
      base_url: "http://localhost:1234/v1"
      model: "qwen2.5"
    openai:
      api_key: "${OPENAI_API_KEY}"
      model: "gpt-4o-mini"
    gemini:
      api_key: "${GEMINI_API_KEY}"
      model: "gemini-1.5-flash"
    anthropic:
      api_key: "${ANTHROPIC_API_KEY}"
      model: "claude-3-5-sonnet-20241022"
    deepseek:
      api_key: "${DEEPSEEK_API_KEY}"
      base_url: "https://api.deepseek.com/v1"
      model: "deepseek-chat"
    qwen:
      api_key: "${DASHSCOPE_API_KEY}"
      base_url: "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
      model: "qwen-plus"
    kimi:
      api_key: "${MOONSHOT_API_KEY}"
      base_url: "https://api.moonshot.cn/v1"
      model: "moonshot-v1-8k"
    grok:
      api_key: "${GROK_API_KEY}"
      base_url: "https://api.x.ai/v1"
      model: "grok-2-latest"

# ------------------------------------------------------------------------------
# 7. GIT SYNCHRONIZATION
# ------------------------------------------------------------------------------
git:
  enabled: false                                 # Enables /git commands and 'leai git'
  remote_url: "${GIT_REMOTE_URL}"                # Remote repository URL (GitLab, GitHub, etc.)
  branch: "main"                                 # Tracking branch
  author_name: "LEAI Bot"                        # Commit author name
  author_email: "leai@local"                     # Commit author email
  auto_sync: false                               # Auto-sync after extraction/compilation
  tracked_paths:
    - "annotations"
    - "docs"
    - "raw"
    - "leai.yml"

# ------------------------------------------------------------------------------
# 8. DISTRIBUTED STORAGE / OBJECT STORAGE (SeaweedFS S3)
# ------------------------------------------------------------------------------
storage:
  seaweedfs:
    enabled: false                                 # If true, commands operate with SeaweedFS by default
    endpoint_url: "${SEAWEEDFS_ENDPOINT:-http://localhost:8333}"
    bucket: "leai"
    access_key: "${SEAWEEDFS_ACCESS_KEY}"
    secret_key: "${SEAWEEDFS_SECRET_KEY}"
    region_name: "us-east-1"
    raw_prefix: "raw"
    annotations_prefix: "annotations"
    auto_create_bucket: true

# ------------------------------------------------------------------------------
# 9. INTERFACE LANGUAGE & LOCALIZATION
# ------------------------------------------------------------------------------
# Interface language for CLI, TUI, and documentation prompts: "en-US" or "pt-BR"
language: "en-US"
"""

DEFAULT_LEAI_CONFIG_TEMPLATE_PT = """# ==============================================================================
# Arquivo de Configuração - LEAI (Oracle Database Documentation & Copilot)
# ==============================================================================

# ------------------------------------------------------------------------------
# 1. CONEXÃO COM O BANCO DE DADOS ORACLE (DSN)
# ------------------------------------------------------------------------------
# Aceita a sintaxe URL oracle:// ou a string de conexão nativa do cx_Oracle/oracledb.
# Suporta variáveis de ambiente no formato ${NOME_DA_VARIAVEL} ou ${VAR:-default}.
dsn: "oracle://${DB_USER}:${DB_PASS}@${DB_HOST}:1521/${DB_SERVICE}"

# Exemplo estático:
# dsn: "oracle://meu_usuario:minha_senha@localhost:1521/ORCLPDB1"

# ------------------------------------------------------------------------------
# 2. DEFINIÇÃO DOS SCHEMAS A EXTRAIR E DOCUMENTAR
# ------------------------------------------------------------------------------
# Opção A: Schema único (Modo tradicional)
schemas:
  - HR

# Opção B: Lista de múltiplos schemas específicos
# schemas:
#   - HR
#   - SALES
#   - FINANCEIRO

# Opção C: TODOS os schemas do banco (Ignora schemas internos do Oracle/SYS)
# Requer usuário com privilégio SELECT ANY DICTIONARY ou role DBA.
# schemas: "ALL"

# ------------------------------------------------------------------------------
# 3. DIRETORES DO PIPELINE
# ------------------------------------------------------------------------------
rawPath: "./raw"                  # Snapshot técnico puro em formato JSON
annotationsPath: "./annotations"  # Camada editável de anotações de negócio em YAML
docPath: "./docs"                  # Documentação final compilada em Markdown para RAG

# ------------------------------------------------------------------------------
# 4. FILTROS DE OBJETOS (Inclusão e Exclusão)
# ------------------------------------------------------------------------------
# Suporta caracteres curinga do padrão LIKE do Oracle (ex: VENDAS_%, BIN$%)
include:
  - FUNCIONARIOS
  - VENDAS_%

exclude:
  - BIN$%
  - SYS_%

# ------------------------------------------------------------------------------
# 5. TIPOS DE OBJETOS A SEREM PROCESSADOS
# ------------------------------------------------------------------------------
# Descomente apenas as categorias de objetos que deseja incluir na extração:
object_types:
  - tables
  - views
  - mviews
  - procedures
  - functions
  - packages
  - types
  - triggers
  - sequences
  - indexes
  - synonyms

# ------------------------------------------------------------------------------
# 6. CONFIGURAÇÃO DE IA (LLMs para Auto-Enriquecimento e Assistente)
# ------------------------------------------------------------------------------
ai:
  default_provider: "ollama" # "ollama", "local", "openai", "gemini", "anthropic", "deepseek", "qwen", "kimi", "grok"
  temperature: 0.2
  timeout: 300.0
  max_history_turns: 15
  max_agent_iterations: 10
  max_subagent_iterations: 5
  providers:
    ollama:
      base_url: "http://localhost:11434/v1"
      model: "qwen2.5-coder:latest"
    local:
      base_url: "http://localhost:1234/v1"
      model: "qwen2.5"
    openai:
      api_key: "${OPENAI_API_KEY}"
      model: "gpt-4o-mini"
    gemini:
      api_key: "${GEMINI_API_KEY}"
      model: "gemini-1.5-flash"
    anthropic:
      api_key: "${ANTHROPIC_API_KEY}"
      model: "claude-3-5-sonnet-20241022"
    deepseek:
      api_key: "${DEEPSEEK_API_KEY}"
      base_url: "https://api.deepseek.com/v1"
      model: "deepseek-chat"
    qwen:
      api_key: "${DASHSCOPE_API_KEY}"
      base_url: "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
      model: "qwen-plus"
    kimi:
      api_key: "${MOONSHOT_API_KEY}"
      base_url: "https://api.moonshot.cn/v1"
      model: "moonshot-v1-8k"
    grok:
      api_key: "${GROK_API_KEY}"
      base_url: "https://api.x.ai/v1"
      model: "grok-2-latest"

# ------------------------------------------------------------------------------
# 7. SINCRONIZAÇÃO COM GIT / GITLAB
# ------------------------------------------------------------------------------
git:
  enabled: false                                 # Ativa comandos /git e leai git
  remote_url: "${GIT_REMOTE_URL}"                # URL do repositório remoto (GitLab, GitHub, etc.)
  branch: "main"                                 # Branch de rastreamento
  author_name: "LEAI Bot"                        # Nome do autor para commits automáticos
  author_email: "leai@local"                     # E-mail do autor para commits automáticos
  auto_sync: false                               # Sincronização automática após extração/compilação
  tracked_paths:
    - "annotations"
    - "docs"
    - "raw"
    - "leai.yml"

# ------------------------------------------------------------------------------
# 8. ARMAZENAMENTO DISTRIBUÍDO / OBJECT STORAGE (SeaweedFS S3)
# ------------------------------------------------------------------------------
storage:
  seaweedfs:
    enabled: false                                 # Se true, os comandos usam SeaweedFS por padrão
    endpoint_url: "${SEAWEEDFS_ENDPOINT:-http://localhost:8333}"
    bucket: "leai"
    access_key: "${SEAWEEDFS_ACCESS_KEY}"
    secret_key: "${SEAWEEDFS_SECRET_KEY}"
    region_name: "us-east-1"
    raw_prefix: "raw"
    annotations_prefix: "annotations"
    auto_create_bucket: true

# ------------------------------------------------------------------------------
# 9. IDIOMA DA INTERFACE & LOCALIZAÇÃO
# ------------------------------------------------------------------------------
# Idioma da interface para CLI, TUI e prompts: "en-US" ou "pt-BR"
language: "pt-BR"
"""

DEFAULT_LEAI_CONFIG_TEMPLATE = DEFAULT_LEAI_CONFIG_TEMPLATE_EN


def get_default_config_template(lang: str | None = None) -> str:
    """Returns the canonical configuration template for the specified language."""
    from leai.i18n import normalize_locale

    loc = normalize_locale(lang)
    if loc == "pt-BR":
        return DEFAULT_LEAI_CONFIG_TEMPLATE_PT
    return DEFAULT_LEAI_CONFIG_TEMPLATE_EN


def write_default_config(target_path: Path, overwrite: bool = False, lang: str | None = None) -> bool:
    """Writes the canonical default config to target_path for the specified language.

    Returns True if written, False if target exists and overwrite is False.
    """
    if target_path.exists() and not overwrite:
        return False

    content = get_default_config_template(lang=lang)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(content, encoding="utf-8")
    return True
