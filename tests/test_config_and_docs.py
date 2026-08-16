import tempfile
import unittest
from pathlib import Path

from leai.config import load_config
from leai.docs import (
    MANUAL_END,
    MANUAL_START,
    render_table_markdown,
    write_schema_docs,
    write_table_docs,
)
from leai.models import (
    CodeObjectMeta,
    ColumnMeta,
    ForeignKeyMeta,
    SchemaMetadata,
    SubprogramMeta,
    TableMeta,
    TriggerMeta,
    ViewMeta,
)
from leai.oracle import _build_connect_kwargs, _like_pattern_to_regex, _split_package_source
from leai.raw import load_raw_schema, load_raw_schemas, save_raw_schema


class ConfigAndDocsTests(unittest.TestCase):
    def test_load_config_normalizes_paths_and_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg_file = root / "leai.yml"
            dsn = "oracle://usuario:senha@localhost:1521/ORCLPDB1"
            cfg_file.write_text(
                f"""
                dsn: "{dsn}"
                schema: "meu_schema"
                docPath: "./docs"
                rawPath: "./raw"
                annotationsPath: "./annotations"
                include: ["funcionarios"]
                exclude: ["BIN$%"]
                """,
                encoding="utf-8",
            )
            cfg = load_config(cfg_file)
            self.assertEqual(cfg.schema_name, "MEU_SCHEMA")
            self.assertEqual(cfg.schemas, ["MEU_SCHEMA"])
            self.assertFalse(cfg.is_all_schemas)
            self.assertEqual(cfg.include, ["FUNCIONARIOS"])
            self.assertEqual(cfg.rawPath, (root / "raw").resolve())
            self.assertEqual(cfg.docPath, (root / "docs").resolve())
            self.assertEqual(cfg.annotationsPath, (root / "annotations").resolve())

    def test_load_config_expands_env_vars(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg_file = root / "leai_env.yml"
            import os
            os.environ["TEST_LEAI_DB_HOST"] = "oracle.empresa.com"
            os.environ["TEST_LEAI_SCHEMA"] = "prod_schema"

            cfg_file.write_text(
                """
                dsn: "oracle://usr:pwd@${TEST_LEAI_DB_HOST}:1521/X"
                schemas:
                  - "${TEST_LEAI_SCHEMA}"
                """,
                encoding="utf-8",
            )
            cfg = load_config(cfg_file)
            self.assertIn("oracle.empresa.com", cfg.dsn)
            self.assertEqual(cfg.schemas, ["PROD_SCHEMA"])

    def test_load_config_supports_multi_schemas_and_all(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg_file = root / "leai.yml"
            cfg_file.write_text(
                """
                dsn: "oracle://usr:pwd@localhost:1521/X"
                schemas:
                  - HR
                  - sales
                """,
                encoding="utf-8",
            )
            cfg = load_config(cfg_file)
            self.assertEqual(cfg.schemas, ["HR", "SALES"])
            self.assertFalse(cfg.is_all_schemas)

            # Test ALL mode
            cfg_file_all = root / "leai_all.yml"
            cfg_file_all.write_text(
                """
                dsn: "oracle://usr:pwd@localhost:1521/X"
                schemas: "ALL"
                """,
                encoding="utf-8",
            )
            cfg_all = load_config(cfg_file_all)
            self.assertTrue(cfg_all.is_all_schemas)
            self.assertEqual(cfg_all.schemas, ["ALL"])

    def test_multi_schema_pipeline_generates_isolated_folders(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_dir = root / "raw"
            ann_dir = root / "annotations"
            docs_dir = root / "docs"

            schema_hr = SchemaMetadata(schema_name="HR", tables=[TableMeta(name="EMPLOYEES", columns=[ColumnMeta(name="ID", data_type="NUMBER", nullable=False)])])
            schema_sales = SchemaMetadata(schema_name="SALES", tables=[TableMeta(name="ORDERS", columns=[ColumnMeta(name="ID", data_type="NUMBER", nullable=False)])])

            save_raw_schema(schema_hr, raw_dir, multi_schema=True)
            save_raw_schema(schema_sales, raw_dir, multi_schema=True)

            self.assertTrue((raw_dir / "HR" / "tables" / "EMPLOYEES.json").exists())
            self.assertTrue((raw_dir / "SALES" / "tables" / "ORDERS.json").exists())

            # Test multi-schema loading
            loaded_schemas = load_raw_schemas(raw_dir)
            self.assertEqual(len(loaded_schemas), 2)
            self.assertEqual({s.schema_name for s in loaded_schemas}, {"HR", "SALES"})

            # Compile to Markdown
            for s in loaded_schemas:
                write_schema_docs(s, docs_dir, annotations_path=ann_dir, multi_schema=True)

            self.assertTrue((docs_dir / "HR" / "tables" / "EMPLOYEES.md").exists())
            self.assertTrue((docs_dir / "SALES" / "tables" / "ORDERS.md").exists())
            self.assertTrue((ann_dir / "HR" / "tables" / "EMPLOYEES.yml").exists())

    def test_write_table_docs_preserves_manual_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = Path(tmp)
            path = docs_dir / "tables" / "FUNCIONARIOS.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "\n".join(
                    [
                        "# TABLE: FUNCIONARIOS",
                        "",
                        "## Documentação humana",
                        "",
                        MANUAL_START,
                        "Regra de negócio antiga.",
                        MANUAL_END,
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            table = TableMeta(
                name="FUNCIONARIOS",
                columns=[ColumnMeta(name="ID", data_type="NUMBER", nullable=False)],
                primary_keys=["ID"],
            )
            write_table_docs([table], docs_dir)

            content = path.read_text(encoding="utf-8")
            self.assertIn("Regra de negócio antiga.", content)
            self.assertIn("| ID | NUMBER | NÃO |  |  |", content)

    def test_oracle_url_dsn_is_parsed_to_connect_kwargs(self):
        dsn = "oracle://usuario:senha@localhost:1521/ORCLPDB1"
        kwargs = _build_connect_kwargs(dsn)
        self.assertEqual(kwargs["user"], "usuario")
        self.assertEqual(kwargs["password"], "senha")
        self.assertEqual(kwargs["dsn"], "localhost:1521/ORCLPDB1")

    def test_like_pattern_to_regex_handles_bin_and_wildcards(self):
        regex = _like_pattern_to_regex("BIN$%")
        self.assertTrue(regex.match("BIN$F012345678==$0"))
        self.assertFalse(regex.match("FUNCIONARIOS"))

        regex_sys = _like_pattern_to_regex("SYS_%")
        self.assertTrue(regex_sys.match("SYS_USER"))
        self.assertFalse(regex_sys.match("SYS"))

    def test_render_table_markdown_renders_default_and_sanitizes_newlines(self):
        table = TableMeta(
            name="TESTE",
            columns=[
                ColumnMeta(
                    name="STATUS",
                    data_type="VARCHAR2(1)",
                    nullable=False,
                    default="'A'",
                    comment="Status do registro\nLinha 2",
                )
            ],
        )
        md = render_table_markdown(table)
        self.assertIn("| Coluna | Tipo | Nulo | Padrão | Comentário |", md)
        self.assertIn("| STATUS | VARCHAR2(1) | NÃO | 'A' | Status do registro Linha 2 |", md)

    def test_split_package_source_extracts_procedures_and_functions(self):
        plsql = """
        PACKAGE BODY PKG_FOLHA AS
          PROCEDURE CALCULA_INSS(p_id IN NUMBER) IS
          BEGIN
            NULL;
          END CALCULA_INSS;

          FUNCTION CALCULA_IRRF(p_salario IN NUMBER) RETURN NUMBER IS
          BEGIN
            RETURN 0;
          END CALCULA_IRRF;
        END PKG_FOLHA;
        """
        subs = _split_package_source("PKG_FOLHA", plsql)
        self.assertEqual(len(subs), 2)
        self.assertEqual(subs[0].name, "CALCULA_INSS")
        self.assertEqual(subs[0].subprogram_type, "PROCEDURE")
        self.assertEqual(subs[1].name, "CALCULA_IRRF")
        self.assertEqual(subs[1].subprogram_type, "FUNCTION")

    def test_package_splitting_generates_subprogram_markdowns_and_annotations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs_dir = root / "docs"
            ann_dir = root / "annotations"

            code_pkg = CodeObjectMeta(
                name="PKG_FOLHA",
                object_type="PACKAGE BODY",
                subprograms=[
                    SubprogramMeta(package_name="PKG_FOLHA", name="CALCULA_INSS", subprogram_type="PROCEDURE", source="PROCEDURE CALCULA_INSS IS BEGIN NULL; END;"),
                    SubprogramMeta(package_name="PKG_FOLHA", name="CALCULA_IRRF", subprogram_type="FUNCTION", source="FUNCTION CALCULA_IRRF RETURN NUMBER IS BEGIN RETURN 0; END;"),
                ],
            )
            schema = SchemaMetadata(code_objects=[code_pkg])
            generated_md, generated_ann = write_schema_docs(schema, docs_dir, annotations_path=ann_dir)

            # 1 Global Pkg + 2 Subprograms + 1 INDEX.md = 4 generated files
            self.assertEqual(len(generated_md), 4)
            self.assertEqual(len(generated_ann), 3)

            # Verify existence of sub-files
            self.assertTrue((docs_dir / "package_bodys" / "PKG_FOLHA.md").exists())
            self.assertTrue((docs_dir / "package_bodys" / "PKG_FOLHA" / "CALCULA_INSS.md").exists())
            self.assertTrue((docs_dir / "package_bodys" / "PKG_FOLHA" / "CALCULA_IRRF.md").exists())
            self.assertTrue((docs_dir / "INDEX.md").exists())

            # Verify subprogram annotations
            self.assertTrue((ann_dir / "package_bodys" / "PKG_FOLHA" / "CALCULA_INSS.yml").exists())

            # Content of subprogram markdown
            inss_md = (docs_dir / "package_bodys" / "PKG_FOLHA" / "CALCULA_INSS.md").read_text(encoding="utf-8")
            self.assertIn("# PROCEDURE: PKG_FOLHA.CALCULA_INSS", inss_md)
            self.assertIn("PROCEDURE CALCULA_INSS IS BEGIN NULL; END;", inss_md)

    def test_raw_schema_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw_dir = Path(tmp) / "raw"
            schema = SchemaMetadata(
                tables=[TableMeta(name="T1", columns=[ColumnMeta(name="ID", data_type="NUMBER", nullable=False)])],
                views=[ViewMeta(name="V1", text="SELECT 1 FROM DUAL")],
            )
            saved = save_raw_schema(schema, raw_dir)
            self.assertEqual(len(saved), 2)
            self.assertTrue((raw_dir / "tables" / "T1.json").exists())
            self.assertTrue((raw_dir / "views" / "V1.json").exists())

            loaded_schema = load_raw_schema(raw_dir)
            self.assertEqual(len(loaded_schema.tables), 1)
            self.assertEqual(loaded_schema.tables[0].name, "T1")
            self.assertEqual(len(loaded_schema.views), 1)
            self.assertEqual(loaded_schema.views[0].name, "V1")

    def test_offline_compile_from_raw_and_annotations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_dir = root / "raw"
            ann_dir = root / "annotations"
            docs_dir = root / "docs"

            schema = SchemaMetadata(tables=[TableMeta(name="T1", columns=[ColumnMeta(name="ID", data_type="NUMBER", nullable=False)])])
            save_raw_schema(schema, raw_dir)

            # Modify annotation
            ann_file = ann_dir / "tables" / "T1.yml"
            ann_file.parent.mkdir(parents=True, exist_ok=True)
            ann_file.write_text("description: 'Anotação offline'\nbusiness_rules:\n  - 'Regra offline'", encoding="utf-8")

            # Compile offline
            loaded_schema = load_raw_schema(raw_dir)
            write_schema_docs(loaded_schema, docs_dir, annotations_path=ann_dir)

            md = (docs_dir / "tables" / "T1.md").read_text(encoding="utf-8")
            self.assertIn("Anotação offline", md)
            self.assertIn("- Regra offline", md)

    def test_ensure_annotation_stub_preserves_existing_and_appends_new_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            ann_file = Path(tmp) / "tables" / "T1.yml"
            ann_file.parent.mkdir(parents=True, exist_ok=True)
            ann_file.write_text(
                """
                description: "Descrição de negócio existente"
                business_rules:
                  - "Regra mantida 100%"
                columns:
                  COD: "Código legado"
                """,
                encoding="utf-8",
            )

            from leai.annotations import ensure_annotation_stub
            # Simulate new 'EMAIL' column coming from RAW/database
            ann = ensure_annotation_stub(ann_file, column_names=["COD", "EMAIL"])

            self.assertEqual(ann.description, "Descrição de negócio existente")
            self.assertEqual(ann.business_rules, ["Regra mantida 100%"])
            self.assertEqual(ann.columns["COD"], "Código legado")
            self.assertEqual(ann.columns["EMAIL"], "")

    def test_audit_fields_serialization_and_markdown_rendering(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_dir = root / "raw"
            docs_dir = root / "docs"

            tbl = TableMeta(
                name="AUDIT_TBL",
                columns=[ColumnMeta(name="ID", data_type="NUMBER", nullable=False)],
                last_ddl_time="2026-08-13 14:30:00",
                last_modified_by="HR",
            )
            schema = SchemaMetadata(tables=[tbl])

            # Test saving and loading RAW
            save_raw_schema(schema, raw_dir)
            loaded = load_raw_schema(raw_dir)
            self.assertEqual(loaded.tables[0].last_ddl_time, "2026-08-13 14:30:00")
            self.assertEqual(loaded.tables[0].last_modified_by, "HR")

            # Test Markdown rendering
            write_schema_docs(loaded, docs_dir)
            md = (docs_dir / "tables" / "AUDIT_TBL.md").read_text(encoding="utf-8")
            self.assertIn("**Última Modificação DDL:** 2026-08-13 14:30:00 (por `HR`)", md)

    def test_raw_schema_type_and_type_body_loading(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw_dir = Path(tmp) / "raw"
            type_obj = CodeObjectMeta(name="TP_PESSOA", object_type="TYPE", source="TYPE TP_PESSOA AS OBJECT (id NUMBER);")
            type_body_obj = CodeObjectMeta(name="TP_PESSOA", object_type="TYPE BODY", source="TYPE BODY TP_PESSOA AS END;")
            schema = SchemaMetadata(code_objects=[type_obj, type_body_obj])
            save_raw_schema(schema, raw_dir)

            loaded = load_raw_schema(raw_dir)
            self.assertEqual(len(loaded.code_objects), 2)
            types_found = {c.object_type for c in loaded.code_objects}
            self.assertEqual(types_found, {"TYPE", "TYPE BODY"})

    def test_write_schema_docs_object_types_filtering(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs_dir = root / "docs"
            ann_dir = root / "annotations"

            tbl = TableMeta(name="TBL1", columns=[ColumnMeta(name="ID", data_type="NUMBER", nullable=False)])
            view = ViewMeta(name="VIEW1", text="SELECT 1 FROM DUAL")
            schema = SchemaMetadata(tables=[tbl], views=[view])

            # Filter only tables
            gen_md, gen_ann = write_schema_docs(schema, docs_dir, annotations_path=ann_dir, object_types=["tables"])
            self.assertTrue((docs_dir / "tables" / "TBL1.md").exists())
            self.assertFalse((docs_dir / "views" / "VIEW1.md").exists())

    def test_sync_schema_annotations_only_generates_annotations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs_dir = root / "docs"
            ann_dir = root / "annotations"

            tbl = TableMeta(name="TBL1", columns=[ColumnMeta(name="ID", data_type="NUMBER", nullable=False)])
            schema = SchemaMetadata(tables=[tbl])

            from leai.docs import sync_schema_annotations
            gen_ann = sync_schema_annotations(schema, ann_dir)
            self.assertEqual(len(gen_ann), 1)
            self.assertTrue((ann_dir / "tables" / "TBL1.yml").exists())
            self.assertFalse((docs_dir / "tables" / "TBL1.md").exists())

    def test_trace_raw_dependencies_resolves_full_neighborhood(self):
        dept = TableMeta(name="DEPARTAMENTOS", columns=[ColumnMeta(name="ID", data_type="NUMBER", nullable=False)])
        func = TableMeta(
            name="FUNCIONARIOS",
            columns=[
                ColumnMeta(name="ID", data_type="NUMBER", nullable=False),
                ColumnMeta(name="DEP_ID", data_type="NUMBER", nullable=False),
            ],
            foreign_keys=[
                ForeignKeyMeta(name="FK_FUNC_DEP", column="DEP_ID", referenced_table="DEPARTAMENTOS", referenced_column="ID")
            ],
        )
        dep = TableMeta(
            name="DEPENDENTES",
            columns=[
                ColumnMeta(name="ID", data_type="NUMBER", nullable=False),
                ColumnMeta(name="FUNC_ID", data_type="NUMBER", nullable=False),
            ],
            foreign_keys=[
                ForeignKeyMeta(name="FK_DEP_FUNC", column="FUNC_ID", referenced_table="FUNCIONARIOS", referenced_column="ID")
            ],
        )
        vw = ViewMeta(name="VW_FOLHA", text="SELECT f.ID, f.DEP_ID FROM FUNCIONARIOS f")
        trg = TriggerMeta(name="TRG_FUNC_AUDIT", table_name="FUNCIONARIOS", trigger_type="BEFORE INSERT", triggering_event="INSERT")

        schema = SchemaMetadata(
            tables=[dept, func, dep],
            views=[vw],
            triggers=[trg],
        )

        from leai.raw import trace_raw_dependencies
        res = trace_raw_dependencies([schema], "FUNCIONARIOS")

        self.assertEqual(res.focal_name, "FUNCIONARIOS")
        self.assertEqual(res.focal_type, "TABLE")
        self.assertIsNotNone(res.focal_object)

        # Must contain 4 dependency links (outgoing FK, incoming FK, View, Trigger)
        self.assertEqual(len(res.dependencies), 4)

        rel_types = {d.relation_type for d in res.dependencies}
        self.assertIn("FK_REFERENCES", rel_types)
        self.assertIn("FK_REFERENCED_BY", rel_types)
        self.assertIn("READS/SELECTS", rel_types)
        self.assertIn("TRIGGER_ON", rel_types)

        self.assertEqual(len(res.related_tables), 2)  # DEPARTAMENTOS and DEPENDENTES
        self.assertEqual(len(res.related_views), 1)   # VW_FOLHA
        self.assertEqual(len(res.related_triggers), 1) # TRG_FUNC_AUDIT

    def test_dossier_markdown_and_mermaid_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs_dir = root / "docs"
            ann_dir = root / "annotations"

            func = TableMeta(
                name="FUNCIONARIOS",
                comment="Tabela de colaboradores da empresa",
                columns=[ColumnMeta(name="ID", data_type="NUMBER", nullable=False)],
            )
            schema = SchemaMetadata(tables=[func])

            from leai.docs import write_dossier_doc, write_rag_json_file
            from leai.raw import trace_raw_dependencies

            res = trace_raw_dependencies([schema], "FUNCIONARIOS")
            out_file = docs_dir / "dossiers" / "FUNCIONARIOS.md"

            # Write pre-existing file with manual section
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_text(f"{MANUAL_START}\nDocumentação humana prévia do dossiê\n{MANUAL_END}\n", encoding="utf-8")

            written = write_dossier_doc(res, out_file, annotations_path=ann_dir)
            self.assertTrue(written.exists())

            content = written.read_text(encoding="utf-8")
            self.assertIn("rag_metadata:", content)
            self.assertIn("entity: FUNCIONARIOS", content)
            self.assertIn("Raio-X de Impacto Técnico:", content)
            self.assertIn("## 🧠 Resumo Narrativo Semântico (RAG Ready)", content)
            self.assertIn("# DOSSIÊ DE IMPACTO E DOCUMENTAÇÃO FOCAL: FUNCIONARIOS", content)
            self.assertIn("Tabela de colaboradores da empresa", content)
            self.assertIn("Documentação humana prévia do dossiê", content)

            # Test RAG JSON generation
            json_file = docs_dir / "chunks" / "FUNCIONARIOS.json"
            written_json = write_rag_json_file(res, json_file, annotations_path=ann_dir)
            self.assertTrue(written_json.exists())

            import json
            chunk_data = json.loads(written_json.read_text(encoding="utf-8"))
            self.assertEqual(chunk_data["entity"], "FUNCIONARIOS")
            self.assertEqual(chunk_data["chunk_id"], "trace_funcionarios")
            self.assertIn("text_for_embedding", chunk_data)
            self.assertIn("Tabela de colaboradores da empresa", chunk_data["text_for_embedding"])

    def test_trace_raw_dependencies_multilevel_depth_and_cycle_prevention(self):
        emp = TableMeta(name="EMPRESAS", columns=[ColumnMeta(name="ID", data_type="NUMBER", nullable=False)])
        dept = TableMeta(
            name="DEPARTAMENTOS",
            columns=[ColumnMeta(name="ID", data_type="NUMBER", nullable=False), ColumnMeta(name="EMP_ID", data_type="NUMBER", nullable=False)],
            foreign_keys=[ForeignKeyMeta(name="FK_DEP_EMP", column="EMP_ID", referenced_table="EMPRESAS", referenced_column="ID")],
        )
        func = TableMeta(
            name="FUNCIONARIOS",
            columns=[ColumnMeta(name="ID", data_type="NUMBER", nullable=False), ColumnMeta(name="DEP_ID", data_type="NUMBER", nullable=False)],
            foreign_keys=[ForeignKeyMeta(name="FK_FUNC_DEP", column="DEP_ID", referenced_table="DEPARTAMENTOS", referenced_column="ID")],
        )
        dep = TableMeta(
            name="DEPENDENTES",
            columns=[ColumnMeta(name="ID", data_type="NUMBER", nullable=False), ColumnMeta(name="FUNC_ID", data_type="NUMBER", nullable=False)],
            foreign_keys=[ForeignKeyMeta(name="FK_DEP_FUNC", column="FUNC_ID", referenced_table="FUNCIONARIOS", referenced_column="ID")],
        )
        hist = TableMeta(
            name="HISTORICO_DEP",
            columns=[ColumnMeta(name="ID", data_type="NUMBER", nullable=False), ColumnMeta(name="DEP_ID", data_type="NUMBER", nullable=False)],
            foreign_keys=[ForeignKeyMeta(name="FK_HIST_DEP", column="DEP_ID", referenced_table="DEPENDENTES", referenced_column="ID")],
        )

        # Cycle: Trigger on EMPRESAS referencing FUNCIONARIOS
        trg_cycle = TriggerMeta(name="TRG_EMP_CYCLE", table_name="EMPRESAS", trigger_type="AFTER UPDATE", triggering_event="UPDATE")

        schema = SchemaMetadata(
            tables=[emp, dept, func, dep, hist],
            triggers=[trg_cycle],
        )

        from leai.raw import trace_raw_dependencies

        # 1. Test Depth = 1 (Direct neighbors only)
        res_depth1 = trace_raw_dependencies([schema], "FUNCIONARIOS", max_depth=1)
        rel_tables_d1 = {t.name for t in res_depth1.related_tables}
        self.assertEqual(rel_tables_d1, {"DEPARTAMENTOS", "DEPENDENTES"})
        self.assertNotIn("EMPRESAS", rel_tables_d1)
        self.assertNotIn("HISTORICO_DEP", rel_tables_d1)

        # 2. Test Depth = 2 (Direct + Indirect neighbors)
        res_depth2 = trace_raw_dependencies([schema], "FUNCIONARIOS", max_depth=2)
        rel_tables_d2 = {t.name for t in res_depth2.related_tables}
        self.assertEqual(rel_tables_d2, {"DEPARTAMENTOS", "DEPENDENTES", "EMPRESAS", "HISTORICO_DEP"})

        # Validate recorded link depths
        depth_map = {(d.source_name, d.target_name): d.depth for d in res_depth2.dependencies}
        self.assertEqual(depth_map.get(("FUNCIONARIOS", "DEPARTAMENTOS")), 1)
        self.assertEqual(depth_map.get(("DEPENDENTES", "FUNCIONARIOS")), 1)
        self.assertEqual(depth_map.get(("DEPARTAMENTOS", "EMPRESAS")), 2)
        self.assertEqual(depth_map.get(("HISTORICO_DEP", "DEPENDENTES")), 2)

    def test_annotation_use_cases_and_markdown_rendering(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            from leai.annotations import load_annotation, save_annotation
            from leai.docs import render_table_markdown
            from leai.models import ObjectAnnotation

            ann_file = Path(tmpdir) / "EMPLOYEES.yml"
            ann = ObjectAnnotation(
                description="Tabela de empregados",
                business_rules=["Regra 1: Salário maior que zero"],
                use_cases=[
                    "SELECT id, nome FROM employees WHERE status = 'A';",
                    "Relatório de folha de pagamento por departamento",
                ],
                columns={"ID": "Identificador único"},
            )
            save_annotation(ann_file, ann)
            self.assertTrue(ann_file.exists())

            loaded = load_annotation(ann_file)
            self.assertEqual(len(loaded.use_cases), 2)
            self.assertIn("SELECT id, nome FROM employees WHERE status = 'A';", loaded.use_cases[0])

            table = TableMeta(
                name="EMPLOYEES",
                columns=[ColumnMeta(name="ID", data_type="NUMBER", nullable=False)],
            )
            md = render_table_markdown(table, annotation=loaded)
            self.assertIn("## Casos de uso e Consultas de Exemplo", md)
            self.assertIn("```sql\nSELECT id, nome FROM employees WHERE status = 'A';\n```", md)
            self.assertIn("- Relatório de folha de pagamento por departamento", md)

    def test_write_schema_docs_with_traces_and_rag_chunks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            from leai.docs import write_schema_docs
            from leai.models import ColumnMeta, ForeignKeyMeta, SchemaMetadata, TableMeta

            root = Path(tmpdir)
            docs_dir = root / "docs"
            ann_dir = root / "annotations"

            dept = TableMeta(
                name="DEPARTMENTS",
                columns=[ColumnMeta(name="ID", data_type="NUMBER", nullable=False)],
                primary_keys=["ID"],
            )
            emp = TableMeta(
                name="EMPLOYEES",
                columns=[
                    ColumnMeta(name="ID", data_type="NUMBER", nullable=False),
                    ColumnMeta(name="DEPT_ID", data_type="NUMBER", nullable=False),
                ],
                primary_keys=["ID"],
                foreign_keys=[
                    ForeignKeyMeta(name="FK_EMP_DEPT", column="DEPT_ID", referenced_table="DEPARTMENTS", referenced_column="ID"),
                ],
            )
            schema = SchemaMetadata(schema_name="HR", tables=[dept, emp])

            gen_md, gen_ann = write_schema_docs(
                schema,
                doc_path=docs_dir,
                annotations_path=ann_dir,
                with_traces=True,
                generate_rag_chunks=True,
            )

            # Check INDEX.md
            index_file = docs_dir / "INDEX.md"
            self.assertTrue(index_file.exists())
            index_content = index_file.read_text(encoding="utf-8")
            self.assertIn("Catálogo e Matriz de Governança", index_content)
            self.assertIn("EMPLOYEES", index_content)
            self.assertIn("DEPARTMENTS", index_content)

            # Check EMPLOYEES.md contains unified trace and Mermaid
            emp_md_file = docs_dir / "tables" / "EMPLOYEES.md"
            self.assertTrue(emp_md_file.exists())
            emp_content = emp_md_file.read_text(encoding="utf-8")
            self.assertIn("rag_metadata:", emp_content)
            self.assertIn("Raio-X de Impacto Técnico e Risco", emp_content)
            self.assertIn("DEPARTMENTS", emp_content)
            self.assertIn("```mermaid", emp_content)

            # Check RAG chunks exported to docs/chunks/
            chunks_dir = docs_dir / "chunks"
            self.assertTrue(chunks_dir.exists())
            self.assertTrue((chunks_dir / "EMPLOYEES.json").exists())
            self.assertTrue((chunks_dir / "DEPARTMENTS.json").exists())

            import json
            emp_chunk = json.loads((chunks_dir / "EMPLOYEES.json").read_text(encoding="utf-8"))
            self.assertEqual(emp_chunk["entity"], "EMPLOYEES")
            self.assertIn("text_for_embedding", emp_chunk)


if __name__ == "__main__":
    unittest.main()



