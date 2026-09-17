from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from leai.annotations import ObjectAnnotation, load_annotation
from leai.compression import extract_subprogram_block, minify_plsql_source
from leai.config import LeaiConfig
from leai.models import SchemaMetadata, TableMeta
from leai.raw import trace_raw_dependencies

DATABASE_TOOLS_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "lookup_business_term",
            "description": "Searches the global business glossary (annotations/glossary.yml) for domain concepts, organizational business rules, status codes, and canonical SQL filters (e.g. 'usuários ativos', 'vacanciados no ano', 'folha suplementar', 'cargo efetivo'). ALWAYS call this tool first whenever the user asks for concepts, business definitions, calculation rules, or specific status filters.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The business term, domain concept, status name, or rule to look up (e.g. 'usuario ativo', 'vacanciado', 'folha suplementar').",
                    },
                    "tag": {
                        "type": "string",
                        "description": "Optional tag filter (e.g. 'rh', 'seguranca', 'financeiro').",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_business_documentation",
            "description": "Searches human and AI documentation across YAML annotations (descriptions, column comments, business rules, tags) and Markdown documents for business concepts, domain keywords, and functional rules (e.g. 'vacation', 'leave', 'payroll calculation', 'night shift allowance'). Use this when the user asks conceptual questions or when table names are not obvious.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The business concept, functional term, or keyword to search in documentation (e.g. 'vacation', 'leave', 'payroll', 'salary').",
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
    {
        "type": "function",
        "function": {
            "name": "explain_and_tune_sql",
            "description": "Analyzes an Oracle SQL query for performance anti-patterns, non-sargable filters (functions on indexed columns like TRUNC, TO_CHAR, UPPER, NVL), missing partition/index clauses, predictable Full Table Scans (FTS), NOT IN subqueries with nullable columns, and provides optimized SQL rewrites, compound index recommendations, and analytic windowing advice (e.g. ROW_NUMBER() OVER (PARTITION BY ...)).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The SQL query to inspect, explain, and tune for Oracle Database.",
                    },
                    "target_tables": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of table names involved in the query to inspect schema metadata and index structures.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "validate_oracle_sql",
            "description": "Validates SQL syntax specifically for Oracle Database dialect compatibility, flagging non-Oracle anti-patterns (e.g. LIMIT/OFFSET, ILIKE, BOOLEAN columns, IFNULL, DATEADD, AUTO_INCREMENT, VARCHAR(MAX), text concatenation with '+') and cross-referencing referenced tables and columns against database schema metadata.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "The SQL statement (SELECT, DML, or DDL) to validate for Oracle Database dialect compatibility.",
                    },
                },
                "required": ["sql"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delegate_to_specialist",
            "description": "Delegates an in-depth investigation task to an autonomous specialized subagent (e.g. catalog discovery, deep PL/SQL reverse engineering, lineage risk audit, or patch generation).",
            "parameters": {
                "type": "object",
                "properties": {
                    "specialist_role": {
                        "type": "string",
                        "enum": ["catalog_researcher", "plsql_analyst", "lineage_auditor", "patch_generator", "doc_annotator"],
                        "description": "Role of the specialist subagent: 'catalog_researcher' (tables/cols/synonyms), 'plsql_analyst' (code/logic/DMLs), 'lineage_auditor' (dependencies/consumers/risk), 'patch_generator' (scripts/tests), 'doc_annotator' (business rules/tags).",
                    },
                    "task": {
                        "type": "string",
                        "description": "Clear and detailed description of the objective/investigation for the specialist subagent.",
                    },
                },
                "required": ["specialist_role", "task"],
            },
        },
    },
]


_SCHEMA_ANNOTATIONS_INDEX_CACHE: dict[str, dict[str, Any]] = {}


def _resolve_storage_for_tools(config: LeaiConfig | None) -> Any:
    """Lazily resolves SeaweedFSStorage instance if configured and enabled."""
    if config and getattr(getattr(config, "storage", None), "seaweedfs", None):
        sw = config.storage.seaweedfs
        if getattr(sw, "enabled", False) or getattr(sw, "endpoint_url", None):
            try:
                from leai.storage import SeaweedFSStorage

                return SeaweedFSStorage(sw)
            except Exception:
                return None
    return None


