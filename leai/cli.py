from __future__ import annotations

import time
from pathlib import Path

import oracledb
import typer
from rich.console import Console, Group
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

from leai.config import ConfigError, load_config
from leai.docs import sync_schema_annotations, write_dossier_doc, write_rag_json_file, write_schema_docs
from leai.oracle import _build_connect_kwargs, fetch_available_schemas, fetch_focal_trace, fetch_schema_metadata
from leai.raw import load_raw_schemas, save_raw_schema, trace_raw_dependencies

app = typer.Typer(help="CLI para Documentação de Bancos de Dados Oracle.")
console = Console()


@app.command()
def extract(
    config: Path = typer.Option(Path("leai.yml"), "--config", "-c", help="Caminho para o leai.yml"),
    object_types: list[str] = typer.Option(None, "--object-type", "-t", help="Tipos de objeto a extrair (ex: tables, views, procedures)"),
) -> None:
    """Extrai o snapshot técnico puro do banco Oracle em rawPath."""
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
            f"[cyan]Schemas a extrair:[/cyan] [bold]{', '.join(target_schemas[:10])}{'...' if len(target_schemas) > 10 else ''}[/bold] (Total: {len(target_schemas)})\n"
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
            task_id = progress.add_task("Extraindo Schemas...", total=len(target_schemas))

            for schema_name in target_schemas:
                schema_obj_count = [0]

                def _cb(cat: str, count: int, step_idx: int, total_steps: int, s_name=schema_name) -> None:
                    schema_obj_count[0] += count
                    pct = int((step_idx / total_steps) * 100) if total_steps else 100
                    progress.update(
                        task_id,
                        description=f"Extraindo [bold yellow]{s_name}[/bold yellow] [[bold cyan]{pct}%[/bold cyan]] ([bold green]{schema_obj_count[0]:,} objetos[/bold green])",
                    )

                progress.update(task_id, description=f"Extraindo [bold yellow]{schema_name}[/bold yellow]")
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
            title="Extração RAW Concluída",
            total_schemas=len(target_schemas),
            totals=totals,
            elapsed_seconds=elapsed,
            output_paths={"Snapshot RAW": cfg.rawPath},
        )
    except Exception as exc:
        console.print(f"[red]Erro durante a extração RAW:[/red] {exc}")
        raise typer.Exit(code=1)


@app.command()
def annotate(
    config: Path = typer.Option(Path("leai.yml"), "--config", "-c", help="Caminho para o leai.yml"),
    object_types: list[str] = typer.Option(None, "--object-type", "-t", help="Tipos de objeto a sincronizar (ex: tables, views, procedures)"),
) -> None:
    """Gera/sincroniza apenas os esqueletos de anotações YAML em annotationsPath a partir do rawPath (Offline)."""
    start_time = time.perf_counter()
    try:
        cfg = load_config(config)
        if object_types:
            cfg.object_types = [t.lower() for t in object_types]
    except ConfigError as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        raise typer.Exit(code=1)

    try:
        console.print(f"[cyan]Carregando snapshots de[/cyan] [bold]{cfg.rawPath}[/bold]...\n")
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
            task_id = progress.add_task("Sincronizando Anotações...", total=len(schemas_meta))

            for schema_meta in schemas_meta:
                s_name = schema_meta.schema_name or cfg.schema_name
                progress.update(task_id, description=f"Sincronizando [bold yellow]{s_name}[/bold yellow]")

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
            title="Sincronização de Anotações Concluída",
            total_schemas=len(schemas_meta),
            totals=totals,
            elapsed_seconds=elapsed,
            output_paths={
                "Anotações YAML Sincronizadas": cfg.annotationsPath,
            },
        )
    except Exception as exc:
        console.print(f"[red]Erro durante a sincronização de anotações:[/red] {exc}")
        raise typer.Exit(code=1)


@app.command()
def compile(
    config: Path = typer.Option(Path("leai.yml"), "--config", "-c", help="Caminho para o leai.yml"),
    object_types: list[str] = typer.Option(None, "--object-type", "-t", help="Tipos de objeto a compilar (ex: tables, views, procedures)"),
) -> None:
    """Compila os Markdowns em docPath mesclando rawPath + annotationsPath (Offline)."""
    start_time = time.perf_counter()
    try:
        cfg = load_config(config)
        if object_types:
            cfg.object_types = [t.lower() for t in object_types]
    except ConfigError as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        raise typer.Exit(code=1)

    try:
        console.print(f"[cyan]Carregando snapshots de[/cyan] [bold]{cfg.rawPath}[/bold]...\n")
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
            task_id = progress.add_task("Compilando Schemas...", total=len(schemas_meta))

            for schema_meta in schemas_meta:
                s_name = schema_meta.schema_name or cfg.schema_name
                progress.update(task_id, description=f"Compilando [bold yellow]{s_name}[/bold yellow]")

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
            title="Compilação Markdown Concluída",
            total_schemas=len(schemas_meta),
            totals=totals,
            elapsed_seconds=elapsed,
            output_paths={
                "Documentos Markdown": cfg.docPath,
                "Anotações YAML Sincronizadas": cfg.annotationsPath,
            },
        )
    except Exception as exc:
        console.print(f"[red]Erro durante a compilação:[/red] {exc}")
        raise typer.Exit(code=1)


