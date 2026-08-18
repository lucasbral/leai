from __future__ import annotations

import json
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

from leai.config import LeaiConfig
from leai.models import CodeObjectMeta, ColumnMeta, ForeignKeyMeta, SchemaMetadata, TableMeta
from leai.web.server import start_server


class WebServerTests(unittest.TestCase):
    def setUp(self):
        self.table = TableMeta(
            name="EMPLOYEES",
            comment="Tabela de funcionários",
            columns=[
                ColumnMeta(name="EMP_ID", data_type="NUMBER(10)", nullable=False, comment="ID do funcionário"),
                ColumnMeta(name="NAME", data_type="VARCHAR2(100)", nullable=False, comment="Nome completo"),
            ],
            primary_keys=["EMP_ID"],
            foreign_keys=[
                ForeignKeyMeta(
                    name="FK_EMP_DEP",
                    column="DEP_ID",
                    referenced_table="DEPARTMENTS",
                    referenced_column="DEP_ID",
                )
            ],
        )
        self.code_obj = CodeObjectMeta(
            name="PKG_PAYROLL",
            object_type="PACKAGE",
            comment="Pacote de folha",
            source="CREATE OR REPLACE PACKAGE PKG_PAYROLL AS END;",
        )
        self.schema = SchemaMetadata(
            schema_name="HR",
            tables=[self.table],
            views=[],
            code_objects=[self.code_obj],
            triggers=[],
            synonyms=[],
            sequences=[],
        )

    def test_web_server_endpoints(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            cfg = LeaiConfig()
            cfg.schemas = ["HR"]
            cfg.rawPath = base / "raw"
            cfg.annotationsPath = base / "annotations"
            cfg.docPath = base / "docs"

            test_config_file = base / "leai.yml"
            test_config_file.write_text("schemas:\n  - HR\n", encoding="utf-8")

            server, url = start_server(
                config=cfg,
                schemas=[self.schema],
                client=None,
                host="127.0.0.1",
                port=8899,
                open_browser=False,
                in_background=True,
                config_path=test_config_file,
            )

            try:
                time.sleep(0.3)

                # 1. Test GET / (HTML)
                req = urllib.request.urlopen(f"{url}/")
                self.assertEqual(req.status, 200)
                html_body = req.read().decode("utf-8")
                self.assertIn("LEAI Docs", html_body)

                # 2. Test GET /api/status
                req_status = urllib.request.urlopen(f"{url}/api/status")
                self.assertEqual(req_status.status, 200)
                status_data = json.loads(req_status.read().decode("utf-8"))
                self.assertEqual(status_data["status"], "online")
                self.assertEqual(status_data["schemas_count"], 1)

                # 3. Test GET /api/catalog
                req_cat = urllib.request.urlopen(f"{url}/api/catalog")
                self.assertEqual(req_cat.status, 200)
                cat_data = json.loads(req_cat.read().decode("utf-8"))
                self.assertEqual(len(cat_data["schemas"]), 1)
                self.assertEqual(cat_data["schemas"][0]["schema_name"], "HR")
                self.assertEqual(cat_data["schemas"][0]["tables"][0]["name"], "EMPLOYEES")
                self.assertEqual(cat_data["schemas"][0]["code_objects"][0]["name"], "PKG_PAYROLL")
                self.assertEqual(cat_data["schemas"][0]["code_objects"][0]["type"], "PACKAGE")

                # 4. Test GET /api/object (Table and Package)
                req_obj = urllib.request.urlopen(f"{url}/api/object?schema=HR&type=TABLE&name=EMPLOYEES")
                self.assertEqual(req_obj.status, 200)
                obj_data = json.loads(req_obj.read().decode("utf-8"))
                self.assertEqual(obj_data["object_name"], "EMPLOYEES")
                self.assertEqual(len(obj_data["columns"]), 2)
                self.assertEqual(obj_data["primary_keys"], ["EMP_ID"])

                req_code = urllib.request.urlopen(f"{url}/api/object?schema=HR&type=PACKAGE&name=PKG_PAYROLL")
                self.assertEqual(req_code.status, 200)
                code_data = json.loads(req_code.read().decode("utf-8"))
                self.assertEqual(code_data["object_name"], "PKG_PAYROLL")
                self.assertEqual(code_data["object_type"], "PACKAGE")

                # 5. Test POST /api/annotations (Save & Recompile All 7 Fields)
                payload = {
                    "schema": "HR",
                    "object_type": "TABLE",
                    "object_name": "EMPLOYEES",
                    "business_description": "Cadastro corporativo de servidores e colaboradores.",
                    "business_rules": ["Todo funcionário tem matrícula única."],
                    "use_cases": ["Relatório mensal de folha", "SELECT * FROM EMPLOYEES WHERE STATUS = 'A'"],
                    "warnings": ["Tabela crítica com particionamento anual."],
                    "related_objects": ["DEPARTMENTS", "SALARIES"],
                    "columns": {
                        "EMP_ID": {"description": "Chave primária do colaborador."},
                        "NAME": {"description": "Nome de registro civil."},
                    },
                    "tags": ["RH", "CADASTRO"],
                }
                req_post = urllib.request.Request(
                    f"{url}/api/annotations",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                res_post = urllib.request.urlopen(req_post)
                self.assertEqual(res_post.status, 200)
                save_data = json.loads(res_post.read().decode("utf-8"))
                self.assertTrue(save_data["success"])

                # Verify YAML file created with all 7 fields
                saved_yaml = (
                    (cfg.annotationsPath / "tables" / "EMPLOYEES.yml")
                    if (cfg.annotationsPath / "tables" / "EMPLOYEES.yml").exists()
                    else (cfg.annotationsPath / "HR" / "tables" / "EMPLOYEES.yml")
                )
                self.assertTrue(saved_yaml.exists())
                yaml_content = saved_yaml.read_text(encoding="utf-8")
                self.assertIn("Cadastro corporativo", yaml_content)
                self.assertIn("Relatório mensal de folha", yaml_content)
                self.assertIn("Tabela crítica", yaml_content)
                self.assertIn("DEPARTMENTS", yaml_content)

                # Verify Markdown recompiled with all 7 fields
                compiled_md = (
                    (cfg.docPath / "tables" / "EMPLOYEES.md")
                    if (cfg.docPath / "tables" / "EMPLOYEES.md").exists()
                    else (cfg.docPath / "HR" / "tables" / "EMPLOYEES.md")
                )
                self.assertTrue(compiled_md.exists())
                md_content = compiled_md.read_text(encoding="utf-8")
                self.assertIn("Cadastro corporativo", md_content)
                self.assertIn("Relatório mensal de folha", md_content)
                self.assertIn("Tabela crítica", md_content)
                self.assertIn("DEPARTMENTS", md_content)

                # Verify GET /api/object returns all 7 fields
                req_reload = urllib.request.urlopen(f"{url}/api/object?schema=HR&type=TABLE&name=EMPLOYEES")
                reload_data = json.loads(req_reload.read().decode("utf-8"))
                self.assertEqual(
                    reload_data["annotations"]["use_cases"], ["Relatório mensal de folha", "SELECT * FROM EMPLOYEES WHERE STATUS = 'A'"]
                )
                self.assertEqual(reload_data["annotations"]["warnings"], ["Tabela crítica com particionamento anual."])
                self.assertEqual(reload_data["annotations"]["related_objects"], ["DEPARTMENTS", "SALARIES"])

                # 6. Test POST /api/compile
                req_compile = urllib.request.Request(
                    f"{url}/api/compile",
                    data=b"{}",
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                res_compile = urllib.request.urlopen(req_compile)
                self.assertEqual(res_compile.status, 200)
                comp_data = json.loads(res_compile.read().decode("utf-8"))
                self.assertTrue(comp_data["success"])

                # 7. Test GET /api/config
                req_cfg = urllib.request.urlopen(f"{url}/api/config")
                self.assertEqual(req_cfg.status, 200)
                cfg_data = json.loads(req_cfg.read().decode("utf-8"))
                self.assertIn("schemas", cfg_data)
                self.assertIn("ai", cfg_data)
                self.assertEqual(cfg_data["schemas"], ["HR"])

                # 8. Test POST /api/config (save to leai.yml)
                cfg_payload = {
                    "dsn": "scott/tiger@localhost:1521/XEPDB1",
                    "schemas": ["HR", "FINANCE"],
                    "include": ["TAB_*"],
                    "exclude": ["TMP_*"],
                    "object_types": ["tables", "views"],
                    "rawPath": str(cfg.rawPath),
                    "annotationsPath": str(cfg.annotationsPath),
                    "docPath": str(cfg.docPath),
                    "ai": {
                        "default_provider": "gemini",
                        "temperature": 0.35,
                        "providers": {"gemini": {"model": "gemini-1.5-flash", "base_url": "", "api_key": "test-key-123"}},
                    },
                }
                req_save_cfg = urllib.request.Request(
                    f"{url}/api/config",
                    data=json.dumps(cfg_payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                res_save_cfg = urllib.request.urlopen(req_save_cfg)
                self.assertEqual(res_save_cfg.status, 200)
                save_cfg_res = json.loads(res_save_cfg.read().decode("utf-8"))
                self.assertTrue(save_cfg_res["success"])
                self.assertEqual(server.config.ai.default_provider, "gemini")
                self.assertEqual(server.config.schemas, ["HR", "FINANCE"])

            finally:
                server.shutdown()


if __name__ == "__main__":
    unittest.main()
