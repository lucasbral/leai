from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from leai.annotations import ensure_annotation_stub
from leai.models import (
    CodeObjectMeta,
    DependencyLink,
    IndexMeta,
    MaterializedViewMeta,
    ObjectAnnotation,
    ObjectTraceResult,
    SchemaMetadata,
    SequenceMeta,
    SubprogramMeta,
    SynonymMeta,
    TableMeta,
    TriggerMeta,
    ViewMeta,
)

MANUAL_START = "<!-- LEAI:MANUAL:START -->"
MANUAL_END = "<!-- LEAI:MANUAL:END -->"


def _extract_manual_section(content: str | None) -> str:
    if not content:
        return ""
    start = content.find(MANUAL_START)
    end = content.find(MANUAL_END)
    if start == -1 or end == -1 or end <= start:
        return ""
    return content[start + len(MANUAL_START) : end].strip("\n")


def _render_manual_section(doc: str = "") -> list[str]:
    return ["", "## Human Documentation", "", MANUAL_START, doc or "", MANUAL_END, ""]


def _render_audit_meta(obj) -> list[str]:
    lines: list[str] = []
    last_ddl = getattr(obj, "last_ddl_time", None)
    modified_by = getattr(obj, "last_modified_by", None)
    created = getattr(obj, "created_at", None)

    parts: list[str] = []
    if last_ddl:
        by_str = f" (by `{modified_by}`)" if modified_by else ""
        parts.append(f"**Last DDL Modification:** {last_ddl}{by_str}")
    if created:
        parts.append(f"**Creation Date:** {created}")

    if parts:
        lines.append(" | ".join(parts))
        lines.append("")
    return lines


def _render_annotation_details(annotation: ObjectAnnotation | None) -> list[str]:
    if not annotation:
        return []
    lines: list[str] = []

    if annotation.tags:
        tags_str = ", ".join(annotation.tags)
        lines.extend(["", f"**Tags / Business Domain:** `{tags_str}`"])

    if annotation.warnings:
        lines.extend(["", "## Technical Alerts & Warnings", ""])
        for warn in annotation.warnings:
            lines.append(f"> [!WARNING]\n> {warn}")

    if annotation.related_objects:
        lines.extend(["", "## Business Relationships", ""])
        for rel in annotation.related_objects:
            lines.append(f"- {rel}")

    return lines


def _render_use_cases(annotation: ObjectAnnotation | None) -> list[str]:
    if not annotation or not annotation.use_cases:
        return []
    lines = ["", "## Use Cases & Sample Queries", ""]
    for uc in annotation.use_cases:
        uc_clean = uc.strip()
        if "SELECT " in uc_clean.upper() and not uc_clean.startswith("```"):
            lines.append(f"```sql\n{uc_clean}\n```\n")
        else:
            lines.append(f"- {uc_clean}")
    return lines


def _render_business_rules(annotation: ObjectAnnotation | None) -> list[str]:
    lines = _render_annotation_details(annotation)
    if annotation and annotation.business_rules:
        lines.extend(["", "## Business Rules", ""])
        for rule in annotation.business_rules:
            lines.append(f"- {rule}")
    lines.extend(_render_use_cases(annotation))
    return lines


def _calculate_risk_level(dep_count: int) -> str:
    if dep_count == 0:
        return "LOW"
    elif dep_count <= 3:
        return "MEDIUM"
    elif dep_count <= 7:
        return "HIGH"
    return "CRITICAL"


def generate_mermaid_graph(focal_name: str, dependencies: list[DependencyLink]) -> str:
    lines = ["```mermaid", "graph TD"]
    focal_id = focal_name.replace("$", "_").replace(".", "_")
    lines.append(f'    {focal_id}["⭐ {focal_name} (Focal)"]:::focalClass')

    nodes = {focal_name: focal_id}
    edges = []

    for dep in dependencies:
        s_id = dep.source_name.replace("$", "_").replace(".", "_")
        t_id = dep.target_name.replace("$", "_").replace(".", "_")

        if dep.source_name not in nodes:
            nodes[dep.source_name] = s_id
            icon = (
                "📊"
                if dep.source_type == "TABLE"
                else (
                    "👁️"
                    if "VIEW" in dep.source_type
                    else ("⚡" if dep.source_type in ("TRIGGER", "SUBPROGRAM", "PROCEDURE", "FUNCTION") else "⚙️")
                )
            )
            lines.append(f'    {s_id}["{icon} {dep.source_name} (L{dep.depth})"]')

        if dep.target_name not in nodes:
            nodes[dep.target_name] = t_id
            icon = (
                "📊"
                if dep.target_type == "TABLE"
                else (
                    "👁️"
                    if "VIEW" in dep.target_type
                    else ("⚡" if dep.target_type in ("TRIGGER", "SUBPROGRAM", "PROCEDURE", "FUNCTION") else "⚙️")
                )
            )
            lines.append(f'    {t_id}["{icon} {dep.target_name} (L{dep.depth})"]')

        label = dep.relation_type.replace("_", " ")
        edges.append(f"    {s_id} -->|{label}| {t_id}")

    lines.extend(edges)
    lines.append("")
    lines.append("    classDef focalClass fill:#ff9800,stroke:#e65100,stroke-width:3px,font-weight:bold,color:#000;")
    lines.append("```")
    return "\n".join(lines)


def generate_semantic_rag_text(trace_result: ObjectTraceResult, annotation: ObjectAnnotation | None = None) -> str:
    focal_name = trace_result.focal_name
    focal_obj = trace_result.focal_object
    focal_type = trace_result.focal_type

    if isinstance(focal_obj, TableMeta):
        focal_type = "TABLE"
    elif isinstance(focal_obj, ViewMeta):
        focal_type = "VIEW"
    elif isinstance(focal_obj, MaterializedViewMeta):
        focal_type = "MATERIALIZED VIEW"
    elif isinstance(focal_obj, CodeObjectMeta):
        focal_type = focal_obj.object_type.upper()
    elif isinstance(focal_obj, TriggerMeta):
        focal_type = "TRIGGER"
    elif isinstance(focal_obj, SynonymMeta):
        focal_type = "SYNONYM"

    desc = (annotation and annotation.description) or getattr(focal_obj, "comment", None) or f"Object {focal_name} of type {focal_type}."

    parts = [f"The object {focal_name} is of type {focal_type}. Business description: {desc.strip()}."]

    if annotation and annotation.business_rules:
        rules_str = " Associated business rules: " + "; ".join(annotation.business_rules) + "."
        parts.append(rules_str)

    if annotation and annotation.use_cases:
        use_cases_str = " Use cases and reference queries: " + " | ".join(annotation.use_cases) + "."
        parts.append(use_cases_str)

    if trace_result.extracted_notes:
        notes_str = " Code notes and extracted rules: " + " | ".join(trace_result.extracted_notes[:5]) + "."
        parts.append(notes_str)

    if trace_result.extracted_tasks:
        tasks_str = " Task / issue traceability: " + ", ".join(trace_result.extracted_tasks) + "."
        parts.append(tasks_str)

    if isinstance(focal_obj, TableMeta):
        cols_summary = ", ".join([f"{c.name} ({c.data_type})" for c in focal_obj.columns[:15]])
        parts.append(f" Primary column structure: {cols_summary}.")

    if trace_result.dependencies:
        dep_descriptions = []
        seen_dep_texts = set()
        for dep in trace_result.dependencies:
            if dep.target_name == focal_name and dep.source_name == focal_name:
                continue
            text = None
            if dep.relation_type == "FK_REFERENCES":
                text = f"has a foreign key pointing to table {dep.target_name}"
            elif dep.relation_type == "FK_REFERENCED_BY":
                text = f"is referenced by child table {dep.source_name}"
            elif dep.relation_type == "READS/SELECTS":
                text = f"queries object {dep.target_name}"
            elif dep.relation_type == "EXECUTES/CALLS":
                text = f"invokes package/routine {dep.target_name}"
            elif dep.relation_type == "CALLS_SUBPROGRAM":
                text = f"is invoked by {dep.source_name}"
            elif dep.relation_type == "TRIGGER_ON":
                text = f"has trigger {dep.source_name}"
            elif dep.relation_type == "PLSQL_DEPENDENCY":
                text = f"is referenced by PL/SQL code {dep.source_name}"
            elif dep.relation_type == "SYNONYM_FOR":
                text = f"has synonym {dep.source_name} pointing to it"
            elif dep.relation_type == "REFERENCED_BY":
                text = f"is referenced by {dep.source_type.lower()} object {dep.source_name}"
            elif dep.relation_type == "DEPENDS_ON":
                text = f"depends on {dep.target_type.lower()} object {dep.target_name}"
            else:
                text = f"has relationship with {dep.target_name} ({dep.relation_type})"

            if text and text not in seen_dep_texts:
                seen_dep_texts.add(text)
                dep_descriptions.append(text)

        if dep_descriptions:
            parts.append(" Relational impact: " + ", ".join(dep_descriptions[:10]) + ".")

    return "".join(parts)


