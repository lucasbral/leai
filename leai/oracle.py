from __future__ import annotations

import re
from collections import defaultdict
from urllib.parse import unquote, urlparse

import oracledb

from leai.config import LeaiConfig
from leai.models import (
    CodeObjectMeta,
    ColumnMeta,
    ForeignKeyMeta,
    IndexMeta,
    MaterializedViewMeta,
    SchemaMetadata,
    SequenceMeta,
    SubprogramMeta,
    SynonymMeta,
    TableMeta,
    TriggerMeta,
    ViewMeta,
)


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
        "password": unquote(parsed.password or ""),
        "dsn": easy_connect,
    }


def _like_pattern_to_regex(pattern: str) -> re.Pattern[str]:
    parts = re.split(r"(%|_)", pattern)
    regex_parts = []
    for part in parts:
        if part == "%":
            regex_parts.append(".*")
        elif part == "_":
            regex_parts.append(".")
        else:
            regex_parts.append(re.escape(part))
    return re.compile(f"^{''.join(regex_parts)}$", re.IGNORECASE)


def _is_excluded(name: str, patterns: list[str]) -> bool:
    upper = name.upper()
    return any(_like_pattern_to_regex(pattern.upper()).match(upper) for pattern in patterns)


def _should_include(name: str, config: LeaiConfig) -> bool:
    name_upper = name.upper()
    if config.include and name_upper not in config.include:
        return False
    if _is_excluded(name_upper, config.exclude):
        return False
    return True


def _format_data_type(row: tuple) -> str:
    data_type, data_length, data_precision, data_scale, char_length = row
    if data_type in {"VARCHAR2", "NVARCHAR2", "CHAR", "NCHAR"}:
        length = int(char_length) if char_length else (int(data_length) if data_length else None)
        if length:
            return f"{data_type}({length})"
    if data_type == "NUMBER" and data_precision:
        if data_scale is None:
            return f"NUMBER({int(data_precision)})"
        return f"NUMBER({int(data_precision)},{int(data_scale)})"
    return data_type or ""


def _fetch_in_table_chunks(cursor: oracledb.Cursor, sql_template: str, owner: str, table_names: tuple[str, ...]) -> list:
    chunk_size = 500
    results = []
    for i in range(0, len(table_names), chunk_size):
        chunk = table_names[i : i + chunk_size]
        placeholders = ", ".join(f":t{j}" for j in range(len(chunk)))
        sql = sql_template.format(table_placeholders=placeholders)
        params = {"owner": owner}
        for j, name in enumerate(chunk):
            params[f"t{j}"] = name
        cursor.execute(sql, params)
        results.extend(cursor.fetchall())
    return results


def _fetch_tables(cursor: oracledb.Cursor, config: LeaiConfig) -> list[TableMeta]:
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
    tables: dict[str, TableMeta] = {}
    for table_name, comment in cursor.fetchall():
        if _should_include(table_name, config):
            tables[table_name] = TableMeta(name=table_name, comment=comment)

    if not tables:
        return []

    table_names = tuple(tables.keys())

    columns_sql = """
        SELECT c.table_name,
               c.column_name,
               c.data_type,
               c.data_length,
               c.data_precision,
               c.data_scale,
               c.nullable,
               c.data_default,
               cc.comments,
               c.char_length
        FROM all_tab_columns c
        LEFT JOIN all_col_comments cc
          ON cc.owner = c.owner
         AND cc.table_name = c.table_name
         AND cc.column_name = c.column_name
        WHERE c.owner = :owner
          AND c.table_name IN ({table_placeholders})
        ORDER BY c.table_name, c.column_id
    """
    for row in _fetch_in_table_chunks(cursor, columns_sql, config.schema_name, table_names):
        table_name = row[0]
        if table_name not in tables:
            continue
        column = ColumnMeta(
            name=row[1],
            data_type=_format_data_type((row[2], row[3], row[4], row[5], row[9])),
            nullable=row[6] == "Y",
            default=row[7].strip() if isinstance(row[7], str) else None,
            comment=row[8],
        )
        tables[table_name].columns.append(column)

    pks_sql = """
        SELECT acc.table_name, acc.column_name
        FROM all_constraints ac
        JOIN all_cons_columns acc
          ON acc.owner = ac.owner
         AND acc.constraint_name = ac.constraint_name
        WHERE ac.owner = :owner
          AND ac.constraint_type = 'P'
          AND acc.table_name IN ({table_placeholders})
        ORDER BY acc.table_name, acc.position
    """
    for table_name, column_name in _fetch_in_table_chunks(cursor, pks_sql, config.schema_name, table_names):
        if table_name in tables:
            tables[table_name].primary_keys.append(column_name)

    fks_sql = """
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
          AND src.table_name IN ({table_placeholders})
        ORDER BY src.table_name, ac.constraint_name, src.position
    """
    grouped_fks: dict[tuple[str, str], list[ForeignKeyMeta]] = defaultdict(list)
    for constraint_name, table_name, column_name, ref_table, ref_col in _fetch_in_table_chunks(
        cursor, fks_sql, config.schema_name, table_names
    ):
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