@app.command()
def generate(
    config: Path = typer.Option(Path("leai.yml"), "--config", "-c", help="Caminho para o leai.yml"),
    object_types: list[str] = typer.Option(None, "--object-type", "-t", help="Tipos de objeto a gerar (ex: tables, views, procedures)"),
) -> None:
    """Gera a documentação completa (Extrai RAW -> Sincroniza Anotações -> Compila Markdown)."""
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
            f"[cyan]Schemas a processar:[/cyan] [bold]{', '.join(target_schemas[:10])}{'...' if len(target_schemas) > 10 else ''}[/bold] (Total: {len(target_schemas)})\n"
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
            task_id = progress.add_task("Processando Pipeline...", total=len(target_schemas))

            for schema_name in target_schemas:
                schema_obj_count = [0]

                def _cb(cat: str, count: int, step_idx: int, total_steps: int, s_name=schema_name) -> None:
                    schema_obj_count[0] += count
                    pct = int((step_idx / total_steps) * 100) if total_steps else 100
                    progress.update(
                        task_id,
                        description=f"Processando [bold yellow]{s_name}[/bold yellow] [[bold cyan]{pct}%[/bold cyan]] ([bold green]{schema_obj_count[0]:,} objetos[/bold green])",
                    )

                progress.update(task_id, description=f"Processando [bold yellow]{schema_name}[/bold yellow]")
                schema_meta = fetch_schema_metadata(cfg, schema_name=schema_name, callback=_cb)

                totals["tables"] += len(schema_meta.tables)
                totals["views"] += len(schema_meta.views)
                totals["mviews"] += len(schema_meta.mviews)
                totals["code_objects"] += len(schema_meta.code_objects)
                totals["triggers"] += len(schema_meta.triggers)
                totals["sequences"] += len(schema_meta.sequences)
                totals["indexes"] += len(schema_meta.indexes)
                totals["synonyms"] += len(schema_meta.synonyms)

                # 1. Salvar Snapshot RAW
                save_raw_schema(schema_meta, cfg.rawPath, multi_schema=is_multi)

                # 2 & 3. Sincronizar Anotações e Compilar Docs
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
            title="Geração de Documentação Concluída",
            total_schemas=len(target_schemas),
            totals=totals,
            elapsed_seconds=elapsed,
            output_paths={
                "Snapshot RAW": cfg.rawPath,
                "Documentos Markdown": cfg.docPath,
                "Anotações YAML Sincronizadas": cfg.annotationsPath,
            },
        )
    except Exception as exc:
        console.print(f"[red]Erro durante a execução:[/red] {exc}")
        raise typer.Exit(code=1)


@app.command()
def changes(
    config: Path = typer.Option(Path("leai.yml"), "--config", "-c", help="Caminho para o leai.yml"),
    days: int = typer.Option(7, "--days", "-d", help="Filtrar objetos alterados nos últimos N dias"),
    user: str = typer.Option(None, "--user", "-u", help="Filtrar por usuário modificador ou schema"),
) -> None:
    """Rastreia e exibe objetos do banco alterados nos últimos N dias."""
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
                ("Tabela", schema_meta.tables),
                ("View", schema_meta.views),
                ("Materialized View", schema_meta.mviews),
                ("Code Object", schema_meta.code_objects),
                ("Trigger", schema_meta.triggers),
                ("Sequence", schema_meta.sequences),
                ("Índice", schema_meta.indexes),
                ("Sinônimo", schema_meta.synonyms),
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

        table = Table(show_header=True, header_style="bold cyan", box=None)
        table.add_column("Schema", style="bold yellow")
        table.add_column("Categoria", style="dim")
        table.add_column("Nome do Objeto", style="bold white")
        table.add_column("Última DDL", style="bold green")
        table.add_column("Modificado Por", style="magenta")

        for row in sorted(results, key=lambda x: x[3], reverse=True):
            table.add_row(*row)

        user_filter_str = f" | Usuário: {user}" if user else ""
        header_text = f"Objetos Alterados nos Últimos {days} Dias ({len(results)} Encontrados){user_filter_str}"

        console.print()
        console.print(Panel(table, title=f"[bold green]{header_text}[/bold green]", border_style="green"))
    except Exception as exc:
        console.print(f"[red]Erro ao rastrear alterações:[/red] {exc}")
        raise typer.Exit(code=1)