def _build_rag_frontmatter(
    trace_result: ObjectTraceResult | None,
    annotation: ObjectAnnotation | None = None,
) -> list[str]:
    if not trace_result:
        return []
    import yaml

    focal_name = trace_result.focal_name
    focal_type = trace_result.focal_type
    dep_count = len(trace_result.dependencies)
    risk_level = _calculate_risk_level(dep_count)

    parents = [
        d.target_name
        for d in trace_result.dependencies
        if d.target_name != focal_name and d.relation_type in ("FK_REFERENCES", "DEPENDS_ON", "READS/SELECTS", "EXECUTES/CALLS")
    ]
    children = [
        d.source_name for d in trace_result.dependencies if d.source_name != focal_name and d.relation_type in ("FK_REFERENCED_BY",)
    ]
    consumers = [
        d.source_name
        for d in trace_result.dependencies
        if d.source_name != focal_name and d.relation_type in ("PLSQL_DEPENDENCY", "TRIGGER_ON", "REFERENCED_BY", "CALLS_SUBPROGRAM")
    ]

    rag_meta = {
        "rag_metadata": {
            "entity": focal_name,
            "type": focal_type,
            "risk_level": risk_level,
            "tags": annotation.tags if annotation else [],
            "use_cases": annotation.use_cases if annotation else [],
            "tasks": trace_result.extracted_tasks,
            "engineering_notes": trace_result.extracted_notes[:5] if trace_result.extracted_notes else [],
            "impact_summary": {
                "total_connections": dep_count,
                "upstream_parents": sorted(set(parents)),
                "downstream_children": sorted(set(children)),
                "consumers": sorted(set(consumers)),
            },
        }
    }
    yaml_str = yaml.safe_dump(rag_meta, sort_keys=False, allow_unicode=True).strip()
    return ["---", yaml_str, "---", ""]


def _render_trace_xray_and_graph(
    trace_result: ObjectTraceResult | None,
    annotation: ObjectAnnotation | None = None,
) -> list[str]:
    if not trace_result:
        return []
    lines: list[str] = []
    focal_name = trace_result.focal_name
    dep_count = len(trace_result.dependencies)
    risk_level = _calculate_risk_level(dep_count)

    parents = [
        d.target_name
        for d in trace_result.dependencies
        if d.target_name != focal_name and d.relation_type in ("FK_REFERENCES", "DEPENDS_ON", "READS/SELECTS", "EXECUTES/CALLS")
    ]
    children = [
        d.source_name for d in trace_result.dependencies if d.source_name != focal_name and d.relation_type in ("FK_REFERENCED_BY",)
    ]
    consumers = [
        d.source_name
        for d in trace_result.dependencies
        if d.source_name != focal_name and d.relation_type in ("PLSQL_DEPENDENCY", "TRIGGER_ON", "REFERENCED_BY", "CALLS_SUBPROGRAM")
    ]

    risk_badge_color = "CRITICAL" if risk_level == "CRITICAL" else ("WARNING" if risk_level in ("HIGH", "MEDIUM") else "NOTE")
    lines.extend(
        [
            "",
            "## 🔍 Technical Impact & Risk X-Ray",
            "",
            f"> [!{risk_badge_color}]",
            "> **Change Risk Analysis:**",
            f"> - **Risk Level:** `{risk_level}` ({dep_count} connections mapped in graph)",
            f"> - **Consumed Objects (Upstream):** `{len(set(parents))}` ({', '.join(sorted(set(parents))) if parents else 'None'})",
            f"> - **Child Tables (Downstream):** `{len(set(children))}` ({', '.join(sorted(set(children))) if children else 'None'})",
            f"> - **Active Consumers (Callers):** `{len(set(consumers))}` ({', '.join(sorted(set(consumers))) if consumers else 'None'})",
            "",
        ]
    )

    if trace_result.extracted_notes or trace_result.extracted_tasks:
        lines.extend(["## 💡 Extracted Code Notes & Rules (Engineering)", "", "> [!NOTE]", "> **Traceability & Internal Rules:**"])
        if trace_result.extracted_notes:
            lines.append("> - **Code Rules:**")
            for note in trace_result.extracted_notes:
                lines.append(f">   - {note}")
        if trace_result.extracted_tasks:
            tasks_str = ", ".join([f"`{t}`" for t in trace_result.extracted_tasks])
            lines.append(f"> - **Linked Tasks / Issues:** {tasks_str}")
        lines.append("")

    if trace_result.dependencies:
        lines.extend(["## Lineage & Relationship Graph", ""])
        lines.append(generate_mermaid_graph(focal_name, trace_result.dependencies))
        lines.append("")

    semantic_text = generate_semantic_rag_text(trace_result, annotation=annotation)
    lines.extend(["## 🧠 Semantic Narrative Summary (RAG Ready)", "", semantic_text, ""])

    return lines


def render_table_markdown(
    table: TableMeta,
    table_doc: str = "",
    column_docs: dict[str, str] | None = None,
    annotation: ObjectAnnotation | None = None,
    trace_result: ObjectTraceResult | None = None,
) -> str:
    column_docs = column_docs or {}
    ann_cols = annotation.columns if annotation else {}
    lines = []
    lines.extend(_build_rag_frontmatter(trace_result, annotation))
    lines.extend([f"# TABLE: {table.name}", "", "## Overview", ""])
    lines.extend(_render_audit_meta(table))
    table_desc = (annotation and annotation.description) or table.comment or table_doc or "No technical description in Oracle dictionary."
    lines.append(table_desc.replace("\r\n", " ").replace("\n", " "))
    lines.extend(_render_business_rules(annotation))

    lines.extend(["", "## Columns", "", "| Column | Type | Nullable | Default | Comment |", "|---|---|---|---|---|"])

    for column in table.columns:
        raw_comment = ann_cols.get(column.name) or column_docs.get(column.name) or column.comment or ""
        comment_clean = raw_comment.replace("\r\n", " ").replace("\n", " ").replace("|", "\\|")
        default_clean = (column.default or "").replace("\r\n", " ").replace("\n", " ").replace("|", "\\|")
        lines.append(f"| {column.name} | {column.data_type} | {'YES' if column.nullable else 'NO'} | {default_clean} | {comment_clean} |")

    lines.extend(["", "## Primary Key", ""])
    lines.append(", ".join(table.primary_keys) if table.primary_keys else "Not defined")

    lines.extend(["", "## Foreign Keys", ""])
    if table.foreign_keys:
        lines.append("| Constraint | Column | Reference |")
        lines.append("|---|---|---|")
        for fk in table.foreign_keys:
            lines.append(f"| {fk.name} | {fk.column} | {fk.referenced_table}.{fk.referenced_column} |")
    else:
        lines.append("None")

    lines.extend(_render_trace_xray_and_graph(trace_result, annotation))
    lines.extend(_render_manual_section(table_doc))
    return "\n".join(lines)


