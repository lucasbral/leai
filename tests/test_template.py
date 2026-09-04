from pathlib import Path

from leai.config import expand_env_vars, load_config
from leai.template import get_default_config_template, write_default_config


def test_expand_env_vars(monkeypatch):
    monkeypatch.delenv("NON_EXISTENT_VAR", raising=False)
    monkeypatch.setenv("EXISTING_VAR", "my_custom_value")

    assert expand_env_vars("${NON_EXISTENT_VAR:-http://localhost:8333}") == "http://localhost:8333"
    assert expand_env_vars("${EXISTING_VAR:-http://localhost:8333}") == "my_custom_value"
    assert expand_env_vars("${EXISTING_VAR}") == "my_custom_value"
    assert expand_env_vars("prefix_${NON_EXISTENT_VAR:-default}_suffix") == "prefix_default_suffix"


def test_get_default_config_template():
    tpl = get_default_config_template()
    assert len(tpl) > 500
    assert "dsn:" in tpl
    assert "schemas:" in tpl
    assert 'default_provider: "ollama"' in tpl or "default_provider: 'ollama'" in tpl or "default_provider: ollama" in tpl
    assert "git:" in tpl
    assert "storage:" in tpl
    assert "seaweedfs:" in tpl
    assert "${SEAWEEDFS_ENDPOINT:-http://localhost:8333}" in tpl


def test_write_default_config(tmp_path: Path):
    target = tmp_path / "subdir" / "leai.yml"
    assert not target.exists()

    # First write creates the file
    res = write_default_config(target, overwrite=False)
    assert res is True
    assert target.exists()
    content = target.read_text(encoding="utf-8")
    assert len(content) > 500
    assert "dsn:" in content

    # Second write without overwrite fails and preserves file
    res2 = write_default_config(target, overwrite=False)
    assert res2 is False

    # Write with overwrite succeeds
    res3 = write_default_config(target, overwrite=True)
    assert res3 is True


def test_load_generated_config(tmp_path: Path, monkeypatch):
    target = tmp_path / "leai.yml"
    write_default_config(target)

    # Clean env to test fallback defaults
    monkeypatch.delenv("SEAWEEDFS_ENDPOINT", raising=False)
    monkeypatch.delenv("LEAI_SEAWEED_ENDPOINT", raising=False)
    monkeypatch.delenv("LEAI_DSN", raising=False)

    cfg = load_config(target)
    assert cfg.schema_name == "HR"
    assert cfg.ai.default_provider == "ollama"
    assert "tables" in cfg.object_types
    assert "types" in cfg.object_types
    assert cfg.git.enabled is False
    assert cfg.storage.seaweedfs.enabled is False
    assert cfg.storage.seaweedfs.endpoint_url == "http://localhost:8333"


def test_load_generated_config_with_env_override(tmp_path: Path, monkeypatch):
    target = tmp_path / "leai.yml"
    write_default_config(target)

    monkeypatch.setenv("SEAWEEDFS_ENDPOINT", "http://seaweed.corp.internal:8333")

    cfg = load_config(target)
    assert cfg.storage.seaweedfs.endpoint_url == "http://seaweed.corp.internal:8333"
