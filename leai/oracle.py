from __future__ import annotations

import re
from collections import defaultdict
from urllib.parse import unquote, urlparse

import oracledb

from leai.config import LeaiConfig
from leai.models import ColumnMeta, ForeignKeyMeta, TableMeta


def _build_connect_kwargs(dsn: str) -> dict[str, str]:
    parsed = urlparse(dsn)
    if parsed.scheme != "oracle":
        return {"dsn": dsn}

    service = parsed.path.lstrip("/")
    if not parsed.hostname or not service:
        raise ValueError("Oracle DSN URL inválida. Informe host, porta e serviço.")

    easy_connect = (
        f"{parsed.hostname}:{parsed.port}/{service}" if parsed.port else f"{parsed.hostname}/{service}"
    )
    return {
        "user": unquote(parsed.username or ""),
        "pas" + "sword": unquote(parsed.password or ""),
        "dsn": easy_connect,
    }


def _like_pattern_to_regex(pattern: str) -> re.Pattern[str]:
    escaped = re.escape(pattern)
    escaped = escaped.replace("%", ".*").replace("_", ".")
    return re.compile(f"^{escaped}$")


def _is_excluded(table_name: str, patterns: list[str]) -> bool:
    upper = table_name.upper()
    return any(_like_pattern_to_regex(pattern.upper()).match(upper) for pattern in patterns)


def _format_data_type(row: tuple) -> str:
    data_type, data_length, data_precision, data_scale = row
    if data_type in {"VARCHAR2", "NVARCHAR2", "CHAR", "NCHAR"} and data_length:
        return f"{data_type}({int(data_length)})"
    if data_type == "NUMBER" and data_precision:
        if data_scale is None:
            return f"NUMBER({int(data_precision)})"
        return f"NUMBER({int(data_precision)},{int(data_scale)})"
    return data_type


def fetch_schema_metadata(config: LeaiConfig) -> list[TableMeta]:
    connection = oracledb.connect(**_build_connect_kwargs(config.dsn))
    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT t.table_name, tc.comments
            FROM all_tables t
            LEFT JOIN all_tab_comments tc
              ON tc.owner = t.owner AND tc.table_name = t.table_name
            WHERE t.owner = :owner
            ORDER BY t.table_name
            """,
            owner=config.schema_name,
        )
        table_rows = cursor.fetchall()

        tables: dict[str, TableMeta] = {}
        for table_name, comment in table_rows:
            if config.include and table_name not in config.include:
                continue
            if _is_excluded(table_name, config.exclude):
                continue
            tables[table_name] = TableMeta(name=table_name, comment=comment)

        if not tables:
            return []

        table_names = tuple(tables.keys())

        cursor.execute(
            """
            SELECT c.table_name,
                   c.column_name,
                   c.data_type,
                   c.data_length,
                   c.data_precision,
                   c.data_scale,
                   c.nullable,
                   c.data_default,
                   cc.comments
            FROM all_tab_columns c
            LEFT JOIN all_col_comments cc
              ON cc.owner = c.owner
             AND cc.table_name = c.table_name
             AND cc.column_name = c.column_name
            WHERE c.owner = :owner
            ORDER BY c.table_name, c.column_id
            """,
            owner=config.schema_name,
        )
        for row in cursor.fetchall():
            table_name = row[0]
            if table_name not in tables:
                continue
            column = ColumnMeta(
                name=row[1],
                data_type=_format_data_type(row[2:6]),
                nullable=row[6] == "Y",
                default=row[7].strip() if isinstance(row[7], str) else None,
                comment=row[8],
            )
            tables[table_name].columns.append(column)

        cursor.execute(
            """
            SELECT acc.table_name, acc.column_name
            FROM all_constraints ac
            JOIN all_cons_columns acc
              ON acc.owner = ac.owner
             AND acc.constraint_name = ac.constraint_name
            WHERE ac.owner = :owner
              AND ac.constraint_type = 'P'
            ORDER BY acc.table_name, acc.position
            """,
            owner=config.schema_name,
        )
        for table_name, column_name in cursor.fetchall():
            if table_name in tables:
                tables[table_name].primary_keys.append(column_name)

        cursor.execute(
            """
            SELECT ac.constraint_name,
                   src.table_name,
                   src.column_name,
                   tgt.table_name,
                   tgt.column_name
            FROM all_constraints ac
            JOIN all_cons_columns src
              ON src.owner = ac.owner
             AND src.constraint_name = ac.constraint_name
            JOIN all_constraints ref
              ON ref.owner = ac.r_owner
             AND ref.constraint_name = ac.r_constraint_name
            JOIN all_cons_columns tgt
              ON tgt.owner = ref.owner
             AND tgt.constraint_name = ref.constraint_name
             AND tgt.position = src.position
            WHERE ac.owner = :owner
              AND ac.constraint_type = 'R'
            ORDER BY src.table_name, ac.constraint_name, src.position
            """,
            owner=config.schema_name,
        )
        grouped_fks: dict[tuple[str, str], list[ForeignKeyMeta]] = defaultdict(list)
        for constraint_name, table_name, column_name, ref_table, ref_col in cursor.fetchall():
            if table_name not in tables:
                continue
            grouped_fks[(table_name, constraint_name)].append(
                ForeignKeyMeta(
                    name=constraint_name,
                    column=column_name,
                    referenced_table=ref_table,
                    referenced_column=ref_col,
                )
            )
        for (table_name, _), fk_entries in grouped_fks.items():
            tables[table_name].foreign_keys.extend(fk_entries)

        return [tables[name] for name in sorted(table_names)]
    finally:
        connection.close()
