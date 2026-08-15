from __future__ import annotations

import time
from pathlib import Path

import oracledb
import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from leai.ai import get_llm_client
from leai.ai.prompts import ASK_SYSTEM_PROMPT
from leai.ask_rag import build_rag_context
from leai.config import ConfigError, load_config
from leai.docs import sync_schema_annotations, write_dossier_doc, write_rag_json_file, write_schema_docs
from leai.enrich import enrich_schema_annotations
from leai.oracle import _build_connect_kwargs, fetch_available_schemas, fetch_focal_trace, fetch_schema_metadata
from leai.raw import load_raw_schemas, save_raw_schema, trace_raw_dependencies
from leai.tui import InteractiveTUISession

app = typer.Typer(help="CLI for Oracle Database Intelligence & Documentation.")
console = Console()


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

    example_path = Path(__file__).resolve().parent.parent / "leai.example.yml"
    if example_path.exists():
        content = example_path.read_text(encoding="utf-8")
    else:
        content = """# LEAI Configuration
dsn: "oracle://${DB_USER}:${DB_PASS}@${DB_HOST}:1521/${DB_SERVICE}"
schemas:
  - HR
rawPath: "./raw"
annotationsPath: "./annotations"
docPath: "./docs"
object_types:
  - tables
  - views
  - mviews
  - procedures
  - functions
  - packages
  - triggers
  - sequences
  - indexes
  - synonyms
ai:
  default_provider: "openai"
  temperature: 0.2
  providers:
    openai:
      api_key: "${OPENAI_API_KEY}"
      model: "gpt-4o-mini"
"""
    output.write_text(content, encoding="utf-8")
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
        schemas_info = ', '.join(cfg.schemas) if cfg.schemas else 'None'
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


@app.command()
def extract(
    config: Path = typer.Option(Path("leai.yml"), "--config", "-c", help="Path to leai.yml"),
    object_types: list[str] = typer.Option(None, "--object-type", "-t", help="Object types to extract (e.g. tables, views, procedures)"),
) -> None:
    """Extracts raw technical snapshot from Oracle database into rawPath."""
    start_time = time.perf_counter()
    try:
        cfg = load_config(config)
        if object_types:
            cfg.object_types = [t.lower() for t in object_types]
    except ConfigError as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        raise typer.Exit(code=1)

    try:
        connection = oracledb.connect(**_build_connect_kwargs(cfg.dsn))
        try:
            target_schemas = fetch_available_schemas(connection, cfg)
        finally:
            connection.close()

        is_multi = len(target_schemas) > 1 or cfg.is_all_schemas
        console.print(
            f"[cyan]Schemas to extract:[/cyan] [bold]{', '.join(target_schemas[:10])}{'...' if len(target_schemas) > 10 else ''}[/bold] (Total: {len(target_schemas)})\n"
        )

        totals = {
            "tables": 0, "views": 0, "mviews": 0, "code_objects": 0,
            "triggers": 0, "sequences": 0, "indexes": 0, "synonyms": 0,
        }

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold cyan]{task.description}[/bold cyan]"),
            BarColumn(),
            MofNCompleteColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task_id = progress.add_task("Extracting Schemas...", total=len(target_schemas))

            for schema_name in target_schemas:
                schema_obj_count = [0]

                def _cb(cat: str, count: int, step_idx: int, total_steps: int, s_name=schema_name) -> None:
                    schema_obj_count[0] += count
                    pct = int((step_idx / total_steps) * 100) if total_steps else 100
                    progress.update(
                        task_id,
                        description=f"Extracting [bold yellow]{s_name}[/bold yellow] [[bold cyan]{pct}%[/bold cyan]] ([bold green]{schema_obj_count[0]:,} objects[/bold green])",
                    )

                progress.update(task_id, description=f"Extracting [bold yellow]{schema_name}[/bold yellow]")
                schema_meta = fetch_schema_metadata(cfg, schema_name=schema_name, callback=_cb)

                totals["tables"] += len(schema_meta.tables)
                totals["views"] += len(schema_meta.views)
                totals["mviews"] += len(schema_meta.mviews)
                totals["code_objects"] += len(schema_meta.code_objects)
                totals["triggers"] += len(schema_meta.triggers)
                totals["sequences"] += len(schema_meta.sequences)
                totals["indexes"] += len(schema_meta.indexes)
                totals["synonyms"] += len(schema_meta.synonyms)

                save_raw_schema(schema_meta, cfg.rawPath, multi_schema=is_multi)
                progress.advance(task_id)

        elapsed = time.perf_counter() - start_time
        _print_final_summary_panel(
            title="RAW Extraction Completed",
            total_schemas=len(target_schemas),
            totals=totals,
            elapsed_seconds=elapsed,
            output_paths={"RAW Snapshot": cfg.rawPath},
        )
    except Exception as exc:
        console.print(f"[red]Error during RAW extraction:[/red] {exc}")
        raise typer.Exit(code=1)


