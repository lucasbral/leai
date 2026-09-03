import os
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


class AIConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    default_provider: str = "openai"
    temperature: float = 0.2
    providers: dict[str, AIProviderConfig] = Field(default_factory=dict)


class GitConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    enabled: bool = True
    auto_pull_on_start: bool = False
    remote: str = "origin"
    branch: str = "main"
    tracked_paths: list[str] = Field(default_factory=lambda: ["annotations", "docs", "raw", "leai.yml"])


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

    @property
    def schema_name(self) -> str:
        return self.schemas[0] if self.schemas else ""

    @property
    def is_all_schemas(self) -> bool:
        return any(s.upper() == "ALL" for s in self.schemas)


class ConfigError(ValueError):
    pass


def load_config(config_path: Path) -> LeaiConfig:
    if not config_path.exists():
        raise ConfigError(f"Config file not found: {config_path}")

    raw_text = config_path.read_text(encoding="utf-8")
    expanded_text = os.path.expandvars(raw_text)
    raw = yaml.safe_load(expanded_text)
    if not isinstance(raw, dict):
        raise ConfigError("Invalid config format: expected a YAML mapping")

    if os.environ.get("LEAI_DSN"):
        raw["dsn"] = os.environ["LEAI_DSN"]

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