def _get_schema_annotations_index(s_name: str, config: LeaiConfig | None = None, storage: Any = None) -> dict[str, Any]:
    """Retrieves annotations_index.json for a schema with memory caching (from local disk or SeaweedFS)."""
    norm_s = (s_name or "DEFAULT").upper()
    if norm_s in _SCHEMA_ANNOTATIONS_INDEX_CACHE:
        return _SCHEMA_ANNOTATIONS_INDEX_CACHE[norm_s]

    index_data: dict[str, Any] | None = None

    # 1. Try from storage if available
    if storage and hasattr(storage, "load_annotations_index"):
        try:
            res = storage.load_annotations_index(norm_s)
            if res and isinstance(res, dict) and res.get("objects"):
                index_data = res
        except Exception:
            pass

    # 2. Try from local disk annotationsPath
    if index_data is None and config and config.annotationsPath:
        is_multi = config.is_all_schemas or len(config.schemas or []) > 1
        ann_dir = config.annotationsPath / norm_s if is_multi else config.annotationsPath
        local_idx = ann_dir / "annotations_index.json"
        if not local_idx.exists():
            local_idx = config.annotationsPath / "annotations_index.json"
        if local_idx.exists():
            try:
                loaded = json.loads(local_idx.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    index_data = loaded
            except Exception:
                pass

    if index_data is not None:
        _SCHEMA_ANNOTATIONS_INDEX_CACHE[norm_s] = index_data
        return index_data

    return {"schema": norm_s, "enriched_count": 0, "objects": {}}


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
            for suffix in (
                "AMENTO",
                "IMENTO",
                "ACOES",
                "ICOES",
                "ACAO",
                "ICAO",
                "ADO",
                "ADA",
                "ADOS",
                "ADAS",
                "AL",
                "AIS",
                "AR",
                "ER",
                "IR",
                "OS",
                "AS",
                "ES",
                "IS",
                "OR",
                "ORES",
            ):
                if w.endswith(suffix) and len(w) - len(suffix) >= 4:
                    tokens.add(w[: -len(suffix)])

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

    # 0. Search Global Business Glossary (annotations/glossary.yml)
    try:
        from leai.glossary import load_glossary, search_glossary

        storage = _resolve_storage_for_tools(config)
        glossary = load_glossary(config.annotationsPath)
        if not glossary.terms and storage and hasattr(storage, "load_glossary"):
            try:
                remote_glossary = storage.load_glossary()
                if remote_glossary.terms:
                    glossary = remote_glossary
            except Exception:
                pass

        gloss_matches = search_glossary(glossary, q_raw)
        for g_term, g_score in gloss_matches[:5]:
            item_key = f"GLOBAL.{g_term.term.upper()}"
            if item_key not in seen_keys:
                seen_keys.add(item_key)
                matched_snippets = [f"definition: '{g_term.definition}'"]
                if g_term.canonical_filter:
                    matched_snippets.append(f"canonical_filter: '{g_term.canonical_filter}'")
                results.append(
                    {
                        "object_name": g_term.term,
                        "object_type": "GLOSSARY_TERM",
                        "schema": "GLOBAL",
                        "relevance_score": g_score + 60,
                        "matched_fields": ["glossary_term", "business_rules"],
                        "description": g_term.definition,
                        "matched_snippets": matched_snippets,
                        "business_rules": [
                            f"{g_term.term}: {g_term.definition}"
                            + (f" (Filtro Canônico: {g_term.canonical_filter})" if g_term.canonical_filter else "")
                        ],
                        "tags": g_term.tags,
                    }
                )
    except Exception:
        pass

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
                if target_types and obj_type not in target_types and f"{obj_type}S" not in target_types:
                    continue

                norm_name = _normalize_text(obj_name)
                name_matched = any(t in norm_name for t in tokens)

                raw_text = yml_file.read_text(encoding="utf-8", errors="ignore")
                norm_raw = _normalize_text(raw_text)
                if not name_matched and not any(t in norm_raw for t in tokens):
                    continue

                ann = load_annotation(yml_file)
                score = 0
                matched_fields = []
                snippets = []

                # Name check
                if name_matched:
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
                        desc_str = (
                            col_desc
                            if isinstance(col_desc, str)
                            else (col_desc.get("description", "") if isinstance(col_desc, dict) else str(col_desc))
                        )
                        norm_col = _normalize_text(f"{col_name} {desc_str}")
                        if any(t in norm_col for t in tokens):
                            score += 40
                            matched_fields.append(f"column: {col_name}")
                            snippets.append(f"column {col_name}: '{desc_str}'")

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
                    results.append(
                        {
                            "object_name": obj_name,
                            "object_type": obj_type,
                            "schema": schema_name,
                            "relevance_score": score,
                            "matched_fields": matched_fields,
                            "description": ann.description or "",
                            "matched_snippets": snippets[:5],
                            "business_rules": ann.business_rules,
                            "tags": ann.tags,
                        }
                    )
            except Exception:
                continue

    # 1b. If remote storage is configured, search annotations in memory via annotations_index
    if storage:
        target_schemas = [s.schema_name for s in schemas] if schemas else [config.schema_name or "DEFAULT"]
        for s_raw in target_schemas:
            s_name = (s_raw or "DEFAULT").upper()
            ann_index = _get_schema_annotations_index(s_name, config=config, storage=storage)
            for cat_folder, obj_dict in ann_index.get("objects", {}).items():
                obj_type = cat_folder.rstrip("s").upper()
                if obj_type in ("PACKAGE_BODY", "PACKAGE_BODYS"):
                    obj_type = "PACKAGE"
                if target_types and obj_type not in target_types and f"{obj_type}S" not in target_types:
                    continue

                for obj_name, ann_data in obj_dict.items():
                    item_key = f"{s_name}.{obj_name.upper()}"
                    if item_key in seen_keys:
                        continue

                    score = 0
                    matched_fields: list[str] = []
                    snippets: list[str] = []

                    norm_name = _normalize_text(obj_name)
                    if any(t in norm_name for t in tokens):
                        score += 50
                        matched_fields.append("name")

                    ann_desc = ann_data.get("description", "")
                    if fields_filter in ("all", "descriptions", "description") and ann_desc:
                        norm_desc = _normalize_text(ann_desc)
                        if any(t in norm_desc for t in tokens):
                            score += 45
                            matched_fields.append("description")
                            snippets.append(f"description: '{ann_desc}'")

                    ann_rules = ann_data.get("business_rules", [])
                    if fields_filter in ("all", "rules", "business_rules") and ann_rules:
                        for rule in ann_rules:
                            if any(t in _normalize_text(rule) for t in tokens):
                                score += 35
                                if "business_rules" not in matched_fields:
                                    matched_fields.append("business_rules")
                                snippets.append(f"rule: '{rule}'")

                    ann_cols = ann_data.get("columns", {})
                    if fields_filter in ("all", "columns", "cols") and ann_cols:
                        for col_name, col_desc in ann_cols.items():
                            if any(t in _normalize_text(f"{col_name} {col_desc}") for t in tokens):
                                score += 40
                                matched_fields.append(f"column: {col_name}")
                                snippets.append(f"column {col_name}: '{col_desc}'")

                    ann_tags = ann_data.get("tags", [])
                    if fields_filter in ("all", "tags") and ann_tags:
                        for tag in ann_tags:
                            if any(t in _normalize_text(tag) for t in tokens):
                                score += 25
                                matched_fields.append(f"tag: {tag}")
                                snippets.append(f"tag: '{tag}'")

                    if score > 0:
                        seen_keys.add(item_key)
                        results.append(
                            {
                                "object_name": obj_name,
                                "object_type": obj_type,
                                "schema": s_name,
                                "relevance_score": score,
                                "matched_fields": matched_fields,
                                "description": ann_desc,
                                "matched_snippets": snippets[:5],
                                "business_rules": ann_rules,
                                "tags": ann_tags,
                            }
                        )

        # Fallback for legacy storage when annotations_index is empty
        if hasattr(storage, "list_annotated_objects"):
            try:
                remote_objects = storage.list_annotated_objects()
                for s_name, cat_folder, obj_name in remote_objects:
                    target_s_name = (s_name or (schemas[0].schema_name if schemas else config.schema_name or "DEFAULT")).upper()
                    item_key = f"{target_s_name}.{obj_name.upper()}"
                    if item_key in seen_keys:
                        continue
                    obj_type = cat_folder.rstrip("s").upper()
                    if obj_type in ("PACKAGE_BODY", "PACKAGE_BODYS"):
                        obj_type = "PACKAGE"
                    if target_types and obj_type not in target_types and f"{obj_type}S" not in target_types:
                        continue

                    norm_name = _normalize_text(obj_name)
                    if any(t in norm_name for t in tokens):
                        try:
                            ann = storage.load_annotation(s_name, cat_folder, obj_name)
                            if not (ann.description or ann.columns or ann.business_rules or ann.tags):
                                continue
                            score = 50
                            matched_fields = ["name"]
                            snippets = []
                            if fields_filter in ("all", "descriptions", "description") and ann.description:
                                norm_desc = _normalize_text(ann.description)
                                if any(t in norm_desc for t in tokens):
                                    score += 45
                                    matched_fields.append("description")
                                    snippets.append(f"description: '{ann.description}'")
                            if fields_filter in ("all", "rules", "business_rules") and ann.business_rules:
                                for rule in ann.business_rules:
                                    if any(t in _normalize_text(rule) for t in tokens):
                                        score += 35
                                        if "business_rules" not in matched_fields:
                                            matched_fields.append("business_rules")
                                        snippets.append(f"rule: '{rule}'")
                            if score > 0:
                                seen_keys.add(item_key)
                                results.append(
                                    {
                                        "object_name": obj_name,
                                        "object_type": obj_type,
                                        "schema": s_name,
                                        "relevance_score": score,
                                        "matched_fields": matched_fields,
                                        "description": ann.description or "",
                                        "matched_snippets": snippets[:5],
                                        "business_rules": ann.business_rules,
                                        "tags": ann.tags,
                                    }
                                )
                        except Exception:
                            continue
            except Exception:
                pass

    # 2. Also search SchemaMetadata dictionary comments & columns
    for s in schemas:
        s_name = (s.schema_name or "DEFAULT").upper()
        all_objs = (
            [("TABLE", t.name, t.comment, [(c.name, c.comment) for c in t.columns]) for t in s.tables]
            + [("VIEW", v.name, v.comment, [(c.name, c.comment) for c in v.columns]) for v in s.views]
            + [("MVIEW", mv.name, mv.comment, [(c.name, c.comment) for c in mv.columns]) for mv in s.mviews]
            + [
                (
                    "PACKAGE" if co.object_type.upper() == "PACKAGE" else co.object_type.upper(),
                    co.name,
                    co.comment,
                    [(sp.name, sp.comment) for sp in co.subprograms],
                )
                for co in s.code_objects
            ]
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
                    snippets.append(f"column {sname}: '{scomment}'" if scomment else f"column {sname}")

            if score > 0:
                seen_keys.add(item_key)
                results.append(
                    {
                        "object_name": oname.upper(),
                        "object_type": otype,
                        "schema": s_name,
                        "relevance_score": score,
                        "matched_fields": matched_fields,
                        "description": ocomment or "",
                        "matched_snippets": snippets[:5],
                        "business_rules": [],
                        "tags": [],
                    }
                )

    # Sort results by relevance_score descending
    results.sort(key=lambda x: x["relevance_score"], reverse=True)
    return results[:15]


def lookup_business_term(
    config: LeaiConfig,
    query: str,
    tag: str | None = None,
) -> dict[str, Any]:
    from leai.glossary import load_glossary, search_glossary

    glossary = load_glossary(config.annotationsPath)
    if not glossary.terms:
        storage = _resolve_storage_for_tools(config)
        if storage and hasattr(storage, "load_glossary"):
            try:
                remote_glossary = storage.load_glossary()
                if remote_glossary.terms:
                    glossary = remote_glossary
            except Exception:
                pass

    matches = search_glossary(glossary, query)

    if tag:
        tag_norm = tag.strip().lower()
        matches = [(t, s) for t, s in matches if any(tag_norm == tg.lower() for tg in t.tags)]

    results = []
    for term, score in matches[:10]:
        results.append(
            {
                "term": term.term,
                "definition": term.definition,
                "primary_table": term.primary_table,
                "canonical_filter": term.canonical_filter,
                "related_tables": term.related_tables,
                "tags": term.tags,
                "examples": term.examples,
                "relevance_score": score,
            }
        )

    return {
        "query": query,
        "total_matches": len(results),
        "results": results,
    }


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
    storage = _resolve_storage_for_tools(config)

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
        ann_index = _get_schema_annotations_index(s_name, config=config, storage=storage)
        enriched_tables = ann_index.get("objects", {}).get("tables", {})
        enriched_views = ann_index.get("objects", {}).get("views", {})

        # Tables
        if not target_types or "TABLE" in target_types or "TABLES" in target_types:
            for t in s.tables:
                t_up = t.name.upper()
                ann_info = enriched_tables.get(t_up)
                ann_desc = ann_info.get("description", "") if ann_info else ""
                if not ann_desc and storage and not enriched_tables:
                    try:
                        ann = storage.load_annotation(s_name, "tables", t.name)
                        ann_desc = ann.description or ""
                    except Exception:
                        pass
                if not ann_desc and config and config.annotationsPath and not storage:
                    ann_dir = config.annotationsPath / s_name if is_multi else config.annotationsPath
                    ann_file = ann_dir / "tables" / f"{t.name}.yml"
                    if ann_file.exists():
                        ann = load_annotation(ann_file)
                        ann_desc = ann.description or ""

                cols_text = " ".join(f"{c.name} {c.comment or ''}" for c in t.columns)
                haystack = f"{t.name} {t.comment or ''} {ann_desc} {cols_text}"
                if _matches_text(haystack):
                    matched_cols = [c.name for c in t.columns if _matches_text(f"{c.name} {c.comment or ''}")]
                    results.append(
                        {
                            "name": t.name,
                            "type": "TABLE",
                            "schema": s_name,
                            "comment": t.comment or (ann_desc if ann_desc else None),
                            "column_count": len(t.columns),
                            "matched_columns": matched_cols[:5],
                        }
                    )

        # Views
        if not target_types or "VIEW" in target_types or "VIEWS" in target_types:
            for v in s.views:
                v_up = v.name.upper()
                ann_info = enriched_views.get(v_up)
                ann_desc = ann_info.get("description", "") if ann_info else ""
                if not ann_desc and config and config.annotationsPath and not storage:
                    ann_dir = config.annotationsPath / s_name if is_multi else config.annotationsPath
                    ann_file = ann_dir / "views" / f"{v.name}.yml"
                    if ann_file.exists():
                        ann = load_annotation(ann_file)
                        ann_desc = ann.description or ""

                cols_text = " ".join(f"{c.name} {c.comment or ''}" for c in v.columns)
                haystack = f"{v.name} {v.comment or ''} {ann_desc} {cols_text}"
                if _matches_text(haystack):
                    matched_cols = [c.name for c in v.columns if _matches_text(f"{c.name} {c.comment or ''}")]
                    results.append(
                        {
                            "name": v.name,
                            "type": "VIEW",
                            "schema": s_name,
                            "comment": v.comment or (ann_desc if ann_desc else None),
                            "matched_columns": matched_cols[:5],
                        }
                    )

        # Materialized Views
        if not target_types or any(t in target_types for t in ("MVIEW", "MVIEWS", "MATERIALIZED VIEW", "MATERIALIZED VIEWS")):
            for mv in s.mviews:
                cols_text = " ".join(f"{c.name} {c.comment or ''}" for c in mv.columns)
                haystack = f"{mv.name} {mv.comment or ''} {cols_text}"
                if _matches_text(haystack):
                    results.append(
                        {
                            "name": mv.name,
                            "type": "MATERIALIZED VIEW",
                            "schema": s_name,
                            "comment": mv.comment,
                        }
                    )

        # Code Objects (Packages, Procedures, Functions)
        for co in s.code_objects:
            c_type = co.object_type.upper()
            if not target_types or c_type in target_types or f"{c_type}S" in target_types:
                if _matches_text(f"{co.name} {co.comment or ''}"):
                    results.append(
                        {
                            "name": co.name,
                            "type": c_type,
                            "schema": s_name,
                            "subprograms_count": len(co.subprograms),
                            "comment": co.comment,
                        }
                    )

            # Subprograms inside packages
            for sp in co.subprograms:
                sp_full = f"{co.name}.{sp.name}"
                if not target_types or any(
                    t in target_types for t in (sp.subprogram_type.upper(), f"{sp.subprogram_type.upper()}S", "SUBPROGRAM", "SUBPROGRAMS")
                ):
                    if _matches_text(f"{sp.name} {sp_full} {sp.comment or ''}"):
                        results.append(
                            {
                                "name": sp_full,
                                "type": f"{co.object_type}.{sp.subprogram_type}",
                                "schema": s_name,
                                "package": co.name,
                                "subprogram": sp.name,
                                "comment": sp.comment,
                            }
                        )

        # Triggers
        if not target_types or "TRIGGER" in target_types or "TRIGGERS" in target_types:
            for trg in s.triggers:
                if _matches_text(f"{trg.name} {trg.table_name or ''}"):
                    results.append(
                        {
                            "name": trg.name,
                            "type": "TRIGGER",
                            "schema": s_name,
                            "table_name": trg.table_name,
                            "event": f"{trg.trigger_type} {trg.triggering_event}",
                        }
                    )

        # Synonyms
        if not target_types or "SYNONYM" in target_types or "SYNONYMS" in target_types:
            for syn in s.synonyms:
                if _matches_text(f"{syn.name} {syn.table_name or ''}"):
                    target_info = resolve_synonym(schemas, syn.name)
                    target_desc = f"{syn.table_owner or ''}.{syn.table_name or ''}"
                    if target_info and target_info.get("target_type") != "UNKNOWN":
                        target_desc += f" ({target_info['target_type']})"
                    results.append(
                        {
                            "name": syn.name,
                            "type": "SYNONYM",
                            "schema": s_name,
                            "points_to": target_desc,
                        }
                    )

    # Return top 25 matches sorted by closest name match
    results.sort(
        key=lambda x: (
            0 if _normalize_text(x["name"]) == q_norm else (1 if _normalize_text(x["name"]).startswith(q_norm) else 2),
            x["name"],
        )
    )
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
    target_table = table_name.strip().lstrip("@").upper() if table_name else None
    if not target_table and q_norm:
        cand = q_norm.upper()
        for s in schemas:
            s_up = (s.schema_name or "").upper()
            if any(t.name.upper() == cand for t in s.tables) or any(v.name.upper() == cand for v in s.views):
                target_table = cand
                break
            if "." in cand:
                parts = cand.split(".", 1)
                if parts[0] == s_up and (
                    any(t.name.upper() == parts[1] for t in s.tables) or any(v.name.upper() == parts[1] for v in s.views)
                ):
                    target_table = cand
                    break

    storage = _resolve_storage_for_tools(config)

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
        ann_index = _get_schema_annotations_index(s_name, config=config, storage=storage)
        enriched_tables = ann_index.get("objects", {}).get("tables", {})
        enriched_views = ann_index.get("objects", {}).get("views", {})

        # 1. Tables
        if not target_types or any(t in target_types for t in ("TABLE", "TABLES")):
            for t in s.tables:
                t_up = t.name.upper()
                if target_table and t_up != target_table and f"{s_name}.{t_up}" != target_table:
                    continue

                is_exact_table_query = target_table is not None and q_norm.upper() in (t_up, f"{s_name}.{t_up}")
                ann_info = enriched_tables.get(t_up)
                ann_cols = ann_info.get("columns", {}) if ann_info else {}
                if not ann_cols and storage and not enriched_tables:
                    try:
                        ann = storage.load_annotation(s_name, "tables", t.name)
                        if ann and ann.columns:
                            ann_cols = ann.columns
                    except Exception:
                        pass
                pk_cols = set(t.primary_keys) if t.primary_keys else set()

                for c in t.columns:
                    comment = ann_cols.get(c.name) or c.comment or ""
                    matched, score = _score_and_match(f"{comment} {t.comment or ''}", c.name)
                    if is_exact_table_query:
                        matched = True
                        score = max(score, 50)
                    if matched:
                        matches.append(
                            {
                                "schema": s_name,
                                "table_name": t.name,
                                "qualified_name": f"{s_name}.{t.name}",
                                "object_type": "TABLE",
                                "column_name": c.name,
                                "data_type": c.data_type,
                                "nullable": c.nullable,
                                "is_pk": c.name in pk_cols,
                                "comment": comment or "(No comment)",
                                "table_comment": t.comment or "",
                                "_score": score,
                            }
                        )

        # 2. Views
        if not target_types or any(t in target_types for t in ("VIEW", "VIEWS")):
            for v in s.views:
                v_up = v.name.upper()
                if target_table and v_up != target_table and f"{s_name}.{v_up}" != target_table:
                    continue

                is_exact_table_query = target_table is not None and q_norm.upper() in (v_up, f"{s_name}.{v_up}")
                ann_info = enriched_views.get(v_up)
                ann_cols = ann_info.get("columns", {}) if ann_info else {}

                for c in v.columns:
                    comment = ann_cols.get(c.name) or c.comment or ""
                    matched, score = _score_and_match(f"{comment} {v.comment or ''}", c.name)
                    if is_exact_table_query:
                        matched = True
                        score = max(score, 50)
                    if matched:
                        matches.append(
                            {
                                "schema": s_name,
                                "table_name": v.name,
                                "qualified_name": f"{s_name}.{v.name}",
                                "object_type": "VIEW",
                                "column_name": c.name,
                                "data_type": c.data_type,
                                "nullable": c.nullable,
                                "is_pk": False,
                                "comment": comment or "(No comment)",
                                "table_comment": v.comment or "",
                                "_score": score,
                            }
                        )

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
                        matches.append(
                            {
                                "schema": s_name,
                                "table_name": mv.name,
                                "qualified_name": f"{s_name}.{mv.name}",
                                "object_type": "MATERIALIZED VIEW",
                                "column_name": c.name,
                                "data_type": c.data_type,
                                "nullable": c.nullable,
                                "is_pk": False,
                                "comment": comment or "(No comment)",
                                "table_comment": mv.comment or "",
                                "_score": score,
                            }
                        )

    matches.sort(key=lambda x: (-x["_score"], x["table_name"], x["column_name"]))
    for m in matches:
        m.pop("_score", None)

    return matches[:max_results]


def get_table_schema(
    schemas: list[SchemaMetadata],
    config: LeaiConfig,
    table_name: str,
) -> dict[str, Any]:
    raw_name = table_name.strip().lstrip("@").upper()
    target_schema: str | None = None
    target_name = raw_name
    storage = _resolve_storage_for_tools(config)
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
                ann_index = _get_schema_annotations_index(s_name, config=config, storage=storage)
                ann_data = ann_index.get("objects", {}).get("tables", {}).get(t.name.upper())
                if ann_data:
                    ann = ObjectAnnotation.model_validate(ann_data)
                elif storage:
                    try:
                        ann = storage.load_annotation(s_name, "tables", t.name)
                    except Exception:
                        ann = None
                elif config and config.annotationsPath and not storage:
                    is_multi = len(schemas) > 1 or config.is_all_schemas
                    ann_dir = config.annotationsPath / s_name if is_multi else config.annotationsPath
                    ann_file = ann_dir / "tables" / f"{t.name}.yml"
                    ann = load_annotation(ann_file) if ann_file.exists() else None
                else:
                    ann = None

                pk_cols = set(t.primary_keys) if t.primary_keys else set()

                cols_info = []
                for c in t.columns:
                    col_doc = (ann and ann.columns.get(c.name)) or c.comment or ""
                    cols_info.append(
                        {
                            "name": c.name,
                            "type": c.data_type,
                            "nullable": c.nullable,
                            "is_pk": c.name in pk_cols,
                            "description": col_doc,
                        }
                    )

                fks_info = []
                for fk in t.foreign_keys:
                    fks_info.append(
                        {
                            "name": fk.name,
                            "column": fk.column,
                            "references_table": fk.referenced_table,
                            "references_column": fk.referenced_column,
                        }
                    )

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
                ann_index = _get_schema_annotations_index(s_name, config=config, storage=storage)
                ann_data = ann_index.get("objects", {}).get("views", {}).get(v.name.upper())
                if ann_data:
                    ann = ObjectAnnotation.model_validate(ann_data)
                elif storage:
                    try:
                        ann = storage.load_annotation(s_name, "views", v.name)
                    except Exception:
                        ann = None
                elif config and config.annotationsPath and not storage:
                    is_multi = len(schemas) > 1 or config.is_all_schemas
                    ann_dir = config.annotationsPath / s_name if is_multi else config.annotationsPath
                    ann_file = ann_dir / "views" / f"{v.name}.yml"
                    ann = load_annotation(ann_file) if ann_file.exists() else None
                else:
                    ann = None

                cols_info = []
                for c in v.columns:
                    col_doc = (ann and ann.columns.get(c.name)) or c.comment or ""
                    cols_info.append(
                        {
                            "name": c.name,
                            "type": c.data_type,
                            "nullable": c.nullable,
                            "is_pk": False,
                            "description": col_doc,
                        }
                    )

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
                is_multi = len(schemas) > 1 or config.is_all_schemas
                ann_dir = config.annotationsPath / s_name if is_multi else config.annotationsPath
                ann_file = ann_dir / "mviews" / f"{mv.name}.yml"
                ann = (
                    load_annotation(
                        ann_file,
                        storage=storage,
                        schema_name=s_name,
                        obj_folder="mviews",
                        obj_name=mv.name,
                    )
                    if (ann_file.exists() or storage)
                    else None
                )

                cols_info = []
                for c in mv.columns:
                    col_doc = (ann and ann.columns.get(c.name)) or c.comment or ""
                    cols_info.append(
                        {
                            "name": c.name,
                            "type": c.data_type,
                            "nullable": c.nullable,
                            "is_pk": False,
                            "description": col_doc,
                        }
                    )

                return {
                    "table_name": mv.name,
                    "type": "MATERIALIZED VIEW",
                    "schema": s_name,
                    "comment": mv.comment,
                    "business_description": ann.description if ann else None,
                    "business_rules": ann.business_rules if ann else [],
                    "tags": ann.tags if ann else [],
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
                                "source_code": minify_plsql_source(code_src) if code_src else "",
                            }

                    if co.source:
                        code_src = extract_subprogram_block(co.source, sp_name)
                        if code_src:
                            return {
                                "package_name": co.name,
                                "subprogram_name": sp_name,
                                "subprogram_type": "SUBPROGRAM",
                                "schema": s_name,
                                "source_code": minify_plsql_source(code_src),
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
                    "source_code": minify_plsql_source(co.source)
                    if co.source
                    else f"-- Objeto {co.object_type} {co.name} registrado sem fonte inline.",
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
                        "source_code": minify_plsql_source(co.source)
                        if co.source
                        else f"-- Objeto {co.object_type} {co.name} registrado sem fonte inline.",
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
                            "source_code": minify_plsql_source(code_src) if code_src else "",
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
        links_summary.append(
            {
                "source": dep.source_name,
                "source_type": dep.source_type,
                "target": dep.target_name,
                "target_type": dep.target_type,
                "relation": dep.relation_type,
                "details": dep.details,
                "depth": dep.depth,
            }
        )

    obj_name = target_name
    parents = [
        d.target_name
        for d in trace_res.dependencies
        if d.target_name != obj_name
        and d.relation_type in ("FK_REFERENCES", "DEPENDS_ON", "READS/SELECTS", "EXECUTES/CALLS", "SYNONYM_FOR")
    ]
    children = [d.source_name for d in trace_res.dependencies if d.source_name != obj_name and d.relation_type in ("FK_REFERENCED_BY",)]
    consumers = [
        d.source_name
        for d in trace_res.dependencies
        if d.source_name != obj_name and d.relation_type in ("PLSQL_DEPENDENCY", "TRIGGER_ON", "REFERENCED_BY", "CALLS_SUBPROGRAM")
    ]

    from leai.docs import _calculate_risk_level

    risk_level = _calculate_risk_level(len(trace_res.dependencies))

    result_payload: dict[str, Any] = {
        "focal_object": trace_res.focal_name or obj_name,
        "focal_type": trace_res.focal_type if trace_res.focal_type != "UNKNOWN" else ("SYNONYM" if syn_info else "UNKNOWN"),
        "change_risk_level": risk_level,
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
            f"The object '{obj_name}' is a SYNONYM pointing to '{syn_info['target_owner']}.{syn_info['target_name']}' "
            f"(type: {syn_info['target_type']}). To analyze its logic, use 'get_subprogram_source' to read the code or 'get_table_schema' for columns."
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
                    matches.append(
                        {
                            "object_name": co.name,
                            "object_type": co.object_type,
                            "schema": s_name,
                            "line_number": idx,
                            "matching_line": line.strip(),
                            "context_snippet": snippet,
                        }
                    )
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
                    matches.append(
                        {
                            "object_name": trg.name,
                            "object_type": "TRIGGER",
                            "schema": s_name,
                            "line_number": idx,
                            "matching_line": line.strip(),
                            "context_snippet": snippet,
                        }
                    )
                    if len(matches) >= max_results:
                        return matches

    return matches


def validate_oracle_sql(
    schemas: list[SchemaMetadata],
    sql: str,
    config: LeaiConfig | None = None,
) -> dict[str, Any]:
    """Validates SQL statement for Oracle Database dialect compatibility and schema correctness."""
    if not sql or not sql.strip():
        return {"valid": False, "error": "Empty SQL statement provided."}

    raw_sql = sql.strip()
    cleaned_sql = raw_sql
    dialect_issues: list[dict[str, str]] = []
    schema_warnings: list[str] = []

    # 1. Check for LIMIT / OFFSET (Postgres / MySQL)
    limit_match = re.search(r"\bLIMIT\s+(\d+)(?:\s+OFFSET\s+(\d+))?\b", raw_sql, re.IGNORECASE)
    offset_limit_match = re.search(r"\bOFFSET\s+(\d+)\s+LIMIT\s+(\d+)\b", raw_sql, re.IGNORECASE)
    if limit_match or offset_limit_match:
        m = limit_match or offset_limit_match
        snippet = m.group(0)
        dialect_issues.append(
            {
                "rule": "LIMIT_OFFSET_CLAUSE",
                "severity": "ERROR",
                "snippet": snippet,
                "message": "PostgreSQL/MySQL 'LIMIT / OFFSET' clause is not supported in Oracle SQL.",
                "suggested_fix": (
                    "Use 'FETCH FIRST n ROWS ONLY' (or 'OFFSET m ROWS FETCH NEXT n ROWS ONLY' for Oracle 12c+), "
                    "or 'WHERE ROWNUM <= n' for older versions."
                ),
            }
        )
        if limit_match:
            n_rows = limit_match.group(1)
            offset_val = limit_match.group(2)
            if offset_val:
                rep = f"OFFSET {offset_val} ROWS FETCH NEXT {n_rows} ROWS ONLY"
            else:
                rep = f"FETCH FIRST {n_rows} ROWS ONLY"
            cleaned_sql = re.sub(r"\bLIMIT\s+\d+(?:\s+OFFSET\s+\d+)?\b", rep, cleaned_sql, flags=re.IGNORECASE)
        elif offset_limit_match:
            offset_val = offset_limit_match.group(1)
            n_rows = offset_limit_match.group(2)
            rep = f"OFFSET {offset_val} ROWS FETCH NEXT {n_rows} ROWS ONLY"
            cleaned_sql = re.sub(r"\bOFFSET\s+\d+\s+LIMIT\s+\d+\b", rep, cleaned_sql, flags=re.IGNORECASE)

    # 2. Check for BOOLEAN column type or literal
    boolean_matches = re.finditer(r"\bBOOLEAN\b", raw_sql, re.IGNORECASE)
    for bm in boolean_matches:
        snippet = bm.group(0)
        dialect_issues.append(
            {
                "rule": "BOOLEAN_DATA_TYPE",
                "severity": "ERROR",
                "snippet": snippet,
                "message": "Oracle SQL table columns do not support the BOOLEAN data type.",
                "suggested_fix": "Use 'NUMBER(1)' with 'CHECK (col IN (0, 1))' or 'CHAR(1)' with 'CHECK (col IN ('S', 'N'))'.",
            }
        )
        cleaned_sql = re.sub(r"\bBOOLEAN\b", "NUMBER(1) CHECK (/* col */ IN (0, 1))", cleaned_sql, flags=re.IGNORECASE)

    # 3. Check for ILIKE (PostgreSQL)
    ilike_matches = re.finditer(r"(\b\w+(?:\.\w+)?\b)\s+ILIKE\s+('[^']*'|\b\w+\b)", raw_sql, re.IGNORECASE)
    for im in ilike_matches:
        col_name = im.group(1)
        val = im.group(2)
        dialect_issues.append(
            {
                "rule": "ILIKE_OPERATOR",
                "severity": "ERROR",
                "snippet": im.group(0),
                "message": "'ILIKE' is PostgreSQL-specific syntax.",
                "suggested_fix": f"Use 'REGEXP_LIKE({col_name}, {val}, 'i')' or 'UPPER({col_name}) LIKE UPPER({val})'.",
            }
        )
        cleaned_sql = cleaned_sql.replace(im.group(0), f"REGEXP_LIKE({col_name}, {val}, 'i')")

    # 4. Check for IFNULL / ISNULL (MySQL / SQL Server)
    ifnull_matches = re.finditer(r"\b(IFNULL|ISNULL)\s*\(([^,]+),\s*([^)]+)\)", raw_sql, re.IGNORECASE)
    for inm in ifnull_matches:
        fn_name = inm.group(1).upper()
        expr1 = inm.group(2).strip()
        expr2 = inm.group(3).strip()
        dialect_issues.append(
            {
                "rule": "NON_ORACLE_NULL_FUNCTION",
                "severity": "ERROR",
                "snippet": inm.group(0),
                "message": f"Function '{fn_name}' is not native to Oracle SQL.",
                "suggested_fix": f"Use 'NVL({expr1}, {expr2})' or standard 'COALESCE({expr1}, {expr2})'.",
            }
        )
        cleaned_sql = cleaned_sql.replace(inm.group(0), f"NVL({expr1}, {expr2})")

    # 5. Check for DATEADD / DATEDIFF / DATE_ADD / DATE_SUB
    date_fn_matches = re.finditer(r"\b(DATEADD|DATEDIFF|DATE_ADD|DATE_SUB)\s*\(([^)]+)\)", raw_sql, re.IGNORECASE)
    for dfm in date_fn_matches:
        fn_name = dfm.group(1).upper()
        dialect_issues.append(
            {
                "rule": "NON_ORACLE_DATE_MATH",
                "severity": "ERROR",
                "snippet": dfm.group(0),
                "message": f"Date function '{fn_name}' is SQL Server/MySQL specific.",
                "suggested_fix": "In Oracle, add days directly ('dt + n'), use 'ADD_MONTHS(dt, n)', or 'dt + INTERVAL 'n' DAY'.",
            }
        )

    # 6. Check for GETDATE() / NOW() / SYSDATE()
    getdate_matches = re.finditer(r"\b(GETDATE|NOW)\s*\(\s*\)", raw_sql, re.IGNORECASE)
    for gdm in getdate_matches:
        fn_name = gdm.group(1).upper()
        dialect_issues.append(
            {
                "rule": "NON_ORACLE_CURRENT_DATE",
                "severity": "ERROR",
                "snippet": gdm.group(0),
                "message": f"'{fn_name}()' is not native Oracle syntax.",
                "suggested_fix": "Use 'SYSDATE' (without parentheses) or 'CURRENT_TIMESTAMP'.",
            }
        )
        cleaned_sql = re.sub(r"\b(GETDATE|NOW)\s*\(\s*\)", "SYSDATE", cleaned_sql, flags=re.IGNORECASE)

    sysdate_fn_matches = re.finditer(r"\bSYSDATE\s*\(\s*\)", raw_sql, re.IGNORECASE)
    for sfm in sysdate_fn_matches:
        dialect_issues.append(
            {
                "rule": "SYSDATE_WITH_PARENTHESES",
                "severity": "WARNING",
                "snippet": sfm.group(0),
                "message": "In Oracle, 'SYSDATE' is a pseudo-column keyword and must NOT have parentheses.",
                "suggested_fix": "Use 'SYSDATE'.",
            }
        )
        cleaned_sql = re.sub(r"\bSYSDATE\s*\(\s*\)", "SYSDATE", cleaned_sql, flags=re.IGNORECASE)

    # 7. Check for AUTO_INCREMENT / SERIAL / BIGSERIAL
    auto_inc_matches = re.finditer(r"\b(AUTO_INCREMENT|SERIAL|BIGSERIAL)\b", raw_sql, re.IGNORECASE)
    for aim in auto_inc_matches:
        kw = aim.group(0).upper()
        dialect_issues.append(
            {
                "rule": "AUTO_INCREMENT_KEYWORD",
                "severity": "ERROR",
                "snippet": aim.group(0),
                "message": f"'{kw}' is MySQL/PostgreSQL syntax.",
                "suggested_fix": "Use 'NUMBER GENERATED ALWAYS AS IDENTITY' (Oracle 12c+) or a SEQUENCE + TRIGGER.",
            }
        )
        cleaned_sql = re.sub(
            r"\b(AUTO_INCREMENT|SERIAL|BIGSERIAL)\b", "NUMBER GENERATED ALWAYS AS IDENTITY", cleaned_sql, flags=re.IGNORECASE
        )

    # 8. Check for VARCHAR(MAX) / TEXT
    text_matches = re.finditer(r"\bVARCHAR\s*\(\s*MAX\s*\)|\bTEXT\b", raw_sql, re.IGNORECASE)
    for tm in text_matches:
        kw = tm.group(0)
        dialect_issues.append(
            {
                "rule": "NON_ORACLE_TEXT_TYPE",
                "severity": "ERROR",
                "snippet": kw,
                "message": f"Data type '{kw}' is not native to Oracle SQL.",
                "suggested_fix": "Use 'VARCHAR2(4000)' for strings up to 4000 bytes or 'CLOB' for large documents.",
            }
        )
        cleaned_sql = re.sub(r"\bVARCHAR\s*\(\s*MAX\s*\)|\bTEXT\b", "VARCHAR2(4000)", cleaned_sql, flags=re.IGNORECASE)

    # 9. Check for string concatenation with '+'
    plus_concat = re.finditer(r"('[^']*')\s*\+\s*('[^']*'|\b\w+\b)|(\b\w+\b)\s*\+\s*('[^']*')", raw_sql)
    for pc in plus_concat:
        snippet = pc.group(0)
        dialect_issues.append(
            {
                "rule": "PLUS_STRING_CONCATENATION",
                "severity": "ERROR",
                "snippet": snippet,
                "message": "'+' operator is arithmetic addition in Oracle; using it with strings causes ORA-01722 (invalid number).",
                "suggested_fix": "Use '||' for string concatenation (e.g., col1 || ' ' || col2).",
            }
        )

    # 10. Check for backtick identifiers `table` / `col`
    backtick_matches = re.finditer(r"`([^`]+)`", raw_sql)
    for btm in backtick_matches:
        snippet = btm.group(0)
        ident = btm.group(1)
        dialect_issues.append(
            {
                "rule": "BACKTICK_QUOTED_IDENTIFIER",
                "severity": "ERROR",
                "snippet": snippet,
                "message": "Backticks '`' for quoting identifiers are MySQL-specific.",
                "suggested_fix": f"Use standard Oracle double quotes '\"{ident.upper()}\"' or unquoted uppercase '{ident.upper()}'.",
            }
        )
        cleaned_sql = cleaned_sql.replace(snippet, f'"{ident.upper()}"')

    # 11. Check for SELECT TOP n
    top_matches = re.finditer(r"\bSELECT\s+TOP\s+(\d+)\b", raw_sql, re.IGNORECASE)
    for tm in top_matches:
        n_rows = tm.group(1)
        dialect_issues.append(
            {
                "rule": "SELECT_TOP_CLAUSE",
                "severity": "ERROR",
                "snippet": tm.group(0),
                "message": "'SELECT TOP' is SQL Server syntax.",
                "suggested_fix": f"Remove 'TOP {n_rows}' and append 'FETCH FIRST {n_rows} ROWS ONLY' at the end of the query or use 'WHERE ROWNUM <= {n_rows}'.",
            }
        )
        cleaned_sql = re.sub(r"\bSELECT\s+TOP\s+\d+\b", "SELECT", cleaned_sql, flags=re.IGNORECASE)
        if not re.search(r"\bFETCH\s+FIRST\b", cleaned_sql, re.IGNORECASE):
            cleaned_sql = f"{cleaned_sql.rstrip(';')} FETCH FIRST {n_rows} ROWS ONLY;"

    # 12. Cross-reference tables and columns with schema metadata
    if schemas:
        known_tables: dict[str, TableMeta] = {}
        for s in schemas:
            for t in s.tables:
                known_tables[t.name.upper()] = t
            for v in s.views:
                known_tables[v.name.upper()] = TableMeta(name=v.name, columns=v.columns)

        found_tables = re.findall(r"\b(?:FROM|JOIN|INTO|UPDATE)\s+([a-zA-Z0-9_$#\.]+)", raw_sql, re.IGNORECASE)
        for tbl_ref in found_tables:
            tbl_clean = tbl_ref.strip().split(".")[-1].upper()
            if tbl_clean.startswith("("):
                continue
            if tbl_clean in known_tables:
                meta = known_tables[tbl_clean]
                table_cols = {c.name.upper() for c in meta.columns}
                col_refs = re.findall(rf"\b{tbl_clean}\.([a-zA-Z0-9_$#]+)\b", raw_sql, re.IGNORECASE)
                for col in col_refs:
                    col_u = col.upper()
                    if col_u != "*" and col_u not in table_cols:
                        schema_warnings.append(f"Column '{col_u}' not found in schema definition of table '{tbl_clean}'.")

    is_valid = len(dialect_issues) == 0

    return {
        "valid": is_valid,
        "total_issues": len(dialect_issues),
        "dialect_issues": dialect_issues,
        "schema_warnings": schema_warnings,
        "suggested_oracle_sql": cleaned_sql if not is_valid else raw_sql,
        "summary": "Valid Oracle SQL syntax." if is_valid else f"Identified {len(dialect_issues)} non-Oracle dialect issue(s).",
    }


def explain_and_tune_sql(
    schemas: list[SchemaMetadata],
    query: str,
    target_tables: list[str] | None = None,
    config: LeaiConfig | None = None,
    client: Any = None,
) -> dict[str, Any]:
    """Analyzes an Oracle SQL query for performance anti-patterns, non-sargable filters, FTS risks, and suggests optimized rewrites."""
    if not query or not query.strip():
        return {"error": "Empty query provided for analysis."}

    raw_query = query.strip()
    anti_patterns_found: list[dict[str, Any]] = []
    index_recommendations: list[dict[str, Any]] = []
    fts_warnings: list[dict[str, Any]] = []
    rewritten_query = raw_query

    # 1. Non-sargable TRUNC / TO_CHAR / UPPER / NVL on columns in WHERE / JOIN
    trunc_matches = re.finditer(r"\bTRUNC\s*\(\s*([a-zA-Z0-9_$#\.]+)\s*\)\s*(=|>=|<=|>|<|BETWEEN)", raw_query, re.IGNORECASE)
    for tm in trunc_matches:
        col = tm.group(1)
        anti_patterns_found.append(
            {
                "type": "NON_SARGABLE_PREDICATE",
                "snippet": tm.group(0),
                "target": col,
                "impact": "HIGH - Function TRUNC() hides the column from standard B-Tree index range scans and forces Full Table Scan (FTS).",
                "recommendation": f"Rewrite as a date range condition (e.g. `{col} >= :dt_start AND {col} < :dt_end`) or create a Function-Based Index `CREATE INDEX idx_fbi_{col.replace('.', '_')} ON tab (TRUNC({col}))`.",
            }
        )

    to_char_matches = re.finditer(r"\bTO_CHAR\s*\(\s*([a-zA-Z0-9_$#\.]+)[^)]*\)\s*(=|LIKE)", raw_query, re.IGNORECASE)
    for tcm in to_char_matches:
        col = tcm.group(1)
        anti_patterns_found.append(
            {
                "type": "NON_SARGABLE_PREDICATE",
                "snippet": tcm.group(0),
                "target": col,
                "impact": "HIGH - TO_CHAR() prevents optimizer index range scans and performs implicit string conversions per row.",
                "recommendation": f"Filter against native date/number values instead of converting `{col}` to string, or create an FBI on `TO_CHAR({col})`.",
            }
        )

    upper_lower_matches = re.finditer(r"\b(UPPER|LOWER)\s*\(\s*([a-zA-Z0-9_$#\.]+)\s*\)\s*(=|LIKE)", raw_query, re.IGNORECASE)
    for ulm in upper_lower_matches:
        fn = ulm.group(1).upper()
        col = ulm.group(2)
        anti_patterns_found.append(
            {
                "type": "FUNCTION_ON_INDEXED_COLUMN",
                "snippet": ulm.group(0),
                "target": col,
                "impact": f"MEDIUM - {fn}() prevents standard index usage unless a Function-Based Index exists.",
                "recommendation": f"Ensure data is stored standardized in uppercase, or create a Function-Based Index `CREATE INDEX idx_{fn.lower()}_{col.replace('.', '_')} ON tab ({fn}({col}))`.",
            }
        )

    nvl_matches = re.finditer(
        r"\b(NVL|COALESCE)\s*\(\s*([a-zA-Z0-9_$#\.]+)\s*,[^)]+\)\s*(?:=|!=|<>|>=|<=|>|<|\bIS\b|\bBETWEEN\b|\bLIKE\b)",
        raw_query,
        re.IGNORECASE,
    )
    for nm in nvl_matches:
        fn = nm.group(1).upper()
        col = nm.group(2)
        anti_patterns_found.append(
            {
                "type": "NULL_WRAPPER_PREDICATE",
                "snippet": nm.group(0),
                "target": col,
                "impact": f"MEDIUM - {fn}() prevents optimizer from utilizing index nullability statistics.",
                "recommendation": f"Rewrite condition using explicit boolean logic: `({col} = :val OR {col} IS NULL)`.",
            }
        )

    # 2. Leading wildcard LIKE '%value'
    wildcard_matches = re.finditer(r"([a-zA-Z0-9_$#\.]+)\s+LIKE\s+'%[^']+'", raw_query, re.IGNORECASE)
    for wm in wildcard_matches:
        col = wm.group(1)
        anti_patterns_found.append(
            {
                "type": "LEADING_WILDCARD_LIKE",
                "snippet": wm.group(0),
                "target": col,
                "impact": "HIGH - Leading wildcard '%...' cannot traverse a B-Tree index and requires Full Table Scan.",
                "recommendation": "Use trailing wildcard only (`LIKE 'PREFIX%'`), Oracle Text (`CONTAINS`), or a Reverse Key Index for suffix matching.",
            }
        )

    # 3. NOT IN subqueries with potentially nullable columns
    not_in_matches = re.finditer(
        r"([a-zA-Z0-9_$#\.]+)\s+NOT\s+IN\s*\(\s*SELECT\s+([a-zA-Z0-9_$#\.]+)\s+FROM\s+([a-zA-Z0-9_$#\.]+)([^)]*)\)",
        raw_query,
        re.IGNORECASE,
    )
    for nim in not_in_matches:
        outer_col = nim.group(1)
        sub_col = nim.group(2)
        sub_tab = nim.group(3)
        extra = nim.group(4).strip()
        anti_patterns_found.append(
            {
                "type": "NOT_IN_SUBQUERY_NULL_RISK",
                "snippet": nim.group(0),
                "target": f"{outer_col} NOT IN (SELECT {sub_col} FROM {sub_tab})",
                "impact": "CRITICAL - If the subquery returns even one NULL row, NOT IN evaluates to UNKNOWN and returns 0 rows. Additionally, optimizer cannot easily transform this into a Hash Anti-Join.",
                "recommendation": f"Rewrite using `NOT EXISTS (SELECT 1 FROM {sub_tab} WHERE {sub_tab}.{sub_col.split('.')[-1]} = {outer_col})` or `LEFT JOIN ... WHERE {sub_tab}.{sub_col.split('.')[-1]} IS NULL`.",
            }
        )
        where_join = f"WHERE {sub_tab}.{sub_col.split('.')[-1]} = {outer_col}"
        if extra and extra.upper().startswith("WHERE"):
            where_join += f" AND ({extra[5:].strip()})"
        elif extra:
            where_join += f" {extra}"
        rewritten_query = rewritten_query.replace(nim.group(0), f"NOT EXISTS (SELECT 1 FROM {sub_tab} {where_join})")

    # 4. Correlated subqueries in SELECT list
    select_sub_matches = re.finditer(r"SELECT\s+[^;]*,\s*\(\s*SELECT\s+[^)]+\s+FROM\s+([a-zA-Z0-9_$#\.]+)[^)]*\)", raw_query, re.IGNORECASE)
    for ssm in select_sub_matches:
        anti_patterns_found.append(
            {
                "type": "CORRELATED_SCALAR_SUBQUERY",
                "snippet": ssm.group(0)[:120] + "...",
                "target": "SELECT list scalar subquery",
                "impact": "HIGH - Scalar subquery in SELECT projection may execute once per parent row (N+1 execution pattern).",
                "recommendation": "Rewrite using a `LEFT JOIN` with aggregated subquery/inline view, or analytic functions (e.g. `MAX(...) OVER (PARTITION BY ...)`).",
            }
        )

    # 5. Schema-Aware Index & FTS analysis
    table_names: list[str] = list(target_tables or [])
    if not table_names:
        found = re.findall(r"\b(?:FROM|JOIN|INTO|UPDATE)\s+([a-zA-Z0-9_$#\.]+)", raw_query, re.IGNORECASE)
        for t in found:
            clean = t.strip().split(".")[-1].upper()
            if not clean.startswith("(") and clean not in table_names:
                table_names.append(clean)

    if schemas:
        known_tables: dict[str, TableMeta] = {}
        for s in schemas:
            for t in s.tables:
                known_tables[t.name.upper()] = t
            for v in s.views:
                known_tables[v.name.upper()] = TableMeta(name=v.name, columns=v.columns)

        for t_name in table_names:
            if t_name in known_tables:
                meta = known_tables[t_name]
                pks = set(meta.primary_keys or [])
                fks = {fk.column.upper() for fk in (meta.foreign_keys or []) if fk.column}
                indexed_cols = pks | fks
                table_cols = {c.name.upper() for c in meta.columns}

                raw_where_cols = re.findall(
                    rf"\b(?:{t_name}\.)?([a-zA-Z0-9_$#]+)\s*(?:=|!=|<>|>=|<=|>|<|\bBETWEEN\b|\bIN\b|\bLIKE\b|\bIS\b)",
                    raw_query,
                    re.IGNORECASE,
                )
                used_where_cols = {c.upper() for c in raw_where_cols if c.upper() in table_cols}

                has_index_filter = bool(used_where_cols & indexed_cols)
                if not has_index_filter and used_where_cols:
                    fts_warnings.append(
                        {
                            "table": t_name,
                            "used_filters": list(sorted(used_where_cols)),
                            "warning": f"Table '{t_name}' is filtered on columns ({', '.join(sorted(used_where_cols))}) without Primary Key ({', '.join(sorted(pks)) or 'None'}) or Foreign Key filters, which may cause a Full Table Scan (FTS).",
                        }
                    )
                    eq_cols = []
                    range_cols = []
                    for c in used_where_cols:
                        if re.search(rf"\b(?:{t_name}\.)?{c}\s*=", raw_query, re.IGNORECASE):
                            eq_cols.append(c)
                        else:
                            range_cols.append(c)
                    ordered_idx_cols = eq_cols + range_cols
                    index_recommendations.append(
                        {
                            "table": t_name,
                            "suggested_index": f"CREATE INDEX idx_{t_name.lower()}_{'_'.join(ordered_idx_cols).lower()} ON {t_name} ({', '.join(ordered_idx_cols)});",
                            "rationale": "Compound index ordering: Equality columns placed first, followed by range/inequality columns to maximize index pruning.",
                        }
                    )

    # 6. AI-assisted synthesis if client is available
    ai_tuning_proposal: str | None = None
    if client and hasattr(client, "generate_text") and callable(client.generate_text):
        try:
            prompt = (
                f"You are an expert Oracle SQL Performance & DBA Tuning Specialist.\n"
                f"Analyze and optimize this Oracle SQL query:\n```sql\n{raw_query}\n```\n\n"
                f"Identified Heuristic Anti-Patterns:\n{json.dumps(anti_patterns_found, indent=2, ensure_ascii=False)}\n\n"
                f"FTS Warnings:\n{json.dumps(fts_warnings, indent=2, ensure_ascii=False)}\n\n"
                f"Provide:\n"
                f"1. A fully rewritten, high-performance Oracle SQL query.\n"
                f"2. Step-by-step rationale for each optimization (e.g. sargability, anti-join, analytic functions, indexing).\n"
                f"3. Expected execution plan improvements (e.g. INDEX RANGE SCAN vs FULL TABLE SCAN, HASH ANTI-JOIN)."
            )
            ai_tuning_proposal = client.generate_text(
                prompt, system_prompt="You are an expert Oracle Database Performance Tuning Engineer."
            )
        except Exception:
            ai_tuning_proposal = None

    return {
        "query": raw_query,
        "analyzed_tables": table_names,
        "anti_patterns_count": len(anti_patterns_found),
        "anti_patterns": anti_patterns_found,
        "fts_warnings": fts_warnings,
        "index_recommendations": index_recommendations,
        "rewritten_query": rewritten_query if rewritten_query != raw_query else None,
        "ai_tuning_proposal": ai_tuning_proposal,
        "summary": (
            f"Analysis complete: {len(anti_patterns_found)} anti-pattern(s) detected, "
            f"{len(fts_warnings)} potential FTS warning(s), {len(index_recommendations)} index recommendation(s)."
        ),
    }


def execute_tool_call(
    tool_name: str,
    arguments: dict[str, Any],
    schemas: list[SchemaMetadata],
    config: LeaiConfig,
    client: Any = None,
) -> str:
    """Dispatches and executes the requested database tool call and returns a JSON string response."""
    try:
        # Sanitize any @ prefixes passed by LLM due to user @mentions in chat/terminal
        for k in ("table_name", "object_name", "package_name", "subprogram_name"):
            if k in arguments and isinstance(arguments[k], str):
                arguments[k] = arguments[k].lstrip("@").strip()
        if tool_name == "delegate_to_specialist":
            from leai.ai.subagents import execute_subagent

            role = arguments.get("specialist_role") or arguments.get("role", "")
            task = arguments.get("task", "")
            if not client:
                res = {"error": "LLM Client not available for delegating to specialist."}
            else:
                out = execute_subagent(role=role, task=task, schemas=schemas, config=config, client=client)
                res = {"specialist": role, "result": out}
        elif tool_name == "lookup_business_term":
            res = lookup_business_term(
                config=config,
                query=arguments.get("query", ""),
                tag=arguments.get("tag"),
            )
        elif tool_name == "search_business_documentation":
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
            res = search_database_objects(
                schemas, query=arguments.get("query", ""), object_type=arguments.get("object_type"), config=config
            )
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
        elif tool_name == "explain_and_tune_sql":
            res = explain_and_tune_sql(
                schemas,
                query=arguments.get("query", ""),
                target_tables=arguments.get("target_tables"),
                config=config,
                client=client,
            )
        elif tool_name == "validate_oracle_sql":
            res = validate_oracle_sql(
                schemas,
                sql=arguments.get("sql", ""),
                config=config,
            )
        else:
            res = {"error": f"Unknown tool: '{tool_name}'"}
        return json.dumps(res, ensure_ascii=False, separators=(",", ":"))
    except Exception as exc:
        return json.dumps({"error": f"Tool execution failed ({tool_name}): {str(exc)}"}, ensure_ascii=False, separators=(",", ":"))


def summarize_tool_result(tool_name: str, arguments: dict[str, Any], raw_output: str) -> str:
    """Generates a concise, human-readable summary of a tool execution result."""
    try:
        data = json.loads(raw_output)
        if isinstance(data, dict) and "error" in data:
            return f"❌ {data['error']}"

        if tool_name == "lookup_business_term":
            results = data.get("results", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            count = len(results)
            if count == 0:
                return "0 business terms found"
            top_term = results[0].get("term", "")
            return f"{count} term{'s' if count > 1 else ''} found ('{top_term}')"

        if tool_name == "delegate_to_specialist":
            role = arguments.get("specialist_role", "specialist")
            return f"Specialist @{role} completed analysis"

        if tool_name == "explain_and_tune_sql":
            if isinstance(data, dict):
                ap_cnt = data.get("anti_patterns_count", 0)
                idx_cnt = len(data.get("index_recommendations", []))
                return f"{ap_cnt} anti-pattern{'s' if ap_cnt != 1 else ''}, {idx_cnt} index rec{'s' if idx_cnt != 1 else ''}"
            return "SQL tuning analysis complete"

        if tool_name == "validate_oracle_sql":
            if isinstance(data, dict):
                if data.get("valid"):
                    return "✓ Valid Oracle SQL"
                issues = data.get("total_issues", 0)
                return f"⚠️ {issues} non-Oracle dialect issue{'s' if issues != 1 else ''}"
            return "SQL validated"

        if tool_name == "search_column_comments":
            results = data if isinstance(data, list) else data.get("results", [])
            count = len(results)
            if count == 0:
                return "0 columns found"
            return f"{count} column{'s' if count > 1 else ''} found"

        if tool_name == "grep_plsql_code":
            matches = data.get("matches", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            count = len(matches)
            if count == 0:
                return "0 occurrences found"
            return f"{count} occurrence{'s' if count > 1 else ''} found"

        if tool_name == "get_table_schema":
            if isinstance(data, dict):
                cols = len(data.get("columns", []))
                pks = len(data.get("primary_keys", []))
                fks = len(data.get("foreign_keys", []))
                pk_str = f", {pks} PK" if pks else ""
                fk_str = f", {fks} FK" if fks else ""
                return f"{cols} columns{pk_str}{fk_str}"
            return "Table retrieved"

        if tool_name == "get_subprogram_source":
            if isinstance(data, dict):
                source = data.get("source", "")
                if source:
                    lines = len(source.splitlines())
                    return f"{lines} lines of PL/SQL code"
                subprograms = data.get("subprograms", [])
                if subprograms:
                    return f"Package with {len(subprograms)} routines"
            return "PL/SQL code extracted"

        if tool_name == "trace_object_lineage":
            if isinstance(data, dict):
                deps = len(data.get("dependencies", []))
                risk = data.get("risk_level", "NORMAL")
                return f"{deps} dependencies (Risk: {risk})"
            return "Lineage mapped"

        if tool_name == "search_business_documentation":
            results = data.get("results", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            count = len(results)
            if count == 0:
                return "0 documentation results"
            return f"{count} object{'s' if count > 1 else ''}/rule{'s' if count > 1 else ''} found"

        if tool_name == "search_database_objects":
            results = data.get("results", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            count = len(results)
            if count == 0:
                return "0 objects found"
            return f"{count} object{'s' if count > 1 else ''} found"

        if isinstance(data, list):
            return f"{len(data)} items"
        return "OK"
    except Exception:
        return "Completed"
