from __future__ import annotations

import re
from typing import Any

from leai.annotations import load_annotation
from leai.compression import (
    compact_schema_notation,
    extract_package_skeleton,
    extract_subprogram_block,
    minify_plsql_source,
)
from leai.config import LeaiConfig
from leai.docs import render_dossier_markdown
from leai.models import CodeObjectMeta, SchemaMetadata
from leai.raw import trace_raw_dependencies


def extract_entities_from_question(
    question: str,
    available_objects: set[str],
    top_level_objects: set[str] | None = None,
) -> list[str]:
    """Identifies database object names present in the user question strictly via explicit @ mentions."""
    if not question:
        return []

    # Check for explicit @mentions (e.g. @FUNCIONARIOS, @ERGON.FUNCIONARIOS, @PCK_FOLHA.CALCULA)
    # The focal RAG context is generated strictly when the user explicitly selects/mentions an object with @.
    explicit_mentions = re.findall(r"@([A-Za-z0-9_$#]+(?:\.[A-Za-z0-9_$#]+)?)", question)
    if not explicit_mentions:
        return []

    found_mentions: list[str] = []
    for m in explicit_mentions:
        m_up = m.strip().upper()
        candidate = m_up
        if "." in m_up:
            parts = m_up.split(".")
            # Check if second part (e.g. TABLE from SCHEMA.TABLE) or full qualified name matches
            if parts[1] in available_objects:
                candidate = parts[1]
            elif m_up in available_objects:
                candidate = m_up
        if candidate in available_objects and candidate not in found_mentions:
            found_mentions.append(candidate)

    return found_mentions


