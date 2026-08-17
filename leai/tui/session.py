from __future__ import annotations

import os
import time
from datetime import datetime, timedelta
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory, InMemoryHistory
from rich import box
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.tree import Tree

from leai.ai import get_llm_client
from leai.ai.base import BaseLLMClient
from leai.chat_session import ChatSession
from leai.config import LeaiConfig
from leai.docs import _calculate_risk_level, write_dossier_doc
from leai.models import SchemaMetadata
from leai.raw import trace_raw_dependencies
from leai.tui.completer import LeaiCompleter
from leai.tui.styles import PT_STYLE

console = Console()


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
        self.completer = LeaiCompleter(schemas)

        # Setup persistent history
        hist_dir = Path.home() / ".leai"
        try:
            hist_dir.mkdir(parents=True, exist_ok=True)
            self.history = FileHistory(str(hist_dir / "chat_history"))
        except Exception:
            self.history = InMemoryHistory()

        try:
            self.prompt_session = PromptSession(
                history=self.history,
                completer=self.completer,
                style=PT_STYLE,
                auto_suggest=AutoSuggestFromHistory(),
                complete_while_typing=True,
            )
        except Exception:
            from prompt_toolkit.output import DummyOutput
            self.prompt_session = PromptSession(
                history=self.history,
                completer=self.completer,
                style=PT_STYLE,
                auto_suggest=AutoSuggestFromHistory(),
                complete_while_typing=True,
                output=DummyOutput(),
            )

    def _get_bottom_toolbar(self) -> HTML:
        """Renders dynamic OpenCode bottom status bar."""
        schemas_count = len(self.schemas)
        schema_text = f"{schemas_count} schemas" if schemas_count > 1 else (self.schemas[0].schema_name if self.schemas else "None")
        msg_count = len(self.session.messages)
        latency_str = f"{self.last_latency:.2f}s" if self.last_latency is not None else "ready"

        return HTML(
            f" <b>LEAI Copilot</b> │ "
            f"Schema: <b><style fg='#f9e2af'>{schema_text}</style></b> │ "
            f"Model: <b><style fg='#a6e3a1'>{self.provider_name}:{self.client.model}</style></b> │ "
            f"Latency: <style fg='#9399b2'>{latency_str}</style> │ "
            f"History: <b>{msg_count}</b> msgs "
        )

    def print_welcome_banner(self) -> None:
        """Displays sleek OpenCode header banner."""
        total_tables = sum(len(s.tables) for s in self.schemas)
        total_views = sum(len(s.views) for s in self.schemas)
        total_code = sum(len(s.code_objects) for s in self.schemas)
        total_triggers = sum(len(s.triggers) for s in self.schemas)

        schemas_str = ", ".join(s.schema_name for s in self.schemas) if self.schemas else "All Schemas"
        header_content = (
            f"[bold cyan]✦ LEAI Interactive Studio[/bold cyan] [dim]v{self._get_version()}[/dim]\n"
            f"[dim]Oracle Database AI Assistant with Deep Lineage & RAG Impact Graph[/dim]\n\n"
            f"[bold white]Active Schema:[/bold white] [bold yellow]{schemas_str}[/bold yellow]  •  "
            f"[bold white]AI Model:[/bold white] [bold green]{self.provider_name.upper()} ({self.client.model})[/bold green]\n"
            f"[dim]Catalog Index:[/dim] [cyan]{total_tables}[/cyan] Tables • [cyan]{total_views}[/cyan] Views • [cyan]{total_code}[/cyan] Code Objects • [cyan]{total_triggers}[/cyan] Triggers\n\n"
            f"[dim]Quick Start:[/dim] Type [bold cyan]/help[/bold cyan] for slash commands or [bold cyan]@[/bold cyan] to autocomplete tables/procedures."
        )

        console.print()
        console.print(
            Panel(
                header_content,
                box=box.ROUNDED,
                border_style="cyan",
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
            elif len(parts) == 2 and parts[1].lower() in ("openai", "gemini", "anthropic", "deepseek", "qwen", "kimi", "ollama"):
                # List models for specified provider
                self._render_models_table(parts[1].lower())
            else:
                # Switch provider and/or model
                if len(parts) >= 3:
                    new_prov = parts[1].lower()
                    new_model = parts[2]
                elif parts[1].lower() in ("openai", "gemini", "anthropic", "deepseek", "qwen", "kimi", "ollama"):
                    new_prov = parts[1].lower()
                    new_model = None
                else:
                    new_prov = self.provider_name
                    new_model = parts[1]

                try:
                    self.client = get_llm_client(self.config, provider_override=new_prov, model_override=new_model)
                    self.provider_name = new_prov
                    self.session.client = self.client
                    console.print(f"[green]✓ Switched AI client to [bold]{new_prov.upper()}[/bold] (Model: [bold cyan]{self.client.model}[/bold cyan])[/green]")
                except Exception as exc:
                    console.print(f"[red]Failed to switch model:[/red] {exc}")
            return True

        if cmd == "/save":
            out_file = Path(parts[1].strip()) if len(parts) > 1 else None
            saved = self.session.save_transcript(out_file)
            console.print(f"[green]✓ Conversation transcript saved to:[/green] [bold cyan]{saved}[/bold cyan]")
            return True

        console.print(f"[yellow]Unknown command '{cmd}'. Type [bold cyan]/help[/bold cyan] for available commands.[/yellow]")
        return True

    def _render_models_table(self, provider_name: str | None = None, interactive: bool = True) -> None:
        target_prov = (provider_name or self.provider_name or "openai").lower()
        try:
            temp_client = self.client if target_prov == (self.provider_name or "").lower() else get_llm_client(self.config, provider_override=target_prov)
            with console.status(f"[cyan]Fetching available models from [bold yellow]{target_prov.upper()}[/bold yellow] API...[/cyan]", spinner="dots"):
                models_list = temp_client.list_models()
        except Exception as exc:
            console.print(f"[red]Could not fetch models for {target_prov.upper()}:[/red] {exc}\n")
            return

        if not models_list:
            console.print(f"[yellow]No models returned for {target_prov.upper()}.[/yellow]\n")
            return

        table = Table(show_header=True, header_style="bold cyan", box=box.ROUNDED)
        table.add_column("#", justify="right", style="cyan", width=4)
        table.add_column("Status", justify="center", width=8)
        table.add_column("Model ID", style="bold yellow")
        table.add_column("Display Name", style="white")
        table.add_column("Description / Notes", style="dim")

        for idx, m in enumerate(models_list, 1):
            m_id = m.get("id", "")
            is_active = (target_prov == (self.provider_name or "").lower() and m_id == self.client.model)
            status_badge = "[bold green]ACTIVE[/bold green]" if is_active else "[dim]-[/dim]"
            table.add_row(f"[{idx}]", status_badge, m_id, m.get("name", m_id), m.get("description", m.get("note", "")))

        console.print()
        console.print(Panel(table, title=f"[bold cyan]✦ Available Models for {target_prov.upper()} ({len(models_list)} Total)[/bold cyan]", box=box.ROUNDED, border_style="cyan"))

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
                        console.print(f"[green]✓ Switched AI client to [bold]{target_prov.upper()}[/bold] (Model: [bold cyan]{self.client.model}[/bold cyan])[/green]\n")
                    else:
                        console.print(f"[red]Invalid selection: '{choice}'[/red]\n")
            except (KeyboardInterrupt, EOFError):
                console.print()
        else:
            console.print(f"[dim]To switch model, type: [bold cyan]/model {target_prov} <model_id>[/bold cyan][/dim]\n")

    def _render_help(self) -> None:
        table = Table(show_header=True, header_style="bold cyan", box=box.ROUNDED)
        table.add_column("Command", style="bold yellow", width=18)
        table.add_column("Description", style="white")
        table.add_row("/trace <obj>", "Perform inline dependency lineage & impact X-ray")
        table.add_row("/tables", "List all tables with column counts and primary keys")
        table.add_row("/schema", "Show comprehensive overview of all catalog objects")
        table.add_row("/changes [days]", "Inspect database objects modified in last N days (default: 7)")
        table.add_row("/models [prov]", "List all available AI models returned by the API key")
        table.add_row("/model <p> [m]", "Switch AI provider and/or model on the fly")
        table.add_row("/save [file.md]", "Export current session conversation to Markdown")
        table.add_row("/clear", "Clear session context memory and reset screen")
        table.add_row("/help", "Show this interactive command guide")
        table.add_row("/exit, /quit", "Exit LEAI interactive copilot")

        console.print()
        console.print(Panel(table, title="[bold cyan]✦ LEAI Interactive Commands Reference[/bold cyan]", box=box.ROUNDED, border_style="cyan"))
        console.print()

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
        console.print(Panel(table, title=f"[bold green]✦ Database Tables ({total} Total)[/bold green]", box=box.ROUNDED, border_style="green"))
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
        console.print(Panel(table, title=f"[bold green]✦ Objects Modified in the Last {days} Days ({len(results)} Found)[/bold green]", box=box.ROUNDED, border_style="green"))
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

    def run(self) -> None:
        """Main interaction loop."""
        self.print_welcome_banner()

        while True:
            try:
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

                # Query AI Assistant with animated status spinner and live tool execution display
                start_t = time.perf_counter()
                tool_calls_executed = []

                def _on_tool_start(t_name: str, t_args: dict) -> None:
                    tool_calls_executed.append(t_name)
                    args_str = ", ".join(f"{k}={v}" for k, v in t_args.items())
                    console.print(f"[dim cyan]  ⚙️ Investigating:[/dim cyan] [bold yellow]{t_name}[/bold yellow]({args_str})")

                with console.status(
                    f"[cyan]Thinking with [bold yellow]{self.provider_name.upper()}[/bold yellow] ([bold green]{self.client.model}[/bold green])...[/cyan]",
                    spinner="dots",
                ):
                    reply, detected = self.session.send(
                        user_input,
                        on_tool_start=_on_tool_start,
                    )
                self.last_latency = time.perf_counter() - start_t

                # Display detected entities in RAG context or tools executed
                if tool_calls_executed:
                    console.print(f"[dim]🛠️ Tools Executed: [bold yellow]{', '.join(tool_calls_executed)}[/bold yellow][/dim]")
                elif detected:
                    console.print(f"[dim]🔍 Active RAG Context: [bold yellow]{', '.join(detected)}[/bold yellow][/dim]")

                subtitle_str = (
                    f"[dim]⚡ {self.last_latency:.2f}s • {self.provider_name.upper()} ({self.client.model})"
                    f"{' • RAG: ' + ', '.join(detected) if detected else ''}[/dim]"
                )

                console.print()
                console.print(
                    Panel(
                        Markdown(reply),
                        title="[bold green]✦ LEAI Assistant[/bold green]",
                        subtitle=subtitle_str,
                        box=box.ROUNDED,
                        border_style="cyan",
                        padding=(1, 2),
                    )
                )
                console.print()

            except KeyboardInterrupt:
                console.print("\n[dim]KeyboardInterrupt: Press Ctrl+D or type /exit to quit.[/dim]")
                continue
            except EOFError:
                console.print("\n[yellow]✦ Goodbye![/yellow]")
                break
            except Exception as exc:
                console.print(f"\n[red]Error in interactive session:[/red] {exc}\n")
