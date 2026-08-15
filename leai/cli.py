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

from leai.ai import get_llm_client
from leai.ai.prompts import ASK_SYSTEM_PROMPT
from leai.ask_rag import build_rag_context
from leai.config import ConfigError, load_config
from leai.docs import sync_schema_annotations, write_dossier_doc, write_rag_json_file, write_schema_docs
from leai.enrich import enrich_schema_annotations
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
            console.print(f"\n[dim]🔍 Modo Offline: Rastreando dependências de [bold yellow]{target_obj}[/bold yellow] (Profundidade: {depth})...[/dim]")
            schemas_meta = load_raw_schemas(cfg.rawPath)
            if not schemas_meta:
                console.print(f"[red]Nenhum snapshot encontrado em '{cfg.rawPath}'. Execute 'leai extract' primeiro.[/red]")
                raise typer.Exit(code=1)
            trace_res = trace_raw_dependencies(schemas_meta, target_obj, max_depth=depth)
        else:
            try:
                console.print(f"\n[dim]🌐 Consultando catálogo de dependências em tempo real no Oracle para [bold yellow]{target_obj}[/bold yellow]...[/dim]")
                trace_res = fetch_focal_trace(cfg, target_obj, schema_name=schema, max_depth=depth)
            except Exception as live_exc:
                console.print(f"[yellow]Aviso: falha na conexão online ({live_exc}). Tentando resolver via snapshot RAW local...[/yellow]")
                schemas_meta = load_raw_schemas(cfg.rawPath)
                if not schemas_meta:
                    raise live_exc
                trace_res = trace_raw_dependencies(schemas_meta, target_obj, max_depth=depth)

        if not trace_res.focal_object and trace_res.focal_type == "UNKNOWN":
            console.print(f"[red]Objeto '{target_obj}' não foi localizado no catálogo nem no snapshot RAW.[/red]")
            raise typer.Exit(code=1)

        # 1. Painel de Raio-X de Impacto
        risk_level = _calculate_risk_level(len(trace_res.dependencies))
        risk_color = "red" if risk_level == "CRITICAL" else ("yellow" if risk_level in ("HIGH", "MEDIUM") else "green")

        target_schema = schema or getattr(trace_res.focal_object, "schema_name", None) or cfg.schema_name or "DEFAULT"
        console.print(
            Panel(
                f"[bold]Objeto Focal:[/bold] [bold yellow]{target_obj}[/bold yellow] • [bold]Tipo:[/bold] `{trace_res.focal_type}` • [bold]Schema:[/bold] `{target_schema}`\n"
                f"[bold]Risco de Alteração:[/bold] [{risk_color}]{risk_level}[/{risk_color}] ([bold]{len(trace_res.dependencies)}[/bold] conexões mapeadas em profundidade {depth})",
                title="[bold cyan]🔍 Raio-X de Impacto e Linhagem Técnica[/bold cyan]",
                border_style="cyan",
            )
        )

        # 2. Renderizar Árvore Hierárquica no Terminal
        if trace_res.dependencies:
            tree = Tree(f"[bold yellow]⭐ {target_obj}[/bold yellow] [dim]({trace_res.focal_type})[/dim]")
            by_depth: dict[int, list] = {}
            for dep in trace_res.dependencies:
                by_depth.setdefault(dep.depth, []).append(dep)

            for d_level in sorted(by_depth.keys()):
                level_branch = tree.add(f"[bold cyan]Nível {d_level}[/bold cyan] [dim]({'Direto' if d_level == 1 else 'Indireto'})[/dim]")
                for dep in by_depth[d_level]:
                    icon = "📊" if dep.source_type == "TABLE" or dep.target_type == "TABLE" else ("👁️" if "VIEW" in dep.source_type else ("⚡" if dep.source_type == "TRIGGER" else "⚙️"))
                    label = f"{icon} [bold]{dep.source_name}[/bold] [dim]({dep.relation_type} -> {dep.target_name})[/dim]"
                    if dep.details:
                        label += f" [dim italic]- {dep.details}[/dim italic]"
                    level_branch.add(label)

            console.print(tree)
            console.print("")

        # 3. Determinar caminho de saída e salvar Dossiê
        doc_dir = cfg.docPath / target_schema if (cfg.is_all_schemas and target_schema) else cfg.docPath
        out_file = output or (doc_dir / "dossiers" / f"{target_obj}.md")
        written_path = write_dossier_doc(trace_res, out_file, annotations_path=cfg.annotationsPath)

        if rag_json:
            json_file = doc_dir / "chunks" / f"{target_obj}.json"
            written_json = write_rag_json_file(trace_res, json_file, annotations_path=cfg.annotationsPath)
            console.print(f"[green]✓ Chunk JSON para RAG gerado em:[/green] [bold cyan]{written_json}[/bold cyan]")

        elapsed = time.perf_counter() - start_time
        console.print(f"[green]✓ Dossiê Markdown com Mermaid gerado em:[/green] [bold cyan]{written_path}[/bold cyan] [dim]({elapsed:.2f}s)[/dim]\n")

    except typer.Exit:
        raise
    except Exception as exc:
        console.print(f"[red]Erro ao executar trace focal:[/red] {exc}")
        raise typer.Exit(code=1)


