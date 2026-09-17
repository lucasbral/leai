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
updates_log_path: "./logs/updates" # Incremental update audit logs and manifests (latest.json, latest.md)
generate_update_log: true         # Whether to generate update audit logs in leai update

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
updates_log_path: "./logs/updates" # Logs e manifestos de atualização incremental (latest.json, latest.md)
generate_update_log: true         # Gera auditoria detalhada de objetos alterados no leai update

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


def deep_merge_missing_fields(target: dict, defaults: dict, prefix: str = "") -> list[str]:
    """Recursively adds missing keys from defaults into target without modifying any existing values.

    Returns the list of added key paths.
    """
    added = []
    for k, v in defaults.items():
        key_path = f"{prefix}.{k}" if prefix else str(k)
        if k not in target:
            if isinstance(v, dict):
                import copy

                target[k] = copy.deepcopy(v)
            elif isinstance(v, list):
                target[k] = list(v)
            else:
                target[k] = v
            added.append(key_path)
        elif isinstance(target[k], dict) and isinstance(v, dict):
            added.extend(deep_merge_missing_fields(target[k], v, prefix=key_path))
    return added


def _format_yaml_value(val: object) -> str:
    """Formats a scalar Python value for YAML output."""
    if val is None:
        return "null"
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (int, float)):
        return str(val)
    s = str(val)
    if "\n" in s:
        import yaml

        return yaml.dump(s).strip()
    return f'"{s}"'


