from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from leai.annotations import load_annotation
from leai.compression import extract_subprogram_block
from leai.config import LeaiConfig
from leai.models import SchemaMetadata
from leai.raw import trace_raw_dependencies

DATABASE_TOOLS_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_business_documentation",
            "description": "Searches human and AI documentation across YAML annotations (descriptions, column comments, business rules, tags) and Markdown documents for business concepts, domain keywords, and functional rules (e.g. 'férias', 'afastamento', 'cálculo de proventos', 'adicional noturno'). Use this when the user asks conceptual questions or when table names are not obvious.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The business concept, functional term, or keyword to search in documentation (e.g. 'ferias', 'afastamento', 'licenca', 'salario').",
                    },
                    "object_type": {
                        "type": "string",
                        "description": "Optional filter by object type: 'table', 'view', 'package', 'procedure', 'function', 'trigger'.",
                    },
                    "search_fields": {
                        "type": "string",
                        "description": "Optional fields to search: 'all' (default), 'descriptions', 'columns', 'rules', 'tags'.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_database_objects",
            "description": "Searches tables, views, materialized views, packages, procedures, functions, triggers, and synonyms in the database catalog by name or keyword.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search term or partial name of the database object (e.g. 'usuario', 'funcionario', 'pack_ergon', 'tgovpe').",
                    },
                    "object_type": {
                        "type": "string",
                        "description": "Optional filter by object type: 'table', 'view', 'package', 'procedure', 'function', 'trigger', 'synonym'.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_column_comments",
            "description": "Searches for column names and Oracle column comments (ALL_COL_COMMENTS) across all tables, views, and materialized views in the database. Use this tool specifically when the user asks 'qual tabela tem o campo/data X?', 'onde fica a coluna Y?', 'qual tabela guarda a data de recadastramento?' or whenever searching for specific data attributes and column descriptions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Keyword, column prefix, or concept to find in column comments or column names (e.g. 'recadastramento', 'cpf', 'data nascimento', 'dt_recad', 'salario').",
                    },
                    "object_type": {
                        "type": "string",
                        "description": "Optional filter: 'table', 'view', 'mview', or 'table,view'. Default searches all.",
                    },
                    "table_name": {
                        "type": "string",
                        "description": "Optional filter by specific table or view name.",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum column matches to return (default 25).",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_table_schema",
            "description": "Retrieves full detailed schema metadata of a table or view: columns, data types, nullability, primary key, foreign keys, and business rules. If given a SYNONYM name, it automatically dereferences it to the target table.",
            "parameters": {
                "type": "object",
                "properties": {
                    "table_name": {
                        "type": "string",
                        "description": "Exact name of the table or synonym to inspect (e.g. 'VINCULOS', 'EVENTO_FUNC', 'USUARIOS').",
                    },
                },
                "required": ["table_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_subprogram_source",
            "description": "Retrieves the exact PL/SQL source code and business logic of a procedure, function, package routine, or SYNONYM. If given a standalone procedure/function or a synonym name, it automatically dereferences and extracts the source code.",
            "parameters": {
                "type": "object",
                "properties": {
                    "package_name": {
                        "type": "string",
                        "description": "Optional name of the PL/SQL package (e.g. 'PACK_ERGON', 'PACK_CERGON'). Leave empty if inspecting a standalone procedure/function or synonym.",
                    },
                    "subprogram_name": {
                        "type": "string",
                        "description": "Name of the procedure, function, routine, or synonym (e.g. 'TGOVPE_RMS_ENVIA_ARQ_CREDITO', 'GET_SETOR_FUNC', 'CALCULA_SALARIO').",
                    },
                },
                "required": ["subprogram_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "trace_object_lineage",
            "description": "Traces technical impact, risk level, upstream consumed tables/packages, target objects for SYNONYMS, and downstream callers/consumers of any database object.",
            "parameters": {
                "type": "object",
                "properties": {
                    "object_name": {
                        "type": "string",
                        "description": "Name of the table, view, procedure, synonym, or package to analyze (e.g. 'TGOVPE_RMS_ENVIA_ARQ_CREDITO', 'PACK_ERGON.GET_SETOR_FUNC', 'VINCULOS').",
                    },
                    "depth": {
                        "type": "integer",
                        "description": "Search depth for relationship traversal (default 1, max 3).",
                    },
                },
                "required": ["object_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep_plsql_code",
            "description": "Searches for a text pattern, constant name, column name, or regex across all PL/SQL packages, procedures, and triggers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Text or regex pattern to search across code sources (e.g. 'C_RETORNA_NULO', 'DTVAC', 'GET_OPCAO').",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of code matches to return (default 10).",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
]


def resolve_synonym(schemas: list[SchemaMetadata], name: str) -> dict[str, Any] | None:
    """Resolves a synonym name to its target owner, target object name, db link, and target object type."""
    if not name:
        return None
    n_up = name.strip().upper()
    for s in schemas:
        for syn in s.synonyms:
            if syn.name.upper() == n_up:
                target_owner = (syn.table_owner or "").upper()
                target_name = (syn.table_name or "").upper()

                target_type = "UNKNOWN"
                target_obj = None

                # Check tables
                for s2 in schemas:
                    for t in s2.tables:
                        if t.name.upper() == target_name:
                            target_type = "TABLE"
                            target_obj = t
                            break
                    if target_obj:
                        break
                    for v in s2.views:
                        if v.name.upper() == target_name:
                            target_type = "VIEW"
                            target_obj = v
                            break
                    if target_obj:
                        break
                    for mv in s2.mviews:
                        if mv.name.upper() == target_name:
                            target_type = "MATERIALIZED VIEW"
                            target_obj = mv
                            break
                    if target_obj:
                        break
                    for co in s2.code_objects:
                        if co.name.upper() == target_name:
                            target_type = co.object_type.upper()
                            target_obj = co
                            break
                        for sp in co.subprograms:
                            if sp.name.upper() == target_name:
                                target_type = f"{co.object_type.upper()} SUBPROGRAM ({sp.subprogram_type})"
                                target_obj = sp
                                break
                    if target_obj:
                        break

                return {
                    "synonym_name": syn.name,
                    "target_owner": target_owner,
                    "target_name": target_name,
                    "db_link": syn.db_link,
                    "target_type": target_type,
                    "target_object": target_obj,
                }
    return None


def _normalize_text(text: str) -> str:
    """Removes diacritics and accents for robust case-insensitive search."""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", str(text))
    return "".join(c for c in normalized if not unicodedata.combining(c)).upper()


def _extract_search_tokens(query: str) -> list[str]:
    """Generates search tokens and Portuguese morphological roots/stems from the query."""
    if not query:
        return []
    q_norm = _normalize_text(query).strip()
    if not q_norm:
        return []
    raw_words = [w for w in re.split(r"[\s,;_\-\.:/\\]+", q_norm) if len(w) >= 2]
    tokens = set(raw_words)
    tokens.add(q_norm)

    for w in raw_words:
        if len(w) >= 5:
            tokens.add(w[:5])
            tokens.add(w[:6])
            tokens.add(w[:7])
            tokens.add(w[:8])
            for suffix in ("AMENTO", "IMENTO", "ACOES", "ICOES", "ACAO", "ICAO", "ADO", "ADA", "ADOS", "ADAS", "AL", "AIS", "AR", "ER", "IR", "OS", "AS", "ES", "IS", "OR", "ORES"):
                if w.endswith(suffix) and len(w) - len(suffix) >= 4:
                    tokens.add(w[:-len(suffix)])

    return [t for t in tokens if len(t) >= 3]


def _parse_target_types(object_type: str | None) -> set[str] | None:
    """Parses and normalizes single or comma-separated object types (e.g. 'table,view', 'tables, views')."""
    if not object_type:
        return None
    raw_list = [item.strip().upper() for item in re.split(r"[,;\s]+", object_type.strip().upper()) if item.strip()]
    result: set[str] = set()
    for item in raw_list:
        clean = item.rstrip("S")
        result.add(clean)
        result.add(f"{clean}S")
        if clean in ("MATERIALIZED VIEW", "MVIEW"):
            result.update({"MVIEW", "MVIEWS", "MATERIALIZED VIEW", "MATERIALIZED VIEWS"})
        elif clean in ("PACKAGE_BODY", "PACKAGE_BODYS", "PACKAGE"):
            result.update({"PACKAGE", "PACKAGES", "PACKAGE_BODY", "PACKAGE_BODYS"})
        elif clean in ("TYPE_BODY", "TYPE_BODYS", "TYPE"):
            result.update({"TYPE", "TYPES", "TYPE_BODY", "TYPE_BODYS"})
    return result if result else None


def search_business_documentation(
    schemas: list[SchemaMetadata],
    config: LeaiConfig,
    query: str,
    object_type: str | None = None,
    search_fields: str | None = None,
) -> list[dict[str, Any]]:
    """Searches human and AI documentation across YAML annotations, Oracle dictionary comments, and columns for business concepts."""
    if not query or not query.strip():
        return []

    q_raw = query.strip()
    tokens = _extract_search_tokens(q_raw)
    if not tokens:
        tokens = [_normalize_text(q_raw)]

    target_types = _parse_target_types(object_type)
    fields_filter = (search_fields or "all").strip().lower()

    results: list[dict[str, Any]] = []
    seen_keys: set[str] = set()

    # 1. Search in YAML Annotations (config.annotationsPath)
    ann_path = config.annotationsPath
    if ann_path and ann_path.exists():
        for yml_file in ann_path.glob("**/*.yml"):
            try:
                rel_parts = yml_file.relative_to(ann_path).parts
                if not rel_parts:
                    continue

                if len(rel_parts) >= 3:
                    schema_name = rel_parts[0].upper()
                    cat_folder = rel_parts[1].lower()
                    obj_name = yml_file.stem.upper()
                elif len(rel_parts) == 2:
                    schema_name = (schemas[0].schema_name if schemas else config.schema_name or "DEFAULT").upper()
                    cat_folder = rel_parts[0].lower()
                    obj_name = yml_file.stem.upper()
                else:
                    continue

                obj_type = cat_folder.rstrip("s").upper()
                if obj_type in ("PACKAGE_BODY", "PACKAGE_BODYS"):
                    obj_type = "PACKAGE"
                elif obj_type in ("TYPE_BODY", "TYPE_BODYS"):
                    obj_type = "TYPE"

                if target_types and obj_type not in target_types and f"{obj_type}S" not in target_types:
                    continue

                ann = load_annotation(yml_file)
                score = 0
                matched_fields = []
                snippets = []

                # Name check
                norm_name = _normalize_text(obj_name)
                if any(t in norm_name for t in tokens):
                    score += 50
                    matched_fields.append("name")

                # Description check
                if fields_filter in ("all", "descriptions", "description") and ann.description:
                    norm_desc = _normalize_text(ann.description)
                    if any(t in norm_desc for t in tokens):
                        score += 45
                        matched_fields.append("description")
                        snippets.append(f"description: '{ann.description}'")

                # Business rules check
                if fields_filter in ("all", "rules", "business_rules") and ann.business_rules:
                    for rule in ann.business_rules:
                        norm_rule = _normalize_text(rule)
                        if any(t in norm_rule for t in tokens):
                            score += 35
                            if "business_rules" not in matched_fields:
                                matched_fields.append("business_rules")
                            snippets.append(f"rule: '{rule}'")

                # Columns check
                if fields_filter in ("all", "columns", "cols") and ann.columns:
                    for col_name, col_desc in ann.columns.items():
                        desc_str = col_desc if isinstance(col_desc, str) else (col_desc.get("description", "") if isinstance(col_desc, dict) else str(col_desc))
                        norm_col = _normalize_text(f"{col_name} {desc_str}")
                        if any(t in norm_col for t in tokens):
                            score += 40
                            matched_fields.append(f"column: {col_name}")
                            snippets.append(f"coluna {col_name}: '{desc_str}'")

                # Tags check
                if fields_filter in ("all", "tags") and ann.tags:
                    for tag in ann.tags:
                        if any(t in _normalize_text(tag) for t in tokens):
                            score += 25
                            matched_fields.append(f"tag: {tag}")
                            snippets.append(f"tag: '{tag}'")

                if score > 0:
                    item_key = f"{schema_name}.{obj_name}"
                    seen_keys.add(item_key)
                    results.append({
                        "object_name": obj_name,
                        "object_type": obj_type,
                        "schema": schema_name,
                        "relevance_score": score,
                        "matched_fields": matched_fields,
                        "description": ann.description or "",
                        "matched_snippets": snippets[:5],
                        "business_rules": ann.business_rules,
                        "tags": ann.tags,
                    })
            except Exception:
                continue

    # 2. Also search SchemaMetadata dictionary comments & columns
    for s in schemas:
        s_name = (s.schema_name or "DEFAULT").upper()
        all_objs = (
            [("TABLE", t.name, t.comment, [(c.name, c.comment) for c in t.columns]) for t in s.tables]
            + [("VIEW", v.name, v.comment, [(c.name, c.comment) for c in v.columns]) for v in s.views]
            + [("MVIEW", mv.name, mv.comment, [(c.name, c.comment) for c in mv.columns]) for mv in s.mviews]
            + [("PACKAGE" if co.object_type.upper() == "PACKAGE" else co.object_type.upper(), co.name, co.comment, [(sp.name, sp.comment) for sp in co.subprograms]) for co in s.code_objects]
            + [("TRIGGER", tr.name, None, []) for tr in s.triggers]
            + [("SYNONYM", syn.name, None, []) for syn in s.synonyms]
        )

        for otype, oname, ocomment, subitems in all_objs:
            if target_types and otype not in target_types and f"{otype}S" not in target_types:
                continue
            item_key = f"{s_name}.{oname.upper()}"
            if item_key in seen_keys:
                continue

            score = 0
            matched_fields = []
            snippets = []

            norm_name = _normalize_text(oname)
            if any(t in norm_name for t in tokens):
                score += 30
                matched_fields.append("name")

            if ocomment:
                norm_ocomment = _normalize_text(ocomment)
                if any(t in norm_ocomment for t in tokens):
                    score += 45
                    matched_fields.append("oracle_comment")
                    snippets.append(f"comment: '{ocomment}'")

            for sname, scomment in subitems:
                norm_sname = _normalize_text(sname)
                norm_scomment = _normalize_text(scomment or "")
                matched_sub = False
                if any(t in norm_sname for t in tokens):
                    score += 35
                    matched_sub = True
                if scomment and any(t in norm_scomment for t in tokens):
                    score += 45
                    matched_sub = True

                if matched_sub:
                    matched_fields.append(f"column/routine: {sname}")
                    snippets.append(f"coluna {sname}: '{scomment}'" if scomment else f"coluna {sname}")

            if score > 0:
                seen_keys.add(item_key)
                results.append({
                    "object_name": oname.upper(),
                    "object_type": otype,
                    "schema": s_name,
                    "relevance_score": score,
                    "matched_fields": matched_fields,
                    "description": ocomment or "",
                    "matched_snippets": snippets[:5],
                    "business_rules": [],
                    "tags": [],
                })

    # Sort results by relevance_score descending
    results.sort(key=lambda x: x["relevance_score"], reverse=True)
    return results[:15]


def search_database_objects(
    schemas: list[SchemaMetadata],
    query: str,
    object_type: str | None = None,
    config: LeaiConfig | None = None,
) -> list[dict[str, Any]]:
    q_norm = _normalize_text(query).strip()
    words = [w for w in q_norm.split() if w]
    tokens = _extract_search_tokens(query)
    target_types = _parse_target_types(object_type)
    results: list[dict[str, Any]] = []

    def _matches_text(text: str) -> bool:
        norm = _normalize_text(text)
        if q_norm and q_norm in norm:
            return True
        if words and len(words) > 1 and all(w in norm for w in words):
            return True
        if "_" not in q_norm and tokens and any(tok in norm for tok in tokens):
            return True
        return False

    for s in schemas:
        s_name = s.schema_name or "DEFAULT"
        is_multi = len(schemas) > 1 or (config and config.is_all_schemas)

        # Tables
        if not target_types or "TABLE" in target_types or "TABLES" in target_types:
            for t in s.tables:
                ann_desc = ""
                if config and config.annotationsPath:
                    ann_dir = config.annotationsPath / s_name if is_multi else config.annotationsPath
                    ann_file = ann_dir / "tables" / f"{t.name}.yml"
                    if ann_file.exists():
                        ann = load_annotation(ann_file)
                        ann_desc = ann.description or ""

                cols_text = " ".join(f"{c.name} {c.comment or ''}" for c in t.columns)
                haystack = f"{t.name} {t.comment or ''} {ann_desc} {cols_text}"
                if _matches_text(haystack):
                    matched_cols = [c.name for c in t.columns if _matches_text(f"{c.name} {c.comment or ''}")]
                    results.append({
                        "name": t.name,
                        "type": "TABLE",
                        "schema": s_name,
                        "comment": t.comment or (ann_desc if ann_desc else None),
                        "column_count": len(t.columns),
                        "matched_columns": matched_cols[:5],
                    })

        # Views
        if not target_types or "VIEW" in target_types or "VIEWS" in target_types:
            for v in s.views:
                cols_text = " ".join(f"{c.name} {c.comment or ''}" for c in v.columns)
                haystack = f"{v.name} {v.comment or ''} {cols_text}"
                if _matches_text(haystack):
                    matched_cols = [c.name for c in v.columns if _matches_text(f"{c.name} {c.comment or ''}")]
                    results.append({
                        "name": v.name,
                        "type": "VIEW",
                        "schema": s_name,
                        "comment": v.comment,
                        "matched_columns": matched_cols[:5],
                    })

        # Materialized Views
        if not target_types or any(t in target_types for t in ("MVIEW", "MVIEWS", "MATERIALIZED VIEW", "MATERIALIZED VIEWS")):
            for mv in s.mviews:
                cols_text = " ".join(f"{c.name} {c.comment or ''}" for c in mv.columns)
                haystack = f"{mv.name} {mv.comment or ''} {cols_text}"
                if _matches_text(haystack):
                    results.append({
                        "name": mv.name,
                        "type": "MATERIALIZED VIEW",
                        "schema": s_name,
                        "comment": mv.comment,
                    })

        # Code Objects (Packages, Procedures, Functions)
        for co in s.code_objects:
            c_type = co.object_type.upper()
            if not target_types or c_type in target_types or f"{c_type}S" in target_types:
                if _matches_text(f"{co.name} {co.comment or ''}"):
                    results.append({
                        "name": co.name,
                        "type": c_type,
                        "schema": s_name,
                        "subprograms_count": len(co.subprograms),
                        "comment": co.comment,
                    })

            # Subprograms inside packages
            for sp in co.subprograms:
                sp_full = f"{co.name}.{sp.name}"
                if not target_types or any(t in target_types for t in (sp.subprogram_type.upper(), f"{sp.subprogram_type.upper()}S", "SUBPROGRAM", "SUBPROGRAMS")):
                    if _matches_text(f"{sp.name} {sp_full} {sp.comment or ''}"):
                        results.append({
                            "name": sp_full,
                            "type": f"{co.object_type}.{sp.subprogram_type}",
                            "schema": s_name,
                            "package": co.name,
                            "subprogram": sp.name,
                            "comment": sp.comment,
                        })

        # Triggers
        if not target_types or "TRIGGER" in target_types or "TRIGGERS" in target_types:
            for trg in s.triggers:
                if _matches_text(f"{trg.name} {trg.table_name or ''}"):
                    results.append({
                        "name": trg.name,
                        "type": "TRIGGER",
                        "schema": s_name,
                        "table_name": trg.table_name,
                        "event": f"{trg.trigger_type} {trg.triggering_event}",
                    })

        # Synonyms
        if not target_types or "SYNONYM" in target_types or "SYNONYMS" in target_types:
            for syn in s.synonyms:
                if _matches_text(f"{syn.name} {syn.table_name or ''}"):
                    target_info = resolve_synonym(schemas, syn.name)
                    target_desc = f"{syn.table_owner or ''}.{syn.table_name or ''}"
                    if target_info and target_info.get("target_type") != "UNKNOWN":
                        target_desc += f" ({target_info['target_type']})"
                    results.append({
                        "name": syn.name,
                        "type": "SYNONYM",
                        "schema": s_name,
                        "points_to": target_desc,
                    })

    # Return top 25 matches sorted by closest name match
    results.sort(key=lambda x: (0 if _normalize_text(x["name"]) == q_norm else (1 if _normalize_text(x["name"]).startswith(q_norm) else 2), x["name"]))
    return results[:25]


def search_column_comments(
    schemas: list[SchemaMetadata],
    query: str,
    object_type: str | None = None,
    table_name: str | None = None,
    max_results: int = 25,
    config: LeaiConfig | None = None,
) -> list[dict[str, Any]]:
    """Searches column names and Oracle column comments across all tables, views, and materialized views."""
    q_norm = _normalize_text(query).strip()
    if not q_norm:
        return []

    tokens = _extract_search_tokens(query)
    target_types = _parse_target_types(object_type)
    target_table = table_name.strip().upper() if table_name else None

    matches: list[dict[str, Any]] = []

    def _score_and_match(text: str, col_name: str) -> tuple[bool, int]:
        t_norm = _normalize_text(text)
        c_norm = _normalize_text(col_name)
        score = 0

        # Exact query match in comment or column name
        if q_norm in t_norm:
            score += 100
        if q_norm in c_norm:
            score += 80

        # Token / stem matching
        for tok in tokens:
            if tok in t_norm:
                score += 30
            if tok in c_norm:
                score += 25

        return (score > 0, score)

    for s in schemas:
        s_name = (s.schema_name or "DEFAULT").upper()

        # 1. Tables
        if not target_types or any(t in target_types for t in ("TABLE", "TABLES")):
            for t in s.tables:
                t_up = t.name.upper()
                if target_table and t_up != target_table and f"{s_name}.{t_up}" != target_table:
                    continue

                ann = None
                if config:
                    is_multi = len(schemas) > 1 or config.is_all_schemas
                    ann_dir = config.annotationsPath / s_name if is_multi else config.annotationsPath
                    ann_file = ann_dir / "tables" / f"{t.name}.yml"
                    ann = load_annotation(ann_file) if ann_file.exists() else None

                pk_cols = set(t.primary_keys) if t.primary_keys else set()

                for c in t.columns:
                    comment = (ann and ann.columns.get(c.name)) or c.comment or ""
                    matched, score = _score_and_match(f"{comment} {t.comment or ''}", c.name)
                    if matched:
                        matches.append({
                            "schema": s_name,
                            "table_name": t.name,
                            "qualified_name": f"{s_name}.{t.name}",
                            "object_type": "TABLE",
                            "column_name": c.name,
                            "data_type": c.data_type,
                            "nullable": c.nullable,
                            "is_pk": c.name in pk_cols,
                            "comment": comment or "(Sem comentário)",
                            "table_comment": t.comment or "",
                            "_score": score,
                        })

        # 2. Views
        if not target_types or any(t in target_types for t in ("VIEW", "VIEWS")):
            for v in s.views:
                v_up = v.name.upper()
                if target_table and v_up != target_table and f"{s_name}.{v_up}" != target_table:
                    continue

                ann = None
                if config:
                    is_multi = len(schemas) > 1 or config.is_all_schemas
                    ann_dir = config.annotationsPath / s_name if is_multi else config.annotationsPath
                    ann_file = ann_dir / "views" / f"{v.name}.yml"
                    ann = load_annotation(ann_file) if ann_file.exists() else None

                for c in v.columns:
                    comment = (ann and ann.columns.get(c.name)) or c.comment or ""
                    matched, score = _score_and_match(f"{comment} {v.comment or ''}", c.name)
                    if matched:
                        matches.append({
                            "schema": s_name,
                            "table_name": v.name,
                            "qualified_name": f"{s_name}.{v.name}",
                            "object_type": "VIEW",
                            "column_name": c.name,
                            "data_type": c.data_type,
                            "nullable": c.nullable,
                            "is_pk": False,
                            "comment": comment or "(Sem comentário)",
                            "table_comment": v.comment or "",
                            "_score": score,
                        })

        # 3. Materialized Views
        if not target_types or any(t in target_types for t in ("MVIEW", "MVIEWS", "MATERIALIZED VIEW", "MATERIALIZED VIEWS")):
            for mv in s.mviews:
                mv_up = mv.name.upper()
                if target_table and mv_up != target_table and f"{s_name}.{mv_up}" != target_table:
                    continue

                for c in mv.columns:
                    comment = c.comment or ""
                    matched, score = _score_and_match(f"{comment} {mv.comment or ''}", c.name)
                    if matched:
                        matches.append({
                            "schema": s_name,
                            "table_name": mv.name,
                            "qualified_name": f"{s_name}.{mv.name}",
                            "object_type": "MATERIALIZED VIEW",
                            "column_name": c.name,
                            "data_type": c.data_type,
                            "nullable": c.nullable,
                            "is_pk": False,
                            "comment": comment or "(Sem comentário)",
                            "table_comment": mv.comment or "",
                            "_score": score,
                        })

    matches.sort(key=lambda x: (-x["_score"], x["table_name"], x["column_name"]))
    for m in matches:
        m.pop("_score", None)

    return matches[:max_results]


def get_table_schema(
    schemas: list[SchemaMetadata],
    config: LeaiConfig,
    table_name: str,
) -> dict[str, Any]:
    raw_name = table_name.strip().upper()
    target_schema: str | None = None
    target_name = raw_name
    if "." in raw_name:
        parts = raw_name.split(".", 1)
        target_schema = parts[0].strip()
        target_name = parts[1].strip()

    # 1. Search in Tables
    for s in schemas:
        s_name = (s.schema_name or "DEFAULT").upper()
        if target_schema and s_name != target_schema:
            continue
        for t in s.tables:
            if t.name.upper() == target_name:
                is_multi = len(schemas) > 1 or config.is_all_schemas
                ann_dir = config.annotationsPath / s_name if is_multi else config.annotationsPath
                ann_file = ann_dir / "tables" / f"{t.name}.yml"
                ann = load_annotation(ann_file) if ann_file.exists() else None

                pk_cols = set(t.primary_keys) if t.primary_keys else set()

                cols_info = []
                for c in t.columns:
                    col_doc = (ann and ann.columns.get(c.name)) or c.comment or ""
                    cols_info.append({
                        "name": c.name,
                        "type": c.data_type,
                        "nullable": c.nullable,
                        "is_pk": c.name in pk_cols,
                        "description": col_doc,
                    })

                fks_info = []
                for fk in t.foreign_keys:
                    fks_info.append({
                        "name": fk.name,
                        "column": fk.column,
                        "references_table": fk.referenced_table,
                        "references_column": fk.referenced_column,
                    })

                return {
                    "table_name": t.name,
                    "type": "TABLE",
                    "schema": s_name,
                    "comment": t.comment,
                    "business_description": ann.description if ann else None,
                    "business_rules": ann.business_rules if ann else [],
                    "tags": ann.tags if ann else [],
                    "columns": cols_info,
                    "foreign_keys": fks_info,
                }

    # 2. Search in Views
    for s in schemas:
        s_name = (s.schema_name or "DEFAULT").upper()
        if target_schema and s_name != target_schema:
            continue
        for v in s.views:
            if v.name.upper() == target_name:
                is_multi = len(schemas) > 1 or config.is_all_schemas
                ann_dir = config.annotationsPath / s_name if is_multi else config.annotationsPath
                ann_file = ann_dir / "views" / f"{v.name}.yml"
                ann = load_annotation(ann_file) if ann_file.exists() else None

                cols_info = []
                for c in v.columns:
                    col_doc = (ann and ann.columns.get(c.name)) or c.comment or ""
                    cols_info.append({
                        "name": c.name,
                        "type": c.data_type,
                        "nullable": c.nullable,
                        "is_pk": False,
                        "description": col_doc,
                    })

                return {
                    "table_name": v.name,
                    "type": "VIEW",
                    "schema": s_name,
                    "comment": v.comment,
                    "business_description": ann.description if ann else None,
                    "business_rules": ann.business_rules if ann else [],
                    "tags": ann.tags if ann else [],
                    "columns": cols_info,
                    "foreign_keys": [],
                }

    # 3. Search in Materialized Views
    for s in schemas:
        s_name = (s.schema_name or "DEFAULT").upper()
        if target_schema and s_name != target_schema:
            continue
        for mv in s.mviews:
            if mv.name.upper() == target_name:
                cols_info = []
                for c in mv.columns:
                    cols_info.append({
                        "name": c.name,
                        "type": c.data_type,
                        "nullable": c.nullable,
                        "is_pk": False,
                        "description": c.comment or "",
                    })

                return {
                    "table_name": mv.name,
                    "type": "MATERIALIZED VIEW",
                    "schema": s_name,
                    "comment": mv.comment,
                    "business_description": None,
                    "business_rules": [],
                    "tags": [],
                    "columns": cols_info,
                    "foreign_keys": [],
                }

    # 4. If not found directly, check if table_name is a synonym
    syn_info = resolve_synonym(schemas, target_name)
    if syn_info and syn_info.get("target_name") and syn_info["target_name"] != target_name:
        resolved_table = get_table_schema(schemas, config, syn_info["target_name"])
        if "error" not in resolved_table:
            resolved_table["accessed_via_synonym"] = raw_name
            resolved_table["synonym_target_owner"] = syn_info["target_owner"]
            return resolved_table

    return {"error": f"Table/View '{table_name}' was not found in the loaded schemas."}


def get_subprogram_source(
    schemas: list[SchemaMetadata],
    package_name: str | None = None,
    subprogram_name: str | None = None,
) -> dict[str, Any]:
    p_name = (package_name or "").strip().upper()
    sp_name = (subprogram_name or "").strip().upper()

    target_schema: str | None = None
    if sp_name and not p_name:
        parts = sp_name.split(".")
        if len(parts) == 3:
            target_schema, p_name, sp_name = parts[0], parts[1], parts[2]
        elif len(parts) == 2:
            p_name, sp_name = parts[0], parts[1]
    elif p_name and "." in p_name:
        parts = p_name.split(".", 1)
        target_schema, p_name = parts[0], parts[1]

    search_names = [n for n in (p_name, sp_name) if n]
    if not search_names:
        return {"error": "Please provide a package_name and/or subprogram_name to inspect."}

    # 1. Search inside packages
    if p_name and sp_name:
        package_found = False
        for s in schemas:
            s_name = (s.schema_name or "DEFAULT").upper()
            if target_schema and s_name != target_schema:
                continue
            for co in s.code_objects:
                if co.name.upper() == p_name:
                    package_found = True
                    for sp in co.subprograms:
                        if sp.name.upper() == sp_name:
                            code_src = sp.source or (extract_subprogram_block(co.source, sp.name) if co.source else "")
                            return {
                                "package_name": co.name,
                                "subprogram_name": sp.name,
                                "subprogram_type": sp.subprogram_type,
                                "schema": s_name,
                                "source_code": code_src,
                            }

                    if co.source:
                        code_src = extract_subprogram_block(co.source, sp_name)
                        if code_src:
                            return {
                                "package_name": co.name,
                                "subprogram_name": sp_name,
                                "subprogram_type": "SUBPROGRAM",
                                "schema": s_name,
                                "source_code": code_src,
                            }

        if package_found:
            return {"error": f"Subprogram '{sp_name}' was not found inside package '{p_name}'."}

    # 2. Search standalone code objects (Procedures, Functions, Packages)
    name_candidate = sp_name or p_name
    for s in schemas:
        s_name = (s.schema_name or "DEFAULT").upper()
        if target_schema and s_name != target_schema:
            continue
        for co in s.code_objects:
            if co.name.upper() == name_candidate:
                return {
                    "package_name": None if co.object_type.upper() != "PACKAGE" else co.name,
                    "subprogram_name": co.name,
                    "subprogram_type": co.object_type.upper(),
                    "schema": s_name,
                    "source_code": co.source or f"-- Objeto {co.object_type} {co.name} registrado sem fonte inline.",
                }

    # 3. Check Synonyms
    syn_info = resolve_synonym(schemas, name_candidate)
    if syn_info and syn_info.get("target_name") and syn_info["target_name"] != name_candidate:
        target_name = syn_info["target_name"]
        target_owner = (syn_info.get("target_owner") or "").upper()
        matching_entry = None

        for s in schemas:
            s_name = (s.schema_name or "DEFAULT").upper()
            for co in s.code_objects:
                if co.name.upper() == target_name:
                    entry = {
                        "accessed_via_synonym": name_candidate,
                        "synonym_target_owner": syn_info["target_owner"],
                        "package_name": None if co.object_type.upper() != "PACKAGE" else co.name,
                        "subprogram_name": co.name,
                        "subprogram_type": co.object_type.upper(),
                        "schema": s_name,
                        "source_code": co.source or f"-- Objeto {co.object_type} {co.name} registrado sem fonte inline.",
                    }
                    if target_owner and s_name == target_owner:
                        matching_entry = entry
                        break
                    elif not matching_entry:
                        matching_entry = entry

                for sp in co.subprograms:
                    if sp.name.upper() == target_name:
                        code_src = sp.source or (extract_subprogram_block(co.source, sp.name) if co.source else "")
                        entry = {
                            "accessed_via_synonym": name_candidate,
                            "synonym_target_owner": syn_info["target_owner"],
                            "package_name": co.name,
                            "subprogram_name": sp.name,
                            "subprogram_type": sp.subprogram_type,
                            "schema": s_name,
                            "source_code": code_src,
                        }
                        if target_owner and s_name == target_owner:
                            matching_entry = entry
                            break
                        elif not matching_entry:
                            matching_entry = entry

            if matching_entry and target_owner and matching_entry.get("schema") == target_owner:
                break

        if matching_entry:
            return matching_entry

    return {"error": f"Subprogram/Procedure '{sp_name or p_name}' was not found in the loaded schemas or synonyms."}


def trace_object_lineage(
    schemas: list[SchemaMetadata],
    object_name: str,
    depth: int = 1,
) -> dict[str, Any]:
    try:
        depth = min(max(1, int(depth)), 3)
    except Exception:
        depth = 1

    raw_name = object_name.strip().upper()
    target_schema: str | None = None
    target_name = raw_name
    if "." in raw_name:
        parts = raw_name.split(".", 1)
        target_schema, target_name = parts[0].strip(), parts[1].strip()

    trace_res = trace_raw_dependencies(schemas, target_name, max_depth=depth, schema_name=target_schema)
    syn_info = resolve_synonym(schemas, target_name)

    if not trace_res.focal_object and trace_res.focal_type == "UNKNOWN" and not syn_info:
        return {"error": f"Object '{object_name}' was not found for lineage tracing."}

    links_summary = []
    for dep in trace_res.dependencies:
        links_summary.append({
            "source": dep.source_name,
            "source_type": dep.source_type,
            "target": dep.target_name,
            "target_type": dep.target_type,
            "relation": dep.relation_type,
            "details": dep.details,
            "depth": dep.depth,
        })

    obj_name = target_name
    parents = [d.target_name for d in trace_res.dependencies if d.target_name != obj_name and d.relation_type in ("FK_REFERENCES", "DEPENDS_ON", "READS/SELECTS", "EXECUTES/CALLS", "SYNONYM_FOR")]
    children = [d.source_name for d in trace_res.dependencies if d.source_name != obj_name and d.relation_type in ("FK_REFERENCED_BY",)]
    consumers = [
        d.source_name
        for d in trace_res.dependencies
        if d.source_name != obj_name and d.relation_type in ("PLSQL_DEPENDENCY", "TRIGGER_ON", "REFERENCED_BY", "CALLS_SUBPROGRAM")
    ]

    result_payload: dict[str, Any] = {
        "focal_object": trace_res.focal_name or obj_name,
        "focal_type": trace_res.focal_type if trace_res.focal_type != "UNKNOWN" else ("SYNONYM" if syn_info else "UNKNOWN"),
        "total_connections": len(trace_res.dependencies),
        "upstream_parents": sorted(set(parents)),
        "downstream_children": sorted(set(children)),
        "consumers": sorted(set(consumers)),
        "dependencies": links_summary[:50],
    }

    if syn_info:
        result_payload["is_synonym"] = True
        result_payload["points_to"] = {
            "owner": syn_info["target_owner"] or "N/A",
            "target_object": syn_info["target_name"],
            "target_type": syn_info["target_type"],
            "db_link": syn_info["db_link"],
        }
        result_payload["synonym_guidance"] = (
            f"O objeto '{obj_name}' é um SYNONYM que aponta para '{syn_info['target_owner']}.{syn_info['target_name']}' "
            f"(tipo: {syn_info['target_type']}). Para analisar a lógica, use 'get_subprogram_source' para ler o código ou 'get_table_schema' para as colunas."
        )

    return result_payload


def grep_plsql_code(
    schemas: list[SchemaMetadata],
    pattern: str,
    max_results: int = 10,
) -> list[dict[str, Any]]:
    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except Exception:
        regex = re.compile(re.escape(pattern), re.IGNORECASE)

    matches: list[dict[str, Any]] = []

    for s in schemas:
        s_name = s.schema_name or "DEFAULT"

        for co in s.code_objects:
            if not co.source:
                continue
            lines = co.source.splitlines()
            for idx, line in enumerate(lines, 1):
                if regex.search(line):
                    snippet_start = max(0, idx - 3)
                    snippet_end = min(len(lines), idx + 3)
                    snippet = "\n".join(lines[snippet_start:snippet_end])
                    matches.append({
                        "object_name": co.name,
                        "object_type": co.object_type,
                        "schema": s_name,
                        "line_number": idx,
                        "matching_line": line.strip(),
                        "context_snippet": snippet,
                    })
                    if len(matches) >= max_results:
                        return matches

        for trg in s.triggers:
            if not trg.trigger_body:
                continue
            lines = trg.trigger_body.splitlines()
            for idx, line in enumerate(lines, 1):
                if regex.search(line):
                    snippet_start = max(0, idx - 2)
                    snippet_end = min(len(lines), idx + 2)
                    snippet = "\n".join(lines[snippet_start:snippet_end])
                    matches.append({
                        "object_name": trg.name,
                        "object_type": "TRIGGER",
                        "schema": s_name,
                        "line_number": idx,
                        "matching_line": line.strip(),
                        "context_snippet": snippet,
                    })
                    if len(matches) >= max_results:
                        return matches

    return matches


def execute_tool_call(
    tool_name: str,
    arguments: dict[str, Any],
    schemas: list[SchemaMetadata],
    config: LeaiConfig,
) -> str:
    """Dispatches and executes the requested database tool call and returns a JSON string response."""
    try:
        if tool_name == "search_business_documentation":
            res = search_business_documentation(
                schemas,
                config=config,
                query=arguments.get("query", ""),
                object_type=arguments.get("object_type"),
                search_fields=arguments.get("search_fields"),
            )
        elif tool_name == "search_column_comments":
            res = search_column_comments(
                schemas,
                query=arguments.get("query", ""),
                object_type=arguments.get("object_type"),
                table_name=arguments.get("table_name"),
                max_results=arguments.get("max_results", 25),
                config=config,
            )
        elif tool_name == "search_database_objects":
            res = search_database_objects(schemas, query=arguments.get("query", ""), object_type=arguments.get("object_type"), config=config)
        elif tool_name == "get_table_schema":
            res = get_table_schema(schemas, config=config, table_name=arguments.get("table_name", ""))
        elif tool_name == "get_subprogram_source":
            res = get_subprogram_source(
                schemas,
                package_name=arguments.get("package_name"),
                subprogram_name=arguments.get("subprogram_name") or arguments.get("object_name") or arguments.get("package_name"),
            )
        elif tool_name == "trace_object_lineage":
            res = trace_object_lineage(
                schemas,
                object_name=arguments.get("object_name", ""),
                depth=arguments.get("depth", 1),
            )
        elif tool_name == "grep_plsql_code":
            res = grep_plsql_code(
                schemas,
                pattern=arguments.get("pattern", ""),
                max_results=arguments.get("max_results", 10),
            )
        else:
            res = {"error": f"Unknown tool: '{tool_name}'"}
        return json.dumps(res, ensure_ascii=False, indent=2)
    except Exception as exc:
        return json.dumps({"error": f"Tool execution failed ({tool_name}): {str(exc)}"})


def summarize_tool_result(tool_name: str, arguments: dict[str, Any], raw_output: str) -> str:
    """Generates a concise, human-readable summary of a tool execution result."""
    try:
        data = json.loads(raw_output)
        if isinstance(data, dict) and "error" in data:
            return f"❌ {data['error']}"

        if tool_name == "search_column_comments":
            results = data if isinstance(data, list) else data.get("results", [])
            count = len(results)
            if count == 0:
                return "0 colunas encontradas"
            return f"{count} coluna{'s' if count > 1 else ''} encontrada{'s' if count > 1 else ''}"

        if tool_name == "grep_plsql_code":
            matches = data.get("matches", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            count = len(matches)
            if count == 0:
                return "0 ocorrências"
            return f"{count} ocorrência{'s' if count > 1 else ''} encontrada{'s' if count > 1 else ''}"

        if tool_name == "get_table_schema":
            if isinstance(data, dict):
                cols = len(data.get("columns", []))
                pks = len(data.get("primary_keys", []))
                fks = len(data.get("foreign_keys", []))
                pk_str = f", {pks} PK" if pks else ""
                fk_str = f", {fks} FK" if fks else ""
                return f"{cols} colunas{pk_str}{fk_str}"
            return "Tabela recuperada"

        if tool_name == "get_subprogram_source":
            if isinstance(data, dict):
                source = data.get("source", "")
                if source:
                    lines = len(source.splitlines())
                    return f"{lines} linhas de código PL/SQL"
                subprograms = data.get("subprograms", [])
                if subprograms:
                    return f"Pacote com {len(subprograms)} rotinas"
            return "Código PL/SQL extraído"

        if tool_name == "trace_object_lineage":
            if isinstance(data, dict):
                deps = len(data.get("dependencies", []))
                risk = data.get("risk_level", "NORMAL")
                return f"{deps} conexões (Risco: {risk})"
            return "Linhagem mapeada"

        if tool_name == "search_business_documentation":
            results = data.get("results", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            count = len(results)
            if count == 0:
                return "0 resultados na documentação"
            return f"{count} objeto{'s' if count > 1 else ''}/regra{'s' if count > 1 else ''} encontrado{'s' if count > 1 else ''}"

        if tool_name == "search_database_objects":
            results = data.get("results", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            count = len(results)
            if count == 0:
                return "0 objetos encontrados"
            return f"{count} objeto{'s' if count > 1 else ''} encontrado{'s' if count > 1 else ''}"

        if isinstance(data, list):
            return f"{len(data)} itens"
        return "OK"
    except Exception:
        return "Concluído"

