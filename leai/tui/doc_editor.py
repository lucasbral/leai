import sys
from pathlib import Path
from typing import Callable

from prompt_toolkit import prompt
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn, TimeElapsedColumn
from rich.syntax import Syntax
from rich.table import Column, Table

from leai.annotations import ensure_annotation_stub, load_annotation, save_annotation
from leai.config import LeaiConfig
from leai.docs import count_schema_objects, write_schema_docs
from leai.models import ObjectAnnotation, SchemaMetadata

console = Console()


def _default_input_fn(label: str) -> str:
    if not sys.stdin or not getattr(sys.stdin, "isatty", lambda: False)():
        line = sys.stdin.readline() if sys.stdin else ""
        return line.rstrip("\r\n")
    return prompt(label)


def find_object_in_schemas(
    object_name: str,
    schemas: list[SchemaMetadata],
) -> tuple[SchemaMetadata | None, str | None, any]:
    """Finds an object by name (and optional SCHEMA.NAME) across loaded schemas."""
    target_clean = object_name.strip().lstrip("@").upper()
    target_schema = None
    target_obj = target_clean

    if "." in target_clean:
        parts = target_clean.split(".", maxsplit=1)
        target_schema = parts[0]
        target_obj = parts[1]

    for s in schemas:
        if target_schema and s.schema_name.upper() != target_schema:
            continue

        for t in s.tables:
            if t.name.upper() == target_obj:
                return s, "tables", t
        for v in s.views:
            if v.name.upper() == target_obj:
                return s, "views", v
        for mv in s.mviews:
            if mv.name.upper() == target_obj:
                return s, "mviews", mv
        for co in s.code_objects:
            if co.name.upper() == target_obj:
                cat = f"{co.object_type.lower()}s"
                if cat == "package bodys":
                    cat = "packages"
                elif cat == "type bodys":
                    cat = "types"
                return s, cat, co
        for tr in s.triggers:
            if tr.name.upper() == target_obj:
                return s, "triggers", tr
        for sq in s.sequences:
            if sq.name.upper() == target_obj:
                return s, "sequences", sq
        for sn in s.synonyms:
            if sn.name.upper() == target_obj:
                return s, "synonyms", sn

    return None, None, None


def resolve_annotation_path(
    config: LeaiConfig,
    schema_name: str,
    category: str,
    object_name: str,
    is_multi: bool,
) -> Path:
    """Returns the absolute file path to the YAML annotation for a given object."""
    if is_multi:
        return config.annotationsPath / schema_name / category / f"{object_name.upper()}.yml"
    return config.annotationsPath / category / f"{object_name.upper()}.yml"


def _calculate_doc_completeness(
    annotation: ObjectAnnotation,
    cols: list[str],
) -> tuple[int, str]:
    """Calculates completion percentage and visual progress bar."""
    score = 0.0
    has_desc = bool(annotation.description and annotation.description.strip())
    if has_desc:
        score += 35.0

    if cols:
        cols_done = sum(1 for c in cols if annotation.columns.get(c) and str(annotation.columns[c]).strip())
        score += (cols_done / len(cols)) * 35.0
    else:
        score += 35.0

    if annotation.business_rules:
        score += 20.0

    if annotation.tags:
        score += 10.0

    pct = int(min(100.0, score))
    blocks = int(pct / 10)
    bar = "█" * blocks + "░" * (10 - blocks)

    if pct >= 80:
        bar_str = f"[bold green]{bar} {pct}%[/bold green]"
    elif pct >= 40:
        bar_str = f"[bold yellow]{bar} {pct}%[/bold yellow]"
    else:
        bar_str = f"[bold red]{bar} {pct}%[/bold red]"

    return pct, bar_str