def render_view_markdown(
    view: ViewMeta,
    view_doc: str = "",
    column_docs: dict[str, str] | None = None,
    annotation: ObjectAnnotation | None = None,
    trace_result: ObjectTraceResult | None = None,
) -> str:
    column_docs = column_docs or {}
    ann_cols = annotation.columns if annotation else {}
    lines = []
    lines.extend(_build_rag_frontmatter(trace_result, annotation))
    lines.extend([f"# VIEW: {view.name}", "", "## Overview", ""])
    desc = (annotation and annotation.description) or view.comment or view_doc or "Oracle database View."
    lines.append(desc.replace("\r\n", " ").replace("\n", " "))
    lines.extend(_render_business_rules(annotation))

    lines.extend(["", "## Columns", "", "| Column | Type | Nullable | Default | Comment |", "|---|---|---|---|---|"])

    for column in view.columns:
        raw_comment = ann_cols.get(column.name) or column_docs.get(column.name) or column.comment or ""
        comment_clean = raw_comment.replace("\r\n", " ").replace("\n", " ").replace("|", "\\|")
        default_clean = (column.default or "").replace("\r\n", " ").replace("\n", " ").replace("|", "\\|")
        lines.append(f"| {column.name} | {column.data_type} | {'YES' if column.nullable else 'NO'} | {default_clean} | {comment_clean} |")

    if view.text:
        lines.extend(["", "## SQL Definition", "", "```sql", view.text.strip(), "```"])

    lines.extend(_render_trace_xray_and_graph(trace_result, annotation))
    lines.extend(_render_manual_section(view_doc))
    return "\n".join(lines)


def render_mview_markdown(
    mview: MaterializedViewMeta,
    mview_doc: str = "",
    annotation: ObjectAnnotation | None = None,
    trace_result: ObjectTraceResult | None = None,
) -> str:
    lines = []
    lines.extend(_build_rag_frontmatter(trace_result, annotation))
    lines.extend([f"# MATERIALIZED VIEW: {mview.name}", "", "## Overview", ""])
    desc = (annotation and annotation.description) or mview.comment or mview_doc or "Oracle Materialized View."
    lines.append(desc.replace("\r\n", " ").replace("\n", " "))
    lines.extend(_render_business_rules(annotation))

    lines.extend(
        [
            "",
            "## Properties",
            "",
            "| Property | Value |",
            "|---|---|",
            f"| Refresh Mode | {mview.refresh_mode or 'N/A'} |",
            f"| Refresh Type | {mview.refresh_type or 'N/A'} |",
            f"| Updatable | {'YES' if mview.updatable else 'NO'} |",
        ]
    )

    if mview.columns:
        ann_cols = annotation.columns if annotation else {}
        lines.extend(["", "## Columns", "", "| Column | Type | Nullable | Comment |", "|---|---|---|---|"])
        for column in mview.columns:
            raw_comment = ann_cols.get(column.name) or column.comment or ""
            comment_clean = raw_comment.replace("\r\n", " ").replace("\n", " ").replace("|", "\\|")
            lines.append(f"| {column.name} | {column.data_type} | {'YES' if column.nullable else 'NO'} | {comment_clean} |")

    if mview.query:
        lines.extend(["", "## SQL Query", "", "```sql", mview.query.strip(), "```"])

    lines.extend(_render_trace_xray_and_graph(trace_result, annotation))
    lines.extend(_render_manual_section(mview_doc))
    return "\n".join(lines)


def render_subprogram_markdown(
    sub: SubprogramMeta,
    sub_doc: str = "",
    annotation: ObjectAnnotation | None = None,
    trace_result: ObjectTraceResult | None = None,
) -> str:
    lines = []
    lines.extend(_build_rag_frontmatter(trace_result, annotation))
    lines.extend([f"# {sub.subprogram_type.upper()}: {sub.package_name}.{sub.name}", "", "## Overview", ""])
    desc = (
        (annotation and annotation.description)
        or sub.comment
        or sub_doc
        or f"PL/SQL routine (`{sub.name}`) belonging to package `{sub.package_name}`."
    )
    lines.append(desc.replace("\r\n", " ").replace("\n", " "))
    lines.extend(_render_business_rules(annotation))

    if sub.source:
        lines.extend(["", "## PL/SQL Source Code", "", "```sql", sub.source.strip(), "```"])

    lines.extend(_render_trace_xray_and_graph(trace_result, annotation))
    lines.extend(_render_manual_section(sub_doc))
    return "\n".join(lines)


def render_code_object_markdown(
    code_obj: CodeObjectMeta,
    code_doc: str = "",
    annotation: ObjectAnnotation | None = None,
    trace_result: ObjectTraceResult | None = None,
) -> str:
    lines = []
    lines.extend(_build_rag_frontmatter(trace_result, annotation))
    lines.extend([f"# {code_obj.object_type.upper()}: {code_obj.name}", "", "## Overview", ""])
    desc = (
        (annotation and annotation.description)
        or code_obj.comment
        or code_doc
        or f"PL/SQL object ({code_obj.object_type}) stored in Oracle."
    )
    lines.append(desc.replace("\r\n", " ").replace("\n", " "))
    lines.extend(_render_business_rules(annotation))

    if code_obj.subprograms:
        lines.extend(["", "## Disassembled Subprograms", "", "| Type | Name | File |", "|---|---|---|"])
        for sub in code_obj.subprograms:
            lines.append(f"| {sub.subprogram_type} | {sub.name} | `{code_obj.name}/{sub.name}.md` |")

    if code_obj.source:
        lines.extend(["", "## Package Source Code", "", "```sql", code_obj.source.strip(), "```"])

    lines.extend(_render_trace_xray_and_graph(trace_result, annotation))
    lines.extend(_render_manual_section(code_doc))
    return "\n".join(lines)


def render_trigger_markdown(
    trigger: TriggerMeta,
    trigger_doc: str = "",
    annotation: ObjectAnnotation | None = None,
    trace_result: ObjectTraceResult | None = None,
) -> str:
    lines = []
    lines.extend(_build_rag_frontmatter(trace_result, annotation))
    lines.extend(
        [
            f"# TRIGGER: {trigger.name}",
            "",
            "## Overview",
            "",
            (annotation and annotation.description) or f"Trigger associated with table `{trigger.table_name or 'N/A'}`.",
        ]
    )
    lines.extend(_render_business_rules(annotation))
    lines.extend(
        [
            "",
            "## Properties",
            "",
            "| Property | Value |",
            "|---|---|",
            f"| Target Table | {trigger.table_name or 'N/A'} |",
            f"| Type | {trigger.trigger_type or 'N/A'} |",
            f"| Event | {trigger.triggering_event or 'N/A'} |",
            f"| Status | {trigger.status or 'N/A'} |",
        ]
    )

    if trigger.trigger_body:
        lines.extend(["", "## Trigger Code", "", "```sql", trigger.trigger_body.strip(), "```"])

    lines.extend(_render_trace_xray_and_graph(trace_result, annotation))
    lines.extend(_render_manual_section(trigger_doc))
    return "\n".join(lines)


def render_sequence_markdown(
    sequence: SequenceMeta,
    seq_doc: str = "",
    annotation: ObjectAnnotation | None = None,
) -> str:
    lines = [
        f"# SEQUENCE: {sequence.name}",
        "",
        "## Overview",
        "",
        (annotation and annotation.description) or "Oracle numeric sequence.",
    ]
    lines.extend(_render_business_rules(annotation))
    lines.extend(
        [
            "",
            "## Properties",
            "",
            "| Property | Value |",
            "|---|---|",
            f"| Minimum Value | {sequence.min_value if sequence.min_value is not None else 'N/A'} |",
            f"| Maximum Value | {sequence.max_value if sequence.max_value is not None else 'N/A'} |",
            f"| Increment | {sequence.increment_by if sequence.increment_by is not None else 'N/A'} |",
            f"| Last Number | {sequence.last_number if sequence.last_number is not None else 'N/A'} |",
        ]
    )
    lines.extend(_render_manual_section(seq_doc))
    return "\n".join(lines)


