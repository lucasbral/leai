from __future__ import annotations
import json
from pathlib import Path

from leai.annotations import ensure_annotation_stub
from leai.models import (
    CodeObjectMeta,
    DependencyLink,
    IndexMeta,
    MaterializedViewMeta,
    ObjectAnnotation,
    ObjectTraceResult,
    SchemaMetadata,
    SequenceMeta,
    SubprogramMeta,
    SynonymMeta,
    TableMeta,
    TriggerMeta,
    ViewMeta,
)

MANUAL_START = "<!-- LEAI:MANUAL:START -->"
MANUAL_END = "<!-- LEAI:MANUAL:END -->"


def _extract_manual_section(content: str | None) -> str:
    if not content:
        return ""
    start = content.find(MANUAL_START)
    end = content.find(MANUAL_END)
    if start == -1 or end == -1 or end <= start:
        return ""
    return content[start + len(MANUAL_START) : end].strip("\n")


def _render_manual_section(doc: str = "") -> list[str]:
    return ["", "## Documentação humana", "", MANUAL_START, doc or "", MANUAL_END, ""]


def _render_audit_meta(obj) -> list[str]:
    lines: list[str] = []
    last_ddl = getattr(obj, "last_ddl_time", None)
    modified_by = getattr(obj, "last_modified_by", None)
    created = getattr(obj, "created_at", None)

    parts: list[str] = []
    if last_ddl:
        by_str = f" (por `{modified_by}`)" if modified_by else ""
        parts.append(f"**Última Modificação DDL:** {last_ddl}{by_str}")
    if created:
        parts.append(f"**Data de Criação:** {created}")

    if parts:
        lines.append(" | ".join(parts))
        lines.append("")
    return lines


def _render_annotation_details(annotation: ObjectAnnotation | None) -> list[str]:
    if not annotation:
        return []
    lines: list[str] = []

    if annotation.tags:
        tags_str = ", ".join(annotation.tags)
        lines.extend(["", f"**Tags / Domínio de Negócio:** `{tags_str}`"])

    if annotation.warnings:
        lines.extend(["", "## Alertas e avisos técnicos", ""])
        for warn in annotation.warnings:
            lines.append(f"> [!WARNING]\n> {warn}")

    if annotation.related_objects:
        lines.extend(["", "## Relacionamentos de negócio", ""])
        for rel in annotation.related_objects:
            lines.append(f"- {rel}")

    return lines


def _render_business_rules(annotation: ObjectAnnotation | None) -> list[str]:
    lines = _render_annotation_details(annotation)
    if not annotation or not annotation.business_rules:
        return lines
    lines.extend(["", "## Regras de negócio", ""])
    for rule in annotation.business_rules:
        lines.append(f"- {rule}")
    return lines


def render_table_markdown(
    table: TableMeta,
    table_doc: str = "",
    column_docs: dict[str, str] | None = None,
    annotation: ObjectAnnotation | None = None,
) -> str:
    column_docs = column_docs or {}
    ann_cols = annotation.columns if annotation else {}
    lines = [f"# TABLE: {table.name}", "", "## Visão geral", ""]
    lines.extend(_render_audit_meta(table))
    table_desc = (
        (annotation and annotation.description)
        or table.comment
        or table_doc
        or "Sem descrição técnica no dicionário Oracle."
    )
    lines.append(table_desc.replace("\r\n", " ").replace("\n", " "))
    lines.extend(_render_business_rules(annotation))

    lines.extend(["", "## Colunas", "", "| Coluna | Tipo | Nulo | Padrão | Comentário |", "|---|---|---|---|---|"])

    for column in table.columns:
        raw_comment = ann_cols.get(column.name) or column_docs.get(column.name) or column.comment or ""
        comment_clean = raw_comment.replace("\r\n", " ").replace("\n", " ").replace("|", "\\|")
        default_clean = (column.default or "").replace("\r\n", " ").replace("\n", " ").replace("|", "\\|")
        lines.append(
            f"| {column.name} | {column.data_type} | {'SIM' if column.nullable else 'NÃO'} | {default_clean} | {comment_clean} |"
        )

    lines.extend(["", "## Chave primária", ""])
    lines.append(", ".join(table.primary_keys) if table.primary_keys else "Não definida")

    lines.extend(["", "## Chaves estrangeiras", ""])
    if table.foreign_keys:
        lines.append("| Constraint | Coluna | Referência |")
        lines.append("|---|---|---|")
        for fk in table.foreign_keys:
            lines.append(
                f"| {fk.name} | {fk.column} | {fk.referenced_table}.{fk.referenced_column} |"
            )
    else:
        lines.append("Nenhuma")

    lines.extend(_render_manual_section(table_doc))
    return "\n".join(lines)


