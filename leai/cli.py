from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

if sys.platform == "win32":
    try:
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if sys.stderr and hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
        import ctypes

        kernel32 = ctypes.windll.kernel32
        for std_handle_id in (-11, -12):
            handle = kernel32.GetStdHandle(std_handle_id)
            mode = ctypes.c_ulong()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
                mode.value |= 0x0004
                kernel32.SetConsoleMode(handle, mode)
    except Exception:
        pass

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Column, Table

from leai.config import ConfigError, LeaiConfig, load_config
from leai.models import SchemaMetadata
from leai.raw import load_raw_schemas


def _build_connect_kwargs(*args, **kwargs):
    from leai.oracle import _build_connect_kwargs as fn

    return fn(*args, **kwargs)


def fetch_schema_metadata(*args, **kwargs):
    from leai.oracle import fetch_schema_metadata as fn

    return fn(*args, **kwargs)


def fetch_available_schemas(*args, **kwargs):
    from leai.oracle import fetch_available_schemas as fn

    return fn(*args, **kwargs)


def fetch_focal_trace(*args, **kwargs):
    from leai.oracle import fetch_focal_trace as fn

    return fn(*args, **kwargs)


def save_raw_schema(*args, **kwargs):
    from leai.raw import save_raw_schema as fn

    return fn(*args, **kwargs)


def trace_raw_dependencies(*args, **kwargs):
    from leai.raw import trace_raw_dependencies as fn

    return fn(*args, **kwargs)


def sync_schema_annotations(*args, **kwargs):
    from leai.docs import sync_schema_annotations as fn

    return fn(*args, **kwargs)


def count_schema_objects(*args, **kwargs):
    from leai.docs import count_schema_objects as fn

    return fn(*args, **kwargs)


def write_schema_docs(*args, **kwargs):
    from leai.docs import write_schema_docs as fn

    return fn(*args, **kwargs)


def write_dossier_doc(*args, **kwargs):
    from leai.docs import write_dossier_doc as fn

    return fn(*args, **kwargs)


def write_rag_json_file(*args, **kwargs):
    from leai.docs import write_rag_json_file as fn

    return fn(*args, **kwargs)


def _resolve_storage(cfg: LeaiConfig, seaweed_flag: bool = False):
    if seaweed_flag or cfg.storage.seaweedfs.enabled:
        from leai.storage import SeaweedFSStorage

        return SeaweedFSStorage(cfg.storage.seaweedfs)
    return None


def _calculate_risk_level(*args, **kwargs):
    from leai.docs import _calculate_risk_level as fn

    return fn(*args, **kwargs)


def enrich_schema_annotations(*args, **kwargs):
    from leai.enrich import enrich_schema_annotations as fn

    return fn(*args, **kwargs)


def get_llm_client(*args, **kwargs):
    from leai.ai import get_llm_client as fn

    return fn(*args, **kwargs)


class _LazyOracledb:
    def __getattr__(self, name):
        import oracledb

        return getattr(oracledb, name)


oracledb = _LazyOracledb()


class _LazyChatSession:
    def __new__(cls, *args, **kwargs):
        from leai.chat_session import ChatSession

        return ChatSession(*args, **kwargs)


ChatSession = _LazyChatSession


class _LazyInteractiveTUISession:
    def __new__(cls, *args, **kwargs):
        from leai.tui import InteractiveTUISession

        return InteractiveTUISession(*args, **kwargs)


InteractiveTUISession = _LazyInteractiveTUISession


class _LazyDocEditor:
    def __new__(cls, *args, **kwargs):
        from leai.tui import DocEditor

        return DocEditor(*args, **kwargs)


DocEditor = _LazyDocEditor


app = typer.Typer(help="CLI for Oracle Database Intelligence & Documentation.")
console = Console(legacy_windows=False)


def _create_progress_bar():
    """Creates a fully responsive progress bar that gracefully handles terminal resizing without wrapping or ghost lines."""
    from rich.progress import (
        BarColumn,
        Progress,
        SpinnerColumn,
        TaskProgressColumn,
        TextColumn,
        TimeElapsedColumn,
    )

    return Progress(
        SpinnerColumn(spinner_name="dots", style="bold cyan", finished_text="[bold green]✓[/bold green]"),
        TextColumn(
            "{task.description}",
            table_column=Column(no_wrap=True, overflow="ellipsis"),
        ),
        BarColumn(
            bar_width=20,
            table_column=Column(no_wrap=True),
        ),
        TaskProgressColumn(table_column=Column(no_wrap=True)),
        TimeElapsedColumn(table_column=Column(no_wrap=True)),
        console=console,
        expand=False,
        auto_refresh=True,
        refresh_per_second=6,
        transient=False,
    )


def _version_callback(value: bool) -> None:
    if value:
        from leai import __version__

        console.print(f"[bold cyan]LEAI CLI[/bold cyan] version [bold green]{__version__}[/bold green]")
        raise typer.Exit()


def _print_final_summary_panel(
    title: str,
    total_schemas: int,
    totals: dict[str, int],
    elapsed_seconds: float,
    output_paths: dict[str, Path],
) -> None:
    total_objects = sum(totals.values())
    lines = [
        f"[bold]Total Schemas:[/bold] {total_schemas}",
        f"[bold]Processed Objects:[/bold] {total_objects:,} items",
        f"[dim]  • Tables: {totals.get('tables', 0)} | Views: {totals.get('views', 0)} | MViews: {totals.get('mviews', 0)}[/dim]",
        f"[dim]  • Code Objects: {totals.get('code_objects', 0)} | Triggers: {totals.get('triggers', 0)} | Sequences: {totals.get('sequences', 0)}[/dim]",
        f"[dim]  • Indexes: {totals.get('indexes', 0)} | Synonyms: {totals.get('synonyms', 0)}[/dim]",
        "",
        f"[bold]Execution Time:[/bold] {elapsed_seconds:.2f}s",
    ]
    if output_paths:
        lines.append("\n[bold]Generated Outputs:[/bold]")
        for label, path in output_paths.items():
            lines.append(f"  • {label}: [bold cyan]{path}[/bold cyan]")

    console.print()
    console.print(Panel("\n".join(lines), title=f"[bold green]✓ {title}[/bold green]", border_style="green"))