def render_index_markdown(
    index: IndexMeta,
    idx_doc: str = "",
    annotation: ObjectAnnotation | None = None,
) -> str:
    cols = ", ".join(index.columns) if index.columns else "None"
    lines = [
        f"# INDEX: {index.name}",
        "",
        "## Overview",
        "",
        (annotation and annotation.description) or f"Index created on table `{index.table_name}` ({index.uniqueness}).",
    ]
    lines.extend(_render_business_rules(annotation))
    lines.extend(
        [
            "",
            "## Properties",
            "",
            "| Property | Value |",
            "|---|---|",
            f"| Target Table | {index.table_name} |",
            f"| Uniqueness | {index.uniqueness} |",
            f"| Indexed Columns | {cols} |",
        ]
    )
    lines.extend(_render_manual_section(idx_doc))
    return "\n".join(lines)


def render_synonym_markdown(
    synonym: SynonymMeta,
    syn_doc: str = "",
    annotation: ObjectAnnotation | None = None,
) -> str:
    lines = [
        f"# SYNONYM: {synonym.name}",
        "",
        "## Overview",
        "",
        (annotation and annotation.description) or f"Synonym pointing to `{synonym.table_owner or ''}.{synonym.table_name or ''}`.",
    ]
    lines.extend(_render_business_rules(annotation))
    lines.extend(
        [
            "",
            "## Properties",
            "",
            "| Property | Value |",
            "|---|---|",
            f"| Target Owner | {synonym.table_owner or 'N/A'} |",
            f"| Target Object | {synonym.table_name or 'N/A'} |",
            f"| DB Link | {synonym.db_link or 'None'} |",
        ]
    )
    lines.extend(_render_manual_section(syn_doc))
    return "\n".join(lines)


def _write_single_doc(file_path: Path, new_markdown: str) -> Path:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(new_markdown, encoding="utf-8")
    return file_path


def _is_category_allowed(category: str, allowed_types: set[str] | None) -> bool:
    if not allowed_types:
        return True
    return category.lower() in allowed_types


def _is_code_obj_allowed(code_obj: CodeObjectMeta, allowed_types: set[str] | None) -> bool:
    if not allowed_types:
        return True
    otype = code_obj.object_type.upper()
    if otype == "PROCEDURE" and "procedures" in allowed_types:
        return True
    if otype == "FUNCTION" and "functions" in allowed_types:
        return True
    if otype in ("PACKAGE", "PACKAGE BODY") and "packages" in allowed_types:
        return True
    if otype in ("TYPE", "TYPE BODY") and "types" in allowed_types:
        return True
    return False


def render_schema_index_markdown(
    schema: SchemaMetadata,
    trace_map: dict[str, ObjectTraceResult] | None = None,
    annotations_map: dict[str, ObjectAnnotation] | None = None,
) -> str:
    """Renders a central governance index (INDEX.md) with risk matrix and object catalogue."""
    trace_map = trace_map or {}
    annotations_map = annotations_map or {}
    schema_name = schema.schema_name or "DEFAULT"

    lines = [
        f"# Schema Catalog & Governance Matrix: `{schema_name}`",
        "",
        "This document consolidates the object inventory, change risk matrix, and links to unified technical documentation generated by **LEAI**.",
        "",
        "## 📊 Object Quantitative Summary",
        "",
        "| Object Type | Quantity |",
        "|---|---|",
        f"| Tables | {len(schema.tables)} |",
        f"| Views | {len(schema.views)} |",
        f"| Materialized Views | {len(schema.mviews)} |",
        f"| Code Objects (Packages/Procedures) | {len(schema.code_objects)} |",
        f"| Triggers | {len(schema.triggers)} |",
        f"| Sequences | {len(schema.sequences)} |",
        f"| Indexes | {len(schema.indexes)} |",
        f"| Synonyms | {len(schema.synonyms)} |",
        "",
        "## 🔍 Change Risk Matrix & Lineage",
        "",
        "| Object | Type | Risk | Connections | Columns / PK | Tags | Documentation |",
        "|---|---|---|---|---|---|---|",
    ]

    for t in sorted(schema.tables, key=lambda x: x.name):
        tr = trace_map.get(t.name.upper())
        ann = annotations_map.get(t.name.upper())
        dep_count = len(tr.dependencies) if tr else 0
        risk = _calculate_risk_level(dep_count)
        risk_emoji = "🔴" if risk in ("CRITICAL", "HIGH") else ("🟡" if risk == "MEDIUM" else "🟢")
        pk_str = f"PK: {', '.join(t.primary_keys)}" if t.primary_keys else "No PK"
        cols_str = f"{len(t.columns)} cols ({pk_str})"
        tags_str = f"`{', '.join(ann.tags)}`" if (ann and ann.tags) else "-"
        lines.append(
            f"| `{t.name}` | Table | {risk_emoji} `{risk}` | {dep_count} | {cols_str} | {tags_str} | [View Details](tables/{t.name}.md) |"
        )

    for v in sorted(schema.views, key=lambda x: x.name):
        tr = trace_map.get(v.name.upper())
        ann = annotations_map.get(v.name.upper())
        dep_count = len(tr.dependencies) if tr else 0
        risk = _calculate_risk_level(dep_count)
        risk_emoji = "🔴" if risk in ("CRITICAL", "HIGH") else ("🟡" if risk == "MEDIUM" else "🟢")
        cols_str = f"{len(v.columns)} cols"
        tags_str = f"`{', '.join(ann.tags)}`" if (ann and ann.tags) else "-"
        lines.append(
            f"| `{v.name}` | View | {risk_emoji} `{risk}` | {dep_count} | {cols_str} | {tags_str} | [View Details](views/{v.name}.md) |"
        )

    for mv in sorted(schema.mviews, key=lambda x: x.name):
        tr = trace_map.get(mv.name.upper())
        ann = annotations_map.get(mv.name.upper())
        dep_count = len(tr.dependencies) if tr else 0
        risk = _calculate_risk_level(dep_count)
        risk_emoji = "🔴" if risk in ("CRITICAL", "HIGH") else ("🟡" if risk == "MEDIUM" else "🟢")
        cols_str = f"{len(mv.columns)} cols"
        tags_str = f"`{', '.join(ann.tags)}`" if (ann and ann.tags) else "-"
        lines.append(
            f"| `{mv.name}` | MView | {risk_emoji} `{risk}` | {dep_count} | {cols_str} | {tags_str} | [View Details](mviews/{mv.name}.md) |"
        )

    for co in sorted(schema.code_objects, key=lambda x: x.name):
        tr = trace_map.get(co.name.upper())
        ann = annotations_map.get(co.name.upper())
        dep_count = len(tr.dependencies) if tr else 0
        risk = _calculate_risk_level(dep_count)
        risk_emoji = "🔴" if risk in ("CRITICAL", "HIGH") else ("🟡" if risk == "MEDIUM" else "🟢")
        obj_dir = co.object_type.lower().replace(" ", "_") + "s"
        subs_str = f"{len(co.subprograms)} routines" if co.subprograms else "PL/SQL Code"
        tags_str = f"`{', '.join(ann.tags)}`" if (ann and ann.tags) else "-"
        lines.append(
            f"| `{co.name}` | {co.object_type} | {risk_emoji} `{risk}` | {dep_count} | {subs_str} | {tags_str} | [View Details]({obj_dir}/{co.name}.md) |"
        )

    return "\n".join(lines)


def count_schema_objects(schema: SchemaMetadata, object_types: list[str] | None = None) -> int:
    allowed_types = {t.lower() for t in object_types} if object_types else None
    total = 0
    if _is_category_allowed("tables", allowed_types):
        total += len(schema.tables)
    if _is_category_allowed("views", allowed_types):
        total += len(schema.views)
    if _is_category_allowed("mviews", allowed_types):
        total += len(schema.mviews)
    if _is_category_allowed("triggers", allowed_types):
        total += len(schema.triggers)
    if _is_category_allowed("sequences", allowed_types):
        total += len(schema.sequences)
    if _is_category_allowed("indexes", allowed_types):
        total += len(schema.indexes)
    if _is_category_allowed("synonyms", allowed_types):
        total += len(schema.synonyms)
    for code_obj in schema.code_objects:
        if _is_code_obj_allowed(code_obj, allowed_types):
            total += 1 + len(code_obj.subprograms)
    return max(1, total)


