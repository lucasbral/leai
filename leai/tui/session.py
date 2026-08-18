from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory, InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from rich import box
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn, TimeElapsedColumn
from rich.prompt import Prompt
from rich.syntax import Syntax
from rich.table import Column, Table
from rich.tree import Tree

from leai.ai import get_llm_client
from leai.ai.base import BaseLLMClient
from leai.audit import SessionAuditLogger
from leai.chat_session import ChatSession
from leai.config import LeaiConfig
from leai.docs import (
    _calculate_risk_level,
    count_schema_objects,
    sync_schema_annotations,
    write_dossier_doc,
    write_schema_docs,
)
from leai.enrich import enrich_schema_annotations
from leai.models import SchemaMetadata
from leai.oracle import _build_connect_kwargs, fetch_available_schemas, fetch_schema_metadata
from leai.raw import load_raw_schemas, save_raw_schema, trace_raw_dependencies
from leai.tui.completer import LeaiCompleter
from leai.tui.doc_editor import DocEditor
from leai.tui.styles import PT_STYLE

console = Console()


def _create_progress_bar() -> Progress:
    """Creates a responsive progress bar with spinner, percentage, and real-time elapsed timer."""
    return Progress(
        SpinnerColumn(spinner_name="dots", style="bold cyan", finished_text="[bold green]✓[/bold green]"),
        TextColumn(
            "{task.description}",
            table_column=Column(no_wrap=True, overflow="ellipsis"),
        ),
        BarColumn(
            bar_width=None,
            style="dim cyan",
            complete_style="bold cyan",
            finished_style="bold green",
            table_column=Column(ratio=1),
        ),
        TaskProgressColumn(
            style="bold cyan",
            table_column=Column(no_wrap=True, justify="right", width=6),
        ),
        TimeElapsedColumn(
            table_column=Column(no_wrap=True, justify="right", width=8, style="dim"),
        ),
        console=console,
        expand=True,
        transient=False,
    )


def _format_tokens(total: int, last: int | None = None) -> str:
    """Formats token count with k/M suffixes and last turn delta."""

    def _fmt(n: int) -> str:
        if n >= 1_000_000:
            return f"{n / 1_000_000:.1f}M"
        elif n >= 1_000:
            return f"{n / 1_000:.1f}k"
        return str(n)

    tot_str = _fmt(total)
    if last is not None and last > 0:
        return f"{tot_str} (↑{_fmt(last)})"
    return tot_str