def _collect_all_objects(
    schemas: list[SchemaMetadata],
    config: LeaiConfig,
) -> list[dict]:
    """Collects and ranks all objects across schemas with doc status."""
    is_multi = len(schemas) > 1 or config.is_all_schemas
    items: list[dict] = []

    for s in schemas:
        s_name = s.schema_name or "MAIN"

        # Tables
        for t in s.tables:
            ann_file = resolve_annotation_path(config, s_name, "tables", t.name, is_multi)
            ann = load_annotation(ann_file) if ann_file.exists() else ObjectAnnotation()
            cols = [c.name for c in t.columns]
            pct, bar_str = _calculate_doc_completeness(ann, cols)
            pk_str = f"PK: {', '.join(t.primary_keys)}" if t.primary_keys else "No PK"
            items.append(
                {
                    "schema": s_name,
                    "category": "tables",
                    "type": "TABLE",
                    "name": t.name,
                    "obj_meta": t,
                    "cols": cols,
                    "details": f"{len(t.columns)} cols ({pk_str})",
                    "ann_file": ann_file,
                    "pct": pct,
                    "bar_str": bar_str,
                    "status": "[green]✓ Done[/green]" if pct == 100 else (f"[yellow]⚠️ {pct}%[/yellow]" if pct > 0 else "[red]❌ 0%[/red]"),
                }
            )

        # Views
        for v in s.views:
            ann_file = resolve_annotation_path(config, s_name, "views", v.name, is_multi)
            ann = load_annotation(ann_file) if ann_file.exists() else ObjectAnnotation()
            cols = [c.name for c in v.columns]
            pct, bar_str = _calculate_doc_completeness(ann, cols)
            items.append(
                {
                    "schema": s_name,
                    "category": "views",
                    "type": "VIEW",
                    "name": v.name,
                    "obj_meta": v,
                    "cols": cols,
                    "details": f"{len(v.columns)} cols",
                    "ann_file": ann_file,
                    "pct": pct,
                    "bar_str": bar_str,
                    "status": "[green]✓ Done[/green]" if pct == 100 else (f"[yellow]⚠️ {pct}%[/yellow]" if pct > 0 else "[red]❌ 0%[/red]"),
                }
            )

        # Materialized Views
        for mv in s.mviews:
            ann_file = resolve_annotation_path(config, s_name, "mviews", mv.name, is_multi)
            ann = load_annotation(ann_file) if ann_file.exists() else ObjectAnnotation()
            cols = [c.name for c in mv.columns]
            pct, bar_str = _calculate_doc_completeness(ann, cols)
            items.append(
                {
                    "schema": s_name,
                    "category": "mviews",
                    "type": "MVIEW",
                    "name": mv.name,
                    "obj_meta": mv,
                    "cols": cols,
                    "details": f"{len(mv.columns)} cols",
                    "ann_file": ann_file,
                    "pct": pct,
                    "bar_str": bar_str,
                    "status": "[green]✓ Done[/green]" if pct == 100 else (f"[yellow]⚠️ {pct}%[/yellow]" if pct > 0 else "[red]❌ 0%[/red]"),
                }
            )

        # Code Objects (Packages, Procedures, Functions, Types)
        for co in s.code_objects:
            cat = f"{co.object_type.lower()}s"
            if cat == "package bodys":
                cat = "packages"
            elif cat == "type bodys":
                cat = "types"
            ann_file = resolve_annotation_path(config, s_name, cat, co.name, is_multi)
            ann = load_annotation(ann_file) if ann_file.exists() else ObjectAnnotation()
            cols = [sp.name for sp in getattr(co, "subprograms", [])]
            pct, bar_str = _calculate_doc_completeness(ann, cols)
            if co.subprograms:
                details = f"{len(co.subprograms)} routines"
            elif co.source:
                details = f"{len(co.source.splitlines())} lines"
            else:
                details = "code"
            items.append(
                {
                    "schema": s_name,
                    "category": cat,
                    "type": co.object_type.upper(),
                    "name": co.name,
                    "obj_meta": co,
                    "cols": cols,
                    "details": details,
                    "ann_file": ann_file,
                    "pct": pct,
                    "bar_str": bar_str,
                    "status": "[green]✓ Done[/green]" if pct == 100 else (f"[yellow]⚠️ {pct}%[/yellow]" if pct > 0 else "[red]❌ 0%[/red]"),
                }
            )

        # Triggers
        for tr in s.triggers:
            ann_file = resolve_annotation_path(config, s_name, "triggers", tr.name, is_multi)
            ann = load_annotation(ann_file) if ann_file.exists() else ObjectAnnotation()
            pct, bar_str = _calculate_doc_completeness(ann, [])
            items.append(
                {
                    "schema": s_name,
                    "category": "triggers",
                    "type": "TRIGGER",
                    "name": tr.name,
                    "obj_meta": tr,
                    "cols": [],
                    "details": f"on {tr.table_name or 'DB'}",
                    "ann_file": ann_file,
                    "pct": pct,
                    "bar_str": bar_str,
                    "status": "[green]✓ Done[/green]" if pct == 100 else (f"[yellow]⚠️ {pct}%[/yellow]" if pct > 0 else "[red]❌ 0%[/red]"),
                }
            )

        # Sequences
        for sq in s.sequences:
            ann_file = resolve_annotation_path(config, s_name, "sequences", sq.name, is_multi)
            ann = load_annotation(ann_file) if ann_file.exists() else ObjectAnnotation()
            pct, bar_str = _calculate_doc_completeness(ann, [])
            items.append(
                {
                    "schema": s_name,
                    "category": "sequences",
                    "type": "SEQUENCE",
                    "name": sq.name,
                    "obj_meta": sq,
                    "cols": [],
                    "details": "Sequence",
                    "ann_file": ann_file,
                    "pct": pct,
                    "bar_str": bar_str,
                    "status": "[green]✓ Done[/green]" if pct == 100 else (f"[yellow]⚠️ {pct}%[/yellow]" if pct > 0 else "[red]❌ 0%[/red]"),
                }
            )

        # Synonyms
        for sn in s.synonyms:
            ann_file = resolve_annotation_path(config, s_name, "synonyms", sn.name, is_multi)
            ann = load_annotation(ann_file) if ann_file.exists() else ObjectAnnotation()
            pct, bar_str = _calculate_doc_completeness(ann, [])
            items.append(
                {
                    "schema": s_name,
                    "category": "synonyms",
                    "type": "SYNONYM",
                    "name": sn.name,
                    "obj_meta": sn,
                    "cols": [],
                    "details": f"-> {sn.table_owner or ''}.{sn.table_name or ''}",
                    "ann_file": ann_file,
                    "pct": pct,
                    "bar_str": bar_str,
                    "status": "[green]✓ Done[/green]" if pct == 100 else (f"[yellow]⚠️ {pct}%[/yellow]" if pct > 0 else "[red]❌ 0%[/red]"),
                }
            )

    return items


