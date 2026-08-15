from __future__ import annotations

from typing import Iterable

from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document

from leai.models import SchemaMetadata

SLASH_COMMANDS: list[tuple[str, str]] = [
    ("/trace", "Trace object lineage, impacts & Mermaid graph"),
    ("/tables", "List all tables, columns count and stats"),
    ("/schema", "Show active schema metadata & object counts"),
    ("/changes", "Inspect recent DDL modifications in database"),
    ("/model", "Switch AI provider and model dynamically"),
    ("/save", "Save conversation transcript to Markdown file"),
    ("/clear", "Clear conversation memory and terminal screen"),
    ("/help", "Display interactive command reference"),
    ("/exit", "Exit LEAI interactive copilot"),
]


class LeaiCompleter(Completer):
    """Smart autocomplete engine for slash commands (/) and database object mentions (@)."""

    def __init__(self, schemas: list[SchemaMetadata]) -> None:
        self.schemas = schemas
        self._db_objects: list[tuple[str, str]] = []
        self._build_object_cache()

    def _build_object_cache(self) -> None:
        objs: list[tuple[str, str]] = []
        for s in self.schemas:
            for t in s.tables:
                objs.append((t.name, "Table"))
            for v in s.views:
                objs.append((v.name, "View"))
            for mv in s.mviews:
                objs.append((mv.name, "MView"))
            for co in s.code_objects:
                objs.append((co.name, co.object_type.title()))
            for tr in s.triggers:
                objs.append((tr.name, "Trigger"))
            for sq in s.sequences:
                objs.append((sq.name, "Sequence"))
            for sn in s.synonyms:
                objs.append((sn.name, "Synonym"))

        # Deduplicate preserving order
        seen = set()
        deduped = []
        for name, otype in objs:
            key = (name.upper(), otype)
            if key not in seen:
                seen.add(key)
                deduped.append((name.upper(), otype))
        self._db_objects = deduped

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

            # Sub-argument completion for /trace
            if parts[0].lower() == "/trace":
                arg_query = parts[1].lstrip("@").upper() if len(parts) > 1 else ""
                if text.endswith(" ") and len(parts) == 1:
                    arg_query = ""
                for name, otype in self._db_objects:
                    if name.startswith(arg_query):
                        yield Completion(
                            text=name,
                            start_position=-len(word_before_cursor),
                            display=name,
                            display_meta=otype,
                        )
                return

            # Sub-argument completion for /model
            if parts[0].lower() == "/model":
                providers = [
                    ("openai", "OpenAI (gpt-4o, gpt-4o-mini)"),
                    ("gemini", "Google Gemini (gemini-1.5-flash, gemini-1.5-pro)"),
                    ("anthropic", "Anthropic Claude (claude-3-5-sonnet)"),
                    ("deepseek", "DeepSeek API (deepseek-chat)"),
                    ("ollama", "Local Ollama LLM"),
                ]
                prov_query = parts[1].lower() if len(parts) > 1 else ""
                if len(parts) <= 2 and not (len(parts) == 2 and text.endswith(" ")):
                    for p_name, desc in providers:
                        if p_name.startswith(prov_query):
                            yield Completion(
                                text=p_name,
                                start_position=-len(word_before_cursor),
                                display=p_name,
                                display_meta=desc,
                            )
                return

        # 2. @ Mentions anywhere in prompt
        if word_before_cursor.startswith("@"):
            query = word_before_cursor[1:].upper()
            for name, otype in self._db_objects:
                if name.startswith(query):
                    yield Completion(
                        text=f"@{name}",
                        start_position=-len(word_before_cursor),
                        display=f"@{name}",
                        display_meta=otype,
                    )
