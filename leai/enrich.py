from __future__ import annotations

import json
from collections.abc import Callable

from rich.console import Console

from leai.ai.base import BaseLLMClient
from leai.ai.prompts import CODE_OBJECT_ENRICHMENT_SYSTEM_PROMPT, TABLE_ENRICHMENT_SYSTEM_PROMPT
from leai.annotations import ensure_annotation_stub, save_annotation
from leai.config import LeaiConfig
from leai.models import CodeObjectMeta, ObjectAnnotation, SchemaMetadata, TableMeta

console = Console()


def enrich_table_annotation(
    table: TableMeta,
    annotation: ObjectAnnotation,
    client: BaseLLMClient,
    overwrite: bool = False,
) -> ObjectAnnotation:
    """Enriches a table annotation using the LLM client."""
    # Check if enrichment is needed
    has_desc = bool(annotation.description and annotation.description.strip())
    missing_cols = [c.name for c in table.columns if not annotation.columns.get(c.name)]

    if has_desc and not missing_cols and not overwrite:
        return annotation

    # Build context for the LLM
    cols_data = [{"name": c.name, "type": c.data_type, "nullable": c.nullable, "existing_comment": c.comment} for c in table.columns]
    fks_data = [{"name": fk.name, "column": fk.column, "referenced_table": fk.referenced_table} for fk in table.foreign_keys]

    payload = {
        "table_name": table.name,
        "existing_comment": table.comment,
        "primary_keys": table.primary_keys,
        "foreign_keys": fks_data,
        "columns": cols_data,
    }

    user_prompt = f"Analyze the following Oracle table and return the business documentation:\n```json\n{json.dumps(payload, indent=2, ensure_ascii=False)}\n```"

    try:
        ai_data = client.generate_json(user_prompt, system_prompt=TABLE_ENRICHMENT_SYSTEM_PROMPT)
    except Exception as exc:
        console.print(f"[yellow]Warning: Failed to enrich table {table.name} with AI: {exc}[/yellow]")
        return annotation

    # Update description
    if overwrite or not has_desc:
        if ai_data.get("description"):
            annotation.description = str(ai_data["description"]).strip()

    # Update business rules
    if ai_data.get("business_rules") and isinstance(ai_data["business_rules"], list):
        if overwrite:
            annotation.business_rules = [str(r).strip() for r in ai_data["business_rules"]]
        else:
            existing_rules = set(annotation.business_rules)
            for r in ai_data["business_rules"]:
                r_clean = str(r).strip()
                if r_clean and r_clean not in existing_rules:
                    annotation.business_rules.append(r_clean)

    # Update use cases
    if ai_data.get("use_cases") and isinstance(ai_data["use_cases"], list):
        if overwrite:
            annotation.use_cases = [str(u).strip() for u in ai_data["use_cases"]]
        else:
            existing_uc = set(annotation.use_cases)
            for u in ai_data["use_cases"]:
                u_clean = str(u).strip()
                if u_clean and u_clean not in existing_uc:
                    annotation.use_cases.append(u_clean)

    # Update warnings
    if ai_data.get("warnings") and isinstance(ai_data["warnings"], list):
        if overwrite:
            annotation.warnings = [str(w).strip() for w in ai_data["warnings"]]
        else:
            existing_w = set(annotation.warnings)
            for w in ai_data["warnings"]:
                w_clean = str(w).strip()
                if w_clean and w_clean not in existing_w:
                    annotation.warnings.append(w_clean)

    # Update related objects
    if ai_data.get("related_objects") and isinstance(ai_data["related_objects"], list):
        if overwrite:
            annotation.related_objects = [str(ro).strip() for ro in ai_data["related_objects"]]
        else:
            existing_ro = set(annotation.related_objects)
            for ro in ai_data["related_objects"]:
                ro_clean = str(ro).strip()
                if ro_clean and ro_clean not in existing_ro:
                    annotation.related_objects.append(ro_clean)

    # Update tags
    if ai_data.get("tags") and isinstance(ai_data["tags"], list):
        if overwrite:
            annotation.tags = [str(t).strip() for t in ai_data["tags"]]
        else:
            existing_tags = set(annotation.tags)
            for t in ai_data["tags"]:
                t_clean = str(t).strip()
                if t_clean and t_clean not in existing_tags:
                    annotation.tags.append(t_clean)

    # Update columns
    ai_cols = ai_data.get("columns", {})
    if isinstance(ai_cols, dict):
        for col in table.columns:
            ai_comm = ai_cols.get(col.name)
            if ai_comm and (overwrite or not annotation.columns.get(col.name)):
                annotation.columns[col.name] = str(ai_comm).strip()

    return annotation