@app.command()
def annotate(
    config: Path = typer.Option(Path("leai.yml"), "--config", "-c", help="Path to leai.yml"),
    object_types: list[str] = typer.Option(None, "--object-type", "-t", help="Object types to sync (e.g. tables, views, procedures)"),
) -> None:
    """Generates/synchronizes YAML annotation stubs in annotationsPath from rawPath (Offline)."""
    start_time = time.perf_counter()
    try:
        cfg = load_config(config)
        if object_types:
            cfg.object_types = [t.lower() for t in object_types]
    except ConfigError as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        raise typer.Exit(code=1)

    try:
        console.print(f"[cyan]Loading snapshots from[/cyan] [bold]{cfg.rawPath}[/bold]...\n")
        schemas_meta = load_raw_schemas(cfg.rawPath)
        is_multi = len(schemas_meta) > 1

        totals = {
            "tables": 0, "views": 0, "mviews": 0, "code_objects": 0,
            "triggers": 0, "sequences": 0, "indexes": 0, "synonyms": 0,
        }
        total_ann = 0

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold cyan]{task.description}[/bold cyan]"),
            BarColumn(),
            MofNCompleteColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task_id = progress.add_task("Synchronizing Annotations...", total=len(schemas_meta))

            for schema_meta in schemas_meta:
                s_name = schema_meta.schema_name or cfg.schema_name
                progress.update(task_id, description=f"Synchronizing [bold yellow]{s_name}[/bold yellow]")

                totals["tables"] += len(schema_meta.tables)
                totals["views"] += len(schema_meta.views)
                totals["mviews"] += len(schema_meta.mviews)
                totals["code_objects"] += len(schema_meta.code_objects)
                totals["triggers"] += len(schema_meta.triggers)
                totals["sequences"] += len(schema_meta.sequences)
                totals["indexes"] += len(schema_meta.indexes)
                totals["synonyms"] += len(schema_meta.synonyms)

                generated_ann = sync_schema_annotations(
                    schema_meta,
                    annotations_path=cfg.annotationsPath,
                    multi_schema=is_multi,
                    object_types=cfg.object_types,
                )
                total_ann += len(generated_ann)
                progress.advance(task_id)

        elapsed = time.perf_counter() - start_time
        _print_final_summary_panel(
            title="Annotation Synchronization Completed",
            total_schemas=len(schemas_meta),
            totals=totals,
            elapsed_seconds=elapsed,
            output_paths={
                "Synchronized YAML Annotations": cfg.annotationsPath,
            },
        )
    except Exception as exc:
        console.print(f"[red]Error during annotation synchronization:[/red] {exc}")
        raise typer.Exit(code=1)


