"""Diagnostic health-check module for LEAI environment and active configurations."""

from __future__ import annotations

from pathlib import Path

from rich.box import ROUNDED
from rich.console import Console
from rich.panel import Panel

from leai.config import ConfigError, LeaiConfig, load_config
from leai.i18n import t


def _troubleshoot_oracle(err_msg: str) -> list[str]:
    """Provides actionable troubleshooting tips based on Oracle error message."""
    tips = []
    err_upper = err_msg.upper()
    if "ORA-01017" in err_upper or "INVALID USERNAME/PASSWORD" in err_upper:
        tips.append(t("doctor.oracle_troubleshoot_creds"))
    elif "ORA-12170" in err_upper or "CONNECT TIMEOUT" in err_upper or "TIMED OUT" in err_upper:
        tips.append(t("doctor.oracle_troubleshoot_timeout"))
    elif "ORA-12541" in err_upper or "NO LISTENER" in err_upper:
        tips.append(t("doctor.oracle_troubleshoot_listener"))
    elif "ORA-12514" in err_upper or "LISTENER DOES NOT CURRENTLY KNOW OF SERVICE" in err_upper:
        tips.append(t("doctor.oracle_troubleshoot_service"))
    else:
        tips.append(t("doctor.oracle_troubleshoot_syntax"))
    return tips


def _troubleshoot_seaweedfs(err_msg: str, endpoint: str, bucket: str) -> list[str]:
    """Provides actionable troubleshooting tips based on SeaweedFS/S3 error message."""
    tips = []
    err_upper = err_msg.upper()
    if "COULD NOT CONNECT" in err_upper or "CONNECTION REFUSED" in err_upper or "TIMED OUT" in err_upper:
        tips.append(t("doctor.seaweed_troubleshoot_connect", endpoint=endpoint))
        if endpoint.startswith("https://"):
            tips.append(t("doctor.seaweed_troubleshoot_ssl_hint"))
        tips.append(t("doctor.seaweed_troubleshoot_port"))
        tips.append(t("doctor.seaweed_troubleshoot_dns"))
    elif "SSL" in err_upper or "CERTIFICATE" in err_upper:
        tips.append(t("doctor.seaweed_troubleshoot_ssl"))
    elif "ACCESSDENIED" in err_upper or "INVALIDACCESSKEYID" in err_upper or "SIGNATUREDOESNOTMATCH" in err_upper:
        tips.append(t("doctor.seaweed_troubleshoot_auth"))
    elif "NOSUCHBUCKET" in err_upper:
        tips.append(t("doctor.seaweed_troubleshoot_bucket", bucket=bucket))
    else:
        tips.append(t("doctor.seaweed_troubleshoot_generic"))
    return tips


def _troubleshoot_ai(err_msg: str, provider: str) -> list[str]:
    """Provides actionable troubleshooting tips based on AI provider error."""
    tips = []
    prov_lower = provider.lower()
    if prov_lower == "ollama":
        tips.append(t("doctor.ai_troubleshoot_ollama_daemon"))
        tips.append(t("doctor.ai_troubleshoot_ollama_model"))
    elif prov_lower in ("openai", "gemini", "anthropic", "deepseek", "qwen"):
        tips.append(t("doctor.ai_troubleshoot_api_key", provider=prov_lower.upper()))
    elif prov_lower == "local":
        tips.append(t("doctor.ai_troubleshoot_local"))
    return tips


