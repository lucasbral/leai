"""Diagnostic health-check module for LEAI environment and active configurations."""

from __future__ import annotations

from pathlib import Path

from rich.box import ROUNDED
from rich.console import Console
from rich.panel import Panel

from leai.config import ConfigError, LeaiConfig, load_config


def _troubleshoot_oracle(err_msg: str) -> list[str]:
    """Provides actionable troubleshooting tips based on Oracle error message."""
    tips = []
    err_upper = err_msg.upper()
    if "ORA-01017" in err_upper or "INVALID USERNAME/PASSWORD" in err_upper:
        tips.append("Verifique as credenciais no leai.yml ou .env (DB_USER e DB_PASS).")
    elif "ORA-12170" in err_upper or "CONNECT TIMEOUT" in err_upper or "TIMED OUT" in err_upper:
        tips.append(
            "Tempo limite de conexão esgotado. Verifique se o host e a porta (1521) estão acessíveis da sua rede/VM (firewall/VPN)."
        )
    elif "ORA-12541" in err_upper or "NO LISTENER" in err_upper:
        tips.append("O Listener do Oracle não está respondendo na porta configurada (padrão: 1521).")
    elif "ORA-12514" in err_upper or "LISTENER DOES NOT CURRENTLY KNOW OF SERVICE" in err_upper:
        tips.append("O nome do serviço Oracle (DB_SERVICE ou SID) não foi reconhecido pelo Listener.")
    else:
        tips.append("Confira a sintaxe da DSN: oracle://${DB_USER}:${DB_PASS}@${DB_HOST}:1521/${DB_SERVICE}")
    return tips


def _troubleshoot_seaweedfs(err_msg: str, endpoint: str, bucket: str) -> list[str]:
    """Provides actionable troubleshooting tips based on SeaweedFS/S3 error message."""
    tips = []
    err_upper = err_msg.upper()
    if "COULD NOT CONNECT" in err_upper or "CONNECTION REFUSED" in err_upper or "TIMED OUT" in err_upper:
        tips.append(f"Não foi possível conectar ao endpoint: '{endpoint}'.")
        if endpoint.startswith("https://"):
            tips.append("Dica: Se o SeaweedFS rodar internamente sem certificado SSL, tente trocar para 'http://' no endpoint_url.")
        tips.append("Dica: Verifique se a porta do SeaweedFS S3 está correta (ex: porta 8333 padrão, ou 9000).")
        tips.append("Dica: Teste a resolução de DNS na VM: 'ping s3-host' ou adicione o IP no '/etc/hosts'.")
    elif "SSL" in err_upper or "CERTIFICATE" in err_upper:
        tips.append("Erro de validação do certificado SSL. Se for certificado interno/autoassinado, use 'http://' ou adicione a CA na VM.")
    elif "ACCESSDENIED" in err_upper or "INVALIDACCESSKEYID" in err_upper or "SIGNATUREDOESNOTMATCH" in err_upper:
        tips.append("Credenciais de acesso S3 recusadas. Verifique 'access_key' e 'secret_key' no leai.yml ou .env.")
    elif "NOSUCHBUCKET" in err_upper:
        tips.append(f"O bucket '{bucket}' não existe. Habilite 'auto_create_bucket: true' no leai.yml para criá-lo automaticamente.")
    else:
        tips.append("Verifique as configurações em 'storage.seaweedfs' no leai.yml.")
    return tips