@app.command()
def trace(
    object_name: str = typer.Argument(..., help="Nome do objeto focal a rastrear e documentar (ex: FUNCIONARIOS)"),
    depth: int = typer.Option(1, "--depth", "-d", help="Profundidade máxima da busca no grafo de dependências"),
    rag_json: bool = typer.Option(False, "--rag-json", "--rag", help="Gerar também arquivo JSON estruturado para ingestão em Vector DB/RAG"),
    config: Path = typer.Option(Path("leai.yml"), "--config", "-c", help="Caminho para o leai.yml"),
    schema: str = typer.Option(None, "--schema", "-s", help="Schema específico (se diferente do leai.yml)"),
    offline: bool = typer.Option(False, "--offline", help="Forçar resolução de dependências no snapshot RAW em vez do banco"),
    output: Path = typer.Option(None, "--output", "-o", help="Caminho do arquivo Markdown de saída"),
) -> None:
    """Gera um dossiê técnico aprofundado e grafo de dependências (Mermaid.js) para um objeto específico."""
    start_time = time.perf_counter()
    try:
        cfg = load_config(config)
    except ConfigError as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        raise typer.Exit(code=1)

    target_obj = object_name.strip().upper()
    console.print(f"\n[cyan]Iniciando rastreamento focal e análise de impacto para:[/cyan] [bold yellow]{target_obj}[/bold yellow] (Profundidade: [bold green]{depth}[/bold green])...")

    try:
        if offline or not cfg.dsn:
            console.print("[dim]Modo Offline ativado: buscando grafo de dependências no snapshot RAW...[/dim]")
            schemas_meta = load_raw_schemas(cfg.rawPath)
            if not schemas_meta:
                console.print(f"[red]Nenhum snapshot encontrado em '{cfg.rawPath}'. Execute 'leai extract' primeiro.[/red]")
                raise typer.Exit(code=1)
            trace_res = trace_raw_dependencies(schemas_meta, target_obj, max_depth=depth)
        else:
            try:
                console.print("[dim]Consultando catálogo de dependências em tempo real no Oracle...[/dim]")
                trace_res = fetch_focal_trace(cfg, target_obj, schema_name=schema, max_depth=depth)
            except Exception as live_exc:
                console.print(f"[yellow]Aviso: falha na conexão/consulta online ({live_exc}). Tentando resolver via snapshot RAW local...[/yellow]")
                schemas_meta = load_raw_schemas(cfg.rawPath)
                if not schemas_meta:
                    raise live_exc
                trace_res = trace_raw_dependencies(schemas_meta, target_obj, max_depth=depth)

        if not trace_res.focal_object and trace_res.focal_type == "UNKNOWN":
            console.print(f"[red]Objeto '{target_obj}' não foi localizado no catálogo nem no snapshot RAW.[/red]")
            raise typer.Exit(code=1)

        # Determinar caminho de saída
        target_schema = schema or cfg.schema_name
        doc_dir = cfg.docPath / target_schema if (cfg.is_all_schemas and target_schema) else cfg.docPath
        out_file = output or (doc_dir / "dossiers" / f"{target_obj}.md")

        written_path = write_dossier_doc(trace_res, out_file, annotations_path=cfg.annotationsPath)

        if rag_json:
            json_file = doc_dir / "chunks" / f"{target_obj}.json"
            written_json = write_rag_json_file(trace_res, json_file, annotations_path=cfg.annotationsPath)
            console.print(f"[green]✓ Chunk JSON para RAG gerado em:[/green] [bold cyan]{written_json}[/bold cyan]")

        elapsed = time.perf_counter() - start_time
        console.print(f"\n[green]✓ Dossiê focal gerado com sucesso em:[/green] [bold cyan]{written_path}[/bold cyan]")
        console.print(f"[dim]Dependências mapeadas: [bold]{len(trace_res.dependencies)}[/bold] conexões | Tempo: [bold]{elapsed:.2f}s[/bold][/dim]\n")

    except typer.Exit:
        raise
    except Exception as exc:
        console.print(f"[red]Erro ao executar trace focal:[/red] {exc}")
        raise typer.Exit(code=1)


@app.callback(invoke_without_command=True)
def default(
    ctx: typer.Context,
    config: Path = typer.Option(Path("leai.yml"), "--config", "-c", help="Caminho para o leai.yml"),
    object_types: list[str] = typer.Option(None, "--object-type", "-t", help="Tipos de objeto a gerar (ex: tables, views, procedures)"),
) -> None:
    if ctx.invoked_subcommand is None:
        ctx.invoke(generate, config=config, object_types=object_types)