@app.command()
def enrich(
    object_name: str = typer.Option(None, "--object-name", "-o", help="Nome de um objeto específico a enriquecer (opcional)"),
    provider: str = typer.Option(None, "--provider", "-p", help="Provedor de IA (openai, gemini, anthropic, deepseek, qwen, kimi, ollama)"),
    model: str = typer.Option(None, "--model", "-m", help="Nome do modelo de IA (ex: gpt-4o, gemini-1.5-flash, claude-3-5-sonnet)"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Forçar sobrescrita de descrições e comentários existentes"),
    object_types: list[str] = typer.Option(None, "--object-type", "-t", help="Tipos de objeto a enriquecer (ex: tables, packages)"),
    config: Path = typer.Option(Path("leai.yml"), "--config", "-c", help="Caminho para o leai.yml"),
) -> None:
    """Utiliza IA (LLMs) para preencher e enriquecer automaticamente as anotações de negócio em YAML."""
    start_time = time.perf_counter()
    try:
        cfg = load_config(config)
    except ConfigError as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        raise typer.Exit(code=1)

    schemas = load_raw_schemas(cfg.rawPath)
    if not schemas:
        console.print(f"[red]Nenhum snapshot encontrado em '{cfg.rawPath}'. Execute 'leai extract' primeiro.[/red]")
        raise typer.Exit(code=1)

    try:
        client = get_llm_client(cfg, provider_override=provider, model_override=model)
    except Exception as exc:
        console.print(f"[red]Erro ao inicializar cliente de IA:[/red] {exc}")
        raise typer.Exit(code=1)

    provider_label = (provider or cfg.ai.default_provider or "openai").upper()

    # Contar total de objetos elegíveis para a barra de progresso
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
            f"[bold]Provedor de IA:[/bold] [bold yellow]{provider_label}[/bold yellow] • [bold]Modelo:[/bold] [bold green]{client.model}[/bold green]\n"
            f"[bold]Modo de Operação:[/bold] {'[bold red]Forçar Sobrescrita (--overwrite)[/bold red]' if overwrite else '[bold green]Preservar Documentação Existente[/bold green]'}\n"
            f"[bold]Objetos Elegíveis:[/bold] {total_eligible} itens encontrados em `{cfg.rawPath}`",
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
            task = progress.add_task("[cyan]Enriquecendo metadados...", total=total_eligible)

            def _on_progress(obj_type: str, obj_name: str):
                progress.update(task, advance=1, description=f"[cyan]Analisando {obj_type} [bold yellow]{obj_name}[/bold yellow]...")

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
                f"[green]✓ {tables_done} Tabelas[/green] anotadas com descrições de negócio e comentários de colunas\n"
                f"[green]✓ {code_done} Packages/Procedures[/green] enriquecidas com regras inferidas\n"
                f"[bold]Tempo Total:[/bold] {elapsed:.2f}s • [bold]Destino:[/bold] [bold cyan]{cfg.annotationsPath}[/bold cyan]\n\n"
                f"[dim]Dica: Execute [bold cyan]leai compile[/bold cyan] para atualizar os Markdowns em docs/ com as novas anotações.[/dim]",
                title="[bold green]Resumo do Enriquecimento Concluído[/bold green]",
                border_style="green",
            )
        )
    except Exception as exc:
        console.print(f"[red]Erro durante o enriquecimento:[/red] {exc}")
        raise typer.Exit(code=1)


