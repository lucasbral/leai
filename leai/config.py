import os
import re
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

DEFAULT_OBJECT_TYPES = [
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


class AIProviderConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    timeout: float | None = None


class AIConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    default_provider: str = "openai"
    temperature: float = 0.2
    timeout: float = 300.0
    providers: dict[str, AIProviderConfig] = Field(default_factory=dict)


class GitConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    enabled: bool = True
    auto_pull_on_start: bool = False
    remote: str = "origin"
    branch: str = "main"
    tracked_paths: list[str] = Field(default_factory=lambda: ["annotations", "docs", "raw", "leai.yml"])


class SeaweedFSConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    enabled: bool = False
    endpoint_url: str = ""
    bucket: str = "leai"
    access_key: str | None = None
    secret_key: str | None = None
    region_name: str = "us-east-1"
    raw_prefix: str = "raw"
    annotations_prefix: str = "annotations"
    auto_create_bucket: bool = True
    no_cache: bool = False
    incremental: bool = True


class StorageConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    seaweedfs: SeaweedFSConfig = Field(default_factory=SeaweedFSConfig)


class LeaiConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    dsn: str = ""
    schemas: list[str] = Field(default_factory=list)
    rawPath: Path = Field(default=Path("./raw"))
    annotationsPath: Path = Field(default=Path("./annotations"))
    docPath: Path = Field(default=Path("./docs"))
    include: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)
    object_types: list[str] = Field(default_factory=lambda: list(DEFAULT_OBJECT_TYPES))
    docs: dict[str, dict[str, str]] = Field(default_factory=dict)
    ai: AIConfig = Field(default_factory=AIConfig)
    git: GitConfig = Field(default_factory=GitConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)

    @property
    def schema_name(self) -> str:
        return self.schemas[0] if self.schemas else ""

    @property
    def is_all_schemas(self) -> bool:
        return any(s.upper() == "ALL" for s in self.schemas)


class ConfigError(ValueError):
    pass


def expand_env_vars(text: str) -> str:
    """Expands environment variables with support for ${VAR:-default} and standard $VAR / ${VAR}."""

    def _replace_default(match: re.Match) -> str:
        var_name = match.group(1)
        default_val = match.group(2) if match.group(2) is not None else ""
        return os.environ.get(var_name, default_val)

    pattern = re.compile(r"\$\{([A-Za-z0-9_]+):-([^}]*)\}")
    text = pattern.sub(_replace_default, text)
    return os.path.expandvars(text)


def load_config(config_path: Path) -> LeaiConfig:
    if not config_path.exists():
        raise ConfigError(f"Config file not found: {config_path}")

    raw_text = config_path.read_text(encoding="utf-8")
    expanded_text = expand_env_vars(raw_text)
    raw = yaml.safe_load(expanded_text)
    if not isinstance(raw, dict):
        raise ConfigError("Invalid config format: expected a YAML mapping")

    if os.environ.get("LEAI_DSN"):
        raw["dsn"] = os.environ["LEAI_DSN"]

    if os.environ.get("LEAI_AI_TIMEOUT"):
        try:
            if "ai" not in raw or not isinstance(raw["ai"], dict):
                raw["ai"] = {}
            raw["ai"]["timeout"] = float(os.environ["LEAI_AI_TIMEOUT"])
        except ValueError:
            pass

    raw_schemas = raw.get("schemas") or raw.get("schema")
    if not raw_schemas:
        raise ConfigError("Must define 'schema' or 'schemas' in leai.yml")

    parsed_schemas: list[str] = []

    if isinstance(raw_schemas, str):
        parsed_schemas = [raw_schemas.strip().upper()]
    elif isinstance(raw_schemas, list):
        for s in raw_schemas:
            parsed_schemas.append(str(s).strip().upper())

    raw["schemas"] = parsed_schemas

    # Environment variables overrides for SeaweedFS
    storage_dict = raw.setdefault("storage", {})
    if isinstance(storage_dict, dict):
        sw_dict = storage_dict.setdefault("seaweedfs", {})
        if isinstance(sw_dict, dict):
            if os.environ.get("LEAI_SEAWEED_ENABLED"):
                sw_dict["enabled"] = os.environ["LEAI_SEAWEED_ENABLED"].strip().lower() in ("true", "1", "yes")
            if os.environ.get("LEAI_SEAWEED_ENDPOINT"):
                sw_dict["endpoint_url"] = os.environ["LEAI_SEAWEED_ENDPOINT"]
            if os.environ.get("LEAI_SEAWEED_BUCKET"):
                sw_dict["bucket"] = os.environ["LEAI_SEAWEED_BUCKET"]
            if os.environ.get("LEAI_SEAWEED_ACCESS_KEY"):
                sw_dict["access_key"] = os.environ["LEAI_SEAWEED_ACCESS_KEY"]
            if os.environ.get("LEAI_SEAWEED_SECRET_KEY"):
                sw_dict["secret_key"] = os.environ["LEAI_SEAWEED_SECRET_KEY"]
            if os.environ.get("LEAI_SEAWEED_NO_CACHE"):
                sw_dict["no_cache"] = os.environ["LEAI_SEAWEED_NO_CACHE"].strip().lower() in ("true", "1", "yes")
            if os.environ.get("LEAI_SEAWEED_INCREMENTAL"):
                sw_dict["incremental"] = os.environ["LEAI_SEAWEED_INCREMENTAL"].strip().lower() in ("true", "1", "yes")

    try:
        config = LeaiConfig.model_validate(raw)
    except Exception as exc:  # pydantic provides detailed message
        raise ConfigError(f"Invalid config file: {exc}") from exc

    config.rawPath = (config_path.parent / config.rawPath).resolve()
    config.docPath = (config_path.parent / config.docPath).resolve()
    config.annotationsPath = (config_path.parent / config.annotationsPath).resolve()
    config.include = [item.upper() for item in config.include]
    config.exclude = [item.upper() for item in config.exclude]
    config.object_types = [item.lower() for item in config.object_types]
    return config
