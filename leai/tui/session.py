from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.filters import has_completions
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory, InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from rich import box
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn, TimeElapsedColumn
from rich.prompt import Confirm, Prompt
from rich.rule import Rule
from rich.syntax import Syntax
from rich.table import Column, Table
from rich.tree import Tree

from leai.ai import get_llm_client
from leai.ai.base import BaseLLMClient
from leai.audit import SessionAuditLogger
from leai.chat_session import ChatSession
from leai.clipboard import copy_to_clipboard, extract_code_blocks
from leai.config import LeaiConfig
from leai.docs import (
    _calculate_risk_level,
    count_schema_objects,
    sync_schema_annotations,
    write_dossier_doc,
    write_schema_docs,
)
from leai.enrich import enrich_schema_annotations
from leai.i18n import t
from leai.models import SchemaMetadata
from leai.oracle import _build_connect_kwargs, fetch_available_schemas, fetch_schema_metadata
from leai.raw import load_raw_schemas, save_raw_schema, trace_raw_dependencies
from leai.status import LiveStatusTicker
from leai.tui.completer import LeaiCompleter
from leai.tui.doc_editor import DocEditor
from leai.tui.styles import PT_STYLE

console = Console(legacy_windows=False)


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
        # Ensure active locale matches project configuration
        from leai.i18n import resolve_locale, set_locale

        set_locale(resolve_locale(None, getattr(config, "language", None)))
        self.client = client
        self.provider_name = (provider_name or config.ai.default_provider or "openai").lower()
        self.session = ChatSession(schemas=schemas, config=config, client=client)
        self.last_latency: float | None = None
        self.last_ai_reply: str = ""
        self.last_code_blocks: list[dict] = []
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

        @kb.add("enter", filter=has_completions)
        def _(event):
            """Applies selected completion and adds trailing space without submitting the prompt."""
            b = event.current_buffer
            if b.complete_state:
                if b.complete_state.current_completion:
                    b.apply_completion(b.complete_state.current_completion)
                elif b.complete_state.completions:
                    b.apply_completion(b.complete_state.completions[0])
                b.cancel_completion()
                b.insert_text(" ")
            else:
                b.validate_and_handle()

        @kb.add("tab", filter=has_completions)
        def _(event):
            """Fills highlighted completion and appends a trailing space without jumping lines."""
            b = event.current_buffer
            if b.complete_state:
                if b.complete_state.current_completion:
                    b.apply_completion(b.complete_state.current_completion)
                elif b.complete_state.completions:
                    b.apply_completion(b.complete_state.completions[0])
                b.cancel_completion()
                b.insert_text(" ")

        @kb.add("down", filter=has_completions)
        def _(event):
            """Navigates to the next completion in the dropdown list."""
            event.current_buffer.complete_next()

        @kb.add("up", filter=has_completions)
        def _(event):
            """Navigates to the previous completion in the dropdown list."""
            event.current_buffer.complete_previous()

        @kb.add("escape", filter=has_completions)
        def _(event):
            """Dismisses completion dropdown without selecting."""
            event.current_buffer.cancel_completion()

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
                    key_bindings=kb,
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
                key_bindings=kb,
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
        latency_str = f"{self.last_latency:.2f}s" if self.last_latency is not None else t("tui.toolbar_ready")
        tokens_str = _format_tokens(self.session.total_tokens, self.session.last_turn_tokens)

        return HTML(
            f" <b><style fg='#cba6f7'>✦ LEAI</style></b> │ "
            f"{t('tui.toolbar_schema')}: <b><style fg='#f9e2af'>{schema_text}</style></b> │ "
            f"{t('tui.toolbar_model')}: <b><style fg='#a6e3a1'>{self.provider_name.upper()}:{self.model_name}</style></b> │ "
            f"{t('tui.toolbar_latency')}: <style fg='#9399b2'>{latency_str}</style> │ "
            f"{t('tui.toolbar_history')}: <b>{msg_count}</b> msgs │ "
            f"{t('tui.toolbar_tokens')}: <b><style fg='#89b4fa'>{tokens_str}</style></b> "
        )

    def _generate_starter_suggestions(self) -> list[str]:
        """Generates dynamic, contextual starter queries based on loaded database objects."""
        if not self.schemas:
            return [
                t("tui.suggest_extract"),
                t("tui.suggest_config"),
                t("tui.suggest_help"),
            ]

        all_tables = [tbl_obj.name for s in self.schemas for tbl_obj in s.tables]
        all_views = [v.name for s in self.schemas for v in s.views]
        all_code = [co.name for s in self.schemas for co in s.code_objects]

        suggestions = []
        if all_tables:
            tbl = all_tables[0]
            suggestions.append(t("tui.suggest_table_purpose", tbl=tbl))

        if all_code:
            routine = all_code[0]
            suggestions.append(t("tui.suggest_routine_trace", routine=routine))
        elif all_views:
            vw = all_views[0]
            suggestions.append(t("tui.suggest_view_definition", vw=vw))
        elif len(all_tables) > 1:
            tbl2 = all_tables[1]
            suggestions.append(t("tui.suggest_table_relation", tbl=tbl2))

        if all_tables and len(all_tables) > 2:
            tbl3 = all_tables[2]
            suggestions.append(t("tui.suggest_fk_lookup", tbl=tbl3))
        else:
            suggestions.append(t("tui.suggest_risk_summary"))

        return suggestions[:3]

    def print_welcome_banner(self) -> None:
        """Displays sleek, modern OpenCode-style developer dashboard."""
        version = self._get_version()

        # 1. ASCII Art Header with Catppuccin Gradient
        ascii_logo = (
            "[bold #cba6f7] ██╗     ███████╗ █████╗ ██╗[/bold #cba6f7]\n"
            "[bold #b4befe] ██║     ██╔════╝██╔══██╗██║[/bold #b4befe]\n"
            "[bold #89b4fa] ██║     █████╗  ███████║██║[/bold #89b4fa]\n"
            "[bold #74c7ec] ██║     ██╔══╝  ██╔══██║██║[/bold #74c7ec]\n"
            "[bold #89dceb] ███████╗███████╗██║  ██║██║[/bold #89dceb]\n"
            "[bold #94e2d5] ╚══════╝╚══════╝╚═╝  ╚═╝╚═╝[/bold #94e2d5]"
        )

        header_grid = Table.grid(expand=True)
        header_grid.add_column(ratio=3)
        header_grid.add_column(ratio=2, justify="right")

        header_left = f"{ascii_logo}\n[dim #6c7086]{t('tui.header_sub')}[/dim #6c7086]"

        header_right = (
            f"\n[bold #cba6f7]LEAI CLI[/bold #cba6f7] [bold green]v{version}[/bold green]\n"
            f"[dim #9399b2]{t('tui.header_hint')}[/dim #9399b2]"
        )
        header_grid.add_row(header_left, header_right)

        console.print()
        console.print(
            Panel(
                header_grid,
                box=box.ROUNDED,
                border_style="#cba6f7",
                padding=(1, 2),
            )
        )

        # 2. Side-by-Side Status Cards
        total_tables = sum(len(s.tables) for s in self.schemas)
        total_views = sum(len(s.views) for s in self.schemas)
        total_code = sum(len(s.code_objects) for s in self.schemas)
        total_triggers = sum(len(s.triggers) for s in self.schemas)
        schemas_count = len(self.schemas)

        def _fmt_path(p: Path | str) -> str:
            try:
                p_obj = Path(p).resolve()
                cwd = Path.cwd().resolve()
                if p_obj == cwd:
                    return "./"
                if p_obj.is_relative_to(cwd):
                    return f"./{p_obj.relative_to(cwd)}"
                return str(p_obj)
            except Exception:
                return str(p)

        raw_display = _fmt_path(self.config.rawPath)
        ann_display = _fmt_path(self.config.annotationsPath)

        # 2. Unified Status Table (Rounded, perfectly aligned across all terminal sizes)
        status_table = Table(
            expand=True,
            box=box.ROUNDED,
            border_style="#89b4fa",
            show_header=True,
            header_style="bold",
            pad_edge=True,
            padding=(0, 1),
        )
        status_table.add_column(f"[bold #89b4fa]{t('tui.col_db_catalog')}[/bold #89b4fa]", ratio=1)
        status_table.add_column(f"[bold #a6e3a1]{t('tui.col_ai_engine')}[/bold #a6e3a1]", ratio=1)

        # Left Column: Database Status
        if not self.schemas:
            target_str = ", ".join(self.config.schemas) if (self.config.schemas and not self.config.is_all_schemas) else "ALL"
            db_lines = [
                f"[bold #cdd6f4]{t('tui.schemas_label')}[/bold #cdd6f4] [bold #f9e2af]{target_str}[/bold #f9e2af]",
                f"[bold #cdd6f4]{t('tui.snapshot_label')}[/bold #cdd6f4] [dim]{raw_display}[/dim]",
                f"[bold yellow]{t('tui.no_snapshot_loaded')}[/bold yellow]",
                t("tui.run_extract_hint"),
            ]
        else:
            if schemas_count == 1:
                schema_badge = f"[bold #f9e2af]{self.schemas[0].schema_name}[/bold #f9e2af] [dim]{t('tui.active_badge')}[/dim]"
            else:
                s_names = [s.schema_name for s in self.schemas]
                preview = ", ".join(s_names[:4]) + (f" (+{schemas_count - 4} more)" if schemas_count > 4 else "")
                schema_badge = f"[bold #f9e2af]{preview}[/bold #f9e2af] [dim]{t('tui.schemas_count_badge', count=schemas_count)}[/dim]"

            db_lines = [
                f"[bold #cdd6f4]{t('tui.schemas_label')}[/bold #cdd6f4] {schema_badge}",
                f"[bold #cdd6f4]{t('tui.catalog_label')}[/bold #cdd6f4] {t('tui.catalog_counts', tables=total_tables, views=total_views)}",
                f"[bold #cdd6f4]{t('tui.objects_label')}[/bold #cdd6f4] {t('tui.objects_counts', routines=total_code, triggers=total_triggers)}",
                f"[bold #cdd6f4]{t('tui.snapshot_label')}[/bold #cdd6f4] [dim]{raw_display}[/dim] [bold green]{t('tui.ready_badge')}[/bold green]",
            ]

        # Right Column: AI Status
        provider_name = (self.provider_name or self.config.ai.default_provider or "openai").upper()
        model_name = self.model_name or "default"
        is_client_ok = self.client is not None
        client_status = (
            f"[bold green]{t('tui.status_connected')}[/bold green]"
            if is_client_ok
            else f"[bold yellow]{t('tui.status_not_configured')}[/bold yellow]"
        )

        chunks_dir = self.config.docPath / "chunks"
        chunk_count = len(list(chunks_dir.glob("*.json"))) if chunks_dir.exists() else 0
        chunk_info = t("tui.chunks_indexed", count=chunk_count) if chunk_count > 0 else f"[dim]{t('tui.run_compile_to_index')}[/dim]"

        ai_lines = [
            f"[bold #cdd6f4]{t('tui.provider_label')}[/bold #cdd6f4] [bold #a6e3a1]{provider_name}[/bold #a6e3a1] [dim]({model_name})[/dim]",
            f"[bold #cdd6f4]{t('tui.status_label')}[/bold #cdd6f4] {client_status} [dim](Temp: {self.config.ai.temperature:.2f})[/dim]",
            f"[bold #cdd6f4]{t('tui.rag_memory_label')}[/bold #cdd6f4] {chunk_info}",
            f"[bold #cdd6f4]{t('tui.annotations_label')}[/bold #cdd6f4] [dim]{ann_display}[/dim]",
        ]

        status_table.add_row("\n".join(db_lines), "\n".join(ai_lines))
        console.print(status_table)

        # Git / GitLab Repository Observability Notice
        if getattr(self.config, "git", None) and self.config.git.enabled:
            try:
                from leai.git_ops import get_git_status, git_pull

                if self.config.git.auto_pull_on_start:
                    pulled_ok, pull_msg = git_pull()
                    if pulled_ok and "Already up to date" not in pull_msg:
                        console.print(f"[bold green]✓ Sincronizado com GitLab ({pull_msg})[/bold green]")
                        target_schemas_filter = self.config.schemas if not self.config.is_all_schemas else None
                        self.schemas = load_raw_schemas(self.config.rawPath, target_schemas=target_schemas_filter)
                        self.completer.update_schemas(self.schemas)
                        self.session.update_schemas(self.schemas)

                git_info = get_git_status(fetch=False)
                if git_info.is_repo:
                    plat = git_info.platform_name
                    branch = git_info.branch or "main"
                    if git_info.behind > 0:
                        console.print(t("tui.git_behind_warning", behind=git_info.behind, platform=plat))
                    elif git_info.has_uncommitted:
                        total_mod = len(git_info.modified_files) + len(git_info.untracked_files)
                        console.print(
                            t("tui.git_status_branch", platform=plat, branch=branch, count=total_mod)
                            + " (use [bold cyan]/git sync[/bold cyan])\n"
                        )
                    else:
                        console.print(t("tui.git_synced", platform=plat, branch=branch))
            except Exception:
                pass

        # 3. Essential Actions & Shortcuts Cheat-sheet
        actions_grid = Table.grid(expand=True, padding=(0, 2))
        actions_grid.add_column(ratio=1)
        actions_grid.add_column(ratio=1)

        actions_grid.add_row(
            f"  [bold #74c7ec]@OBJECT[/bold #74c7ec]     [dim]{t('tui.action_autocomplete')}[/dim]",
            f"  [bold #74c7ec]/doc @OBJ[/bold #74c7ec]   [dim]{t('tui.action_edit_annotations')}[/dim]",
        )
        actions_grid.add_row(
            f"  [bold #74c7ec]/extract[/bold #74c7ec]    [dim]{t('tui.action_pull_metadata')}[/dim]",
            f"  [bold #74c7ec]/rule add[/bold #74c7ec]   [dim]{t('tui.action_add_rule')}[/dim]",
        )
        actions_grid.add_row(
            f"  [bold #74c7ec]/compile[/bold #74c7ec]    [dim]{t('tui.action_generate_docs')}[/dim]",
            f"  [bold #74c7ec]/git status[/bold #74c7ec] [dim]{t('tui.action_git_sync')}[/dim]",
        )
        actions_grid.add_row(
            f"  [bold #74c7ec]/trace @OBJ[/bold #74c7ec] [dim]{t('tui.action_lineage_graph')}[/dim]",
            f"  [bold #74c7ec]/help[/bold #74c7ec]       [dim]{t('tui.action_full_guide')}[/dim]",
        )

        actions_panel = Panel(
            actions_grid,
            title=f"[bold #fab387]{t('tui.quick_actions_title')}[/bold #fab387]",
            title_align="left",
            box=box.ROUNDED,
            border_style="#fab387",
            padding=(0, 1),
        )
        console.print(actions_panel)

        # 4. Contextual Starter Suggestions
        suggestions = self._generate_starter_suggestions()
        if suggestions:
            console.print(f"[dim #f9e2af]{t('tui.suggest_title')}[/dim #f9e2af]")
            for s in suggestions:
                console.print(f"   [dim #6c7086]•[/dim #6c7086] {s}")
            console.print()

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
            console.print(t("tui.cmd_exit_goodbye"))
            return False

        if cmd == "/help":
            self._render_help()
            return True

        if cmd == "/clear":
            self.session.clear()
            self.last_latency = None
            os.system("clear" if os.name == "posix" else "cls")
            self.print_welcome_banner()
            console.print(t("tui.cmd_clear_reset"))
            return True

        if cmd == "/doc":
            obj_arg = parts[1].lstrip("@") if len(parts) > 1 else None
            self._run_doc(obj_arg)
            return True

        if cmd == "/extract":
            schemas_arg = parts[1:] if len(parts) > 1 else None
            self._run_extract(schemas_arg)
            return True

        if cmd == "/update":
            update_args = parts[1:] if len(parts) > 1 else None
            self._run_update(update_args)
            return True

        if cmd == "/seaweed":
            sub_arg = parts[1].lower() if len(parts) > 1 else "status"
            self._run_seaweed(sub_arg)
            return True

        if cmd in ("/compile", "/build"):
            target_obj = parts[1].lstrip("@").strip() if len(parts) > 1 else None
            self._run_compile(object_name=target_obj)
            return True

        if cmd == "/annotate":
            args = parts[1:] if len(parts) > 1 else None
            self._run_annotate(args)
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
                        "You don't need to type [bold cyan]/chat[/bold cyan]! Any question typed directly in the terminal is answered by the AI with database context and RAG.\n\n"
                        "[dim]Examples:[/dim]\n"
                        "  • [yellow]Which tables are related to payroll?[/yellow]\n"
                        "  • [yellow]@EMPLOYEES which columns are primary keys?[/yellow]\n"
                        "  • [yellow]Generate a SQL query to list active employees by department.[/yellow]",
                        title="[bold green]✦ AI Copilot[/bold green]",
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

        if cmd == "/agent":
            from leai.ai.subagents import SUBAGENT_REGISTRY, execute_subagent, list_registered_subagents

            if len(parts) < 2 or parts[1].lower() == "list":
                agents = list_registered_subagents()
                tbl = Table(title="[bold cyan]⚡ LEAI Specialized Subagents[/bold cyan]", box=box.ROUNDED)
                tbl.add_column("Role / Command", style="bold yellow")
                tbl.add_column("Specialist Name", style="bold white")
                tbl.add_column("Description", style="dim")
                for a in agents:
                    tbl.add_row(f"/agent {a['role']}", a["name"], a["description"])
                console.print()
                console.print(tbl)
                console.print("[dim]Usage: [bold cyan]/agent <role> <task/question>[/bold cyan][/dim]\n")
                return True

            target_role = parts[1].lower().lstrip("@")
            if target_role not in SUBAGENT_REGISTRY:
                available = ", ".join(SUBAGENT_REGISTRY.keys())
                console.print(f"[red]Unknown specialist role:[/red] '{target_role}'. Available: {available}")
                return True

            if len(parts) < 3:
                console.print(f"[yellow]Usage: /agent {target_role} <task or question>[/yellow]")
                return True

            task_query = " ".join(parts[2:])
            spec = SUBAGENT_REGISTRY[target_role]
            console.print()
            console.print(f"[dim]🤖 Consulting Specialist [bold yellow]{spec.name}[/bold yellow]...[/dim]")

            def _on_sub_start(t_name: str, t_args: dict, step: int):
                args_str = ", ".join(f"{k}={repr(v)[:20]}" for k, v in t_args.items())
                console.print(f"[dim]  ⚡ [{step}] {t_name}({args_str}) ➔ Executing...[/dim]")

            def _on_sub_end(t_name: str, t_out: str, summary: str, dur: float):
                console.print(f"     [green]✓[/green] [dim]{summary} ({dur:.2f}s)[/dim]")

            try:
                sub_reply = execute_subagent(
                    role=target_role,
                    task=task_query,
                    schemas=self.schemas,
                    config=self.config,
                    client=self.client,
                    on_tool_start=_on_sub_start,
                    on_tool_end=_on_sub_end,
                )
                console.print()
                console.print(Panel(sub_reply, title=f"[bold green]✨ {spec.name}[/bold green]", border_style="green"))
                console.print()
            except Exception as exc:
                console.print(f"[red]Specialist error:[/red] {exc}")
            return True

        if cmd == "/workflow":
            from leai.workflows import get_workflow, list_workflows

            if len(parts) < 2 or parts[1].lower() == "list":
                wfs = list_workflows()
                tbl = Table(title="[bold cyan]⚙️ LEAI Autonomous Workflows[/bold cyan]", box=box.ROUNDED)
                tbl.add_column("Workflow / Command", style="bold yellow")
                tbl.add_column("Description", style="white")
                for w in wfs:
                    tbl.add_row(f"/workflow {w['name']}", w["description"])
                console.print()
                console.print(tbl)
                console.print(
                    "[dim]Usage: [bold cyan]/workflow <name> <target_object>[/bold cyan] (e.g. /workflow impact VINCULOS)[/dim]\n"
                )
                return True

            wf_name = parts[1].lower()
            if wf_name in ("run", "exec") and len(parts) >= 4:
                wf_name = parts[2].lower()
                target_obj = parts[3].lstrip("@")
            elif len(parts) >= 3:
                target_obj = parts[2].lstrip("@")
            else:
                console.print(f"[yellow]Usage: /workflow {wf_name} <target_object>[/yellow]")
                return True

            wf = get_workflow(name=wf_name, schemas=self.schemas, config=self.config, client=self.client)
            if not wf:
                from leai.workflows import WORKFLOW_REGISTRY

                available = ", ".join(sorted(set(WORKFLOW_REGISTRY.keys())))
                console.print(f"[red]Unknown workflow:[/red] '{wf_name}'. Available: {available}")
                return True

            console.print()
            console.print(
                f"[bold cyan]⚙️ Running workflow [bold yellow]{wf.name}[/bold yellow] on [bold white]{target_obj.upper()}[/bold white]...[/bold cyan]"
            )

            def _on_wf_start(step):
                console.print(f"[dim]  ▶ Step {step.step_number}: {step.name}[/dim]")

            def _on_wf_end(step):
                console.print(f"    [green]✓[/green] [dim]{step.output_summary} ({step.duration_seconds}s)[/dim]")

            try:
                res = wf.run(target=target_obj, on_step_start=_on_wf_start, on_step_end=_on_wf_end)
                console.print()
                console.print(
                    Panel(
                        res.report_markdown,
                        title=f"[bold green]✨ {wf.name.upper()} Completed ({res.total_duration_seconds}s)[/bold green]",
                        border_style="green",
                    )
                )
                console.print()
            except Exception as exc:
                console.print(f"[red]Workflow error:[/red] {exc}")
            return True

        if cmd in ("/copy", "/yank"):
            sub_args = parts[1:] if len(parts) > 1 else []
            self._run_copy(sub_args)
            return True

        if cmd == "/save":
            out_file = Path(parts[1].strip()) if len(parts) > 1 else None
            saved = self.session.save_transcript(out_file)
            console.print(f"[green]✓ Conversation transcript saved to:[/green] [bold cyan]{saved}[/bold cyan]")
            return True

        if cmd in ("/doctor", "/check"):
            self._run_doctor()
            return True

        if cmd == "/init":
            force = len(parts) > 1 and parts[1].strip().lower() in ("--force", "-f", "force")
            self._run_init(force=force)
            return True

        if cmd in ("/audit", "/log", "/tools"):
            sub_arg = parts[1] if len(parts) > 1 else None
            extra_arg = parts[2] if len(parts) > 2 else None
            self._run_audit(sub_arg, extra_arg)
            return True

        if cmd in ("/rule", "/rules", "/learn", "/glossary"):
            self._run_rule(parts[1:])
            return True

        if cmd in ("/git", "/sync"):
            self._run_git(parts[1:])
            return True

        console.print(f"[yellow]Unknown command '{cmd}'. Type [bold cyan]/help[/bold cyan] for available commands.[/yellow]")
        return True

    def _run_copy(self, args: list[str]) -> None:
        """Copies the last AI assistant response or specific code block to OS clipboard."""
        if not self.last_ai_reply:
            console.print(t("tui.copy_no_ai_response"))
            return

        arg0 = args[0].strip().lower() if args else "all"

        if arg0 == "list":
            if not self.last_code_blocks:
                console.print(t("tui.copy_no_code_block"))
                return
            tbl = Table(title=t("tui.copy_blocks_title"), box=box.ROUNDED)
            tbl.add_column("#", style="bold yellow", justify="center", width=4)
            tbl.add_column(t("tui.copy_col_lang"), style="bold cyan", width=12)
            tbl.add_column(t("tui.copy_col_lines"), justify="right", width=8)
            tbl.add_column(t("tui.copy_col_preview"), style="dim")
            for b in self.last_code_blocks:
                preview = b["code"].splitlines()[0] if b["code"] else ""
                if len(preview) > 60:
                    preview = preview[:57] + "..."
                tbl.add_row(str(b["index"]), b["language"].upper(), str(b["lines"]), preview)
            console.print()
            console.print(tbl)
            console.print(t("tui.copy_how_to"))
            return

        # Check if user specified a block number (e.g. /copy 1, /copy 2)
        if arg0.isdigit():
            idx = int(arg0) - 1
            if idx < 0 or idx >= len(self.last_code_blocks):
                console.print(t("tui.block_not_found", index=arg0, total=len(self.last_code_blocks)))
                return
            block = self.last_code_blocks[idx]
            ok, msg = copy_to_clipboard(block["code"])
            if ok:
                console.print(t("tui.block_copied", index=block["index"], lang=block["language"].upper(), lines=block["lines"]))
            else:
                console.print(f"[red]✕ {msg}[/red]\n")
            return

        # Check if user specified /copy code, /copy sql, /copy plsql
        if arg0 in ("code", "sql", "plsql", "python", "json"):
            target_lang = "sql" if arg0 == "plsql" else arg0
            matching = [
                b
                for b in self.last_code_blocks
                if (target_lang == "code" or b["language"] == target_lang or (target_lang == "sql" and "sql" in b["language"]))
            ]
            if not matching:
                if self.last_code_blocks:
                    matching = [self.last_code_blocks[0]]
                else:
                    console.print(t("tui.no_code_block"))
                    return
            block = matching[0]
            ok, msg = copy_to_clipboard(block["code"])
            if ok:
                console.print(t("tui.block_copied", index=block["index"], lang=block["language"].upper(), lines=block["lines"]))
            else:
                console.print(f"[red]✕ {msg}[/red]\n")
            return

        # Default: copy entire text
        ok, msg = copy_to_clipboard(self.last_ai_reply)
        if ok:
            console.print(t("tui.reply_copied", chars=len(self.last_ai_reply)))
        else:
            console.print(f"[red]✕ {msg}[/red]\n")

    def _get_storage(self) -> Any:
        """Resolves SeaweedFSStorage if configured and enabled or endpoint provided."""
        cfg = self.config.storage.seaweedfs
        if cfg.enabled or cfg.endpoint_url:
            from leai.storage import SeaweedFSStorage

            try:
                return SeaweedFSStorage(cfg)
            except Exception:
                return None
        return None

    def _run_rule(self, args: list[str]) -> None:
        """Manages the global business glossary and domain rules."""
        from rich.prompt import Prompt

        from leai.glossary import add_or_update_term, delete_term, load_glossary, search_glossary
        from leai.models import GlossaryTerm

        subcmd = args[0].lower() if args else "list"

        if subcmd in ("list", "ls"):
            storage = self._get_storage()
            glossary = None
            if storage:
                try:
                    remote_glossary = storage.load_glossary()
                    if remote_glossary.terms:
                        local_glossary = load_glossary(self.config.annotationsPath)
                        from leai.glossary import merge_glossaries

                        glossary = merge_glossaries(remote_glossary, local_glossary)
                except Exception:
                    pass

            if glossary is None:
                glossary = load_glossary(self.config.annotationsPath)

            if not glossary.terms:
                console.print(t("rule.empty"))
                console.print(t("rule.hint_add"))
                return

            tbl = Table(title=t("rule.table_title"), box=box.ROUNDED)
            tbl.add_column(t("rule.col_term"), style="bold yellow", width=22)
            tbl.add_column(t("rule.col_table"), style="bold cyan", width=16)
            tbl.add_column(t("rule.col_filter"), style="green", width=34)
            tbl.add_column(t("rule.col_definition"), style="white")

            for t_item in glossary.terms:
                tbl.add_row(
                    t_item.term,
                    t_item.primary_table or "-",
                    t_item.canonical_filter or "-",
                    t_item.definition,
                )
            console.print()
            console.print(tbl)
            s3_tag = t("rule.synced_s3_tag", bucket=self.config.storage.seaweedfs.bucket) if storage else ""
            console.print(t("rule.total_terms", count=len(glossary.terms), path=self.config.annotationsPath, tag=s3_tag))
            return

        if subcmd in ("find", "search"):
            if len(args) < 2:
                console.print(t("rule.search_usage"))
                return
            query = " ".join(args[1:])
            glossary = load_glossary(self.config.annotationsPath)
            matches = search_glossary(glossary, query)
            if not matches:
                console.print(t("rule.not_found", query=query))
                return

            tbl = Table(title=t("rule.search_title", query=query), box=box.ROUNDED)
            tbl.add_column(t("rule.col_term"), style="bold yellow")
            tbl.add_column(t("rule.col_table"), style="bold cyan")
            tbl.add_column(t("rule.col_filter"), style="green")
            tbl.add_column(t("rule.col_definition"), style="white")
            for term, score in matches:
                tbl.add_row(term.term, term.primary_table or "-", term.canonical_filter or "-", term.definition)
            console.print()
            console.print(tbl)
            console.print()
            return

        if subcmd in ("add", "new"):
            console.print(t("rule.add_header"))
            term_name = " ".join(args[1:]).strip() if len(args) > 1 else ""
            if not term_name:
                term_name = Prompt.ask(t("rule.prompt_term"))
            if not term_name.strip():
                console.print(t("rule.cancelled_term_req"))
                return

            definition = Prompt.ask(t("rule.prompt_definition"))
            primary_table = Prompt.ask(t("rule.prompt_table"), default="")
            canonical_filter = Prompt.ask(
                t("rule.prompt_filter"),
                default="",
            )
            tags_str = Prompt.ask(t("rule.prompt_tags"), default="")
            tags = [tag.strip() for tag in tags_str.split(",") if tag.strip()]

            new_term = GlossaryTerm(
                term=term_name.strip(),
                definition=definition.strip(),
                primary_table=primary_table.strip().upper() if primary_table.strip() else None,
                canonical_filter=canonical_filter.strip() if canonical_filter.strip() else None,
                tags=tags,
            )

            storage = self._get_storage()
            add_or_update_term(self.config.annotationsPath, new_term, storage=storage)
            s3_msg = f" and synchronized with SeaweedFS bucket '[bold]{self.config.storage.seaweedfs.bucket}[/bold]'" if storage else ""
            console.print(t("rule.saved", term=new_term.term, path=f"{self.config.annotationsPath}/glossary.yml", s3_msg=s3_msg))
            console.print(t("rule.ai_hint"))
            return

        if subcmd in ("del", "delete", "rm"):
            if len(args) < 2:
                console.print(t("rule.del_usage"))
                return
            term_to_del = " ".join(args[1:]).strip()
            storage = self._get_storage()
            removed = delete_term(self.config.annotationsPath, term_to_del, storage=storage)
            if removed:
                s3_msg = f" and from SeaweedFS bucket '{self.config.storage.seaweedfs.bucket}'" if storage else ""
                console.print(t("rule.deleted", term=term_to_del, path=f"{self.config.annotationsPath}/glossary.yml", s3_msg=s3_msg))
            else:
                console.print(t("rule.del_not_found", term=term_to_del))
            return

        console.print(t("rule.general_usage"))

    def _run_git(self, args: list[str]) -> None:
        """Manages Git and GitLab repository synchronization for database metadata."""
        from leai.git_ops import get_git_status, git_pull, git_sync

        subcmd = args[0].lower() if args else "status"

        if subcmd in ("status", "st", "info"):
            with console.status(t("git.checking_status"), spinner="dots"):
                info = get_git_status(fetch=True)

            if not info.is_repo:
                console.print(t("git.not_repo"))
                console.print(t("git.init_hint"))
                return

            tbl = Table(title=t("tui.git_tbl_title", platform=info.platform_name), box=box.ROUNDED)
            tbl.add_column(t("tui.git_col_prop"), style="bold yellow", width=22)
            tbl.add_column(t("tui.git_col_val"), style="white")

            tbl.add_row(t("tui.git_row_platform"), f"[bold green]{info.platform_name}[/bold green]")
            tbl.add_row(t("tui.git_row_branch"), f"[bold cyan]{info.branch}[/bold cyan]")
            tbl.add_row(t("tui.git_row_remote"), info.remote_url or t("tui.git_no_remote"))

            sync_status = []
            if info.behind > 0:
                sync_status.append(t("tui.git_behind_commits", count=info.behind))
            if info.ahead > 0:
                sync_status.append(t("tui.git_ahead_commits", count=info.ahead))
            if not sync_status:
                sync_status.append(t("tui.git_synced_status"))
            tbl.add_row(t("tui.git_row_sync"), ", ".join(sync_status))

            mod_count = len(info.modified_files)
            untr_count = len(info.untracked_files)
            changes_desc = []
            if mod_count > 0:
                changes_desc.append(t("tui.git_files_modified", count=mod_count))
            if untr_count > 0:
                changes_desc.append(t("tui.git_files_untracked", count=untr_count))
            if not changes_desc:
                changes_desc.append(t("tui.git_clean_working_tree"))
            tbl.add_row(t("tui.git_row_changes"), ", ".join(changes_desc))

            console.print()
            console.print(tbl)

            if info.modified_files or info.untracked_files:
                console.print(t("git.changed_files"))
                for f in (info.modified_files + info.untracked_files)[:8]:
                    console.print(f"  [dim yellow]• {f}[/dim yellow]")
                if len(info.modified_files + info.untracked_files) > 8:
                    console.print(t("git.and_more_files", count=len(info.modified_files + info.untracked_files) - 8))
                console.print(t("git.hint_sync"))
            else:
                console.print()
            return

        if subcmd in ("pull", "update", "fetch"):
            console.print(t("git.pulling"))
            ok, msg = git_pull()
            if ok:
                console.print(f"[green]✓ {msg}[/green]")
                target_schemas_filter = self.config.schemas if not self.config.is_all_schemas else None
                self.schemas = load_raw_schemas(self.config.rawPath, target_schemas=target_schemas_filter)
                self.completer.update_schemas(self.schemas)
                self.session.update_schemas(self.schemas)
                console.print(t("git.reloaded_memory"))
            else:
                console.print(t("git.pull_error", error=msg))
            return

        if subcmd in ("sync", "push", "commit"):
            commit_msg = " ".join(args[1:]).strip() if len(args) > 1 else None
            console.print(t("git.syncing"))
            ok, msg = git_sync(message=commit_msg)
            if ok:
                console.print(f"[green]✓ {msg}[/green]\n")
            else:
                console.print(t("git.sync_error", error=msg))
            return

        console.print(t("git.usage"))

    def _run_doc(self, object_name: str | None = None) -> None:
        """Launches the in-terminal interactive documentation editor."""
        if not self.schemas:
            console.print("[yellow]! No database metadata loaded. Please run [bold cyan]/extract[/bold cyan] first.[/yellow]\n")
            return

        # /doc saves strictly to local disk (no SeaweedFS sync)
        editor = DocEditor(self.config, self.schemas)
        saved = editor.run(object_name)
        if saved:
            # Refresh schemas and completer cache while preserving conversation history
            target_schemas_filter = self.config.schemas if not self.config.is_all_schemas else None
            self.schemas = load_raw_schemas(self.config.rawPath, target_schemas=target_schemas_filter)
            self.completer.update_schemas(self.schemas)
            self.session.update_schemas(self.schemas)

    def _run_extract(self, schemas_arg: list[str] | None = None, days: int | None = None) -> None:
        """Extracts metadata snapshots from Oracle into rawPath and/or SeaweedFS."""
        import oracledb

        from leai.storage import SeaweedFSStorage

        if not self.config.dsn:
            console.print("[red]✕ DSN is not configured in leai.yml or LEAI_DSN env var.[/red]\n")
            return

        extract_cfg = self.config.model_copy()
        target_schemas_input = []
        seaweed_flag = False
        no_cache_flag = False
        force_upload_flag = False

        if schemas_arg:
            for s in schemas_arg:
                s_clean = s.strip()
                s_lower = s_clean.lower()
                if s_lower in ("--seaweed", "-w"):
                    seaweed_flag = True
                elif s_lower == "--no-cache":
                    no_cache_flag = True
                elif s_lower in ("--force-upload", "-f", "--force"):
                    force_upload_flag = True
                elif s_clean.isdigit() and days is None:
                    days = int(s_clean)
                elif s_clean.startswith(("--days=", "-d=")):
                    try:
                        days = int(s_clean.split("=")[1])
                    except Exception:
                        pass
                elif s_clean not in ("--days", "-d"):
                    target_schemas_input.append(s_clean.upper())

        if target_schemas_input:
            extract_cfg.schemas = target_schemas_input

        # Resolve SeaweedFS storage
        use_seaweed = seaweed_flag or extract_cfg.storage.seaweedfs.enabled
        is_no_cache = no_cache_flag or extract_cfg.storage.seaweedfs.no_cache

        storage: SeaweedFSStorage | None = None
        if use_seaweed:
            try:
                storage = SeaweedFSStorage(extract_cfg.storage.seaweedfs)
                storage.ensure_bucket_exists()
                mode_tags = []
                if is_no_cache:
                    mode_tags.append("Remote-only")
                if extract_cfg.storage.seaweedfs.incremental and not force_upload_flag:
                    mode_tags.append("SHA-256 Incremental")
                elif force_upload_flag:
                    mode_tags.append("Force Upload")
                tag_str = f" [dim]({', '.join(mode_tags)})[/dim]" if mode_tags else ""
                console.print(
                    f"[cyan]SeaweedFS Storage:[/cyan] [bold green]Active[/bold green] (Endpoint: {extract_cfg.storage.seaweedfs.endpoint_url}, Bucket: {extract_cfg.storage.seaweedfs.bucket}){tag_str}\n"
                )
            except Exception as exc:
                console.print(f"[red]SeaweedFS error:[/red] {exc}\n")
                if is_no_cache:
                    return
                console.print("[yellow]Falling back to local-only extraction.[/yellow]\n")
                storage = None
        elif is_no_cache:
            console.print("[red]Error:[/red] --no-cache requires SeaweedFS to be enabled (use --seaweed or enable it in leai.yml).\n")
            return

        total_s3_uploaded = 0
        total_s3_skipped = 0

        start_time = time.perf_counter()
        try:
            with console.status("[cyan]Connecting to Oracle database...[/cyan]", spinner="dots"):
                connection = oracledb.connect(**_build_connect_kwargs(extract_cfg.dsn))
            try:
                target_schemas = fetch_available_schemas(connection, extract_cfg)

                is_multi = len(target_schemas) > 1 or extract_cfg.is_all_schemas
                days_banner = f" • [bold yellow]Incremental (last {days} days)[/bold yellow]" if days else ""
                console.print(
                    f"[cyan]Extracting metadata for schema(s):[/cyan] [bold yellow]{', '.join(target_schemas)}[/bold yellow] ({len(target_schemas)} total){days_banner}\n"
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

                        def _cb(cat: str, count: int, step_idx: int, total_steps: int, s_title=s_name, obj_count=schema_obj_count) -> None:
                            if count > 0:
                                obj_count[0] += count
                            pct = int((step_idx / total_steps) * 100) if total_steps else 100
                            progress.update(
                                schema_task,
                                completed=pct,
                                total=100,
                                description=f"Extracting [bold yellow]{s_title}[/bold yellow] [[bold cyan]{pct}%[/bold cyan]] ({obj_count[0]:,} objects) [dim]│ {cat}[/dim]",
                            )

                        schema_meta = fetch_schema_metadata(extract_cfg, schema_name=s_name, callback=_cb, days=days, connection=connection)
                        save_raw_schema(
                            schema_meta,
                            extract_cfg.rawPath,
                            multi_schema=True,
                            storage=storage,
                            local_cache=not is_no_cache,
                            force_upload=force_upload_flag,
                        )
                        if storage and hasattr(storage, "last_save_result") and storage.last_save_result:
                            total_s3_uploaded += getattr(storage.last_save_result, "uploaded", 0)
                            total_s3_skipped += getattr(storage.last_save_result, "skipped", 0)

                        total_tables += len(schema_meta.tables)
                        total_views += len(schema_meta.views)
                        total_code += len(schema_meta.code_objects)

                        if overall_task is not None:
                            progress.update(
                                overall_task,
                                advance=1,
                                description=f"[bold cyan]Overall Pipeline[/bold cyan] ({s_idx}/{len(target_schemas)} schemas)",
                            )
            finally:
                connection.close()

            elapsed = time.perf_counter() - start_time

            # Reload internal state while preserving conversation history
            target_schemas_filter = self.config.schemas if not self.config.is_all_schemas else None
            self.schemas = load_raw_schemas(
                self.config.rawPath,
                target_schemas=target_schemas_filter,
                storage=storage,
                local_cache=not is_no_cache,
            )
            self.completer.update_schemas(self.schemas)
            self.session.update_schemas(self.schemas)

            dest_display = (
                "[bold magenta]SeaweedFS S3 (remote-only)[/bold magenta]"
                if is_no_cache
                else f"[bold cyan]{self.config.rawPath}[/bold cyan]"
            )
            panel_lines = [
                f"[green]✓ {len(target_schemas)} Schemas Extracted[/green]",
                f"[green]✓ {total_tables} Tables • {total_views} Views • {total_code} Code Objects[/green]",
                f"[bold]Elapsed:[/bold] {elapsed:.2f}s • [bold]Snapshot Destination:[/bold] {dest_display}",
            ]
            if storage:
                panel_lines.append(
                    f"[bold cyan]SeaweedFS S3:[/bold cyan] [bold green]{total_s3_uploaded}[/bold green] uploaded • [dim]{total_s3_skipped} skipped (identical SHA-256)[/dim] • Bucket: [bold]{extract_cfg.storage.seaweedfs.bucket}[/bold]"
                )
            panel_lines.append(
                "\n[dim]Tip: You can now run [bold cyan]/doc <TABLE>[/bold cyan] to document objects or ask questions directly![/dim]"
            )

            console.print(
                Panel(
                    "\n".join(panel_lines),
                    title="[bold green]RAW Extraction Completed[/bold green]",
                    border_style="green",
                )
            )
        except Exception as exc:
            console.print(f"[red]Error during extraction:[/red] {exc}\n")

    def _run_update(self, args: list[str] | None = None) -> None:
        """Fast incremental update of modified objects from Oracle, merges schemas, syncs annotations, and pushes delta to SeaweedFS."""
        import oracledb

        from leai.docs import count_schema_objects, sync_schema_annotations, write_schema_docs
        from leai.oracle import _build_connect_kwargs, fetch_available_schemas, fetch_schema_metadata
        from leai.raw import merge_schema_metadata, save_raw_schema
        from leai.storage import SeaweedFSStorage

        if not self.config.dsn:
            console.print("[red]✕ DSN is not configured in leai.yml or LEAI_DSN env var.[/red]\n")
            return

        update_cfg = self.config.model_copy()
        target_schemas_input = []
        seaweed_flag = False
        no_cache_flag = False
        force_upload_flag = False
        compile_flag = False
        hours_val: float | None = None
        days_val: float | None = None

        if args:
            for a in args:
                s_clean = a.strip()
                s_lower = s_clean.lower()
                if s_lower in ("--seaweed", "-w"):
                    seaweed_flag = True
                elif s_lower in ("--compile", "-c"):
                    compile_flag = True
                elif s_lower == "--no-cache":
                    no_cache_flag = True
                elif s_lower in ("--force-upload", "-f", "--force"):
                    force_upload_flag = True
                elif s_lower.endswith("h"):
                    try:
                        hours_val = float(s_lower[:-1])
                    except Exception:
                        pass
                elif s_lower.endswith("d"):
                    try:
                        days_val = float(s_lower[:-1])
                    except Exception:
                        pass
                elif s_clean.startswith(("--hours=", "-h=")):
                    try:
                        hours_val = float(s_clean.split("=")[1])
                    except Exception:
                        pass
                elif s_clean.startswith(("--days=", "-d=")):
                    try:
                        days_val = float(s_clean.split("=")[1])
                    except Exception:
                        pass
                elif s_clean.isdigit():
                    days_val = float(s_clean)
                elif s_clean not in ("--hours", "-h", "--days", "-d"):
                    target_schemas_input.append(s_clean.upper())

        if target_schemas_input:
            update_cfg.schemas = target_schemas_input

        if hours_val is None and days_val is None:
            days_val = 1.0

        time_desc = f"last {hours_val:g} hours" if hours_val else f"last {days_val:g} days"

        use_seaweed = seaweed_flag or update_cfg.storage.seaweedfs.enabled
        is_no_cache = no_cache_flag or update_cfg.storage.seaweedfs.no_cache

        storage: SeaweedFSStorage | None = None
        if use_seaweed:
            try:
                storage = SeaweedFSStorage(update_cfg.storage.seaweedfs)
                storage.ensure_bucket_exists()
                mode_tags = []
                if is_no_cache:
                    mode_tags.append("Remote-only")
                if update_cfg.storage.seaweedfs.incremental and not force_upload_flag:
                    mode_tags.append("SHA-256 Incremental")
                elif force_upload_flag:
                    mode_tags.append("Force Upload")
                tag_str = f" [dim]({', '.join(mode_tags)})[/dim]" if mode_tags else ""
                console.print(
                    f"[cyan]SeaweedFS Storage:[/cyan] [bold green]Active[/bold green] (Endpoint: {update_cfg.storage.seaweedfs.endpoint_url}, Bucket: {update_cfg.storage.seaweedfs.bucket}){tag_str}\n"
                )
            except Exception as exc:
                console.print(f"[red]SeaweedFS error:[/red] {exc}\n")
                if is_no_cache:
                    return
                console.print("[yellow]Falling back to local-only update.[/yellow]\n")
                storage = None
        elif is_no_cache:
            console.print("[red]Error:[/red] --no-cache requires SeaweedFS to be enabled (use --seaweed or enable it in leai.yml).\n")
            return

        total_s3_uploaded = 0
        total_s3_skipped = 0
        total_ann = 0
        total_md = 0
        total_modified = 0

        start_time = time.perf_counter()
        try:
            with console.status(
                f"[cyan]Querying Oracle for objects modified in [bold yellow]{time_desc}[/bold yellow]...[/cyan]",
                spinner="dots",
            ) as status:
                connection = oracledb.connect(**_build_connect_kwargs(update_cfg.dsn))
                try:
                    target_schemas = fetch_available_schemas(connection, update_cfg)
                    total_schemas = len(target_schemas)

                    for s_idx, schema_name in enumerate(target_schemas, 1):
                        schema_t0 = time.perf_counter()
                        prefix = f"[{schema_name} ({s_idx}/{total_schemas})]"

                        with LiveStatusTicker(
                            status,
                            prefix=prefix,
                            t0=schema_t0,
                            initial_msg=f"Consultando alterações ({time_desc})...",
                        ) as ticker:

                            def _on_meta_progress(step_name: str, count: int, current_step: int, total_steps: int) -> None:
                                ticker.update(f"Extraindo {step_name}...")

                            schema_meta = fetch_schema_metadata(
                                update_cfg,
                                schema_name=schema_name,
                                callback=_on_meta_progress,
                                days=days_val,
                                hours=hours_val,
                                connection=connection,
                            )
                            num_objs = count_schema_objects(schema_meta, update_cfg.object_types)
                            schema_dur = time.perf_counter() - schema_t0

                            if num_objs == 0:
                                console.print(
                                    f"  [dim]• Schema [bold]{schema_name}[/bold]: no modifications in {time_desc} ({schema_dur:.1f}s).[/dim]"
                                )
                                continue

                            console.print(
                                f"  [green]✓[/green] Schema [bold yellow]{schema_name}[/bold yellow]: [bold green]{num_objs} modified object(s)[/bold green] found ({schema_dur:.1f}s)."
                            )

                            def _on_s3_progress(done: int, total: int) -> None:
                                msg = t("cli.syncing_seaweedfs", done=done, total=total)
                                ticker.update(msg)

                            ticker.update(t("cli.saving_raw"))

                            # 1. Save delta RAW and merge with existing snapshot
                            save_raw_schema(
                                schema_meta,
                                update_cfg.rawPath,
                                multi_schema=True,
                                storage=storage,
                                local_cache=not is_no_cache,
                                force_upload=force_upload_flag,
                                is_delta=True,
                                progress_callback=_on_s3_progress,
                            )
                            if storage and hasattr(storage, "last_save_result"):
                                total_s3_uploaded += getattr(storage.last_save_result, "uploaded", 0)
                                total_s3_skipped += getattr(storage.last_save_result, "skipped", 0)

                            ticker.update(t("cli.syncing_annotations"))

                            # 2. Sync annotations ONLY for modified objects (preserves existing comments)
                            gen_ann = sync_schema_annotations(
                                schema_meta,
                                annotations_path=update_cfg.annotationsPath,
                                multi_schema=True,
                                object_types=update_cfg.object_types,
                                storage=storage,
                            )
                            total_ann += len(gen_ann)

                            # 3. Optional compilation for modified objects
                            if compile_flag:
                                ticker.update(t("cli.compiling_docs"))
                                gen_md, _ = write_schema_docs(
                                    schema_meta,
                                    doc_path=update_cfg.docPath,
                                    annotations_path=update_cfg.annotationsPath,
                                    docs_overrides=update_cfg.docs,
                                    multi_schema=True,
                                    object_types=update_cfg.object_types,
                                )
                                total_md += len(gen_md)

                        # 4. Update in-memory schema metadata in TUI session
                        found_idx = -1
                        for idx, existing_s in enumerate(self.schemas):
                            if existing_s.schema_name.upper() == schema_name.upper():
                                found_idx = idx
                                break
                        if found_idx >= 0:
                            self.schemas[found_idx] = merge_schema_metadata(self.schemas[found_idx], schema_meta)
                        else:
                            self.schemas.append(schema_meta)
                finally:
                    connection.close()

                if storage:
                    status.update(f"[cyan]{t('cli.syncing_glossary')}[/cyan]")
                    try:
                        storage.sync_glossary(update_cfg.annotationsPath, no_cache=is_no_cache)
                    except Exception as exc:
                        console.print(f"[yellow]Warning: Could not synchronize glossary with SeaweedFS: {exc}[/yellow]")

            # Refresh completer cache with any newly discovered objects
            if hasattr(self, "completer") and self.completer:
                self.completer.update_schemas(self.schemas)

            elapsed = time.perf_counter() - start_time
            panel_lines = [
                f"[green]✓ Incremental Update Completed ({time_desc})[/green]",
                f"[bold]Modified Objects:[/bold] {total_modified} • [bold]Annotations Synced:[/bold] {total_ann} stubs",
            ]
            if compile_flag:
                panel_lines.append(f"[bold]Docs Compiled:[/bold] {total_md} Markdown files")
            if storage:
                panel_lines.append(
                    f"[bold cyan]SeaweedFS S3:[/bold cyan] [bold green]{total_s3_uploaded}[/bold green] versioned • [dim]{total_s3_skipped} skipped[/dim] • Bucket: [bold]{update_cfg.storage.seaweedfs.bucket}[/bold]"
                )
            panel_lines.append(f"[bold]Elapsed:[/bold] {elapsed:.2f}s • [dim]In-memory AI catalog refreshed.[/dim]")

            console.print(
                Panel(
                    "\n".join(panel_lines),
                    title="[bold green]✦ Incremental Update Succeeded[/bold green]",
                    border_style="green",
                )
            )
        except Exception as exc:
            console.print(f"[red]Error during incremental update:[/red] {exc}\n")

    def _run_seaweed(self, sub_arg: str = "status") -> None:
        """Manages SeaweedFS S3 storage connection, push, and pull."""
        from leai.storage import SeaweedFSStorage

        cfg = self.config.storage.seaweedfs
        if not cfg.enabled and not cfg.endpoint_url:
            console.print(
                "[yellow]! SeaweedFS is not configured in leai.yml.[/yellow]\n"
                "[dim]Configure storage.seaweedfs in leai.yml or set LEAI_SEAWEED_ENDPOINT to use S3 storage.[/dim]\n"
            )
            return

        storage = SeaweedFSStorage(cfg)

        if sub_arg == "status":
            with console.status("[cyan]Testing SeaweedFS connection...[/cyan]", spinner="dots"):
                res = storage.test_connection()

            table = Table(title="SeaweedFS S3 Storage Status", show_header=True, header_style="bold cyan", box=box.ROUNDED)
            table.add_column("Property", style="bold")
            table.add_column("Value")
            table.add_row("Endpoint URL", res.get("endpoint", cfg.endpoint_url))
            table.add_row("Bucket", res.get("bucket", cfg.bucket))
            status_style = "bold green" if res.get("success") else "bold red"
            status_text = "OPERATIONAL" if res.get("success") else "FAILED"
            table.add_row("Connection Status", f"[{status_style}]{status_text}[/{status_style}]")
            if res.get("objects_found") is not None:
                table.add_row("Objects Found", str(res["objects_found"]))
            if res.get("message"):
                table.add_row("Details", res["message"])
            table.add_row("Raw Prefix", cfg.raw_prefix)
            table.add_row("Annotations Prefix", cfg.annotations_prefix)
            table.add_row("Incremental SHA-256", "Enabled" if cfg.incremental else "Disabled")
            table.add_row("Remote-only (no_cache)", "Yes" if cfg.no_cache else "No")
            console.print(table)
            console.print()
            return

        if sub_arg == "push":
            with console.status("[cyan]Pushing local metadata to SeaweedFS...[/cyan]", spinner="dots"):
                try:
                    res = storage.push_local_to_remote(self.config.rawPath, self.config.annotationsPath)
                    console.print(
                        f"[green]✓ Successfully uploaded {res.get('raw', 0)} RAW JSON files and {res.get('annotations', 0)} YAML annotation files to SeaweedFS bucket '{cfg.bucket}'.[/green]\n"
                    )
                except Exception as exc:
                    console.print(f"[red]Push failed:[/red] {exc}\n")
            return

        if sub_arg == "pull":
            with console.status("[cyan]Pulling remote metadata from SeaweedFS...[/cyan]", spinner="dots"):
                try:
                    res = storage.pull_remote_to_local(self.config.rawPath, self.config.annotationsPath)
                    console.print(
                        f"[green]✓ Successfully downloaded {res.get('raw', 0)} RAW JSON files and {res.get('annotations', 0)} YAML annotation files from SeaweedFS bucket '{cfg.bucket}'.[/green]\n"
                    )
                    target_schemas_filter = self.config.schemas if not self.config.is_all_schemas else None
                    self.schemas = load_raw_schemas(self.config.rawPath, target_schemas=target_schemas_filter)
                    self.completer.update_schemas(self.schemas)
                    self.session.update_schemas(self.schemas)
                except Exception as exc:
                    console.print(f"[red]Pull failed:[/red] {exc}\n")
            return

        if sub_arg == "sync":
            with console.status("[cyan]Synchronizing metadata with SeaweedFS...[/cyan]", spinner="dots"):
                try:
                    pushed = storage.push_local_to_remote(self.config.rawPath, self.config.annotationsPath)
                    pulled = storage.pull_remote_to_local(self.config.rawPath, self.config.annotationsPath)
                    console.print(
                        f"[green]✓ Pushed {pushed.get('raw', 0)} RAW, {pushed.get('annotations', 0)} annotations[/green]\n"
                        f"[green]✓ Pulled {pulled.get('raw', 0)} RAW, {pulled.get('annotations', 0)} annotations from '{cfg.bucket}'[/green]\n"
                    )
                    target_schemas_filter = self.config.schemas if not self.config.is_all_schemas else None
                    self.schemas = load_raw_schemas(self.config.rawPath, target_schemas=target_schemas_filter)
                    self.completer.update_schemas(self.schemas)
                    self.session.update_schemas(self.schemas)
                except Exception as exc:
                    console.print(f"[red]Sync failed:[/red] {exc}\n")
            return

        console.print(f"[yellow]Unknown /seaweed subcommand '{sub_arg}'. Available: status, push, pull, sync.[/yellow]\n")

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

    def _run_annotate(self, args: list[str] | None = None) -> None:
        """Synchronizes YAML annotation stubs in annotationsPath and/or SeaweedFS."""
        if not self.schemas:
            console.print("[yellow]! No database snapshots found in raw/. Run [bold cyan]/extract[/bold cyan] first.[/yellow]\n")
            return

        seaweed_flag = False
        no_cache_flag = False
        if args:
            for a in args:
                a_lower = a.strip().lower()
                if a_lower in ("--seaweed", "-w"):
                    seaweed_flag = True
                elif a_lower == "--no-cache":
                    no_cache_flag = True

        # Resolve SeaweedFS storage
        use_seaweed = seaweed_flag or self.config.storage.seaweedfs.enabled
        is_no_cache = no_cache_flag or self.config.storage.seaweedfs.no_cache

        storage = None
        if is_no_cache and not use_seaweed:
            console.print("[red]✕ Error:[/red] --no-cache requires SeaweedFS to be enabled (use --seaweed or enable it in leai.yml).\n")
            return

        if use_seaweed:
            from leai.storage import SeaweedFSStorage

            try:
                storage = SeaweedFSStorage(self.config.storage.seaweedfs)
                storage.ensure_bucket_exists()
                mode_tags = []
                if is_no_cache:
                    mode_tags.append("Remote-only")
                tag_str = f" [dim]({', '.join(mode_tags)})[/dim]" if mode_tags else ""
                console.print(
                    f"[cyan]SeaweedFS Storage:[/cyan] [bold green]Active[/bold green] (Endpoint: {self.config.storage.seaweedfs.endpoint_url}, Bucket: {self.config.storage.seaweedfs.bucket}){tag_str}\n"
                )
            except Exception as exc:
                console.print(f"[red]SeaweedFS error:[/red] {exc}\n")
                if is_no_cache:
                    return
                console.print("[yellow]Falling back to local-only annotation sync.[/yellow]\n")
                storage = None

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
                        storage=storage,
                    )
                    total_ann += len(gen_ann)

                    if overall_task is not None:
                        progress.update(
                            overall_task,
                            advance=1,
                            description=f"[bold cyan]Overall Synchronization[/bold cyan] ({s_idx}/{len(self.schemas)} schemas)",
                        )

            if storage:
                try:
                    storage.sync_glossary(self.config.annotationsPath, no_cache=is_no_cache)
                except Exception as exc:
                    console.print(f"[yellow]Warning: Could not synchronize glossary with SeaweedFS: {exc}[/yellow]")

            elapsed = time.perf_counter() - start_time
            storage_info = (
                f"\n[bold]SeaweedFS:[/bold] [bold cyan]{self.config.storage.seaweedfs.bucket}/{self.config.storage.seaweedfs.annotations_prefix}[/bold cyan]"
                if storage
                else ""
            )
            console.print(
                Panel(
                    f"[green]✓ {total_ann} YAML Annotation Stubs Synchronized[/green]\n"
                    f"[bold]Elapsed:[/bold] {elapsed:.2f}s • [bold]Destination:[/bold] [bold cyan]{self.config.annotationsPath}[/bold cyan]{storage_info}\n\n"
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
            for tbl in s.tables:
                if not target_upper or tbl.name.upper() == target_upper:
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
                try:
                    self.web_server.server_close()
                except Exception:
                    pass
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

            storage = None
            if self.config.storage.seaweedfs.enabled:
                from leai.storage import SeaweedFSStorage

                try:
                    storage = SeaweedFSStorage(self.config.storage.seaweedfs)
                    storage.ensure_bucket_exists()
                except Exception:
                    storage = None

            if (not self.schemas) and storage:
                try:
                    with console.status(t("seaweedfs.sync_catalog"), spinner="dots") as status:
                        is_no_cache = getattr(self.config.storage.seaweedfs, "no_cache", False)
                        target_schemas = self.config.schemas if not self.config.is_all_schemas else None
                        loaded = load_raw_schemas(
                            self.config.rawPath, target_schemas=target_schemas, storage=storage, local_cache=not is_no_cache
                        )
                        if loaded:
                            self.schemas = loaded
                            from leai.tui.completer import LeaiCompleter

                            self.completer = LeaiCompleter(self.schemas, config=self.config)
                        status.update(f"[bold green]✓ {t('seaweedfs.catalog_synced')}[/bold green]")
                        import time

                        time.sleep(0.4)
                except Exception as e:
                    console.print(f"[yellow]Warning loading schemas from SeaweedFS: {e}[/yellow]")

            self.web_server, self.web_url = start_server(
                config=self.config,
                schemas=self.schemas,
                client=self.client,
                provider_name=self.provider_name,
                port=port,
                open_browser=True,
                in_background=True,
                storage=storage,
            )
            console.print()
            sw_note = (
                f"\n[bold white]SeaweedFS S3:[/bold white] [bold green]Active[/bold green] [dim]({self.config.storage.seaweedfs.bucket})[/dim]"
                if storage
                else ""
            )
            console.print(
                Panel(
                    f"[bold cyan]⚡ LEAI Web Documentation & Annotation Studio[/bold cyan]\n\n"
                    f"[bold white]URL:[/bold white] [bold yellow underline]{self.web_url}[/bold yellow underline]{sw_note}\n"
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
            f"[green]✓ Documentation Store:[/green] [cyan]{ann_count}[/cyan] annotations in [bold]{self.config.annotationsPath}[/bold] • [cyan]{doc_count}[/cyan] docs in [bold]{self.config.docPath}[/bold]"
        )

        # 5. Check SeaweedFS S3 Storage
        if getattr(self.config, "storage", None) and self.config.storage.seaweedfs.enabled:
            try:
                from leai.storage import SeaweedFSStorage

                sw_storage = SeaweedFSStorage(self.config.storage.seaweedfs)
                res = sw_storage.test_connection()
                status_str = "OK" if res.get("success") else "Failed"
                objs = res.get("objects_found", 0)
                console.print(
                    f"[green]✓ SeaweedFS S3 Storage:[/green] [bold]{status_str}[/bold] (Bucket: {self.config.storage.seaweedfs.bucket}, Objects: {objs})"
                )
            except Exception as exc:
                console.print(f"[yellow]! SeaweedFS Warning:[/yellow] {exc}")

        # 6. Check Git / GitLab Status
        try:
            from leai.git_ops import get_git_status

            git_info = get_git_status(fetch=False)
            if git_info.is_repo:
                plat = git_info.platform_name
                sync_desc = f"{git_info.behind} behind" if git_info.behind > 0 else "up to date"
                console.print(
                    f"[green]✓ Git Repository ({plat}):[/green] branch [bold]{git_info.branch}[/bold] • {sync_desc} • {len(git_info.modified_files)} modified\n"
                )
            else:
                console.print("[dim]! Git Repository: not inside a git working tree[/dim]\n")
        except Exception:
            console.print()

    def _run_doctor(self) -> None:
        """Executes full diagnostic pre-flight health check (alias for /check)."""
        self._run_check()

    def _run_init(self, force: bool = False) -> None:
        """Informs or initializes leai.yml with interactive overwrite confirmation."""
        from leai.i18n import get_locale, t
        from leai.template import write_default_config

        out_file = Path("leai.yml")
        if out_file.exists() and not force:
            console.print(t("tui.config_exists", path=out_file.resolve()))
            try:
                overwrite = Confirm.ask(t("tui.overwrite_prompt"), default=False)
            except (EOFError, KeyboardInterrupt, OSError):
                console.print(t("tui.operation_cancelled"))
                return
            if not overwrite:
                console.print(t("tui.operation_cancelled_kept"))
                return

        write_default_config(out_file, overwrite=True, lang=get_locale())
        console.print(t("tui.config_created", path=out_file.resolve()))
        console.print(t("tui.config_created_hint"))

    def _render_help(self) -> None:
        from leai.i18n import get_locale

        is_pt = get_locale() == "pt-BR"

        table = Table(show_header=True, header_style="bold #74c7ec", box=box.ROUNDED)
        table.add_column(t("tui.help_col_command"), style="bold #f9e2af", width=22)
        table.add_column(t("tui.help_col_category"), style="dim #9399b2", width=14)
        table.add_column(t("tui.help_col_description"), style="#cdd6f4")

        rows = [
            (
                "/doc [obj]",
                "Documentação" if is_pt else "Documentation",
                "Editor interativo no terminal para anotações YAML e documentação"
                if is_pt
                else "Interactive terminal editor for YAML annotations and docs",
            ),
            (
                "/rule [list|add|find]",
                "Glossário" if is_pt else "Glossary",
                "Gerencia regras canônicas de negócio e termos do glossário"
                if is_pt
                else "Manage global business rules and canonical domain filters",
            ),
            (
                "/enrich [obj]",
                "Estúdio IA" if is_pt else "AI Studio",
                "Preenche automaticamente descrições e regras de negócio com IA"
                if is_pt
                else "Auto-enrich descriptions and business rules with AI",
            ),
            (
                "/compile [obj]",
                "Pipeline",
                "Compila documentação Markdown em docs/ (suporta objeto único)"
                if is_pt
                else "Compile final Markdown files into docs/ (supports single object)",
            ),
            (
                "/annotate [-W]",
                "Pipeline",
                "Sincroniza anotações YAML em annotations/ e/ou SeaweedFS"
                if is_pt
                else "Synchronize YAML annotation stubs into annotations/ and/or SeaweedFS",
            ),
            (
                "/extract [s] [d] [-W]",
                "Pipeline",
                "Extrai snapshot do Oracle (suporta schema, dias, --seaweed, --no-cache)"
                if is_pt
                else "Extract Oracle snapshot (supports schema, days, --seaweed, --no-cache, --force-upload)",
            ),
            (
                "/update [h|d] [-W] [-C]",
                "Pipeline",
                "Atualização incremental rápida de objetos alterados recentemente"
                if is_pt
                else "Fast incremental update of recently modified objects, stubs & S3",
            ),
            (
                "/seaweed [status|push|pull|sync]",
                "SeaweedFS",
                "Verifica status do S3, envia, baixa ou sincroniza metadados"
                if is_pt
                else "Check SeaweedFS S3 status, push, pull, or bi-directional sync",
            ),
            (
                "/serve [port|stop]",
                "Web Studio",
                "Inicia o Web Studio com editor no navegador e sincronização ao vivo"
                if is_pt
                else "Launch Web Studio with browser editor and live sync",
            ),
            (
                "/git [status|pull|sync]",
                "Git/GitLab",
                "Verifica status, sincroniza ou faz commit e push de documentação"
                if is_pt
                else "Check sync status, pull updates, or commit & push metadata",
            ),
            (
                "/trace <obj>",
                "Linhagem" if is_pt else "Lineage",
                "Rastreia dependências e exibe grafo de impacto de arquitetura"
                if is_pt
                else "Run dependency tracing and X-ray architecture graph",
            ),
            (
                "/tables",
                "Inspeção" if is_pt else "Inspection",
                "Lista todas as tabelas com contagem de colunas e chaves primárias"
                if is_pt
                else "List all tables with column counts and primary keys",
            ),
            (
                "/schema [s]",
                "Inspeção" if is_pt else "Inspection",
                "Exibe visão geral detalhada do catálogo do schema" if is_pt else "Display detailed catalog overview for schema",
            ),
            (
                "/changes [d]",
                "Inspeção" if is_pt else "Inspection",
                "Inspeciona objetos modificados nos últimos N dias (padrão: 7)"
                if is_pt
                else "Inspect objects modified in the last N days (default: 7)",
            ),
            (
                "/agent <role> <task>",
                "Multi-Agente" if is_pt else "Multi-Agent",
                "Executa subagente especialista diretamente (catalog, plsql, lineage, patch, doc)"
                if is_pt
                else "Directly execute specialized subagent (catalog, plsql, lineage, patch, doc)",
            ),
            (
                "/workflow <name> <obj>",
                "Workflows",
                "Executa workflow autônomo multi-etapas (impact, refactor)" if is_pt else "Execute autonomous pipeline (impact, refactor)",
            ),
            (
                "/models [p]",
                "Config IA" if is_pt else "AI Config",
                "Lista modelos de IA disponíveis na API do provedor" if is_pt else "List available AI models from the provider API",
            ),
            (
                "/model <p> [m]",
                "Config IA" if is_pt else "AI Config",
                "Alterna o provedor de IA (openai, gemini, grok, etc.) e modelo"
                if is_pt
                else "Switch provider (openai, gemini, grok, etc.) and model",
            ),
            (
                "/doctor, /check",
                "Diagnóstico" if is_pt else "Diagnostics",
                "Diagnóstico preventivo de conectividade Oracle, IA, Storage e Git"
                if is_pt
                else "Pre-flight health check on Oracle, AI, Storage, and Git",
            ),
            (
                "/init",
                "Configuração" if is_pt else "Setup",
                "Verifica ou inicializa o arquivo de configuração leai.yml"
                if is_pt
                else "Check or initialize the leai.yml configuration file",
            ),
            (
                "/copy [all|code|N]",
                "Clipboard",
                "Copia última resposta da IA ou bloco de código para o clipboard"
                if is_pt
                else "Copy last AI response or specific code block to OS clipboard",
            ),
            (
                "/audit [last|session|export]",
                "Auditoria" if is_pt else "Audit",
                "Inspeciona traces de ferramentas, raciocínio, latência e logs"
                if is_pt
                else "Inspect AI tool traces, reasoning, latency, and logs",
            ),
            (
                "/tools",
                "Auditoria" if is_pt else "Audit",
                "Visualizador rápido de payloads de entrada/saída de ferramentas"
                if is_pt
                else "Quick viewer for tool input/output payload inspection",
            ),
            (
                "/save [file.md]",
                "Sessão" if is_pt else "Session",
                "Exporta transcrição da conversa para um arquivo Markdown"
                if is_pt
                else "Export conversation transcript to a Markdown file",
            ),
            (
                "/clear",
                "Sessão" if is_pt else "Session",
                "Limpa a memória do chat e reseta a tela do terminal" if is_pt else "Reset chat memory and clear terminal screen",
            ),
            (
                "/chat <msg>",
                "Copilot",
                "Envia uma pergunta para o assistente de IA (ou digite direto)"
                if is_pt
                else "Send a query to the AI assistant (or type directly)",
            ),
            (
                "/help",
                "Referência" if is_pt else "Reference",
                "Exibe este guia interativo de comandos" if is_pt else "Display this interactive command guide",
            ),
            (
                "/exit, /quit",
                "Sessão" if is_pt else "Session",
                "Encerra a sessão interativa do copilot" if is_pt else "Exit interactive copilot session",
            ),
        ]

        for cmd, cat, desc in rows:
            table.add_row(cmd, cat, desc)

        console.print()
        console.print(
            Panel(
                table,
                title=f"[bold #cba6f7]{t('tui.help_title')}[/bold #cba6f7]",
                box=box.ROUNDED,
                border_style="#74c7ec",
            )
        )
        console.print(f"[dim #9399b2]{t('tui.help_tip')}[/dim #9399b2]\n")

    def _render_models_table(self, provider_name: str | None = None, interactive: bool = True) -> None:
        target_prov = (provider_name or self.provider_name or "openai").lower()
        try:
            temp_client = (
                self.client
                if target_prov == (self.provider_name or "").lower()
                else get_llm_client(self.config, provider_override=target_prov)
            )
            with console.status(
                f"[#74c7ec]Fetching available models from [bold #f9e2af]{target_prov.upper()}[/bold #f9e2af] API...[/#74c7ec]",
                spinner="dots",
            ):
                models_list = temp_client.list_models()
        except Exception as exc:
            console.print(f"[red]Could not fetch models for {target_prov.upper()}:[/red] {exc}\n")
            return

        if not models_list:
            console.print(f"[yellow]No models returned for {target_prov.upper()}.[/yellow]\n")
            return

        table = Table(show_header=True, header_style="bold #74c7ec", box=box.ROUNDED)
        table.add_column("#", justify="right", style="#74c7ec", width=4)
        table.add_column("Status", justify="center", width=8)
        table.add_column("Model ID", style="bold #f9e2af")
        table.add_column("Display Name", style="#cdd6f4")
        table.add_column("Description / Notes", style="dim #9399b2")

        for idx, m in enumerate(models_list, 1):
            m_id = m.get("id", "")
            is_active = target_prov == (self.provider_name or "").lower() and m_id == self.client.model
            status_badge = "[bold #a6e3a1]ACTIVE[/bold #a6e3a1]" if is_active else "[dim #6c7086]-[/dim #6c7086]"
            table.add_row(f"[{idx}]", status_badge, m_id, m.get("name", m_id), m.get("description", m.get("note", "")))

        console.print()
        console.print(
            Panel(
                table,
                title=f"[bold #cba6f7]✦ Available Models for {target_prov.upper()} ({len(models_list)} Total)[/bold #cba6f7]",
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
        table.add_column(t("tui.tables_col_schema"), style="yellow")
        table.add_column(t("tui.tables_col_table"), style="bold white")
        table.add_column(t("tui.tables_col_cols"), justify="right", style="cyan")
        table.add_column(t("tui.tables_col_pks"), style="green")
        table.add_column(t("tui.tables_col_comment"), style="dim")

        total = 0
        for s in self.schemas:
            s_name = s.schema_name or "DEFAULT"
            for tbl in s.tables:
                total += 1
                pks = ", ".join(tbl.primary_keys) if tbl.primary_keys else "-"
                comm = (tbl.comment or "").strip()
                if len(comm) > 60:
                    comm = comm[:57] + "..."
                table.add_row(s_name, tbl.name, str(len(tbl.columns)), pks, comm)

        console.print()
        console.print(
            Panel(table, title=f"[bold green]{t('tui.tables_title', total=total)}[/bold green]", box=box.ROUNDED, border_style="green")
        )
        console.print()

    def _render_schema_summary(self) -> None:
        for s in self.schemas:
            s_name = s.schema_name or "DEFAULT"
            tbl = Table(show_header=True, header_style="bold cyan", box=box.ROUNDED)
            tbl.add_column(t("tui.schema_summary_col_type"), style="bold white")
            tbl.add_column(t("tui.schema_summary_col_count"), justify="right", style="bold green")

            tbl.add_row("Tables", str(len(s.tables)))
            tbl.add_row("Views", str(len(s.views)))
            tbl.add_row("Materialized Views", str(len(s.mviews)))
            tbl.add_row("Code Objects (Packages/Procedures)", str(len(s.code_objects)))
            tbl.add_row("Triggers", str(len(s.triggers)))
            tbl.add_row("Sequences", str(len(s.sequences)))
            tbl.add_row("Indexes", str(len(s.indexes)))
            tbl.add_row("Synonyms", str(len(s.synonyms)))

            console.print()
            console.print(
                Panel(
                    tbl,
                    title=f"[bold yellow]{t('tui.schema_summary_title', schema=s_name)}[/bold yellow]",
                    box=box.ROUNDED,
                    border_style="yellow",
                )
            )
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
        self.last_ai_reply = reply
        self.last_code_blocks = extract_code_blocks(reply)

        # Record in Session Audit Logger
        turn_audit = self.audit_logger.record_turn(
            user_prompt=user_input,
            ai_response=reply,
            system_prompt=getattr(self.session, "last_system_prompt", ""),
            rag_context=getattr(self.session, "last_rag_context", ""),
            messages=getattr(self.session, "last_working_messages", []),
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
        rag_badge = f" • RAG: {', '.join(detected)}" if detected else ""

        # Render response in clean borderless Markdown format (no vertical box chars to interfere with mouse selection)
        console.print()
        console.print(
            f"[bold #a6e3a1]✦ LEAI Assistant[/bold #a6e3a1] [dim #6c7086]({self.provider_name.upper()} • {self.client.model}){rag_badge}[/dim #6c7086]"
        )
        console.print(Rule(style="#45475a"))
        console.print()
        console.print(Markdown(reply, code_theme="monokai"))
        console.print()
        console.print(Rule(style="#313244"))

        # Footer stats & Smart copy hint
        if self.last_code_blocks:
            c_count = len(self.last_code_blocks)
            first_lang = self.last_code_blocks[0]["language"].upper()
            code_hint = t("tui.copy_code_single", lang=first_lang) if c_count == 1 else t("tui.copy_code_multi", count=c_count)
        else:
            code_hint = ""

        console.print(
            t(
                "tui.copy_tip",
                latency=self.last_latency,
                turn_tokens=turn_tok_str,
                tool_badge=tool_badge,
                code_hint=code_hint,
            )
        )

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
