from __future__ import annotations

import json
from pathlib import Path

from leai.models import (
    CodeObjectMeta,
    IndexMeta,
    MaterializedViewMeta,
    SchemaMetadata,
    SequenceMeta,
    SynonymMeta,
    TableMeta,
    TriggerMeta,
    ViewMeta,
)


def save_raw_schema(schema: SchemaMetadata, raw_path: Path, multi_schema: bool = False) -> list[Path]:
    target_path = (raw_path / schema.schema_name) if (multi_schema and schema.schema_name) else raw_path
    target_path.mkdir(parents=True, exist_ok=True)
    saved_files: list[Path] = []

    def _write_json(file_path: Path, data: dict) -> Path:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return file_path

    # 1. Tables
    for table in schema.tables:
        p = target_path / "tables" / f"{table.name}.json"
        saved_files.append(_write_json(p, table.model_dump()))

    # 2. Views
    for view in schema.views:
        p = target_path / "views" / f"{view.name}.json"
        saved_files.append(_write_json(p, view.model_dump()))

    # 3. Materialized Views
    for mview in schema.mviews:
        p = target_path / "mviews" / f"{mview.name}.json"
        saved_files.append(_write_json(p, mview.model_dump()))

    # 4. Code Objects
    for code_obj in schema.code_objects:
        obj_folder = code_obj.object_type.lower().replace(" ", "_") + "s"
        p = target_path / obj_folder / f"{code_obj.name}.json"
        saved_files.append(_write_json(p, code_obj.model_dump()))

    # 5. Triggers
    for trigger in schema.triggers:
        p = target_path / "triggers" / f"{trigger.name}.json"
        saved_files.append(_write_json(p, trigger.model_dump()))

    # 6. Sequences
    for sequence in schema.sequences:
        p = target_path / "sequences" / f"{sequence.name}.json"
        saved_files.append(_write_json(p, sequence.model_dump()))

    # 7. Indexes
    for index in schema.indexes:
        p = target_path / "indexes" / f"{index.name}.json"
        saved_files.append(_write_json(p, index.model_dump()))

    # 8. Synonyms
    for synonym in schema.synonyms:
        p = target_path / "synonyms" / f"{synonym.name}.json"
        saved_files.append(_write_json(p, synonym.model_dump()))

    return saved_files


def load_raw_schema(raw_path: Path, schema_name: str = "") -> SchemaMetadata:
    schema = SchemaMetadata(schema_name=schema_name)
    if not raw_path.exists():
        return schema

    # 1. Tables
    tables_dir = raw_path / "tables"
    if tables_dir.exists():
        for p in sorted(tables_dir.glob("*.json")):
            raw_data = json.loads(p.read_text(encoding="utf-8"))
            schema.tables.append(TableMeta.model_validate(raw_data))

    # 2. Views
    views_dir = raw_path / "views"
    if views_dir.exists():
        for p in sorted(views_dir.glob("*.json")):
            raw_data = json.loads(p.read_text(encoding="utf-8"))
            schema.views.append(ViewMeta.model_validate(raw_data))

    # 3. Materialized Views
    mviews_dir = raw_path / "mviews"
    if mviews_dir.exists():
        for p in sorted(mviews_dir.glob("*.json")):
            raw_data = json.loads(p.read_text(encoding="utf-8"))
            schema.mviews.append(MaterializedViewMeta.model_validate(raw_data))

    # 4. Code Objects
    for folder_name in ["procedures", "functions", "packages", "package_bodys", "types", "type_bodys"]:
        code_dir = raw_path / folder_name
        if code_dir.exists():
            for p in sorted(code_dir.glob("*.json")):
                raw_data = json.loads(p.read_text(encoding="utf-8"))
                schema.code_objects.append(CodeObjectMeta.model_validate(raw_data))

    # 5. Triggers
    trig_dir = raw_path / "triggers"
    if trig_dir.exists():
        for p in sorted(trig_dir.glob("*.json")):
            raw_data = json.loads(p.read_text(encoding="utf-8"))
            schema.triggers.append(TriggerMeta.model_validate(raw_data))

    # 6. Sequences
    seq_dir = raw_path / "sequences"
    if seq_dir.exists():
        for p in sorted(seq_dir.glob("*.json")):
            raw_data = json.loads(p.read_text(encoding="utf-8"))
            schema.sequences.append(SequenceMeta.model_validate(raw_data))

    # 7. Indexes
    idx_dir = raw_path / "indexes"
    if idx_dir.exists():
        for p in sorted(idx_dir.glob("*.json")):
            raw_data = json.loads(p.read_text(encoding="utf-8"))
            schema.indexes.append(IndexMeta.model_validate(raw_data))

    # 8. Synonyms
    syn_dir = raw_path / "synonyms"
    if syn_dir.exists():
        for p in sorted(syn_dir.glob("*.json")):
            raw_data = json.loads(p.read_text(encoding="utf-8"))
            schema.synonyms.append(SynonymMeta.model_validate(raw_data))

    return schema