def _fetch_views(cursor: oracledb.Cursor, config: LeaiConfig) -> list[ViewMeta]:
    cursor.execute(
        """
        SELECT v.view_name, v.text, tc.comments
        FROM all_views v
        LEFT JOIN all_tab_comments tc
          ON tc.owner = v.owner AND tc.table_name = v.view_name
        WHERE v.owner = :owner
        ORDER BY v.view_name
        """,
        owner=config.schema_name,
    )
    views: dict[str, ViewMeta] = {}
    for view_name, text, comment in cursor.fetchall():
        if _should_include(view_name, config):
            views[view_name] = ViewMeta(name=view_name, text=str(text) if text else None, comment=comment)

    if not views:
        return []

    view_names = tuple(views.keys())
    columns_sql = """
        SELECT c.table_name,
               c.column_name,
               c.data_type,
               c.data_length,
               c.data_precision,
               c.data_scale,
               c.nullable,
               c.data_default,
               cc.comments,
               c.char_length
        FROM all_tab_columns c
        LEFT JOIN all_col_comments cc
          ON cc.owner = c.owner
         AND cc.table_name = c.table_name
         AND cc.column_name = c.column_name
        WHERE c.owner = :owner
          AND c.table_name IN ({table_placeholders})
        ORDER BY c.table_name, c.column_id
    """
    for row in _fetch_in_table_chunks(cursor, columns_sql, config.schema_name, view_names):
        view_name = row[0]
        if view_name not in views:
            continue
        column = ColumnMeta(
            name=row[1],
            data_type=_format_data_type((row[2], row[3], row[4], row[5], row[9])),
            nullable=row[6] == "Y",
            default=row[7].strip() if isinstance(row[7], str) else None,
            comment=row[8],
        )
        views[view_name].columns.append(column)

    return [views[name] for name in sorted(view_names)]


def _fetch_mviews(cursor: oracledb.Cursor, config: LeaiConfig) -> list[MaterializedViewMeta]:
    cursor.execute(
        """
        SELECT mv.mview_name, mv.query, mv.refresh_mode, mv.refresh_type, mv.updatable, tc.comments
        FROM all_mviews mv
        LEFT JOIN all_tab_comments tc
          ON tc.owner = mv.owner AND tc.table_name = mv.mview_name
        WHERE mv.owner = :owner
        ORDER BY mv.mview_name
        """,
        owner=config.schema_name,
    )
    mviews: dict[str, MaterializedViewMeta] = {}
    for mv_name, query, refresh_mode, refresh_type, updatable, comment in cursor.fetchall():
        if _should_include(mv_name, config):
            mviews[mv_name] = MaterializedViewMeta(
                name=mv_name,
                query=str(query) if query else None,
                refresh_mode=refresh_mode,
                refresh_type=refresh_type,
                updatable=updatable == "Y",
                comment=comment,
            )

    if not mviews:
        return []

    mv_names = tuple(mviews.keys())
    columns_sql = """
        SELECT c.table_name,
               c.column_name,
               c.data_type,
               c.data_length,
               c.data_precision,
               c.data_scale,
               c.nullable,
               c.data_default,
               cc.comments,
               c.char_length
        FROM all_tab_columns c
        LEFT JOIN all_col_comments cc
          ON cc.owner = c.owner
         AND cc.table_name = c.table_name
         AND cc.column_name = c.column_name
        WHERE c.owner = :owner
          AND c.table_name IN ({table_placeholders})
        ORDER BY c.table_name, c.column_id
    """
    for row in _fetch_in_table_chunks(cursor, columns_sql, config.schema_name, mv_names):
        mv_name = row[0]
        if mv_name not in mviews:
            continue
        column = ColumnMeta(
            name=row[1],
            data_type=_format_data_type((row[2], row[3], row[4], row[5], row[9])),
            nullable=row[6] == "Y",
            default=row[7].strip() if isinstance(row[7], str) else None,
            comment=row[8],
        )
        mviews[mv_name].columns.append(column)

    return [mviews[name] for name in sorted(mv_names)]


