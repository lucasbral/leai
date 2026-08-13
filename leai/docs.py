from leai.annotations import ensure_annotation_stub
from leai.models import (
    CodeObjectMeta,
    IndexMeta,
    MaterializedViewMeta,
    ObjectAnnotation,
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


def write_schema_docs(
    schema: SchemaMetadata,
    doc_path: Path,
    annotations_path: Path | None = None,
    docs_overrides: dict[str, dict[str, str]] | None = None,
    multi_schema: bool = False,
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

    generated_md: list[Path] = []
    generated_ann: list[Path] = []

    # 1. Tables
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
    for mview in schema.mviews:
        ann_path = target_ann_path / "mviews" / f"{mview.name}.yml"
        annotation = ensure_annotation_stub(ann_path, db_comment=mview.comment, column_names=[c.name for c in mview.columns])
        generated_ann.append(ann_path)

        file_path = target_doc_path / "mviews" / f"{mview.name}.md"
        existing = file_path.read_text(encoding="utf-8") if file_path.exists() else None
        manual_doc = _extract_manual_section(existing)
        markdown = render_mview_markdown(mview, mview_doc=manual_doc, annotation=annotation)
        generated_md.append(_write_single_doc(file_path, markdown))

    # 4. Code Objects (Procedures, Functions, Packages)
    for code_obj in schema.code_objects:
        obj_folder = code_obj.object_type.lower().replace(" ", "_") + "s"
        ann_path = target_ann_path / obj_folder / f"{code_obj.name}.yml"
        annotation = ensure_annotation_stub(ann_path, db_comment=code_obj.comment)
        generated_ann.append(ann_path)

        file_path = target_doc_path / obj_folder / f"{code_obj.name}.md"
        existing = file_path.read_text(encoding="utf-8") if file_path.exists() else None
        manual_doc = _extract_manual_section(existing)
        markdown = render_code_object_markdown(code_obj, code_doc=manual_doc, annotation=annotation)
        generated_md.append(_write_single_doc(file_path, markdown))

        # Desmembramento de sub-rotinas (Package Splitting)
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
) -> list[Path]:
    target_ann_path = (annotations_path / schema.schema_name) if (multi_schema and schema.schema_name) else annotations_path
    generated_ann: list[Path] = []

    for table in schema.tables:
        ann_path = target_ann_path / "tables" / f"{table.name}.yml"
        ensure_annotation_stub(ann_path, db_comment=table.comment, column_names=[c.name for c in table.columns])
        generated_ann.append(ann_path)

    for view in schema.views:
        ann_path = target_ann_path / "views" / f"{view.name}.yml"
        ensure_annotation_stub(ann_path, db_comment=view.comment, column_names=[c.name for c in view.columns])
        generated_ann.append(ann_path)

    for mview in schema.mviews:
        ann_path = target_ann_path / "mviews" / f"{mview.name}.yml"
        ensure_annotation_stub(ann_path, db_comment=mview.comment, column_names=[c.name for c in mview.columns])
        generated_ann.append(ann_path)

    for code_obj in schema.code_objects:
        obj_folder = code_obj.object_type.lower().replace(" ", "_") + "s"
        ann_path = target_ann_path / obj_folder / f"{code_obj.name}.yml"
        ensure_annotation_stub(ann_path, db_comment=code_obj.comment)
        generated_ann.append(ann_path)

        for sub in code_obj.subprograms:
            sub_ann_path = target_ann_path / obj_folder / code_obj.name / f"{sub.name}.yml"
            ensure_annotation_stub(sub_ann_path, db_comment=sub.comment)
            generated_ann.append(sub_ann_path)

    for trigger in schema.triggers:
        ann_path = target_ann_path / "triggers" / f"{trigger.name}.yml"
        ensure_annotation_stub(ann_path)
        generated_ann.append(ann_path)

    for sequence in schema.sequences:
        ann_path = target_ann_path / "sequences" / f"{sequence.name}.yml"
        ensure_annotation_stub(ann_path)
        generated_ann.append(ann_path)

    for index in schema.indexes:
        ann_path = target_ann_path / "indexes" / f"{index.name}.yml"
        ensure_annotation_stub(ann_path)
        generated_ann.append(ann_path)

    for synonym in schema.synonyms:
        ann_path = target_ann_path / "synonyms" / f"{synonym.name}.yml"
        ensure_annotation_stub(ann_path)
        generated_ann.append(ann_path)

    return generated_ann