def render_view_markdown(
    view: ViewMeta,
    view_doc: str = "",
    column_docs: dict[str, str] | None = None,
    annotation: ObjectAnnotation | None = None,
) -> str:
    column_docs = column_docs or {}
    ann_cols = annotation.columns if annotation else {}
    lines = [f"# VIEW: {view.name}", "", "## Visão geral", ""]
    desc = (annotation and annotation.description) or view.comment or view_doc or "Visão (View) do banco de dados Oracle."
    lines.append(desc.replace("\r\n", " ").replace("\n", " "))
    lines.extend(_render_business_rules(annotation))

    lines.extend(["", "## Colunas", "", "| Coluna | Tipo | Nulo | Padrão | Comentário |", "|---|---|---|---|---|"])

    for column in view.columns:
        raw_comment = ann_cols.get(column.name) or column_docs.get(column.name) or column.comment or ""
        comment_clean = raw_comment.replace("\r\n", " ").replace("\n", " ").replace("|", "\\|")
        default_clean = (column.default or "").replace("\r\n", " ").replace("\n", " ").replace("|", "\\|")
        lines.append(
            f"| {column.name} | {column.data_type} | {'SIM' if column.nullable else 'NÃO'} | {default_clean} | {comment_clean} |"
        )

    if view.text:
        lines.extend(["", "## Definição SQL", "", "```sql", view.text.strip(), "```"])

    lines.extend(_render_manual_section(view_doc))
    return "\n".join(lines)


def render_mview_markdown(
    mview: MaterializedViewMeta,
    mview_doc: str = "",
    annotation: ObjectAnnotation | None = None,
) -> str:
    lines = [f"# MATERIALIZED VIEW: {mview.name}", "", "## Visão geral", ""]
    desc = (annotation and annotation.description) or mview.comment or mview_doc or "Visão Materializada (Materialized View) do Oracle."
    lines.append(desc.replace("\r\n", " ").replace("\n", " "))
    lines.extend(_render_business_rules(annotation))

    lines.extend(
        [
            "",
            "## Propriedades",
            "",
            "| Propriedade | Valor |",
            "|---|---|",
            f"| Modo de Atualização | {mview.refresh_mode or 'N/A'} |",
            f"| Tipo de Atualização | {mview.refresh_type or 'N/A'} |",
            f"| Atualizável | {'SIM' if mview.updatable else 'NÃO'} |",
        ]
    )

    if mview.columns:
        ann_cols = annotation.columns if annotation else {}
        lines.extend(["", "## Colunas", "", "| Coluna | Tipo | Nulo | Comentário |", "|---|---|---|---|"])
        for column in mview.columns:
            raw_comment = ann_cols.get(column.name) or column.comment or ""
            comment_clean = raw_comment.replace("\r\n", " ").replace("\n", " ").replace("|", "\\|")
            lines.append(f"| {column.name} | {column.data_type} | {'SIM' if column.nullable else 'NÃO'} | {comment_clean} |")

    if mview.query:
        lines.extend(["", "## Consulta SQL", "", "```sql", mview.query.strip(), "```"])

    lines.extend(_render_manual_section(mview_doc))
    return "\n".join(lines)


def render_subprogram_markdown(
    sub: SubprogramMeta,
    sub_doc: str = "",
    annotation: ObjectAnnotation | None = None,
) -> str:
    lines = [f"# {sub.subprogram_type.upper()}: {sub.package_name}.{sub.name}", "", "## Visão geral", ""]
    desc = (
        (annotation and annotation.description)
        or sub.comment
        or sub_doc
        or f"Sub-rotina PL/SQL (`{sub.name}`) pertencente ao pacote `{sub.package_name}`."
    )
    lines.append(desc.replace("\r\n", " ").replace("\n", " "))
    lines.extend(_render_business_rules(annotation))

    if sub.source:
        lines.extend(["", "## Código-fonte PL/SQL", "", "```sql", sub.source.strip(), "```"])

    lines.extend(_render_manual_section(sub_doc))
    return "\n".join(lines)


def render_code_object_markdown(
    code_obj: CodeObjectMeta,
    code_doc: str = "",
    annotation: ObjectAnnotation | None = None,
) -> str:
    lines = [f"# {code_obj.object_type.upper()}: {code_obj.name}", "", "## Visão geral", ""]
    desc = (annotation and annotation.description) or code_obj.comment or code_doc or f"Objeto PL/SQL ({code_obj.object_type}) armazenado no Oracle."
    lines.append(desc.replace("\r\n", " ").replace("\n", " "))
    lines.extend(_render_business_rules(annotation))

    if code_obj.subprograms:
        lines.extend(["", "## Sub-rotinas desmembradas", "", "| Tipo | Nome | Arquivo |", "|---|---|---|"])
        for sub in code_obj.subprograms:
            lines.append(f"| {sub.subprogram_type} | {sub.name} | `{code_obj.name}/{sub.name}.md` |")

    if code_obj.source:
        lines.extend(["", "## Código-fonte do Pacote", "", "```sql", code_obj.source.strip(), "```"])

    lines.extend(_render_manual_section(code_doc))
    return "\n".join(lines)


