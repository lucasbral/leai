from __future__ import annotations

from pathlib import Path
import yaml

from leai.models import ObjectAnnotation


def load_annotation(file_path: Path) -> ObjectAnnotation:
    if not file_path.exists():
        return ObjectAnnotation()
    try:
        raw = yaml.safe_load(file_path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return ObjectAnnotation.model_validate(raw)
    except Exception:
        pass
    return ObjectAnnotation()


def save_annotation(file_path: Path, annotation: ObjectAnnotation) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    data = annotation.model_dump(exclude_defaults=False, exclude_none=False)
    clean_data = {
        "description": data.get("description") or "",
        "business_rules": data.get("business_rules") or [],
        "columns": data.get("columns") or {},
    }
    file_path.write_text(yaml.safe_dump(clean_data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def ensure_annotation_stub(
    file_path: Path,
    db_comment: str | None = None,
    column_names: list[str] | None = None,
) -> ObjectAnnotation:
    if file_path.exists():
        return load_annotation(file_path)

    column_names = column_names or []
    cols_dict = {col: "" for col in column_names}
    annotation = ObjectAnnotation(
        description=db_comment or "",
        business_rules=[],
        columns=cols_dict,
    )
    save_annotation(file_path, annotation)
    return annotation