def _render_catalog_table(
    objects: list[dict],
    search_filter: str | None = None,
    page: int = 1,
    page_size: int = 12,
) -> tuple[Table, list[dict], int]:
    """Renders formatted catalog table with pagination and filtering."""
    filtered = objects
    if search_filter:
        q = search_filter.strip().lower()
        if q in ("pending", "pendente"):
            filtered = [o for o in objects if o["pct"] == 0]
        elif q in ("partial", "parcial"):
            filtered = [o for o in objects if 0 < o["pct"] < 100]
        elif q in ("done", "documented", "documentado"):
            filtered = [o for o in objects if o["pct"] == 100]
        else:
            filtered = [
                o
                for o in objects
                if q in o["name"].lower() or q in o["schema"].lower() or q in o["type"].lower() or q in f"{o['schema']}.{o['name']}".lower()
            ]

    total_items = len(filtered)
    total_pages = max(1, (total_items + page_size - 1) // page_size)
    curr_page = min(max(1, page), total_pages)
    start_idx = (curr_page - 1) * page_size
    page_items = filtered[start_idx : start_idx + page_size]

    filter_info = f" • Filter: '[bold yellow]{search_filter}[/bold yellow]'" if search_filter else ""
    table = Table(
        title=f"[bold cyan]✦ Database Objects Catalog ({total_items} objects{filter_info}) • Page {curr_page}/{total_pages}[/bold cyan]",
        box=box.ROUNDED,
        header_style="bold cyan",
        expand=True,
    )
    table.add_column("#", style="bold yellow", width=4, justify="right")
    table.add_column("Schema", style="bold yellow", width=12)
    table.add_column("Type", style="bold magenta", width=12)
    table.add_column("Object Name", style="bold white", ratio=2)
    table.add_column("Technical Details", style="dim", ratio=2)
    table.add_column("Doc Status", justify="center", width=18)

    type_color_map = {
        "TABLE": "cyan",
        "VIEW": "blue",
        "MVIEW": "blue",
        "PACKAGE": "magenta",
        "PACKAGE BODY": "magenta",
        "PROCEDURE": "yellow",
        "FUNCTION": "yellow",
        "TRIGGER": "red",
        "SEQUENCE": "dim",
        "SYNONYM": "dim",
    }

    for idx, item in enumerate(page_items, start=1):
        color = type_color_map.get(item["type"], "white")
        type_badge = f"[{color}]{item['type']}[/{color}]"
        table.add_row(
            str(idx),
            item["schema"],
            type_badge,
            item["name"],
            item["details"],
            item["bar_str"],
        )

    return table, page_items, total_pages


class DocEditor:
    """Interactive TUI Form to edit YAML annotations for database objects."""

    def __init__(
        self,
        config: LeaiConfig,
        schemas: list[SchemaMetadata],
        input_fn: Callable[[str], str] | None = None,
    ) -> None:
        self.config = config
        self.schemas = schemas
        self.input_fn = input_fn or _default_input_fn
        self.is_multi = len(schemas) > 1 or config.is_all_schemas

    def run(self, object_name_arg: str | None = None) -> bool:
        """Executes the interactive documentation editor. Returns True if saved."""
        target_name = object_name_arg

        if not target_name:
            all_objects = _collect_all_objects(self.schemas, self.config)
            if not all_objects:
                console.print("[yellow]! No database metadata loaded. Please run [bold cyan]/extract[/bold cyan] first.[/yellow]\n")
                return False

            current_page = 1
            current_filter = None

            while True:
                table, page_items, total_pages = _render_catalog_table(all_objects, search_filter=current_filter, page=current_page)
                console.print()
                console.print(table)
                console.print(
                    "[dim]Actions: Enter [bold cyan]# (e.g. 1)[/bold cyan] to select • [bold cyan]<NAME>[/bold cyan] or [bold cyan]<SCHEMA.NAME>[/bold cyan] • "
                    "Type text to search (e.g. [bold cyan]hr[/bold cyan], [bold cyan]table[/bold cyan], [bold cyan]pending[/bold cyan]) • "
                    "[bold cyan]n[/bold cyan]/[bold cyan]p[/bold cyan] for next/prev page • [bold red]0[/bold red] to exit[/dim]"
                )

                try:
                    user_choice = self.input_fn("Select object or action: ").strip()
                except (EOFError, KeyboardInterrupt):
                    console.print("\n[yellow]Documentation editing cancelled.[/yellow]")
                    return False

                if not user_choice or user_choice in ("0", "q", "exit", "cancel"):
                    console.print("[yellow]Exited documentation editor.[/yellow]\n")
                    return False

                if user_choice.lower() in ("n", "next"):
                    if current_page < total_pages:
                        current_page += 1
                    continue
                elif user_choice.lower() in ("p", "prev", "previous"):
                    if current_page > 1:
                        current_page -= 1
                    continue
                elif user_choice.lower() in ("c", "clear", "/clear"):
                    current_filter = None
                    current_page = 1
                    continue

                # Check if user typed a number
                if user_choice.isdigit():
                    idx_val = int(user_choice)
                    if 1 <= idx_val <= len(page_items):
                        target_name = f"{page_items[idx_val - 1]['schema']}.{page_items[idx_val - 1]['name']}"
                        break
                    else:
                        console.print(f"[yellow]! Invalid index. Enter between 1 and {len(page_items)}.[/yellow]")
                        continue

                # Check if user typed an exact object name (or schema.name)
                found_match = [
                    o
                    for o in all_objects
                    if o["name"].upper() == user_choice.upper() or f"{o['schema']}.{o['name']}".upper() == user_choice.upper()
                ]
                if found_match:
                    target_name = f"{found_match[0]['schema']}.{found_match[0]['name']}"
                    break

                # Otherwise, treat as search filter
                current_filter = user_choice
                current_page = 1

        if not target_name:
            console.print("[yellow]! No object specified.[/yellow]")
            return False

        schema, category, obj_meta = find_object_in_schemas(target_name, self.schemas)

        if not schema or not category or not obj_meta:
            console.print(f"[red]✕ Object '[bold]{target_name}[/bold]' not found in extracted schemas.[/red]")
            console.print(
                "[dim]Tip: Check available tables with [bold cyan]/tables[/bold cyan] or run [bold cyan]/extract[/bold cyan].[/dim]"
            )
            return False

        s_name = schema.schema_name or self.config.schema_name or "MAIN"
        o_name = getattr(obj_meta, "name", target_name).upper()
        type_label = getattr(obj_meta, "object_type", category.rstrip("s")).upper()
        ann_file = resolve_annotation_path(self.config, s_name, category, o_name, self.is_multi)

        # Collect columns or subprograms for column comments
        cols: list[str] = []
        if hasattr(obj_meta, "columns"):
            cols = [c.name for c in obj_meta.columns]
        elif hasattr(obj_meta, "subprograms"):
            cols = [sp.name for sp in obj_meta.subprograms]

        # Load or initialize annotation
        if ann_file.exists():
            annotation = load_annotation(ann_file)
            # Ensure missing columns are present
            for col in cols:
                if col not in annotation.columns:
                    annotation.columns[col] = ""
        else:
            db_comment = getattr(obj_meta, "comments", "") or ""
            annotation = ensure_annotation_stub(ann_file, db_comment=db_comment, column_names=cols)

        # Main interactive editing loop
        dirty = False
        while True:
            self._display_editor_header(s_name, category, o_name, type_label, ann_file, annotation, cols, obj_meta)
            choice = self._prompt_menu_choice()

            if choice in ("0", "q", "exit", "cancel"):
                if dirty:
                    confirm = self._prompt_text("You have unsaved changes. Discard and exit? [y/N]: ").strip().lower()
                    if confirm not in ("y", "yes", "s", "sim"):
                        continue
                console.print("[yellow]Exited documentation editor.[/yellow]\n")
                return False

            elif choice == "1":
                new_desc = self._edit_multiline_text("Object Description", annotation.description)
                if new_desc != annotation.description:
                    annotation.description = new_desc
                    dirty = True

            elif choice == "2":
                if cols:
                    if self._edit_columns_menu(annotation, cols, category):
                        dirty = True
                else:
                    console.print("[yellow]! This object type does not have column/subprogram items.[/yellow]")

            elif choice == "3":
                if self._edit_list_menu("Business Rules", annotation.business_rules):
                    dirty = True

            elif choice == "4":
                if self._edit_tags_menu(annotation):
                    dirty = True

            elif choice == "5":
                if self._edit_list_menu("Technical Warnings / Alerts", annotation.warnings):
                    dirty = True

            elif choice == "6":
                if self._edit_list_menu("Related Objects", annotation.related_objects):
                    dirty = True

            elif choice in ("7", "s", "save"):
                save_annotation(ann_file, annotation)
                self._display_save_success(ann_file, annotation)

                # Prompt to compile markdown doc for this specific object
                try:
                    recompile = self._prompt_text(f"Recompile Markdown doc for {o_name} now? [Y/n]: ").strip().lower()
                except Exception:
                    recompile = "y"

                if recompile in ("", "y", "yes", "s", "sim"):
                    self._recompile_docs(schema, target_object=o_name)

                return True

    def _display_editor_header(
        self,
        schema_name: str,
        category: str,
        object_name: str,
        type_label: str,
        ann_file: Path,
        annotation: ObjectAnnotation,
        cols: list[str],
        obj_meta: any,
    ) -> None:
        pct, bar_str = _calculate_doc_completeness(annotation, cols)

        table = Table(box=box.ROUNDED, expand=True, show_header=False)
        table.add_column("Field", style="bold cyan", width=22)
        table.add_column("Value", style="white")

        desc_preview = (
            (annotation.description[:120] + "...")
            if len(annotation.description or "") > 120
            else (annotation.description or "[dim italic]No description defined yet[/dim italic]")
        )
        cols_annotated = sum(1 for c in cols if annotation.columns.get(c) and str(annotation.columns[c]).strip())
        rules_count = len(annotation.business_rules)
        tags_str = ", ".join(annotation.tags) if annotation.tags else "[dim]None[/dim]"

        # Badges line
        badges = (
            f"[bold on #1e66f5 white] SCHEMA: {schema_name} [/]  "
            f"[bold on #8839ef white] TYPE: {type_label} [/]  "
            f"[bold on #df8e1d black] OBJECT: {object_name} [/]"
        )
        table.add_row("Context Badges", badges)
        table.add_row("Doc Completeness", bar_str)

        # Technical details
        if hasattr(obj_meta, "primary_keys") and obj_meta.primary_keys:
            table.add_row("Primary Keys", f"[bold yellow]{', '.join(obj_meta.primary_keys)}[/bold yellow]")
        if hasattr(obj_meta, "foreign_keys") and obj_meta.foreign_keys:
            table.add_row("Foreign Keys", f"[cyan]{len(obj_meta.foreign_keys)} FK constraints[/cyan]")
        if hasattr(obj_meta, "last_ddl_time") and obj_meta.last_ddl_time:
            table.add_row("Last DDL Time", f"[dim]{obj_meta.last_ddl_time}[/dim]")

        table.add_row("Annotation File", f"[dim]{ann_file}[/dim]")
        table.add_row("Description", desc_preview)
        if cols:
            item_label = "Subprograms" if category == "packages" else "Columns"
            table.add_row(f"{item_label} Annotated", f"[bold green]{cols_annotated}[/bold green] / {len(cols)}")
        table.add_row("Business Rules", f"[bold green]{rules_count}[/bold green] rules registered")
        table.add_row("Tags / Domain", tags_str)

        menu_text = (
            "[bold white]Select an action to edit:[/bold white]\n"
            "  [bold cyan]1[/bold cyan] • 📝 Edit Main Object Description\n"
            "  [bold cyan]2[/bold cyan] • 📊 Edit Column / Routine Comments\n"
            "  [bold cyan]3[/bold cyan] • 📌 Edit Business Rules (Bullet Points)\n"
            "  [bold cyan]4[/bold cyan] • 🏷️  Edit Tags & Functional Domain\n"
            "  [bold cyan]5[/bold cyan] • ⚠️  Edit Technical Warnings / Alerts\n"
            "  [bold cyan]6[/bold cyan] • 🔗 Edit Related Objects Lineage\n"
            "  [bold green]7[/bold green] • 💾 [bold green]Preview YAML & Save Changes[/bold green]\n"
            "  [bold red]0[/bold red] • ❌ Cancel & Back"
        )

        console.print()
        console.print(
            Panel(
                table,
                title=f"[bold cyan]✦ LEAI Documentation Studio • {schema_name}.{object_name} [{type_label}][/bold cyan]",
                border_style="cyan",
            )
        )
        console.print(Panel(menu_text, box=box.SIMPLE))

    def _prompt_menu_choice(self) -> str:
        try:
            return self.input_fn("Option [1-7, 0]: ").strip()
        except (EOFError, KeyboardInterrupt):
            return "0"

    def _prompt_text(self, label: str, default: str = "") -> str:
        try:
            val = self.input_fn(label)
            return val if val else default
        except (EOFError, KeyboardInterrupt):
            return default

    def _edit_multiline_text(self, label: str, current_value: str | None) -> str:
        console.print(f"\n[bold cyan]Edit {label}:[/bold cyan]")
        if current_value:
            console.print(f"[dim]Current value:\n{current_value}[/dim]\n")
        console.print("[dim](Type new description and press Enter. Leave blank to keep current)[/dim]")
        new_val = self._prompt_text(f"New {label}: ", default=current_value or "")
        return new_val.strip()

    def _edit_columns_menu(self, annotation: ObjectAnnotation, cols: list[str], category: str) -> bool:
        item_label = "Routine" if category == "packages" else "Column"
        dirty = False

        while True:
            table = Table(title=f"Annotate {item_label}s ({len(cols)} items)", box=box.ROUNDED)
            table.add_column("#", style="dim", justify="right", width=4)
            table.add_column(item_label, style="bold yellow")
            table.add_column("Business Description / Comment", style="white")

            for idx, col in enumerate(cols, 1):
                comment = annotation.columns.get(col, "")
                comment_disp = comment if comment else "[dim italic]-[/dim italic]"
                table.add_row(str(idx), col, comment_disp)

            console.print()
            console.print(table)
            console.print(f"[dim]Enter #{item_label} to edit (1-{len(cols)}), or 0 to finish:[/dim]")

            choice = self._prompt_text(f"Select {item_label} #: ")
            if choice in ("0", "q", "", "done", "back"):
                break

            try:
                idx = int(choice)
                if 1 <= idx <= len(cols):
                    target_col = cols[idx - 1]
                    cur_comment = annotation.columns.get(target_col, "")
                    console.print(f"\n[cyan]Editing {item_label}:[/cyan] [bold yellow]{target_col}[/bold yellow]")
                    if cur_comment:
                        console.print(f"[dim]Current comment: {cur_comment}[/dim]")
                    new_comment = self._prompt_text(f"Description for {target_col}: ", default=cur_comment)
                    annotation.columns[target_col] = new_comment.strip()
                    dirty = True
                    console.print(f"[green]✓ Updated {target_col}[/green]")
            except ValueError:
                console.print("[yellow]Invalid option. Enter a valid number.[/yellow]")

        return dirty

    def _edit_list_menu(self, title: str, items_list: list[str]) -> bool:
        dirty = False
        while True:
            table = Table(title=f"Edit {title} ({len(items_list)} registered)", box=box.ROUNDED)
            table.add_column("#", style="dim", justify="right", width=4)
            table.add_column("Content", style="white")

            for idx, item in enumerate(items_list, 1):
                table.add_row(str(idx), item)

            if not items_list:
                table.add_row("-", "[dim italic]No entries yet[/dim italic]")

            console.print()
            console.print(table)
            console.print(
                "[bold white]Actions:[/bold white] "
                "[bold cyan][+] Add new[/bold cyan] • "
                "[bold yellow][#] Edit existing[/bold yellow] • "
                "[bold red][d#] Delete (e.g. d1)[/bold red] • "
                "[bold green][0] Finish[/bold green]"
            )

            choice = self._prompt_text("Action: ").strip()
            if choice in ("0", "q", "", "done", "back"):
                break

            if choice in ("+", "add", "novo"):
                new_item = self._prompt_text("Enter new item: ").strip()
                if new_item:
                    items_list.append(new_item)
                    dirty = True
                    console.print(f"[green]✓ Added item #{len(items_list)}[/green]")
            elif choice.lower().startswith("d") and choice[1:].isdigit():
                idx_to_del = int(choice[1:])
                if 1 <= idx_to_del <= len(items_list):
                    removed = items_list.pop(idx_to_del - 1)
                    dirty = True
                    console.print(f"[red]✓ Removed: {removed}[/red]")
            elif choice.isdigit():
                idx = int(choice)
                if 1 <= idx <= len(items_list):
                    cur_val = items_list[idx - 1]
                    console.print(f"[dim]Current: {cur_val}[/dim]")
                    edited = self._prompt_text("New value: ", default=cur_val).strip()
                    if edited:
                        items_list[idx - 1] = edited
                        dirty = True
                        console.print(f"[green]✓ Updated item #{idx}[/green]")

        return dirty

    def _edit_tags_menu(self, annotation: ObjectAnnotation) -> bool:
        current_tags = ", ".join(annotation.tags) if annotation.tags else ""
        console.print("\n[bold cyan]Edit Tags / Functional Domain:[/bold cyan]")
        if current_tags:
            console.print(f"[dim]Current tags: {current_tags}[/dim]")
        console.print("[dim](Enter tags separated by commas, e.g.: Core, Financeiro, Faturamento)[/dim]")

        new_tags_raw = self._prompt_text("Tags: ", default=current_tags)
        parsed = [t.strip() for t in new_tags_raw.split(",") if t.strip()]
        if parsed != annotation.tags:
            annotation.tags = parsed
            console.print(f"[green]✓ Tags updated: {', '.join(parsed)}[/green]")
            return True
        return False

    def _display_save_success(self, ann_file: Path, annotation: ObjectAnnotation) -> None:
        import yaml

        yaml_content = yaml.safe_dump(
            annotation.model_dump(exclude_defaults=False),
            sort_keys=False,
            allow_unicode=True,
        )
        syntax = Syntax(yaml_content, "yaml", theme="monokai", line_numbers=True)

        console.print()
        console.print(
            Panel(
                syntax,
                title=f"[bold green]✓ Successfully Saved Annotation to {ann_file.name}[/bold green]",
                subtitle=f"[dim]{ann_file}[/dim]",
                border_style="green",
            )
        )

    def _recompile_docs(self, schema: SchemaMetadata, target_object: str | None = None) -> None:
        target_obj_up = target_object.strip().upper() if target_object else None
        total_objs = 1 if target_obj_up else count_schema_objects(schema, self.config.object_types)
        try:
            with Progress(
                SpinnerColumn(spinner_name="dots", style="bold cyan", finished_text="[bold green]✓[/bold green]"),
                TextColumn("{task.description}", table_column=Column(no_wrap=True, overflow="ellipsis")),
                BarColumn(
                    bar_width=None, style="dim cyan", complete_style="bold cyan", finished_style="bold green", table_column=Column(ratio=1)
                ),
                TaskProgressColumn(style="bold cyan", table_column=Column(no_wrap=True, justify="right", width=6)),
                TimeElapsedColumn(table_column=Column(no_wrap=True, justify="right", width=8, style="dim")),
                console=console,
                expand=True,
                transient=False,
            ) as progress:
                desc = (
                    f"Compiling [bold yellow]{target_obj_up}[/bold yellow]..."
                    if target_obj_up
                    else f"Compiling [bold yellow]{schema.schema_name}[/bold yellow]..."
                )
                comp_task = progress.add_task(desc, total=total_objs or 1)

                def _on_comp_progress(cat: str, name: str, current: int, total: int) -> None:
                    pct = int((current / total) * 100) if total else 100
                    progress.update(
                        comp_task,
                        completed=current,
                        total=total or 1,
                        description=f"Compiling [bold yellow]{name}[/bold yellow] [[bold cyan]{pct}%[/bold cyan]] [dim]│ {cat}[/dim]",
                    )

                gen_md, gen_ann = write_schema_docs(
                    schema=schema,
                    doc_path=self.config.docPath,
                    annotations_path=self.config.annotationsPath,
                    object_types=self.config.object_types,
                    multi_schema=self.is_multi,
                    all_schemas=self.schemas,
                    progress_callback=_on_comp_progress,
                    target_object=target_obj_up,
                )

            if target_obj_up:
                msg = f"[bold green]✓ Documentation updated:[/bold green] [cyan]{target_obj_up}.md[/cyan] recompiled in [bold cyan]{self.config.docPath}[/bold cyan]\n"
            else:
                msg = f"[bold green]✓ Documentation updated:[/bold green] [cyan]{len(gen_md)}[/cyan] Markdowns recompiled in [bold cyan]{self.config.docPath}[/bold cyan]\n"
            console.print(msg)
        except Exception as exc:
            console.print(f"[yellow]! Warning while recompiling docs:[/yellow] {exc}")