def _split_package_source(package_name: str, source: str | None) -> list[SubprogramMeta]:
    if not source:
        return []
    pattern = re.compile(
        r"(?i)^\s*(PROCEDURE|FUNCTION)\s+([A-Za-z0-9_$]+)",
        re.MULTILINE,
    )
    matches = list(pattern.finditer(source))
    if not matches:
        return []

    subprograms: list[SubprogramMeta] = []
    for i, match in enumerate(matches):
        sub_type = match.group(1).upper()
        sub_name = match.group(2).upper()
        start_idx = match.start()
        end_idx = matches[i + 1].start() if i + 1 < len(matches) else len(source)
        code_snippet = source[start_idx:end_idx].strip()

        subprograms.append(
            SubprogramMeta(
                package_name=package_name,
                name=sub_name,
                subprogram_type=sub_type,
                source=code_snippet,
            )
        )
    return subprograms


def _fetch_code_objects(cursor: oracledb.Cursor, config: LeaiConfig, target_types: set[str]) -> list[CodeObjectMeta]:
    cursor.execute(
        """
        SELECT DISTINCT object_name, object_type
        FROM all_procedures
        WHERE owner = :owner
        ORDER BY object_type, object_name
        """,
        owner=config.schema_name,
    )
    code_objs: list[CodeObjectMeta] = []
    seen = set()
    for obj_name, obj_type in cursor.fetchall():
        if obj_type not in target_types:
            continue
        if (obj_name, obj_type) in seen:
            continue
        if not _should_include(obj_name, config):
            continue
        seen.add((obj_name, obj_type))

        cursor.execute(
            """
            SELECT text
            FROM all_source
            WHERE owner = :owner
              AND name = :name
              AND type = :type
            ORDER BY line
            """,
            owner=config.schema_name,
            name=obj_name,
            type=obj_type,
        )
        source_lines = [row[0] for row in cursor.fetchall()]
        source = "".join(source_lines) if source_lines else None

        code_obj = CodeObjectMeta(name=obj_name, object_type=obj_type, source=source)
        if obj_type in {"PACKAGE", "PACKAGE BODY"} and source:
            code_obj.subprograms = _split_package_source(obj_name, source)

        code_objs.append(code_obj)

    return code_objs


def _fetch_triggers(cursor: oracledb.Cursor, config: LeaiConfig) -> list[TriggerMeta]:
    cursor.execute(
        """
        SELECT trigger_name, table_name, trigger_type, triggering_event, status, trigger_body
        FROM all_triggers
        WHERE owner = :owner
        ORDER BY trigger_name
        """,
        owner=config.schema_name,
    )
    triggers: list[TriggerMeta] = []
    for trg_name, table_name, trg_type, trg_event, status, body in cursor.fetchall():
        if _should_include(trg_name, config):
            triggers.append(
                TriggerMeta(
                    name=trg_name,
                    table_name=table_name,
                    trigger_type=trg_type,
                    triggering_event=trg_event,
                    status=status,
                    trigger_body=str(body) if body else None,
                )
            )
    return triggers


