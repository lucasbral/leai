from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from leai.ai.tools import (
    get_table_schema,
    lookup_business_term,
    search_business_documentation,
    search_column_comments,
    search_database_objects,
)
from leai.ask_rag import build_rag_context
from leai.cli import app
from leai.config import LeaiConfig, SeaweedFSConfig, StorageConfig
from leai.models import (
    BusinessGlossary,
    ColumnMeta,
    GlossaryTerm,
    ObjectAnnotation,
    SchemaMetadata,
    TableMeta,
)

runner = CliRunner()


def _make_remote_config(tmp_path: Path) -> LeaiConfig:
    cfg = LeaiConfig(
        rawPath=tmp_path / "non_existent_raw",
        annotationsPath=tmp_path / "non_existent_annotations",
        docPath=tmp_path / "non_existent_docs",
        schemas=["RH"],
        storage=StorageConfig(
            seaweedfs=SeaweedFSConfig(
                enabled=True,
                endpoint_url="https://s3.example.com",
                bucket="test-bucket",
            )
        ),
    )
    return cfg


def _make_sample_schema() -> SchemaMetadata:
    col_id = ColumnMeta(name="ID", data_type="NUMBER", nullable=False)
    col_sal = ColumnMeta(name="SALARIO", data_type="NUMBER(10,2)", nullable=True)
    table = TableMeta(name="FUNCIONARIOS", columns=[col_id, col_sal], primary_keys=["ID"])
    return SchemaMetadata(schema_name="RH", tables=[table])