def render_trigger_markdown(
    trigger: TriggerMeta,
    trigger_doc: str = "",
    annotation: ObjectAnnotation | None = None,
) -> str:
    lines = [
        f"# TRIGGER: {trigger.name}",
        "",
        "## Visão geral",
        "",
        (annotation and annotation.description) or f"Trigger associado à tabela `{trigger.table_name or 'N/A'}`.",
    ]
    lines.extend(_render_business_rules(annotation))
    lines.extend(
        [
            "",
            "## Propriedades",
            "",
            "| Propriedade | Valor |",
            "|---|---|",
            f"| Tabela Alvo | {trigger.table_name or 'N/A'} |",
            f"| Tipo | {trigger.trigger_type or 'N/A'} |",
            f"| Evento | {trigger.triggering_event or 'N/A'} |",
            f"| Status | {trigger.status or 'N/A'} |",
        ]
    )

    if trigger.trigger_body:
        lines.extend(["", "## Código do Trigger", "", "```sql", trigger.trigger_body.strip(), "```"])

    lines.extend(_render_manual_section(trigger_doc))
    return "\n".join(lines)


def render_sequence_markdown(
    sequence: SequenceMeta,
    seq_doc: str = "",
    annotation: ObjectAnnotation | None = None,
) -> str:
    lines = [
        f"# SEQUENCE: {sequence.name}",
        "",
        "## Visão geral",
        "",
        (annotation and annotation.description) or "Sequência de valores numéricos do Oracle.",
    ]
    lines.extend(_render_business_rules(annotation))
    lines.extend(
        [
            "",
            "## Propriedades",
            "",
            "| Propriedade | Valor |",
            "|---|---|",
            f"| Valor Mínimo | {sequence.min_value if sequence.min_value is not None else 'N/A'} |",
            f"| Valor Máximo | {sequence.max_value if sequence.max_value is not None else 'N/A'} |",
            f"| Incremento | {sequence.increment_by if sequence.increment_by is not None else 'N/A'} |",
            f"| Último Número | {sequence.last_number if sequence.last_number is not None else 'N/A'} |",
        ]
    )
    lines.extend(_render_manual_section(seq_doc))
    return "\n".join(lines)


def render_index_markdown(
    index: IndexMeta,
    idx_doc: str = "",
    annotation: ObjectAnnotation | None = None,
) -> str:
    cols = ", ".join(index.columns) if index.columns else "Nenhuma"
    lines = [
        f"# INDEX: {index.name}",
        "",
        "## Visão geral",
        "",
        (annotation and annotation.description) or f"Índice criado na tabela `{index.table_name}` ({index.uniqueness}).",
    ]
    lines.extend(_render_business_rules(annotation))
    lines.extend(
        [
            "",
            "## Propriedades",
            "",
            "| Propriedade | Valor |",
            "|---|---|",
            f"| Tabela Alvo | {index.table_name} |",
            f"| Unicidade | {index.uniqueness} |",
            f"| Colunas Indexadas | {cols} |",
        ]
    )
    lines.extend(_render_manual_section(idx_doc))
    return "\n".join(lines)


def render_synonym_markdown(
    synonym: SynonymMeta,
    syn_doc: str = "",
    annotation: ObjectAnnotation | None = None,
) -> str:
    lines = [
        f"# SYNONYM: {synonym.name}",
        "",
        "## Visão geral",
        "",
        (annotation and annotation.description) or f"Sinônimo que aponta para `{synonym.table_owner or ''}.{synonym.table_name or ''}`.",
    ]
    lines.extend(_render_business_rules(annotation))
    lines.extend(
        [
            "",
            "## Propriedades",
            "",
            "| Propriedade | Valor |",
            "|---|---|",
            f"| Owner Alvo | {synonym.table_owner or 'N/A'} |",
            f"| Objeto Alvo | {synonym.table_name or 'N/A'} |",
            f"| DB Link | {synonym.db_link or 'Nenhum'} |",
        ]
    )
    lines.extend(_render_manual_section(syn_doc))
    return "\n".join(lines)


def _write_single_doc(file_path: Path, new_markdown: str) -> Path:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(new_markdown, encoding="utf-8")
    return file_path


def _is_category_allowed(category: str, allowed_types: set[str] | None) -> bool:
    if not allowed_types:
        return True
    return category.lower() in allowed_types


def _is_code_obj_allowed(code_obj: CodeObjectMeta, allowed_types: set[str] | None) -> bool:
    if not allowed_types:
        return True
    otype = code_obj.object_type.upper()
    if otype == "PROCEDURE" and "procedures" in allowed_types:
        return True
    if otype == "FUNCTION" and "functions" in allowed_types:
        return True
    if otype in ("PACKAGE", "PACKAGE BODY") and "packages" in allowed_types:
        return True
    if otype in ("TYPE", "TYPE BODY") and "types" in allowed_types:
        return True
    return False