def _fetch_sequences(cursor: oracledb.Cursor, config: LeaiConfig) -> list[SequenceMeta]:
    cursor.execute(
        """
        SELECT sequence_name, min_value, max_value, increment_by, last_number
        FROM all_sequences
        WHERE sequence_owner = :owner
        ORDER BY sequence_name
        """,
        owner=config.schema_name,
    )
    sequences: list[SequenceMeta] = []
    for seq_name, min_val, max_val, inc_by, last_num in cursor.fetchall():
        if _should_include(seq_name, config):
            sequences.append(
                SequenceMeta(
                    name=seq_name,
                    min_value=min_val,
                    max_value=max_val,
                    increment_by=inc_by,
                    last_number=last_num,
                )
            )
    return sequences


def _fetch_indexes(cursor: oracledb.Cursor, config: LeaiConfig) -> list[IndexMeta]:
    cursor.execute(
        """
        SELECT index_name, table_name, uniqueness
        FROM all_indexes
        WHERE owner = :owner
          AND index_type != 'LOB'
        ORDER BY index_name
        """,
        owner=config.schema_name,
    )
    indexes: dict[str, IndexMeta] = {}
    for idx_name, tbl_name, uniqueness in cursor.fetchall():
        if _should_include(idx_name, config):
            indexes[idx_name] = IndexMeta(name=idx_name, table_name=tbl_name, uniqueness=uniqueness or "NONUNIQUE")

    if not indexes:
        return []

    idx_names = tuple(indexes.keys())
    cols_sql = """
        SELECT index_name, column_name
        FROM all_ind_columns
        WHERE index_owner = :owner
          AND index_name IN ({table_placeholders})
        ORDER BY index_name, column_position
    """
    for idx_name, col_name in _fetch_in_table_chunks(cursor, cols_sql, config.schema_name, idx_names):
        if idx_name in indexes:
            indexes[idx_name].columns.append(col_name)

    return [indexes[name] for name in sorted(idx_names)]


def _fetch_synonyms(cursor: oracledb.Cursor, config: LeaiConfig) -> list[SynonymMeta]:
    cursor.execute(
        """
        SELECT synonym_name, table_owner, table_name, db_link
        FROM all_synonyms
        WHERE owner = :owner
        ORDER BY synonym_name
        """,
        owner=config.schema_name,
    )
    synonyms: list[SynonymMeta] = []
    for syn_name, tbl_owner, tbl_name, db_link in cursor.fetchall():
        if _should_include(syn_name, config):
            synonyms.append(
                SynonymMeta(
                    name=syn_name,
                    table_owner=tbl_owner,
                    table_name=tbl_name,
                    db_link=db_link,
                )
            )
    return synonyms


def fetch_schema_metadata(config: LeaiConfig) -> SchemaMetadata:
    connection = oracledb.connect(**_build_connect_kwargs(config.dsn))
    try:
        cursor = connection.cursor()
        schema_meta = SchemaMetadata()
        types = set(config.object_types)

        if "tables" in types:
            schema_meta.tables = _fetch_tables(cursor, config)
        if "views" in types:
            schema_meta.views = _fetch_views(cursor, config)
        if "mviews" in types:
            schema_meta.mviews = _fetch_mviews(cursor, config)

        code_target_types = set()
        if "procedures" in types:
            code_target_types.add("PROCEDURE")
        if "functions" in types:
            code_target_types.add("FUNCTION")
        if "packages" in types:
            code_target_types.union_update({"PACKAGE", "PACKAGE BODY"}) if hasattr(set, "union_update") else code_target_types.update({"PACKAGE", "PACKAGE BODY"})

        if code_target_types:
            schema_meta.code_objects = _fetch_code_objects(cursor, config, code_target_types)

        if "triggers" in types:
            schema_meta.triggers = _fetch_triggers(cursor, config)
        if "sequences" in types:
            schema_meta.sequences = _fetch_sequences(cursor, config)
        if "indexes" in types:
            schema_meta.indexes = _fetch_indexes(cursor, config)
        if "synonyms" in types:
            schema_meta.synonyms = _fetch_synonyms(cursor, config)

        return schema_meta
    finally:
        connection.close()
