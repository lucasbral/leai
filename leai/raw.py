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
