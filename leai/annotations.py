import sys
from pathlib import Path
from typing import Any

import yaml

from leai.models import ObjectAnnotation


def load_annotation(
    file_path: Path,
    storage: Any = None,
    schema_name: str = "",
    obj_folder: str = "",
    obj_name: str = "",
) -> ObjectAnnotation:
    if storage is not None and schema_name and obj_folder and obj_name:
        try:
            remote_ann = storage.load_annotation(schema_name, obj_folder, obj_name)
            if remote_ann.description or remote_ann.columns or remote_ann.business_rules:
                save_annotation(file_path, remote_ann)
                return remote_ann
        except Exception:
            pass

    if not file_path.exists():
        return ObjectAnnotation()
    try:
        raw = yaml.safe_load(file_path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return ObjectAnnotation.model_validate(raw)
    except Exception as exc:
        print(f"Warning: Error loading annotation file '{file_path}': {exc}", file=sys.stderr)
    return ObjectAnnotation()


def save_annotation(
    file_path: Path,
    annotation: ObjectAnnotation,
    storage: Any = None,
    schema_name: str = "",
    obj_folder: str = "",
    obj_name: str = "",
) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    data = annotation.model_dump(exclude_defaults=False, exclude_none=False)
    clean_data = {
        "description": data.get("description") or "",
        "tags": data.get("tags") or [],
        "business_rules": data.get("business_rules") or [],
        "use_cases": data.get("use_cases") or [],
        "related_objects": data.get("related_objects") or [],
        "warnings": data.get("warnings") or [],
        "columns": data.get("columns") or {},
    }
    file_path.write_text(yaml.safe_dump(clean_data, sort_keys=False, allow_unicode=True), encoding="utf-8")

    if storage is not None and schema_name and obj_folder and obj_name:
        try:
            storage.save_annotation(schema_name, obj_folder, obj_name, annotation)
        except Exception as exc:
            print(f"Warning: Failed to upload annotation to SeaweedFS: {exc}", file=sys.stderr)


def ensure_annotation_stub(
    file_path: Path,
    db_comment: str | None = None,
    column_names: list[str] | None = None,
    storage: Any = None,
    schema_name: str = "",
    obj_folder: str = "",
    obj_name: str = "",
) -> ObjectAnnotation:
    column_names = column_names or []
    if file_path.exists() or (storage and schema_name and obj_folder and obj_name):
        existing = load_annotation(
            file_path,
            storage=storage,
            schema_name=schema_name,
            obj_folder=obj_folder,
            obj_name=obj_name,
        )
        if existing.description or existing.columns or existing.business_rules or file_path.exists():
            updated = False
            for col in column_names:
                if col not in existing.columns:
                    existing.columns[col] = ""
                    updated = True
            if updated:
                save_annotation(
                    file_path,
                    existing,
                    storage=storage,
                    schema_name=schema_name,
                    obj_folder=obj_folder,
                    obj_name=obj_name,
                )
            return existing

    cols_dict = {col: "" for col in column_names}
    annotation = ObjectAnnotation(
        description=db_comment or "",
        business_rules=[],
        use_cases=[],
        columns=cols_dict,
    )
    save_annotation(
        file_path,
        annotation,
        storage=storage,
        schema_name=schema_name,
        obj_folder=obj_folder,
        obj_name=obj_name,
    )
    return annotation