def build_rag_context(
    question: str,
    schemas: list[SchemaMetadata],
    config: LeaiConfig,
    include_catalog: bool = True,
) -> tuple[str, list[str]]:
    """Builds the contextual RAG payload combining compressed schema overview and detailed trace with PL/SQL minification."""
    # 1. Map all available object names, subprograms, and synonyms
    all_objects = set()
    top_level_objects = set()
    subprogram_to_package_map: dict[str, tuple[CodeObjectMeta, Any]] = {}
    synonym_map = {}

    for s in schemas:
        for t in s.tables:
            t_name = t.name.upper()
            top_level_objects.add(t_name)
            all_objects.add(t_name)
        for v in s.views:
            v_name = v.name.upper()
            top_level_objects.add(v_name)
            all_objects.add(v_name)
        for mv in s.mviews:
            mv_name = mv.name.upper()
            top_level_objects.add(mv_name)
            all_objects.add(mv_name)
        for co in s.code_objects:
            co_name = co.name.upper()
            top_level_objects.add(co_name)
            all_objects.add(co_name)
            for sp in co.subprograms:
                sp_name = sp.name.upper()
                all_objects.add(sp_name)
                # Only map unqualified subprogram if it does not collide with a top-level object
                if sp_name not in top_level_objects:
                    subprogram_to_package_map[sp_name] = (co, sp)
                # Always support qualified subprogram lookup PACKAGE.SUBPROGRAM
                subprogram_to_package_map[f"{co_name}.{sp_name}"] = (co, sp)
                all_objects.add(f"{co_name}.{sp_name}")
        for trg in s.triggers:
            trg_name = trg.name.upper()
            top_level_objects.add(trg_name)
            all_objects.add(trg_name)
        for syn in s.synonyms:
            syn_name = syn.name.upper()
            top_level_objects.add(syn_name)
            all_objects.add(syn_name)
            synonym_map[syn_name] = syn

    detected_entities = extract_entities_from_question(
        question,
        all_objects,
        top_level_objects=top_level_objects,
    )

    context_parts = []

    # 2. If internal subprograms were detected (and are not top-level objects), surgically extract their code block
    for entity in detected_entities:
        if entity in subprogram_to_package_map and entity not in top_level_objects:
            co, sp = subprogram_to_package_map[entity]
            sub_name = entity.split(".")[-1] if "." in entity else entity
            sub_block = extract_subprogram_block(co.source, sub_name)
            if sub_block:
                skeleton = extract_package_skeleton(co.source, max_signatures=15)
                context_parts.append(
                    f"### [FOCAL PL/SQL SUBPROGRAM: {entity} (PACKAGE {co.name})]\n"
                    f"{skeleton}\n\n"
                    f"MINIFIED SOURCE CODE OF REQUESTED SUBPROGRAM:\n```sql\n{sub_block}\n```"
                )

    # 3. If primary entities are detected, generate the trace and contextual dossier
    if detected_entities:
        context_parts.append("### [RAG CONTEXT] TECHNICAL IMPACT & LINEAGE DOSSIER OF FOCAL ENTITIES:")
        for entity in detected_entities[:2]:  # Limit to max 2 focal entities for pristine prompt focus
            # If the entity is a subprogram not in top_level_objects, trace its parent package
            if entity in subprogram_to_package_map and entity not in top_level_objects:
                target_trace = subprogram_to_package_map[entity][0].name
            else:
                target_trace = entity

            trace_res = trace_raw_dependencies(schemas, target_trace, max_depth=1)

            if trace_res.focal_object or trace_res.focal_type != "UNKNOWN":
                # Minify PL/SQL source code if it is a code object
                if isinstance(trace_res.focal_object, CodeObjectMeta) and trace_res.focal_object.source:
                    trace_res.focal_object.source = minify_plsql_source(trace_res.focal_object.source)[:3000]

                # Cap relationships to avoid blowing through LLM token quotas on core enterprise tables
                if len(trace_res.dependencies) > 20:
                    trace_res.dependencies = trace_res.dependencies[:20]
                if len(trace_res.related_tables) > 10:
                    trace_res.related_tables = trace_res.related_tables[:10]
                if len(trace_res.related_views) > 10:
                    trace_res.related_views = trace_res.related_views[:10]
                if len(trace_res.related_code_objects) > 10:
                    trace_res.related_code_objects = trace_res.related_code_objects[:10]

                # Try loading existing annotation (local or SeaweedFS remote)
                is_multi = len(schemas) > 1 or config.is_all_schemas
                schema_name = getattr(trace_res.focal_object, "schema_name", None) or (schemas[0].schema_name if schemas else "")
                storage = None
                if getattr(getattr(config, "storage", None), "seaweedfs", None):
                    sw = config.storage.seaweedfs
                    if getattr(sw, "enabled", False) or getattr(sw, "endpoint_url", None):
                        try:
                            from leai.storage import SeaweedFSStorage

                            storage = SeaweedFSStorage(sw)
                        except Exception:
                            storage = None

                focal_folder = "tables"
                focal_type = getattr(trace_res, "focal_type", "").upper()
                if "VIEW" in focal_type:
                    focal_folder = "views"
                elif any(k in focal_type for k in ("PACKAGE", "PROCEDURE", "FUNCTION")):
                    focal_folder = "packages"

                ann_dir = config.annotationsPath / schema_name if is_multi else config.annotationsPath
                ann_path = ann_dir / focal_folder / f"{target_trace}.yml"
                if not ann_path.exists():
                    ann_path_dossier = ann_dir / "dossiers" / f"{target_trace}.yml"
                    if ann_path_dossier.exists():
                        ann_path = ann_path_dossier

                ann = (
                    load_annotation(
                        ann_path,
                        storage=storage,
                        schema_name=schema_name,
                        obj_folder=focal_folder,
                        obj_name=target_trace,
                    )
                    if (ann_path.exists() or storage)
                    else None
                )

                # Render dossier in Markdown with Mermaid and Frontmatter (up to 8,000 chars preserved)
                dossier_text = render_dossier_markdown(trace_res, annotation=ann)
                if len(dossier_text) > 8000:
                    dossier_text = (
                        dossier_text[:8000] + "\n\n*(...dossier summary truncated for RAG context. Use tools to query further details.)*"
                    )
                context_parts.append(
                    f"\n--- START OF FOCAL DOSSIER: {target_trace} ---\n{dossier_text}\n--- END OF FOCAL DOSSIER: {target_trace} ---"
                )

    # 4. Add high-level macro catalog summary in compact notation (only if requested, e.g. initial turn)
    if include_catalog:
        context_parts.append("\n### [COMPACT SCHEMA CATALOG]")
        for s in schemas:
            compact_text = compact_schema_notation(s, max_tables=25)
            context_parts.append(compact_text)

    full_context = "\n\n".join(context_parts)
    return full_context, detected_entities
