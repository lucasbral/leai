from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from leai.config import ConfigError, load_config
from leai.docs import write_schema_docs
from leai.oracle import fetch_schema_metadata
from leai.raw import load_raw_schema, save_raw_schema

app = typer.Typer(help="Oracle-native database documentation CLI.")
console = Console()


def _print_summary(schema_meta) -> None:
    console.print("[green]Objetos processados:[/green]")
    console.print(f"  - Tabelas: [bold]{len(schema_meta.tables)}[/bold]")
    console.print(f"  - Views: [bold]{len(schema_meta.views)}[/bold]")
    console.print(f"  - Materialized Views: [bold]{len(schema_meta.mviews)}[/bold]")
    console.print(f"  - Code Objects (Proc/Func/Pkg): [bold]{len(schema_meta.code_objects)}[/bold]")
    console.print(f"  - Triggers: [bold]{len(schema_meta.triggers)}[/bold]")
    console.print(f"  - Sequences: [bold]{len(schema_meta.sequences)}[/bold]")
    console.print(f"  - Índices: [bold]{len(schema_meta.indexes)}[/bold]")
    console.print(f"  - Sinônimos: [bold]{len(schema_meta.synonyms)}[/bold]")


@app.command()
def extract(
    config: Path = typer.Option(Path("leai.yml"), "--config", "-c", help="Path to leai.yml"),
    object_types: list[str] = typer.Option(None, "--object-type", "-t", help="Tipos de objeto a extrair (ex: tables, views, procedures)"),
) -> None:
    """Estágio 1: Extrai o snapshot técnico puro do banco Oracle em rawPath."""
    try:
        cfg = load_config(config)
        if object_types:
            cfg.object_types = [t.lower() for t in object_types]
    except ConfigError as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        raise typer.Exit(code=1)

    try:
        console.print(f"[cyan]Extraindo snapshot técnico do schema[/cyan] [bold]{cfg.schema_name}[/bold]...")
        schema_meta = fetch_schema_metadata(cfg)
        _print_summary(schema_meta)
        saved_raw = save_raw_schema(schema_meta, cfg.rawPath)
        console.print(f"[bold yellow]Estágio 1 Concluído:[/bold yellow] {len(saved_raw)} arquivos salvos em {cfg.rawPath}")
    except Exception as exc:
        console.print(f"[red]Erro durante a extração RAW:[/red] {exc}")
        raise typer.Exit(code=1)


@app.command()
def compile(
    config: Path = typer.Option(Path("leai.yml"), "--config", "-c", help="Path to leai.yml"),
    object_types: list[str] = typer.Option(None, "--object-type", "-t", help="Tipos de objeto a compilar (ex: tables, views, procedures)"),
) -> None:
    """Estágio 3: Compila os Markdowns em docPath mesclando rawPath + annotationsPath (Offline)."""
    try:
        cfg = load_config(config)
        if object_types:
            cfg.object_types = [t.lower() for t in object_types]
    except ConfigError as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        raise typer.Exit(code=1)

    try:
        console.print(f"[cyan]Carregando snapshot técnico de[/cyan] [bold]{cfg.rawPath}[/bold]...")
        schema_meta = load_raw_schema(cfg.rawPath)
        _print_summary(schema_meta)

        generated_md, generated_ann = write_schema_docs(
            schema_meta,
            doc_path=cfg.docPath,
            annotations_path=cfg.annotationsPath,
            docs_overrides=cfg.docs,
        )
        console.print(f"[bold green]Documentos Markdown compilados:[/bold green] {len(generated_md)} em {cfg.docPath}")
        console.print(f"[bold cyan]Anotações YAML sincronizadas:[/bold cyan] {len(generated_ann)} em {cfg.annotationsPath}")
    except Exception as exc:
        console.print(f"[red]Erro durante a compilação:[/red] {exc}")
        raise typer.Exit(code=1)


@app.command()
def generate(
    config: Path = typer.Option(Path("leai.yml"), "--config", "-c", help="Path to leai.yml"),
    object_types: list[str] = typer.Option(None, "--object-type", "-t", help="Tipos de objeto a gerar (ex: tables, views, procedures)"),
) -> None:
    """Pipeline Completo de 3 Estágios (Extrai RAW ➔ Sincroniza Anotações ➔ Compila Docs)."""
    try:
        cfg = load_config(config)
        if object_types:
            cfg.object_types = [t.lower() for t in object_types]
    except ConfigError as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        raise typer.Exit(code=1)

    try:
        console.print(f"[cyan]Conectando ao schema[/cyan] [bold]{cfg.schema_name}[/bold]...")
        schema_meta = fetch_schema_metadata(cfg)
        _print_summary(schema_meta)

        # 1. Salva Snapshot RAW
        save_raw_schema(schema_meta, cfg.rawPath)

        # 2 & 3. Sincroniza anotações e compila Markdown
        generated_md, generated_ann = write_schema_docs(
            schema_meta,
            doc_path=cfg.docPath,
            annotations_path=cfg.annotationsPath,
            docs_overrides=cfg.docs,
        )
        console.print(f"[bold yellow]Snapshot RAW salvo em:[/bold yellow] {cfg.rawPath}")
        console.print(f"[bold green]Documentos Markdown gerados:[/bold green] {len(generated_md)} em {cfg.docPath}")
        console.print(f"[bold cyan]Anotações YAML sincronizadas:[/bold cyan] {len(generated_ann)} em {cfg.annotationsPath}")
    except Exception as exc:
        console.print(f"[red]Erro durante a execução:[/red] {exc}")
        raise typer.Exit(code=1)


@app.callback(invoke_without_command=True)
def default(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        ctx.invoke(generate)