def write_schema_docs(
    schema: SchemaMetadata,
    doc_path: Path,
    annotations_path: Path | None = None,
    docs_overrides: dict[str, dict[str, str]] | None = None,
    multi_schema: bool = False,
    object_types: list[str] | None = None,
) -> tuple[list[Path], list[Path]]:
    base_ann = annotations_path or (doc_path.parent / "annotations")
    target_doc_path = (doc_path / schema.schema_name) if (multi_schema and schema.schema_name) else doc_path
    target_ann_path = (base_ann / schema.schema_name) if (multi_schema and schema.schema_name) else base_ann

    docs_overrides = docs_overrides or {}
    table_overrides = {k.upper(): v for k, v in docs_overrides.get("tables", {}).items()}

    column_overrides_raw = docs_overrides.get("columns", {})
    normalized_column_overrides: dict[str, dict[str, str]] = {}
    for key, value in column_overrides_raw.items():
        if "." not in key:
            continue
        table_name, column_name = key.split(".", maxsplit=1)
        normalized_column_overrides.setdefault(table_name.upper(), {})[column_name.upper()] = value

    allowed_types = {t.lower() for t in object_types} if object_types else None
    generated_md: list[Path] = []
    generated_ann: list[Path] = []

    # 1. Tables
    if _is_category_allowed("tables", allowed_types):
        for table in schema.tables:
            ann_path = target_ann_path / "tables" / f"{table.name}.yml"
            annotation = ensure_annotation_stub(ann_path, db_comment=table.comment, column_names=[c.name for c in table.columns])
            generated_ann.append(ann_path)

            file_path = target_doc_path / "tables" / f"{table.name}.md"
            existing = file_path.read_text(encoding="utf-8") if file_path.exists() else None
            manual_doc = _extract_manual_section(existing) or table_overrides.get(table.name, "")
            markdown = render_table_markdown(
                table,
                table_doc=manual_doc,
                column_docs=normalized_column_overrides.get(table.name, {}),
                annotation=annotation,
            )
            generated_md.append(_write_single_doc(file_path, markdown))

    # 2. Views
    if _is_category_allowed("views", allowed_types):
        for view in schema.views:
            ann_path = target_ann_path / "views" / f"{view.name}.yml"
            annotation = ensure_annotation_stub(ann_path, db_comment=view.comment, column_names=[c.name for c in view.columns])
            generated_ann.append(ann_path)

            file_path = target_doc_path / "views" / f"{view.name}.md"
            existing = file_path.read_text(encoding="utf-8") if file_path.exists() else None
            manual_doc = _extract_manual_section(existing)
            markdown = render_view_markdown(
                view,
                view_doc=manual_doc,
                column_docs=normalized_column_overrides.get(view.name, {}),
                annotation=annotation,
            )
            generated_md.append(_write_single_doc(file_path, markdown))

    # 3. Materialized Views
    if _is_category_allowed("mviews", allowed_types):
        for mview in schema.mviews:
            ann_path = target_ann_path / "mviews" / f"{mview.name}.yml"
            annotation = ensure_annotation_stub(ann_path, db_comment=mview.comment, column_names=[c.name for c in mview.columns])
            generated_ann.append(ann_path)

            file_path = target_doc_path / "mviews" / f"{mview.name}.md"
            existing = file_path.read_text(encoding="utf-8") if file_path.exists() else None
            manual_doc = _extract_manual_section(existing)
            markdown = render_mview_markdown(mview, mview_doc=manual_doc, annotation=annotation)
            generated_md.append(_write_single_doc(file_path, markdown))

    # 4. Code Objects (Procedures, Functions, Packages, Types)
    for code_obj in schema.code_objects:
        if not _is_code_obj_allowed(code_obj, allowed_types):
            continue
        obj_folder = code_obj.object_type.lower().replace(" ", "_") + "s"
        ann_path = target_ann_path / obj_folder / f"{code_obj.name}.yml"
        annotation = ensure_annotation_stub(ann_path, db_comment=code_obj.comment)
        generated_ann.append(ann_path)

        file_path = target_doc_path / obj_folder / f"{code_obj.name}.md"
        existing = file_path.read_text(encoding="utf-8") if file_path.exists() else None
        manual_doc = _extract_manual_section(existing)
        markdown = render_code_object_markdown(code_obj, code_doc=manual_doc, annotation=annotation)
        generated_md.append(_write_single_doc(file_path, markdown))

        # Package Splitting (Subprogram disassembly)
        for sub in code_obj.subprograms:
            sub_ann_path = target_ann_path / obj_folder / code_obj.name / f"{sub.name}.yml"
            sub_annotation = ensure_annotation_stub(sub_ann_path, db_comment=sub.comment)
            generated_ann.append(sub_ann_path)

            sub_file_path = target_doc_path / obj_folder / code_obj.name / f"{sub.name}.md"
            sub_existing = sub_file_path.read_text(encoding="utf-8") if sub_file_path.exists() else None
            sub_manual = _extract_manual_section(sub_existing)
            sub_markdown = render_subprogram_markdown(sub, sub_doc=sub_manual, annotation=sub_annotation)
            generated_md.append(_write_single_doc(sub_file_path, sub_markdown))

    # 5. Triggers
    if _is_category_allowed("triggers", allowed_types):
        for trigger in schema.triggers:
            ann_path = target_ann_path / "triggers" / f"{trigger.name}.yml"
            annotation = ensure_annotation_stub(ann_path)
            generated_ann.append(ann_path)

            file_path = target_doc_path / "triggers" / f"{trigger.name}.md"
            existing = file_path.read_text(encoding="utf-8") if file_path.exists() else None
            manual_doc = _extract_manual_section(existing)
            markdown = render_trigger_markdown(trigger, trigger_doc=manual_doc, annotation=annotation)
            generated_md.append(_write_single_doc(file_path, markdown))

    # 6. Sequences
    if _is_category_allowed("sequences", allowed_types):
        for sequence in schema.sequences:
            ann_path = target_ann_path / "sequences" / f"{sequence.name}.yml"
            annotation = ensure_annotation_stub(ann_path)
            generated_ann.append(ann_path)

            file_path = target_doc_path / "sequences" / f"{sequence.name}.md"
            existing = file_path.read_text(encoding="utf-8") if file_path.exists() else None
            manual_doc = _extract_manual_section(existing)
            markdown = render_sequence_markdown(sequence, seq_doc=manual_doc, annotation=annotation)
            generated_md.append(_write_single_doc(file_path, markdown))

    # 7. Indexes
    if _is_category_allowed("indexes", allowed_types):
        for index in schema.indexes:
            ann_path = target_ann_path / "indexes" / f"{index.name}.yml"
            annotation = ensure_annotation_stub(ann_path)
            generated_ann.append(ann_path)

            file_path = target_doc_path / "indexes" / f"{index.name}.md"
            existing = file_path.read_text(encoding="utf-8") if file_path.exists() else None
            manual_doc = _extract_manual_section(existing)
            markdown = render_index_markdown(index, idx_doc=manual_doc, annotation=annotation)
            generated_md.append(_write_single_doc(file_path, markdown))

    # 8. Synonyms
    if _is_category_allowed("synonyms", allowed_types):
        for synonym in schema.synonyms:
            ann_path = target_ann_path / "synonyms" / f"{synonym.name}.yml"
            annotation = ensure_annotation_stub(ann_path)
            generated_ann.append(ann_path)

            file_path = target_doc_path / "synonyms" / f"{synonym.name}.md"
            existing = file_path.read_text(encoding="utf-8") if file_path.exists() else None
            manual_doc = _extract_manual_section(existing)
            markdown = render_synonym_markdown(synonym, syn_doc=manual_doc, annotation=annotation)
            generated_md.append(_write_single_doc(file_path, markdown))

    return generated_md, generated_ann


