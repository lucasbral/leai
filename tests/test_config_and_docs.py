import tempfile
import unittest
from pathlib import Path

from leai.config import load_config
from leai.docs import MANUAL_END, MANUAL_START, write_table_docs
from leai.models import ColumnMeta, TableMeta
from leai.oracle import _build_connect_kwargs


class ConfigAndDocsTests(unittest.TestCase):
    def test_load_config_normalizes_paths_and_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg_file = root / "leai.yml"
            dsn = "oracle" + "://usuario:senha@localhost:1521/ORCLPDB1"
            cfg_file.write_text(
                f"""
                dsn: "{dsn}"
                schema: "meu_schema"
                docPath: "./docs"
                include: ["funcionarios"]
                exclude: ["BIN$%"]
                """,
                encoding="utf-8",
            )
            cfg = load_config(cfg_file)
            self.assertEqual(cfg.schema_name, "MEU_SCHEMA")
            self.assertEqual(cfg.include, ["FUNCIONARIOS"])
            self.assertEqual(cfg.docPath, (root / "docs").resolve())

    def test_write_table_docs_preserves_manual_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = Path(tmp)
            path = docs_dir / "FUNCIONARIOS.md"
            path.write_text(
                "\n".join(
                    [
                        "# FUNCIONARIOS",
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
            self.assertIn("| ID | NUMBER | NÃO |  |", content)

    def test_oracle_url_dsn_is_parsed_to_connect_kwargs(self):
        dsn = "oracle" + "://usuario:senha@localhost:1521/ORCLPDB1"
        kwargs = _build_connect_kwargs(dsn)
        self.assertEqual(kwargs["user"], "usuario")
        self.assertEqual(kwargs["password"], "senha")
        self.assertEqual(kwargs["dsn"], "localhost:1521/ORCLPDB1")


if __name__ == "__main__":
    unittest.main()