class TestRemoteAITools:
    def test_lookup_business_term_remote(self, tmp_path: Path):
        cfg = _make_remote_config(tmp_path)
        term = GlossaryTerm(
            term="SERVIDOR_ATIVO",
            definition="Servidor em efetivo exercício",
            canonical_filter="STATUS = 'A'",
            tags=["rh", "folha"],
        )
        remote_glossary = BusinessGlossary(terms=[term])

        with patch("leai.storage.SeaweedFSStorage.load_glossary", return_value=remote_glossary):
            res = lookup_business_term(config=cfg, query="servidor ativo")
            assert res["total_matches"] == 1
            assert res["results"][0]["term"] == "SERVIDOR_ATIVO"
            assert res["results"][0]["canonical_filter"] == "STATUS = 'A'"

    def test_get_table_schema_remote_annotations(self, tmp_path: Path):
        cfg = _make_remote_config(tmp_path)
        schema = _make_sample_schema()

        remote_ann = ObjectAnnotation(
            description="Tabela de cadastro geral de servidores e colaboradores.",
            business_rules=["Apenas servidores com posse registrada podem receber remuneração"],
            tags=["rh", "folha"],
            columns={"SALARIO": "Remuneração bruta mensal com gratificações"},
        )

        with patch("leai.storage.SeaweedFSStorage.load_annotation", return_value=remote_ann):
            data = get_table_schema([schema], config=cfg, table_name="FUNCIONARIOS")
            assert data["table_name"] == "FUNCIONARIOS"
            assert data["business_description"] == "Tabela de cadastro geral de servidores e colaboradores."
            assert len(data["business_rules"]) == 1
            assert "Apenas servidores com posse registrada" in data["business_rules"][0]
            # Column comment from remote annotation
            sal_col = next(c for c in data["columns"] if c["name"] == "SALARIO")
            assert sal_col["description"] == "Remuneração bruta mensal com gratificações"

    def test_search_column_comments_remote_annotations(self, tmp_path: Path):
        cfg = _make_remote_config(tmp_path)
        schema = _make_sample_schema()

        remote_ann = ObjectAnnotation(
            columns={"SALARIO": "Remuneração bruta mensal com gratificações"},
        )

        with patch("leai.storage.SeaweedFSStorage.load_annotation", return_value=remote_ann):
            matches = search_column_comments([schema], query="gratificacoes", config=cfg)
            assert len(matches) == 1
            assert matches[0]["column_name"] == "SALARIO"
            assert "Remuneração bruta mensal com gratificações" in matches[0]["comment"]

    def test_search_database_objects_remote_annotations(self, tmp_path: Path):
        cfg = _make_remote_config(tmp_path)
        schema = _make_sample_schema()

        remote_ann = ObjectAnnotation(
            description="Cadastro mestre de servidores públicos",
        )

        with patch("leai.storage.SeaweedFSStorage.load_annotation", return_value=remote_ann):
            res = search_database_objects([schema], query="mestre", config=cfg)
            assert len(res) == 1
            assert res[0]["name"] == "FUNCIONARIOS"
            assert "Cadastro mestre de servidores públicos" in res[0]["comment"]

    def test_search_business_documentation_remote(self, tmp_path: Path):
        cfg = _make_remote_config(tmp_path)
        schema = _make_sample_schema()

        remote_ann = ObjectAnnotation(
            description="Módulo de folha de pagamento e contracheque",
            business_rules=["Cálculo mensal obrigatório"],
        )

        with (
            patch(
                "leai.storage.SeaweedFSStorage.list_annotated_objects",
                return_value={("RH", "tables", "FUNCIONARIOS")},
            ),
            patch("leai.storage.SeaweedFSStorage.load_annotation", return_value=remote_ann),
        ):
            res = search_business_documentation([schema], config=cfg, query="FUNCIONARIOS")
            assert len(res) >= 1
            matched = next((r for r in res if r["object_name"] == "FUNCIONARIOS"), None)
            assert matched is not None
            assert matched["description"] == "Módulo de folha de pagamento e contracheque"

    def test_build_rag_context_remote_annotations(self, tmp_path: Path):
        cfg = _make_remote_config(tmp_path)
        schema = _make_sample_schema()

        remote_ann = ObjectAnnotation(
            description="Dossiê de servidores ativos",
            business_rules=["Regra de negócio confidencial de RH"],
        )

        with patch("leai.storage.SeaweedFSStorage.load_annotation", return_value=remote_ann):
            ctx, detected = build_rag_context(
                question="Quais são as regras da tabela FUNCIONARIOS?",
                schemas=[schema],
                config=cfg,
                include_catalog=False,
            )
            assert "FUNCIONARIOS" in detected
            assert "Regra de negócio confidencial de RH" in ctx

    def test_cli_agent_command_remote_storage(self, tmp_path: Path):
        cfg = _make_remote_config(tmp_path)
        schema = _make_sample_schema()
        cfg_file = tmp_path / "leai.yml"
        cfg_file.write_text("schemas:\n  - RH\nstorage:\n  seaweedfs:\n    enabled: true\n", encoding="utf-8")

        mock_client = MagicMock()
        mock_client.model = "test-model"

        with (
            patch("leai.cli.load_config", return_value=cfg),
            patch("leai.cli.load_raw_schemas", return_value=[schema]) as mock_load,
            patch("leai.cli.get_llm_client", return_value=mock_client),
            patch("leai.ai.subagents.execute_subagent", return_value="Análise de catálogo concluída."),
        ):
            result = runner.invoke(
                app,
                ["agent", "run", "catalog_researcher", "onde fica o salario?", "-c", str(cfg_file)],
            )
            assert result.exit_code == 0
            assert "Análise de catálogo concluída." in result.output
            # Check that storage was passed to load_raw_schemas
            mock_load.assert_called_once()
            _, kwargs = mock_load.call_args
            assert kwargs.get("storage") is not None

    def test_cli_workflow_command_remote_storage(self, tmp_path: Path):
        cfg = _make_remote_config(tmp_path)
        schema = _make_sample_schema()
        cfg_file = tmp_path / "leai.yml"
        cfg_file.write_text("schemas:\n  - RH\nstorage:\n  seaweedfs:\n    enabled: true\n", encoding="utf-8")

        mock_client = MagicMock()
        mock_wf = MagicMock()
        mock_wf.name = "impact-analysis"
        mock_wf.description = "Impact analysis workflow"
        mock_res = MagicMock()
        mock_res.report_markdown = "Relatório de impacto concluído."
        mock_res.total_duration_seconds = 1.2
        mock_wf.run.return_value = mock_res

        with (
            patch("leai.cli.load_config", return_value=cfg),
            patch("leai.cli.load_raw_schemas", return_value=[schema]) as mock_load,
            patch("leai.cli.get_llm_client", return_value=mock_client),
            patch("leai.workflows.get_workflow", return_value=mock_wf),
        ):
            result = runner.invoke(
                app,
                ["workflow", "run", "impact", "FUNCIONARIOS", "-c", str(cfg_file)],
            )
            assert result.exit_code == 0
            assert "Relatório de impacto concluído." in result.output
            mock_load.assert_called_once()
            _, kwargs = mock_load.call_args
            assert kwargs.get("storage") is not None