def write_table_docs(tables: list[TableMeta], doc_path: Path, docs_overrides: dict[str, dict[str, str]] | None = None) -> list[Path]:
    schema = SchemaMetadata(tables=tables)
    generated_md, _ = write_schema_docs(schema, doc_path, docs_overrides=docs_overrides)
    return generated_md


def sync_schema_annotations(
    schema: SchemaMetadata,
    annotations_path: Path,
    multi_schema: bool = False,
    object_types: list[str] | None = None,
) -> list[Path]:
    target_ann_path = (annotations_path / schema.schema_name) if (multi_schema and schema.schema_name) else annotations_path
    allowed_types = {t.lower() for t in object_types} if object_types else None
    generated_ann: list[Path] = []

    if _is_category_allowed("tables", allowed_types):
        for table in schema.tables:
            ann_path = target_ann_path / "tables" / f"{table.name}.yml"
            ensure_annotation_stub(ann_path, db_comment=table.comment, column_names=[c.name for c in table.columns])
            generated_ann.append(ann_path)

    if _is_category_allowed("views", allowed_types):
        for view in schema.views:
            ann_path = target_ann_path / "views" / f"{view.name}.yml"
            ensure_annotation_stub(ann_path, db_comment=view.comment, column_names=[c.name for c in view.columns])
            generated_ann.append(ann_path)

    if _is_category_allowed("mviews", allowed_types):
        for mview in schema.mviews:
            ann_path = target_ann_path / "mviews" / f"{mview.name}.yml"
            ensure_annotation_stub(ann_path, db_comment=mview.comment, column_names=[c.name for c in mview.columns])
            generated_ann.append(ann_path)

    for code_obj in schema.code_objects:
        if not _is_code_obj_allowed(code_obj, allowed_types):
            continue
        obj_folder = code_obj.object_type.lower().replace(" ", "_") + "s"
        ann_path = target_ann_path / obj_folder / f"{code_obj.name}.yml"
        ensure_annotation_stub(ann_path, db_comment=code_obj.comment)
        generated_ann.append(ann_path)

        for sub in code_obj.subprograms:
            sub_ann_path = target_ann_path / obj_folder / code_obj.name / f"{sub.name}.yml"
            ensure_annotation_stub(sub_ann_path, db_comment=sub.comment)
            generated_ann.append(sub_ann_path)

    if _is_category_allowed("triggers", allowed_types):
        for trigger in schema.triggers:
            ann_path = target_ann_path / "triggers" / f"{trigger.name}.yml"
            ensure_annotation_stub(ann_path)
            generated_ann.append(ann_path)

    if _is_category_allowed("sequences", allowed_types):
        for sequence in schema.sequences:
            ann_path = target_ann_path / "sequences" / f"{sequence.name}.yml"
            ensure_annotation_stub(ann_path)
            generated_ann.append(ann_path)

    if _is_category_allowed("indexes", allowed_types):
        for index in schema.indexes:
            ann_path = target_ann_path / "indexes" / f"{index.name}.yml"
            ensure_annotation_stub(ann_path)
            generated_ann.append(ann_path)

    if _is_category_allowed("synonyms", allowed_types):
        for synonym in schema.synonyms:
            ann_path = target_ann_path / "synonyms" / f"{synonym.name}.yml"
            ensure_annotation_stub(ann_path)
            generated_ann.append(ann_path)

    return generated_ann