def render_canonical_config(data: dict, lang: str = "pt-BR") -> str:
    """Renders a fully-commented, canonical leai.yml with populated values from data."""
    import yaml

    from leai.i18n import normalize_locale

    is_pt = normalize_locale(lang) == "pt-BR"

    # Normalize schemas
    schemas_val = data.get("schemas")
    if schemas_val is None and "schema" in data:
        schemas_val = [data["schema"]]
    if schemas_val is None:
        schemas_val = ["HR"]

    # Normalize AI providers
    ai_data = data.get("ai") or {}
    providers = ai_data.get("providers") or {}

    lines: list[str] = []

    if is_pt:
        lines.extend(
            [
                "# ==============================================================================",
                "# Arquivo de Configuração - LEAI (Oracle Database Documentation & Copilot)",
                "# ==============================================================================",
                "",
                "# ------------------------------------------------------------------------------",
                "# 1. CONEXÃO COM O BANCO DE DADOS ORACLE (DSN)",
                "# ------------------------------------------------------------------------------",
                "# Aceita a sintaxe URL oracle:// ou a string de conexão nativa do cx_Oracle/oracledb.",
                "# Suporta variáveis de ambiente no formato ${NOME_DA_VARIAVEL} ou ${VAR:-default}.",
                f"dsn: {_format_yaml_value(data.get('dsn', 'oracle://${DB_USER}:${DB_PASS}@${DB_HOST}:1521/${DB_SERVICE}'))}",
                "",
                "# ------------------------------------------------------------------------------",
                "# 2. DEFINIÇÃO DOS SCHEMAS A EXTRAIR E DOCUMENTAR",
                "# ------------------------------------------------------------------------------",
            ]
        )
    else:
        lines.extend(
            [
                "# ==============================================================================",
                "# Configuration File - LEAI (Oracle Database Documentation & AI Copilot)",
                "# ==============================================================================",
                "",
                "# ------------------------------------------------------------------------------",
                "# 1. ORACLE DATABASE CONNECTION (DSN)",
                "# ------------------------------------------------------------------------------",
                "# Supports oracle:// URL syntax or native cx_Oracle/oracledb connection string.",
                "# Supports environment variables in ${VARIABLE_NAME} or ${VAR:-default} format.",
                f"dsn: {_format_yaml_value(data.get('dsn', 'oracle://${DB_USER}:${DB_PASS}@${DB_HOST}:1521/${DB_SERVICE}'))}",
                "",
                "# ------------------------------------------------------------------------------",
                "# 2. TARGET SCHEMAS TO EXTRACT AND DOCUMENT",
                "# ------------------------------------------------------------------------------",
            ]
        )

    if isinstance(schemas_val, str):
        lines.append(f"schemas: {_format_yaml_value(schemas_val)}")
    elif isinstance(schemas_val, list) and schemas_val:
        lines.append("schemas:")
        for s in schemas_val:
            lines.append(f"  - {s}")
    else:
        lines.append("schemas:\n  - HR")

    if is_pt:
        lines.extend(
            [
                "",
                "# ------------------------------------------------------------------------------",
                "# 3. DIRETORES DO PIPELINE",
                "# ------------------------------------------------------------------------------",
                f"rawPath: {_format_yaml_value(data.get('rawPath', './raw'))}",
                f"annotationsPath: {_format_yaml_value(data.get('annotationsPath', './annotations'))}",
                f"docPath: {_format_yaml_value(data.get('docPath', './docs'))}",
                f"updates_log_path: {_format_yaml_value(data.get('updates_log_path', './logs/updates'))}",
                f"generate_update_log: {'true' if data.get('generate_update_log', True) else 'false'}",
                "",
                "# ------------------------------------------------------------------------------",
                "# 4. FILTROS DE OBJETOS (Inclusão e Exclusão)",
                "# ------------------------------------------------------------------------------",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "# ------------------------------------------------------------------------------",
                "# 3. PIPELINE DIRECTORIES",
                "# ------------------------------------------------------------------------------",
                f"rawPath: {_format_yaml_value(data.get('rawPath', './raw'))}",
                f"annotationsPath: {_format_yaml_value(data.get('annotationsPath', './annotations'))}",
                f"docPath: {_format_yaml_value(data.get('docPath', './docs'))}",
                f"updates_log_path: {_format_yaml_value(data.get('updates_log_path', './logs/updates'))}",
                f"generate_update_log: {'true' if data.get('generate_update_log', True) else 'false'}",
                "",
                "# ------------------------------------------------------------------------------",
                "# 4. OBJECT FILTERS (Include and Exclude)",
                "# ------------------------------------------------------------------------------",
            ]
        )

    include_list = data.get("include")
    if include_list:
        lines.append("include:")
        for inc in include_list:
            lines.append(f"  - {inc}")
    else:
        lines.append("include: []")

    exclude_list = data.get("exclude")
    if exclude_list:
        lines.append("exclude:")
        for exc in exclude_list:
            lines.append(f"  - {exc}")
    else:
        lines.append("exclude: []")

    if is_pt:
        lines.extend(
            [
                "",
                "# ------------------------------------------------------------------------------",
                "# 5. TIPOS DE OBJETOS A SEREM PROCESSADOS",
                "# ------------------------------------------------------------------------------",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "# ------------------------------------------------------------------------------",
                "# 5. OBJECT TYPES TO PROCESS",
                "# ------------------------------------------------------------------------------",
            ]
        )

    object_types = data.get("object_types") or [
        "tables",
        "views",
        "mviews",
        "procedures",
        "functions",
        "packages",
        "types",
        "triggers",
        "sequences",
        "indexes",
        "synonyms",
    ]
    lines.append("object_types:")
    for ot in object_types:
        lines.append(f"  - {ot}")

    if is_pt:
        lines.extend(
            [
                "",
                "# ------------------------------------------------------------------------------",
                "# 6. CONFIGURAÇÃO DE IA (LLMs para Auto-Enriquecimento e Assistente)",
                "# ------------------------------------------------------------------------------",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "# ------------------------------------------------------------------------------",
                "# 6. AI CONFIGURATION (LLMs for Auto-Enrichment and Chat Copilot)",
                "# ------------------------------------------------------------------------------",
            ]
        )

    lines.extend(
        [
            "ai:",
            f"  default_provider: {_format_yaml_value(ai_data.get('default_provider', 'ollama'))}",
            f"  temperature: {ai_data.get('temperature', 0.2)}",
            f"  timeout: {ai_data.get('timeout', 300.0)}",
            f"  max_history_turns: {ai_data.get('max_history_turns', 15)}",
            f"  max_agent_iterations: {ai_data.get('max_agent_iterations', 10)}",
            f"  max_subagent_iterations: {ai_data.get('max_subagent_iterations', 5)}",
        ]
    )

    if "num_ctx" in ai_data and ai_data["num_ctx"] is not None:
        lines.append(f"  num_ctx: {ai_data['num_ctx']}")
    if "keep_alive" in ai_data and ai_data["keep_alive"] is not None:
        lines.append(f"  keep_alive: {_format_yaml_value(ai_data['keep_alive'])}")

    lines.append("  providers:")

    # Render providers
    default_provider_keys = [
        "ollama",
        "local",
        "openai",
        "gemini",
        "anthropic",
        "deepseek",
        "qwen",
        "kimi",
        "grok",
    ]
    all_provider_keys = list(default_provider_keys)
    for p_key in providers.keys():
        if p_key not in all_provider_keys:
            all_provider_keys.append(p_key)

    for p_key in all_provider_keys:
        p_info = providers.get(p_key) or {}
        if not p_info and p_key not in providers:
            continue
        lines.append(f"    {p_key}:")
        for sub_k, sub_v in p_info.items():
            if isinstance(sub_v, dict):
                lines.append(f"      {sub_k}:")
                for inner_k, inner_v in sub_v.items():
                    lines.append(f"        {inner_k}: {_format_yaml_value(inner_v)}")
            elif isinstance(sub_v, list):
                lines.append(f"      {sub_k}:")
                for inner_item in sub_v:
                    lines.append(f"        - {_format_yaml_value(inner_item)}")
            else:
                lines.append(f"      {sub_k}: {_format_yaml_value(sub_v)}")

    # Section 7: Git
    git_data = data.get("git") or {}
    if is_pt:
        lines.extend(
            [
                "",
                "# ------------------------------------------------------------------------------",
                "# 7. SINCRONIZAÇÃO COM GIT / GITLAB",
                "# ------------------------------------------------------------------------------",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "# ------------------------------------------------------------------------------",
                "# 7. GIT SYNCHRONIZATION",
                "# ------------------------------------------------------------------------------",
            ]
        )

    lines.extend(
        [
            "git:",
            f"  enabled: {'true' if git_data.get('enabled', False) else 'false'}",
            f"  remote_url: {_format_yaml_value(git_data.get('remote_url', git_data.get('remote', '${GIT_REMOTE_URL}')))}",
            f"  branch: {_format_yaml_value(git_data.get('branch', 'main'))}",
            f"  author_name: {_format_yaml_value(git_data.get('author_name', 'LEAI Bot'))}",
            f"  author_email: {_format_yaml_value(git_data.get('author_email', 'leai@local'))}",
            f"  auto_sync: {'true' if git_data.get('auto_sync', False) else 'false'}",
        ]
    )
    tracked = git_data.get("tracked_paths") or ["annotations", "docs", "raw", "leai.yml"]
    lines.append("  tracked_paths:")
    for tp in tracked:
        lines.append(f"    - {_format_yaml_value(tp)}")

    # Section 8: Storage
    storage_data = data.get("storage") or {}
    seaweed_data = storage_data.get("seaweedfs") or {}
    if is_pt:
        lines.extend(
            [
                "",
                "# ------------------------------------------------------------------------------",
                "# 8. ARMAZENAMENTO DISTRIBUÍDO / OBJECT STORAGE (SeaweedFS S3)",
                "# ------------------------------------------------------------------------------",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "# ------------------------------------------------------------------------------",
                "# 8. DISTRIBUTED STORAGE / OBJECT STORAGE (SeaweedFS S3)",
                "# ------------------------------------------------------------------------------",
            ]
        )

    lines.extend(
        [
            "storage:",
            "  seaweedfs:",
            f"    enabled: {'true' if seaweed_data.get('enabled', False) else 'false'}",
            f"    endpoint_url: {_format_yaml_value(seaweed_data.get('endpoint_url', '${SEAWEEDFS_ENDPOINT:-http://localhost:8333}'))}",
            f"    bucket: {_format_yaml_value(seaweed_data.get('bucket', 'leai'))}",
            f"    access_key: {_format_yaml_value(seaweed_data.get('access_key', '${SEAWEEDFS_ACCESS_KEY}'))}",
            f"    secret_key: {_format_yaml_value(seaweed_data.get('secret_key', '${SEAWEEDFS_SECRET_KEY}'))}",
            f"    region_name: {_format_yaml_value(seaweed_data.get('region_name', 'us-east-1'))}",
            f"    raw_prefix: {_format_yaml_value(seaweed_data.get('raw_prefix', 'raw'))}",
            f"    annotations_prefix: {_format_yaml_value(seaweed_data.get('annotations_prefix', 'annotations'))}",
            f"    auto_create_bucket: {'true' if seaweed_data.get('auto_create_bucket', True) else 'false'}",
            f"    no_cache: {'true' if seaweed_data.get('no_cache', False) else 'false'}",
            f"    incremental: {'true' if seaweed_data.get('incremental', True) else 'false'}",
        ]
    )

    # Section 9: Language
    lang_val = data.get("language", "pt-BR" if is_pt else "en-US")
    if is_pt:
        lines.extend(
            [
                "",
                "# ------------------------------------------------------------------------------",
                "# 9. IDIOMA DA INTERFACE & LOCALIZAÇÃO",
                "# ------------------------------------------------------------------------------",
                f"language: {_format_yaml_value(lang_val)}",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "# ------------------------------------------------------------------------------",
                "# 9. INTERFACE LANGUAGE & LOCALIZATION",
                "# ------------------------------------------------------------------------------",
                f"language: {_format_yaml_value(lang_val)}",
            ]
        )

    # Custom / extra top-level keys
    handled_keys = {
        "dsn",
        "schemas",
        "schema",
        "rawPath",
        "annotationsPath",
        "docPath",
        "updates_log_path",
        "generate_update_log",
        "include",
        "exclude",
        "object_types",
        "ai",
        "git",
        "storage",
        "language",
        "update_check",
    }
    extra_keys = {k: v for k, v in data.items() if k not in handled_keys}
    if extra_keys:
        lines.extend(
            [
                "",
                "# ------------------------------------------------------------------------------",
                "# CONFIGURAÇÕES CUSTOMIZADAS DO USUÁRIO" if is_pt else "# CUSTOM USER CONFIGURATION",
                "# ------------------------------------------------------------------------------",
            ]
        )
        lines.append(yaml.dump(extra_keys, allow_unicode=True, default_flow_style=False).strip())

    lines.append("")
    return "\n".join(lines)


