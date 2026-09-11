from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from leai.models import SchemaMetadata


def collect_modified_objects(schema_meta: SchemaMetadata) -> list[dict[str, Any]]:
    """Extracts all modified objects from a SchemaMetadata instance into a standardized list."""
    objects: list[dict[str, Any]] = []

    for t in schema_meta.tables:
        item: dict[str, Any] = {
            "type": "TABLE",
            "name": t.name,
            "last_ddl_time": t.last_ddl_time,
            "last_modified_by": t.last_modified_by,
        }
        if t.comment:
            item["comment"] = t.comment
        objects.append(item)

    for v in schema_meta.views:
        item = {
            "type": "VIEW",
            "name": v.name,
            "last_ddl_time": v.last_ddl_time,
            "last_modified_by": v.last_modified_by,
        }
        if v.comment:
            item["comment"] = v.comment
        objects.append(item)

    for mv in schema_meta.mviews:
        item = {
            "type": "MATERIALIZED VIEW",
            "name": mv.name,
            "last_ddl_time": mv.last_ddl_time,
            "last_modified_by": mv.last_modified_by,
        }
        if mv.comment:
            item["comment"] = mv.comment
        objects.append(item)

    for co in schema_meta.code_objects:
        item = {
            "type": co.object_type.upper(),
            "name": co.name,
            "last_ddl_time": co.last_ddl_time,
            "last_modified_by": co.last_modified_by,
        }
        if co.comment:
            item["comment"] = co.comment
        objects.append(item)

    for tr in schema_meta.triggers:
        item = {
            "type": "TRIGGER",
            "name": tr.name,
            "table_name": tr.table_name,
            "last_ddl_time": tr.last_ddl_time,
            "last_modified_by": tr.last_modified_by,
        }
        objects.append(item)

    for sq in schema_meta.sequences:
        item = {
            "type": "SEQUENCE",
            "name": sq.name,
            "last_ddl_time": sq.last_ddl_time,
            "last_modified_by": sq.last_modified_by,
        }
        objects.append(item)

    for ix in schema_meta.indexes:
        item = {
            "type": "INDEX",
            "name": ix.name,
            "table_name": ix.table_name,
            "last_ddl_time": ix.last_ddl_time,
            "last_modified_by": ix.last_modified_by,
        }
        objects.append(item)

    for sy in schema_meta.synonyms:
        item = {
            "type": "SYNONYM",
            "name": sy.name,
            "table_name": sy.table_name,
            "last_ddl_time": sy.last_ddl_time,
            "last_modified_by": sy.last_modified_by,
        }
        objects.append(item)

    return objects


def build_update_manifest(
    schemas_objects: dict[str, list[dict[str, Any]]],
    time_window: str,
    duration_seconds: float,
    sync_summary: dict[str, Any] | None = None,
    timestamp_iso: str | None = None,
) -> dict[str, Any]:
    """Builds a structured dictionary manifest for an incremental update run."""
    ts = timestamp_iso or datetime.now(timezone.utc).isoformat()
    total_modified = sum(len(objs) for objs in schemas_objects.values())

    schemas_payload = {
        schema: {
            "total": len(objs),
            "objects": objs,
        }
        for schema, objs in schemas_objects.items()
    }

    return {
        "timestamp": ts,
        "time_window": time_window,
        "duration_seconds": round(duration_seconds, 2),
        "schemas_processed": list(schemas_objects.keys()),
        "total_modified_objects": total_modified,
        "schemas": schemas_payload,
        "sync_summary": sync_summary or {},
    }


def render_update_markdown(manifest: dict[str, Any]) -> str:
    """Renders a human-readable Markdown report from an update manifest."""
    ts = manifest.get("timestamp", "")
    time_window = manifest.get("time_window", "")
    dur = manifest.get("duration_seconds", 0)
    total_objs = manifest.get("total_modified_objects", 0)
    sync = manifest.get("sync_summary", {})
    schemas = manifest.get("schemas", {})

    lines: list[str] = [
        f"# LEAI Update Report — {ts}",
        "",
        "## Executive Summary",
        f"- **Timestamp (UTC):** `{ts}`",
        f"- **Search Window:** `{time_window}`",
        f"- **Duration:** `{dur}s`",
        f"- **Total Modified Objects:** **{total_objs}**",
    ]

    if sync:
        sync_items = []
        if "s3_uploaded" in sync:
            sync_items.append(f"S3 Uploaded: {sync['s3_uploaded']}")
        if "s3_skipped" in sync:
            sync_items.append(f"S3 Skipped: {sync['s3_skipped']}")
        if "annotations_synced" in sync:
            sync_items.append(f"Annotations Synced: {sync['annotations_synced']}")
        if "docs_compiled" in sync:
            sync_items.append(f"Docs Compiled: {sync['docs_compiled']}")
        if sync_items:
            lines.append(f"- **Synchronization:** {', '.join(sync_items)}")

    lines.append("")

    if total_objs == 0:
        lines.append("> [!NOTE]")
        lines.append(f"> No database objects were modified in the specified window (`{time_window}`).")
        lines.append("")
        return "\n".join(lines)

    lines.append("## Modified Objects by Schema")
    lines.append("")

    for schema_name, s_data in schemas.items():
        objs = s_data.get("objects", [])
        total = s_data.get("total", len(objs))
        lines.append(f"### Schema `{schema_name}` ({total} modified)")
        lines.append("")
        if not objs:
            lines.append("_No modified objects in this schema._")
            lines.append("")
            continue

        lines.append("| Type | Object Name | Oracle Last DDL | Modified By | Details |")
        lines.append("| :--- | :--- | :--- | :--- | :--- |")

        for o in objs:
            o_type = o.get("type", "UNKNOWN")
            o_name = o.get("name", "")
            o_ddl = o.get("last_ddl_time") or "-"
            o_by = o.get("last_modified_by") or "-"
            details = o.get("table_name") or o.get("comment") or "-"
            lines.append(f"| `{o_type}` | **`{o_name}`** | {o_ddl} | {o_by} | {details} |")

        lines.append("")

    return "\n".join(lines)


def save_update_log(
    manifest: dict[str, Any],
    output_dir: Path,
    timestamp_slug: str | None = None,
) -> tuple[Path, Path, Path, Path]:
    """Saves both timestamped and 'latest' JSON and Markdown logs to output_dir."""
    output_dir.mkdir(parents=True, exist_ok=True)

    if not timestamp_slug:
        dt = datetime.now(timezone.utc)
        timestamp_slug = dt.strftime("%Y%m%d_%H%M%S")

    json_path = output_dir / f"update_{timestamp_slug}.json"
    md_path = output_dir / f"update_{timestamp_slug}.md"
    latest_json_path = output_dir / "latest.json"
    latest_md_path = output_dir / "latest.md"

    json_content = json.dumps(manifest, indent=2, ensure_ascii=False)
    md_content = render_update_markdown(manifest)

    # Write timestamped files
    json_path.write_text(json_content, encoding="utf-8")
    md_path.write_text(md_content, encoding="utf-8")

    # Write latest files (pointer copies)
    latest_json_path.write_text(json_content, encoding="utf-8")
    latest_md_path.write_text(md_content, encoding="utf-8")

    return json_path, md_path, latest_json_path, latest_md_path