def run_diagnostics(
    config: LeaiConfig | Path | str = Path("leai.yml"),
    console: Console | None = None,
) -> bool:
    """Runs a comprehensive pre-flight diagnostic health check across all LEAI subsystems.

    Returns:
        True if all critical checks passed without fatal errors, False otherwise.
    """
    out = console or Console()
    out.print(f"\n[bold cyan]{t('doctor.title')}[/bold cyan]")
    out.print(f"[dim]{t('doctor.subtitle')}[/dim]\n")

    has_errors = False
    has_warnings = False

    # -------------------------------------------------------------------------
    # 1. Configuration & Schemas
    # -------------------------------------------------------------------------
    try:
        if isinstance(config, LeaiConfig):
            cfg = config
            out.print(t("doctor.cfg_memory"))
        else:
            cfg = load_config(config)
            out.print(t("doctor.cfg_file"))

        schemas_str = ", ".join(cfg.schemas) if cfg.schemas else t("doctor.none_schemas")
        all_mode = t("doctor.all_mode") if cfg.is_all_schemas else ""
        out.print(f"  [dim]• {t('doctor.schemas_configured')}[/dim] [cyan]{schemas_str}[/cyan]{all_mode}")
        out.print(f"  [dim]• {t('doctor.active_language')}[/dim] [cyan]{cfg.language}[/cyan]")
    except ConfigError as exc:
        out.print(t("doctor.cfg_error", error=exc))
        out.print(t("doctor.cfg_init_hint"))
        return False
    except Exception as exc:
        out.print(t("doctor.cfg_unexpected", error=exc))
        return False

    out.print()

    # -------------------------------------------------------------------------
    # 2. Oracle Database Connection
    # -------------------------------------------------------------------------
    if cfg.dsn:
        try:
            import oracledb

            from leai.oracle import _build_connect_kwargs

            conn_kwargs = _build_connect_kwargs(cfg.dsn)
            conn = oracledb.connect(**conn_kwargs)
            cur = conn.cursor()
            cur.execute("SELECT * FROM v$version WHERE ROWNUM = 1")
            row = cur.fetchone()
            ver_str = row[0] if row else "Oracle Database"
            conn.close()
            out.print(t("doctor.oracle_success"))
            out.print(f"  [dim]• {t('doctor.oracle_version')}[/dim] [cyan]{ver_str}[/cyan]")
        except Exception as exc:
            has_errors = True
            err_str = str(exc).strip()
            out.print(t("doctor.oracle_failed"))
            out.print(f"  [red]{t('doctor.oracle_error_label')}[/red] [white]{err_str}[/white]")
            for tip in _troubleshoot_oracle(err_str):
                out.print(f"  [yellow]{t('doctor.oracle_tip_label')}[/yellow] {tip}")
    else:
        has_warnings = True
        out.print(t("doctor.oracle_offline"))

    out.print()

    # -------------------------------------------------------------------------
    # 3. AI Provider Engine
    # -------------------------------------------------------------------------
    provider = cfg.ai.default_provider or "ollama"
    try:
        from leai.ai import get_llm_client

        client = get_llm_client(cfg)
        out.print(t("doctor.ai_client_success", provider=provider.upper()))
        out.print(f"  [dim]• {t('doctor.ai_active_model')}[/dim] [cyan]{client.model}[/cyan]")
        out.print(f"  [dim]• {t('doctor.ai_timeout_label')}[/dim] [cyan]{cfg.ai.timeout}s[/cyan] | [dim]{t('doctor.ai_temperature_label')}[/dim] [cyan]{cfg.ai.temperature}[/cyan]")
    except Exception as exc:
        has_warnings = True
        err_str = str(exc).strip()
        out.print(t("doctor.ai_init_warning", provider=provider.upper()))
        out.print(f"  [yellow]{t('doctor.ai_detail_label')}[/yellow] {err_str}")
        for tip in _troubleshoot_ai(err_str, provider):
            out.print(f"  [dim]{t('doctor.oracle_tip_label')} {tip}[/dim]")

    out.print()

    # -------------------------------------------------------------------------
    # 4. Storage S3 / SeaweedFS
    # -------------------------------------------------------------------------
    if getattr(cfg, "storage", None) and cfg.storage.seaweedfs.enabled:
        sw_cfg = cfg.storage.seaweedfs
        try:
            from leai.storage import SeaweedFSStorage

            storage = SeaweedFSStorage(sw_cfg)
            res = storage.test_connection()
            if res.get("success"):
                objs = res.get("objects_found", 0)
                out.print(t("doctor.seaweed_success"))
                out.print(f"  [dim]• {t('doctor.seaweed_endpoint')}[/dim] [cyan]{sw_cfg.endpoint_url}[/cyan]")
                out.print(f"  [dim]• {t('doctor.seaweed_bucket')}[/dim] [cyan]{sw_cfg.bucket}[/cyan] ({t('doctor.seaweed_objects_found')} [cyan]{objs}[/cyan])")
                out.print(f"  [dim]• {t('doctor.seaweed_nocache')}[/dim] [cyan]{sw_cfg.no_cache}[/cyan]")
            else:
                has_errors = True
                err_str = str(res.get("error", "Erro desconhecido")).strip()
                out.print(t("doctor.seaweed_failed"))
                out.print(f"  [dim]• {t('doctor.seaweed_endpoint')}[/dim] [cyan]{sw_cfg.endpoint_url}[/cyan]")
                out.print(f"  [dim]• {t('doctor.seaweed_bucket')}[/dim] [cyan]{sw_cfg.bucket}[/cyan]")
                out.print(f"  [red]{t('doctor.oracle_error_label')}[/red] [white]{err_str}[/white]")
                for tip in _troubleshoot_seaweedfs(err_str, sw_cfg.endpoint_url, sw_cfg.bucket):
                    out.print(f"  [yellow]{t('doctor.oracle_tip_label')}[/yellow] {tip}")
        except Exception as exc:
            has_errors = True
            err_str = str(exc).strip()
            out.print(t("doctor.seaweed_test_error"))
            out.print(f"  [red]{t('doctor.oracle_error_label')}[/red] [white]{err_str}[/white]")
            for tip in _troubleshoot_seaweedfs(err_str, sw_cfg.endpoint_url, sw_cfg.bucket):
                out.print(f"  [yellow]{t('doctor.oracle_tip_label')}[/yellow] {tip}")
    else:
        out.print(t("doctor.seaweed_disabled"))

    out.print()

    # -------------------------------------------------------------------------
    # 5. Git / Version Control Ops
    # -------------------------------------------------------------------------
    if getattr(cfg, "git", None) and cfg.git.enabled:
        try:
            from leai.git_ops import get_git_status

            git_info = get_git_status(fetch=False)
            if git_info.is_repo:
                plat = git_info.platform_name
                sync_desc = t("doctor.git_behind_remote", count=git_info.behind) if git_info.behind > 0 else t("doctor.git_synced")
                mod_desc = t("doctor.git_files_modified", count=len(git_info.modified_files)) if git_info.modified_files else t("doctor.git_clean")
                out.print(t("doctor.git_active", platform=plat))
                out.print(
                    f"  [dim]• {t('doctor.git_branch')}[/dim] [cyan]{git_info.branch}[/cyan] • [dim]{t('doctor.git_status')}[/dim] [cyan]{sync_desc}[/cyan] • [dim]{t('doctor.git_modified')}[/dim] [cyan]{mod_desc}[/cyan]"
                )
            else:
                out.print(t("doctor.git_not_repo"))
        except Exception as exc:
            out.print(t("doctor.git_not_available", error=exc))
    else:
        out.print(t("doctor.git_disabled"))

    out.print()

    # -------------------------------------------------------------------------
    # 6. Local Pipeline Directories & Objects
    # -------------------------------------------------------------------------
    raw_exists = cfg.rawPath.exists()
    ann_exists = cfg.annotationsPath.exists()
    doc_exists = cfg.docPath.exists()
    log_exists = cfg.updates_log_path.exists()

    raw_count = len(list(cfg.rawPath.glob("**/*.json"))) if raw_exists else 0
    ann_count = len(list(cfg.annotationsPath.glob("**/*.yml"))) if ann_exists else 0
    doc_count = len(list(cfg.docPath.glob("**/*.md"))) if doc_exists else 0
    log_count = len(list(cfg.updates_log_path.glob("**/*.json"))) if log_exists else 0

    out.print(t("doctor.fs_title"))
    out.print(f"  [dim]• {t('doctor.fs_raw', path=cfg.rawPath)}[/dim] [cyan]{t('doctor.fs_json_files', count=raw_count)}[/cyan]")
    out.print(f"  [dim]• {t('doctor.fs_annotations', path=cfg.annotationsPath)}[/dim] [cyan]{t('doctor.fs_yaml_files', count=ann_count)}[/cyan]")
    out.print(f"  [dim]• {t('doctor.fs_docs', path=cfg.docPath)}[/dim] [cyan]{t('doctor.fs_md_files', count=doc_count)}[/cyan]")
    out.print(f"  [dim]• {t('doctor.fs_logs', path=cfg.updates_log_path)}[/dim] [cyan]{t('doctor.fs_records', count=log_count)}[/cyan]")

    # -------------------------------------------------------------------------
    # Summary
    # -------------------------------------------------------------------------
    out.print()
    if has_errors:
        out.print(
            Panel(
                t("doctor.summary_errors_body"),
                title=t("doctor.summary_errors_title"),
                box=ROUNDED,
                border_style="red",
            )
        )
        return False
    elif has_warnings:
        out.print(
            Panel(
                t("doctor.summary_warnings_body"),
                title=t("doctor.summary_warnings_title"),
                box=ROUNDED,
                border_style="yellow",
            )
        )
        return True
    else:
        out.print(
            Panel(
                t("doctor.summary_success_body"),
                title=t("doctor.summary_success_title"),
                box=ROUNDED,
                border_style="green",
            )
        )
        return True