def load_raw_schemas(raw_path: Path) -> list[SchemaMetadata]:
    if not raw_path.exists():
        return []

    # Verificar se raw_path contém subpastas que representam schemas
    subdirs = [d for d in raw_path.iterdir() if d.is_dir() and d.name not in {
        "tables", "views", "mviews", "procedures", "functions", "packages", "package_bodys", "types", "type_bodys", "triggers", "sequences", "indexes", "synonyms"
    }]

    if subdirs:
        schemas: list[SchemaMetadata] = []
        for d in sorted(subdirs, key=lambda x: x.name):
            schemas.append(load_raw_schema(d, schema_name=d.name))
        return schemas

    return [load_raw_schema(raw_path)]


import re
from leai.models import DependencyLink, ObjectTraceResult


def _find_raw_object(schemas: list[SchemaMetadata], name: str):
    name_upper = name.upper()
    for s in schemas:
        for t in s.tables:
            if t.name.upper() == name_upper:
                return "TABLE", t
        for v in s.views:
            if v.name.upper() == name_upper:
                return "VIEW", v
        for mv in s.mviews:
            if mv.name.upper() == name_upper:
                return "MATERIALIZED VIEW", mv
        for co in s.code_objects:
            if co.name.upper() == name_upper:
                return co.object_type.upper(), co
        for trg in s.triggers:
            if trg.name.upper() == name_upper:
                return "TRIGGER", trg
    return "UNKNOWN", None


