from __future__ import annotations

from typing import Any, Iterable

from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document

from leai.models import SchemaMetadata

SLASH_COMMANDS: list[tuple[str, str]] = [
    ("/doc", "Open in-terminal YAML annotation & documentation editor"),
    ("/rule", "Manage global business glossary and canonical domain rules"),
    ("/extract", "Extract fresh metadata snapshot from Oracle database"),
    ("/compile", "Compile Markdown documentation in docs/"),
    ("/annotate", "Synchronize YAML annotation stubs in annotations/"),
    ("/enrich", "Auto-enrich business descriptions using AI / LLM"),
    ("/chat", "Ask a question to AI Assistant directly with RAG context"),
    ("/serve", "Launch offline web documentation server"),
    ("/trace", "Trace object lineage, impacts & Mermaid graph"),
    ("/tables", "List all tables, columns count and stats"),
    ("/schema", "Show active schema metadata & object counts"),
    ("/changes", "Inspect recent DDL modifications in database"),
    ("/model", "Switch AI provider and model dynamically"),
    ("/agent", "Run specialized subagents (catalog, plsql, lineage, patch, doc)"),
    ("/workflow", "Execute autonomous multi-step workflows (impact, refactor)"),
    ("/copy", "Copy last AI response or specific code block to OS clipboard"),
    ("/save", "Save conversation transcript to Markdown file"),
    ("/audit", "Inspect AI reasoning, tool execution trace and session logs"),
    ("/tools", "Quick viewer for last turn's tool execution inputs/outputs"),
    ("/git", "Check Git status, pull updates, or sync metadata with remote"),
    ("/seaweed", "SeaweedFS S3 storage status, push, and pull operations"),
    ("/doctor", "Pre-flight health check on Oracle, AI, Storage, and Git (alias: /check)"),
    ("/check", "Run environment diagnostics on DB, config and AI provider"),
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
            for t in s.tables:
                pk_str = f" • PK: {', '.join(t.primary_keys)}" if t.primary_keys else ""
                objs.append((s_name, t.name, "TABLE", f"{len(t.columns)} cols{pk_str}"))
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
                for cmd, desc in SLASH_COMMANDS:
                    if cmd.lower().startswith(query):
                        yield Completion(
                            text=cmd,
                            start_position=-len(text),
                            display=cmd,
                            display_meta=desc,
                        )
                return

            cmd_name = parts[0].lower()

            # Sub-argument completion for /doc, /trace, /enrich, /compile, /build (DB Objects)
            if cmd_name in ("/doc", "/trace", "/enrich", "/compile", "/build"):
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

            # Sub-argument completion for /extract (Schemas and SeaweedFS flags)
            if cmd_name == "/extract":
                flag_options = [
                    ("--seaweed", "Save RAW snapshots directly to SeaweedFS S3 storage"),
                    ("-W", "Short for --seaweed"),
                    ("--no-cache", "Do not write local files in raw/, send only to SeaweedFS"),
                    ("--force-upload", "Force upload all objects (bypasses SHA-256 manifest)"),
                    ("-F", "Short for --force-upload"),
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
                        display_meta="Extract all schemas configured in leai.yml",
                    )

                # 2. Suggest individual configured schemas from leai.yml
                for s_name in self._schemas_list:
                    if s_name != "ALL" and s_name.startswith(schema_query):
                        yield Completion(
                            text=s_name,
                            start_position=-len(word_before_cursor),
                            display=s_name,
                            display_meta="Configured Schema (leai.yml)",
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

            # Sub-argument completion for /annotate (SeaweedFS flags)
            if cmd_name == "/annotate":
                ann_flags = [
                    ("--seaweed", "Sync annotations with SeaweedFS S3 storage"),
                    ("-W", "Short for --seaweed"),
                    ("--no-cache", "Do not write local files, sync directly with SeaweedFS"),
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
                        ("status", "Check SeaweedFS S3 connection and bucket operational status"),
                        ("push", "Upload local raw/ snapshots and annotations/ to SeaweedFS"),
                        ("pull", "Download remote raw/ snapshots and annotations/ from SeaweedFS"),
                        ("sync", "Bidirectional smart synchronization between local disk and SeaweedFS"),
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

            # Sub-argument completion for /model and /models (AI Providers)
            if cmd_name in ("/model", "/models"):
                providers = ["openai", "gemini", "anthropic", "grok", "xai", "deepseek", "qwen", "kimi", "ollama"]
                if (len(parts) == 2 and not text.endswith(" ")) or (len(parts) == 1 and text.endswith(" ")):
                    p_query = parts[1].lower() if len(parts) > 1 else ""
                    for p in providers:
                        if p.startswith(p_query):
                            yield Completion(
                                text=p,
                                start_position=-len(word_before_cursor),
                                display=p,
                                display_meta="AI Provider",
                            )
                return

            # Sub-argument completion for /agent (Specialist Roles)
            if cmd_name == "/agent":
                specialists = [
                    ("catalog_researcher", "Discovery of tables, columns, comments, constraints"),
                    ("plsql_analyst", "Reverse engineering of packages, procedures, triggers"),
                    ("lineage_auditor", "Dependency traversal and change impact risk audit"),
                    ("patch_generator", "Production-grade PL/SQL refactoring, unit tests, rollback"),
                    ("doc_annotator", "Business descriptions, rules, domain classification tags"),
                    ("list", "List all registered subagent specialists"),
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
                    ("impact", "Impact assessment: constraints, lineage, code scan & risk matrix"),
                    ("refactor", "Safe PL/SQL subprogram refactoring with unit test & rollback"),
                    ("list", "List all available autonomous workflows"),
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
                                display_meta="Database Schema",
                            )
                return

            # Sub-argument completion for /changes (Day Windows)
            if cmd_name == "/changes":
                if (len(parts) == 2 and not text.endswith(" ")) or (len(parts) == 1 and text.endswith(" ")):
                    c_query = parts[1] if len(parts) > 1 else ""
                    day_options = [
                        ("1", "Last 24 hours"),
                        ("7", "Last 7 days (Default)"),
                        ("15", "Last 15 days"),
                        ("30", "Last 30 days (1 month)"),
                        ("60", "Last 60 days (2 months)"),
                        ("90", "Last 90 days (3 months)"),
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
                        ("leai_chat.md", "Export conversation to leai_chat.md"),
                        ("transcript.md", "Export conversation to transcript.md"),
                        ("history.md", "Export conversation to history.md"),
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
                        ("last", "Inspect tool traces and outputs of last interaction (Default)"),
                        ("session", "View aggregate session statistics and tool breakdown"),
                        ("export", "Export session audit report to Markdown or JSON"),
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
                        ("all", "Copy entire AI response text (Default)"),
                        ("code", "Copy first code block (SQL/PLSQL/etc)"),
                        ("1", "Copy 1st code block"),
                        ("2", "Copy 2nd code block"),
                        ("3", "Copy 3rd code block"),
                        ("sql", "Copy SQL / PL/SQL query or routine"),
                        ("list", "List all code blocks available in last response"),
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

        # 2. @Mentions within chat prompts
        if word_before_cursor.startswith("@"):
            query = word_before_cursor[1:].upper()
            for s_name, name, otype, details in self._db_objects:
                qualified = f"{s_name}.{name}" if s_name else name
                if name.startswith(query) or qualified.startswith(query):
                    meta_desc = f"{s_name} [{otype}] {details}".strip() if s_name else f"[{otype}] {details}".strip()
                    yield Completion(
                        text=f"@{name}",
                        start_position=-len(word_before_cursor),
                        display=f"@{s_name}.{name}" if s_name else f"@{name}",
                        display_meta=meta_desc,
                    )