def write_schema_docs(
    schema: SchemaMetadata,
    doc_path: Path,
    annotations_path: Path | None = None,
    object_types: list[str] | None = None,
    docs_overrides: dict[str, dict[str, str]] | None = None,
    multi_schema: bool = False,
    all_schemas: list[SchemaMetadata] | None = None,
    with_traces: bool = True,
    max_depth: int = 1,
    generate_rag_chunks: bool = False,
    progress_callback: Callable[[str, str, int, int], None] | None = None,
    target_object: str | None = None,
) -> tuple[list[Path], list[Path]]:
    try:
        max_depth = int(getattr(max_depth, "default", max_depth))
    except Exception:
        max_depth = 1
    if hasattr(with_traces, "default"):
        with_traces = bool(getattr(with_traces, "default", True))
    if hasattr(generate_rag_chunks, "default"):
        generate_rag_chunks = bool(getattr(generate_rag_chunks, "default", False))

    from leai.raw import RawDependencyIndex, trace_raw_dependencies, trace_subprogram_dependencies

    target_obj_up = target_object.strip().upper() if target_object else None
    target_clean_obj = target_obj_up
    if target_obj_up and "." in target_obj_up:
        s_part, o_part = target_obj_up.split(".", 1)
        if s_part == (schema.schema_name or "").upper():
            target_clean_obj = o_part

    def _matches_target(name: str) -> bool:
        if not target_clean_obj:
            return True
        up = name.upper()
        return up == target_clean_obj or up == target_obj_up

    target_doc_path = (doc_path / schema.schema_name) if (multi_schema and schema.schema_name) else doc_path
    base_ann = annotations_path or (doc_path.parent / "annotations")
    target_ann_path = (base_ann / schema.schema_name) if (multi_schema and schema.schema_name) else base_ann
    schemas_context = all_schemas or [schema]
    dep_index = RawDependencyIndex(schemas_context) if with_traces else None

    docs_overrides = docs_overrides or {}
    table_overrides = docs_overrides.get("tables", {})
    column_overrides_raw = docs_overrides.get("columns", {})
    normalized_column_overrides: dict[str, dict[str, str]] = {}
    for key, value in column_overrides_raw.items():
        if "." not in key:
            continue
        table_name, column_name = key.split(".", maxsplit=1)
        normalized_column_overrides.setdefault(table_name.upper(), {})[column_name.upper()] = value

    allowed_types = {t.lower() for t in object_types} if object_types else None
    generated_md: list[Path] = []
    generated_ann: list[Path] = []
    trace_map: dict[str, ObjectTraceResult] = {}
    annotations_map: dict[str, ObjectAnnotation] = {}

    total_objects = 1 if target_clean_obj else count_schema_objects(schema, object_types)
    processed_count = 0

    # 1. Tables
    if _is_category_allowed("tables", allowed_types):
        for table in schema.tables:
            if target_clean_obj and not _matches_target(table.name):
                continue
            processed_count += 1
            if progress_callback:
                progress_callback("Table", table.name, processed_count, total_objects)

            ann_path = target_ann_path / "tables" / f"{table.name}.yml"
            annotation = ensure_annotation_stub(ann_path, db_comment=table.comment, column_names=[c.name for c in table.columns])
            generated_ann.append(ann_path)
            annotations_map[table.name.upper()] = annotation

            tr = (
                trace_raw_dependencies(
                    schemas_context,
                    table.name,
                    max_depth=max_depth,
                    index=dep_index,
                    expected_type="TABLE",
                    schema_name=schema.schema_name,
                )
                if with_traces
                else None
            )
            if tr:
                trace_map[table.name.upper()] = tr

            file_path = target_doc_path / "tables" / f"{table.name}.md"
            existing = file_path.read_text(encoding="utf-8") if file_path.exists() else None
            manual_doc = _extract_manual_section(existing) or table_overrides.get(table.name, "")
            markdown = render_table_markdown(
                table,
                table_doc=manual_doc,
                column_docs=normalized_column_overrides.get(table.name, {}),
                annotation=annotation,
                trace_result=tr,
            )
            generated_md.append(_write_single_doc(file_path, markdown))

            if generate_rag_chunks and tr:
                chunk_file = target_doc_path / "chunks" / f"{table.name}.json"
                write_rag_json_file(tr, chunk_file, annotation=annotation)

    # 2. Views
    if _is_category_allowed("views", allowed_types):
        for view in schema.views:
            if target_clean_obj and not _matches_target(view.name):
                continue
            processed_count += 1
            if progress_callback:
                progress_callback("View", view.name, processed_count, total_objects)

            ann_path = target_ann_path / "views" / f"{view.name}.yml"
            annotation = ensure_annotation_stub(ann_path, db_comment=view.comment, column_names=[c.name for c in view.columns])
            generated_ann.append(ann_path)
            annotations_map[view.name.upper()] = annotation

            tr = (
                trace_raw_dependencies(
                    schemas_context,
                    view.name,
                    max_depth=max_depth,
                    index=dep_index,
                    expected_type="VIEW",
                    schema_name=schema.schema_name,
                )
                if with_traces
                else None
            )
            if tr:
                trace_map[view.name.upper()] = tr

            file_path = target_doc_path / "views" / f"{view.name}.md"
            existing = file_path.read_text(encoding="utf-8") if file_path.exists() else None
            manual_doc = _extract_manual_section(existing)
            markdown = render_view_markdown(
                view,
                view_doc=manual_doc,
                column_docs=normalized_column_overrides.get(view.name, {}),
                annotation=annotation,
                trace_result=tr,
            )
            generated_md.append(_write_single_doc(file_path, markdown))

            if generate_rag_chunks and tr:
                chunk_file = target_doc_path / "chunks" / f"{view.name}.json"
                write_rag_json_file(tr, chunk_file, annotation=annotation)

    # 3. Materialized Views
    if _is_category_allowed("mviews", allowed_types):
        for mview in schema.mviews:
            if target_clean_obj and not _matches_target(mview.name):
                continue
            processed_count += 1
            if progress_callback:
                progress_callback("MView", mview.name, processed_count, total_objects)

            ann_path = target_ann_path / "mviews" / f"{mview.name}.yml"
            annotation = ensure_annotation_stub(ann_path, db_comment=mview.comment, column_names=[c.name for c in mview.columns])
            generated_ann.append(ann_path)
            annotations_map[mview.name.upper()] = annotation

            tr = (
                trace_raw_dependencies(
                    schemas_context,
                    mview.name,
                    max_depth=max_depth,
                    index=dep_index,
                    expected_type="MATERIALIZED VIEW",
                    schema_name=schema.schema_name,
                )
                if with_traces
                else None
            )
            if tr:
                trace_map[mview.name.upper()] = tr

            file_path = target_doc_path / "mviews" / f"{mview.name}.md"
            existing = file_path.read_text(encoding="utf-8") if file_path.exists() else None
            manual_doc = _extract_manual_section(existing)
            markdown = render_mview_markdown(mview, mview_doc=manual_doc, annotation=annotation, trace_result=tr)
            generated_md.append(_write_single_doc(file_path, markdown))

            if generate_rag_chunks and tr:
                chunk_file = target_doc_path / "chunks" / f"{mview.name}.json"
                write_rag_json_file(tr, chunk_file, annotation=annotation)

    # 4. Code Objects (Procedures, Functions, Packages, Types)
    for code_obj in schema.code_objects:
        if not _is_code_obj_allowed(code_obj, allowed_types):
            continue
        if target_clean_obj and not (
            _matches_target(code_obj.name)
            or any(_matches_target(sub.name) or _matches_target(f"{code_obj.name}.{sub.name}") for sub in code_obj.subprograms)
        ):
            continue
        processed_count += 1
        if progress_callback:
            progress_callback(code_obj.object_type.title(), code_obj.name, processed_count, total_objects)

        obj_folder = code_obj.object_type.lower().replace(" ", "_") + "s"
        ann_path = target_ann_path / obj_folder / f"{code_obj.name}.yml"
        annotation = ensure_annotation_stub(ann_path, db_comment=code_obj.comment)
        generated_ann.append(ann_path)
        annotations_map[code_obj.name.upper()] = annotation

        tr = (
            trace_raw_dependencies(
                schemas_context,
                code_obj.name,
                max_depth=max_depth,
                index=dep_index,
                expected_type=code_obj.object_type,
                schema_name=schema.schema_name,
            )
            if with_traces
            else None
        )
        if tr:
            trace_map[code_obj.name.upper()] = tr

        file_path = target_doc_path / obj_folder / f"{code_obj.name}.md"
        existing = file_path.read_text(encoding="utf-8") if file_path.exists() else None
        manual_doc = _extract_manual_section(existing)
        markdown = render_code_object_markdown(code_obj, code_doc=manual_doc, annotation=annotation, trace_result=tr)
        generated_md.append(_write_single_doc(file_path, markdown))

        if generate_rag_chunks and tr:
            chunk_file = target_doc_path / "chunks" / f"{code_obj.name}.json"
            write_rag_json_file(tr, chunk_file, annotation=annotation)

        # Package Splitting (Subprogram disassembly)
        for sub in code_obj.subprograms:
            if target_clean_obj and not (_matches_target(sub.name) or _matches_target(f"{code_obj.name}.{sub.name}")):
                continue
            processed_count += 1
            if progress_callback:
                progress_callback("Routine", f"{code_obj.name}.{sub.name}", processed_count, total_objects)

            sub_ann_path = target_ann_path / obj_folder / code_obj.name / f"{sub.name}.yml"
            sub_annotation = ensure_annotation_stub(sub_ann_path, db_comment=sub.comment)
            generated_ann.append(sub_ann_path)

            sub_tr = trace_subprogram_dependencies(schemas_context, sub, index=dep_index) if with_traces else None

            sub_file_path = target_doc_path / obj_folder / code_obj.name / f"{sub.name}.md"
            sub_existing = sub_file_path.read_text(encoding="utf-8") if sub_file_path.exists() else None
            sub_manual = _extract_manual_section(sub_existing)
            sub_markdown = render_subprogram_markdown(sub, sub_doc=sub_manual, annotation=sub_annotation, trace_result=sub_tr)
            generated_md.append(_write_single_doc(sub_file_path, sub_markdown))

    # 5. Triggers
    if _is_category_allowed("triggers", allowed_types):
        for trigger in schema.triggers:
            if target_clean_obj and not _matches_target(trigger.name):
                continue
            processed_count += 1
            if progress_callback:
                progress_callback("Trigger", trigger.name, processed_count, total_objects)

            ann_path = target_ann_path / "triggers" / f"{trigger.name}.yml"
            annotation = ensure_annotation_stub(ann_path)
            generated_ann.append(ann_path)
            annotations_map[trigger.name.upper()] = annotation

            tr = (
                trace_raw_dependencies(
                    schemas_context,
                    trigger.name,
                    max_depth=max_depth,
                    index=dep_index,
                    expected_type="TRIGGER",
                    schema_name=schema.schema_name,
                )
                if with_traces
                else None
            )
            if tr:
                trace_map[trigger.name.upper()] = tr

            file_path = target_doc_path / "triggers" / f"{trigger.name}.md"
            existing = file_path.read_text(encoding="utf-8") if file_path.exists() else None
            manual_doc = _extract_manual_section(existing)
            markdown = render_trigger_markdown(trigger, trigger_doc=manual_doc, annotation=annotation, trace_result=tr)
            generated_md.append(_write_single_doc(file_path, markdown))

            if generate_rag_chunks and tr:
                chunk_file = target_doc_path / "chunks" / f"{trigger.name}.json"
                write_rag_json_file(tr, chunk_file, annotation=annotation)

    # 6. Sequences
    if _is_category_allowed("sequences", allowed_types):
        for sequence in schema.sequences:
            if target_clean_obj and not _matches_target(sequence.name):
                continue
            processed_count += 1
            if progress_callback:
                progress_callback("Sequence", sequence.name, processed_count, total_objects)

            ann_path = target_ann_path / "sequences" / f"{sequence.name}.yml"
            annotation = ensure_annotation_stub(ann_path)
            generated_ann.append(ann_path)

            file_path = target_doc_path / "sequences" / f"{sequence.name}.md"
            existing = file_path.read_text(encoding="utf-8") if file_path.exists() else None
            manual_doc = _extract_manual_section(existing)
            markdown = render_sequence_markdown(sequence, seq_doc=manual_doc, annotation=annotation)
            generated_md.append(_write_single_doc(file_path, markdown))

    # 7. Indexes
    if _is_category_allowed("indexes", allowed_types):
        for index in schema.indexes:
            if target_clean_obj and not _matches_target(index.name):
                continue
            processed_count += 1
            if progress_callback:
                progress_callback("Index", index.name, processed_count, total_objects)

            ann_path = target_ann_path / "indexes" / f"{index.name}.yml"
            annotation = ensure_annotation_stub(ann_path)
            generated_ann.append(ann_path)

            file_path = target_doc_path / "indexes" / f"{index.name}.md"
            existing = file_path.read_text(encoding="utf-8") if file_path.exists() else None
            manual_doc = _extract_manual_section(existing)
            markdown = render_index_markdown(index, idx_doc=manual_doc, annotation=annotation)
            generated_md.append(_write_single_doc(file_path, markdown))

    # 8. Synonyms
    if _is_category_allowed("synonyms", allowed_types):
        for synonym in schema.synonyms:
            if target_clean_obj and not _matches_target(synonym.name):
                continue
            processed_count += 1
            if progress_callback:
                progress_callback("Synonym", synonym.name, processed_count, total_objects)

            ann_path = target_ann_path / "synonyms" / f"{synonym.name}.yml"
            annotation = ensure_annotation_stub(ann_path)
            generated_ann.append(ann_path)

            file_path = target_doc_path / "synonyms" / f"{synonym.name}.md"
            existing = file_path.read_text(encoding="utf-8") if file_path.exists() else None
            manual_doc = _extract_manual_section(existing)
            markdown = render_synonym_markdown(synonym, syn_doc=manual_doc, annotation=annotation)
            generated_md.append(_write_single_doc(file_path, markdown))

    # 9. Schema Index & Risk Matrix (only when compiling entire schema)
    if not target_clean_obj:
        index_path = target_doc_path / "INDEX.md"
        index_md = render_schema_index_markdown(schema, trace_map=trace_map, annotations_map=annotations_map)
        generated_md.append(_write_single_doc(index_path, index_md))

    # 10. Global Business Glossary & Domain Rules
    gloss_file = write_glossary_doc(annotations_path, doc_path)
    if gloss_file:
        generated_md.append(gloss_file)

    return generated_md, generated_ann