def _troubleshoot_ai(err_msg: str, provider: str) -> list[str]:
    """Provides actionable troubleshooting tips based on AI provider error."""
    tips = []
    prov_lower = provider.lower()
    if prov_lower == "ollama":
        tips.append("Certifique-se de que o daemon do Ollama está rodando ('ollama serve' ou 'systemctl status ollama').")
        tips.append("Verifique se o modelo está baixado via 'ollama list' ou baixe com 'ollama pull <modelo>'.")
    elif prov_lower in ("openai", "gemini", "anthropic", "deepseek", "qwen"):
        tips.append(f"Verifique se a chave de API ({prov_lower.upper()}_API_KEY) está configurada e é válida.")
    elif prov_lower == "local":
        tips.append("Verifique se o servidor de inferência local (LM Studio / vLLM / LocalAI) está ativo na URL configurada.")
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
    out.print("\n[bold cyan]✦ Diagnóstico de Ambiente LEAI (doctor)[/bold cyan]")
    out.print("[dim]Verificando configurações ativas, conectividade e subsistemas...[/dim]\n")

    has_errors = False
    has_warnings = False

    # -------------------------------------------------------------------------
    # 1. Configuration & Schemas
    # -------------------------------------------------------------------------
    try:
        if isinstance(config, LeaiConfig):
            cfg = config
            out.print("[green]✓ Configuração:[/green] [bold]Instância carregada em memória[/bold]")
        else:
            cfg = load_config(config)
            out.print("[green]✓ Configuração:[/green] [bold]Arquivo validado com sucesso[/bold]")

        schemas_str = ", ".join(cfg.schemas) if cfg.schemas else "Nenhum"
        all_mode = " (Modo ALL schemas)" if cfg.is_all_schemas else ""
        out.print(f"  [dim]• Schemas configurados:[/dim] [cyan]{schemas_str}[/cyan]{all_mode}")
        out.print(f"  [dim]• Idioma ativo:[/dim] [cyan]{cfg.language}[/cyan]")
    except ConfigError as exc:
        out.print(f"[red]✗ Erro Crítico na Configuração:[/red] {exc}")
        out.print("  [yellow]💡 Dica: Execute 'leai init' para criar um novo arquivo leai.yml válido.[/yellow]\n")
        return False
    except Exception as exc:
        out.print(f"[red]✗ Falha inesperada ao ler configuração:[/red] {exc}\n")
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
            out.print("[green]✓ Banco de Dados Oracle:[/green] [bold]Conexão bem-sucedida![/bold]")
            out.print(f"  [dim]• Versão:[/dim] [cyan]{ver_str}[/cyan]")
        except Exception as exc:
            has_errors = True
            err_str = str(exc).strip()
            out.print("[red]✗ Banco de Dados Oracle:[/red] [bold red]Falha na conexão[/bold red]")
            out.print(f"  [red]Erro:[/red] [white]{err_str}[/white]")
            for tip in _troubleshoot_oracle(err_str):
                out.print(f"  [yellow]💡 Dica:[/yellow] {tip}")
    else:
        has_warnings = True
        out.print("[yellow]! Banco de Dados Oracle:[/yellow] [dim]DSN não configurado (modo offline / documentação local)[/dim]")

    out.print()

    # -------------------------------------------------------------------------
    # 3. AI Provider Engine
    # -------------------------------------------------------------------------
    provider = cfg.ai.default_provider or "ollama"
    try:
        from leai.ai import get_llm_client

        client = get_llm_client(cfg)
        out.print(
            f"[green]✓ Motor de IA ([bold yellow]{provider.upper()}[/bold yellow]):[/green] [bold]Cliente inicializado com sucesso[/bold]"
        )
        out.print(f"  [dim]• Modelo ativo:[/dim] [cyan]{client.model}[/cyan]")
        out.print(f"  [dim]• Timeout:[/dim] [cyan]{cfg.ai.timeout}s[/cyan] | [dim]Temperatura:[/dim] [cyan]{cfg.ai.temperature}[/cyan]")
    except Exception as exc:
        has_warnings = True
        err_str = str(exc).strip()
        out.print(f"[yellow]! Motor de IA ([bold]{provider.upper()}[/bold]):[/yellow] [bold yellow]Aviso na inicialização[/bold yellow]")
        out.print(f"  [yellow]Detalhe:[/yellow] {err_str}")
        for tip in _troubleshoot_ai(err_str, provider):
            out.print(f"  [dim]💡 Dica: {tip}[/dim]")

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
                out.print("[green]✓ Armazenamento S3 (SeaweedFS):[/green] [bold]Operacional[/bold]")
                out.print(f"  [dim]• Endpoint:[/dim] [cyan]{sw_cfg.endpoint_url}[/cyan]")
                out.print(f"  [dim]• Bucket:[/dim] [cyan]{sw_cfg.bucket}[/cyan] (Objetos detectados: [cyan]{objs}[/cyan])")
                out.print(f"  [dim]• Modo No-Cache:[/dim] [cyan]{sw_cfg.no_cache}[/cyan]")
            else:
                has_errors = True
                err_str = str(res.get("error", "Erro desconhecido")).strip()
                out.print("[red]✗ Armazenamento S3 (SeaweedFS):[/red] [bold red]Falha na conexão[/bold red]")
                out.print(f"  [dim]• Endpoint configurado:[/dim] [cyan]{sw_cfg.endpoint_url}[/cyan]")
                out.print(f"  [dim]• Bucket:[/dim] [cyan]{sw_cfg.bucket}[/cyan]")
                out.print(f"  [red]Erro:[/red] [white]{err_str}[/white]")
                for tip in _troubleshoot_seaweedfs(err_str, sw_cfg.endpoint_url, sw_cfg.bucket):
                    out.print(f"  [yellow]💡 Dica:[/yellow] {tip}")
        except Exception as exc:
            has_errors = True
            err_str = str(exc).strip()
            out.print("[red]✗ Armazenamento S3 (SeaweedFS):[/red] [bold red]Falha ao testar serviço[/bold red]")
            out.print(f"  [red]Erro:[/red] [white]{err_str}[/white]")
            for tip in _troubleshoot_seaweedfs(err_str, sw_cfg.endpoint_url, sw_cfg.bucket):
                out.print(f"  [yellow]💡 Dica:[/yellow] {tip}")
    else:
        out.print("[dim]• Armazenamento S3 (SeaweedFS): Desabilitado no leai.yml (usando apenas disco local)[/dim]")

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
                sync_desc = f"{git_info.behind} atrás do remoto" if git_info.behind > 0 else "sincronizado"
                mod_desc = f"{len(git_info.modified_files)} arquivos alterados" if git_info.modified_files else "limpo"
                out.print(f"[green]✓ Controle de Versão Git ({plat}):[/green] [bold]Ativo[/bold]")
                out.print(
                    f"  [dim]• Branch:[/dim] [cyan]{git_info.branch}[/cyan] • [dim]Status:[/dim] [cyan]{sync_desc}[/cyan] • [dim]Modificados:[/dim] [cyan]{mod_desc}[/cyan]"
                )
            else:
                out.print("[dim]• Controle de Versão Git: O diretório atual não é um repositório Git[/dim]")
        except Exception as exc:
            out.print(f"[dim]• Controle de Versão Git: Não disponível ({exc})[/dim]")
    else:
        out.print("[dim]• Controle de Versão Git: Desabilitado na configuração[/dim]")

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

    out.print("[green]✓ Estrutura de Arquivos Locais:[/green]")
    out.print(f"  [dim]• Raw Snapshots ({cfg.rawPath}):[/dim] [cyan]{raw_count}[/cyan] arquivos JSON")
    out.print(f"  [dim]• Anotações ({cfg.annotationsPath}):[/dim] [cyan]{ann_count}[/cyan] arquivos YAML")
    out.print(f"  [dim]• Documentação ({cfg.docPath}):[/dim] [cyan]{doc_count}[/cyan] arquivos Markdown")
    out.print(f"  [dim]• Logs de Atualização ({cfg.updates_log_path}):[/dim] [cyan]{log_count}[/cyan] registros")

    # -------------------------------------------------------------------------
    # Summary
    # -------------------------------------------------------------------------
    out.print()
    if has_errors:
        out.print(
            Panel(
                "[bold red]✗ O diagnóstico encontrou inconsistências ou falhas de conexão.[/bold red]\n"
                "[dim]Verifique as mensagens de erro e as dicas acima para corrigir a configuração.[/dim]",
                title="[bold red]Resultado do Diagnóstico[/bold red]",
                box=ROUNDED,
                border_style="red",
            )
        )
        return False
    elif has_warnings:
        out.print(
            Panel(
                "[bold yellow]! O ambiente está operacional, com alguns avisos leves ou serviços opcionais desligados.[/bold yellow]\n"
                "[dim]LEAI está pronto para uso local ou operações offline.[/dim]",
                title="[bold yellow]Resultado do Diagnóstico[/bold yellow]",
                box=ROUNDED,
                border_style="yellow",
            )
        )
        return True
    else:
        out.print(
            Panel(
                "[bold green]✓ Todos os subsistemas e conexões foram validados com 100% de sucesso![/bold green]\n"
                "[dim]O LEAI está totalmente pronto para extração, chat e pipelines autônomos.[/dim]",
                title="[bold green]Resultado do Diagnóstico[/bold green]",
                box=ROUNDED,
                border_style="green",
            )
        )
        return True