@app.command()
def compile(
    config: Path = typer.Option(Path("leai.yml"), "--config", "-c", help="Path to leai.yml"),
    object_types: list[str] = typer.Option(None, "--object-type", "-t", help="Object types to compile (e.g. tables, views, procedures)"),
) -> None:
    """Compiles Markdown docs in docPath merging rawPath + annotationsPath (Offline)."""
    start_time = time.perf_counter()
    try:
        cfg = load_config(config)
        if object_types:
            cfg.object_types = [t.lower() for t in object_types]
    except ConfigError as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        raise typer.Exit(code=1)

    try:
        console.print(f"[cyan]Loading snapshots from[/cyan] [bold]{cfg.rawPath}[/bold]...\n")
        schemas_meta = load_raw_schemas(cfg.rawPath)
        is_multi = len(schemas_meta) > 1

        totals = {
            "tables": 0, "views": 0, "mviews": 0, "code_objects": 0,
            "triggers": 0, "sequences": 0, "indexes": 0, "synonyms": 0,
        }
        total_md = 0
        total_ann = 0

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold cyan]{task.description}[/bold cyan]"),
            BarColumn(),
            MofNCompleteColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task_id = progress.add_task("Compiling Schemas...", total=len(schemas_meta))

            for schema_meta in schemas_meta:
                s_name = schema_meta.schema_name or cfg.schema_name
                progress.update(task_id, description=f"Compiling [bold yellow]{s_name}[/bold yellow]")

                totals["tables"] += len(schema_meta.tables)
                totals["views"] += len(schema_meta.views)
                totals["mviews"] += len(schema_meta.mviews)
                totals["code_objects"] += len(schema_meta.code_objects)
                totals["triggers"] += len(schema_meta.triggers)
                totals["sequences"] += len(schema_meta.sequences)
                totals["indexes"] += len(schema_meta.indexes)
                totals["synonyms"] += len(schema_meta.synonyms)

                generated_md, generated_ann = write_schema_docs(
                    schema_meta,
                    doc_path=cfg.docPath,
                    annotations_path=cfg.annotationsPath,
                    docs_overrides=cfg.docs,
                    multi_schema=is_multi,
                    object_types=cfg.object_types,
                )
                total_md += len(generated_md)
                total_ann += len(generated_ann)
                progress.advance(task_id)

        elapsed = time.perf_counter() - start_time
        _print_final_summary_panel(
            title="Markdown Compilation Completed",
            total_schemas=len(schemas_meta),
            totals=totals,
            elapsed_seconds=elapsed,
            output_paths={
                "Markdown Documents": cfg.docPath,
                "Synchronized YAML Annotations": cfg.annotationsPath,
            },
        )
    except Exception as exc:
        console.print(f"[red]Error during compilation:[/red] {exc}")
        raise typer.Exit(code=1)


@app.command()
def generate(
    config: Path = typer.Option(Path("leai.yml"), "--config", "-c", help="Path to leai.yml"),
    object_types: list[str] = typer.Option(None, "--object-type", "-t", help="Object types to generate (e.g. tables, views, procedures)"),
) -> None:
    """Generates complete documentation (Extracts RAW -> Syncs Annotations -> Compiles Markdown)."""
    start_time = time.perf_counter()
    try:
        cfg = load_config(config)
        if object_types:
            cfg.object_types = [t.lower() for t in object_types]
    except ConfigError as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        raise typer.Exit(code=1)

    try:
        connection = oracledb.connect(**_build_connect_kwargs(cfg.dsn))
        try:
            target_schemas = fetch_available_schemas(connection, cfg)
        finally:
            connection.close()

        is_multi = len(target_schemas) > 1 or cfg.is_all_schemas
        console.print(
            f"[cyan]Schemas to process:[/cyan] [bold]{', '.join(target_schemas[:10])}{'...' if len(target_schemas) > 10 else ''}[/bold] (Total: {len(target_schemas)})\n"
        )

        totals = {
            "tables": 0, "views": 0, "mviews": 0, "code_objects": 0,
            "triggers": 0, "sequences": 0, "indexes": 0, "synonyms": 0,
        }
        total_md = 0
        total_ann = 0

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold cyan]{task.description}[/bold cyan]"),
            BarColumn(),
            MofNCompleteColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task_id = progress.add_task("Processing Pipeline...", total=len(target_schemas))

            for schema_name in target_schemas:
                schema_obj_count = [0]

                def _cb(cat: str, count: int, step_idx: int, total_steps: int, s_name=schema_name) -> None:
                    schema_obj_count[0] += count
                    pct = int((step_idx / total_steps) * 100) if total_steps else 100
                    progress.update(
                        task_id,
                        description=f"Processing [bold yellow]{s_name}[/bold yellow] [[bold cyan]{pct}%[/bold cyan]] ([bold green]{schema_obj_count[0]:,} objects[/bold green])",
                    )

                progress.update(task_id, description=f"Processing [bold yellow]{schema_name}[/bold yellow]")
                schema_meta = fetch_schema_metadata(cfg, schema_name=schema_name, callback=_cb)

                totals["tables"] += len(schema_meta.tables)
                totals["views"] += len(schema_meta.views)
                totals["mviews"] += len(schema_meta.mviews)
                totals["code_objects"] += len(schema_meta.code_objects)
                totals["triggers"] += len(schema_meta.triggers)
                totals["sequences"] += len(schema_meta.sequences)
                totals["indexes"] += len(schema_meta.indexes)
                totals["synonyms"] += len(schema_meta.synonyms)

                # 1. Save RAW Snapshot
                save_raw_schema(schema_meta, cfg.rawPath, multi_schema=is_multi)

                # 2 & 3. Sync Annotations and Compile Docs
                generated_md, generated_ann = write_schema_docs(
                    schema_meta,
                    doc_path=cfg.docPath,
                    annotations_path=cfg.annotationsPath,
                    docs_overrides=cfg.docs,
                    multi_schema=is_multi,
                    object_types=cfg.object_types,
                )
                total_md += len(generated_md)
                total_ann += len(generated_ann)
                progress.advance(task_id)

        elapsed = time.perf_counter() - start_time
        _print_final_summary_panel(
            title="Documentation Generation Completed",
            total_schemas=len(target_schemas),
            totals=totals,
            elapsed_seconds=elapsed,
            output_paths={
                "RAW Snapshot": cfg.rawPath,
                "Markdown Documents": cfg.docPath,
                "Synchronized YAML Annotations": cfg.annotationsPath,
            },
        )
    except Exception as exc:
        console.print(f"[red]Error during execution:[/red] {exc}")
        raise typer.Exit(code=1)


