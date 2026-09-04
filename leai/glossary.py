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


def load_glossary(
    annotations_path: Path | str | None = None,
    content: str | None = None,
) -> BusinessGlossary:
    """Loads a BusinessGlossary from a local file path or from a YAML string."""
    if content is not None:
        try:
            raw = yaml.safe_load(content)
            if isinstance(raw, dict):
                return BusinessGlossary.model_validate(raw)
        except Exception as exc:
            print(f"Warning: Error parsing glossary content: {exc}", file=sys.stderr)
        return BusinessGlossary()

    if annotations_path is None:
        return BusinessGlossary()

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


def dump_glossary_yaml(glossary: BusinessGlossary) -> str:
    """Serializes BusinessGlossary to clean YAML format."""
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
    return yaml.safe_dump(clean_data, sort_keys=False, allow_unicode=True)


def merge_glossaries(base: BusinessGlossary, delta: BusinessGlossary) -> BusinessGlossary:
    """Merges two BusinessGlossary objects non-destructively.

    If the same term exists in both:
    - Base (remote/existing SeaweedFS) definition and canonical_filter are prioritized if present.
    - If base definition or canonical_filter is empty/blank, delta is used.
    - primary_table is preserved from base, or filled from delta if empty.
    - tags, related_tables, and examples are combined without duplicates.
    - New terms from delta are added.
    """
    merged_terms: dict[str, GlossaryTerm] = {}

    # 1. Add all base terms
    for t in base.terms:
        norm = _normalize_text(t.term)
        merged_terms[norm] = t.model_copy(deep=True)

    # 2. Merge delta terms
    for dt in delta.terms:
        norm = _normalize_text(dt.term)
        if norm in merged_terms:
            bt = merged_terms[norm]
            # Prioritize base definition if non-empty, otherwise take delta
            chosen_def = bt.definition.strip() if bt.definition and bt.definition.strip() else (dt.definition or "")
            chosen_filter = (
                bt.canonical_filter.strip() if bt.canonical_filter and bt.canonical_filter.strip() else (dt.canonical_filter or None)
            )
            chosen_primary_tbl = bt.primary_table.strip() if bt.primary_table and bt.primary_table.strip() else (dt.primary_table or None)

            # Union of lists preserving order
            merged_tags = list(dict.fromkeys((bt.tags or []) + (dt.tags or [])))
            merged_related = list(dict.fromkeys((bt.related_tables or []) + (dt.related_tables or [])))
            merged_examples = list(dict.fromkeys((bt.examples or []) + (dt.examples or [])))

            merged_terms[norm] = GlossaryTerm(
                term=bt.term or dt.term,
                definition=chosen_def,
                primary_table=chosen_primary_tbl,
                canonical_filter=chosen_filter,
                related_tables=merged_related,
                tags=merged_tags,
                examples=merged_examples,
            )
        else:
            merged_terms[norm] = dt.model_copy(deep=True)

    # Return sorted by term name
    sorted_terms = sorted(merged_terms.values(), key=lambda x: x.term.upper())
    return BusinessGlossary(terms=sorted_terms)


def save_glossary(
    annotations_path: Path | str | None,
    glossary: BusinessGlossary,
    storage: Any = None,
) -> None:
    yaml_content = dump_glossary_yaml(glossary)
    if annotations_path:
        file_path = get_glossary_file(annotations_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(yaml_content, encoding="utf-8")

    if storage is not None and hasattr(storage, "save_glossary"):
        try:
            storage.save_glossary(glossary)
        except Exception as exc:
            print(f"Warning: Failed to save glossary to SeaweedFS: {exc}", file=sys.stderr)


def add_or_update_term(
    annotations_path: Path | str,
    new_term: GlossaryTerm,
    storage: Any = None,
) -> None:
    glossary = load_glossary(annotations_path)
    if storage is not None and hasattr(storage, "load_glossary"):
        try:
            remote_glossary = storage.load_glossary()
            if isinstance(remote_glossary, BusinessGlossary) and remote_glossary.terms:
                glossary = merge_glossaries(remote_glossary, glossary)
        except Exception:
            pass

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

    save_glossary(annotations_path, glossary, storage=storage)


def delete_term(
    annotations_path: Path | str,
    term_name: str,
    storage: Any = None,
) -> bool:
    """Removes a glossary term by name. Returns True if found and deleted, False otherwise."""
    glossary = load_glossary(annotations_path)
    if storage is not None and hasattr(storage, "load_glossary"):
        try:
            remote_glossary = storage.load_glossary()
            if isinstance(remote_glossary, BusinessGlossary) and remote_glossary.terms:
                glossary = merge_glossaries(remote_glossary, glossary)
        except Exception:
            pass

    norm_target = _normalize_text(term_name)
    initial_len = len(glossary.terms)
    glossary.terms = [t for t in glossary.terms if _normalize_text(t.term) != norm_target]
    if len(glossary.terms) < initial_len:
        save_glossary(annotations_path, glossary, storage=storage)
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