def write_table_docs(tables: list[TableMeta], doc_path: Path, docs_overrides: dict[str, dict[str, str]] | None = None) -> list[Path]:
    schema = SchemaMetadata(tables=tables)
    generated_md, _ = write_schema_docs(schema, doc_path, docs_overrides=docs_overrides)
    return generated_md


def sync_schema_annotations(
    schema: SchemaMetadata,
    annotations_path: Path,
    multi_schema: bool = False,
    object_types: list[str] | None = None,
    progress_callback: Callable[[str, str, int, int], None] | None = None,
    storage: Any = None,
) -> list[Path]:
    target_ann_path = (annotations_path / schema.schema_name) if (multi_schema and schema.schema_name) else annotations_path
    allowed_types = {t.lower() for t in object_types} if object_types else None
    generated_ann: list[Path] = []

    total_objects = count_schema_objects(schema, object_types)
    processed_count = 0
    s_name = schema.schema_name or ""

    if _is_category_allowed("tables", allowed_types):
        for table in schema.tables:
            processed_count += 1
            if progress_callback:
                progress_callback("Table", table.name, processed_count, total_objects)

            ann_path = target_ann_path / "tables" / f"{table.name}.yml"
            ensure_annotation_stub(
                ann_path,
                db_comment=table.comment,
                column_names=[c.name for c in table.columns],
                storage=storage,
                schema_name=s_name,
                obj_folder="tables",
                obj_name=table.name,
            )
            generated_ann.append(ann_path)

    if _is_category_allowed("views", allowed_types):
        for view in schema.views:
            processed_count += 1
            if progress_callback:
                progress_callback("View", view.name, processed_count, total_objects)

            ann_path = target_ann_path / "views" / f"{view.name}.yml"
            ensure_annotation_stub(
                ann_path,
                db_comment=view.comment,
                column_names=[c.name for c in view.columns],
                storage=storage,
                schema_name=s_name,
                obj_folder="views",
                obj_name=view.name,
            )
            generated_ann.append(ann_path)

    if _is_category_allowed("mviews", allowed_types):
        for mview in schema.mviews:
            processed_count += 1
            if progress_callback:
                progress_callback("MView", mview.name, processed_count, total_objects)

            ann_path = target_ann_path / "mviews" / f"{mview.name}.yml"
            ensure_annotation_stub(
                ann_path,
                db_comment=mview.comment,
                column_names=[c.name for c in mview.columns],
                storage=storage,
                schema_name=s_name,
                obj_folder="mviews",
                obj_name=mview.name,
            )
            generated_ann.append(ann_path)

    for code_obj in schema.code_objects:
        if not _is_code_obj_allowed(code_obj, allowed_types):
            continue
        processed_count += 1
        if progress_callback:
            progress_callback(code_obj.object_type.title(), code_obj.name, processed_count, total_objects)

        obj_folder = code_obj.object_type.lower().replace(" ", "_") + "s"
        ann_path = target_ann_path / obj_folder / f"{code_obj.name}.yml"
        ensure_annotation_stub(
            ann_path,
            db_comment=code_obj.comment,
            storage=storage,
            schema_name=s_name,
            obj_folder=obj_folder,
            obj_name=code_obj.name,
        )
        generated_ann.append(ann_path)

        for sub in code_obj.subprograms:
            processed_count += 1
            if progress_callback:
                progress_callback("Routine", f"{code_obj.name}.{sub.name}", processed_count, total_objects)

            sub_ann_path = target_ann_path / obj_folder / code_obj.name / f"{sub.name}.yml"
            ensure_annotation_stub(
                sub_ann_path,
                db_comment=sub.comment,
                storage=storage,
                schema_name=s_name,
                obj_folder=f"{obj_folder}/{code_obj.name}",
                obj_name=sub.name,
            )
            generated_ann.append(sub_ann_path)

    if _is_category_allowed("triggers", allowed_types):
        for trigger in schema.triggers:
            processed_count += 1
            if progress_callback:
                progress_callback("Trigger", trigger.name, processed_count, total_objects)

            ann_path = target_ann_path / "triggers" / f"{trigger.name}.yml"
            ensure_annotation_stub(
                ann_path,
                storage=storage,
                schema_name=s_name,
                obj_folder="triggers",
                obj_name=trigger.name,
            )
            generated_ann.append(ann_path)

    if _is_category_allowed("sequences", allowed_types):
        for sequence in schema.sequences:
            processed_count += 1
            if progress_callback:
                progress_callback("Sequence", sequence.name, processed_count, total_objects)

            ann_path = target_ann_path / "sequences" / f"{sequence.name}.yml"
            ensure_annotation_stub(
                ann_path,
                storage=storage,
                schema_name=s_name,
                obj_folder="sequences",
                obj_name=sequence.name,
            )
            generated_ann.append(ann_path)

    if _is_category_allowed("indexes", allowed_types):
        for index in schema.indexes:
            processed_count += 1
            if progress_callback:
                progress_callback("Index", index.name, processed_count, total_objects)

            ann_path = target_ann_path / "indexes" / f"{index.name}.yml"
            ensure_annotation_stub(
                ann_path,
                storage=storage,
                schema_name=s_name,
                obj_folder="indexes",
                obj_name=index.name,
            )
            generated_ann.append(ann_path)

    if _is_category_allowed("synonyms", allowed_types):
        for synonym in schema.synonyms:
            processed_count += 1
            if progress_callback:
                progress_callback("Synonym", synonym.name, processed_count, total_objects)

            ann_path = target_ann_path / "synonyms" / f"{synonym.name}.yml"
            ensure_annotation_stub(
                ann_path,
                storage=storage,
                schema_name=s_name,
                obj_folder="synonyms",
                obj_name=synonym.name,
            )
            generated_ann.append(ann_path)

    return generated_ann


