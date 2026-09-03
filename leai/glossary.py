from __future__ import annotations

import sys
import unicodedata
from pathlib import Path
from typing import Any

import yaml

from leai.models import BusinessGlossary, GlossaryTerm


def _normalize_text(text: str) -> str:
    """Removes accents and converts to lowercase for resilient keyword search."""
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def get_glossary_file(annotations_path: Path | str) -> Path:
    base = Path(annotations_path)
    return base / "glossary.yml"


def load_glossary(annotations_path: Path | str) -> BusinessGlossary:
    file_path = get_glossary_file(annotations_path)
    if not file_path.exists():
        return BusinessGlossary()
    try:
        raw = yaml.safe_load(file_path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return BusinessGlossary.model_validate(raw)
    except Exception as exc:
        print(f"Warning: Error loading glossary file '{file_path}': {exc}", file=sys.stderr)
    return BusinessGlossary()


def save_glossary(annotations_path: Path | str, glossary: BusinessGlossary) -> None:
    file_path = get_glossary_file(annotations_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    terms_data = []
    for t in sorted(glossary.terms, key=lambda x: x.term.upper()):
        item: dict[str, Any] = {
            "term": t.term,
            "definition": t.definition,
        }
        if t.primary_table:
            item["primary_table"] = t.primary_table.upper()
        if t.canonical_filter:
            item["canonical_filter"] = t.canonical_filter
        if t.related_tables:
            item["related_tables"] = [tbl.upper() for tbl in t.related_tables]
        if t.tags:
            item["tags"] = t.tags
        if t.examples:
            item["examples"] = t.examples
        terms_data.append(item)

    clean_data = {"terms": terms_data}
    file_path.write_text(yaml.safe_dump(clean_data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def add_or_update_term(annotations_path: Path | str, new_term: GlossaryTerm) -> None:
    glossary = load_glossary(annotations_path)
    norm_new = _normalize_text(new_term.term)

    existing_idx = None
    for idx, t in enumerate(glossary.terms):
        if _normalize_text(t.term) == norm_new:
            existing_idx = idx
            break

    if existing_idx is not None:
        glossary.terms[existing_idx] = new_term
    else:
        glossary.terms.append(new_term)

    save_glossary(annotations_path, glossary)


def delete_term(annotations_path: Path | str, term_name: str) -> bool:
    """Removes a glossary term by name. Returns True if found and deleted, False otherwise."""
    glossary = load_glossary(annotations_path)
    norm_target = _normalize_text(term_name)
    initial_len = len(glossary.terms)
    glossary.terms = [t for t in glossary.terms if _normalize_text(t.term) != norm_target]
    if len(glossary.terms) < initial_len:
        save_glossary(annotations_path, glossary)
        return True
    return False


def search_glossary(glossary: BusinessGlossary, query: str) -> list[tuple[GlossaryTerm, int]]:
    """Searches glossary terms returning matches sorted by relevance score."""
    if not query.strip():
        return [(t, 100) for t in glossary.terms]

    norm_query = _normalize_text(query)
    tokens = [t for t in norm_query.split() if len(t) >= 2]
    if not tokens:
        tokens = [norm_query]

    matches: list[tuple[GlossaryTerm, int]] = []
    for t in glossary.terms:
        score = 0
        norm_term = _normalize_text(t.term)
        norm_def = _normalize_text(t.definition)
        norm_filter = _normalize_text(t.canonical_filter or "")
        norm_tbl = _normalize_text(t.primary_table or "")
        norm_tags = " ".join(_normalize_text(tag) for tag in t.tags)

        # Exact or substring match in term
        if norm_query in norm_term or norm_term in norm_query:
            score += 100

        # Token checks
        for token in tokens:
            if token in norm_term:
                score += 50
            if token in norm_def:
                score += 30
            if token in norm_tbl:
                score += 25
            if token in norm_filter:
                score += 20
            if token in norm_tags:
                score += 15

        if score > 0:
            matches.append((t, score))

    matches.sort(key=lambda x: x[1], reverse=True)
    return matches
