from __future__ import annotations

from typing import Any, Iterable

from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document

from leai.i18n import t
from leai.models import SchemaMetadata


def get_slash_commands() -> list[tuple[str, str]]:
    """Returns slash commands and their localized descriptions."""
    return [
        ("/doc", t("completer.cmd_doc")),
        ("/rule", t("completer.cmd_rule")),
        ("/tune", t("completer.cmd_tune")),
        ("/validate", t("completer.cmd_validate")),
        ("/thoughts", t("completer.cmd_thoughts")),
        ("/extract", t("completer.cmd_extract")),
        ("/update", t("completer.cmd_update")),
        ("/compile", t("completer.cmd_compile")),
        ("/annotate", t("completer.cmd_annotate")),
        ("/enrich", t("completer.cmd_enrich")),
        ("/chat", t("completer.cmd_chat")),
        ("/serve", t("completer.cmd_serve")),
        ("/trace", t("completer.cmd_trace")),
        ("/tables", t("completer.cmd_tables")),
        ("/schema", t("completer.cmd_schema")),
        ("/changes", t("completer.cmd_changes")),
        ("/model", t("completer.cmd_model")),
        ("/provider", t("completer.cmd_provider")),
        ("/agent", t("completer.cmd_agent")),
        ("/workflow", t("completer.cmd_workflow")),
        ("/copy", t("completer.cmd_copy")),
        ("/save", t("completer.cmd_save")),
        ("/audit", t("completer.cmd_audit")),
        ("/tools", t("completer.cmd_tools")),
        ("/git", t("completer.cmd_git")),
        ("/seaweed", t("completer.cmd_seaweed")),
        ("/doctor", t("completer.cmd_doctor")),
        ("/init", t("completer.cmd_init")),
        ("/clear", t("completer.cmd_clear")),
        ("/help", t("completer.cmd_help")),
        ("/exit", t("completer.cmd_exit")),
    ]


SLASH_COMMANDS: list[tuple[str, str]] = [
    ("/doc", "Open in-terminal YAML annotation & documentation editor"),
    ("/rule", "Manage global business glossary and canonical domain rules"),
    ("/tune", "Analyze and tune SQL query (sargability, FTS risks, compound indexes)"),
    ("/validate", "Validate SQL query Oracle dialect compliance and schema objects"),
    ("/thoughts", "Toggle live reasoning/thought token streaming in terminal (on/off)"),
    ("/extract", "Extract fresh metadata snapshot from Oracle database"),
    ("/update", "Fast incremental update of recently modified objects, stubs & S3"),
    ("/compile", "Compile Markdown documentation in docs/"),
    ("/annotate", "Synchronize YAML annotation stubs in annotations/"),
    ("/enrich", "Auto-enrich business descriptions using AI / LLM"),
    ("/chat", "Ask a question to AI Assistant directly with RAG context"),
    ("/serve", "Launch offline web documentation server"),
    ("/trace", "Trace object lineage, impacts & Mermaid graph"),
    ("/tables", "List all tables, columns count and stats"),
    ("/schema", "Show active schema metadata & object counts"),
    ("/changes", "Inspect recent DDL modifications in database"),
    ("/model", "Switch AI model dynamically in active session"),
    ("/provider", "Switch AI provider dynamically (ollama, openai, gemini, etc.)"),
    ("/agent", "Run specialized subagents (catalog, plsql, lineage, patch, doc)"),
    ("/workflow", "Execute autonomous multi-step workflows (reverse-procedure, impact, refactor)"),
    ("/copy", "Copy last AI response or specific code block to OS clipboard"),
    ("/save", "Save conversation transcript to Markdown file"),
    ("/audit", "Inspect AI reasoning, tool execution trace and session logs"),
    ("/tools", "Quick viewer for last turn's tool execution inputs/outputs"),
    ("/git", "Check Git status, pull updates, or sync metadata with remote"),
    ("/seaweed", "SeaweedFS S3 storage status, push, and pull operations"),
    ("/doctor", "Pre-flight health check on Oracle, AI, Storage, Git, and local stores"),
    ("/init", "Create or check leai.yml configuration file"),
    ("/clear", "Clear conversation memory and terminal screen"),
    ("/help", "Display interactive command reference"),
    ("/exit", "Exit LEAI interactive copilot"),
]