def generate_rag_json(trace_result: ObjectTraceResult, annotation: ObjectAnnotation | None = None) -> dict:
    focal_name = trace_result.focal_name
    focal_type = trace_result.focal_type
    focal_obj = trace_result.focal_object
    risk = _calculate_risk_level(len(trace_result.dependencies))
    semantic_text = generate_semantic_rag_text(trace_result, annotation=annotation)

    columns_info = []
    pks = []
    fks = []
    if isinstance(focal_obj, TableMeta):
        columns_info = [{"name": c.name, "type": c.data_type, "nullable": c.nullable, "comment": c.comment} for c in focal_obj.columns]
        pks = focal_obj.primary_keys
        fks = [
            {"name": fk.name, "column": fk.column, "referenced_table": fk.referenced_table, "referenced_column": fk.referenced_column}
            for fk in focal_obj.foreign_keys
        ]

    deps_info = [
        {
            "depth": d.depth,
            "source_name": d.source_name,
            "source_type": d.source_type,
            "target_name": d.target_name,
            "target_type": d.target_type,
            "relation_type": d.relation_type,
            "details": d.details,
        }
        for d in trace_result.dependencies
    ]

    return {
        "chunk_id": f"trace_{focal_name.lower()}",
        "entity": focal_name,
        "type": focal_type,
        "risk_level": risk,
        "tags": annotation.tags if annotation else [],
        "use_cases": annotation.use_cases if annotation else [],
        "text_for_embedding": semantic_text,
        "schema_context": {
            "columns": columns_info,
            "primary_keys": pks,
            "foreign_keys": fks,
            "dependencies": deps_info,
        },
    }


def write_glossary_doc(annotations_path: Path, doc_path: Path) -> Path | None:
    """Generates docs/GLOSSARY.md summarizing global business rules and canonical filters."""
    try:
        from leai.glossary import load_glossary

        glossary = load_glossary(annotations_path)
        out_file = doc_path / "GLOSSARY.md"
        if not glossary.terms:
            if out_file.exists():
                try:
                    out_file.unlink()
                except Exception:
                    pass
            return None

        lines = [
            "# Business Glossary & Canonical Domain Rules",
            "",
            "> [!NOTE]",
            "> This document defines the organizational business rules, domain terms, and canonical SQL filters",
            "> governing the database schema. These definitions are consumed by humans and the LEAI AI Copilot.",
            "",
            "## Summary of Terms",
            "",
            "| Business Term | Primary Table | Canonical SQL Filter | Tags |",
            "| :--- | :--- | :--- | :--- |",
        ]

        for t in glossary.terms:
            tbl = f"`{t.primary_table}`" if t.primary_table else "*-*"
            filt = f"`{t.canonical_filter}`" if t.canonical_filter else "*-*"
            tags = ", ".join(f"`{tag}`" for tag in t.tags) if t.tags else "*-*"
            lines.append(f"| **{t.term}** | {tbl} | {filt} | {tags} |")

        lines.extend(["", "---", "", "## Detailed Business Rules", ""])

        for t in glossary.terms:
            lines.append(f"### 📖 {t.term}")
            lines.append(f"**Definition:** {t.definition}")
            lines.append("")
            if t.primary_table:
                lines.append(f"- **Primary Table:** `{t.primary_table}`")
            if t.related_tables:
                lines.append(f"- **Related Tables:** {', '.join(f'`{rt}`' for rt in t.related_tables)}")
            if t.canonical_filter:
                lines.append("- **Canonical SQL Filter:**")
                lines.append("```sql")
                lines.append(t.canonical_filter)
                lines.append("```")
            if t.tags:
                lines.append(f"- **Tags:** {', '.join(f'`{tag}`' for tag in t.tags)}")
            if t.examples:
                lines.append("- **Examples / Scenarios:**")
                for ex in t.examples:
                    lines.append(f"  - {ex}")
            lines.append("")

        out_file = doc_path / "GLOSSARY.md"
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text("\n".join(lines), encoding="utf-8")
        return out_file
    except Exception:
        return None