def generate_mermaid_graph(focal_name: str, dependencies: list[DependencyLink]) -> str:
    lines = ["```mermaid", "graph TD"]
    focal_id = focal_name.replace("$", "_").replace(".", "_")
    lines.append(f'    {focal_id}["⭐ {focal_name} (Focal)"]:::focalClass')

    nodes = {focal_name: focal_id}
    edges = []

    for dep in dependencies:
        s_id = dep.source_name.replace("$", "_").replace(".", "_")
        t_id = dep.target_name.replace("$", "_").replace(".", "_")

        if dep.source_name not in nodes:
            nodes[dep.source_name] = s_id
            icon = "📊" if dep.source_type == "TABLE" else ("👁️" if "VIEW" in dep.source_type else ("⚡" if dep.source_type == "TRIGGER" else "⚙️"))
            lines.append(f'    {s_id}["{icon} {dep.source_name} (L{dep.depth})"]')

        if dep.target_name not in nodes:
            nodes[dep.target_name] = t_id
            icon = "📊" if dep.target_type == "TABLE" else ("👁️" if "VIEW" in dep.target_type else ("⚡" if dep.target_type == "TRIGGER" else "⚙️"))
            lines.append(f'    {t_id}["{icon} {dep.target_name} (L{dep.depth})"]')

        label = dep.relation_type.replace("_", " ")
        edges.append(f"    {s_id} -->|{label}| {t_id}")

    lines.extend(edges)
    lines.append("")
    lines.append("    classDef focalClass fill:#ff9800,stroke:#e65100,stroke-width:3px,font-weight:bold,color:#000;")
    lines.append("```")
    return "\n".join(lines)


def _calculate_risk_level(dep_count: int) -> str:
    if dep_count == 0:
        return "LOW"
    elif dep_count <= 3:
        return "MEDIUM"
    elif dep_count <= 7:
        return "HIGH"
    return "CRITICAL"


def generate_semantic_rag_text(trace_result: ObjectTraceResult, annotation: ObjectAnnotation | None = None) -> str:
    focal_name = trace_result.focal_name
    focal_type = trace_result.focal_type
    focal_obj = trace_result.focal_object
    desc = (annotation and annotation.description) or getattr(focal_obj, "comment", None) or f"Objeto {focal_name} do tipo {focal_type}."

    parts = [f"O objeto {focal_name} é do tipo {focal_type}. Descrição de negócio: {desc.strip()}."]

    if annotation and annotation.business_rules:
        rules_str = " Regras de negócio associadas: " + "; ".join(annotation.business_rules) + "."
        parts.append(rules_str)

    if isinstance(focal_obj, TableMeta):
        cols_summary = ", ".join([f"{c.name} ({c.data_type})" for c in focal_obj.columns[:15]])
        parts.append(f" Estrutura de colunas principais: {cols_summary}.")

    if trace_result.dependencies:
        dep_descriptions = []
        for dep in trace_result.dependencies:
            if dep.relation_type == "FK_REFERENCES":
                dep_descriptions.append(f"possui chave estrangeira para a tabela {dep.target_name}")
            elif dep.relation_type == "FK_REFERENCED_BY":
                dep_descriptions.append(f"é referenciada pela tabela filha {dep.source_name}")
            elif dep.relation_type == "READS/SELECTS":
                dep_descriptions.append(f"é lida pela {dep.source_type.lower()} {dep.source_name}")
            elif dep.relation_type == "TRIGGER_ON":
                dep_descriptions.append(f"possui a trigger {dep.source_name}")
            elif dep.relation_type == "PLSQL_DEPENDENCY":
                dep_descriptions.append(f"é manipulada pelo código PL/SQL {dep.source_name}")
            elif dep.relation_type == "SYNONYM_FOR":
                dep_descriptions.append(f"possui o sinônimo {dep.source_name} apontando para si")
            elif dep.relation_type == "REFERENCED_BY":
                dep_descriptions.append(f"é referenciada pelo objeto {dep.source_type.lower()} {dep.source_name}")
            elif dep.relation_type == "DEPENDS_ON":
                dep_descriptions.append(f"depende do objeto {dep.target_type.lower()} {dep.target_name}")
            else:
                dep_descriptions.append(f"possui vínculo com {dep.target_name} ({dep.relation_type})")
        parts.append(" Impacto relacional: " + ", ".join(dep_descriptions[:10]) + ".")

    return "".join(parts)