@app.command()
def init(
    output: Path = typer.Option(Path("leai.yml"), "--output", "-o", help="Configuration file path to create"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite if the file already exists"),
) -> None:
    """Creates an initial leai.yml configuration file in the current directory."""
    if output.exists() and not force:
        console.print(f"[yellow]The file [bold]{output}[/bold] already exists. Use [bold]--force[/bold] to overwrite.[/yellow]")
        raise typer.Exit(code=1)

    from leai.template import write_default_config

    write_default_config(output, overwrite=True)
    console.print(f"[green]✓ Configuration file created successfully at:[/green] [bold cyan]{output}[/bold cyan]")
    console.print("[dim]Edit the file with your Oracle credentials and AI keys before running 'leai extract'.[/dim]")


@app.command()
def check(
    config: Path = typer.Option(Path("leai.yml"), "--config", "-c", help="Path to leai.yml"),
) -> None:
    """Validates the configuration file, tests Oracle connection, and checks AI providers."""
    console.print(f"[cyan]Checking configuration file:[/cyan] [bold]{config}[/bold]...")
    try:
        cfg = load_config(config)
        schemas_info = ", ".join(cfg.schemas) if cfg.schemas else "None"
        console.print(f"[green]✓ Valid configuration![/green] (Configured schemas: [bold]{schemas_info}[/bold])")
    except ConfigError as exc:
        console.print(f"[red]✗ Configuration error:[/red] {exc}")
        raise typer.Exit(code=1)

    # 1. Verify Oracle database connection
    if cfg.dsn:
        console.print("\n[cyan]Testing Oracle database connection...[/cyan]")
        try:
            conn = oracledb.connect(**_build_connect_kwargs(cfg.dsn))
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM v$version WHERE ROWNUM = 1")
            ver = cursor.fetchone()
            ver_str = ver[0] if ver else "Oracle Database"
            conn.close()
            console.print(f"[green]✓ Connection to Oracle successful![/green] ([dim]{ver_str}[/dim])")
        except Exception as exc:
            console.print(f"[red]✗ Failed to connect to Oracle:[/red] {exc}")
    else:
        console.print("\n[yellow]! DSN not configured. Online extraction operations will not be available.[/yellow]")

    # 2. Verify AI Provider
    default_prov = cfg.ai.default_provider or "openai"
    console.print(f"\n[cyan]Verifying default AI provider ([bold yellow]{default_prov}[/bold yellow])...[/cyan]")
    try:
        client = get_llm_client(cfg)
        console.print(f"[green]✓ AI client initialized successfully![/green] (Model: [bold green]{client.model}[/bold green])")
    except Exception as exc:
        console.print(f"[yellow]! Warning during AI initialization:[/yellow] {exc}")


@app.command(name="doctor")
def doctor(
    config: Path = typer.Option(Path("leai.yml"), "--config", "-c", help="Path to leai.yml"),
) -> None:
    """Pre-flight diagnostic health check (alias for 'check'). Validates Oracle connection, config, and AI."""
    check(config=config)


@app.command()
def extract(
    config: Path = typer.Option(Path("leai.yml"), "--config", "-c", help="Path to leai.yml"),
    schemas: list[str] = typer.Option(None, "--schema", "--schemas", "-s", help="Oracle schema name(s) to extract (overrides leai.yml)"),
    object_types: list[str] = typer.Option(None, "--object-type", "-t", help="Object types to extract (e.g. tables, views, procedures)"),
    days: int = typer.Option(None, "--days", "-d", help="Extract only objects modified in the last N days (incremental extraction)"),
    seaweed: bool = typer.Option(False, "--seaweed", "-W", help="Save RAW snapshots directly to SeaweedFS S3 storage"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Do not write local files in rawPath, send only to SeaweedFS"),
    force_upload: bool = typer.Option(
        False, "--force-upload", "-F", help="Force upload of all objects to SeaweedFS (bypasses SHA-256 manifest)"
    ),
) -> None:
    """Extracts raw technical snapshot from Oracle database into rawPath."""
    start_time = time.perf_counter()
    try:
        cfg = load_config(config)
        if schemas:
            cfg.schemas = [s.strip().upper() for s in schemas]
        if object_types:
            cfg.object_types = [t.lower() for t in object_types]
    except ConfigError as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        raise typer.Exit(code=1)

    storage = _resolve_storage(cfg, seaweed)
    is_no_cache = no_cache or cfg.storage.seaweedfs.no_cache
    if is_no_cache and not storage:
        console.print("[red]Error:[/red] --no-cache requires SeaweedFS to be enabled (use --seaweed or enable it in leai.yml).")
        raise typer.Exit(code=1)

    if storage:
        try:
            storage.ensure_bucket_exists()
            mode_tags = []
            if is_no_cache:
                mode_tags.append("Remote-only")
            if cfg.storage.seaweedfs.incremental and not force_upload:
                mode_tags.append("SHA-256 Incremental")
            elif force_upload:
                mode_tags.append("Force Upload")
            tag_str = f" [dim]({', '.join(mode_tags)})[/dim]" if mode_tags else ""
            console.print(
                f"[cyan]SeaweedFS Storage:[/cyan] [bold green]Active[/bold green] (Endpoint: {cfg.storage.seaweedfs.endpoint_url}, Bucket: {cfg.storage.seaweedfs.bucket}){tag_str}\n"
            )
        except Exception as exc:
            console.print(f"[red]SeaweedFS error:[/red] {exc}")
            raise typer.Exit(code=1)

    total_s3_uploaded = 0
    total_s3_skipped = 0

    try:
        connection = oracledb.connect(**_build_connect_kwargs(cfg.dsn))
        try:
            target_schemas = fetch_available_schemas(connection, cfg)

            is_multi = len(target_schemas) > 1 or cfg.is_all_schemas
            days_banner = f" • [bold yellow]Incremental (last {days} days)[/bold yellow]" if days else ""
            console.print(
                f"[cyan]Schemas to extract:[/cyan] [bold]{', '.join(target_schemas[:10])}{'...' if len(target_schemas) > 10 else ''}[/bold] (Total: {len(target_schemas)}){days_banner}\n"
            )

            totals = {
                "tables": 0,
                "views": 0,
                "mviews": 0,
                "code_objects": 0,
                "triggers": 0,
                "sequences": 0,
                "indexes": 0,
                "synonyms": 0,
            }

            with _create_progress_bar() as progress:
                overall_task = (
                    progress.add_task(
                        f"[bold cyan]Overall Extraction[/bold cyan] (0/{len(target_schemas)} schemas)",
                        total=len(target_schemas),
                    )
                    if is_multi
                    else None
                )
                schema_task = progress.add_task("Extracting...", total=100)

                for s_idx, schema_name in enumerate(target_schemas, 1):
                    schema_obj_count = [0]
                    progress.reset(
                        schema_task,
                        total=100,
                        description=f"Extracting [bold yellow]{schema_name}[/bold yellow]",
                    )
                    progress.refresh()

                    def _cb(cat: str, count: int, step_idx: int, total_steps: int, s_name=schema_name) -> None:
                        if count > 0:
                            schema_obj_count[0] += count
                        pct = int((step_idx / total_steps) * 100) if total_steps else 100
                        progress.update(
                            schema_task,
                            completed=pct,
                            total=100,
                            description=f"Extracting [bold yellow]{s_name}[/bold yellow] [[bold cyan]{pct}%[/bold cyan]] ({schema_obj_count[0]:,} objects) [dim]│ {cat}[/dim]",
                        )
                        progress.refresh()

                    schema_meta = fetch_schema_metadata(cfg, schema_name=schema_name, callback=_cb, days=days, connection=connection)

                    totals["tables"] += len(schema_meta.tables)
                    totals["views"] += len(schema_meta.views)
                    totals["mviews"] += len(schema_meta.mviews)
                    totals["code_objects"] += len(schema_meta.code_objects)
                    totals["triggers"] += len(schema_meta.triggers)
                    totals["sequences"] += len(schema_meta.sequences)
                    totals["indexes"] += len(schema_meta.indexes)
                    totals["synonyms"] += len(schema_meta.synonyms)

                    save_raw_schema(
                        schema_meta,
                        cfg.rawPath,
                        multi_schema=True,
                        storage=storage,
                        local_cache=not is_no_cache,
                        force_upload=force_upload,
                    )
                    if storage and hasattr(storage, "last_save_result"):
                        total_s3_uploaded += getattr(storage.last_save_result, "uploaded", 0)
                        total_s3_skipped += getattr(storage.last_save_result, "skipped", 0)

                    if overall_task is not None:
                        progress.advance(overall_task, 1)
                        progress.update(
                            overall_task,
                            description=f"[bold cyan]Overall Extraction[/bold cyan] ({s_idx}/{len(target_schemas)} schemas)",
                        )
        finally:
            connection.close()

        elapsed = time.perf_counter() - start_time
        output_paths: dict[str, Any] = {}
        if not is_no_cache:
            output_paths["RAW Snapshot"] = cfg.rawPath
        if storage:
            bucket_str = f"{cfg.storage.seaweedfs.bucket}/{cfg.storage.seaweedfs.raw_prefix}"
            if total_s3_skipped > 0 or total_s3_uploaded > 0:
                bucket_str += f" ([bold green]{total_s3_uploaded} versionados[/bold green], [dim]{total_s3_skipped} inalterados/skip[/dim])"
            output_paths["SeaweedFS S3"] = bucket_str
        if is_no_cache:
            output_paths["Local Disk Cache"] = "[yellow]Disabled (Remote-only)[/yellow]"

        _print_final_summary_panel(
            title="RAW Extraction Completed",
            total_schemas=len(target_schemas),
            totals=totals,
            elapsed_seconds=elapsed,
            output_paths=output_paths,
        )
    except Exception as exc:
        console.print(f"[red]Error during RAW extraction:[/red] {exc}")
        raise typer.Exit(code=1)


@app.command()
def annotate(
    config: Path = typer.Option(Path("leai.yml"), "--config", "-c", help="Path to leai.yml"),
    schemas: list[str] = typer.Option(None, "--schema", "--schemas", "-s", help="Oracle schema name(s) to sync (overrides leai.yml)"),
    object_types: list[str] = typer.Option(None, "--object-type", "-t", help="Object types to sync (e.g. tables, views, procedures)"),
    seaweed: bool = typer.Option(False, "--seaweed", "-W", help="Sync annotations with SeaweedFS S3 storage"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Do not write local cache files, operate directly with SeaweedFS"),
) -> None:
    """Generates/synchronizes YAML annotation stubs in annotationsPath from rawPath (Offline)."""
    start_time = time.perf_counter()
    try:
        cfg = load_config(config)
        if schemas:
            cfg.schemas = [s.strip().upper() for s in schemas]
        if object_types:
            cfg.object_types = [t.lower() for t in object_types]
    except ConfigError as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        raise typer.Exit(code=1)

    storage = _resolve_storage(cfg, seaweed)
    is_no_cache = no_cache or cfg.storage.seaweedfs.no_cache
    if is_no_cache and not storage:
        console.print("[red]Error:[/red] --no-cache requires SeaweedFS to be enabled (use --seaweed or enable it in leai.yml).")
        raise typer.Exit(code=1)

    if storage:
        try:
            storage.ensure_bucket_exists()
            remote_tag = " [dim](Remote-only / No local cache)[/dim]" if is_no_cache else ""
            console.print(
                f"[cyan]SeaweedFS Storage:[/cyan] [bold green]Active[/bold green] (Endpoint: {cfg.storage.seaweedfs.endpoint_url}, Bucket: {cfg.storage.seaweedfs.bucket}){remote_tag}\n"
            )
        except Exception as exc:
            console.print(f"[red]SeaweedFS error:[/red] {exc}")
            raise typer.Exit(code=1)

    try:
        source_desc = f"SeaweedFS ({cfg.storage.seaweedfs.bucket})" if (storage and is_no_cache) else str(cfg.rawPath)
        console.print(f"[cyan]Loading snapshots from[/cyan] [bold]{source_desc}[/bold]...\n")
        target_schemas = cfg.schemas if not cfg.is_all_schemas else None
        schemas_meta = load_raw_schemas(cfg.rawPath, target_schemas=target_schemas, storage=storage, local_cache=not is_no_cache)
        is_multi = len(schemas_meta) > 1

        totals = {
            "tables": 0,
            "views": 0,
            "mviews": 0,
            "code_objects": 0,
            "triggers": 0,
            "sequences": 0,
            "indexes": 0,
            "synonyms": 0,
        }
        total_ann = 0
        total_objects_all = sum(count_schema_objects(s, cfg.object_types) for s in schemas_meta)

        with _create_progress_bar() as progress:
            overall_task = (
                progress.add_task(
                    f"[bold cyan]Overall Synchronization[/bold cyan] (0/{len(schemas_meta)} schemas)",
                    total=max(1, total_objects_all),
                )
                if is_multi
                else None
            )
            schema_task = progress.add_task("Synchronizing...", total=100)

            for s_idx, schema_meta in enumerate(schemas_meta, 1):
                s_name = schema_meta.schema_name or cfg.schema_name
                schema_total_objs = count_schema_objects(schema_meta, cfg.object_types)
                progress.reset(
                    schema_task,
                    total=schema_total_objs,
                    description=f"Synchronizing [bold yellow]{s_name}[/bold yellow]",
                )

                totals["tables"] += len(schema_meta.tables)
                totals["views"] += len(schema_meta.views)
                totals["mviews"] += len(schema_meta.mviews)
                totals["code_objects"] += len(schema_meta.code_objects)
                totals["triggers"] += len(schema_meta.triggers)
                totals["sequences"] += len(schema_meta.sequences)
                totals["indexes"] += len(schema_meta.indexes)
                totals["synonyms"] += len(schema_meta.synonyms)

                def _on_ann_progress(cat: str, name: str, current: int, total: int, s_title=s_name) -> None:
                    pct = int((current / total) * 100) if total else 100
                    progress.update(
                        schema_task,
                        completed=current,
                        total=total,
                        description=f"Synchronizing [bold yellow]{s_title}[/bold yellow] [[bold cyan]{pct}%[/bold cyan]] ({current:,}/{total:,} objs) [dim]│ {cat} {name}[/dim]",
                    )
                    if overall_task is not None:
                        progress.advance(overall_task, 1)
                    progress.refresh()

                generated_ann = sync_schema_annotations(
                    schema_meta,
                    annotations_path=cfg.annotationsPath,
                    multi_schema=True,
                    object_types=cfg.object_types,
                    progress_callback=_on_ann_progress,
                    storage=storage,
                )
                total_ann += len(generated_ann)

                if overall_task is not None:
                    progress.update(
                        overall_task,
                        description=f"[bold cyan]Overall Synchronization[/bold cyan] ({s_idx}/{len(schemas_meta)} schemas)",
                    )

        elapsed = time.perf_counter() - start_time
        out_paths = {
            "Synchronized YAML Annotations": cfg.annotationsPath,
        }
        if storage:
            out_paths["SeaweedFS Annotations"] = f"{cfg.storage.seaweedfs.bucket}/{cfg.storage.seaweedfs.annotations_prefix}"

        _print_final_summary_panel(
            title="Annotation Synchronization Completed",
            total_schemas=len(schemas_meta),
            totals=totals,
            elapsed_seconds=elapsed,
            output_paths=out_paths,
        )
    except Exception as exc:
        console.print(f"[red]Error during annotation synchronization:[/red] {exc}")
        raise typer.Exit(code=1)


@app.command()
def ask(
    question: str = typer.Argument(..., help="Natural language question about the database"),
    provider: str = typer.Option(
        None, "--provider", "-p", help="AI provider (openai, gemini, anthropic, grok, xai, deepseek, qwen, kimi, ollama)"
    ),
    model: str = typer.Option(None, "--model", "-m", help="AI model name"),
    config: Path = typer.Option(Path("leai.yml"), "--config", "-c", help="Path to leai.yml"),
    seaweed: bool = typer.Option(False, "--seaweed", "-W", help="Load database knowledge from SeaweedFS S3 storage"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Do not write local cache files, operate directly with SeaweedFS"),
) -> None:
    """Interactive AI assistant to answer technical and business questions about the database."""
    from rich.markdown import Markdown

    start_time = time.perf_counter()
    try:
        cfg = load_config(config)
    except ConfigError as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        raise typer.Exit(code=1)

    storage = _resolve_storage(cfg, seaweed)
    is_no_cache = no_cache or cfg.storage.seaweedfs.no_cache
    schemas = load_raw_schemas(cfg.rawPath, storage=storage, local_cache=not is_no_cache)
    if not schemas:
        console.print(f"[red]No snapshot found in '{cfg.rawPath}'. Run 'leai extract' first.[/red]")
        raise typer.Exit(code=1)

    try:
        client = get_llm_client(cfg, provider_override=provider, model_override=model)
    except Exception as exc:
        console.print(f"[red]Error initializing AI client:[/red] {exc}")
        raise typer.Exit(code=1)

    session = ChatSession(schemas=schemas, config=cfg, client=client)
    provider_name = (provider or cfg.ai.default_provider or "openai").upper()
    tools_used = []

    def _on_tool_start(t_name: str, t_args: dict) -> None:
        tools_used.append(t_name)
        args_str = ", ".join(f"{k}={v}" for k, v in t_args.items())
        console.print(f"[dim cyan]  ⚙️ Investigating:[/dim cyan] [bold yellow]{t_name}[/bold yellow]({args_str})")

    try:
        with console.status(
            f"[cyan]Agent analyzing database ([bold yellow]{provider_name}[/bold yellow] • [bold green]{client.model}[/bold green])...[/cyan]",
            spinner="dots",
        ):
            answer, detected_entities = session.send(question, on_tool_start=_on_tool_start)

        elapsed = time.perf_counter() - start_time
        meta_parts = [f"⚡ {elapsed:.2f}s", f"Provider: {provider_name} ({client.model})"]
        if tools_used:
            meta_parts.append(f"Tools: {', '.join(tools_used)}")
        elif detected_entities:
            meta_parts.append(f"RAG: {', '.join(detected_entities)}")

        subtitle_text = f"[dim]{' • '.join(meta_parts)}[/dim]"
        console.print(
            Panel(Markdown(answer), title="[bold green]🤖 LEAI Assistant[/bold green]", subtitle=subtitle_text, border_style="cyan")
        )
    except Exception as exc:
        console.print(f"[red]Error querying AI:[/red] {exc}")
        raise typer.Exit(code=1)


@app.command()
def chat(
    provider: str = typer.Option(
        None, "--provider", "-p", help="AI provider (openai, gemini, anthropic, grok, xai, deepseek, qwen, kimi, ollama)"
    ),
    model: str = typer.Option(None, "--model", "-m", help="AI model name"),
    config: Path = typer.Option(Path("leai.yml"), "--config", "-c", help="Path to leai.yml"),
    seaweed: bool = typer.Option(False, "--seaweed", "-W", help="Load schema knowledge from SeaweedFS S3 storage"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Do not write local cache files, operate directly with SeaweedFS"),
) -> None:
    """Starts an interactive OpenCode-style TUI copilot with RAG, tools and @ mentions."""
    try:
        cfg = load_config(config)
    except ConfigError as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        raise typer.Exit(code=1)

    storage = _resolve_storage(cfg, seaweed)
    is_no_cache = no_cache or cfg.storage.seaweedfs.no_cache
    schemas = load_raw_schemas(cfg.rawPath, storage=storage, local_cache=not is_no_cache)
    if not schemas:
        console.print(f"[red]No snapshot found in '{cfg.rawPath}'. Run 'leai extract' first.[/red]")
        raise typer.Exit(code=1)

    try:
        client = get_llm_client(cfg, provider_override=provider, model_override=model)
    except Exception as exc:
        console.print(f"[red]Error initializing AI client:[/red] {exc}")
        raise typer.Exit(code=1)

    session = InteractiveTUISession(
        schemas=schemas,
        config=cfg,
        client=client,
        provider_name=provider,
    )
    session.run()


@app.command()
def models(
    provider: str = typer.Option(
        None, "--provider", "-p", help="AI provider to query (openai, gemini, anthropic, grok, xai, deepseek, qwen, kimi, ollama)"
    ),
    config: Path = typer.Option(Path("leai.yml"), "--config", "-c", help="Path to leai.yml"),
) -> None:
    """Lists available AI models returned by the provider API for the configured API key."""
    try:
        cfg = load_config(config)
    except ConfigError as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        raise typer.Exit(code=1)

    target_prov = (provider or cfg.ai.default_provider or "openai").lower()
    try:
        client = get_llm_client(cfg, provider_override=target_prov)
        with console.status(
            f"[cyan]Querying [bold yellow]{target_prov.upper()}[/bold yellow] API for available models...[/cyan]", spinner="dots"
        ):
            models_list = client.list_models()
    except Exception as exc:
        console.print(f"[red]Error fetching models for {target_prov.upper()}:[/red] {exc}")
        raise typer.Exit(code=1)

    table = Table(show_header=True, header_style="bold cyan", box=box.ROUNDED)
    table.add_column("Status", justify="center", width=8)
    table.add_column("Model ID", style="bold yellow")
    table.add_column("Display Name", style="white")
    table.add_column("Description / Notes", style="dim")

    for m in models_list:
        m_id = m.get("id", "")
        is_active = m_id == client.model
        status_badge = "[bold green]ACTIVE[/bold green]" if is_active else "[dim]-[/dim]"
        table.add_row(status_badge, m_id, m.get("name", m_id), m.get("description", m.get("note", "")))

    console.print()
    console.print(
        Panel(
            table,
            title=f"[bold cyan]✦ Available Models for {target_prov.upper()} ({len(models_list)} Total)[/bold cyan]",
            box=box.ROUNDED,
            border_style="cyan",
        )
    )
    console.print(
        f"[dim]Tip: Use in chat with [bold cyan]/model {target_prov} <model_id>[/bold cyan] or CLI with [bold cyan]-p {target_prov} -m <model_id>[/bold cyan][/dim]\n"
    )


@app.callback(invoke_without_command=True)
def default(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        callback=_version_callback,
        is_eager=True,
        help="Show LEAI version and exit.",
    ),
    provider: str = typer.Option(
        None, "--provider", "-p", help="AI provider (openai, gemini, anthropic, grok, xai, deepseek, qwen, kimi, ollama)"
    ),
    model: str = typer.Option(None, "--model", "-m", help="AI model name"),
    config: Path = typer.Option(Path("leai.yml"), "--config", "-c", help="Path to leai.yml"),
    schemas: list[str] = typer.Option(None, "--schema", "--schemas", "-s", help="Oracle schema name(s) to target (overrides leai.yml)"),
) -> None:
    """LEAI: Autonomous Oracle Database Intelligence, Documentation Engine & Copilot."""
    if hasattr(config, "default") or not isinstance(config, (str, Path)):
        config = getattr(config, "default", Path("leai.yml")) or Path("leai.yml")
    if not isinstance(config, Path):
        config = Path(config)
    if hasattr(schemas, "default"):
        schemas = getattr(schemas, "default", None)
    if hasattr(provider, "default"):
        provider = getattr(provider, "default", None)
    if hasattr(model, "default"):
        model = getattr(model, "default", None)

    if ctx.invoked_subcommand is None:
        try:
            cfg = load_config(config)
            if schemas:
                cfg.schemas = [s.strip().upper() for s in schemas]
        except Exception as exc:
            if config.exists():
                console.print(f"[bold yellow]⚠️ Warning:[/bold yellow] Failed to load [cyan]{config}[/cyan]: {exc}")
            cfg = LeaiConfig()

        target_schemas = cfg.schemas if not cfg.is_all_schemas else None
        schemas_meta = load_raw_schemas(cfg.rawPath, target_schemas=target_schemas)
        try:
            client = get_llm_client(cfg, provider_override=provider, model_override=model)
        except Exception:
            client = None

        session = InteractiveTUISession(
            schemas=schemas_meta,
            config=cfg,
            client=client,
            provider_name=provider,
        )
        session.run()


@app.command()
def doc(
    object_name: str = typer.Argument(None, help="Name of the database object to document (e.g. EMPLOYEES, PKG_FIN)"),
    config: Path = typer.Option(Path("leai.yml"), "--config", "-c", help="Path to leai.yml"),
    seaweed: bool = typer.Option(False, "--seaweed", "-W", help="Load snapshots from SeaweedFS S3 storage"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Do not write local cache files, operate directly with SeaweedFS"),
) -> None:
    """Interactive in-terminal documentation and annotation editor."""
    try:
        cfg = load_config(config)
    except ConfigError as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        raise typer.Exit(code=1)

    storage = _resolve_storage(cfg, seaweed)
    is_no_cache = no_cache or cfg.storage.seaweedfs.no_cache
    target_schemas = cfg.schemas if not cfg.is_all_schemas else None
    schemas_meta = load_raw_schemas(cfg.rawPath, target_schemas=target_schemas, storage=storage, local_cache=not is_no_cache)
    if not schemas_meta:
        console.print(f"[yellow]No snapshots found in '{cfg.rawPath}'. Run 'leai extract' first.[/yellow]")
        raise typer.Exit(code=1)

    editor = DocEditor(cfg, schemas_meta)
    editor.run(object_name)


@app.command()
def compile(
    config: Path = typer.Option(Path("leai.yml"), "--config", "-c", help="Path to leai.yml"),
    object_name: str = typer.Option(None, "--object-name", "-o", help="Specific database object name to compile (e.g. EMPLOYEES)"),
    schemas: list[str] = typer.Option(None, "--schema", "--schemas", "-s", help="Oracle schema name(s) to compile (overrides leai.yml)"),
    object_types: list[str] = typer.Option(None, "--object-type", "-t", help="Object types to compile (e.g. tables, views, procedures)"),
    with_traces: bool = typer.Option(True, "--with-traces/--no-traces", help="Include dependency lineage, risk analysis and Mermaid graph"),
    rag_json: bool = typer.Option(False, "--rag-json", "--rag", help="Also export structured JSON chunks to docs/chunks/ for Vector DB"),
    depth: int = typer.Option(1, "--depth", "-d", help="Max dependency graph traversal depth (default: 1)"),
    seaweed: bool = typer.Option(False, "--seaweed", "-W", help="Compile docs using schemas and annotations from SeaweedFS S3 storage"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Do not write local cache files, operate directly with SeaweedFS"),
) -> None:
    """Compiles Markdown docs in docPath merging rawPath + annotationsPath (Offline)."""
    try:
        depth = int(getattr(depth, "default", depth))
    except Exception:
        depth = 1
    if hasattr(with_traces, "default"):
        with_traces = bool(getattr(with_traces, "default", True))
    if hasattr(rag_json, "default"):
        rag_json = bool(getattr(rag_json, "default", False))
    if hasattr(config, "default") or not isinstance(config, (str, Path)):
        config = getattr(config, "default", Path("leai.yml")) or Path("leai.yml")
    if not isinstance(config, Path):
        config = Path(config)
    if hasattr(object_types, "default"):
        object_types = getattr(object_types, "default", None)
    if hasattr(schemas, "default"):
        schemas = getattr(schemas, "default", None)
    if hasattr(object_name, "default"):
        object_name = getattr(object_name, "default", None)
    if object_name:
        object_name = str(object_name).strip()

    start_time = time.perf_counter()
    try:
        cfg = load_config(config)
        if schemas:
            cfg.schemas = [s.strip().upper() for s in schemas]
        if object_types:
            cfg.object_types = [t.lower() for t in object_types]
    except ConfigError as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        raise typer.Exit(code=1)

    storage = _resolve_storage(cfg, seaweed)
    is_no_cache = no_cache or cfg.storage.seaweedfs.no_cache
    if is_no_cache and not storage:
        console.print("[red]Error:[/red] --no-cache requires SeaweedFS to be enabled (use --seaweed or enable it in leai.yml).")
        raise typer.Exit(code=1)

    try:
        source_desc = f"SeaweedFS ({cfg.storage.seaweedfs.bucket})" if (storage and is_no_cache) else str(cfg.rawPath)
        console.print(f"[cyan]Loading snapshots from[/cyan] [bold]{source_desc}[/bold]...\n")
        target_schemas = cfg.schemas if not cfg.is_all_schemas else None
        schemas_meta = load_raw_schemas(cfg.rawPath, target_schemas=target_schemas, storage=storage, local_cache=not is_no_cache)

        if object_name:
            clean_obj = object_name.strip().upper()
            target_schemas_list = []
            if "." in clean_obj:
                s_part, o_part = clean_obj.split(".", 1)
                for s in schemas_meta:
                    if (s.schema_name or "").upper() == s_part:
                        target_schemas_list.append(s)
            if not target_schemas_list:
                for s in schemas_meta:
                    if (
                        any(t.name.upper() == clean_obj for t in s.tables)
                        or any(v.name.upper() == clean_obj for v in s.views)
                        or any(mv.name.upper() == clean_obj for mv in s.mviews)
                        or any(
                            co.name.upper() == clean_obj
                            or any(
                                sub.name.upper() == clean_obj or f"{co.name.upper()}.{sub.name.upper()}" == clean_obj
                                for sub in co.subprograms
                            )
                            for co in s.code_objects
                        )
                        or any(tr.name.upper() == clean_obj for tr in s.triggers)
                        or any(sq.name.upper() == clean_obj for sq in s.sequences)
                        or any(idx.name.upper() == clean_obj for idx in s.indexes)
                        or any(sn.name.upper() == clean_obj for sn in s.synonyms)
                    ):
                        target_schemas_list.append(s)
            if target_schemas_list:
                schemas_meta = target_schemas_list
            else:
                avail_str = ", ".join(s.schema_name for s in schemas_meta)
                console.print(
                    f"[yellow]! Object '[bold cyan]{object_name}[/bold cyan]' was not found in loaded snapshots ({avail_str}).[/yellow]"
                )
                raise typer.Exit(code=1)

        is_multi = len(schemas_meta) > 1

        totals = {
            "tables": 0,
            "views": 0,
            "mviews": 0,
            "code_objects": 0,
            "triggers": 0,
            "sequences": 0,
            "indexes": 0,
            "synonyms": 0,
        }
        total_md = 0
        total_ann = 0
        total_objects_all = 1 if object_name else sum(count_schema_objects(s, cfg.object_types) for s in schemas_meta)

        with _create_progress_bar() as progress:
            overall_task = (
                progress.add_task(
                    f"[bold cyan]Overall Compilation[/bold cyan] (0/{len(schemas_meta)} schemas)",
                    total=max(1, total_objects_all),
                )
                if is_multi and not object_name
                else None
            )
            schema_task = progress.add_task("Compiling...", total=100)

            for s_idx, schema_meta in enumerate(schemas_meta, 1):
                s_name = schema_meta.schema_name or cfg.schema_name
                schema_total_objs = count_schema_objects(schema_meta, cfg.object_types)
                progress.reset(
                    schema_task,
                    total=schema_total_objs,
                    description=f"Compiling [bold yellow]{s_name}[/bold yellow]",
                )

                totals["tables"] += len(schema_meta.tables)
                totals["views"] += len(schema_meta.views)
                totals["mviews"] += len(schema_meta.mviews)
                totals["code_objects"] += len(schema_meta.code_objects)
                totals["triggers"] += len(schema_meta.triggers)
                totals["sequences"] += len(schema_meta.sequences)
                totals["indexes"] += len(schema_meta.indexes)
                totals["synonyms"] += len(schema_meta.synonyms)

                def _on_comp_progress(cat: str, name: str, current: int, total: int, s_title=s_name) -> None:
                    pct = int((current / total) * 100) if total else 100
                    progress.update(
                        schema_task,
                        completed=current,
                        total=total,
                        description=f"Compiling [bold yellow]{s_title}[/bold yellow] [[bold cyan]{pct}%[/bold cyan]] ({current:,}/{total:,} objs) [dim]│ {cat} {name}[/dim]",
                    )
                    if overall_task is not None:
                        progress.advance(overall_task, 1)
                    progress.refresh()

                generated_md, generated_ann = write_schema_docs(
                    schema_meta,
                    doc_path=cfg.docPath,
                    annotations_path=cfg.annotationsPath,
                    docs_overrides=cfg.docs,
                    multi_schema=True,
                    object_types=cfg.object_types,
                    all_schemas=schemas_meta,
                    with_traces=with_traces,
                    max_depth=depth,
                    generate_rag_chunks=rag_json,
                    progress_callback=_on_comp_progress,
                    target_object=object_name,
                )
                total_md += len(generated_md)
                total_ann += len(generated_ann)

                if overall_task is not None:
                    progress.update(
                        overall_task,
                        description=f"[bold cyan]Overall Compilation[/bold cyan] ({s_idx}/{len(schemas_meta)} schemas)",
                    )

        elapsed = time.perf_counter() - start_time
        out_paths = {
            "Markdown Documents": cfg.docPath,
            "Synchronized YAML Annotations": cfg.annotationsPath,
        }
        if rag_json:
            out_paths["RAG Vector Chunks"] = cfg.docPath / "chunks"
        _print_final_summary_panel(
            title="Markdown Compilation Completed",
            total_schemas=len(schemas_meta),
            totals=totals,
            elapsed_seconds=elapsed,
            output_paths=out_paths,
        )
    except Exception as exc:
        console.print(f"[red]Error during compilation:[/red] {exc}")
        raise typer.Exit(code=1)


@app.command()
def generate(
    config: Path = typer.Option(Path("leai.yml"), "--config", "-c", help="Path to leai.yml"),
    schemas: list[str] = typer.Option(None, "--schema", "--schemas", "-s", help="Oracle schema name(s) to generate (overrides leai.yml)"),
    object_types: list[str] = typer.Option(None, "--object-type", "-t", help="Object types to generate (e.g. tables, views, procedures)"),
    with_traces: bool = typer.Option(True, "--with-traces/--no-traces", help="Include dependency lineage, risk analysis and Mermaid graph"),
    rag_json: bool = typer.Option(False, "--rag-json", "--rag", help="Also export structured JSON chunks to docs/chunks/ for Vector DB"),
    depth: int = typer.Option(1, "--depth", "-d", help="Max dependency graph traversal depth (default: 1)"),
    seaweed: bool = typer.Option(False, "--seaweed", "-W", help="Store RAW snapshots and annotations in SeaweedFS S3 storage"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Do not write local files in rawPath, send only to SeaweedFS"),
    force_upload: bool = typer.Option(
        False, "--force-upload", "-F", help="Force upload of all objects to SeaweedFS (bypasses SHA-256 manifest)"
    ),
) -> None:
    """Generates complete documentation (Extracts RAW -> Syncs Annotations -> Compiles Markdown)."""
    try:
        depth = int(getattr(depth, "default", depth))
    except Exception:
        depth = 1
    if hasattr(with_traces, "default"):
        with_traces = bool(getattr(with_traces, "default", True))
    if hasattr(rag_json, "default"):
        rag_json = bool(getattr(rag_json, "default", False))
    if hasattr(config, "default") or not isinstance(config, (str, Path)):
        config = getattr(config, "default", Path("leai.yml")) or Path("leai.yml")
    if not isinstance(config, Path):
        config = Path(config)
    if hasattr(object_types, "default"):
        object_types = getattr(object_types, "default", None)
    if hasattr(schemas, "default"):
        schemas = getattr(schemas, "default", None)

    start_time = time.perf_counter()
    try:
        cfg = load_config(config)
        if schemas:
            cfg.schemas = [s.strip().upper() for s in schemas]
        if object_types:
            cfg.object_types = [t.lower() for t in object_types]
    except ConfigError as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        raise typer.Exit(code=1)

    storage = _resolve_storage(cfg, seaweed)
    is_no_cache = no_cache or cfg.storage.seaweedfs.no_cache
    if is_no_cache and not storage:
        console.print("[red]Error:[/red] --no-cache requires SeaweedFS to be enabled (use --seaweed or enable it in leai.yml).")
        raise typer.Exit(code=1)

    if storage:
        try:
            storage.ensure_bucket_exists()
            remote_tag = " [dim](Remote-only / No local cache)[/dim]" if is_no_cache else ""
            console.print(
                f"[cyan]SeaweedFS Storage:[/cyan] [bold green]Active[/bold green] (Endpoint: {cfg.storage.seaweedfs.endpoint_url}, Bucket: {cfg.storage.seaweedfs.bucket}){remote_tag}\n"
            )
        except Exception as exc:
            console.print(f"[red]SeaweedFS error:[/red] {exc}")
            raise typer.Exit(code=1)

    try:
        connection = oracledb.connect(**_build_connect_kwargs(cfg.dsn))
        try:
            target_schemas = fetch_available_schemas(connection, cfg)

            is_multi = len(target_schemas) > 1 or cfg.is_all_schemas
            console.print(
                f"[cyan]Schemas to process:[/cyan] [bold]{', '.join(target_schemas[:10])}{'...' if len(target_schemas) > 10 else ''}[/bold] (Total: {len(target_schemas)})\n"
            )

            totals = {
                "tables": 0,
                "views": 0,
                "mviews": 0,
                "code_objects": 0,
                "triggers": 0,
                "sequences": 0,
                "indexes": 0,
                "synonyms": 0,
            }
            total_md = 0
            total_ann = 0
            all_schemas_meta: list[SchemaMetadata] = []

            with _create_progress_bar() as progress:
                overall_task = (
                    progress.add_task(
                        f"[bold cyan]Overall Pipeline[/bold cyan] (0/{len(target_schemas)} schemas)",
                        total=len(target_schemas),
                    )
                    if is_multi
                    else None
                )
                schema_task = progress.add_task("Processing...", total=100)

                for s_idx, schema_name in enumerate(target_schemas, 1):
                    schema_obj_count = [0]
                    progress.reset(
                        schema_task,
                        total=100,
                        description=f"Processing [bold yellow]{schema_name}[/bold yellow]",
                    )
                    progress.refresh()

                    def _cb(cat: str, count: int, step_idx: int, total_steps: int, s_name=schema_name) -> None:
                        if count > 0:
                            schema_obj_count[0] += count
                        pct = int((step_idx / total_steps) * 100) if total_steps else 100
                        progress.update(
                            schema_task,
                            completed=pct,
                            total=100,
                            description=f"Extracting [bold yellow]{s_name}[/bold yellow] [[bold cyan]{pct}%[/bold cyan]] ({schema_obj_count[0]:,} objects) [dim]│ {cat}[/dim]",
                        )
                        progress.refresh()

                    schema_meta = fetch_schema_metadata(cfg, schema_name=schema_name, callback=_cb, connection=connection)
                    all_schemas_meta.append(schema_meta)

                    totals["tables"] += len(schema_meta.tables)
                    totals["views"] += len(schema_meta.views)
                    totals["mviews"] += len(schema_meta.mviews)
                    totals["code_objects"] += len(schema_meta.code_objects)
                    totals["triggers"] += len(schema_meta.triggers)
                    totals["sequences"] += len(schema_meta.sequences)
                    totals["indexes"] += len(schema_meta.indexes)
                    totals["synonyms"] += len(schema_meta.synonyms)

                    # 1. Save RAW Snapshot
                    save_raw_schema(
                        schema_meta,
                        cfg.rawPath,
                        multi_schema=True,
                        storage=storage,
                        local_cache=not is_no_cache,
                        force_upload=force_upload,
                    )

                    # 2 & 3. Sync Annotations and Compile Docs with granular object progress
                    schema_total_objs = count_schema_objects(schema_meta, cfg.object_types)
                    progress.reset(
                        schema_task,
                        total=schema_total_objs,
                        description=f"Compiling [bold yellow]{schema_name}[/bold yellow]",
                    )

                    def _on_gen_progress(cat: str, name: str, current: int, total: int, s_title=schema_name) -> None:
                        pct = int((current / total) * 100) if total else 100
                        progress.update(
                            schema_task,
                            completed=pct,
                            total=total,
                            description=f"Compiling [bold yellow]{s_title}[/bold yellow] [[bold cyan]{pct}%[/bold cyan]] ({current:,}/{total:,} objs) [dim]│ {cat} {name}[/dim]",
                        )
                        progress.refresh()

                    generated_md, generated_ann = write_schema_docs(
                        schema_meta,
                        doc_path=cfg.docPath,
                        annotations_path=cfg.annotationsPath,
                        docs_overrides=cfg.docs,
                        multi_schema=True,
                        object_types=cfg.object_types,
                        all_schemas=all_schemas_meta,
                        with_traces=with_traces,
                        max_depth=depth,
                        generate_rag_chunks=rag_json,
                        progress_callback=_on_gen_progress,
                    )
                    total_md += len(generated_md)
                    total_ann += len(generated_ann)

                    if overall_task is not None:
                        progress.advance(overall_task, 1)
                        progress.update(
                            overall_task,
                            description=f"[bold cyan]Overall Pipeline[/bold cyan] ({s_idx}/{len(target_schemas)} schemas)",
                        )
        finally:
            connection.close()

        if storage:
            storage.push_local_to_remote(local_raw_path=cfg.rawPath, local_annotations_path=cfg.annotationsPath)

        elapsed = time.perf_counter() - start_time
        out_paths = {}
        if not is_no_cache:
            out_paths["RAW Snapshot"] = cfg.rawPath
        out_paths["Markdown Documents"] = cfg.docPath
        out_paths["Synchronized YAML Annotations"] = cfg.annotationsPath
        if storage:
            out_paths["SeaweedFS Storage"] = f"{cfg.storage.seaweedfs.bucket}"
        if is_no_cache:
            out_paths["Local Disk Cache"] = "[yellow]Disabled (Remote-only)[/yellow]"
        if rag_json:
            out_paths["RAG Vector Chunks"] = cfg.docPath / "chunks"
        _print_final_summary_panel(
            title="Documentation Generation Completed",
            total_schemas=len(target_schemas),
            totals=totals,
            elapsed_seconds=elapsed,
            output_paths=out_paths,
        )
    except Exception as exc:
        console.print(f"[red]Error during execution:[/red] {exc}")
        raise typer.Exit(code=1)


@app.command()
def changes(
    config: Path = typer.Option(Path("leai.yml"), "--config", "-c", help="Path to leai.yml"),
    days: int = typer.Option(7, "--days", "-d", help="Filter objects modified in the last N days"),
    user: str = typer.Option(None, "--user", "-u", help="Filter by modifying user or schema"),
    seaweed: bool = typer.Option(False, "--seaweed", "-W", help="Load schemas from SeaweedFS S3 storage"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Do not write local cache files, operate directly with SeaweedFS"),
) -> None:
    """Tracks and displays database objects modified in the last N days."""
    from datetime import datetime, timedelta

    try:
        cfg = load_config(config)
    except ConfigError as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        raise typer.Exit(code=1)

    storage = _resolve_storage(cfg, seaweed)
    is_no_cache = no_cache or cfg.storage.seaweedfs.no_cache
    try:
        target_schemas = cfg.schemas if not cfg.is_all_schemas else None
        schemas_meta = load_raw_schemas(cfg.rawPath, target_schemas=target_schemas, storage=storage, local_cache=not is_no_cache)
        cutoff = datetime.now() - timedelta(days=days)
        results = []

        for schema_meta in schemas_meta:
            s_name = schema_meta.schema_name or cfg.schema_name
            categories = [
                ("Table", schema_meta.tables),
                ("View", schema_meta.views),
                ("Materialized View", schema_meta.mviews),
                ("Code Object", schema_meta.code_objects),
                ("Trigger", schema_meta.triggers),
                ("Sequence", schema_meta.sequences),
                ("Index", schema_meta.indexes),
                ("Synonym", schema_meta.synonyms),
            ]

            for cat_label, obj_list in categories:
                for obj in obj_list:
                    ddl_str = getattr(obj, "last_ddl_time", None)
                    mod_by = getattr(obj, "last_modified_by", None) or s_name
                    if user and user.upper() not in (mod_by.upper(), s_name.upper()):
                        continue

                    if ddl_str:
                        dt = None
                        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
                            try:
                                dt = datetime.strptime(ddl_str, fmt)
                                break
                            except ValueError:
                                pass
                        if dt and dt >= cutoff:
                            results.append((s_name, cat_label, obj.name, ddl_str, mod_by))

        if not results:
            user_filter_str = f" | User: {user}" if user else ""
            console.print(
                Panel(
                    f"[yellow]No database objects were modified in the last {days} days.[/yellow]\n"
                    f"[dim]Applied filters: Days={days}{user_filter_str}[/dim]",
                    title="[bold green]DDL Changes Tracking[/bold green]",
                    border_style="yellow",
                )
            )
            return

        table = Table(show_header=True, header_style="bold cyan", box=None)
        table.add_column("Schema", style="bold yellow")
        table.add_column("Category", style="dim")
        table.add_column("Object Name", style="bold white")
        table.add_column("Last DDL", style="bold green")
        table.add_column("Modified By", style="magenta")

        for row in sorted(results, key=lambda x: x[3], reverse=True):
            table.add_row(*row)

        user_filter_str = f" | User: {user}" if user else ""
        header_text = f"Objects Modified in the Last {days} Days ({len(results)} Found){user_filter_str}"

        console.print()
        console.print(Panel(table, title=f"[bold green]{header_text}[/bold green]", border_style="green"))
    except Exception as exc:
        console.print(f"[red]Error tracking changes:[/red] {exc}")
        raise typer.Exit(code=1)


@app.command()
def trace(
    object_name: str = typer.Argument(..., help="Name of focal object to trace and document (e.g. EMPLOYEES)"),
    depth: int = typer.Option(1, "--depth", "-d", help="Maximum search depth in dependency graph"),
    rag_json: bool = typer.Option(False, "--rag-json", "--rag", help="Also generate structured JSON chunk for Vector DB / RAG ingestion"),
    config: Path = typer.Option(Path("leai.yml"), "--config", "-c", help="Path to leai.yml"),
    schema: str = typer.Option(None, "--schema", "-s", help="Specific schema (if different from leai.yml)"),
    offline: bool = typer.Option(False, "--offline", help="Force dependency resolution from RAW snapshot instead of database"),
    output: Path = typer.Option(None, "--output", "-o", help="Path for output Markdown file"),
    seaweed: bool = typer.Option(False, "--seaweed", "-W", help="Load schemas from SeaweedFS S3 storage"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Do not write local cache files, operate directly with SeaweedFS"),
) -> None:
    """Generates in-depth technical dossier and Mermaid.js dependency graph for a specific object."""
    from rich.tree import Tree

    try:
        depth = int(getattr(depth, "default", depth))
    except Exception:
        depth = 1
    if hasattr(offline, "default"):
        offline = bool(getattr(offline, "default", False))
    if hasattr(rag_json, "default"):
        rag_json = bool(getattr(rag_json, "default", False))
    if hasattr(config, "default") or not isinstance(config, (str, Path)):
        config = getattr(config, "default", Path("leai.yml")) or Path("leai.yml")
    if not isinstance(config, Path):
        config = Path(config)

    start_time = time.perf_counter()
    try:
        cfg = load_config(config)
    except ConfigError as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        raise typer.Exit(code=1)

    target_obj = object_name.strip().upper()
    storage = _resolve_storage(cfg, seaweed)
    is_no_cache = no_cache or cfg.storage.seaweedfs.no_cache

    try:
        if offline or not cfg.dsn:
            console.print(
                f"\n[dim]🔍 Offline Mode: Tracing dependencies for [bold yellow]{target_obj}[/bold yellow] (Depth: {depth})...[/dim]"
            )
            trace_target_schemas = [schema.strip().upper()] if schema else (cfg.schemas if not cfg.is_all_schemas else None)
            schemas_meta = load_raw_schemas(cfg.rawPath, target_schemas=trace_target_schemas, storage=storage, local_cache=not is_no_cache)
            if not schemas_meta:
                console.print(f"[red]No snapshot found in '{cfg.rawPath}'. Run 'leai extract' first.[/red]")
                raise typer.Exit(code=1)
            trace_res = trace_raw_dependencies(schemas_meta, target_obj, max_depth=depth)
        else:
            try:
                console.print(
                    f"\n[dim]🌐 Querying real-time dependency catalog in Oracle for [bold yellow]{target_obj}[/bold yellow]...[/dim]"
                )
                trace_res = fetch_focal_trace(cfg, target_obj, schema_name=schema, max_depth=depth)
            except Exception as live_exc:
                console.print(f"[yellow]Warning: online connection failed ({live_exc}). Falling back to local RAW snapshot...[/yellow]")
                trace_target_schemas = [schema.strip().upper()] if schema else (cfg.schemas if not cfg.is_all_schemas else None)
                schemas_meta = load_raw_schemas(
                    cfg.rawPath, target_schemas=trace_target_schemas, storage=storage, local_cache=not is_no_cache
                )
                if not schemas_meta:
                    raise live_exc
                trace_res = trace_raw_dependencies(schemas_meta, target_obj, max_depth=depth)

        if not trace_res.focal_object and trace_res.focal_type == "UNKNOWN":
            console.print(f"[red]Object '{target_obj}' was not found in catalog or RAW snapshot.[/red]")
            raise typer.Exit(code=1)

        # 1. Impact X-Ray Summary Panel
        risk_level = _calculate_risk_level(len(trace_res.dependencies))
        risk_color = "red" if risk_level == "CRITICAL" else ("yellow" if risk_level in ("HIGH", "MEDIUM") else "green")

        target_schema = schema or getattr(trace_res.focal_object, "schema_name", None) or cfg.schema_name or "DEFAULT"
        console.print(
            Panel(
                f"[bold]Focal Object:[/bold] [bold yellow]{target_obj}[/bold yellow] • [bold]Type:[/bold] `{trace_res.focal_type}` • [bold]Schema:[/bold] `{target_schema}`\n"
                f"[bold]Change Risk Level:[/bold] [{risk_color}]{risk_level}[/{risk_color}] ([bold]{len(trace_res.dependencies)}[/bold] connections mapped at depth {depth})",
                title="[bold cyan]🔍 Impact X-Ray & Technical Lineage[/bold cyan]",
                border_style="cyan",
            )
        )

        # 2. Render Hierarchical Tree in Terminal
        if trace_res.dependencies:
            tree = Tree(f"[bold yellow]⭐ {target_obj}[/bold yellow] [dim]({trace_res.focal_type})[/dim]")
            by_depth: dict[int, list] = {}
            for dep in trace_res.dependencies:
                by_depth.setdefault(dep.depth, []).append(dep)

            for d_level in sorted(by_depth.keys()):
                level_branch = tree.add(f"[bold cyan]Level {d_level}[/bold cyan] [dim]({'Direct' if d_level == 1 else 'Indirect'})[/dim]")
                for dep in by_depth[d_level]:
                    icon = (
                        "📊"
                        if dep.source_type == "TABLE" or dep.target_type == "TABLE"
                        else ("👁️" if "VIEW" in dep.source_type else ("⚡" if dep.source_type == "TRIGGER" else "⚙️"))
                    )
                    label = f"{icon} [bold]{dep.source_name}[/bold] [dim]({dep.relation_type} -> {dep.target_name})[/dim]"
                    if dep.details:
                        label += f" [dim italic]- {dep.details}[/dim italic]"
                    level_branch.add(label)

            console.print(tree)
            console.print("")

        # 3. Determine output path and save Dossier
        doc_dir = cfg.docPath / target_schema if (cfg.is_all_schemas and target_schema) else cfg.docPath
        out_file = output or (doc_dir / "dossiers" / f"{target_obj}.md")
        written_path = write_dossier_doc(trace_res, out_file, annotations_path=cfg.annotationsPath)

        if rag_json:
            json_file = doc_dir / "chunks" / f"{target_obj}.json"
            written_json = write_rag_json_file(trace_res, json_file, annotations_path=cfg.annotationsPath)
            console.print(f"[green]✓ RAG JSON chunk generated at:[/green] [bold cyan]{written_json}[/bold cyan]")

        elapsed = time.perf_counter() - start_time
        console.print(
            f"[green]✓ Markdown Dossier with Mermaid generated at:[/green] [bold cyan]{written_path}[/bold cyan] [dim]({elapsed:.2f}s)[/dim]\n"
        )

    except typer.Exit:
        raise
    except Exception as exc:
        console.print(f"[red]Error executing focal trace:[/red] {exc}")
        raise typer.Exit(code=1)


@app.command()
def enrich(
    object_name: str = typer.Option(None, "--object-name", "-o", help="Specific object name to enrich (optional)"),
    provider: str = typer.Option(
        None, "--provider", "-p", help="AI provider (openai, gemini, anthropic, grok, xai, deepseek, qwen, kimi, ollama)"
    ),
    model: str = typer.Option(None, "--model", "-m", help="AI model name (e.g. gpt-4o, gemini-1.5-flash, claude-3-5-sonnet)"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Force overwrite existing descriptions and comments"),
    schemas: list[str] = typer.Option(None, "--schema", "--schemas", "-s", help="Oracle schema name(s) to enrich (overrides leai.yml)"),
    object_types: list[str] = typer.Option(None, "--object-type", "-t", help="Object types to enrich (e.g. tables, packages)"),
    config: Path = typer.Option(Path("leai.yml"), "--config", "-c", help="Path to leai.yml"),
    seaweed: bool = typer.Option(False, "--seaweed", "-W", help="Load and update annotations on SeaweedFS S3 storage"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Do not write local cache files, operate directly with SeaweedFS"),
) -> None:
    """Uses AI (LLMs) to automatically populate and enrich business annotations in YAML."""
    start_time = time.perf_counter()
    try:
        cfg = load_config(config)
        if schemas:
            cfg.schemas = [s.strip().upper() for s in schemas]
    except ConfigError as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        raise typer.Exit(code=1)

    storage = _resolve_storage(cfg, seaweed)
    is_no_cache = no_cache or cfg.storage.seaweedfs.no_cache
    target_schemas = cfg.schemas if not cfg.is_all_schemas else None
    schemas_meta = load_raw_schemas(cfg.rawPath, target_schemas=target_schemas, storage=storage, local_cache=not is_no_cache)
    if not schemas_meta:
        console.print(f"[red]No snapshot found in '{cfg.rawPath}'. Run 'leai extract' first.[/red]")
        raise typer.Exit(code=1)

    try:
        client = get_llm_client(cfg, provider_override=provider, model_override=model)
    except Exception as exc:
        console.print(f"[red]Error initializing AI client:[/red] {exc}")
        raise typer.Exit(code=1)

    provider_label = (provider or cfg.ai.default_provider or "openai").upper()

    # Count total eligible objects for the progress bar
    types_filter = [t.lower().rstrip("s") for t in (object_types or cfg.object_types)]
    target_upper = object_name.strip().upper() if object_name else None
    total_eligible = 0

    for s in schemas_meta:
        if "table" in types_filter or not object_types:
            total_eligible += sum(1 for t in s.tables if not target_upper or t.name.upper() == target_upper)
        if any(t in types_filter for t in ("procedure", "function", "package", "type", "code_object")) or not object_types:
            total_eligible += sum(1 for co in s.code_objects if not target_upper or co.name.upper() == target_upper)

    console.print(
        Panel(
            f"[bold]AI Provider:[/bold] [bold yellow]{provider_label}[/bold yellow] • [bold]Model:[/bold] [bold green]{client.model}[/bold green]\n"
            f"[bold]Operation Mode:[/bold] {'[bold red]Force Overwrite (--overwrite)[/bold red]' if overwrite else '[bold green]Preserve Existing Documentation[/bold green]'}\n"
            f"[bold]Eligible Objects:[/bold] {total_eligible} items found in `{cfg.rawPath}`",
            title="[bold cyan]🤖 LEAI AI Auto-Enrichment Studio[/bold cyan]",
            border_style="cyan",
        )
    )

    try:
        with _create_progress_bar() as progress:
            task = progress.add_task("[cyan]Enriching metadata...", total=total_eligible)

            def _on_progress(obj_type: str, obj_name: str):
                progress.update(task, advance=1, description=f"[cyan]Analyzing {obj_type} [bold yellow]{obj_name}[/bold yellow]...")

            tables_done, code_done = enrich_schema_annotations(
                schemas=schemas_meta,
                config=cfg,
                client=client,
                overwrite=overwrite,
                target_object_name=object_name,
                target_object_types=object_types,
                progress_callback=_on_progress,
            )

        if storage:
            with console.status("[cyan]Uploading enriched annotations to SeaweedFS...[/cyan]"):
                pushed = storage.push_local_to_remote(local_raw_path=cfg.rawPath, local_annotations_path=cfg.annotationsPath)
                console.print(f"[green]✓ Uploaded {pushed['annotations']} enriched annotations to SeaweedFS![/green]")

        elapsed = time.perf_counter() - start_time
        console.print(
            Panel(
                f"[green]✓ {tables_done} Tables[/green] annotated with business descriptions and column comments\n"
                f"[green]✓ {code_done} Packages/Procedures[/green] enriched with inferred rules\n"
                f"[bold]Total Time:[/bold] {elapsed:.2f}s • [bold]Destination:[/bold] [bold cyan]{cfg.annotationsPath}[/bold cyan]\n\n"
                f"[dim]Tip: Run [bold cyan]leai compile[/bold cyan] to update Markdowns in docs/ with the new annotations.[/dim]",
                title="[bold green]Enrichment Summary Completed[/bold green]",
                border_style="green",
            )
        )
    except Exception as exc:
        console.print(f"[red]Error during enrichment:[/red] {exc}")
        raise typer.Exit(code=1)


@app.command()
def serve(
    port: int = typer.Option(8000, "--port", "-p", help="Port to bind LEAI Web Studio"),
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host address to bind"),
    open_browser: bool = typer.Option(True, "--open/--no-open", help="Automatically open default browser"),
    config: Path = typer.Option(Path("leai.yml"), "--config", "-c", help="Path to leai.yml"),
    provider: str = typer.Option(None, "--provider", help="AI provider override"),
) -> None:
    """Launch interactive LEAI Web Documentation & Annotation Studio in the browser."""
    try:
        cfg = load_config(config)
    except Exception as exc:
        if config.exists():
            console.print(f"[bold yellow]⚠️ Aviso:[/bold yellow] Falha ao ler [cyan]{config}[/cyan]: {exc}")
        cfg = LeaiConfig()

    schemas_meta = load_raw_schemas(cfg.rawPath)
    try:
        client = get_llm_client(cfg, provider_override=provider)
    except Exception:
        client = None

    url = f"http://{host}:{port}"

    console.print()
    console.print(
        Panel(
            f"[bold cyan]⚡ LEAI Web Documentation & Annotation Studio[/bold cyan]\n\n"
            f"[bold white]URL:[/bold white] [bold yellow underline]{url}[/bold yellow underline]\n"
            f"[bold white]Schemas Loaded:[/bold white] [cyan]{len(schemas_meta)}[/cyan] schemas\n"
            f"[bold white]AI Model:[/bold white] [bold green]{client.model if client else 'Offline'}[/bold green]\n\n"
            f"[dim]Features: In-browser annotation editing, instant Markdown sync, AI auto-enrichment, lineage graphs.[/dim]\n"
            f"[dim]Press [bold red]Ctrl+C[/bold red] to stop server.[/dim]",
            title="[bold green]🌐 Web Studio Running[/bold green]",
            box=box.ROUNDED,
            border_style="green",
        )
    )

    from leai.web import start_server

    start_server(
        config=cfg,
        schemas=schemas_meta,
        client=client,
        provider_name=provider,
        host=host,
        port=port,
        open_browser=open_browser,
        in_background=False,
        config_path=config,
        initial_path="/",
    )


# ==============================================================================
# SUBAGENTS CLI SUB-COMMANDS (`leai agent`)
# ==============================================================================
agent_app = typer.Typer(help="Execute specialized autonomous subagents directly.")
app.add_typer(agent_app, name="agent")


@agent_app.command("list")
def list_agents_command() -> None:
    """List all available specialized subagents and their capabilities."""
    from leai.ai.subagents import list_registered_subagents

    agents = list_registered_subagents()
    table = Table(
        title="[bold cyan]⚡ LEAI Specialized Subagents Registry[/bold cyan]",
        box=box.ROUNDED,
        header_style="bold magenta",
    )
    table.add_column("Role / Command ID", style="bold yellow")
    table.add_column("Specialist Name", style="bold white")
    table.add_column("Description", style="dim")
    table.add_column("Allowed Tools", style="cyan")

    for a in agents:
        table.add_row(
            a["role"],
            a["name"],
            a["description"],
            ", ".join(a["allowed_tools"]),
        )

    console.print()
    console.print(table)
    console.print()
    console.print("[dim]Usage example: [bold cyan]leai agent run plsql_analyst 'Explain routine X'[/bold cyan][/dim]\n")


@agent_app.command("run")
def run_agent_command(
    role: str = typer.Argument(
        ..., help="Specialist role: catalog_researcher, plsql_analyst, lineage_auditor, patch_generator, doc_annotator"
    ),
    task: str = typer.Argument(..., help="Objective, task, or question for the specialist"),
    config: Path = typer.Option(Path("leai.yml"), "--config", "-c", help="Path to leai.yml"),
    provider: str = typer.Option(None, "--provider", help="AI provider override"),
    model: str = typer.Option(None, "--model", "-m", help="AI model override"),
) -> None:
    """Run a specialized subagent in clean, isolated context with real-time streaming."""
    from leai.ai.subagents import SUBAGENT_REGISTRY, execute_subagent

    role_clean = role.strip().lower()
    if role_clean not in SUBAGENT_REGISTRY:
        available = ", ".join(SUBAGENT_REGISTRY.keys())
        console.print(f"[red]Error:[/red] Unknown subagent role '[bold yellow]{role}[/bold yellow]'.")
        console.print(f"[dim]Available specialists: {available}[/dim]")
        raise typer.Exit(code=1)

    try:
        cfg = load_config(config)
    except Exception:
        cfg = LeaiConfig()

    schemas_meta = load_raw_schemas(cfg.rawPath)
    if not schemas_meta:
        console.print("[yellow]Warning:[/yellow] No offline schemas found in rawPath. Run [bold cyan]leai extract[/bold cyan] first.")

    try:
        client = get_llm_client(cfg, provider_override=provider)
        if model:
            client.model = model
    except Exception as exc:
        console.print(f"[red]Error initializing AI client:[/red] {exc}")
        raise typer.Exit(code=1)

    spec = SUBAGENT_REGISTRY[role_clean]
    console.print()
    console.print(
        Panel(
            f"[bold white]Specialist:[/bold white] [bold yellow]{spec.name}[/bold yellow] ([cyan]@{role_clean}[/cyan])\n"
            f"[bold white]AI Model:[/bold white] [green]{client.model}[/green] ({client.__class__.__name__})\n"
            f"[bold white]Task:[/bold white] {task}",
            title="[bold cyan]🤖 Dispatching to Subagent Specialist[/bold cyan]",
            border_style="cyan",
            box=box.ROUNDED,
        )
    )
    console.print()

    def _on_tool_start(t_name: str, t_args: dict, step: int):
        args_str = ", ".join(f"{k}={repr(v)[:25]}" for k, v in t_args.items())
        console.print(f"[dim]⚡ [{step}] {t_name}({args_str}) ➔ Executing...[/dim]")

    def _on_tool_end(t_name: str, t_out: str, summary: str, dur: float):
        console.print(f"   [green]✓[/green] [dim]{summary} ({dur:.2f}s)[/dim]")

    try:
        reply = execute_subagent(
            role=role_clean,
            task=task,
            schemas=schemas_meta,
            config=cfg,
            client=client,
            on_tool_start=_on_tool_start,
            on_tool_end=_on_tool_end,
        )
        console.print()
        console.print(Panel(reply, title=f"[bold green]✨ {spec.name} Output[/bold green]", border_style="green"))
    except Exception as exc:
        console.print(f"[red]Execution failed:[/red] {exc}")
        raise typer.Exit(code=1)


# ==============================================================================
# WORKFLOWS CLI SUB-COMMANDS (`leai workflow`)
# ==============================================================================
workflow_app = typer.Typer(help="Execute autonomous multi-step database workflows.")
app.add_typer(workflow_app, name="workflow")


@workflow_app.command("list")
def list_workflows_command() -> None:
    """List all available autonomous database workflows and pipelines."""
    from leai.workflows import list_workflows

    workflows = list_workflows()
    table = Table(
        title="[bold cyan]⚙️ LEAI Autonomous Workflows Registry[/bold cyan]",
        box=box.ROUNDED,
        header_style="bold magenta",
    )
    table.add_column("Workflow Name", style="bold yellow")
    table.add_column("Aliases", style="cyan")
    table.add_column("Description", style="white")

    for w in workflows:
        table.add_row(
            w["name"],
            ", ".join(w["aliases"]) if w["aliases"] else "-",
            w["description"],
        )

    console.print()
    console.print(table)
    console.print()
    console.print("[dim]Usage example: [bold cyan]leai workflow run impact VINCULOS[/bold cyan][/dim]\n")


@workflow_app.command("run")
def run_workflow_command(
    name: str = typer.Argument(..., help="Workflow name or alias: impact-analysis, impact, safe-refactor, refactor"),
    target: str = typer.Argument(..., help="Target table, view, procedure, or package name"),
    config: Path = typer.Option(Path("leai.yml"), "--config", "-c", help="Path to leai.yml"),
    provider: str = typer.Option(None, "--provider", help="AI provider override"),
    output: Path = typer.Option(None, "--output", "-o", help="Optional path to export generated report Markdown"),
) -> None:
    """Run an autonomous multi-step workflow pipeline against a database object."""
    from leai.workflows import get_workflow

    try:
        cfg = load_config(config)
    except Exception:
        cfg = LeaiConfig()

    schemas_meta = load_raw_schemas(cfg.rawPath)
    if not schemas_meta:
        console.print("[yellow]Warning:[/yellow] No offline schemas found in rawPath. Run [bold cyan]leai extract[/bold cyan] first.")

    try:
        client = get_llm_client(cfg, provider_override=provider)
    except Exception as exc:
        console.print(f"[red]Error initializing AI client:[/red] {exc}")
        raise typer.Exit(code=1)

    wf = get_workflow(name=name, schemas=schemas_meta, config=cfg, client=client)
    if not wf:
        from leai.workflows import WORKFLOW_REGISTRY

        available = ", ".join(sorted(set(WORKFLOW_REGISTRY.keys())))
        console.print(f"[red]Error:[/red] Unknown workflow '[bold yellow]{name}[/bold yellow]'. Available: {available}")
        raise typer.Exit(code=1)

    console.print()
    console.print(
        Panel(
            f"[bold white]Workflow:[/bold white] [bold yellow]{wf.name}[/bold yellow]\n"
            f"[bold white]Target Object:[/bold white] [bold cyan]{target.upper()}[/bold cyan]\n"
            f"[bold white]Description:[/bold white] {wf.description}\n"
            f"[bold white]AI Engine:[/bold white] [green]{client.model}[/green]",
            title="[bold cyan]⚙️ Starting Autonomous Workflow Pipeline[/bold cyan]",
            border_style="cyan",
            box=box.ROUNDED,
        )
    )
    console.print()

    def _on_step_start(step):
        console.print(f"[bold cyan]▶ Step {step.step_number}: {step.name}[/bold cyan] ➔ [dim]{step.description}[/dim]")

    def _on_step_end(step):
        status_color = "green" if step.status == "COMPLETED" else "red"
        console.print(f"  [{status_color}]✓ {step.output_summary} ({step.duration_seconds}s)[/{status_color}]\n")

    try:
        result = wf.run(
            target=target,
            on_step_start=_on_step_start,
            on_step_end=_on_step_end,
        )

        console.print(
            Panel(
                result.report_markdown,
                title=f"[bold green]✨ {wf.name.upper()} Pipeline Completed ({result.total_duration_seconds}s)[/bold green]",
                border_style="green",
            )
        )

        if output or result.success:
            saved_path = result.export_report(output)
            console.print(f"[bold green]✓[/bold green] [dim]Report exported to: [bold cyan]{saved_path}[/bold cyan][/dim]\n")

    except Exception as exc:
        console.print(f"[red]Workflow execution failed:[/red] {exc}")
        raise typer.Exit(code=1)


# ==============================================================================
# BUSINESS GLOSSARY & RULES CLI SUB-COMMANDS (`leai rule`)
# ==============================================================================
rule_app = typer.Typer(help="Manage global business glossary, domain terms, and canonical SQL rules.")
app.add_typer(rule_app, name="rule")


@rule_app.command("list")
def list_rules_command(
    config: Path = typer.Option(Path("leai.yml"), "--config", "-c", help="Path to leai.yml"),
) -> None:
    """List all defined business glossary terms and canonical rules."""
    from leai.glossary import load_glossary

    try:
        cfg = load_config(config)
    except Exception:
        cfg = LeaiConfig()

    glossary = load_glossary(cfg.annotationsPath)
    if not glossary.terms:
        console.print(f"[yellow]No business rules found in '{cfg.annotationsPath}/glossary.yml'.[/yellow]")
        console.print("Use [bold cyan]leai rule add <term>[/bold cyan] to register rules.")
        return

    table = Table(
        title="[bold cyan]📖 LEAI Business Glossary & Canonical Rules[/bold cyan]",
        box=box.ROUNDED,
        header_style="bold magenta",
    )
    table.add_column("Business Term", style="bold yellow")
    table.add_column("Primary Table", style="bold cyan")
    table.add_column("Canonical SQL Filter", style="green")
    table.add_column("Definition", style="white")

    for t in glossary.terms:
        table.add_row(
            t.term,
            t.primary_table or "-",
            t.canonical_filter or "-",
            t.definition,
        )

    console.print()
    console.print(table)
    console.print(f"\n[dim]Total: {len(glossary.terms)} terms defined in {cfg.annotationsPath}/glossary.yml[/dim]\n")


@rule_app.command("add")
def add_rule_command(
    term: str = typer.Argument(..., help="Name of the business term or domain concept"),
    definition: str = typer.Option(..., "--definition", "-d", help="Business definition and functional meaning"),
    table: str = typer.Option(None, "--table", "-t", help="Primary table associated with this concept"),
    canonical_filter: str = typer.Option(None, "--filter", "-f", help="Canonical SQL filter condition (e.g. STATUS = 'A')"),
    tags: str = typer.Option(None, "--tags", help="Comma-separated tags (e.g. 'rh,seguranca')"),
    config: Path = typer.Option(Path("leai.yml"), "--config", "-c", help="Path to leai.yml"),
) -> None:
    """Register or update a business glossary term in annotations/glossary.yml."""
    from leai.glossary import add_or_update_term
    from leai.models import GlossaryTerm

    try:
        cfg = load_config(config)
    except Exception:
        cfg = LeaiConfig()

    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

    new_term = GlossaryTerm(
        term=term.strip(),
        definition=definition.strip(),
        primary_table=table.strip().upper() if table else None,
        canonical_filter=canonical_filter.strip() if canonical_filter else None,
        tags=tag_list,
    )

    add_or_update_term(cfg.annotationsPath, new_term)
    console.print(
        f"[green]✓ Term '[bold]{new_term.term}[/bold]' saved to [bold cyan]{cfg.annotationsPath}/glossary.yml[/bold cyan]![/green]"
    )


@rule_app.command("show")
def show_rule_command(
    term: str = typer.Argument(..., help="Term name to display"),
    config: Path = typer.Option(Path("leai.yml"), "--config", "-c", help="Path to leai.yml"),
) -> None:
    """Show details of a specific business glossary term."""
    from leai.glossary import load_glossary, search_glossary

    try:
        cfg = load_config(config)
    except Exception:
        cfg = LeaiConfig()

    glossary = load_glossary(cfg.annotationsPath)
    matches = search_glossary(glossary, term)
    if not matches:
        console.print(f"[yellow]Term '{term}' not found in glossary.[/yellow]")
        return

    top_term, _ = matches[0]
    content = [
        f"[bold white]Term:[/bold white] [bold yellow]{top_term.term}[/bold yellow]",
        f"[bold white]Definition:[/bold white] {top_term.definition}",
        f"[bold white]Primary Table:[/bold white] [bold cyan]{top_term.primary_table or '-'}[/bold cyan]",
        f"[bold white]Canonical SQL Filter:[/bold white] [green]{top_term.canonical_filter or '-'}[/green]",
    ]
    if top_term.related_tables:
        content.append(f"[bold white]Related Tables:[/bold white] {', '.join(top_term.related_tables)}")
    if top_term.tags:
        content.append(f"[bold white]Tags:[/bold white] {', '.join(top_term.tags)}")

    console.print()
    console.print(Panel("\n".join(content), title=f"[bold cyan]📖 Glossary Term: {top_term.term}[/bold cyan]", border_style="cyan"))
    console.print()


# ==============================================================================
# GIT / GITLAB INTEGRATION CLI SUB-COMMANDS (`leai git`)
# ==============================================================================
git_app = typer.Typer(help="Manage Git and GitLab repository synchronization for database metadata.")
app.add_typer(git_app, name="git")


@git_app.command("status")
def git_status_command(
    fetch: bool = typer.Option(True, "--fetch/--no-fetch", help="Fetch remote updates to check behind/ahead status"),
) -> None:
    """Check Git / GitLab repository status, active branch, and local modifications."""
    from leai.git_ops import get_git_status

    with console.status("[cyan]Checking Git/GitLab repository status...[/cyan]", spinner="dots"):
        info = get_git_status(fetch=fetch)

    if not info.is_repo:
        console.print("[yellow]! Current directory is not a Git repository.[/yellow]")
        console.print("[dim]Initialize with: git init && git remote add origin <GITLAB_URL>[/dim]\n")
        return

    table = Table(
        title=f"[bold cyan]🌿 LEAI Git Repository Status ({info.platform_name})[/bold cyan]",
        box=box.ROUNDED,
        header_style="bold magenta",
    )
    table.add_column("Property", style="bold yellow", width=22)
    table.add_column("Value", style="white")

    table.add_row("Platform", f"[bold green]{info.platform_name}[/bold green]")
    table.add_row("Active Branch", f"[bold cyan]{info.branch}[/bold cyan]")
    table.add_row("Remote (origin)", info.remote_url or "[dim]No remote configured[/dim]")

    sync_status = []
    if info.behind > 0:
        sync_status.append(f"[bold yellow]⤓ {info.behind} commit(s) behind remote (run 'leai git pull')[/bold yellow]")
    if info.ahead > 0:
        sync_status.append(f"[bold green]⤒ {info.ahead} commit(s) ahead of remote[/bold green]")
    if not sync_status:
        sync_status.append("[bold green]● Up to date with remote[/bold green]")
    table.add_row("Sync Status", ", ".join(sync_status))

    mod_count = len(info.modified_files)
    untr_count = len(info.untracked_files)
    changes = []
    if mod_count > 0:
        changes.append(f"{mod_count} modified file(s)")
    if untr_count > 0:
        changes.append(f"{untr_count} untracked file(s)")
    if not changes:
        changes.append("[green]Working tree clean[/green]")
    table.add_row("Local Changes", ", ".join(changes))

    console.print()
    console.print(table)

    if info.modified_files or info.untracked_files:
        console.print("\n[dim]Modified metadata / documentation files:[/dim]")
        for f in (info.modified_files + info.untracked_files)[:8]:
            console.print(f"  [dim yellow]• {f}[/dim yellow]")
        if len(info.modified_files + info.untracked_files) > 8:
            console.print(f"  [dim]... and {len(info.modified_files + info.untracked_files) - 8} more file(s)[/dim]")
        console.print("\n[dim]To stage, commit, and push to remote: [bold cyan]leai git sync[/bold cyan][/dim]\n")
    else:
        console.print()


@git_app.command("pull")
def git_pull_command() -> None:
    """Pull latest metadata, annotations, and glossary updates from GitLab/remote."""
    from leai.git_ops import git_pull

    console.print("[cyan]⤓ Pulling updates from remote repository...[/cyan]")
    ok, msg = git_pull()
    if ok:
        console.print(f"[green]✓ {msg}[/green]\n")
    else:
        console.print(f"[red]✕ Error pulling updates:[/red] {msg}\n")
        raise typer.Exit(code=1)


@git_app.command("sync")
def git_sync_command(
    message: str = typer.Option(None, "--message", "-m", help="Custom commit message"),
) -> None:
    """Stage metadata, annotations, and docs, commit and push to GitLab/remote."""
    from leai.git_ops import git_sync

    console.print("[cyan]⤒ Synchronizing database metadata with remote (add + commit + push)...[/cyan]")
    ok, msg = git_sync(message=message)
    if ok:
        console.print(f"[green]✓ {msg}[/green]\n")
    else:
        console.print(f"[red]✕ Sync failed:[/red] {msg}\n")
        raise typer.Exit(code=1)


# -----------------------------------------------------------------------------
# SEAWEEDFS SUBCOMMAND GROUP
# -----------------------------------------------------------------------------

seaweed_app = typer.Typer(help="Manage and synchronize database metadata with SeaweedFS S3 storage.")
app.add_typer(seaweed_app, name="seaweed")


@seaweed_app.command("status")
def seaweed_status_command(
    config: Path = typer.Option(Path("leai.yml"), "--config", "-c", help="Path to leai.yml"),
) -> None:
    """Test connection to SeaweedFS S3 storage and check bucket status."""
    try:
        cfg = load_config(config)
    except ConfigError as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        raise typer.Exit(code=1)

    from leai.storage import SeaweedFSStorage

    sw_cfg = cfg.storage.seaweedfs
    if not sw_cfg.endpoint_url:
        console.print("[yellow]Warning:[/yellow] SeaweedFS endpoint_url is not configured in leai.yml or LEAI_SEAWEED_ENDPOINT.")
        console.print("[dim]Example: storage.seaweedfs.endpoint_url: http://localhost:8333[/dim]")
        raise typer.Exit(code=1)

    console.print(f"[cyan]Testing connection to SeaweedFS S3 at[/cyan] [bold]{sw_cfg.endpoint_url}[/bold]...")
    storage = SeaweedFSStorage(sw_cfg)
    res = storage.test_connection()

    table = Table(show_header=True, header_style="bold cyan", box=box.ROUNDED)
    table.add_column("Property", style="bold white")
    table.add_column("Value", style="bold green")

    table.add_row("Endpoint URL", sw_cfg.endpoint_url)
    table.add_row("Bucket", sw_cfg.bucket)
    table.add_row("RAW Prefix", sw_cfg.raw_prefix)
    table.add_row("Annotations Prefix", sw_cfg.annotations_prefix)
    table.add_row("Connection Status", "[green]OPERATIONAL[/green]" if res.get("success") else "[red]FAILED[/red]")
    if res.get("success"):
        table.add_row("Sample Objects Found", str(res.get("objects_found", 0)))
    else:
        table.add_row("Error Details", f"[red]{res.get('error')}[/red]")

    console.print()
    console.print(Panel(table, title="[bold green]SeaweedFS S3 Storage Status[/bold green]", border_style="cyan"))


@seaweed_app.command("push")
def seaweed_push_command(
    config: Path = typer.Option(Path("leai.yml"), "--config", "-c", help="Path to leai.yml"),
) -> None:
    """Upload local RAW snapshots and YAML annotations to SeaweedFS S3 bucket."""
    start_time = time.perf_counter()
    try:
        cfg = load_config(config)
    except ConfigError as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        raise typer.Exit(code=1)

    from leai.storage import SeaweedFSStorage

    sw_cfg = cfg.storage.seaweedfs
    if not sw_cfg.endpoint_url:
        console.print("[red]Error:[/red] SeaweedFS endpoint_url is not configured.")
        raise typer.Exit(code=1)

    storage = SeaweedFSStorage(sw_cfg)
    console.print(f"[cyan]⤒ Uploading metadata to SeaweedFS ([bold yellow]{sw_cfg.endpoint_url}/{sw_cfg.bucket}[/bold yellow])...[/cyan]\n")

    with console.status("[cyan]Pushing RAW and annotations to SeaweedFS...[/cyan]"):
        counts = storage.push_local_to_remote(local_raw_path=cfg.rawPath, local_annotations_path=cfg.annotationsPath)

    elapsed = time.perf_counter() - start_time
    console.print(
        Panel(
            f"[green]✓ {counts['raw']} RAW JSON files uploaded to `{sw_cfg.raw_prefix}/`[/green]\n"
            f"[green]✓ {counts['annotations']} YAML annotation files uploaded to `{sw_cfg.annotations_prefix}/`[/green]\n"
            f"[dim]Bucket: {sw_cfg.bucket} • Time: {elapsed:.2f}s[/dim]",
            title="[bold green]SeaweedFS Push Completed[/bold green]",
            border_style="green",
        )
    )


@seaweed_app.command("pull")
def seaweed_pull_command(
    config: Path = typer.Option(Path("leai.yml"), "--config", "-c", help="Path to leai.yml"),
) -> None:
    """Download RAW snapshots and YAML annotations from SeaweedFS S3 bucket to local directories."""
    start_time = time.perf_counter()
    try:
        cfg = load_config(config)
    except ConfigError as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        raise typer.Exit(code=1)

    from leai.storage import SeaweedFSStorage

    sw_cfg = cfg.storage.seaweedfs
    if not sw_cfg.endpoint_url:
        console.print("[red]Error:[/red] SeaweedFS endpoint_url is not configured.")
        raise typer.Exit(code=1)

    storage = SeaweedFSStorage(sw_cfg)
    console.print(
        f"[cyan]⤓ Downloading metadata from SeaweedFS ([bold yellow]{sw_cfg.endpoint_url}/{sw_cfg.bucket}[/bold yellow])...[/cyan]\n"
    )

    with console.status("[cyan]Pulling RAW and annotations from SeaweedFS...[/cyan]"):
        counts = storage.pull_remote_to_local(local_raw_path=cfg.rawPath, local_annotations_path=cfg.annotationsPath)

    elapsed = time.perf_counter() - start_time
    console.print(
        Panel(
            f"[green]✓ {counts['raw']} RAW JSON files downloaded to `{cfg.rawPath}`[/green]\n"
            f"[green]✓ {counts['annotations']} YAML annotation files downloaded to `{cfg.annotationsPath}`[/green]\n"
            f"[dim]Bucket: {sw_cfg.bucket} • Time: {elapsed:.2f}s[/dim]",
            title="[bold green]SeaweedFS Pull Completed[/bold green]",
            border_style="green",
        )
    )


@seaweed_app.command("sync")
def seaweed_sync_command(
    config: Path = typer.Option(Path("leai.yml"), "--config", "-c", help="Path to leai.yml"),
) -> None:
    """Bidirectional synchronization between local metadata and SeaweedFS S3 bucket."""
    start_time = time.perf_counter()
    try:
        cfg = load_config(config)
    except ConfigError as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        raise typer.Exit(code=1)

    from leai.storage import SeaweedFSStorage

    sw_cfg = cfg.storage.seaweedfs
    if not sw_cfg.endpoint_url:
        console.print("[red]Error:[/red] SeaweedFS endpoint_url is not configured.")
        raise typer.Exit(code=1)

    storage = SeaweedFSStorage(sw_cfg)
    console.print(
        f"[cyan]🔄 Synchronizing metadata with SeaweedFS ([bold yellow]{sw_cfg.endpoint_url}/{sw_cfg.bucket}[/bold yellow])...[/cyan]\n"
    )

    with console.status("[cyan]Synchronizing with SeaweedFS...[/cyan]"):
        pushed = storage.push_local_to_remote(local_raw_path=cfg.rawPath, local_annotations_path=cfg.annotationsPath)
        pulled = storage.pull_remote_to_local(local_raw_path=cfg.rawPath, local_annotations_path=cfg.annotationsPath)

    elapsed = time.perf_counter() - start_time
    console.print(
        Panel(
            f"[green]✓ Pushed {pushed['raw']} RAW and {pushed['annotations']} annotations to SeaweedFS[/green]\n"
            f"[green]✓ Pulled {pulled['raw']} RAW and {pulled['annotations']} annotations from SeaweedFS[/green]\n"
            f"[dim]Bucket: {sw_cfg.bucket} • Time: {elapsed:.2f}s[/dim]",
            title="[bold green]SeaweedFS Sync Completed[/bold green]",
            border_style="green",
        )
    )