@app.command()
def ask(
    question: str = typer.Argument(..., help="Pergunta em linguagem natural sobre o banco de dados"),
    provider: str = typer.Option(None, "--provider", "-p", help="Provedor de IA (openai, gemini, anthropic, deepseek, qwen, kimi, ollama)"),
    model: str = typer.Option(None, "--model", "-m", help="Nome do modelo de IA"),
    config: Path = typer.Option(Path("leai.yml"), "--config", "-c", help="Caminho para o leai.yml"),
) -> None:
    """Assistente interativo com IA para responder dúvidas técnicas e de negócio sobre o banco de dados."""
    from rich.markdown import Markdown

    start_time = time.perf_counter()
    try:
        cfg = load_config(config)
    except ConfigError as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        raise typer.Exit(code=1)

    schemas = load_raw_schemas(cfg.rawPath)
    if not schemas:
        console.print(f"[red]Nenhum snapshot encontrado em '{cfg.rawPath}'. Execute 'leai extract' primeiro.[/red]")
        raise typer.Exit(code=1)

    try:
        client = get_llm_client(cfg, provider_override=provider, model_override=model)
    except Exception as exc:
        console.print(f"[red]Erro ao inicializar cliente de IA:[/red] {exc}")
        raise typer.Exit(code=1)

    # Construir contexto RAG com trace dinâmico
    rag_context, detected_entities = build_rag_context(question, schemas, cfg)

    if detected_entities:
        console.print(f"[dim]🔍 [bold cyan]RAG Context Ativo:[/bold cyan] Rastreando grafo e impacto de: [bold yellow]{', '.join(detected_entities)}[/bold yellow][/dim]")

    user_prompt = f"Contexto do Banco de Dados Oracle (com Linhagem e Impacto RAG):\n{rag_context}\n\nPergunta do Usuário: {question}"
    provider_name = (provider or cfg.ai.default_provider or "openai").upper()

    try:
        with console.status(f"[cyan]Consultando IA ([bold yellow]{provider_name}[/bold yellow] • [bold green]{client.model}[/bold green])...[/cyan]", spinner="dots"):
            answer = client.generate_text(user_prompt, system_prompt=ASK_SYSTEM_PROMPT)

        elapsed = time.perf_counter() - start_time
        subtitle_text = f"[dim]⚡ {elapsed:.2f}s • Provedor: {provider_name} ({client.model}){' • RAG: ' + ', '.join(detected_entities) if detected_entities else ''}[/dim]"
        console.print(Panel(Markdown(answer), title="[bold green]🤖 Assistente LEAI[/bold green]", subtitle=subtitle_text, border_style="cyan"))
    except Exception as exc:
        console.print(f"[red]Erro ao consultar IA:[/red] {exc}")
        raise typer.Exit(code=1)