def generate_rag_json(trace_result: ObjectTraceResult, annotation: ObjectAnnotation | None = None) -> dict:
    focal_name = trace_result.focal_name
    focal_type = trace_result.focal_type
    focal_obj = trace_result.focal_object
    risk = _calculate_risk_level(len(trace_result.dependencies))
    semantic_text = generate_semantic_rag_text(trace_result, annotation=annotation)

    columns_info = []
    pks = []
    fks = []
    if isinstance(focal_obj, TableMeta):
        columns_info = [{"name": c.name, "type": c.data_type, "nullable": c.nullable, "comment": c.comment} for c in focal_obj.columns]
        pks = focal_obj.primary_keys
        fks = [{"name": fk.name, "column": fk.column, "referenced_table": fk.referenced_table, "referenced_column": fk.referenced_column} for fk in focal_obj.foreign_keys]

    deps_info = [
        {
            "depth": d.depth,
            "source_name": d.source_name,
            "source_type": d.source_type,
            "target_name": d.target_name,
            "target_type": d.target_type,
            "relation_type": d.relation_type,
            "details": d.details,
        }
        for d in trace_result.dependencies
    ]

    return {
        "chunk_id": f"trace_{focal_name.lower()}",
        "entity": focal_name,
        "type": focal_type,
        "risk_level": risk,
        "tags": annotation.tags if annotation else [],
        "text_for_embedding": semantic_text,
        "schema_context": {
            "columns": columns_info,
            "primary_keys": pks,
            "foreign_keys": fks,
            "dependencies": deps_info,
        },
    }


def write_rag_json_file(
    trace_result: ObjectTraceResult,
    output_path: Path,
    annotations_path: Path | None = None,
) -> Path:
    import json
    base_ann = annotations_path or (output_path.parent.parent / "annotations")
    ann_path = base_ann / "dossiers" / f"{trace_result.focal_name}.yml"
    annotation = ensure_annotation_stub(ann_path)

    data = generate_rag_json(trace_result, annotation=annotation)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return output_path


