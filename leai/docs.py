from __future__ import annotations

from pathlib import Path

from leai.models import TableMeta

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


def render_table_markdown(table: TableMeta, table_doc: str = "", column_docs: dict[str, str] | None = None) -> str:
    column_docs = column_docs or {}
    lines = [f"# {table.name}", "", "## Visão geral", ""]
    lines.append(table.comment or table_doc or "Sem descrição técnica no dicionário Oracle.")
    lines.extend(["", "## Colunas", "", "| Coluna | Tipo | Nulo | Comentário |", "|---|---|---|---|"])

    for column in table.columns:
        comment = column_docs.get(column.name) or column.comment or ""
        lines.append(
            f"| {column.name} | {column.data_type} | {'SIM' if column.nullable else 'NÃO'} | {comment.replace('|', '\\|')} |"
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

    lines.extend(["", "## Documentação humana", "", MANUAL_START])
    lines.append(table_doc or "")
    lines.extend([MANUAL_END, ""])
    return "\n".join(lines)


def write_table_docs(tables: list[TableMeta], doc_path: Path, docs_overrides: dict[str, dict[str, str]] | None = None) -> list[Path]:
    docs_overrides = docs_overrides or {}
    table_overrides = {k.upper(): v for k, v in docs_overrides.get("tables", {}).items()}

    column_overrides_raw = docs_overrides.get("columns", {})
    normalized_column_overrides: dict[str, dict[str, str]] = {}
    for key, value in column_overrides_raw.items():
        table_name, column_name = key.split(".", maxsplit=1)
        normalized_column_overrides.setdefault(table_name.upper(), {})[column_name.upper()] = value

    doc_path.mkdir(parents=True, exist_ok=True)
    generated_files: list[Path] = []

    for table in tables:
        file_path = doc_path / f"{table.name}.md"
        existing = file_path.read_text(encoding="utf-8") if file_path.exists() else None
        manual_doc = _extract_manual_section(existing) or table_overrides.get(table.name, "")
        markdown = render_table_markdown(
            table,
            table_doc=manual_doc,
            column_docs=normalized_column_overrides.get(table.name, {}),
        )
        file_path.write_text(markdown, encoding="utf-8")
        generated_files.append(file_path)

    return generated_files
