from __future__ import annotations

import re

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


def extract_entities_from_question(question: str, available_objects: set[str]) -> list[str]:
    """Identifies database object names present in the user question."""
    found = []
    # Sort in descending length order to prioritize longer/more specific names (e.g. PKG_PAYROLL_PROCESSING before PKG_PAYROLL)
    sorted_candidates = sorted(available_objects, key=len, reverse=True)

    for obj_name in sorted_candidates:
        if len(obj_name) < 2:
            continue
        pattern = rf"\b{re.escape(obj_name)}\b"
        if re.search(pattern, question, re.IGNORECASE):
            found.append(obj_name)
    return found


def build_rag_context(
    question: str,
    schemas: list[SchemaMetadata],
    config: LeaiConfig,
) -> tuple[str, list[str]]:
    """Builds the contextual RAG payload combining compressed schema overview and detailed trace with PL/SQL minification."""
    # 1. Map all available object names, subprograms, and synonyms
    all_objects = set()
    subprogram_to_package_map = {}
    synonym_map = {}

    for s in schemas:
        for t in s.tables:
            all_objects.add(t.name.upper())
        for v in s.views:
            all_objects.add(v.name.upper())
        for mv in s.mviews:
            all_objects.add(mv.name.upper())
        for co in s.code_objects:
            co_name = co.name.upper()
            all_objects.add(co_name)
            for sp in co.subprograms:
                sp_name = sp.name.upper()
                all_objects.add(sp_name)
                subprogram_to_package_map[sp_name] = (co, sp)
        for trg in s.triggers:
            all_objects.add(trg.name.upper())
        for syn in s.synonyms:
            syn_name = syn.name.upper()
            all_objects.add(syn_name)
            synonym_map[syn_name] = syn

    detected_entities = extract_entities_from_question(question, all_objects)

    context_parts = []

    # 2. If internal subprograms were detected, surgically extract their code block
    for entity in detected_entities:
        if entity in subprogram_to_package_map:
            co, sp = subprogram_to_package_map[entity]
            sub_block = extract_subprogram_block(co.source, entity)
            if sub_block:
                skeleton = extract_package_skeleton(co.source)
                context_parts.append(
                    f"### [SUBPROGRAMA PL/SQL FOCAL: {entity} (PACOTE {co.name})]\n"
                    f"{skeleton}\n\n"
                    f"CÓDIGO-FONTE MINIFICADO DO SUBPROGRAMA REQUISITADO:\n```sql\n{sub_block}\n```"
                )

    # 3. If primary entities are detected, generate the trace and contextual dossier
    if detected_entities:
        context_parts.append("### [RAG CONTEXT] DETALHAMENTO DE IMPACTO E LINHAGEM TÉCNICA DAS ENTIDADES FOCAIS:")
        for entity in detected_entities[:3]:  # Limit to 3 entities to avoid context overflow
            # If the entity is a subprogram, trace its parent package
            target_trace = subprogram_to_package_map[entity][0].name if entity in subprogram_to_package_map else entity
            trace_res = trace_raw_dependencies(schemas, target_trace, max_depth=2)

            if trace_res.focal_object or trace_res.focal_type != "UNKNOWN":
                # Minify PL/SQL source code if it is a code object
                if isinstance(trace_res.focal_object, CodeObjectMeta) and trace_res.focal_object.source:
                    trace_res.focal_object.source = minify_plsql_source(trace_res.focal_object.source)[:6000]

                # Try loading existing annotation
                is_multi = len(schemas) > 1 or config.is_all_schemas
                schema_name = getattr(trace_res.focal_object, "schema_name", None) or (schemas[0].schema_name if schemas else "")
                ann_dir = config.annotationsPath / schema_name if is_multi else config.annotationsPath
                ann_path = ann_dir / "dossiers" / f"{target_trace}.yml"
                ann = load_annotation(ann_path) if ann_path.exists() else None

                # Render dossier in Markdown with Mermaid and Frontmatter
                dossier_text = render_dossier_markdown(trace_res, annotation=ann)
                context_parts.append(f"\n--- INÍCIO DO DOSSIÊ FOCAL: {target_trace} ---\n{dossier_text}\n--- FIM DO DOSSIÊ FOCAL: {target_trace} ---")

    # 4. Add high-level macro catalog summary in compact notation (low token consumption)
    context_parts.append("\n### [CATÁLOGO COMPACTO DO SCHEMA]")
    for s in schemas:
        compact_text = compact_schema_notation(s, max_tables=50)
        context_parts.append(compact_text)

    full_context = "\n\n".join(context_parts)
    return full_context, detected_entities