def trace_raw_dependencies(schemas: list[SchemaMetadata], target_object_name: str, max_depth: int = 1) -> ObjectTraceResult:
    target_upper = target_object_name.strip().upper()
    focal_type, focal_obj = _find_raw_object(schemas, target_upper)

    result = ObjectTraceResult(
        focal_name=target_upper,
        focal_type=focal_type,
        focal_object=focal_obj,
    )

    all_related_names = set()
    visited_nodes = {target_upper}
    seen_links = set()

    current_layer = {target_upper}

    for current_depth in range(1, max(1, max_depth) + 1):
        if not current_layer:
            break
        next_layer = set()

        for curr_name in current_layer:
            curr_type, curr_obj = _find_raw_object(schemas, curr_name)
            word_pattern = re.compile(rf"\b{re.escape(curr_name)}\b", re.IGNORECASE)

            for schema in schemas:
                # A) Chaves Estrangeiras de saída
                if isinstance(curr_obj, TableMeta):
                    for fk in curr_obj.foreign_keys:
                        ref_tbl = fk.referenced_table.upper()
                        fk_key = ("FK", curr_name, ref_tbl, (fk.column or "").upper())
                        if fk_key not in seen_links:
                            seen_links.add(fk_key)
                            result.dependencies.append(
                                DependencyLink(
                                    source_name=curr_name,
                                    source_type="TABLE",
                                    target_name=ref_tbl,
                                    target_type="TABLE",
                                    relation_type="FK_REFERENCES",
                                    details=f"Coluna {fk.column} -> {ref_tbl}.{fk.referenced_column} ({fk.name})",
                                    depth=current_depth,
                                )
                            )
                        if ref_tbl not in visited_nodes:
                            visited_nodes.add(ref_tbl)
                            next_layer.add(ref_tbl)
                            all_related_names.add(ref_tbl)

                # B) Chaves Estrangeiras de entrada
                for t in schema.tables:
                    if t.name.upper() == curr_name:
                        continue
                    for fk in t.foreign_keys:
                        if fk.referenced_table.upper() == curr_name:
                            child_name = t.name.upper()
                            fk_key = ("FK", child_name, curr_name, (fk.column or "").upper())
                            if fk_key not in seen_links:
                                seen_links.add(fk_key)
                                result.dependencies.append(
                                    DependencyLink(
                                        source_name=child_name,
                                        source_type="TABLE",
                                        target_name=curr_name,
                                        target_type=curr_type,
                                        relation_type="FK_REFERENCED_BY",
                                        details=f"Tabela filha {t.name}.{fk.column} referencia {curr_name}.{fk.referenced_column}",
                                        depth=current_depth,
                                    )
                                )
                            if child_name not in visited_nodes:
                                visited_nodes.add(child_name)
                                next_layer.add(child_name)
                                all_related_names.add(child_name)

                # C) Triggers vinculadas
                for trg in schema.triggers:
                    trg_tbl = (trg.table_name or "").upper()
                    if trg_tbl == curr_name:
                        trg_name = trg.name.upper()
                        link_key = (trg_name, curr_name, "TRIGGER_ON")
                        if link_key not in seen_links:
                            seen_links.add(link_key)
                            result.dependencies.append(
                                DependencyLink(
                                    source_name=trg_name,
                                    source_type="TRIGGER",
                                    target_name=curr_name,
                                    target_type=curr_type,
                                    relation_type="TRIGGER_ON",
                                    details=f"Evento {trg.trigger_type} {trg.triggering_event}",
                                    depth=current_depth,
                                )
                            )
                        if trg_name not in visited_nodes:
                            visited_nodes.add(trg_name)
                            next_layer.add(trg_name)
                            all_related_names.add(trg_name)

                # D) Views que consultam o objeto
                for v in schema.views:
                    if v.name.upper() == curr_name:
                        continue
                    if v.text and word_pattern.search(v.text):
                        v_name = v.name.upper()
                        link_key = (v_name, curr_name, "READS/SELECTS")
                        if link_key not in seen_links:
                            seen_links.add(link_key)
                            result.dependencies.append(
                                DependencyLink(
                                    source_name=v_name,
                                    source_type="VIEW",
                                    target_name=curr_name,
                                    target_type=curr_type,
                                    relation_type="READS/SELECTS",
                                    details="View realiza consulta SQL sobre o objeto",
                                    depth=current_depth,
                                )
                            )
                        if v_name not in visited_nodes:
                            visited_nodes.add(v_name)
                            next_layer.add(v_name)
                            all_related_names.add(v_name)

                # E) Materialized Views
                for mv in schema.mviews:
                    if mv.name.upper() == curr_name:
                        continue
                    if mv.query and word_pattern.search(mv.query):
                        mv_name = mv.name.upper()
                        link_key = (mv_name, curr_name, "READS/SELECTS")
                        if link_key not in seen_links:
                            seen_links.add(link_key)
                            result.dependencies.append(
                                DependencyLink(
                                    source_name=mv_name,
                                    source_type="MATERIALIZED VIEW",
                                    target_name=curr_name,
                                    target_type=curr_type,
                                    relation_type="READS/SELECTS",
                                    details="Materialized View baseada no objeto",
                                    depth=current_depth,
                                )
                            )
                        if mv_name not in visited_nodes:
                            visited_nodes.add(mv_name)
                            next_layer.add(mv_name)
                            all_related_names.add(mv_name)

                # F) Code Objects (Procedures, Functions, Packages)
                for co in schema.code_objects:
                    if co.name.upper() == curr_name:
                        continue
                    if co.source and word_pattern.search(co.source):
                        co_name = co.name.upper()
                        link_key = (co_name, curr_name, "PLSQL_DEPENDENCY")
                        if link_key not in seen_links:
                            seen_links.add(link_key)
                            result.dependencies.append(
                                DependencyLink(
                                    source_name=co_name,
                                    source_type=co.object_type.upper(),
                                    target_name=curr_name,
                                    target_type=curr_type,
                                    relation_type="PLSQL_DEPENDENCY",
                                    details=f"Objeto {co.object_type} manipula ou referencia {curr_name} no código-fonte",
                                    depth=current_depth,
                                )
                            )
                        if co_name not in visited_nodes:
                            visited_nodes.add(co_name)
                            next_layer.add(co_name)
                            all_related_names.add(co_name)

        current_layer = next_layer

    # Anexar metadados dos objetos relacionados
    for schema in schemas:
        for t in schema.tables:
            if t.name.upper() in all_related_names and t.name.upper() != target_upper:
                result.related_tables.append(t)
        for v in schema.views:
            if v.name.upper() in all_related_names and v.name.upper() != target_upper:
                result.related_views.append(v)
        for co in schema.code_objects:
            if co.name.upper() in all_related_names and co.name.upper() != target_upper:
                result.related_code_objects.append(co)
        for trg in schema.triggers:
            if trg.name.upper() in all_related_names and trg.name.upper() != target_upper:
                result.related_triggers.append(trg)

    return result


