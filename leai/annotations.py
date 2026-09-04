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
    remote_ann: ObjectAnnotation | None = None
    if storage is not None and schema_name and obj_folder and obj_name:
        try:
            r = storage.load_annotation(schema_name, obj_folder, obj_name)
            if isinstance(r, ObjectAnnotation) and (r.description or r.columns or r.business_rules):
                remote_ann = r
        except Exception:
            pass

    local_ann: ObjectAnnotation | None = None
    if file_path.exists():
        try:
            raw = yaml.safe_load(file_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                local_ann = ObjectAnnotation.model_validate(raw)
        except Exception as exc:
            print(f"Warning: Error loading annotation file '{file_path}': {exc}", file=sys.stderr)

    if remote_ann is not None and local_ann is not None:
        # Merge remote and local annotations, preserving human descriptions and comments from both!
        merged_desc = remote_ann.description or local_ann.description or ""

        # Merge column comments: prefer non-empty comments from either
        merged_cols = dict(local_ann.columns)
        for col, desc in remote_ann.columns.items():
            if desc:
                merged_cols[col] = desc
            elif col not in merged_cols:
                merged_cols[col] = ""

        def _merge_lists(a: list[str], b: list[str]) -> list[str]:
            seen = set()
            res = []
            for item in a + b:
                if item and item not in seen:
                    seen.add(item)
                    res.append(item)
            return res

        merged_ann = ObjectAnnotation(
            description=merged_desc,
            tags=_merge_lists(remote_ann.tags, local_ann.tags),
            business_rules=_merge_lists(remote_ann.business_rules, local_ann.business_rules),
            use_cases=_merge_lists(remote_ann.use_cases, local_ann.use_cases),
            related_objects=_merge_lists(remote_ann.related_objects, local_ann.related_objects),
            warnings=_merge_lists(remote_ann.warnings, local_ann.warnings),
            columns=merged_cols,
        )
        save_annotation(file_path, merged_ann)
        return merged_ann

    if remote_ann is not None:
        save_annotation(file_path, remote_ann)
        return remote_ann

    if local_ann is not None:
        return local_ann

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
    existing = load_annotation(
        file_path,
        storage=storage,
        schema_name=schema_name,
        obj_folder=obj_folder,
        obj_name=obj_name,
    )
    if existing.description or existing.columns or existing.business_rules or file_path.exists():
        updated = False
        if not existing.description and db_comment:
            existing.description = db_comment
            updated = True
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
