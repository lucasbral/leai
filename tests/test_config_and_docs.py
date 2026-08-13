import tempfile
import unittest
from pathlib import Path

from leai.config import load_config
from leai.docs import (
    MANUAL_END,
    MANUAL_START,
    render_code_object_markdown,
    render_index_markdown,
    render_mview_markdown,
    render_sequence_markdown,
    render_synonym_markdown,
    render_table_markdown,
    render_trigger_markdown,
    render_view_markdown,
    write_schema_docs,
    write_table_docs,
)
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
from leai.models import SubprogramMeta
from leai.oracle import _build_connect_kwargs, _format_data_type, _like_pattern_to_regex, _split_package_source
from leai.raw import load_raw_schema, save_raw_schema


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
            self.assertEqual(cfg.include, ["FUNCIONARIOS"])
            self.assertEqual(cfg.rawPath, (root / "raw").resolve())
            self.assertEqual(cfg.docPath, (root / "docs").resolve())
            self.assertEqual(cfg.annotationsPath, (root / "annotations").resolve())

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

            # 1 Pkg Global + 2 Subprogramas = 3 arquivos gerados
            self.assertEqual(len(generated_md), 3)
            self.assertEqual(len(generated_ann), 3)

            # Verificar existência dos sub-arquivos
            self.assertTrue((docs_dir / "package_bodys" / "PKG_FOLHA.md").exists())
            self.assertTrue((docs_dir / "package_bodys" / "PKG_FOLHA" / "CALCULA_INSS.md").exists())
            self.assertTrue((docs_dir / "package_bodys" / "PKG_FOLHA" / "CALCULA_IRRF.md").exists())

            # Verificar anotações dos subprogramas
            self.assertTrue((ann_dir / "package_bodys" / "PKG_FOLHA" / "CALCULA_INSS.yml").exists())

            # Conteúdo do sub-markdown
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

            # Modificar anotação
            ann_file = ann_dir / "tables" / "T1.yml"
            ann_file.parent.mkdir(parents=True, exist_ok=True)
            ann_file.write_text("description: 'Anotação offline'\nbusiness_rules:\n  - 'Regra offline'", encoding="utf-8")

            # Compilar offline
            loaded_schema = load_raw_schema(raw_dir)
            write_schema_docs(loaded_schema, docs_dir, annotations_path=ann_dir)

            md = (docs_dir / "tables" / "T1.md").read_text(encoding="utf-8")
            self.assertIn("Anotação offline", md)
            self.assertIn("- Regra offline", md)


if __name__ == "__main__":
    unittest.main()

