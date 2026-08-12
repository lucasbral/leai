from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class LeaiConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    dsn: str
    schema_name: str = Field(alias="schema")
    docPath: Path = Field(default=Path("./docs"))
    include: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)
    docs: dict[str, dict[str, str]] = Field(default_factory=dict)


class ConfigError(ValueError):
    pass


def load_config(config_path: Path) -> LeaiConfig:
    if not config_path.exists():
        raise ConfigError(f"Config file not found: {config_path}")

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ConfigError("Invalid config format: expected a YAML mapping")

    try:
        config = LeaiConfig.model_validate(raw)
    except Exception as exc:  # pydantic provides detailed message
        raise ConfigError(f"Invalid config file: {exc}") from exc

    config.docPath = (config_path.parent / config.docPath).resolve()
    config.schema_name = config.schema_name.upper()
    config.include = [item.upper() for item in config.include]
    return config