@app.command()
def chat(
    provider: str = typer.Option(None, "--provider", "-p", help="Provedor de IA (openai, gemini, anthropic, deepseek, qwen, kimi, ollama)"),
    model: str = typer.Option(None, "--model", "-m", help="Nome do modelo de IA"),
    config: Path = typer.Option(Path("leai.yml"), "--config", "-c", help="Caminho para o leai.yml"),
) -> None:
    """Inicia um chat interativo multi-turno no terminal com RAG e memória de contexto sobre o banco."""
    from rich.markdown import Markdown
    from leai.chat_session import ChatSession

    try:
        cfg = load_config(config)
    except ConfigError as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        raise typer.Exit(code=1)

    schemas = load_raw_schemas(cfg.rawPath)
    if not schemas:
        console.print(f"[red]Nenhum snapshot encontrado em '{cfg.rawPath}'. Execute 'leai extract' primeiro.[/red]")
        raise typer.Exit(code=1)

    try:
        client = get_llm_client(cfg, provider_override=provider, model_override=model)
    except Exception as exc:
        console.print(f"[red]Erro ao inicializar cliente de IA:[/red] {exc}")
        raise typer.Exit(code=1)

    session = ChatSession(schemas=schemas, config=cfg, client=client)
    provider_name = (provider or cfg.ai.default_provider or "openai").upper()
    schemas_label = " • ".join(s.schema_name for s in schemas) if schemas else "Banco Completo"

    console.print(
        Panel(
            f"[bold cyan]🤖 LEAI Interactive Studio Copilot (Ecossistema Multi-Schema Integrado)[/bold cyan]\n"
            f"[dim]Provedor:[/dim] [bold yellow]{provider_name}[/bold yellow] | [dim]Modelo:[/dim] [bold green]{client.model}[/bold green] | [dim]Schemas no Grafo:[/dim] [bold]{schemas_label}[/bold]\n"
            f"[dim]Atalhos: [bold cyan]/clear[/bold cyan] (limpar memória) • [bold cyan]/save [arquivo.md][/bold cyan] (salvar) • [bold cyan]/exit[/bold cyan] (sair)[/dim]",
            title="[bold yellow]Oracle Database AI Chat[/bold yellow]",
            border_style="cyan",
        )
    )

    while True:
        try:
            prompt_label = "[bold cyan](leai)[/bold cyan] ❯ "
            user_input = console.input(f"\n{prompt_label}").strip()
            if not user_input:
                continue


            cmd_lower = user_input.lower()
            if cmd_lower in ("/exit", "/quit", "exit", "quit"):
                console.print("[yellow]Encerrando sessão de chat. Até logo![/yellow]")
                break

            if cmd_lower == "/clear":
                session.clear()
                console.print("[dim]🧹 Histórico da conversa e entidades limpos com sucesso![/dim]")
                continue

            if cmd_lower.startswith("/save"):
                parts = user_input.split(maxsplit=1)
                save_file = Path(parts[1].strip()) if len(parts) > 1 else None
                saved_path = session.save_transcript(save_file)
                console.print(f"[green]✓ Transcrição da conversa salva em:[/green] [bold cyan]{saved_path}[/bold cyan]")
                continue

            if cmd_lower == "/help":
                console.print(
                    Panel(
                        "- [bold cyan]/clear[/bold cyan]: Limpa a memória e o histórico da sessão.\n"
                        "- [bold cyan]/save [arquivo.md][/bold cyan]: Salva o histórico da conversa em arquivo Markdown.\n"
                        "- [bold cyan]/exit[/bold cyan] ou [bold cyan]/quit[/bold cyan]: Sai do chat.",
                        title="Ajuda do Chat LEAI",
                        border_style="yellow",
                    )
                )
                continue

            # Processar pergunta via LLM com spinner animado
            start_t = time.perf_counter()
            with console.status(f"[cyan]Pensando com {provider_name} ({client.model})...[/cyan]", spinner="dots"):
                reply, detected = session.send(user_input)

            elapsed_t = time.perf_counter() - start_t

            if detected:
                console.print(f"[dim]🔍 RAG Context Atualizado: [bold yellow]{', '.join(detected)}[/bold yellow][/dim]")

            subtitle_text = f"[dim]⚡ {elapsed_t:.2f}s • Provedor: {provider_name} ({client.model}){' • RAG: ' + ', '.join(detected) if detected else ''}[/dim]"
            console.print(Panel(Markdown(reply), title="[bold green]🤖 Assistente LEAI[/bold green]", subtitle=subtitle_text, border_style="cyan"))

        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Sessão de chat finalizada.[/yellow]")
            break
        except Exception as exc:
            console.print(f"[red]Erro na resposta da IA:[/red] {exc}")






@app.callback(invoke_without_command=True)
def default(
    ctx: typer.Context,
    config: Path = typer.Option(Path("leai.yml"), "--config", "-c", help="Caminho para o leai.yml"),
    object_types: list[str] = typer.Option(None, "--object-type", "-t", help="Tipos de objeto a gerar (ex: tables, views, procedures)"),
) -> None:
    if ctx.invoked_subcommand is None:
        ctx.invoke(generate, config=config, object_types=object_types)
