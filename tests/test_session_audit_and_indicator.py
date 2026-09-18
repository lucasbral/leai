import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from prompt_toolkit.formatted_text import HTML

from leai.audit import SessionAuditLogger, ToolExecutionAudit, TurnAuditRecord
from leai.config import LeaiConfig
from leai.models import SchemaMetadata
from leai.tui.completer import LeaiCompleter, get_slash_commands
from leai.tui.session import InteractiveTUISession


def test_turn_audit_record_error_fields():
    record = TurnAuditRecord(
        user_prompt="SELECT * FROM INVALID",
        ai_response="",
        status="error",
        error="429 Resource Exhausted",
        error_type="RateLimitError",
        error_traceback="Traceback (most recent call last):\n  ...",
    )
    assert record.status == "error"
    assert record.error == "429 Resource Exhausted"
    assert record.error_type == "RateLimitError"
    assert "Traceback" in record.error_traceback


def test_session_audit_logger_tracks_success_and_errors(tmp_path):
    logger = SessionAuditLogger(session_id="test_sess_123456", log_dir=tmp_path)
    assert logger.session_id == "test_sess_123456"

    # 1. Record successful turn
    logger.record_turn(
        user_prompt="Who created TRANSACAO?",
        ai_response="The table was created by DBA.",
        provider="gemini",
        model="gemini-flash",
        latency_seconds=1.2,
        tokens_used=150,
        status="success",
    )

    summary = logger.get_session_summary()
    assert summary["total_turns"] == 1
    assert summary["total_errors"] == 0
    assert summary["has_errors"] is False

    # 2. Record error turn
    logger.record_turn(
        user_prompt="Run deep PLSQL trace",
        ai_response="",
        provider="gemini",
        model="gemini-flash",
        latency_seconds=0.5,
        tokens_used=0,
        status="error",
        error="429 RESOURCE_EXHAUSTED",
        error_type="GoogleGenerativeAIError",
        error_traceback="Traceback...",
    )

    summary2 = logger.get_session_summary()
    assert summary2["total_turns"] == 2
    assert summary2["total_errors"] == 1
    assert summary2["has_errors"] is True


def test_session_audit_export_json_and_markdown(tmp_path):
    logger = SessionAuditLogger(session_id="test_export_999", log_dir=tmp_path)
    logger.record_turn(
        user_prompt="Test Question",
        ai_response="Test Answer",
        status="success",
        latency_seconds=0.8,
        tokens_used=100,
    )
    logger.record_turn(
        user_prompt="Failing Question",
        ai_response="",
        status="error",
        error="Network timeout after 300s",
        error_type="TimeoutError",
        latency_seconds=5.0,
        tokens_used=0,
    )

    # Export JSON
    json_path = tmp_path / "audit.json"
    exported_json = logger.export_json(json_path)
    assert exported_json.exists()
    data = json.loads(exported_json.read_text(encoding="utf-8"))
    assert data["session_id"] == "test_export_999"
    assert data["total_turns"] == 2
    assert data["total_errors"] == 1
    assert data["turns"][1]["status"] == "error"
    assert data["turns"][1]["error"] == "Network timeout after 300s"

    # Export Markdown
    md_path = tmp_path / "audit.md"
    exported_md = logger.export_markdown(md_path)
    assert exported_md.exists()
    content = exported_md.read_text(encoding="utf-8")
    assert "Total Errors / Exceptions:** `1`" in content
    assert "❌ Turn 2:" in content
    assert "Network timeout after 300s" in content


def test_bottom_toolbar_and_session_indicator():
    config = LeaiConfig(dsn="oracle://user:pass@localhost:1521/XE")
    schemas = [SchemaMetadata(schema_name="SADRH", tables=[], views=[])]
    mock_client = MagicMock()
    mock_client.model = "gpt-4o-mini"
    mock_client.total_tokens = 500

    tui = InteractiveTUISession(schemas=schemas, config=config, client=mock_client, provider_name="openai")
    tui.audit_logger = SessionAuditLogger(session_id="20260918_140819_d4e131")

    # Initial toolbar without errors
    toolbar_html = tui._get_bottom_toolbar()
    assert isinstance(toolbar_html, HTML)
    rendered = toolbar_html.value
    assert "sess" in rendered
    assert "d4e131" in rendered
    assert "⚠️" not in rendered

    # Record error turn -> Toolbar shows error badge
    tui.audit_logger.record_turn(
        user_prompt="Failing call",
        ai_response="",
        status="error",
        error="Rate limit exceeded",
    )
    toolbar_with_err = tui._get_bottom_toolbar().value
    assert "d4e131" in toolbar_with_err
    assert "⚠️ 1 err" in toolbar_with_err


def test_slash_command_session_and_completer():
    config = LeaiConfig(dsn="oracle://user:pass@localhost:1521/XE")
    schemas = [SchemaMetadata(schema_name="SADRH", tables=[], views=[])]
    mock_client = MagicMock()
    mock_client.model = "qwen2.5"

    tui = InteractiveTUISession(schemas=schemas, config=config, client=mock_client, provider_name="ollama")

    # Check completer commands
    commands = dict(get_slash_commands())
    assert "/session" in commands

    # Test /session command execution
    with patch("leai.tui.session.console.print") as mock_print:
        handled = tui.handle_slash_command("/session")
        assert handled is True
        assert mock_print.called

    # Test /session export execution
    with patch("leai.tui.session.console.print") as mock_print:
        with tempfile.TemporaryDirectory() as tmp_d:
            export_target = str(Path(tmp_d) / "session_export.md")
            handled_export = tui.handle_slash_command(f"/session export {export_target}")
            assert handled_export is True
            assert Path(export_target).exists()


def test_send_ai_prompt_catches_exception_and_records_audit():
    config = LeaiConfig(dsn="oracle://user:pass@localhost:1521/XE")
    schemas = [SchemaMetadata(schema_name="SADRH", tables=[], views=[])]
    mock_client = MagicMock()
    mock_client.model = "gemini-flash"

    tui = InteractiveTUISession(schemas=schemas, config=config, client=mock_client, provider_name="gemini")
    tui.session = MagicMock()
    tui.session.send.side_effect = RuntimeError("429 RESOURCE_EXHAUSTED: quota exceeded")

    with patch("leai.tui.session.console.print") as mock_print:
        # Calling prompt should NOT raise an unhandled exception
        tui._send_ai_prompt("Execute deep analysis")
        assert mock_print.called

    # Verify turn was safely captured in audit_logger
    assert len(tui.audit_logger.turns) == 1
    turn = tui.audit_logger.turns[0]
    assert turn.status == "error"
    assert "429 RESOURCE_EXHAUSTED" in turn.error
    assert turn.error_type == "RuntimeError"
    assert turn.user_prompt == "Execute deep analysis"