def enrich_code_object_annotation(
    co: CodeObjectMeta,
    annotation: ObjectAnnotation,
    client: BaseLLMClient,
    overwrite: bool = False,
) -> ObjectAnnotation:
    """Enriches a Procedure, Function, Package or Trigger annotation using LLM."""
    has_desc = bool(annotation.description and annotation.description.strip())
    if has_desc and not overwrite:
        return annotation

    source_preview = (co.source or "")[:12000]  # Reasonable token limit
    subprograms_list = [sp.name for sp in co.subprograms]

    payload = {
        "name": co.name,
        "object_type": co.object_type,
        "subprograms": subprograms_list,
        "source_code": source_preview,
    }

    user_prompt = f"Analyze the following Oracle PL/SQL code and return the business documentation:\n```json\n{json.dumps(payload, indent=2, ensure_ascii=False)}\n```"

    try:
        ai_data = client.generate_json(user_prompt, system_prompt=CODE_OBJECT_ENRICHMENT_SYSTEM_PROMPT)
    except Exception as exc:
        console.print(f"[yellow]Warning: Failed to enrich {co.object_type} {co.name} with AI: {exc}[/yellow]")
        return annotation

    if overwrite or not has_desc:
        if ai_data.get("description"):
            annotation.description = str(ai_data["description"]).strip()

    if ai_data.get("business_rules") and isinstance(ai_data["business_rules"], list):
        if overwrite:
            annotation.business_rules = [str(r).strip() for r in ai_data["business_rules"]]
        else:
            existing_rules = set(annotation.business_rules)
            for r in ai_data["business_rules"]:
                r_clean = str(r).strip()
                if r_clean and r_clean not in existing_rules:
                    annotation.business_rules.append(r_clean)

    if ai_data.get("use_cases") and isinstance(ai_data["use_cases"], list):
        if overwrite:
            annotation.use_cases = [str(u).strip() for u in ai_data["use_cases"]]
        else:
            existing_uc = set(annotation.use_cases)
            for u in ai_data["use_cases"]:
                u_clean = str(u).strip()
                if u_clean and u_clean not in existing_uc:
                    annotation.use_cases.append(u_clean)

    if ai_data.get("warnings") and isinstance(ai_data["warnings"], list):
        if overwrite:
            annotation.warnings = [str(w).strip() for w in ai_data["warnings"]]
        else:
            existing_w = set(annotation.warnings)
            for w in ai_data["warnings"]:
                w_clean = str(w).strip()
                if w_clean and w_clean not in existing_w:
                    annotation.warnings.append(w_clean)

    if ai_data.get("related_objects") and isinstance(ai_data["related_objects"], list):
        if overwrite:
            annotation.related_objects = [str(ro).strip() for ro in ai_data["related_objects"]]
        else:
            existing_ro = set(annotation.related_objects)
            for ro in ai_data["related_objects"]:
                ro_clean = str(ro).strip()
                if ro_clean and ro_clean not in existing_ro:
                    annotation.related_objects.append(ro_clean)

    if ai_data.get("tags") and isinstance(ai_data["tags"], list):
        if overwrite:
            annotation.tags = [str(t).strip() for t in ai_data["tags"]]
        else:
            existing_tags = set(annotation.tags)
            for t in ai_data["tags"]:
                t_clean = str(t).strip()
                if t_clean and t_clean not in existing_tags:
                    annotation.tags.append(t_clean)

    return annotation


def enrich_schema_annotations(
    schemas: list[SchemaMetadata],
    config: LeaiConfig,
    client: BaseLLMClient,
    overwrite: bool = False,
    target_object_name: str | None = None,
    target_object_types: list[str] | None = None,
    progress_callback: Callable[[str, str], None] | None = None,
) -> tuple[int, int]:
    """Iterates through schemas and auto-completes annotations using the LLM client.
    Returns (processed_tables_count, processed_code_objects_count).
    """
    tables_count = 0
    code_count = 0
    is_multi = len(schemas) > 1 or config.is_all_schemas
    types_filter = [t.lower().rstrip("s") for t in (target_object_types or config.object_types)]
    target_upper = target_object_name.strip().upper() if target_object_name else None

    for schema in schemas:
        base_dir = config.annotationsPath / schema.schema_name if is_multi else config.annotationsPath

        # 1. Tables
        if "table" in types_filter or not target_object_types:
            for t in schema.tables:
                if target_upper and t.name.upper() != target_upper:
                    continue
                if progress_callback:
                    progress_callback("TABLE", t.name)
                ann_path = base_dir / "tables" / f"{t.name}.yml"
                ann = ensure_annotation_stub(ann_path)
                enriched = enrich_table_annotation(t, ann, client, overwrite=overwrite)
                save_annotation(ann_path, enriched)
                tables_count += 1

        # 2. Code Objects (Procedures, Functions, Packages, Types)
        if any(t in types_filter for t in ("procedure", "function", "package", "type", "code_object")) or not target_object_types:
            for co in schema.code_objects:
                if target_upper and co.name.upper() != target_upper:
                    continue
                if progress_callback:
                    progress_callback(co.object_type, co.name)
                ann_path = base_dir / "code_objects" / f"{co.name}.yml"
                ann = ensure_annotation_stub(ann_path)
                enriched = enrich_code_object_annotation(co, ann, client, overwrite=overwrite)
                save_annotation(ann_path, enriched)
                code_count += 1

    return tables_count, code_count

