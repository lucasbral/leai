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


class LeaiConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    dsn: str
    schemas: list[str] = Field(default_factory=list)
    is_all_schemas: bool = False
    rawPath: Path = Field(default=Path("./raw"))
    annotationsPath: Path = Field(default=Path("./annotations"))
    docPath: Path = Field(default=Path("./docs"))
    include: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)
    object_types: list[str] = Field(default_factory=lambda: list(DEFAULT_OBJECT_TYPES))
    docs: dict[str, dict[str, str]] = Field(default_factory=dict)

    @property
    def schema_name(self) -> str:
        return self.schemas[0] if self.schemas else ""


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
        raise ConfigError("É necessário definir 'schema' ou 'schemas' no leai.yml")

    is_all = False
    parsed_schemas: list[str] = []

    if isinstance(raw_schemas, str):
        if raw_schemas.strip().upper() == "ALL":
            is_all = True
            parsed_schemas = ["ALL"]
        else:
            parsed_schemas = [raw_schemas.strip().upper()]
    elif isinstance(raw_schemas, list):
        for s in raw_schemas:
            item = str(s).strip().upper()
            if item == "ALL":
                is_all = True
            parsed_schemas.append(item)

    raw["schemas"] = parsed_schemas

    try:
        config = LeaiConfig.model_validate(raw)
        config.is_all_schemas = is_all
    except Exception as exc:  # pydantic provides detailed message
        raise ConfigError(f"Invalid config file: {exc}") from exc

    config.rawPath = (config_path.parent / config.rawPath).resolve()
    config.docPath = (config_path.parent / config.docPath).resolve()
    config.annotationsPath = (config_path.parent / config.annotationsPath).resolve()
    config.include = [item.upper() for item in config.include]
    config.object_types = [item.lower() for item in config.object_types]
    return config