class LeaiCompleter(Completer):
    """Smart autocomplete engine for slash commands (/), sub-arguments, and database object mentions (@)."""

    def __init__(self, schemas: list[SchemaMetadata], config: Any = None) -> None:
        self.schemas = schemas
        self.config = config
        self._db_objects: list[tuple[str, str, str, str]] = []
        self._schemas_list: list[str] = []
        self._build_object_cache()

    def update_schemas(self, schemas: list[SchemaMetadata]) -> None:
        """Dynamically updates the schema cache after extractions."""
        self.schemas = schemas
        self._build_object_cache()

    def _build_object_cache(self) -> None:
        objs: list[tuple[str, str, str, str]] = []
        s_names: set[str] = set()

        for s in self.schemas:
            s_name = s.schema_name.upper() if s.schema_name else ""
            if s_name:
                s_names.add(s_name)
            for tbl in s.tables:
                pk_str = f" • PK: {', '.join(tbl.primary_keys)}" if tbl.primary_keys else ""
                objs.append((s_name, tbl.name, "TABLE", f"{len(tbl.columns)} cols{pk_str}"))
            for v in s.views:
                objs.append((s_name, v.name, "VIEW", f"{len(v.columns)} cols"))
            for mv in s.mviews:
                objs.append((s_name, mv.name, "MVIEW", f"{len(mv.columns)} cols"))
            for co in s.code_objects:
                ot_up = co.object_type.upper()
                if "PACKAGE" in ot_up:
                    badge = "PACKAGE"
                elif "PROCEDURE" in ot_up:
                    badge = "PROCEDURE"
                elif "FUNCTION" in ot_up:
                    badge = "FUNCTION"
                else:
                    badge = ot_up

                if co.subprograms:
                    sub_count = len(co.subprograms)
                    label = "routines"
                elif co.source:
                    sub_count = len(co.source.splitlines())
                    label = "lines"
                else:
                    sub_count = 0
                    label = "code"
                objs.append((s_name, co.name, badge, f"{sub_count} {label}"))
            for tr in s.triggers:
                objs.append((s_name, tr.name, "TRIGGER", f"on {tr.table_name or 'DB'}"))
            for sq in s.sequences:
                objs.append((s_name, sq.name, "SEQUENCE", ""))
            for sn in s.synonyms:
                objs.append((s_name, sn.name, "SYNONYM", f"-> {sn.table_name or ''}"))

        # Deduplicate preserving order
        seen = set()
        deduped = []
        for s_name, name, otype, details in objs:
            key = (s_name, name.upper(), otype)
            if key not in seen:
                seen.add(key)
                deduped.append((s_name, name.upper(), otype, details))
        self._db_objects = deduped

        # Build glossary cache from annotations_path if configured
        glossary_items: list[tuple[str, str, str]] = []
        ann_path = getattr(self.config, "annotationsPath", None) or "./annotations"
        try:
            from leai.glossary import load_glossary

            g = load_glossary(ann_path)
            for term_obj in g.terms:
                t_name = term_obj.term.upper()
                tags_str = f"[{', '.join(term_obj.tags)}]" if term_obj.tags else ""
                desc = term_obj.definition or term_obj.canonical_filter or ""
                glossary_items.append((t_name, tags_str, desc))
        except Exception:
            pass
        self._glossary_terms = glossary_items

        # Collect configured schemas from config.schemas
        cfg_schemas = [
            s.strip().upper() for s in getattr(self.config, "schemas", []) or [] if s and not getattr(self.config, "is_all_schemas", False)
        ]
        self._schemas_list = sorted(list(set(cfg_schemas or s_names)))

    def get_completions(self, document: Document, complete_event: CompleteEvent) -> Iterable[Completion]:
        text = document.text_before_cursor
        word_before_cursor = document.get_word_before_cursor(WORD=True)

        # 1. Slash commands at line start
        if text.startswith("/"):
            parts = text.split()
            if len(parts) <= 1 and not text.endswith(" "):
                query = text.lower()
                for cmd, desc in get_slash_commands():
                    if cmd.lower().startswith(query):
                        yield Completion(
                            text=cmd,
                            start_position=-len(text),
                            display=cmd,
                            display_meta=desc,
                        )
                return

            cmd_name = parts[0].lower()

            # Sub-argument completion for /doc, /trace, /enrich, /compile, /build, /tune, /validate (DB Objects)
            if cmd_name in ("/doc", "/trace", "/enrich", "/compile", "/build", "/tune", "/validate"):
                arg_query = parts[1].lstrip("@").upper() if len(parts) > 1 else ""
                if text.endswith(" ") and len(parts) == 1:
                    arg_query = ""
                for s_name, name, otype, details in self._db_objects:
                    qualified = f"{s_name}.{name}" if s_name else name
                    if name.startswith(arg_query) or qualified.startswith(arg_query):
                        meta_desc = f"{s_name} [{otype}] ({details})" if (s_name and details) else f"[{otype}] {details}".strip()
                        yield Completion(
                            text=name,
                            start_position=-len(word_before_cursor),
                            display=f"{s_name}.{name}" if s_name else name,
                            display_meta=meta_desc,
                        )
                return

            # Sub-argument completion for /thoughts (on, off, toggle)
            if cmd_name in ("/thoughts", "/thought"):
                if (len(parts) == 2 and not text.endswith(" ")) or (len(parts) == 1 and text.endswith(" ")):
                    th_query = parts[1].lower() if len(parts) > 1 else ""
                    th_options = [
                        ("on", t("completer.th_on")),
                        ("off", t("completer.th_off")),
                        ("toggle", t("completer.th_toggle")),
                    ]
                    for t_opt, t_meta in th_options:
                        if t_opt.startswith(th_query):
                            yield Completion(
                                text=t_opt,
                                start_position=-len(word_before_cursor),
                                display=t_opt,
                                display_meta=t_meta,
                            )
                return

            # Sub-argument completion for /extract (Schemas and SeaweedFS flags)
            if cmd_name == "/extract":
                flag_options = [
                    ("--seaweed", t("completer.extract_seaweed")),
                    ("-W", t("completer.extract_short_seaweed")),
                    ("--no-cache", t("completer.extract_no_cache")),
                    ("--force-upload", t("completer.extract_force_upload")),
                    ("-F", t("completer.extract_short_force")),
                ]
                if word_before_cursor.startswith("-"):
                    for flag_name, flag_desc in flag_options:
                        if flag_name.startswith(word_before_cursor):
                            yield Completion(
                                text=flag_name,
                                start_position=-len(word_before_cursor),
                                display=flag_name,
                                display_meta=flag_desc,
                            )
                    return

                schema_query = word_before_cursor.upper()

                # 1. Suggest ALL option first
                if "ALL".startswith(schema_query):
                    yield Completion(
                        text="ALL",
                        start_position=-len(word_before_cursor),
                        display="ALL",
                        display_meta=t("completer.extract_all"),
                    )

                # 2. Suggest individual configured schemas from leai.yml
                for s_name in self._schemas_list:
                    if s_name != "ALL" and s_name.startswith(schema_query):
                        yield Completion(
                            text=s_name,
                            start_position=-len(word_before_cursor),
                            display=s_name,
                            display_meta=t("completer.extract_schema_desc"),
                        )

                # 3. Also suggest flags
                for flag_name, flag_desc in flag_options:
                    if flag_name.startswith(word_before_cursor):
                        yield Completion(
                            text=flag_name,
                            start_position=-len(word_before_cursor),
                            display=flag_name,
                            display_meta=flag_desc,
                        )
                return

            # Sub-argument completion for /update (Flags and Schemas)
            if cmd_name == "/update":
                upd_flags = [
                    ("--hours", t("completer.update_hours")),
                    ("-H", t("completer.update_short_hours")),
                    ("--days", t("completer.update_days")),
                    ("-d", t("completer.update_short_days")),
                    ("--compile", t("completer.update_compile")),
                    ("-C", t("completer.update_short_compile")),
                    ("--seaweed", t("completer.update_seaweed")),
                    ("-W", t("completer.extract_short_seaweed")),
                    ("--no-cache", t("completer.update_no_cache")),
                    ("--force-upload", t("completer.extract_force_upload")),
                    ("-F", t("completer.extract_short_force")),
                ]
                if word_before_cursor.startswith("-"):
                    for flag_name, flag_desc in upd_flags:
                        if flag_name.startswith(word_before_cursor):
                            yield Completion(
                                text=flag_name,
                                start_position=-len(word_before_cursor),
                                display=flag_name,
                                display_meta=flag_desc,
                            )
                    return

                schema_query = word_before_cursor.upper()
                for s_name in self._schemas_list:
                    if s_name != "ALL" and s_name.startswith(schema_query):
                        yield Completion(
                            text=s_name,
                            start_position=-len(word_before_cursor),
                            display=s_name,
                            display_meta=t("completer.extract_schema_desc"),
                        )

                for flag_name, flag_desc in upd_flags:
                    if flag_name.startswith(word_before_cursor):
                        yield Completion(
                            text=flag_name,
                            start_position=-len(word_before_cursor),
                            display=flag_name,
                            display_meta=flag_desc,
                        )
                return

            # Sub-argument completion for /rule (list, add, del, find)
            if cmd_name in ("/rule", "/rules"):
                if (len(parts) == 2 and not text.endswith(" ")) or (len(parts) == 1 and text.endswith(" ")):
                    rule_query = parts[1].lower() if len(parts) > 1 else ""
                    rule_options = [
                        ("list", t("completer.rule_list")),
                        ("add", t("completer.rule_add")),
                        ("del", t("completer.rule_del")),
                        ("find", t("completer.rule_find")),
                    ]
                    for r_cmd, r_desc in rule_options:
                        if r_cmd.startswith(rule_query):
                            yield Completion(
                                text=r_cmd,
                                start_position=-len(word_before_cursor),
                                display=r_cmd,
                                display_meta=r_desc,
                            )
                return

            # Sub-argument completion for /annotate (SeaweedFS flags)
            if cmd_name == "/annotate":
                ann_flags = [
                    ("--seaweed", t("completer.annotate_seaweed")),
                    ("-W", t("completer.extract_short_seaweed")),
                    ("--no-cache", t("completer.annotate_no_cache")),
                ]
                for flag_name, flag_desc in ann_flags:
                    if flag_name.startswith(word_before_cursor):
                        yield Completion(
                            text=flag_name,
                            start_position=-len(word_before_cursor),
                            display=flag_name,
                            display_meta=flag_desc,
                        )
                return

            # Sub-argument completion for /seaweed (status, push, pull)
            if cmd_name == "/seaweed":
                if (len(parts) == 2 and not text.endswith(" ")) or (len(parts) == 1 and text.endswith(" ")):
                    sw_query = parts[1].lower() if len(parts) > 1 else ""
                    sw_options = [
                        ("status", t("completer.seaweed_status")),
                        ("push", t("completer.seaweed_push")),
                        ("pull", t("completer.seaweed_pull")),
                        ("sync", t("completer.seaweed_sync")),
                    ]
                    for sw_cmd, sw_desc in sw_options:
                        if sw_cmd.startswith(sw_query):
                            yield Completion(
                                text=sw_cmd,
                                start_position=-len(word_before_cursor),
                                display=sw_cmd,
                                display_meta=sw_desc,
                            )
                return

            # Sub-argument completion for /provider and /model
            if cmd_name in ("/provider", "/providers", "/model", "/models"):
                providers = ["ollama", "local", "openai", "gemini", "anthropic", "deepseek", "qwen", "kimi", "grok", "xai"]
                if (len(parts) == 2 and not text.endswith(" ")) or (len(parts) == 1 and text.endswith(" ")):
                    p_query = parts[1].lower() if len(parts) > 1 else ""
                    for p in providers:
                        if p.startswith(p_query):
                            yield Completion(
                                text=p,
                                start_position=-len(word_before_cursor),
                                display=p,
                                display_meta=t("completer.provider_desc"),
                            )
                return

            # Sub-argument completion for /agent (Specialist Roles)
            if cmd_name == "/agent":
                specialists = [
                    ("catalog_researcher", t("completer.agent_catalog")),
                    ("plsql_analyst", t("completer.agent_plsql")),
                    ("lineage_auditor", t("completer.agent_lineage")),
                    ("patch_generator", t("completer.agent_patch")),
                    ("doc_annotator", t("completer.agent_doc")),
                    ("list", t("completer.agent_list")),
                ]
                if (len(parts) == 2 and not text.endswith(" ")) or (len(parts) == 1 and text.endswith(" ")):
                    a_query = parts[1].lower() if len(parts) > 1 else ""
                    for role_name, role_desc in specialists:
                        if role_name.startswith(a_query):
                            yield Completion(
                                text=role_name,
                                start_position=-len(word_before_cursor),
                                display=f"@{role_name}",
                                display_meta=role_desc,
                            )
                return

            # Sub-argument completion for /workflow (Pipelines)
            if cmd_name == "/workflow":
                workflows = [
                    ("reverse-procedure", t("completer.wf_reverse_proc")),
                    ("reverse", t("completer.wf_reverse_alias")),
                    ("decomp", t("completer.wf_reverse_alias")),
                    ("impact-analysis", t("completer.wf_impact")),
                    ("impact", t("completer.wf_impact_alias")),
                    ("safe-refactor", t("completer.wf_safe_refactor")),
                    ("refactor", t("completer.wf_refactor_alias")),
                    ("list", t("completer.wf_list")),
                ]
                if (len(parts) == 2 and not text.endswith(" ")) or (len(parts) == 1 and text.endswith(" ")):
                    w_query = parts[1].lower() if len(parts) > 1 else ""
                    for wf_name, wf_desc in workflows:
                        if wf_name.startswith(w_query):
                            yield Completion(
                                text=wf_name,
                                start_position=-len(word_before_cursor),
                                display=wf_name,
                                display_meta=wf_desc,
                            )
                elif len(parts) >= 2:
                    # Suggest DB objects as 2nd argument (target)
                    arg_query = parts[-1].lstrip("@").upper() if not text.endswith(" ") else ""
                    for s_name, name, otype, details in self._db_objects:
                        qualified = f"{s_name}.{name}" if s_name else name
                        if name.startswith(arg_query) or qualified.startswith(arg_query):
                            meta_desc = f"{s_name} [{otype}] ({details})" if (s_name and details) else f"[{otype}] {details}".strip()
                            yield Completion(
                                text=name,
                                start_position=-len(word_before_cursor),
                                display=f"{s_name}.{name}" if s_name else name,
                                display_meta=meta_desc,
                            )
                return

            # Sub-argument completion for /schema (Database Schemas)
            if cmd_name == "/schema":
                if (len(parts) == 2 and not text.endswith(" ")) or (len(parts) == 1 and text.endswith(" ")):
                    s_query = parts[1].upper() if len(parts) > 1 else ""
                    for s_name in self._schemas_list:
                        if s_name.startswith(s_query):
                            yield Completion(
                                text=s_name,
                                start_position=-len(word_before_cursor),
                                display=s_name,
                                display_meta=t("completer.extract_schema_desc"),
                            )
                return

            # Sub-argument completion for /changes (Day Windows)
            if cmd_name == "/changes":
                if (len(parts) == 2 and not text.endswith(" ")) or (len(parts) == 1 and text.endswith(" ")):
                    c_query = parts[1] if len(parts) > 1 else ""
                    day_options = [
                        ("1", t("completer.changes_1d")),
                        ("7", t("completer.changes_7d")),
                        ("15", t("completer.changes_15d")),
                        ("30", t("completer.changes_30d")),
                        ("60", t("completer.changes_60d")),
                        ("90", t("completer.changes_90d")),
                    ]
                    for d_str, d_meta in day_options:
                        if d_str.startswith(c_query):
                            yield Completion(
                                text=d_str,
                                start_position=-len(word_before_cursor),
                                display=f"{d_str} days",
                                display_meta=d_meta,
                            )
                return

            # Sub-argument completion for /save (File Names)
            if cmd_name == "/save":
                if (len(parts) == 2 and not text.endswith(" ")) or (len(parts) == 1 and text.endswith(" ")):
                    f_query = parts[1].lower() if len(parts) > 1 else ""
                    file_options = [
                        ("leai_chat.md", t("completer.save_chat_md")),
                        ("transcript.md", t("completer.save_transcript_md")),
                        ("history.md", t("completer.save_history_md")),
                    ]
                    for f_name, f_meta in file_options:
                        if f_name.lower().startswith(f_query):
                            yield Completion(
                                text=f_name,
                                start_position=-len(word_before_cursor),
                                display=f_name,
                                display_meta=f_meta,
                            )
                return

            # Sub-argument completion for /audit (last, session, export)
            if cmd_name == "/audit":
                if (len(parts) == 2 and not text.endswith(" ")) or (len(parts) == 1 and text.endswith(" ")):
                    a_query = parts[1].lower() if len(parts) > 1 else ""
                    audit_options = [
                        ("last", t("completer.audit_last")),
                        ("session", t("completer.audit_session")),
                        ("export", t("completer.audit_export")),
                    ]
                    for a_opt, a_meta in audit_options:
                        if a_opt.startswith(a_query):
                            yield Completion(
                                text=a_opt,
                                start_position=-len(word_before_cursor),
                                display=a_opt,
                                display_meta=a_meta,
                            )
                return

            # Sub-argument completion for /copy and /yank
            if cmd_name in ("/copy", "/yank"):
                if (len(parts) == 2 and not text.endswith(" ")) or (len(parts) == 1 and text.endswith(" ")):
                    c_query = parts[1].lower() if len(parts) > 1 else ""
                    copy_options = [
                        ("all", t("completer.copy_all")),
                        ("code", t("completer.copy_code")),
                        ("1", t("completer.copy_1")),
                        ("2", t("completer.copy_2")),
                        ("3", t("completer.copy_3")),
                        ("sql", t("completer.copy_sql")),
                        ("list", t("completer.copy_list")),
                    ]
                    for c_opt, c_meta in copy_options:
                        if c_opt.startswith(c_query):
                            yield Completion(
                                text=c_opt,
                                start_position=-len(word_before_cursor),
                                display=c_opt,
                                display_meta=c_meta,
                            )
                return

            return

        # 2. @Mentions within chat prompts (Database objects)
        if word_before_cursor.startswith("@"):
            query = word_before_cursor[1:].upper()
            icon_map = {
                "TABLE": "📋",
                "VIEW": "👁️",
                "MVIEW": "⚡",
                "PACKAGE": "📦",
                "PROCEDURE": "⚙️",
                "FUNCTION": "ƒ",
                "TRIGGER": "⚡",
                "SEQUENCE": "🔢",
                "SYNONYM": "🔗",
            }
            for s_name, name, otype, details in self._db_objects:
                qualified = f"{s_name}.{name}" if s_name else name
                if name.startswith(query) or qualified.startswith(query):
                    icon = icon_map.get(otype, "•")
                    meta_desc = f"{icon} {s_name} [{otype}] {details}".strip() if s_name else f"{icon} [{otype}] {details}".strip()
                    yield Completion(
                        text=f"@{name}",
                        start_position=-len(word_before_cursor),
                        display=f"@{s_name}.{name}" if s_name else f"@{name}",
                        display_meta=meta_desc,
                    )
            return

        # 3. #Mentions within chat prompts (Business glossary rules)
        if word_before_cursor.startswith("#"):
            query = word_before_cursor[1:].upper()
            for t_name, tags, desc in self._glossary_terms:
                if t_name.startswith(query):
                    meta_desc = f"📖 {tags} {desc}"[:60].strip()
                    yield Completion(
                        text=f"#{t_name}",
                        start_position=-len(word_before_cursor),
                        display=f"#{t_name}",
                        display_meta=meta_desc,
                    )
            return

        # 4. /Slash commands within prompt
        if word_before_cursor.startswith("/"):
            query = word_before_cursor.lower()
            for cmd, desc in get_slash_commands():
                if cmd.lower().startswith(query):
                    yield Completion(
                        text=cmd,
                        start_position=-len(word_before_cursor),
                        display=cmd,
                        display_meta=desc,
                    )
            return