def update_existing_config(
    target_path: Path,
    lang: str | None = None,
    backup: bool = True,
) -> tuple[bool, list[str]]:
    """Updates an existing leai.yml configuration layout with missing fields without changing existing values.

    Args:
        target_path: Path to existing configuration file.
        lang: Language preference ('pt-BR' or 'en-US'). If omitted, infers from existing file.
        backup: If True, creates a '.yml.bak' backup before updating.

    Returns:
        tuple[bool, list[str]]: (was_modified, list_of_added_key_paths)
    """
    import yaml

    if not target_path.exists():
        written = write_default_config(target_path, overwrite=False, lang=lang)
        return (written, ["* (new file created)"])

    raw_text = target_path.read_text(encoding="utf-8")
    try:
        existing_data = yaml.safe_load(raw_text) or {}
    except Exception:
        existing_data = {}

    if not isinstance(existing_data, dict):
        existing_data = {}

    detected_lang = lang or existing_data.get("language") or "pt-BR"
    canonical_defaults_yaml = get_default_config_template(lang=detected_lang)
    default_data = yaml.safe_load(canonical_defaults_yaml) or {}

    added_keys = deep_merge_missing_fields(existing_data, default_data)

    # Render updated canonical content
    new_content = render_canonical_config(existing_data, lang=detected_lang)

    # If content changed or fields were added
    if new_content.strip() != raw_text.strip() or added_keys:
        if backup and target_path.exists():
            bak_path = target_path.with_suffix(".yml.bak")
            try:
                bak_path.write_text(raw_text, encoding="utf-8")
            except Exception:
                pass
        target_path.write_text(new_content, encoding="utf-8")
        return (True, added_keys)

    return (False, [])
