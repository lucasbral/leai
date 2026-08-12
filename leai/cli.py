from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from leai.config import ConfigError, load_config
from leai.docs import write_table_docs
from leai.oracle import fetch_schema_metadata

app = typer.Typer(help="Oracle-native database documentation CLI.")
console = Console()


@app.command()
def generate(config: Path = typer.Option(Path("leai.yml"), "--config", "-c", help="Path to leai.yml")) -> None:
    """Generate per-table Markdown docs from Oracle metadata."""
    try:
        cfg = load_config(config)
    except ConfigError as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        raise typer.Exit(code=1)

    console.print(f"[cyan]Conectando ao schema[/cyan] [bold]{cfg.schema_name}[/bold]...")
    tables = fetch_schema_metadata(cfg)
    console.print(f"[green]Tabelas encontradas:[/green] {len(tables)}")

    generated = write_table_docs(tables, cfg.docPath, cfg.docs)
    console.print(f"[green]Arquivos gerados:[/green] {len(generated)} em {cfg.docPath}")


@app.callback(invoke_without_command=True)
def default(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        ctx.invoke(generate)