def render_dossier_markdown(
    trace_result: ObjectTraceResult,
    annotation: ObjectAnnotation | None = None,
    manual_doc: str = "",
) -> str:
    focal_name = trace_result.focal_name
    focal_type = trace_result.focal_type
    focal_obj = trace_result.focal_object
    dep_count = len(trace_result.dependencies)
    risk_level = _calculate_risk_level(dep_count)

    parents = [d.target_name for d in trace_result.dependencies if d.relation_type in ("FK_REFERENCES", "DEPENDS_ON")]
    children = [d.source_name for d in trace_result.dependencies if d.relation_type == "FK_REFERENCED_BY"]
    consumers = [d.source_name for d in trace_result.dependencies if d.relation_type in ("READS/SELECTS", "PLSQL_DEPENDENCY", "TRIGGER_ON", "REFERENCED_BY")]

    # 1. YAML Frontmatter for RAG / LLM
    import yaml
    rag_meta = {
        "rag_metadata": {
            "entity": focal_name,
            "type": focal_type,
            "risk_level": risk_level,
            "tags": annotation.tags if annotation else [],
            "impact_summary": {
                "total_connections": dep_count,
                "upstream_parents": list(set(parents)),
                "downstream_children": list(set(children)),
                "consumers": list(set(consumers)),
            },
        }
    }
    yaml_frontmatter = yaml.safe_dump(rag_meta, sort_keys=False, allow_unicode=True).strip()

    lines = [
        "---",
        yaml_frontmatter,
        "---",
        "",
        f"# DOSSIÊ DE IMPACTO E DOCUMENTAÇÃO FOCAL: {focal_name}",
        "",
        f"**Tipo de Objeto:** `{focal_type}`",
    ]

    if focal_obj:
        lines.extend(_render_audit_meta(focal_obj))

    # 2. Executive Summary Card / Impact X-Ray
    risk_badge_color = "CRITICAL" if risk_level == "CRITICAL" else ("WARNING" if risk_level in ("HIGH", "MEDIUM") else "NOTE")
    lines.extend(
        [
            f"> [!{risk_badge_color}]",
            f"> **Raio-X de Impacto Técnico:**",
            f"> - **Nível de Risco de Alteração:** `{risk_level}` ({dep_count} conexões no grafo)",
            f"> - **Tabelas Pais (Upstream):** `{len(set(parents))}` | **Tabelas Filhas (Downstream):** `{len(set(children))}`",
            f"> - **Consumidores Ativos (Views/Procs/Triggers):** `{len(set(consumers))}`",
            "",
        ]
    )

    desc = (annotation and annotation.description) or getattr(focal_obj, "comment", None) or f"Análise minuciosa e rastreamento de linhagem técnica para o objeto `{focal_name}`."
    lines.extend(["## Visão geral de negócio", "", desc])
    lines.extend(_render_business_rules(annotation))

    # 3. Semantic Narrative Summary (RAG Ready)
    semantic_text = generate_semantic_rag_text(trace_result, annotation=annotation)
    lines.extend(["", "## 🧠 Resumo Narrativo Semântico (RAG Ready)", "", semantic_text])

    # 4. Mermaid Lineage Graph
    lines.extend(["", "## Grafo de Linhagem e Relacionamentos", ""])
    if trace_result.dependencies:
        lines.append(generate_mermaid_graph(focal_name, trace_result.dependencies))
    else:
        lines.append("*Nenhuma dependência direta identificada no catálogo/snapshot.*")

    # 5. Dependency Table
    lines.extend(["", "## Mapa de Dependências e Impacto", ""])
    if trace_result.dependencies:
        lines.append("| Nível | Objeto Origem | Tipo | Relação | Objeto Alvo | Tipo | Detalhes |")
        lines.append("|---|---|---|---|---|---|---|")
        for dep in sorted(trace_result.dependencies, key=lambda d: (d.depth, d.source_name)):
            lines.append(
                f"| **Nível {dep.depth}** | `{dep.source_name}` | {dep.source_type} | `{dep.relation_type}` | `{dep.target_name}` | {dep.target_type} | {dep.details or ''} |"
            )
    else:
        lines.append("Nenhuma dependência registrada.")

    # 6. Focal Object Details
    if isinstance(focal_obj, TableMeta):
        lines.extend(["", "## Estrutura de Colunas do Objeto Focal", "", "| Coluna | Tipo | Nulo | Padrão | Comentário |", "|---|---|---|---|---|"])
        ann_cols = annotation.columns if annotation else {}
        for col in focal_obj.columns:
            comm = ann_cols.get(col.name) or col.comment or ""
            lines.append(f"| {col.name} | {col.data_type} | {'SIM' if col.nullable else 'NÃO'} | {col.default or ''} | {comm} |")

        lines.extend(["", "### Chaves Primárias", ", ".join(focal_obj.primary_keys) if focal_obj.primary_keys else "Não definida"])
        lines.extend(["", "### Chaves Estrangeiras de Saída"])
        if focal_obj.foreign_keys:
            for fk in focal_obj.foreign_keys:
                lines.append(f"- `{fk.name}`: Coluna `{fk.column}` aponta para `{fk.referenced_table}.{fk.referenced_column}`")
        else:
            lines.append("Nenhuma")
    elif isinstance(focal_obj, ViewMeta) and focal_obj.text:
        lines.extend(["", "## Definição SQL da View", "```sql", focal_obj.text.strip(), "```"])
    elif isinstance(focal_obj, CodeObjectMeta) and focal_obj.source:
        lines.extend(["", "## Código-Fonte PL/SQL", "```sql", focal_obj.source.strip(), "```"])

    # 7. Related Objects Details
    if trace_result.related_tables or trace_result.related_views or trace_result.related_code_objects or trace_result.related_triggers:
        lines.extend(["", "## Detalhes dos Objetos Relacionados", ""])

        if trace_result.related_tables:
            lines.append("### 📊 Tabelas Conectadas")
            for t in trace_result.related_tables:
                lines.append(f"- **`{t.name}`**: {len(t.columns)} colunas, {len(t.foreign_keys)} FKs ({t.comment or 'Sem comentário'})")

        if trace_result.related_views:
            lines.append("")
            lines.append("### 👁️ Views Conectadas")
            for v in trace_result.related_views:
                lines.append(f"- **`{v.name}`**: {len(v.columns)} colunas ({v.comment or 'Sem comentário'})")

        if trace_result.related_triggers:
            lines.append("")
            lines.append("### ⚡ Triggers Conectados")
            for trg in trace_result.related_triggers:
                lines.append(f"- **`{trg.name}`** (Disparo: `{trg.trigger_type} {trg.triggering_event}` na tabela `{trg.table_name}`)")

        if trace_result.related_code_objects:
            lines.append("")
            lines.append("### ⚙️ Packages / Procedures / Functions Conectadas")
            for co in trace_result.related_code_objects:
                lines.append(f"- **`{co.name}`** ({co.object_type})")

    lines.extend(_render_manual_section(manual_doc))
    return "\n".join(lines)


def write_dossier_doc(
    trace_result: ObjectTraceResult,
    output_path: Path,
    annotations_path: Path | None = None,
) -> Path:
    base_ann = annotations_path or (output_path.parent.parent / "annotations")
    ann_path = base_ann / "dossiers" / f"{trace_result.focal_name}.yml"
    annotation = ensure_annotation_stub(ann_path)

    existing = output_path.read_text(encoding="utf-8") if output_path.exists() else None
    manual_doc = _extract_manual_section(existing)

    markdown = render_dossier_markdown(trace_result, annotation=annotation, manual_doc=manual_doc)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")
    return output_path



