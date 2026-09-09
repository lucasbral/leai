"""Unit tests for LEAI internationalization (i18n) subsystem."""

from pathlib import Path

from typer.testing import CliRunner

from leai.ai.prompts import (
    get_ask_system_prompt,
    get_code_enrichment_prompt,
    get_table_enrichment_prompt,
)
from leai.cli import app
from leai.config import load_config
from leai.i18n import (
    DEFAULT_LOCALE,
    EN_MESSAGES,
    PT_MESSAGES,
    get_locale,
    normalize_locale,
    resolve_locale,
    set_locale,
    t,
)
from leai.template import get_default_config_template, write_default_config


def test_locale_key_parity():
    """Ensure both en-US and pt-BR catalogs define the exact same set of translation keys."""
    en_keys = set(EN_MESSAGES.keys())
    pt_keys = set(PT_MESSAGES.keys())
    missing_in_pt = en_keys - pt_keys
    missing_in_en = pt_keys - en_keys
    assert not missing_in_pt, f"Keys present in en-US but missing in pt-BR: {missing_in_pt}"
    assert not missing_in_en, f"Keys present in pt-BR but missing in en-US: {missing_in_en}"


def test_normalize_locale():
    """Verify locale string normalization and aliases."""
    assert normalize_locale("pt-BR") == "pt-BR"
    assert normalize_locale("pt_BR") == "pt-BR"
    assert normalize_locale("pt") == "pt-BR"
    assert normalize_locale("PT") == "pt-BR"
    assert normalize_locale("pt-br") == "pt-BR"

    assert normalize_locale("en-US") == "en-US"
    assert normalize_locale("en_US") == "en-US"
    assert normalize_locale("en") == "en-US"
    assert normalize_locale("EN") == "en-US"
    assert normalize_locale("en-us") == "en-US"

    assert normalize_locale("es") == DEFAULT_LOCALE
    assert normalize_locale("fr-FR") == DEFAULT_LOCALE
    assert normalize_locale(None) == DEFAULT_LOCALE
    assert normalize_locale("") == DEFAULT_LOCALE


def test_resolve_locale(monkeypatch):
    """Test resolution precedence: cli_lang > LEAI_LANG env > config_lang > default."""
    # 1. Default fallback
    monkeypatch.delenv("LEAI_LANG", raising=False)
    assert resolve_locale() == "en-US"

    # 2. Config language
    assert resolve_locale(config_lang="pt-BR") == "pt-BR"
    assert resolve_locale(config_lang="pt") == "pt-BR"

    # 3. Environment variable overrides config
    monkeypatch.setenv("LEAI_LANG", "pt")
    assert resolve_locale(config_lang="en-US") == "pt-BR"

    # 4. CLI option overrides both env and config
    assert resolve_locale(cli_lang="en-US", config_lang="pt-BR") == "en-US"
    assert resolve_locale(cli_lang="pt-BR", config_lang="en-US") == "pt-BR"


def test_translate_function():
    """Test t() formatting, locale switching, and fallback."""
    set_locale("en-US")
    assert get_locale() == "en-US"
    en_msg = t("updater.updated_success", version="1.2.3")
    assert "LEAI successfully updated to v1.2.3!" in en_msg

    set_locale("pt-BR")
    assert get_locale() == "pt-BR"
    pt_msg = t("updater.updated_success", version="1.2.3")
    assert "LEAI atualizado com sucesso para v1.2.3!" in pt_msg

    # Fallback to key if unknown
    assert t("non_existent_key_xyz") == "non_existent_key_xyz"

    # Safe formatting if required param is omitted
    safe_msg = t("updater.updated_success")
    assert "updater.updated_success" in safe_msg or "version" in safe_msg

    # Reset to default
    set_locale("en-US")


def test_bilingual_templates(tmp_path: Path):
    """Verify English and Portuguese config templates."""
    tpl_en = get_default_config_template("en-US")
    assert 'language: "en-US"' in tpl_en
    assert "1. ORACLE DATABASE CONNECTION (DSN)" in tpl_en

    tpl_pt = get_default_config_template("pt-BR")
    assert 'language: "pt-BR"' in tpl_pt
    assert "1. CONEXÃO COM O BANCO DE DADOS ORACLE" in tpl_pt

    # Write PT template and check loading
    pt_file = tmp_path / "leai_pt.yml"
    write_default_config(pt_file, lang="pt-BR")
    cfg_pt = load_config(pt_file)
    assert cfg_pt.language == "pt-BR"

    # Write EN template and check loading
    en_file = tmp_path / "leai_en.yml"
    write_default_config(en_file, lang="en-US")
    cfg_en = load_config(en_file)
    assert cfg_en.language == "en-US"


def test_cli_lang_flag():
    """Verify --lang and -L flags on CLI."""
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "--lang" in result.output or "-L" in result.output


def test_cli_init_with_lang(tmp_path: Path, monkeypatch):
    """Verify leai init --lang generates the requested language template."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["init", "--lang", "pt-BR"])
    assert result.exit_code == 0
    cfg_file = tmp_path / "leai.yml"
    assert cfg_file.exists()
    content = cfg_file.read_text(encoding="utf-8")
    assert 'language: "pt-BR"' in content
    assert "1. CONEXÃO COM O BANCO DE DADOS ORACLE" in content


def test_bilingual_ai_prompts():
    """Verify localized AI system prompts for table enrichment, code enrichment, and copilot chat."""
    # Table prompt
    en_table_prompt = get_table_enrichment_prompt("en-US")
    pt_table_prompt = get_table_enrichment_prompt("pt-BR")
    assert "You are an Expert Oracle Data Engineer" in en_table_prompt
    assert "Engenheiro de Dados e DBA Oracle Especialista" in pt_table_prompt
    assert "description" in en_table_prompt and "description" in pt_table_prompt
    assert "business_rules" in en_table_prompt and "business_rules" in pt_table_prompt

    # Code prompt
    en_code_prompt = get_code_enrichment_prompt("en-US")
    pt_code_prompt = get_code_enrichment_prompt("pt-BR")
    assert "Software Architect and Oracle PL/SQL Specialist" in en_code_prompt
    assert "Arquiteto de Software e Especialista em Oracle PL/SQL" in pt_code_prompt
    assert "subprograms" in en_code_prompt and "subprograms" in pt_code_prompt

    # Ask Copilot prompt
    en_ask_prompt = get_ask_system_prompt("en-US")
    pt_ask_prompt = get_ask_system_prompt("pt-BR")
    assert "You are the LEAI Expert Assistant" in en_ask_prompt
    assert "Você é o Assistente Especialista LEAI" in pt_ask_prompt