@app.command()
def changes(
    config: Path = typer.Option(Path("leai.yml"), "--config", "-c", help="Path to leai.yml"),
    days: int = typer.Option(7, "--days", "-d", help="Filter objects modified in the last N days"),
    user: str = typer.Option(None, "--user", "-u", help="Filter by modifying user or schema"),
) -> None:
    """Tracks and displays database objects modified in the last N days."""
    from datetime import datetime, timedelta

    try:
        cfg = load_config(config)
    except ConfigError as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        raise typer.Exit(code=1)

    try:
        schemas_meta = load_raw_schemas(cfg.rawPath)
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
) -> None:
    """Generates in-depth technical dossier and Mermaid.js dependency graph for a specific object."""
    from rich.tree import Tree

    from leai.docs import _calculate_risk_level

    start_time = time.perf_counter()
    try:
        cfg = load_config(config)
    except ConfigError as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        raise typer.Exit(code=1)

    target_obj = object_name.strip().upper()

    try:
        if offline or not cfg.dsn:
            console.print(f"\n[dim]🔍 Offline Mode: Tracing dependencies for [bold yellow]{target_obj}[/bold yellow] (Depth: {depth})...[/dim]")
            schemas_meta = load_raw_schemas(cfg.rawPath)
            if not schemas_meta:
                console.print(f"[red]No snapshot found in '{cfg.rawPath}'. Run 'leai extract' first.[/red]")
                raise typer.Exit(code=1)
            trace_res = trace_raw_dependencies(schemas_meta, target_obj, max_depth=depth)
        else:
            try:
                console.print(f"\n[dim]🌐 Querying real-time dependency catalog in Oracle for [bold yellow]{target_obj}[/bold yellow]...[/dim]")
                trace_res = fetch_focal_trace(cfg, target_obj, schema_name=schema, max_depth=depth)
            except Exception as live_exc:
                console.print(f"[yellow]Warning: online connection failed ({live_exc}). Falling back to local RAW snapshot...[/yellow]")
                schemas_meta = load_raw_schemas(cfg.rawPath)
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
                    icon = "📊" if dep.source_type == "TABLE" or dep.target_type == "TABLE" else ("👁️" if "VIEW" in dep.source_type else ("⚡" if dep.source_type == "TRIGGER" else "⚙️"))
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
        console.print(f"[green]✓ Markdown Dossier with Mermaid generated at:[/green] [bold cyan]{written_path}[/bold cyan] [dim]({elapsed:.2f}s)[/dim]\n")

    except typer.Exit:
        raise
    except Exception as exc:
        console.print(f"[red]Error executing focal trace:[/red] {exc}")
        raise typer.Exit(code=1)


