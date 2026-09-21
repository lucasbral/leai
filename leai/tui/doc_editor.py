import sys
from pathlib import Path
from typing import Any, Callable

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
from leai.i18n import t
from leai.models import ObjectAnnotation, SchemaMetadata

console = Console(legacy_windows=False)


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

        for t_tab in s.tables:
            if t_tab.name.upper() == target_obj:
                return s, "tables", t_tab
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
        for t_obj in s.tables:
            ann_file = resolve_annotation_path(config, s_name, "tables", t_obj.name, is_multi)
            ann = load_annotation(ann_file) if ann_file.exists() else ObjectAnnotation()
            cols = [c.name for c in t_obj.columns]
            pct, bar_str = _calculate_doc_completeness(ann, cols)
            pk_str = f"PK: {', '.join(t_obj.primary_keys)}" if t_obj.primary_keys else t("doc_editor.no_pk")
            items.append(
                {
                    "schema": s_name,
                    "category": "tables",
                    "type": "TABLE",
                    "name": t_obj.name,
                    "obj_meta": t_obj,
                    "cols": cols,
                    "details": f"{t('doc_editor.cols_count', count=len(t_obj.columns))} ({pk_str})",
                    "ann_file": ann_file,
                    "pct": pct,
                    "bar_str": bar_str,
                    "status": f"[green]✓ {t('doc_editor.status_done')}[/green]"
                    if pct == 100
                    else (f"[yellow]⚠️ {pct}%[/yellow]" if pct > 0 else "[red]❌ 0%[/red]"),
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
                    "details": t("doc_editor.cols_count", count=len(v.columns)),
                    "ann_file": ann_file,
                    "pct": pct,
                    "bar_str": bar_str,
                    "status": f"[green]✓ {t('doc_editor.status_done')}[/green]"
                    if pct == 100
                    else (f"[yellow]⚠️ {pct}%[/yellow]" if pct > 0 else "[red]❌ 0%[/red]"),
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
                    "details": t("doc_editor.cols_count", count=len(mv.columns)),
                    "ann_file": ann_file,
                    "pct": pct,
                    "bar_str": bar_str,
                    "status": f"[green]✓ {t('doc_editor.status_done')}[/green]"
                    if pct == 100
                    else (f"[yellow]⚠️ {pct}%[/yellow]" if pct > 0 else "[red]❌ 0%[/red]"),
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
                details = t("doc_editor.routines_count", count=len(co.subprograms))
            elif co.source:
                details = t("doc_editor.lines_count", count=len(co.source.splitlines()))
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
                    "status": f"[green]✓ {t('doc_editor.status_done')}[/green]"
                    if pct == 100
                    else (f"[yellow]⚠️ {pct}%[/yellow]" if pct > 0 else "[red]❌ 0%[/red]"),
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
                    "status": f"[green]✓ {t('doc_editor.status_done')}[/green]"
                    if pct == 100
                    else (f"[yellow]⚠️ {pct}%[/yellow]" if pct > 0 else "[red]❌ 0%[/red]"),
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
                    "status": f"[green]✓ {t('doc_editor.status_done')}[/green]"
                    if pct == 100
                    else (f"[yellow]⚠️ {pct}%[/yellow]" if pct > 0 else "[red]❌ 0%[/red]"),
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
                    "status": f"[green]✓ {t('doc_editor.status_done')}[/green]"
                    if pct == 100
                    else (f"[yellow]⚠️ {pct}%[/yellow]" if pct > 0 else "[red]❌ 0%[/red]"),
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

    filter_info = t("doc_editor.filter_info", filter=search_filter) if search_filter else ""
    table = Table(
        title=t("doc_editor.catalog_title", total=total_items, filter=filter_info, page=curr_page, total_pages=total_pages),
        box=box.ROUNDED,
        header_style="bold cyan",
        expand=True,
    )
    table.add_column(t("doc_editor.col_num"), style="bold yellow", width=4, justify="right")
    table.add_column(t("doc_editor.col_schema"), style="bold yellow", width=12)
    table.add_column(t("doc_editor.col_type"), style="bold magenta", width=12)
    table.add_column(t("doc_editor.col_name"), style="bold white", ratio=2)
    table.add_column(t("doc_editor.col_details"), style="dim", ratio=2)
    table.add_column(t("doc_editor.col_status"), justify="center", width=18)

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
        storage: Any = None,
    ) -> None:
        self.config = config
        self.schemas = schemas
        self.input_fn = input_fn or _default_input_fn
        self.storage = storage
        self.is_multi = len(schemas) > 1 or config.is_all_schemas

    def run(self, object_name_arg: str | None = None) -> bool:
        """Executes the interactive documentation editor. Returns True if saved."""
        target_name = object_name_arg

        if not target_name:
            all_objects = _collect_all_objects(self.schemas, self.config)
            if not all_objects:
                console.print(t("doc_editor.no_metadata"))
                return False

            current_page = 1
            current_filter = None

            while True:
                table, page_items, total_pages = _render_catalog_table(all_objects, search_filter=current_filter, page=current_page)
                console.print()
                console.print(table)
                console.print(t("doc_editor.actions_hint"))

                try:
                    user_choice = self.input_fn(t("doc_editor.select_prompt")).strip()
                except (EOFError, KeyboardInterrupt):
                    console.print(t("doc_editor.cancelled"))
                    return False

                if not user_choice or user_choice in ("0", "q", "exit", "cancel"):
                    console.print(t("doc_editor.exited"))
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
                        console.print(t("doc_editor.invalid_index", total=len(page_items)))
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
            console.print(t("doc_editor.no_object_specified"))
            return False

        schema, category, obj_meta = find_object_in_schemas(target_name, self.schemas)

        if not schema or not category or not obj_meta:
            console.print(t("doc_editor.object_not_found", target=target_name))
            console.print(t("doc_editor.object_not_found_tip"))
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
        if ann_file.exists() or (self.storage and s_name and category and o_name):
            annotation = load_annotation(
                ann_file,
                storage=self.storage,
                schema_name=s_name,
                obj_folder=category,
                obj_name=o_name,
            )
            # Ensure missing columns are present
            for col in cols:
                if col not in annotation.columns:
                    annotation.columns[col] = ""
        else:
            db_comment = getattr(obj_meta, "comments", "") or ""
            annotation = ensure_annotation_stub(
                ann_file,
                db_comment=db_comment,
                column_names=cols,
                storage=self.storage,
                schema_name=s_name,
                obj_folder=category,
                obj_name=o_name,
            )

        # Main interactive editing loop
        dirty = False
        while True:
            self._display_editor_header(s_name, category, o_name, type_label, ann_file, annotation, cols, obj_meta)
            choice = self._prompt_menu_choice()

            if choice in ("0", "q", "exit", "cancel"):
                if dirty:
                    confirm = self._prompt_text(t("doc_editor.unsaved_changes")).strip().lower()
                    if confirm not in ("y", "yes", "s", "sim"):
                        continue
                console.print(t("doc_editor.exited"))
                return False

            elif choice == "1":
                new_desc = self._edit_multiline_text(t("doc_editor.field_description"), annotation.description)
                if new_desc != annotation.description:
                    annotation.description = new_desc
                    dirty = True

            elif choice == "2":
                if cols:
                    if self._edit_columns_menu(annotation, cols, category):
                        dirty = True
                else:
                    console.print(t("doc_editor.no_columns_routines"))

            elif choice == "3":
                if self._edit_list_menu(t("doc_editor.field_business_rules"), annotation.business_rules):
                    dirty = True

            elif choice == "4":
                if self._edit_tags_menu(annotation):
                    dirty = True

            elif choice == "5":
                if self._edit_list_menu(t("doc_editor.menu_5_warnings"), annotation.warnings):
                    dirty = True

            elif choice == "6":
                if self._edit_list_menu(t("doc_editor.menu_6_related"), annotation.related_objects):
                    dirty = True

            elif choice in ("7", "s", "save"):
                save_annotation(
                    ann_file,
                    annotation,
                    storage=self.storage,
                    schema_name=s_name,
                    obj_folder=category,
                    obj_name=o_name,
                )
                self._display_save_success(ann_file, annotation)

                # Prompt to compile markdown doc for this specific object
                try:
                    recompile = self._prompt_text(t("doc_editor.recompile_prompt", obj=o_name)).strip().lower()
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
            else (annotation.description or f"[dim italic]{t('doc_editor.no_desc_defined')}[/dim italic]")
        )
        cols_annotated = sum(1 for c in cols if annotation.columns.get(c) and str(annotation.columns[c]).strip())
        rules_count = len(annotation.business_rules)
        tags_str = ", ".join(annotation.tags) if annotation.tags else f"[dim]{t('doc_editor.none_defined')}[/dim]"

        # Badges line
        badges = (
            f"[bold on #1e66f5 white] SCHEMA: {schema_name} [/]  "
            f"[bold on #8839ef white] TYPE: {type_label} [/]  "
            f"[bold on #df8e1d black] OBJECT: {object_name} [/]"
        )
        table.add_row(t("doc_editor.field_context_badges"), badges)
        table.add_row(t("doc_editor.field_doc_completeness"), bar_str)

        # Technical details
        if hasattr(obj_meta, "primary_keys") and obj_meta.primary_keys:
            table.add_row(t("doc_editor.field_primary_keys"), f"[bold yellow]{', '.join(obj_meta.primary_keys)}[/bold yellow]")
        if hasattr(obj_meta, "foreign_keys") and obj_meta.foreign_keys:
            table.add_row(t("doc_editor.field_foreign_keys"), f"[cyan]{t('doc_editor.fk_constraints', count=len(obj_meta.foreign_keys))}[/cyan]")
        if hasattr(obj_meta, "last_ddl_time") and obj_meta.last_ddl_time:
            table.add_row(t("doc_editor.field_last_ddl_time"), f"[dim]{obj_meta.last_ddl_time}[/dim]")

        table.add_row(t("doc_editor.field_annotation_file"), f"[dim]{ann_file}[/dim]")
        table.add_row(t("doc_editor.field_description"), desc_preview)
        if cols:
            item_label = t("doc_editor.label_subprograms") if category == "packages" else t("doc_editor.label_columns")
            table.add_row(t("doc_editor.field_annotated", label=item_label), f"[bold green]{cols_annotated}[/bold green] / {len(cols)}")
        table.add_row(t("doc_editor.field_business_rules"), f"[bold green]{rules_count}[/bold green] {t('doc_editor.rules_registered_count', count='').strip()}")
        table.add_row(t("doc_editor.field_tags_domain"), tags_str)

        menu_text = (
            f"[bold white]{t('doc_editor.menu_header')}[/bold white]\n"
            f"  [bold cyan]1[/bold cyan] • 📝 {t('doc_editor.menu_1_desc')}\n"
            f"  [bold cyan]2[/bold cyan] • 📊 {t('doc_editor.menu_2_cols')}\n"
            f"  [bold cyan]3[/bold cyan] • 📌 {t('doc_editor.menu_3_rules')}\n"
            f"  [bold cyan]4[/bold cyan] • 🏷️  {t('doc_editor.menu_4_tags')}\n"
            f"  [bold cyan]5[/bold cyan] • ⚠️  {t('doc_editor.menu_5_warnings')}\n"
            f"  [bold cyan]6[/bold cyan] • 🔗 {t('doc_editor.menu_6_related')}\n"
            f"  [bold green]7[/bold green] • 💾 [bold green]{t('doc_editor.menu_7_save')}[/bold green]\n"
            f"  [bold red]0[/bold red] • ❌ {t('doc_editor.menu_0_back')}"
        )

        console.print()
        console.print(
            Panel(
                table,
                title=t("doc_editor.studio_title", schema=schema_name, obj=object_name, type=type_label),
                border_style="cyan",
            )
        )
        console.print(Panel(menu_text, box=box.SIMPLE))

    def _prompt_menu_choice(self) -> str:
        try:
            return self.input_fn(t("doc_editor.prompt_option")).strip()
        except (EOFError, KeyboardInterrupt):
            return "0"

    def _prompt_text(self, label: str, default: str = "") -> str:
        try:
            val = self.input_fn(label)
            return val if val else default
        except (EOFError, KeyboardInterrupt):
            return default

    def _edit_multiline_text(self, label: str, current_value: str | None) -> str:
        console.print(f"\n[bold cyan]{t('doc_editor.edit_title', label=label)}[/bold cyan]")
        if current_value:
            console.print(f"[dim]{t('doc_editor.current_value')}\n{current_value}[/dim]\n")
        console.print(f"[dim]{t('doc_editor.edit_desc_hint')}[/dim]")
        new_val = self._prompt_text(t("doc_editor.new_label_prompt", label=label), default=current_value or "")
        return new_val.strip()

    def _edit_columns_menu(self, annotation: ObjectAnnotation, cols: list[str], category: str) -> bool:
        item_label = t("doc_editor.label_routine") if category == "packages" else t("doc_editor.label_column")
        dirty = False

        while True:
            table = Table(title=t("doc_editor.annotate_cols_title", label=item_label, count=len(cols)), box=box.ROUNDED)
            table.add_column(t("doc_editor.col_num"), style="dim", justify="right", width=4)
            table.add_column(item_label, style="bold yellow")
            table.add_column(t("doc_editor.col_comment"), style="white")

            for idx, col in enumerate(cols, 1):
                comment = annotation.columns.get(col, "")
                comment_disp = comment if comment else "[dim italic]-[/dim italic]"
                table.add_row(str(idx), col, comment_disp)

            console.print()
            console.print(table)
            console.print(f"[dim]{t('doc_editor.cols_action_hint', label=item_label, total=len(cols))}[/dim]")

            choice = self._prompt_text(t("doc_editor.select_col_prompt", label=item_label))
            if choice in ("0", "q", "", "done", "back", "voltar"):
                break

            try:
                idx = int(choice)
                if 1 <= idx <= len(cols):
                    target_col = cols[idx - 1]
                    cur_comment = annotation.columns.get(target_col, "")
                    console.print(f"\n[cyan]{t('doc_editor.editing_col', label=item_label)}[/cyan] [bold yellow]{target_col}[/bold yellow]")
                    if cur_comment:
                        console.print(f"[dim]{t('doc_editor.current_comment', comment=cur_comment)}[/dim]")
                    new_comment = self._prompt_text(t("doc_editor.col_desc_prompt", name=target_col), default=cur_comment)
                    annotation.columns[target_col] = new_comment.strip()
                    dirty = True
                    console.print(f"[green]✓ {t('doc_editor.col_updated', name=target_col)}[/green]")
            except ValueError:
                console.print(f"[yellow]{t('doc_editor.invalid_number')}[/yellow]")

        return dirty

    def _edit_list_menu(self, title: str, items_list: list[str]) -> bool:
        dirty = False
        while True:
            table = Table(title=t("doc_editor.edit_list_title", title=title, count=len(items_list)), box=box.ROUNDED)
            table.add_column(t("doc_editor.col_num"), style="dim", justify="right", width=4)
            table.add_column(t("doc_editor.col_content"), style="white")

            for idx, item in enumerate(items_list, 1):
                table.add_row(str(idx), item)

            if not items_list:
                table.add_row("-", f"[dim italic]{t('doc_editor.no_entries_yet')}[/dim italic]")

            console.print()
            console.print(table)
            console.print(f"[bold white]{t('doc_editor.list_actions')}[/bold white]")

            choice = self._prompt_text(t("doc_editor.action_prompt")).strip()
            if choice in ("0", "q", "", "done", "back", "voltar"):
                break

            if choice in ("+", "add", "novo"):
                new_item = self._prompt_text(t("doc_editor.enter_new_item")).strip()
                if new_item:
                    items_list.append(new_item)
                    dirty = True
                    console.print(f"[green]✓ {t('doc_editor.added_item', num=len(items_list))}[/green]")
            elif choice.lower().startswith("d") and choice[1:].isdigit():
                idx_to_del = int(choice[1:])
                if 1 <= idx_to_del <= len(items_list):
                    removed = items_list.pop(idx_to_del - 1)
                    dirty = True
                    console.print(f"[red]✓ {t('doc_editor.removed_item', item=removed)}[/red]")
            elif choice.isdigit():
                idx = int(choice)
                if 1 <= idx <= len(items_list):
                    cur_val = items_list[idx - 1]
                    console.print(f"[dim]{t('doc_editor.current_item', val=cur_val)}[/dim]")
                    edited = self._prompt_text(t("doc_editor.new_value_prompt"), default=cur_val).strip()
                    if edited:
                        items_list[idx - 1] = edited
                        dirty = True
                        console.print(f"[green]✓ {t('doc_editor.updated_item', num=idx)}[/green]")

        return dirty

    def _edit_tags_menu(self, annotation: ObjectAnnotation) -> bool:
        current_tags = ", ".join(annotation.tags) if annotation.tags else ""
        console.print(f"\n[bold cyan]{t('doc_editor.edit_tags_title')}[/bold cyan]")
        if current_tags:
            console.print(f"[dim]{t('doc_editor.current_tags', tags=current_tags)}[/dim]")
        console.print(f"[dim]{t('doc_editor.tags_hint')}[/dim]")

        new_tags_raw = self._prompt_text(t("doc_editor.tags_prompt"), default=current_tags)
        parsed = [t_item.strip() for t_item in new_tags_raw.split(",") if t_item.strip()]
        if parsed != annotation.tags:
            annotation.tags = parsed
            console.print(f"[green]✓ {t('doc_editor.tags_updated', tags=', '.join(parsed))}[/green]")
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

        sub_text = (
            f"[dim]{ann_file} • Synced to SeaweedFS ({self.config.storage.seaweedfs.bucket})[/dim]"
            if self.storage
            else f"[dim]{ann_file}[/dim]"
        )

        console.print()
        console.print(
            Panel(
                syntax,
                title=f"[bold green]✓ {t('doc_editor.saved_success', filename=ann_file.name)}[/bold green]",
                subtitle=sub_text,
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
                    t("doc_editor.recompile_single", obj=target_obj_up)
                    if target_obj_up
                    else t("doc_editor.recompile_schema", schema=schema.schema_name)
                )
                comp_task = progress.add_task(desc, total=total_objs or 1)

                def _on_comp_progress(cat: str, name: str, current: int, total: int) -> None:
                    pct = int((current / total) * 100) if total else 100
                    progress.update(
                        comp_task,
                        completed=current,
                        total=total or 1,
                        description=t("doc_editor.compiling_progress", name=name, pct=pct, cat=cat),
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
                msg = f"[bold green]✓ {t('doc_editor.docs_updated_single', obj=target_obj_up, path=self.config.docPath)}[/bold green]\n"
            else:
                msg = f"[bold green]✓ {t('doc_editor.docs_updated_multi', count=len(gen_md), path=self.config.docPath)}[/bold green]\n"
            console.print(msg)
        except Exception as exc:
            console.print(f"[yellow]! {t('doc_editor.recompile_warning', error=exc)}[/yellow]")