class InteractiveTUISession:
    """OpenCode-inspired interactive TUI copilot session for Oracle databases."""

    def __init__(
        self,
        schemas: list[SchemaMetadata],
        config: LeaiConfig,
        client: BaseLLMClient,
        provider_name: str | None = None,
    ) -> None:
        self.schemas = schemas
        self.config = config
        self.client = client
        self.provider_name = (provider_name or config.ai.default_provider or "openai").lower()
        self.session = ChatSession(schemas=schemas, config=config, client=client)
        self.last_latency: float | None = None
        self.completer = LeaiCompleter(schemas, config=config)
        self.audit_logger = SessionAuditLogger()
        self.web_server = None
        self.web_url = None

        # Setup persistent history in project folder (.leai/chat_history)
        hist_dir = Path("./.leai")
        try:
            hist_dir.mkdir(parents=True, exist_ok=True)
            self.history = FileHistory(str(hist_dir / "chat_history"))
        except Exception:
            self.history = InMemoryHistory()

        is_tty = hasattr(sys.stdin, "isatty") and sys.stdin.isatty()
        kb = KeyBindings()

        @kb.add("escape", "enter")
        def _(event):
            """Inserts newline on Alt+Enter or Escape+Enter."""
            event.current_buffer.insert_text("\n")

        if is_tty:
            try:
                self.prompt_session = PromptSession(
                    history=self.history,
                    completer=self.completer,
                    style=PT_STYLE,
                    auto_suggest=AutoSuggestFromHistory(),
                    complete_while_typing=True,
                    key_bindings=kb,
                )
            except Exception:
                from prompt_toolkit.input import DummyInput
                from prompt_toolkit.output import DummyOutput

                self.prompt_session = PromptSession(
                    history=self.history,
                    completer=self.completer,
                    style=PT_STYLE,
                    auto_suggest=AutoSuggestFromHistory(),
                    complete_while_typing=True,
                    input=DummyInput(),
                    output=DummyOutput(),
                )
        else:
            from prompt_toolkit.input import DummyInput
            from prompt_toolkit.output import DummyOutput

            self.prompt_session = PromptSession(
                history=self.history,
                completer=self.completer,
                style=PT_STYLE,
                auto_suggest=AutoSuggestFromHistory(),
                complete_while_typing=True,
                input=DummyInput(),
                output=DummyOutput(),
            )

    @property
    def model_name(self) -> str:
        return self.client.model if self.client else "offline"

    def _get_bottom_toolbar(self) -> HTML:
        """Renders dynamic OpenCode bottom status bar with Catppuccin badges."""
        schemas_count = len(self.schemas)
        schema_text = f"{schemas_count} schemas" if schemas_count > 1 else (self.schemas[0].schema_name if self.schemas else "None")
        msg_count = len(self.session.messages)
        latency_str = f"{self.last_latency:.2f}s" if self.last_latency is not None else "ready"
        tokens_str = _format_tokens(self.session.total_tokens, self.session.last_turn_tokens)

        return HTML(
            f" <b><style fg='#cba6f7'>✦ LEAI</style></b> │ "
            f"Schema: <b><style fg='#f9e2af'>{schema_text}</style></b> │ "
            f"Model: <b><style fg='#a6e3a1'>{self.provider_name.upper()}:{self.model_name}</style></b> │ "
            f"Latency: <style fg='#9399b2'>{latency_str}</style> │ "
            f"History: <b>{msg_count}</b> msgs │ "
            f"Tokens: <b><style fg='#89b4fa'>{tokens_str}</style></b> "
        )

    def print_welcome_banner(self) -> None:
        """Displays sleek OpenCode header banner."""
        total_tables = sum(len(s.tables) for s in self.schemas)
        total_views = sum(len(s.views) for s in self.schemas)
        total_code = sum(len(s.code_objects) for s in self.schemas)
        total_triggers = sum(len(s.triggers) for s in self.schemas)
        schemas_count = len(self.schemas)
        model_display = f"{self.provider_name.upper()} ({self.model_name})"

        if not self.schemas:
            target_str = ", ".join(self.config.schemas) if (self.config.schemas and not self.config.is_all_schemas) else "ALL"
            header_content = (
                f"[bold #cba6f7]Leai[/bold #cba6f7] [dim #9399b2]v{self._get_version()}[/dim #9399b2]\n"
                f"[dim #6c7086]Oracle Database DOC Assistant & Copilot[/dim #6c7086]\n\n"
                f"[bold #cdd6f4]Target Schemas:[/bold #cdd6f4] [bold #f9e2af]{target_str}[/bold #f9e2af]  •  "
                f"[bold #cdd6f4]AI Model:[/bold #cdd6f4] [bold #a6e3a1]{model_display}[/bold #a6e3a1]\n\n"
                f"[yellow]⚠️  Nenhum snapshot de banco encontrado em `{self.config.rawPath}`.[/yellow]\n"
                f"  👉 Digite [bold #74c7ec]/extract[/bold #74c7ec] para conectar ao Oracle e extrair os metadados.\n"
                f"  👉 Digite [bold #74c7ec]/trace <OBJETO>[/bold #74c7ec] para executar rastreamento de linhagem focal.\n"
                f"  👉 Digite [bold #74c7ec]/help[/bold #74c7ec] para a lista completa de comandos."
            )
        else:
            if schemas_count == 1:
                schema_badge = f"[bold #f9e2af]{self.schemas[0].schema_name}[/bold #f9e2af]"
                catalog_title = f"[dim #9399b2]Catálogo ({self.schemas[0].schema_name}):[/dim #9399b2]"
            else:
                s_names = [s.schema_name for s in self.schemas]
                preview = ", ".join(s_names[:8]) + (f" (+{schemas_count - 8} mais)" if schemas_count > 8 else "")
                schema_badge = f"[bold #f9e2af]{preview}[/bold #f9e2af] [dim #9399b2]({schemas_count} schemas)[/dim #9399b2]"
                catalog_title = f"[dim #9399b2]Catálogo ({schemas_count} schemas):[/dim #9399b2]"

            header_content = (
                f"[bold #cba6f7]Leai[/bold #cba6f7] [dim #9399b2]v{self._get_version()}[/dim #9399b2]\n"
                f"[dim #6c7086]Oracle Database DOC Assistant & Copilot[/dim #6c7086]\n\n"
                f"[bold #cdd6f4]Schema{'s' if schemas_count > 1 else ''}:[/bold #cdd6f4] {schema_badge}  •  "
                f"[bold #cdd6f4]AI Model:[/bold #cdd6f4] [bold #a6e3a1]{model_display}[/bold #a6e3a1]\n"
                f"{catalog_title} [bold #74c7ec]{total_tables}[/bold #74c7ec] Tabelas • [bold #74c7ec]{total_views}[/bold #74c7ec] Views • [bold #74c7ec]{total_code}[/bold #74c7ec] Rotinas • [bold #74c7ec]{total_triggers}[/bold #74c7ec] Triggers\n\n"
                f"[dim #9399b2]Atalhos:[/dim #9399b2] Digite qualquer pergunta ou use [bold #74c7ec]@OBJETO[/bold #74c7ec] para autocompletar tabelas/packages, ou [bold #74c7ec]/help[/bold #74c7ec] para comandos."
            )

        console.print()
        console.print(
            Panel(
                header_content,
                box=box.ROUNDED,
                border_style="#cba6f7",
                padding=(1, 2),
            )
        )

    def _get_version(self) -> str:
        try:
            from leai import __version__

            return __version__
        except Exception:
            return "0.1.6"

    def handle_slash_command(self, cmd_line: str) -> bool:
        """Handles slash commands. Returns True if command was handled, False to continue."""
        parts = cmd_line.strip().split()
        if not parts:
            return True
        cmd = parts[0].lower()

        if cmd in ("/exit", "/quit"):
            console.print("\n[yellow]✦ Goodbye! Session ended.[/yellow]")
            return False

        if cmd == "/help":
            self._render_help()
            return True

        if cmd == "/clear":
            self.session.clear()
            self.last_latency = None
            os.system("clear" if os.name == "posix" else "cls")
            self.print_welcome_banner()
            console.print("[dim]🧹 Screen and context memory reset successfully.[/dim]\n")
            return True

        if cmd == "/doc":
            obj_arg = parts[1].lstrip("@") if len(parts) > 1 else None
            self._run_doc(obj_arg)
            return True

        if cmd == "/extract":
            schemas_arg = parts[1:] if len(parts) > 1 else None
            self._run_extract(schemas_arg)
            return True

        if cmd in ("/compile", "/build"):
            target_obj = parts[1].lstrip("@").strip() if len(parts) > 1 else None
            self._run_compile(object_name=target_obj)
            return True

        if cmd == "/annotate":
            self._run_annotate()
            return True

        if cmd == "/enrich":
            target_arg = parts[1].lstrip("@") if len(parts) > 1 else None
            self._run_enrich(target_arg)
            return True

        if cmd == "/chat":
            if len(parts) > 1:
                prompt_text = cmd_line.strip()[len(parts[0]) :].strip()
                self._send_ai_prompt(prompt_text)
            else:
                console.print(
                    Panel(
                        "[bold cyan]Chat Assistant Mode[/bold cyan]\n\n"
                        "Você não precisa digitar [bold cyan]/chat[/bold cyan]! Qualquer pergunta digitada diretamente no terminal é respondida pela IA com contexto de banco de dados e RAG.\n\n"
                        "[dim]Exemplos:[/dim]\n"
                        "  • [yellow]Quais são as tabelas de folha de pagamento?[/yellow]\n"
                        "  • [yellow]@EMPLOYEES quais colunas são chaves primárias?[/yellow]\n"
                        "  • [yellow]Gere uma query SQL para listar aniversariantes do mês.[/yellow]",
                        title="[bold green]✦ IA Copilot[/bold green]",
                        border_style="cyan",
                    )
                )
            return True

        if cmd == "/serve":
            sub_arg = parts[1] if len(parts) > 1 else None
            self._run_serve(sub_arg)
            return True

        if cmd == "/tables":
            self._render_tables_table()
            return True

        if cmd == "/schema":
            self._render_schema_summary()
            return True

        if cmd == "/changes":
            days = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 7
            self._render_changes(days)
            return True

        if cmd == "/trace":
            if len(parts) < 2:
                console.print("[yellow]Usage: /trace <OBJECT_NAME> (e.g. /trace EMPLOYEES)[/yellow]")
            else:
                self._render_trace(parts[1].lstrip("@"))
            return True

        if cmd in ("/model", "/models"):
            if len(parts) < 2:
                # List models for current provider
                self._render_models_table(self.provider_name)
            elif len(parts) == 2 and parts[1].lower() in (
                "openai",
                "gemini",
                "anthropic",
                "grok",
                "xai",
                "deepseek",
                "qwen",
                "kimi",
                "ollama",
            ):
                # List models for specified provider
                self._render_models_table(parts[1].lower())
            else:
                # Switch provider and/or model
                if len(parts) >= 3:
                    new_prov = parts[1].lower()
                    new_model = parts[2]
                elif parts[1].lower() in ("openai", "gemini", "anthropic", "grok", "xai", "deepseek", "qwen", "kimi", "ollama"):
                    new_prov = parts[1].lower()
                    new_model = None
                else:
                    new_prov = self.provider_name
                    new_model = parts[1]

                try:
                    self.client = get_llm_client(self.config, provider_override=new_prov, model_override=new_model)
                    self.provider_name = new_prov
                    self.session.client = self.client
                    console.print(
                        f"[green]✓ Switched AI client to [bold]{new_prov.upper()}[/bold] (Model: [bold cyan]{self.client.model}[/bold cyan])[/green]"
                    )
                except Exception as exc:
                    console.print(f"[red]Failed to switch model:[/red] {exc}")
            return True

        if cmd == "/save":
            out_file = Path(parts[1].strip()) if len(parts) > 1 else None
            saved = self.session.save_transcript(out_file)
            console.print(f"[green]✓ Conversation transcript saved to:[/green] [bold cyan]{saved}[/bold cyan]")
            return True

        if cmd == "/check":
            self._run_check()
            return True

        if cmd == "/init":
            self._run_init()
            return True

        if cmd in ("/audit", "/log", "/tools"):
            sub_arg = parts[1] if len(parts) > 1 else None
            extra_arg = parts[2] if len(parts) > 2 else None
            self._run_audit(sub_arg, extra_arg)
            return True

        console.print(f"[yellow]Unknown command '{cmd}'. Type [bold cyan]/help[/bold cyan] for available commands.[/yellow]")
        return True

    def _run_doc(self, object_name: str | None = None) -> None:
        """Launches the in-terminal interactive documentation editor."""
        if not self.schemas:
            console.print("[yellow]! No database metadata loaded. Please run [bold cyan]/extract[/bold cyan] first.[/yellow]\n")
            return

        editor = DocEditor(self.config, self.schemas)
        saved = editor.run(object_name)
        if saved:
            # Refresh schemas and completer cache while preserving conversation history
            target_schemas_filter = self.config.schemas if not self.config.is_all_schemas else None
            self.schemas = load_raw_schemas(self.config.rawPath, target_schemas=target_schemas_filter)
            self.completer.update_schemas(self.schemas)
            self.session.update_schemas(self.schemas)

    def _run_extract(self, schemas_arg: list[str] | None = None) -> None:
        """Extracts metadata snapshots from Oracle into rawPath."""
        import oracledb

        if not self.config.dsn:
            console.print("[red]✕ DSN is not configured in leai.yml or LEAI_DSN env var.[/red]\n")
            return

        extract_cfg = self.config.model_copy()
        if schemas_arg:
            extract_cfg.schemas = [s.strip().upper() for s in schemas_arg]

        start_time = time.perf_counter()
        try:
            with console.status("[cyan]Connecting to Oracle database...[/cyan]", spinner="dots"):
                connection = oracledb.connect(**_build_connect_kwargs(extract_cfg.dsn))
                try:
                    target_schemas = fetch_available_schemas(connection, extract_cfg)
                finally:
                    connection.close()

            is_multi = len(target_schemas) > 1 or extract_cfg.is_all_schemas
            console.print(
                f"[cyan]Extracting metadata for schema(s):[/cyan] [bold yellow]{', '.join(target_schemas)}[/bold yellow] ({len(target_schemas)} total)\n"
            )

            total_tables = 0
            total_views = 0
            total_code = 0

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

                for s_idx, s_name in enumerate(target_schemas, 1):
                    schema_obj_count = [0]
                    progress.reset(
                        schema_task,
                        total=100,
                        description=f"Extracting [bold yellow]{s_name}[/bold yellow]",
                    )

                    def _cb(cat: str, count: int, step_idx: int, total_steps: int, s_title=s_name) -> None:
                        if count > 0:
                            schema_obj_count[0] += count
                        pct = int((step_idx / total_steps) * 100) if total_steps else 100
                        progress.update(
                            schema_task,
                            completed=pct,
                            total=100,
                            description=f"Extracting [bold yellow]{s_title}[/bold yellow] [[bold cyan]{pct}%[/bold cyan]] ({schema_obj_count[0]:,} objects) [dim]│ {cat}[/dim]",
                        )

                    schema_meta = fetch_schema_metadata(extract_cfg, schema_name=s_name, callback=_cb)
                    save_raw_schema(schema_meta, extract_cfg.rawPath, multi_schema=True)
                    total_tables += len(schema_meta.tables)
                    total_views += len(schema_meta.views)
                    total_code += len(schema_meta.code_objects)

                    if overall_task is not None:
                        progress.update(
                            overall_task,
                            advance=1,
                            description=f"[bold cyan]Overall Pipeline[/bold cyan] ({s_idx}/{len(target_schemas)} schemas)",
                        )

            elapsed = time.perf_counter() - start_time

            # Reload internal state while preserving conversation history
            target_schemas_filter = self.config.schemas if not self.config.is_all_schemas else None
            self.schemas = load_raw_schemas(self.config.rawPath, target_schemas=target_schemas_filter)
            self.completer.update_schemas(self.schemas)
            self.session.update_schemas(self.schemas)

            console.print(
                Panel(
                    f"[green]✓ {len(target_schemas)} Schemas Extracted[/green]\n"
                    f"[green]✓ {total_tables} Tables • {total_views} Views • {total_code} Code Objects[/green]\n"
                    f"[bold]Elapsed:[/bold] {elapsed:.2f}s • [bold]Snapshot Destination:[/bold] [bold cyan]{self.config.rawPath}[/bold cyan]\n\n"
                    f"[dim]Tip: You can now run [bold cyan]/doc <TABLE>[/bold cyan] to document objects or ask questions directly![/dim]",
                    title="[bold green]RAW Extraction Completed[/bold green]",
                    border_style="green",
                )
            )
        except Exception as exc:
            console.print(f"[red]Error during extraction:[/red] {exc}\n")

    def _run_compile(self, object_name: str | None = None) -> None:
        """Compiles Markdown docs merging raw snapshots and annotations."""
        if not self.schemas:
            console.print("[yellow]! No database snapshots found in raw/. Run [bold cyan]/extract[/bold cyan] first.[/yellow]\n")
            return

        start_time = time.perf_counter()
        total_md = 0
        is_multi = len(self.schemas) > 1 or self.config.is_all_schemas
        target_obj_up = object_name.strip().upper() if object_name else None

        # Filter target schemas when a specific object is targeted
        if target_obj_up:
            target_schemas_list = []
            target_clean = target_obj_up
            if "." in target_obj_up:
                s_part, o_part = target_obj_up.split(".", 1)
                for s in self.schemas:
                    if (s.schema_name or "").upper() == s_part:
                        target_schemas_list.append(s)
                if target_schemas_list:
                    target_clean = o_part

            if not target_schemas_list:
                for s in self.schemas:
                    if (
                        any(t.name.upper() == target_clean for t in s.tables)
                        or any(v.name.upper() == target_clean for v in s.views)
                        or any(mv.name.upper() == target_clean for mv in s.mviews)
                        or any(
                            co.name.upper() == target_clean
                            or any(
                                sub.name.upper() == target_clean or f"{co.name.upper()}.{sub.name.upper()}" == target_clean
                                for sub in co.subprograms
                            )
                            for co in s.code_objects
                        )
                        or any(tr.name.upper() == target_clean for tr in s.triggers)
                        or any(sq.name.upper() == target_clean for sq in s.sequences)
                        or any(idx.name.upper() == target_clean for idx in s.indexes)
                        or any(sn.name.upper() == target_clean for sn in s.synonyms)
                    ):
                        target_schemas_list.append(s)

            if not target_schemas_list:
                avail_schemas_str = ", ".join(s.schema_name for s in self.schemas)
                console.print(
                    f"[yellow]! Object '[bold cyan]{object_name}[/bold cyan]' was not found in loaded schemas ({avail_schemas_str}).[/yellow]\n"
                )
                return
        else:
            target_schemas_list = self.schemas

        compiled_files: list[Path] = []
        try:
            with _create_progress_bar() as progress:
                overall_task = (
                    progress.add_task(
                        f"[bold cyan]Overall Compilation[/bold cyan] (0/{len(target_schemas_list)} schemas)",
                        total=len(target_schemas_list),
                    )
                    if len(target_schemas_list) > 1
                    else None
                )
                desc = f"Compiling [bold yellow]{target_obj_up}[/bold yellow]..." if target_obj_up else "Compiling..."
                schema_task = progress.add_task(desc, total=100)

                for s_idx, s in enumerate(target_schemas_list, 1):
                    schema_total_objs = 1 if target_obj_up else count_schema_objects(s, self.config.object_types)
                    progress.reset(
                        schema_task,
                        total=schema_total_objs or 1,
                        description=f"Compiling [bold yellow]{s.schema_name}[/bold yellow]",
                    )

                    def _on_comp_progress(cat: str, name: str, current: int, total: int, s_title=s.schema_name) -> None:
                        pct = int((current / total) * 100) if total else 100
                        progress.update(
                            schema_task,
                            completed=current,
                            total=total or 1,
                            description=f"Compiling [bold yellow]{s_title}[/bold yellow] [[bold cyan]{pct}%[/bold cyan]] ({current:,}/{total:,} objs) [dim]│ {cat} {name}[/dim]",
                        )

                    gen_md, _ = write_schema_docs(
                        schema=s,
                        doc_path=self.config.docPath,
                        annotations_path=self.config.annotationsPath,
                        object_types=self.config.object_types,
                        multi_schema=is_multi,
                        all_schemas=self.schemas,
                        progress_callback=_on_comp_progress,
                        target_object=target_obj_up,
                    )
                    total_md += len(gen_md)
                    compiled_files.extend(gen_md)

                    if overall_task is not None:
                        progress.update(
                            overall_task,
                            advance=1,
                            description=f"[bold cyan]Overall Compilation[/bold cyan] ({s_idx}/{len(target_schemas_list)} schemas)",
                        )

            elapsed = time.perf_counter() - start_time
            if target_obj_up:
                file_dest_str = f"\n[bold]Output:[/bold] [bold cyan]{compiled_files[0]}[/bold cyan]" if compiled_files else ""
                matched_schema = target_schemas_list[0].schema_name if target_schemas_list else ""
                msg = f"[green]✓ Object [bold yellow]{matched_schema}.{target_obj_up.split('.')[-1]}[/bold yellow] Markdown Recompiled ({total_md} file(s)){file_dest_str}[/green]"
            else:
                msg = f"[green]✓ {total_md} Markdown Documents Compiled[/green]"

            console.print(
                Panel(
                    f"{msg}\n"
                    f"[bold]Elapsed:[/bold] {elapsed:.2f}s • [bold]Destination:[/bold] [bold cyan]{self.config.docPath}[/bold cyan]\n\n"
                    f"[dim]Tip: Run [bold cyan]/serve[/bold cyan] to preview documentation locally in your browser.[/dim]",
                    title="[bold green]Documentation Compilation Completed[/bold green]",
                    border_style="green",
                )
            )
        except Exception as exc:
            console.print(f"[red]Error during compilation:[/red] {exc}\n")

    def _run_annotate(self) -> None:
        """Synchronizes YAML annotation stubs in annotationsPath."""
        if not self.schemas:
            console.print("[yellow]! No database snapshots found in raw/. Run [bold cyan]/extract[/bold cyan] first.[/yellow]\n")
            return

        start_time = time.perf_counter()
        total_ann = 0
        is_multi = len(self.schemas) > 1 or self.config.is_all_schemas

        try:
            with _create_progress_bar() as progress:
                overall_task = (
                    progress.add_task(
                        f"[bold cyan]Overall Synchronization[/bold cyan] (0/{len(self.schemas)} schemas)",
                        total=len(self.schemas),
                    )
                    if is_multi
                    else None
                )
                schema_task = progress.add_task("Synchronizing...", total=100)

                for s_idx, s in enumerate(self.schemas, 1):
                    schema_total_objs = count_schema_objects(s, self.config.object_types)
                    progress.reset(
                        schema_task,
                        total=schema_total_objs or 1,
                        description=f"Synchronizing [bold yellow]{s.schema_name}[/bold yellow]",
                    )

                    def _on_ann_progress(cat: str, name: str, current: int, total: int, s_title=s.schema_name) -> None:
                        pct = int((current / total) * 100) if total else 100
                        progress.update(
                            schema_task,
                            completed=current,
                            total=total or 1,
                            description=f"Synchronizing [bold yellow]{s_title}[/bold yellow] [[bold cyan]{pct}%[/bold cyan]] ({current:,}/{total:,} objs) [dim]│ {cat} {name}[/dim]",
                        )

                    gen_ann = sync_schema_annotations(
                        schema=s,
                        annotations_path=self.config.annotationsPath,
                        multi_schema=is_multi,
                        object_types=self.config.object_types,
                        progress_callback=_on_ann_progress,
                    )
                    total_ann += len(gen_ann)

                    if overall_task is not None:
                        progress.update(
                            overall_task,
                            advance=1,
                            description=f"[bold cyan]Overall Synchronization[/bold cyan] ({s_idx}/{len(self.schemas)} schemas)",
                        )

            elapsed = time.perf_counter() - start_time
            console.print(
                Panel(
                    f"[green]✓ {total_ann} YAML Annotation Stubs Synchronized[/green]\n"
                    f"[bold]Elapsed:[/bold] {elapsed:.2f}s • [bold]Destination:[/bold] [bold cyan]{self.config.annotationsPath}[/bold cyan]\n\n"
                    f"[dim]Tip: Use [bold cyan]/doc <OBJECT>[/bold cyan] to edit annotations right in this terminal.[/dim]",
                    title="[bold green]Annotation Synchronization Completed[/bold green]",
                    border_style="green",
                )
            )
        except Exception as exc:
            console.print(f"[red]Error during annotation sync:[/red] {exc}\n")

    def _run_enrich(self, target_object_name: str | None = None) -> None:
        """Uses AI / LLMs to auto-enrich business annotations."""
        if not self.schemas:
            console.print("[yellow]! No database snapshots found in raw/. Run [bold cyan]/extract[/bold cyan] first.[/yellow]\n")
            return

        start_time = time.perf_counter()
        target_upper = target_object_name.strip().upper() if target_object_name else None

        # Count total eligible objects
        total_eligible = 0
        for s in self.schemas:
            for t in s.tables:
                if not target_upper or t.name.upper() == target_upper:
                    total_eligible += 1
            for co in s.code_objects:
                if not target_upper or co.name.upper() == target_upper:
                    total_eligible += 1

        try:
            with _create_progress_bar() as progress:
                enrich_task = progress.add_task(
                    f"AI Enriching with [bold yellow]{self.provider_name.upper()}[/bold yellow] ({self.model_name})...",
                    total=total_eligible or 1,
                )
                processed_count = [0]

                def _on_enrich_progress(cat: str, name: str) -> None:
                    processed_count[0] += 1
                    pct = int((processed_count[0] / (total_eligible or 1)) * 100)
                    progress.update(
                        enrich_task,
                        completed=processed_count[0],
                        total=total_eligible or 1,
                        description=f"AI Enriching [bold yellow]{name}[/bold yellow] [[bold cyan]{pct}%[/bold cyan]] ({processed_count[0]}/{total_eligible}) [dim]│ {cat}[/dim]",
                    )

                tables_done, code_done = enrich_schema_annotations(
                    schemas=self.schemas,
                    config=self.config,
                    client=self.client,
                    overwrite=False,
                    target_object_name=target_object_name,
                    progress_callback=_on_enrich_progress,
                )

            elapsed = time.perf_counter() - start_time
            console.print(
                Panel(
                    f"[green]✓ {tables_done} Tables enriched[/green]\n"
                    f"[green]✓ {code_done} Code Objects enriched[/green]\n"
                    f"[bold]Elapsed:[/bold] {elapsed:.2f}s • [bold]Destination:[/bold] [bold cyan]{self.config.annotationsPath}[/bold cyan]\n\n"
                    f"[dim]Tip: Run [bold cyan]/compile[/bold cyan] to update Markdowns with the enriched annotations.[/dim]",
                    title="[bold green]AI Auto-Enrichment Completed[/bold green]",
                    border_style="green",
                )
            )
        except Exception as exc:
            console.print(f"[red]Error during enrichment:[/red] {exc}\n")

    def _run_serve(self, arg: str | None = None) -> None:
        """Launches or controls background LEAI Web Studio."""
        sub = (arg or "").strip().lower()

        if sub == "stop":
            if self.web_server:
                self.web_server.shutdown()
                self.web_server = None
                self.web_url = None
                console.print("[yellow]✓ LEAI Web Studio stopped.[/yellow]\n")
            else:
                console.print("[dim]LEAI Web Studio is not currently running.[/dim]\n")
            return

        port = 8000
        if sub.isdigit():
            port = int(sub)

        if self.web_server:
            console.print(f"[green]✓ LEAI Web Studio is already running at [bold cyan]{self.web_url}[/bold cyan][/green]")
            import webbrowser

            webbrowser.open(self.web_url)
            console.print("[dim]Type [bold cyan]/serve stop[/bold cyan] to shut down the server.[/dim]\n")
            return

        try:
            from leai.web import start_server

            self.web_server, self.web_url = start_server(
                config=self.config,
                schemas=self.schemas,
                client=self.client,
                provider_name=self.provider_name,
                port=port,
                open_browser=True,
                in_background=True,
            )
            console.print()
            console.print(
                Panel(
                    f"[bold cyan]⚡ LEAI Web Documentation & Annotation Studio[/bold cyan]\n\n"
                    f"[bold white]URL:[/bold white] [bold yellow underline]{self.web_url}[/bold yellow underline]\n"
                    f"[bold white]Features:[/bold white] In-browser real-time annotation editor, instant Markdown sync, AI auto-enrichment & lineage graphs.\n\n"
                    f"[dim]Studio opened in your default browser. Type [bold cyan]/serve stop[/bold cyan] anytime to stop the server.[/dim]",
                    title="[bold green]🌐 Web Studio Launched in Background[/bold green]",
                    box=box.ROUNDED,
                    border_style="green",
                )
            )
            console.print()
        except Exception as exc:
            console.print(f"[red]Failed to launch Web Studio:[/red] {exc}\n")

    def _run_check(self) -> None:
        """Runs diagnostics on Oracle connection, schemas snapshot, and AI provider."""
        import oracledb

        console.print("[cyan]✦ Running LEAI Environment Diagnostics...[/cyan]\n")

        # 1. Check schemas snapshot
        if self.schemas:
            s_names = ", ".join(s.schema_name for s in self.schemas)
            total_objs = sum(len(s.tables) + len(s.views) + len(s.code_objects) for s in self.schemas)
            console.print(
                f"[green]✓ Metadata Snapshot Loaded:[/green] [bold]{len(self.schemas)} schemas[/bold] ({s_names}) • {total_objs:,} objects"
            )
        else:
            console.print(f"[yellow]! No schema metadata snapshot loaded from {self.config.rawPath}[/yellow]")

        # 2. Check Oracle Connection
        if self.config.dsn:
            try:
                from leai.oracle import _build_connect_kwargs

                conn = oracledb.connect(**_build_connect_kwargs(self.config.dsn))
                cur = conn.cursor()
                cur.execute("SELECT * FROM v$version WHERE ROWNUM = 1")
                ver = cur.fetchone()
                ver_str = ver[0] if ver else "Oracle Database"
                conn.close()
                console.print(f"[green]✓ Oracle Database Connection:[/green] [bold]OK[/bold] ([dim]{ver_str}[/dim])")
            except Exception as exc:
                console.print(f"[red]✗ Oracle Connection Error:[/red] {exc}")
        else:
            console.print("[yellow]! DSN not configured in leai.yml (offline mode)[/yellow]")

        # 3. Check AI Provider
        try:
            if self.client:
                console.print(
                    f"[green]✓ Active AI Provider:[/green] [bold yellow]{self.provider_name.upper()}[/bold yellow] (Model: [bold cyan]{self.client.model}[/bold cyan])"
                )
            else:
                console.print("[yellow]! AI Client not initialized[/yellow]")
        except Exception as exc:
            console.print(f"[yellow]! Warning checking AI client:[/yellow] {exc}")

        # 4. Check Documentation Directory
        doc_count = len(list(self.config.docPath.glob("**/*.md"))) if self.config.docPath.exists() else 0
        ann_count = len(list(self.config.annotationsPath.glob("**/*.yml"))) if self.config.annotationsPath.exists() else 0
        console.print(
            f"[green]✓ Documentation Store:[/green] [cyan]{ann_count}[/cyan] annotations in [bold]{self.config.annotationsPath}[/bold] • [cyan]{doc_count}[/cyan] docs in [bold]{self.config.docPath}[/bold]\n"
        )

    def _run_init(self) -> None:
        """Informs or initializes leai.yml."""
        out_file = Path("leai.yml")
        if out_file.exists():
            console.print(f"[green]✓ Configuration file already exists at:[/green] [bold cyan]{out_file.resolve()}[/bold cyan]\n")
        else:
            example_path = Path(__file__).resolve().parent.parent.parent / "leai.example.yml"
            if example_path.exists():
                content = example_path.read_text(encoding="utf-8")
            else:
                content = "# LEAI Configuration\n"
            out_file.write_text(content, encoding="utf-8")
            console.print(f"[green]✓ Configuration file created at:[/green] [bold cyan]{out_file.resolve()}[/bold cyan]\n")

    def _render_help(self) -> None:
        table = Table(show_header=True, header_style="bold #74c7ec", box=box.ROUNDED)
        table.add_column("Comando", style="bold #f9e2af", width=22)
        table.add_column("Categoria", style="dim #9399b2", width=14)
        table.add_column("Descrição", style="#cdd6f4")

        # Documentation & Studio
        table.add_row("/doc [obj]", "Documentação", "Editor interativo no terminal de anotações YAML e docs")
        table.add_row("/enrich [obj]", "AI Studio", "Auto-enriquece descrições e regras de negócio com IA")
        table.add_row("/compile [obj]", "Pipeline", "Compila markdowns finais em docs/ (suporta objeto único)")
        table.add_row("/annotate", "Pipeline", "Sincroniza stubs de anotação YAML em annotations/")
        table.add_row("/extract [s|ALL]", "Pipeline", "Conecta ao Oracle e extrai snapshot novo de metadados")
        table.add_row("/serve [port|stop]", "Web Studio", "Inicia o Web Studio com editor web e sincronização em tempo real")

        # Exploration & Lineage
        table.add_row("/trace <obj>", "Linhagem", "Executa rastreamento de dependências e raio-x com Mermaid")
        table.add_row("/tables", "Inspeção", "Lista todas as tabelas com contagem de colunas e PKs")
        table.add_row("/schema [s]", "Inspeção", "Exibe visão geral detalhada do catálogo do banco")
        table.add_row("/changes [d]", "Inspeção", "Inspeciona objetos modificados nos últimos N dias (padrão: 7)")

        # AI & Configuration
        table.add_row("/models [p]", "Config IA", "Lista os modelos de IA disponíveis na API")
        table.add_row("/model <p> [m]", "Config IA", "Altera provedor (openai, gemini, grok, etc.) e modelo")
        table.add_row("/check", "Diagnóstico", "Verifica conexão Oracle, snapshots, docs e status da IA")
        table.add_row("/init", "Setup", "Verifica ou inicializa o arquivo de configuração leai.yml")

        # Session & Utilities
        table.add_row("/audit [last|session|export]", "Auditoria", "Inspeciona trace de ferramentas da IA, latência e logs")
        table.add_row("/tools", "Auditoria", "Visualizador rápido de entradas/saídas da última chamada de ferramenta")
        table.add_row("/save [file.md]", "Sessão", "Exporta transcrição da conversa para arquivo Markdown")
        table.add_row("/clear", "Sessão", "Limpa a memória do chat e reseta a tela do terminal")
        table.add_row("/chat <msg>", "Copilot", "Envia pergunta para a IA (ou apenas digite diretamente)")
        table.add_row("/help", "Referência", "Exibe este guia de comandos interativo")
        table.add_row("/exit, /quit", "Sessão", "Encerra o copilot interativo")

        console.print()
        console.print(
            Panel(
                table,
                title="[bold #cba6f7]✦ Referência de Comandos Interativos do LEAI[/bold #cba6f7]",
                box=box.ROUNDED,
                border_style="#74c7ec",
            )
        )
        console.print(
            "[dim #9399b2]Dica: Digite qualquer pergunta diretamente, use [bold #74c7ec]@OBJETO[/bold #74c7ec] para autocompletar menções ou [bold #74c7ec]/[/bold #74c7ec] para comandos.[/dim #9399b2]\n"
        )

    def _render_models_table(self, provider_name: str | None = None, interactive: bool = True) -> None:
        target_prov = (provider_name or self.provider_name or "openai").lower()
        try:
            temp_client = (
                self.client
                if target_prov == (self.provider_name or "").lower()
                else get_llm_client(self.config, provider_override=target_prov)
            )
            with console.status(
                f"[#74c7ec]Buscando modelos disponíveis na API [bold #f9e2af]{target_prov.upper()}[/bold #f9e2af]...[/#74c7ec]",
                spinner="dots",
            ):
                models_list = temp_client.list_models()
        except Exception as exc:
            console.print(f"[red]Não foi possível buscar modelos para {target_prov.upper()}:[/red] {exc}\n")
            return

        if not models_list:
            console.print(f"[yellow]Nenhum modelo retornado para {target_prov.upper()}.[/yellow]\n")
            return

        table = Table(show_header=True, header_style="bold #74c7ec", box=box.ROUNDED)
        table.add_column("#", justify="right", style="#74c7ec", width=4)
        table.add_column("Status", justify="center", width=8)
        table.add_column("Model ID", style="bold #f9e2af")
        table.add_column("Display Name", style="#cdd6f4")
        table.add_column("Descrição / Notas", style="dim #9399b2")

        for idx, m in enumerate(models_list, 1):
            m_id = m.get("id", "")
            is_active = target_prov == (self.provider_name or "").lower() and m_id == self.client.model
            status_badge = "[bold #a6e3a1]ACTIVE[/bold #a6e3a1]" if is_active else "[dim #6c7086]-[/dim #6c7086]"
            table.add_row(f"[{idx}]", status_badge, m_id, m.get("name", m_id), m.get("description", m.get("note", "")))

        console.print()
        console.print(
            Panel(
                table,
                title=f"[bold #cba6f7]✦ Modelos Disponíveis para {target_prov.upper()} ({len(models_list)} Total)[/bold #cba6f7]",
                box=box.ROUNDED,
                border_style="#74c7ec",
            )
        )

        if interactive:
            console.print(f"[dim]Type a number (1-{len(models_list)}) or Model ID to switch, or press Enter to keep current:[/dim]")
            try:
                choice = Prompt.ask("[cyan]👉 Select model[/cyan]", default="")
                choice = choice.strip()
                if choice:
                    selected_model = None
                    if choice.isdigit():
                        c_idx = int(choice) - 1
                        if 0 <= c_idx < len(models_list):
                            selected_model = models_list[c_idx]["id"]
                    else:
                        selected_model = choice

                    if selected_model:
                        self.client = get_llm_client(self.config, provider_override=target_prov, model_override=selected_model)
                        self.provider_name = target_prov
                        self.session.client = self.client
                        console.print(
                            f"[green]✓ Switched AI client to [bold]{target_prov.upper()}[/bold] (Model: [bold cyan]{self.client.model}[/bold cyan])[/green]\n"
                        )
                    else:
                        console.print(f"[red]Invalid selection: '{choice}'[/red]\n")
            except (KeyboardInterrupt, EOFError):
                console.print()
        else:
            console.print(f"[dim]To switch model, type: [bold cyan]/model {target_prov} <model_id>[/bold cyan][/dim]\n")

    def _render_tables_table(self) -> None:
        table = Table(show_header=True, header_style="bold cyan", box=box.ROUNDED)
        table.add_column("Schema", style="yellow")
        table.add_column("Table Name", style="bold white")
        table.add_column("Columns", justify="right", style="cyan")
        table.add_column("Primary Keys", style="green")
        table.add_column("Description / Comment", style="dim")

        total = 0
        for s in self.schemas:
            s_name = s.schema_name or "DEFAULT"
            for t in s.tables:
                total += 1
                pks = ", ".join(t.primary_keys) if t.primary_keys else "-"
                comm = (t.comment or "").strip()
                if len(comm) > 60:
                    comm = comm[:57] + "..."
                table.add_row(s_name, t.name, str(len(t.columns)), pks, comm)

        console.print()
        console.print(
            Panel(table, title=f"[bold green]✦ Database Tables ({total} Total)[/bold green]", box=box.ROUNDED, border_style="green")
        )
        console.print()

    def _render_schema_summary(self) -> None:
        for s in self.schemas:
            s_name = s.schema_name or "DEFAULT"
            t = Table(show_header=True, header_style="bold cyan", box=box.ROUNDED)
            t.add_column("Object Type", style="bold white")
            t.add_column("Count", justify="right", style="bold green")

            t.add_row("Tables", str(len(s.tables)))
            t.add_row("Views", str(len(s.views)))
            t.add_row("Materialized Views", str(len(s.mviews)))
            t.add_row("Code Objects (Packages/Procedures)", str(len(s.code_objects)))
            t.add_row("Triggers", str(len(s.triggers)))
            t.add_row("Sequences", str(len(s.sequences)))
            t.add_row("Indexes", str(len(s.indexes)))
            t.add_row("Synonyms", str(len(s.synonyms)))

            console.print()
            console.print(Panel(t, title=f"[bold yellow]✦ Schema Overview: {s_name}[/bold yellow]", box=box.ROUNDED, border_style="yellow"))
        console.print()

    def _render_changes(self, days: int) -> None:
        cutoff = datetime.now() - timedelta(days=days)
        results = []

        for schema_meta in self.schemas:
            s_name = schema_meta.schema_name or "DEFAULT"
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
            console.print(f"[yellow]No objects were modified in the last {days} days.[/yellow]\n")
            return

        table = Table(show_header=True, header_style="bold cyan", box=box.ROUNDED)
        table.add_column("Schema", style="yellow")
        table.add_column("Category", style="dim")
        table.add_column("Object Name", style="bold white")
        table.add_column("Last DDL", style="bold green")
        table.add_column("Modified By", style="magenta")

        for row in sorted(results, key=lambda x: x[3], reverse=True):
            table.add_row(*row)

        console.print()
        console.print(
            Panel(
                table,
                title=f"[bold green]✦ Objects Modified in the Last {days} Days ({len(results)} Found)[/bold green]",
                box=box.ROUNDED,
                border_style="green",
            )
        )
        console.print()

    def _render_trace(self, object_name: str) -> None:
        target_obj = object_name.strip().upper()
        trace_res = trace_raw_dependencies(self.schemas, target_obj, max_depth=1)

        if not trace_res.focal_object and trace_res.focal_type == "UNKNOWN":
            console.print(f"[red]Object '{target_obj}' was not found in catalog.[/red]\n")
            return

        risk_level = _calculate_risk_level(len(trace_res.dependencies))
        risk_color = "red" if risk_level == "CRITICAL" else ("yellow" if risk_level in ("HIGH", "MEDIUM") else "green")

        console.print()
        console.print(
            Panel(
                f"[bold]Focal Object:[/bold] [bold yellow]{target_obj}[/bold yellow]  •  [bold]Type:[/bold] `{trace_res.focal_type}`\n"
                f"[bold]Change Risk Level:[/bold] [{risk_color}]{risk_level}[/{risk_color}] ([bold]{len(trace_res.dependencies)}[/bold] direct connections mapped)",
                title="[bold cyan]🔍 Inline Lineage & Impact X-Ray[/bold cyan]",
                box=box.ROUNDED,
                border_style="cyan",
            )
        )

        if trace_res.dependencies:
            tree = Tree(f"[bold yellow]⭐ {target_obj}[/bold yellow] [dim]({trace_res.focal_type})[/dim]")
            for dep in trace_res.dependencies:
                icon = "📊" if "TABLE" in dep.source_type or "TABLE" in dep.target_type else ("👁️" if "VIEW" in dep.source_type else "⚙️")
                label = f"{icon} [bold]{dep.source_name}[/bold] [dim]({dep.relation_type} -> {dep.target_name})[/dim]"
                if dep.details:
                    label += f" [dim italic]- {dep.details}[/dim italic]"
                tree.add(label)

            console.print(tree)

        # Output Dossier
        out_file = self.config.docPath / "dossiers" / f"{target_obj}.md"
        written = write_dossier_doc(trace_res, out_file, annotations_path=self.config.annotationsPath)
        console.print(f"[dim]✓ Dossier generated at: {written}[/dim]\n")

    def _send_ai_prompt(self, user_input: str) -> None:
        """Queries AI Assistant with live step-by-step tool feedback, audit recording, and latency metrics."""
        if not self.client:
            console.print(
                "[yellow]! No active AI client configured. Type [bold cyan]/model[/bold cyan] to configure a provider.[/yellow]\n"
            )
            return

        start_t = time.perf_counter()

        def _format_args_preview(args: dict) -> str:
            items = []
            for k, v in args.items():
                v_str = repr(v) if not isinstance(v, (dict, list)) else json.dumps(v, ensure_ascii=False)
                if len(v_str) > 32:
                    v_str = v_str[:29] + "..."
                items.append(f"{k}={v_str}")
            return ", ".join(items)

        # 1. Print User message in OpenCode format
        console.print()
        console.print(
            Panel(
                f"[bold #cdd6f4]{user_input}[/bold #cdd6f4]",
                title="[bold #89b4fa]👤 User[/bold #89b4fa]",
                title_align="left",
                border_style="#45475a",
                box=box.ROUNDED,
                padding=(0, 1),
            )
        )

        def _on_tool_start(t_name: str, t_args: dict, step_idx: int = 1) -> None:
            args_str = _format_args_preview(t_args)
            console.print(
                f"  [bold #fab387]⚡ [{step_idx}][/bold #fab387] [bold #74c7ec]{t_name}[/bold #74c7ec][#a6adc8]({args_str})[/#a6adc8] [dim #6c7086]➔ Executando...[/dim #6c7086]"
            )

        def _on_tool_end(t_name: str, t_output: str, summary: str = "", dur: float = 0.0) -> None:
            sum_text = summary or "OK"
            dur_text = f" ({dur:.2f}s)" if dur > 0 else ""
            console.print(f"     [bold #a6e3a1]✓[/bold #a6e3a1] [#bac2de]{sum_text}[/#bac2de][dim #6c7086]{dur_text}[/dim #6c7086]")

        streamed_chunks: list[str] = []

        def _on_token(token: str) -> None:
            streamed_chunks.append(token)

        with console.status(
            f"[#74c7ec]Pensando com [bold #f9e2af]{self.provider_name.upper()}[/bold #f9e2af] ([bold #a6e3a1]{self.client.model}[/bold #a6e3a1])...[/#74c7ec]",
            spinner="dots",
        ):
            reply, detected = self.session.send(
                user_input,
                on_tool_start=_on_tool_start,
                on_tool_end=_on_tool_end,
                on_token=_on_token,
            )
        self.last_latency = time.perf_counter() - start_t

        # Record in Session Audit Logger
        turn_audit = self.audit_logger.record_turn(
            user_prompt=user_input,
            ai_response=reply,
            provider=self.provider_name,
            model=self.client.model if self.client else "",
            latency_seconds=self.last_latency,
            tokens_used=self.session.last_turn_tokens or 0,
            rag_entities=detected,
            tools_executed=self.session.last_tool_audits,
        )

        turn_tok_str = f" • {self.session.last_turn_tokens:,} tokens" if self.session.last_turn_tokens else ""
        tool_count = len(turn_audit.tools_executed)
        tool_badge = f" • {tool_count} tool{'s' if tool_count > 1 else ''}" if tool_count > 0 else ""
        subtitle_str = (
            f"[dim #9399b2]⚡ {self.last_latency:.2f}s{turn_tok_str}{tool_badge} • {self.provider_name.upper()} ({self.client.model})"
            f"{' • RAG: ' + ', '.join(detected) if detected else ''}[/dim #9399b2]"
        )

        console.print()
        console.print(
            Panel(
                Markdown(reply, code_theme="monokai"),
                title="[bold #a6e3a1]✦ LEAI Assistant[/bold #a6e3a1]",
                title_align="left",
                subtitle=subtitle_str,
                subtitle_align="right",
                box=box.ROUNDED,
                border_style="#74c7ec",
                padding=(1, 2),
            )
        )
        if tool_count > 0:
            console.print(
                "[dim #6c7086]💡 Digite [bold #74c7ec]/audit[/bold #74c7ec] ou [bold #74c7ec]/tools[/bold #74c7ec] para inspecionar parâmetros, SQL e respostas brutas das ferramentas.[/dim #6c7086]\n"
            )
        else:
            console.print()

    def _run_audit(self, sub_cmd: str | None = None, arg: str | None = None) -> None:
        """Inspects AI reasoning, tool execution traces, and session audit logs."""
        sub = (sub_cmd or "last").lower()

        if sub == "session":
            summary = self.audit_logger.get_session_summary()
            table = Table(show_header=True, header_style="bold cyan", box=box.ROUNDED)
            table.add_column("Metric", style="bold white", width=25)
            table.add_column("Value", style="bold yellow")

            table.add_row("Session ID", summary["session_id"])
            table.add_row("Session Start Time", summary["start_time"])
            table.add_row("Total Questions Asked", str(summary["total_turns"]))
            table.add_row("Total Tool Executions", str(summary["total_tool_calls"]))
            table.add_row("Total Tokens Used", f"{summary['total_tokens']:,}")
            table.add_row("Total Model Latency", f"{summary['total_latency_seconds']}s")
            table.add_row("Active Audit Log File", summary["log_file"])

            console.print()
            console.print(Panel(table, title="[bold cyan]✦ AI Session Audit Overview[/bold cyan]", box=box.ROUNDED, border_style="cyan"))

            if summary["tool_usage_breakdown"]:
                t_table = Table(show_header=True, header_style="bold cyan", box=box.ROUNDED)
                t_table.add_column("Tool Name", style="bold yellow")
                t_table.add_column("Execution Count", justify="right", style="green")
                for t_name, count in sorted(summary["tool_usage_breakdown"].items(), key=lambda x: x[1], reverse=True):
                    t_table.add_row(t_name, str(count))
                console.print(
                    Panel(t_table, title="[bold green]✦ Tool Execution Breakdown[/bold green]", box=box.ROUNDED, border_style="green")
                )
            console.print()
            return

        if sub in ("export", "save"):
            target_path = Path(arg.strip()) if arg else None
            is_json = target_path and target_path.suffix.lower() == ".json"
            if is_json:
                saved = self.audit_logger.export_json(target_path)
            else:
                saved = self.audit_logger.export_markdown(target_path)
            console.print(f"[green]✓ Audit report successfully exported to:[/green] [bold cyan]{saved.resolve()}[/bold cyan]\n")
            return

        # Default: /audit or /audit last
        last_turn = self.audit_logger.get_last_turn()
        if not last_turn:
            console.print("[yellow]! No interaction has occurred yet in this session.[/yellow]\n")
            return

        console.print()
        info_panel = (
            f"[bold white]Turn ID:[/bold white] [bold cyan]#{last_turn.turn_id}[/bold cyan]  •  "
            f"[bold white]Timestamp:[/bold white] {last_turn.timestamp}  •  "
            f"[bold white]Model:[/bold white] [bold green]{last_turn.provider}:{last_turn.model}[/bold green]\n"
            f'[bold white]Prompt:[/bold white] [yellow]"{last_turn.user_prompt}"[/yellow]\n'
            f"[bold white]Latency:[/bold white] {last_turn.latency_seconds}s  •  "
            f"[bold white]Tokens:[/bold white] {last_turn.tokens_used:,}  •  "
            f"[bold white]Tools Used:[/bold white] [bold]{len(last_turn.tools_executed)}[/bold]"
        )
        console.print(Panel(info_panel, title="[bold cyan]✦ AI Interaction Audit Trace[/bold cyan]", box=box.ROUNDED, border_style="cyan"))

        if not last_turn.tools_executed:
            console.print("[dim]No database tools were invoked for this question (direct answer or RAG context was sufficient).[/dim]\n")
            return

        for te in last_turn.tools_executed:
            t_table = Table(show_header=False, box=box.SIMPLE)
            t_table.add_column("Field", style="dim cyan", width=16)
            t_table.add_column("Value", style="white")

            t_table.add_row("Step", f"[bold yellow]#{te.step}[/bold yellow] ([bold cyan]{te.tool_name}[/bold cyan])")
            t_table.add_row("Duration", f"{te.duration_seconds:.3f}s")
            t_table.add_row("Summary", f"[bold green]{te.summary}[/bold green]")
            args_formatted = json.dumps(te.arguments, indent=2, ensure_ascii=False)
            t_table.add_row("Arguments", Syntax(args_formatted, "json", theme="monokai", word_wrap=True))

            try:
                parsed_out = json.loads(te.raw_output)
                out_formatted = json.dumps(parsed_out, indent=2, ensure_ascii=False)
            except Exception:
                out_formatted = te.raw_output

            if len(out_formatted) > 800:
                out_formatted = out_formatted[:797] + "..."

            t_table.add_row("Raw Output", Syntax(out_formatted, "json", theme="monokai", word_wrap=True))

            console.print(
                Panel(
                    t_table,
                    title=f"[bold yellow]⚡ Step {te.step}: {te.tool_name}[/bold yellow]",
                    box=box.ROUNDED,
                    border_style="yellow",
                )
            )
        console.print(f"[dim]Audit session file: [bold cyan]{self.audit_logger.log_file}[/bold cyan][/dim]\n")

    def run(self) -> None:
        """Main interaction loop."""
        self.print_welcome_banner()

        while True:
            try:
                if not sys.stdin.isatty():
                    line = sys.stdin.readline()
                    if not line:
                        break
                    user_input = line.strip()
                else:
                    user_input = self.prompt_session.prompt(
                        [
                            ("class:prompt.symbol", "✦ "),
                            ("class:prompt.text", "leai"),
                            ("class:prompt.arrow", " ❯ "),
                        ],
                        bottom_toolbar=self._get_bottom_toolbar,
                    ).strip()

                if not user_input:
                    continue

                # Handle slash commands
                if user_input.startswith("/"):
                    should_continue = self.handle_slash_command(user_input)
                    if not should_continue:
                        break
                    continue

                # Handle direct AI Prompt
                self._send_ai_prompt(user_input)

            except KeyboardInterrupt:
                console.print("\n[dim]KeyboardInterrupt: Press Ctrl+D or type /exit to quit.[/dim]")
                continue
            except EOFError:
                console.print("\n[yellow]✦ Goodbye![/yellow]")
                break
            except Exception as exc:
                console.print(f"\n[red]Error in interactive session:[/red] {exc}\n")
