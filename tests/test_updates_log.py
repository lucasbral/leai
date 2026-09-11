from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from leai.models import (
    CodeObjectMeta,
    ColumnMeta,
    IndexMeta,
    MaterializedViewMeta,
    SchemaMetadata,
    SequenceMeta,
    SynonymMeta,
    TableMeta,
    TriggerMeta,
    ViewMeta,
)
from leai.updates_log import (
    build_update_manifest,
    collect_modified_objects,
    render_update_markdown,
    save_update_log,
)


class TestUpdatesLog(unittest.TestCase):
    def setUp(self):
        self.sample_meta = SchemaMetadata(
            schema_name="C_ERGON",
            tables=[
                TableMeta(
                    name="EVENTO_FUNC",
                    comment="Eventos funcionais",
                    columns=[ColumnMeta(name="NUM_FOLHA", data_type="NUMBER", nullable=False)],
                    last_ddl_time="2026-09-11 10:00:00",
                    last_modified_by="SCOTT",
                )
            ],
            views=[
                ViewMeta(
                    name="V_CONTRACHEQUE",
                    comment="Visao de contracheque",
                    last_ddl_time="2026-09-11 10:15:00",
                    last_modified_by="SYS",
                )
            ],
            mviews=[
                MaterializedViewMeta(
                    name="MV_FOLHA_RESUMO",
                    last_ddl_time="2026-09-11 10:20:00",
                    last_modified_by="SYS",
                )
            ],
            code_objects=[
                CodeObjectMeta(
                    name="PKG_CALCULO",
                    object_type="PACKAGE",
                    comment="Pacote de calculo",
                    last_ddl_time="2026-09-11 10:30:00",
                    last_modified_by="DEV_USER",
                )
            ],
            triggers=[
                TriggerMeta(
                    name="TRG_AUDIT_FUNC",
                    table_name="EVENTO_FUNC",
                    last_ddl_time="2026-09-11 10:35:00",
                    last_modified_by="SEC_USER",
                )
            ],
            sequences=[
                SequenceMeta(
                    name="SEQ_EVENTO",
                    last_ddl_time="2026-09-11 10:40:00",
                    last_modified_by="SYS",
                )
            ],
            indexes=[
                IndexMeta(
                    name="IDX_EVENTO_NUM",
                    table_name="EVENTO_FUNC",
                    last_ddl_time="2026-09-11 10:45:00",
                    last_modified_by="DBA",
                )
            ],
            synonyms=[
                SynonymMeta(
                    name="SYN_EVENTO",
                    table_name="EVENTO_FUNC",
                    last_ddl_time="2026-09-11 10:50:00",
                    last_modified_by="APP_USER",
                )
            ],
        )

    def test_collect_modified_objects(self):
        objs = collect_modified_objects(self.sample_meta)
        self.assertEqual(len(objs), 8)

        types = [o["type"] for o in objs]
        self.assertIn("TABLE", types)
        self.assertIn("VIEW", types)
        self.assertIn("MATERIALIZED VIEW", types)
        self.assertIn("PACKAGE", types)
        self.assertIn("TRIGGER", types)
        self.assertIn("SEQUENCE", types)
        self.assertIn("INDEX", types)
        self.assertIn("SYNONYM", types)

        table_obj = next(o for o in objs if o["type"] == "TABLE")
        self.assertEqual(table_obj["name"], "EVENTO_FUNC")
        self.assertEqual(table_obj["last_ddl_time"], "2026-09-11 10:00:00")
        self.assertEqual(table_obj["last_modified_by"], "SCOTT")
        self.assertEqual(table_obj["comment"], "Eventos funcionais")

    def test_build_update_manifest(self):
        objs = collect_modified_objects(self.sample_meta)
        manifest = build_update_manifest(
            schemas_objects={"C_ERGON": objs},
            time_window="last 24 hours",
            duration_seconds=15.42,
            sync_summary={"s3_uploaded": 8, "s3_skipped": 0, "annotations_synced": 8, "docs_compiled": 0},
            timestamp_iso="2026-09-11T14:55:00Z",
        )

        self.assertEqual(manifest["timestamp"], "2026-09-11T14:55:00Z")
        self.assertEqual(manifest["time_window"], "last 24 hours")
        self.assertEqual(manifest["duration_seconds"], 15.42)
        self.assertEqual(manifest["total_modified_objects"], 8)
        self.assertIn("C_ERGON", manifest["schemas"])
        self.assertEqual(manifest["schemas"]["C_ERGON"]["total"], 8)
        self.assertEqual(manifest["sync_summary"]["s3_uploaded"], 8)

    def test_render_update_markdown_empty(self):
        manifest = build_update_manifest(
            schemas_objects={"C_ERGON": []},
            time_window="last 1 hours",
            duration_seconds=3.2,
        )
        md = render_update_markdown(manifest)
        self.assertIn("Total Modified Objects:** **0**", md)
        self.assertIn("No database objects were modified", md)

    def test_render_update_markdown_with_objects(self):
        objs = collect_modified_objects(self.sample_meta)
        manifest = build_update_manifest(
            schemas_objects={"C_ERGON": objs},
            time_window="last 24 hours",
            duration_seconds=12.5,
            sync_summary={"s3_uploaded": 8, "s3_skipped": 2},
        )
        md = render_update_markdown(manifest)
        self.assertIn("# LEAI Update Report", md)
        self.assertIn("Total Modified Objects:** **8**", md)
        self.assertIn("S3 Uploaded: 8", md)
        self.assertIn("Schema `C_ERGON` (8 modified)", md)
        self.assertIn("| `TABLE` | **`EVENTO_FUNC`** | 2026-09-11 10:00:00 | SCOTT |", md)
        self.assertIn("| `PACKAGE` | **`PKG_CALCULO`** | 2026-09-11 10:30:00 | DEV_USER |", md)

    def test_save_update_log(self):
        objs = collect_modified_objects(self.sample_meta)
        manifest = build_update_manifest(
            schemas_objects={"C_ERGON": objs},
            time_window="last 1 days",
            duration_seconds=8.0,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "updates"
            json_p, md_p, latest_json_p, latest_md_p = save_update_log(manifest, out_dir, timestamp_slug="20260911_120000")

            self.assertTrue(json_p.exists())
            self.assertTrue(md_p.exists())
            self.assertTrue(latest_json_p.exists())
            self.assertTrue(latest_md_p.exists())

            self.assertEqual(json_p.name, "update_20260911_120000.json")
            self.assertEqual(md_p.name, "update_20260911_120000.md")

            data = json.loads(latest_json_p.read_text(encoding="utf-8"))
            self.assertEqual(data["total_modified_objects"], 8)
            self.assertIn("EVENTO_FUNC", latest_md_p.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