def write_rag_json_file(
    trace_result: ObjectTraceResult,
    output_path: Path,
    annotations_path: Path | None = None,
    annotation: ObjectAnnotation | None = None,
) -> Path:
    if annotation is None:
        base_ann = annotations_path or (output_path.parent.parent / "annotations")
        ann_path = base_ann / "dossiers" / f"{trace_result.focal_name}.yml"
        annotation = ensure_annotation_stub(ann_path)

    data = generate_rag_json(trace_result, annotation=annotation)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return output_path


def render_dossier_markdown(
    trace_result: ObjectTraceResult,
    annotation: ObjectAnnotation | None = None,
    manual_doc: str = "",
) -> str:
    focal_name = trace_result.focal_name
    focal_type = trace_result.focal_type
    focal_obj = trace_result.focal_object
    dep_count = len(trace_result.dependencies)
    risk_level = _calculate_risk_level(dep_count)

    parents = [d.target_name for d in trace_result.dependencies if d.relation_type in ("FK_REFERENCES", "DEPENDS_ON")]
    children = [d.source_name for d in trace_result.dependencies if d.relation_type == "FK_REFERENCED_BY"]
    consumers = [
        d.source_name
        for d in trace_result.dependencies
        if d.relation_type in ("READS/SELECTS", "PLSQL_DEPENDENCY", "TRIGGER_ON", "REFERENCED_BY")
    ]

    # 1. YAML Frontmatter for RAG / LLM
    import yaml

    rag_meta = {
        "rag_metadata": {
            "entity": focal_name,
            "type": focal_type,
            "risk_level": risk_level,
            "tags": annotation.tags if annotation else [],
            "use_cases": annotation.use_cases if annotation else [],
            "impact_summary": {
                "total_connections": dep_count,
                "upstream_parents": list(set(parents)),
                "downstream_children": list(set(children)),
                "consumers": list(set(consumers)),
            },
        }
    }
    yaml_frontmatter = yaml.safe_dump(rag_meta, sort_keys=False, allow_unicode=True).strip()

    lines = [
        "---",
        yaml_frontmatter,
        "---",
        "",
        f"# TECHNICAL IMPACT & FOCAL DOCUMENTATION DOSSIER: {focal_name}",
        "",
        f"**Object Type:** `{focal_type}`",
    ]

    if focal_obj:
        lines.extend(_render_audit_meta(focal_obj))

    # 2. Executive Summary Card / Impact X-Ray
    risk_badge_color = "CRITICAL" if risk_level == "CRITICAL" else ("WARNING" if risk_level in ("HIGH", "MEDIUM") else "NOTE")
    lines.extend(
        [
            f"> [!{risk_badge_color}]",
            "> **Technical Impact X-Ray:**",
            f"> - **Change Risk Level:** `{risk_level}` ({dep_count} graph connections)",
            f"> - **Parent Tables (Upstream):** `{len(set(parents))}` | **Child Tables (Downstream):** `{len(set(children))}`",
            f"> - **Active Consumers (Views/Procs/Triggers):** `{len(set(consumers))}`",
            "",
        ]
    )

    desc = (
        (annotation and annotation.description)
        or getattr(focal_obj, "comment", None)
        or f"Detailed analysis and technical lineage tracking for object `{focal_name}`."
    )
    lines.extend(["## Business Overview", "", desc])
    lines.extend(_render_business_rules(annotation))

    # 3. Semantic Narrative Summary (RAG Ready)
    semantic_text = generate_semantic_rag_text(trace_result, annotation=annotation)
    lines.extend(["", "## 🧠 Semantic Narrative Summary (RAG Ready)", "", semantic_text])

    # 4. Mermaid Lineage Graph
    lines.extend(["", "## Lineage & Relationship Graph", ""])
    if trace_result.dependencies:
        lines.append(generate_mermaid_graph(focal_name, trace_result.dependencies))
    else:
        lines.append("*No direct dependencies identified in snapshot/catalog.*")

    # 5. Dependency Table
    lines.extend(["", "## Dependency & Impact Map", ""])
    if trace_result.dependencies:
        lines.append("| Level | Source Object | Type | Relation | Target Object | Type | Details |")
        lines.append("|---|---|---|---|---|---|---|")
        for dep in sorted(trace_result.dependencies, key=lambda d: (d.depth, d.source_name)):
            lines.append(
                f"| **Level {dep.depth}** | `{dep.source_name}` | {dep.source_type} | `{dep.relation_type}` | `{dep.target_name}` | {dep.target_type} | {dep.details or ''} |"
            )
    else:
        lines.append("No recorded dependencies.")

    # 6. Focal Object Details
    if isinstance(focal_obj, TableMeta):
        lines.extend(
            ["", "## Focal Object Column Structure", "", "| Column | Type | Nullable | Default | Comment |", "|---|---|---|---|---|"]
        )
        ann_cols = annotation.columns if annotation else {}
        for col in focal_obj.columns:
            comm = ann_cols.get(col.name) or col.comment or ""
            lines.append(f"| {col.name} | {col.data_type} | {'YES' if col.nullable else 'NO'} | {col.default or ''} | {comm} |")

        lines.extend(["", "### Primary Keys", ", ".join(focal_obj.primary_keys) if focal_obj.primary_keys else "Not defined"])
        lines.extend(["", "### Outbound Foreign Keys"])
        if focal_obj.foreign_keys:
            for fk in focal_obj.foreign_keys:
                lines.append(f"- `{fk.name}`: Column `{fk.column}` points to `{fk.referenced_table}.{fk.referenced_column}`")
        else:
            lines.append("None")
    elif isinstance(focal_obj, ViewMeta) and focal_obj.text:
        lines.extend(["", "## View SQL Definition", "```sql", focal_obj.text.strip(), "```"])
    elif isinstance(focal_obj, CodeObjectMeta) and focal_obj.source:
        lines.extend(["", "## PL/SQL Source Code", "```sql", focal_obj.source.strip(), "```"])

    # 7. Related Objects Details
    if trace_result.related_tables or trace_result.related_views or trace_result.related_code_objects or trace_result.related_triggers:
        lines.extend(["", "## Related Objects Details", ""])

        if trace_result.related_tables:
            lines.append("### 📊 Connected Tables")
            for t in trace_result.related_tables:
                lines.append(f"- **`{t.name}`**: {len(t.columns)} columns, {len(t.foreign_keys)} FKs ({t.comment or 'No comment'})")

        if trace_result.related_views:
            lines.append("")
            lines.append("### 👁️ Connected Views")
            for v in trace_result.related_views:
                lines.append(f"- **`{v.name}`**: {len(v.columns)} columns ({v.comment or 'No comment'})")

        if trace_result.related_triggers:
            lines.append("")
            lines.append("### ⚡ Connected Triggers")
            for trg in trace_result.related_triggers:
                lines.append(f"- **`{trg.name}`** (Trigger: `{trg.trigger_type} {trg.triggering_event}` on table `{trg.table_name}`)")

        if trace_result.related_code_objects:
            lines.append("")
            lines.append("### ⚙️ Connected Packages / Procedures / Functions")
            for co in trace_result.related_code_objects:
                lines.append(f"- **`{co.name}`** ({co.object_type})")

    lines.extend(_render_manual_section(manual_doc))
    return "\n".join(lines)


def write_dossier_doc(
    trace_result: ObjectTraceResult,
    output_path: Path,
    annotations_path: Path | None = None,
) -> Path:
    base_ann = annotations_path or (output_path.parent.parent / "annotations")
    ann_path = base_ann / "dossiers" / f"{trace_result.focal_name}.yml"
    annotation = ensure_annotation_stub(ann_path)

    existing = output_path.read_text(encoding="utf-8") if output_path.exists() else None
    manual_doc = _extract_manual_section(existing)

    markdown = render_dossier_markdown(trace_result, annotation=annotation, manual_doc=manual_doc)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")
    return output_path