@app.command()
def enrich(
    object_name: str = typer.Option(None, "--object-name", "-o", help="Specific object name to enrich (optional)"),
    provider: str = typer.Option(None, "--provider", "-p", help="AI provider (openai, gemini, anthropic, deepseek, qwen, kimi, ollama)"),
    model: str = typer.Option(None, "--model", "-m", help="AI model name (e.g. gpt-4o, gemini-1.5-flash, claude-3-5-sonnet)"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Force overwrite existing descriptions and comments"),
    object_types: list[str] = typer.Option(None, "--object-type", "-t", help="Object types to enrich (e.g. tables, packages)"),
    config: Path = typer.Option(Path("leai.yml"), "--config", "-c", help="Path to leai.yml"),
) -> None:
    """Uses AI (LLMs) to automatically populate and enrich business annotations in YAML."""
    start_time = time.perf_counter()
    try:
        cfg = load_config(config)
    except ConfigError as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        raise typer.Exit(code=1)

    schemas = load_raw_schemas(cfg.rawPath)
    if not schemas:
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

    for s in schemas:
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
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold cyan]{task.description}[/bold cyan]"),
            BarColumn(bar_width=35),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("[cyan]Enriching metadata...", total=total_eligible)

            def _on_progress(obj_type: str, obj_name: str):
                progress.update(task, advance=1, description=f"[cyan]Analyzing {obj_type} [bold yellow]{obj_name}[/bold yellow]...")

            tables_done, code_done = enrich_schema_annotations(
                schemas=schemas,
                config=cfg,
                client=client,
                overwrite=overwrite,
                target_object_name=object_name,
                target_object_types=object_types,
                progress_callback=_on_progress,
            )

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
def ask(
    question: str = typer.Argument(..., help="Natural language question about the database"),
    provider: str = typer.Option(None, "--provider", "-p", help="AI provider (openai, gemini, anthropic, deepseek, qwen, kimi, ollama)"),
    model: str = typer.Option(None, "--model", "-m", help="AI model name"),
    config: Path = typer.Option(Path("leai.yml"), "--config", "-c", help="Path to leai.yml"),
) -> None:
    """Interactive AI assistant to answer technical and business questions about the database."""
    from rich.markdown import Markdown

    start_time = time.perf_counter()
    try:
        cfg = load_config(config)
    except ConfigError as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        raise typer.Exit(code=1)

    schemas = load_raw_schemas(cfg.rawPath)
    if not schemas:
        console.print(f"[red]No snapshot found in '{cfg.rawPath}'. Run 'leai extract' first.[/red]")
        raise typer.Exit(code=1)

    try:
        client = get_llm_client(cfg, provider_override=provider, model_override=model)
    except Exception as exc:
        console.print(f"[red]Error initializing AI client:[/red] {exc}")
        raise typer.Exit(code=1)

    # Build RAG context with dynamic lineage trace
    rag_context, detected_entities = build_rag_context(question, schemas, cfg)

    if detected_entities:
        console.print(f"[dim]🔍 [bold cyan]Active RAG Context:[/bold cyan] Tracing graph and impact for: [bold yellow]{', '.join(detected_entities)}[/bold yellow][/dim]")

    user_prompt = f"Oracle Database Context (with Lineage and Impact RAG):\n{rag_context}\n\nUser Question: {question}"
    provider_name = (provider or cfg.ai.default_provider or "openai").upper()

    try:
        with console.status(f"[cyan]Querying AI ([bold yellow]{provider_name}[/bold yellow] • [bold green]{client.model}[/bold green])...[/cyan]", spinner="dots"):
            answer = client.generate_text(user_prompt, system_prompt=ASK_SYSTEM_PROMPT)

        elapsed = time.perf_counter() - start_time
        subtitle_text = f"[dim]⚡ {elapsed:.2f}s • Provider: {provider_name} ({client.model}){' • RAG: ' + ', '.join(detected_entities) if detected_entities else ''}[/dim]"
        console.print(Panel(Markdown(answer), title="[bold green]🤖 LEAI Assistant[/bold green]", subtitle=subtitle_text, border_style="cyan"))
    except Exception as exc:
        console.print(f"[red]Error querying AI:[/red] {exc}")
        raise typer.Exit(code=1)


@app.command()
def chat(
    provider: str = typer.Option(None, "--provider", "-p", help="AI provider (openai, gemini, anthropic, deepseek, qwen, kimi, ollama)"),
    model: str = typer.Option(None, "--model", "-m", help="AI model name"),
    config: Path = typer.Option(Path("leai.yml"), "--config", "-c", help="Path to leai.yml"),
) -> None:
    """Starts an interactive OpenCode-style TUI copilot with RAG, slash commands and @ mentions."""
    try:
        cfg = load_config(config)
    except ConfigError as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        raise typer.Exit(code=1)

    schemas = load_raw_schemas(cfg.rawPath)
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
    config: Path = typer.Option(Path("leai.yml"), "--config", "-c", help="Path to leai.yml"),
    object_types: list[str] = typer.Option(None, "--object-type", "-t", help="Object types to generate (e.g. tables, views, procedures)"),
) -> None:
    if ctx.invoked_subcommand is None:
        ctx.invoke(generate, config=config, object_types=object_types)
