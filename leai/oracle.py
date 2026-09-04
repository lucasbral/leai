from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Callable
from urllib.parse import unquote, urlparse

import oracledb

from leai.config import LeaiConfig
from leai.models import (
    CodeObjectMeta,
    ColumnMeta,
    DependencyLink,
    ForeignKeyMeta,
    IndexMeta,
    MaterializedViewMeta,
    ObjectTraceResult,
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
        raise ValueError("Invalid Oracle DSN URL. Provide host, port, and service name.")

    easy_connect = f"{parsed.hostname}:{parsed.port}/{service}" if parsed.port else f"{parsed.hostname}/{service}"
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


def _is_included(name: str, patterns: list[str]) -> bool:
    upper = name.upper()
    return any(_like_pattern_to_regex(pattern.upper()).match(upper) for pattern in patterns)


def _should_include(name: str, config: LeaiConfig) -> bool:
    name_upper = name.upper()
    if config.include and not _is_included(name_upper, config.include):
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


_CATALOG_PREFIX_CACHE: dict[int, str] = {}


def _detect_catalog_prefix(cursor: oracledb.Cursor) -> str:
    conn_id = None
    try:
        if hasattr(cursor, "connection") and cursor.connection:
            conn_id = id(cursor.connection)
            if conn_id in _CATALOG_PREFIX_CACHE:
                return _CATALOG_PREFIX_CACHE[conn_id]
    except Exception:
        pass

    prefix = "all"
    try:
        cursor.execute("SELECT 1 FROM dba_tables WHERE ROWNUM = 1")
        cursor.fetchone()
        prefix = "dba"
    except Exception:
        prefix = "all"

    if conn_id is not None:
        _CATALOG_PREFIX_CACHE[conn_id] = prefix
    return prefix


def _fetch_tables(cursor: oracledb.Cursor, config: LeaiConfig, prefix: str = "all") -> list[TableMeta]:
    cursor.execute(
        f"""
        SELECT t.table_name, tc.comments
        FROM {prefix}_tables t
        LEFT JOIN {prefix}_tab_comments tc
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
    is_unfiltered = not config.include and not config.exclude

    if is_unfiltered:
        columns_sql = f"""
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
            FROM {prefix}_tab_columns c
            LEFT JOIN {prefix}_col_comments cc
              ON cc.owner = c.owner
             AND cc.table_name = c.table_name
             AND cc.column_name = c.column_name
            WHERE c.owner = :owner
            ORDER BY c.table_name, c.column_id
        """
        cursor.execute(columns_sql, owner=config.schema_name)
        col_rows = cursor.fetchall()
    else:
        columns_sql = f"""
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
            FROM {prefix}_tab_columns c
            LEFT JOIN {prefix}_col_comments cc
              ON cc.owner = c.owner
             AND cc.table_name = c.table_name
             AND cc.column_name = c.column_name
            WHERE c.owner = :owner
              AND c.table_name IN ({{table_placeholders}})
            ORDER BY c.table_name, c.column_id
        """
        col_rows = _fetch_in_table_chunks(cursor, columns_sql, config.schema_name, table_names)

    for row in col_rows:
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

    if is_unfiltered:
        pks_sql = f"""
            SELECT acc.table_name, acc.column_name
            FROM {prefix}_constraints ac
            JOIN {prefix}_cons_columns acc
              ON acc.owner = ac.owner
             AND acc.constraint_name = ac.constraint_name
            WHERE ac.owner = :owner
              AND ac.constraint_type = 'P'
            ORDER BY acc.table_name, acc.position
        """
        cursor.execute(pks_sql, owner=config.schema_name)
        pk_rows = cursor.fetchall()
    else:
        pks_sql = f"""
            SELECT acc.table_name, acc.column_name
            FROM {prefix}_constraints ac
            JOIN {prefix}_cons_columns acc
              ON acc.owner = ac.owner
             AND acc.constraint_name = ac.constraint_name
            WHERE ac.owner = :owner
              AND ac.constraint_type = 'P'
              AND acc.table_name IN ({{table_placeholders}})
            ORDER BY acc.table_name, acc.position
        """
        pk_rows = _fetch_in_table_chunks(cursor, pks_sql, config.schema_name, table_names)

    for table_name, column_name in pk_rows:
        if table_name in tables:
            tables[table_name].primary_keys.append(column_name)

    if is_unfiltered:
        fks_sql = f"""
            SELECT ac.constraint_name,
                   src.table_name,
                   src.column_name,
                   tgt.table_name,
                   tgt.column_name
            FROM {prefix}_constraints ac
            JOIN {prefix}_cons_columns src
              ON src.owner = ac.owner
             AND src.constraint_name = ac.constraint_name
            JOIN {prefix}_constraints ref
              ON ref.owner = ac.r_owner
             AND ref.constraint_name = ac.r_constraint_name
            JOIN {prefix}_cons_columns tgt
              ON tgt.owner = ref.owner
             AND tgt.constraint_name = ref.constraint_name
             AND tgt.position = src.position
            WHERE ac.owner = :owner
              AND ac.constraint_type = 'R'
            ORDER BY src.table_name, ac.constraint_name, src.position
        """
        cursor.execute(fks_sql, owner=config.schema_name)
        fk_rows = cursor.fetchall()
    else:
        fks_sql = f"""
            SELECT ac.constraint_name,
                   src.table_name,
                   src.column_name,
                   tgt.table_name,
                   tgt.column_name
            FROM {prefix}_constraints ac
            JOIN {prefix}_cons_columns src
              ON src.owner = ac.owner
             AND src.constraint_name = ac.constraint_name
            JOIN {prefix}_constraints ref
              ON ref.owner = ac.r_owner
             AND ref.constraint_name = ac.r_constraint_name
            JOIN {prefix}_cons_columns tgt
              ON tgt.owner = ref.owner
             AND tgt.constraint_name = ref.constraint_name
             AND tgt.position = src.position
            WHERE ac.owner = :owner
              AND ac.constraint_type = 'R'
              AND src.table_name IN ({{table_placeholders}})
            ORDER BY src.table_name, ac.constraint_name, src.position
        """
        fk_rows = _fetch_in_table_chunks(cursor, fks_sql, config.schema_name, table_names)

    grouped_fks: dict[tuple[str, str], list[ForeignKeyMeta]] = defaultdict(list)
    for constraint_name, table_name, column_name, ref_table, ref_col in fk_rows:
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


def _fetch_views(cursor: oracledb.Cursor, config: LeaiConfig, prefix: str = "all") -> list[ViewMeta]:
    cursor.execute(
        f"""
        SELECT v.view_name, v.text, tc.comments
        FROM {prefix}_views v
        LEFT JOIN {prefix}_tab_comments tc
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
    is_unfiltered = not config.include and not config.exclude

    if is_unfiltered:
        columns_sql = f"""
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
            FROM {prefix}_tab_columns c
            LEFT JOIN {prefix}_col_comments cc
              ON cc.owner = c.owner
             AND cc.table_name = c.table_name
             AND cc.column_name = c.column_name
            WHERE c.owner = :owner
            ORDER BY c.table_name, c.column_id
        """
        cursor.execute(columns_sql, owner=config.schema_name)
        col_rows = cursor.fetchall()
    else:
        columns_sql = f"""
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
            FROM {prefix}_tab_columns c
            LEFT JOIN {prefix}_col_comments cc
              ON cc.owner = c.owner
             AND cc.table_name = c.table_name
             AND cc.column_name = c.column_name
            WHERE c.owner = :owner
              AND c.table_name IN ({{table_placeholders}})
            ORDER BY c.table_name, c.column_id
        """
        col_rows = _fetch_in_table_chunks(cursor, columns_sql, config.schema_name, view_names)

    for row in col_rows:
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


def _fetch_mviews(cursor: oracledb.Cursor, config: LeaiConfig, prefix: str = "all") -> list[MaterializedViewMeta]:
    cursor.execute(
        f"""
        SELECT mv.mview_name, mv.query, mv.refresh_mode, mv.updatable, tc.comments
        FROM {prefix}_mviews mv
        LEFT JOIN {prefix}_tab_comments tc
          ON tc.owner = mv.owner AND tc.table_name = mv.mview_name
        WHERE mv.owner = :owner
        ORDER BY mv.mview_name
        """,
        owner=config.schema_name,
    )
    mviews: dict[str, MaterializedViewMeta] = {}
    for mv_name, query, refresh_mode, updatable, comment in cursor.fetchall():
        if _should_include(mv_name, config):
            mviews[mv_name] = MaterializedViewMeta(
                name=mv_name,
                query=str(query) if query else None,
                refresh_mode=refresh_mode,
                refresh_type=None,
                updatable=updatable == "Y",
                comment=comment,
            )

    if not mviews:
        return []

    mv_names = tuple(mviews.keys())
    is_unfiltered = not config.include and not config.exclude

    if is_unfiltered:
        columns_sql = f"""
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
            FROM {prefix}_tab_columns c
            LEFT JOIN {prefix}_col_comments cc
              ON cc.owner = c.owner
             AND cc.table_name = c.table_name
             AND cc.column_name = c.column_name
            WHERE c.owner = :owner
            ORDER BY c.table_name, c.column_id
        """
        cursor.execute(columns_sql, owner=config.schema_name)
        col_rows = cursor.fetchall()
    else:
        columns_sql = f"""
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
            FROM {prefix}_tab_columns c
            LEFT JOIN {prefix}_col_comments cc
              ON cc.owner = c.owner
             AND cc.table_name = c.table_name
             AND cc.column_name = c.column_name
            WHERE c.owner = :owner
              AND c.table_name IN ({{table_placeholders}})
            ORDER BY c.table_name, c.column_id
        """
        col_rows = _fetch_in_table_chunks(cursor, columns_sql, config.schema_name, mv_names)

    for row in col_rows:
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


def _fetch_code_objects(cursor: oracledb.Cursor, config: LeaiConfig, target_types: set[str], prefix: str = "all") -> list[CodeObjectMeta]:
    cursor.execute(
        f"""
        SELECT object_name, object_type
        FROM {prefix}_objects
        WHERE owner = :owner
          AND object_type IN ('PROCEDURE', 'FUNCTION', 'PACKAGE', 'PACKAGE BODY', 'TYPE', 'TYPE BODY')
        ORDER BY object_type, object_name
        """,
        owner=config.schema_name,
    )
    raw_objs = cursor.fetchall()

    pkg_bodies = {name for name, otype in raw_objs if otype == "PACKAGE BODY"}
    type_bodies = {name for name, otype in raw_objs if otype == "TYPE BODY"}

    target_objs: list[tuple[str, str]] = []
    seen = set()
    for obj_name, obj_type in raw_objs:
        if obj_type not in target_types:
            continue
        # If PACKAGE BODY or TYPE BODY exists, prioritize BODY to retrieve complete implementation
        if obj_type == "PACKAGE" and obj_name in pkg_bodies and "PACKAGE BODY" in target_types:
            continue
        if obj_type == "TYPE" and obj_name in type_bodies and "TYPE BODY" in target_types:
            continue
        if (obj_name, obj_type) in seen:
            continue
        if not _should_include(obj_name, config):
            continue
        seen.add((obj_name, obj_type))
        target_objs.append((obj_name, obj_type))

    if not target_objs:
        return []

    # Batch fetch source code lines in a single query (or chunked by names if filtered)
    sources: dict[tuple[str, str], list[str]] = defaultdict(list)
    needed_types = sorted({otype for _, otype in target_objs})
    is_unfiltered = not config.include and not config.exclude

    if is_unfiltered:
        type_placeholders = ", ".join(f":tp{j}" for j in range(len(needed_types)))
        src_sql = f"""
            SELECT name, type, text
            FROM {prefix}_source
            WHERE owner = :owner
              AND type IN ({type_placeholders})
            ORDER BY name, type, line
        """
        params = {"owner": config.schema_name}
        for j, tp in enumerate(needed_types):
            params[f"tp{j}"] = tp
        cursor.execute(src_sql, params)
        for name, otype, text in cursor.fetchall():
            sources[(name, otype)].append(text)
    else:
        needed_names = tuple(sorted({name for name, _ in target_objs}))
        chunk_size = 100
        for i in range(0, len(needed_names), chunk_size):
            chunk = needed_names[i : i + chunk_size]
            name_placeholders = ", ".join(f":nm{j}" for j in range(len(chunk)))
            type_placeholders = ", ".join(f":tp{j}" for j in range(len(needed_types)))
            src_sql = f"""
                SELECT name, type, text
                FROM {prefix}_source
                WHERE owner = :owner
                  AND name IN ({name_placeholders})
                  AND type IN ({type_placeholders})
                ORDER BY name, type, line
            """
            params = {"owner": config.schema_name}
            for j, nm in enumerate(chunk):
                params[f"nm{j}"] = nm
            for j, tp in enumerate(needed_types):
                params[f"tp{j}"] = tp
            cursor.execute(src_sql, params)
            for name, otype, text in cursor.fetchall():
                sources[(name, otype)].append(text)

    code_objs: list[CodeObjectMeta] = []
    for obj_name, obj_type in target_objs:
        source_lines = sources.get((obj_name, obj_type))
        source = "".join(source_lines) if source_lines else None
        code_obj = CodeObjectMeta(name=obj_name, object_type=obj_type, source=source)
        if obj_type in {"PACKAGE", "PACKAGE BODY"} and source:
            code_obj.subprograms = _split_package_source(obj_name, source)
        code_objs.append(code_obj)

    return code_objs


def _fetch_triggers(cursor: oracledb.Cursor, config: LeaiConfig, prefix: str = "all") -> list[TriggerMeta]:
    cursor.execute(
        f"""
        SELECT trigger_name, table_name, trigger_type, triggering_event, status, trigger_body
        FROM {prefix}_triggers
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


def _fetch_sequences(cursor: oracledb.Cursor, config: LeaiConfig, prefix: str = "all") -> list[SequenceMeta]:
    owner_col = "sequence_owner"
    cursor.execute(
        f"""
        SELECT sequence_name, min_value, max_value, increment_by, last_number
        FROM {prefix}_sequences
        WHERE {owner_col} = :owner
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


def _fetch_indexes(cursor: oracledb.Cursor, config: LeaiConfig, prefix: str = "all") -> list[IndexMeta]:
    cursor.execute(
        f"""
        SELECT index_name, table_name, uniqueness
        FROM {prefix}_indexes
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
    cols_sql = f"""
        SELECT index_name, column_name
        FROM {prefix}_ind_columns
        WHERE index_owner = :owner
          AND index_name IN ({{table_placeholders}})
        ORDER BY index_name, column_position
    """
    for idx_name, col_name in _fetch_in_table_chunks(cursor, cols_sql, config.schema_name, idx_names):
        if idx_name in indexes:
            indexes[idx_name].columns.append(col_name)

    return [indexes[name] for name in sorted(idx_names)]


def _fetch_synonyms(cursor: oracledb.Cursor, config: LeaiConfig, prefix: str = "all") -> list[SynonymMeta]:
    cursor.execute(
        f"""
        SELECT synonym_name, table_owner, table_name, db_link
        FROM {prefix}_synonyms
        WHERE owner = :owner
           OR (owner = 'PUBLIC' AND table_owner = :owner)
        ORDER BY synonym_name
        """,
        owner=config.schema_name,
    )
    synonyms: list[SynonymMeta] = []
    seen = set()
    for syn_name, tbl_owner, tbl_name, db_link in cursor.fetchall():
        syn_upper = syn_name.upper()
        if syn_upper in seen:
            continue
        if _should_include(syn_name, config):
            seen.add(syn_upper)
            synonyms.append(
                SynonymMeta(
                    name=syn_name,
                    table_owner=tbl_owner,
                    table_name=tbl_name,
                    db_link=db_link,
                )
            )
    return synonyms


ORACLE_SYSTEM_SCHEMAS = {
    "ANONYMOUS",
    "APEX_040000",
    "APEX_040200",
    "APEX_050000",
    "APEX_180000",
    "APEX_190000",
    "APEX_200000",
    "APEX_210000",
    "APEX_220000",
    "APEX_230000",
    "APEX_PUBLIC_USER",
    "APPQOSSYS",
    "AUDSYS",
    "AUTODDL",
    "CTXSYS",
    "DBSNMP",
    "DIP",
    "DVF",
    "DVSYS",
    "EXFSYS",
    "GSMADMIN_INTERNAL",
    "GSMCATUSER",
    "GSMUSER",
    "LBACSYS",
    "LEAI",
    "MDSYS",
    "OASYS",
    "ORACLE_OCM",
    "ORDDATA",
    "ORDPLUGINS",
    "ORDSYS",
    "OUTLN",
    "PDBADMIN",
    "REMOTE_SCHEDULER_AGENT",
    "SI_INFORMTN_SCHEMA",
    "SYS",
    "SYS$UMF",
    "SYSBACKUP",
    "SYSDG",
    "SYSKM",
    "SYSRAC",
    "SYSTEM",
    "TESTE",
    "WMSYS",
    "XDB",
    "XS$NULL",
    "ZABBIX",
}


def fetch_available_schemas(connection: oracledb.Connection, config: LeaiConfig) -> list[str]:
    if config.is_all_schemas or "ALL" in config.schemas:
        cursor = connection.cursor()
        prefix = _detect_catalog_prefix(cursor)
        cursor.execute(f"SELECT username FROM {prefix}_users ORDER BY username")
        all_users = [row[0].upper() for row in cursor.fetchall()]
        return [u for u in all_users if u not in ORACLE_SYSTEM_SCHEMAS]
    return config.schemas


def _fetch_object_timestamps(
    cursor: oracledb.Cursor, owner: str, prefix: str = "all"
) -> tuple[dict[tuple[str, str], tuple[str, str, str]], dict[str, tuple[str, str, str]]]:
    cursor.execute(
        f"""
        SELECT object_name,
               object_type,
               TO_CHAR(created, 'YYYY-MM-DD HH24:MI:SS') AS created_at,
               TO_CHAR(last_ddl_time, 'YYYY-MM-DD HH24:MI:SS') AS last_ddl_time,
               owner AS last_modified_by
        FROM {prefix}_objects
        WHERE owner = :owner
        """,
        owner=owner,
    )
    timestamps: dict[tuple[str, str], tuple[str, str, str]] = {}
    timestamps_by_name: dict[str, tuple[str, str, str]] = {}
    for obj_name, obj_type, created_at, last_ddl, owner_name in cursor.fetchall():
        name_str = str(obj_name).upper()
        type_str = str(obj_type).upper()
        data = (
            str(created_at) if created_at else "",
            str(last_ddl) if last_ddl else "",
            str(owner_name) if owner_name else "",
        )
        timestamps[(name_str, type_str)] = data
        if name_str not in timestamps_by_name:
            timestamps_by_name[name_str] = data
    return timestamps, timestamps_by_name


def _fetch_modified_object_names(cursor: oracledb.Cursor, owner: str, days: float | int, prefix: str = "all") -> set[str]:
    """Queries ALL_OBJECTS / DBA_OBJECTS for names of objects modified in the last N days (or fraction)."""
    try:
        cursor.execute(
            f"""
            SELECT DISTINCT object_name
            FROM {prefix}_objects
            WHERE owner = :owner
              AND last_ddl_time >= SYSDATE - :days
            """,
            owner=owner,
            days=float(days),
        )
        return {str(row[0]).upper() for row in cursor.fetchall()}
    except Exception:
        return set()


def fetch_schema_metadata(
    config: LeaiConfig,
    schema_name: str | None = None,
    callback: Callable[[str, int, int, int], None] | None = None,
    days: float | int | None = None,
    hours: float | int | None = None,
    connection: oracledb.Connection | None = None,
) -> SchemaMetadata:
    target_schema = (schema_name or config.schema_name).upper()
    should_close = False
    if connection is None:
        connection = oracledb.connect(**_build_connect_kwargs(config.dsn))
        should_close = True
    try:
        cursor = connection.cursor()
        cursor.arraysize = 1000
        cursor.prefetchrows = 1000
        prefix = _detect_catalog_prefix(cursor)
        schema_meta = SchemaMetadata(schema_name=target_schema)
        types = set(config.object_types)

        # Create a temporary config pointing to target_schema to reuse internal fetchers
        temp_config = config.model_copy()
        temp_config.schemas = [target_schema]

        # Calculate effective days filter (hours takes precedence if provided)
        effective_days: float | None = None
        if hours is not None and hours > 0:
            effective_days = float(hours) / 24.0
        elif days is not None and days > 0:
            effective_days = float(days)

        # If incremental extraction is requested, filter include list to only recently modified objects
        if effective_days is not None and effective_days > 0:
            modified_names = _fetch_modified_object_names(cursor, target_schema, effective_days, prefix=prefix)
            if temp_config.include:
                temp_config.include = [name for name in temp_config.include if name.upper() in modified_names]
                if not temp_config.include:
                    temp_config.include = ["__LEAI_NO_MATCHING_MODIFIED_OBJECTS__"]
            else:
                temp_config.include = list(modified_names) if modified_names else ["__LEAI_NO_MATCHING_MODIFIED_OBJECTS__"]

        code_target_types = set()
        if "procedures" in types:
            code_target_types.add("PROCEDURE")
        if "functions" in types:
            code_target_types.add("FUNCTION")
        if "packages" in types:
            code_target_types.update({"PACKAGE", "PACKAGE BODY"})
        if "types" in types:
            code_target_types.update({"TYPE", "TYPE BODY"})

        # Calculate total active steps for progress tracking
        active_steps = []
        if "tables" in types:
            active_steps.append("tables")
        if "views" in types:
            active_steps.append("views")
        if "mviews" in types:
            active_steps.append("mviews")
        if code_target_types:
            active_steps.append("code_objects")
        if "triggers" in types:
            active_steps.append("triggers")
        if "sequences" in types:
            active_steps.append("sequences")
        if "indexes" in types:
            active_steps.append("indexes")
        if "synonyms" in types:
            active_steps.append("synonyms")

        total_steps = len(active_steps)
        current_step = 0

        if "tables" in types:
            if callback:
                callback("Tables (querying...)", 0, current_step, total_steps)
            schema_meta.tables = _fetch_tables(cursor, temp_config, prefix=prefix)
            current_step += 1
            if callback:
                callback("Tables", len(schema_meta.tables), current_step, total_steps)

        if "views" in types:
            if callback:
                callback("Views (querying...)", 0, current_step, total_steps)
            schema_meta.views = _fetch_views(cursor, temp_config, prefix=prefix)
            current_step += 1
            if callback:
                callback("Views", len(schema_meta.views), current_step, total_steps)

        if "mviews" in types:
            if callback:
                callback("Materialized Views (querying...)", 0, current_step, total_steps)
            schema_meta.mviews = _fetch_mviews(cursor, temp_config, prefix=prefix)
            current_step += 1
            if callback:
                callback("Materialized Views", len(schema_meta.mviews), current_step, total_steps)

        if code_target_types:
            if callback:
                callback("Code Objects (querying...)", 0, current_step, total_steps)
            schema_meta.code_objects = _fetch_code_objects(cursor, temp_config, code_target_types, prefix=prefix)
            current_step += 1
            if callback:
                callback("Code Objects", len(schema_meta.code_objects), current_step, total_steps)

        if "triggers" in types:
            if callback:
                callback("Triggers (querying...)", 0, current_step, total_steps)
            schema_meta.triggers = _fetch_triggers(cursor, temp_config, prefix=prefix)
            current_step += 1
            if callback:
                callback("Triggers", len(schema_meta.triggers), current_step, total_steps)

        if "sequences" in types:
            if callback:
                callback("Sequences (querying...)", 0, current_step, total_steps)
            schema_meta.sequences = _fetch_sequences(cursor, temp_config, prefix=prefix)
            current_step += 1
            if callback:
                callback("Sequences", len(schema_meta.sequences), current_step, total_steps)

        if "indexes" in types:
            if callback:
                callback("Indexes (querying...)", 0, current_step, total_steps)
            schema_meta.indexes = _fetch_indexes(cursor, temp_config, prefix=prefix)
            current_step += 1
            if callback:
                callback("Indexes", len(schema_meta.indexes), current_step, total_steps)

        if "synonyms" in types:
            if callback:
                callback("Synonyms (querying...)", 0, current_step, total_steps)
            schema_meta.synonyms = _fetch_synonyms(cursor, temp_config, prefix=prefix)
            current_step += 1
            if callback:
                callback("Synonyms", len(schema_meta.synonyms), current_step, total_steps)

        # Enrich objects with audit metadata (CREATED, LAST_DDL_TIME, OWNER)
        try:
            timestamps, timestamps_by_name = _fetch_object_timestamps(cursor, target_schema, prefix=prefix)
            category_mapping = [
                (schema_meta.tables, "TABLE"),
                (schema_meta.views, "VIEW"),
                (schema_meta.mviews, "MATERIALIZED VIEW"),
                (schema_meta.code_objects, None),
                (schema_meta.triggers, "TRIGGER"),
                (schema_meta.sequences, "SEQUENCE"),
                (schema_meta.indexes, "INDEX"),
                (schema_meta.synonyms, "SYNONYM"),
            ]
            for category_list, default_type in category_mapping:
                for item in category_list:
                    otype = (getattr(item, "object_type", None) or default_type or "TABLE").upper()
                    key = (item.name.upper(), otype)
                    if key in timestamps:
                        item.created_at, item.last_ddl_time, item.last_modified_by = timestamps[key]
                    elif item.name.upper() in timestamps_by_name:
                        item.created_at, item.last_ddl_time, item.last_modified_by = timestamps_by_name[item.name.upper()]
        except Exception:
            pass

        return schema_meta
    finally:
        if should_close:
            connection.close()


def fetch_focal_trace(
    config: LeaiConfig,
    object_name: str,
    schema_name: str | None = None,
    max_depth: int = 1,
    connection: oracledb.Connection | None = None,
) -> ObjectTraceResult:
    try:
        max_depth = int(getattr(max_depth, "default", max_depth))
    except Exception:
        max_depth = 1
    target_schema = (schema_name or config.schema_name).upper()
    target_upper = object_name.strip().upper()
    should_close = False
    if connection is None:
        connection = oracledb.connect(**_build_connect_kwargs(config.dsn))
        should_close = True
    try:
        cursor = connection.cursor()
        cursor.arraysize = 1000
        cursor.prefetchrows = 1000
        prefix = _detect_catalog_prefix(cursor)

        # 1. Discover focal object type
        cursor.execute(
            f"""
            SELECT object_type FROM {prefix}_objects
            WHERE owner = :owner AND object_name = :name
            """,
            owner=target_schema,
            name=target_upper,
        )
        types_found = [row[0].upper() for row in cursor.fetchall()]
        if not types_found:
            raise ValueError(f"Object '{target_upper}' not found in schema '{target_schema}'.")

        focal_type = types_found[0]
        if "PACKAGE BODY" in types_found or "PACKAGE" in types_found:
            focal_type = "PACKAGE"

        # Load focal object metadata reusing connection
        focal_cfg = config.model_copy()
        focal_cfg.schemas = [target_schema]
        focal_cfg.include = [target_upper]
        focal_meta_schema = fetch_schema_metadata(focal_cfg, schema_name=target_schema, connection=connection)

        focal_obj = None
        if focal_type == "TABLE" and focal_meta_schema.tables:
            focal_obj = focal_meta_schema.tables[0]
        elif focal_type == "VIEW" and focal_meta_schema.views:
            focal_obj = focal_meta_schema.views[0]
        elif focal_type == "MATERIALIZED VIEW" and focal_meta_schema.mviews:
            focal_obj = focal_meta_schema.mviews[0]
        elif focal_meta_schema.code_objects:
            focal_obj = focal_meta_schema.code_objects[0]
        elif focal_meta_schema.triggers:
            focal_obj = focal_meta_schema.triggers[0]

        result = ObjectTraceResult(
            focal_name=target_upper,
            focal_type=focal_type,
            focal_object=focal_obj,
        )

        all_related_names = set()
        visited_nodes = {target_upper}
        seen_links = set()
        current_layer = {target_upper}

        for current_depth in range(1, max(1, max_depth) + 1):
            if not current_layer:
                break
            next_layer = set()
            layer_items = list(current_layer)
            chunk_size = 50

            for i in range(0, len(layer_items), chunk_size):
                chunk = layer_items[i : i + chunk_size]
                chunk_params = {"owner": target_schema}
                placeholders = []
                for j, name in enumerate(chunk):
                    p_name = f"obj{j}"
                    chunk_params[p_name] = name
                    placeholders.append(f":{p_name}")
                p_str = ", ".join(placeholders)

                # A) ALL_DEPENDENCIES in batch for the layer chunk
                cursor.execute(
                    f"""
                    SELECT name, type, referenced_name, referenced_type
                    FROM {prefix}_dependencies
                    WHERE (referenced_owner = :owner AND referenced_name IN ({p_str}))
                       OR (owner = :owner AND name IN ({p_str}))
                    ORDER BY type, name
                    """,
                    chunk_params,
                )
                for s_name, s_type, r_name, r_type in cursor.fetchall():
                    s_upper = s_name.upper()
                    r_upper = r_name.upper()
                    if s_upper in current_layer:
                        link_key = (s_upper, r_upper, "DEPENDS_ON")
                        if link_key not in seen_links:
                            seen_links.add(link_key)
                            result.dependencies.append(
                                DependencyLink(
                                    source_name=s_upper,
                                    source_type=s_type,
                                    target_name=r_upper,
                                    target_type=r_type,
                                    relation_type="DEPENDS_ON",
                                    details=f"{s_upper} referencia {r_type} {r_upper}",
                                    depth=current_depth,
                                )
                            )
                        if r_upper not in visited_nodes:
                            visited_nodes.add(r_upper)
                            next_layer.add(r_upper)
                            all_related_names.add(r_upper)
                    if r_upper in current_layer:
                        link_key = (s_upper, r_upper, "REFERENCED_BY")
                        if link_key not in seen_links:
                            seen_links.add(link_key)
                            result.dependencies.append(
                                DependencyLink(
                                    source_name=s_upper,
                                    source_type=s_type,
                                    target_name=r_upper,
                                    target_type=r_type,
                                    relation_type="REFERENCED_BY",
                                    details=f"{s_type} {s_upper} depende de {r_upper}",
                                    depth=current_depth,
                                )
                            )
                        if s_upper not in visited_nodes:
                            visited_nodes.add(s_upper)
                            next_layer.add(s_upper)
                            all_related_names.add(s_upper)

                # B) Foreign Keys in batch for the layer chunk
                cursor.execute(
                    f"""
                    SELECT c.table_name, cc.column_name, c.constraint_name, rcc.column_name AS ref_column, rc.table_name AS parent_table
                    FROM {prefix}_constraints c
                    JOIN {prefix}_cons_columns cc ON cc.owner = c.owner AND cc.constraint_name = c.constraint_name
                    JOIN {prefix}_constraints rc ON rc.owner = c.r_owner AND rc.constraint_name = c.r_constraint_name
                    JOIN {prefix}_cons_columns rcc ON rcc.owner = rc.owner AND rcc.constraint_name = rc.constraint_name AND rcc.position = cc.position
                    WHERE c.constraint_type = 'R'
                      AND rc.owner = :owner
                      AND rc.table_name IN ({p_str})
                    ORDER BY c.table_name, c.constraint_name
                    """,
                    chunk_params,
                )
                for child_table, child_col, c_name, parent_col, p_tbl in cursor.fetchall():
                    child_upper = child_table.upper()
                    curr_name = (p_tbl or "").upper()
                    link_key = ("FK", child_upper, curr_name, (child_col or "").upper())
                    if link_key not in seen_links:
                        seen_links.add(link_key)
                        result.dependencies.append(
                            DependencyLink(
                                source_name=child_upper,
                                source_type="TABLE",
                                target_name=curr_name,
                                target_type="TABLE",
                                relation_type="FK_REFERENCED_BY",
                                details=f"Tabela filha {child_upper}.{child_col} -> {curr_name}.{parent_col} ({c_name})",
                                depth=current_depth,
                            )
                        )
                    if child_upper not in visited_nodes:
                        visited_nodes.add(child_upper)
                        next_layer.add(child_upper)
                        all_related_names.add(child_upper)

                # C) Triggers in batch for the layer chunk
                cursor.execute(
                    f"""
                    SELECT trigger_name, trigger_type, triggering_event, table_name
                    FROM {prefix}_triggers
                    WHERE owner = :owner AND table_name IN ({p_str})
                    """,
                    chunk_params,
                )
                for trg_name, trg_type, trg_ev, t_name in cursor.fetchall():
                    trg_upper = trg_name.upper()
                    tbl_upper = (t_name or "").upper()
                    link_key = ("TRIGGER", trg_upper, tbl_upper)
                    if link_key not in seen_links:
                        seen_links.add(link_key)
                        result.dependencies.append(
                            DependencyLink(
                                source_name=trg_upper,
                                source_type="TRIGGER",
                                target_name=tbl_upper,
                                target_type="TABLE",
                                relation_type="TRIGGER_ON",
                                details=f"{trg_type} {trg_ev}",
                                depth=current_depth,
                            )
                        )
                    if trg_upper not in visited_nodes:
                        visited_nodes.add(trg_upper)
                        next_layer.add(trg_upper)
                        all_related_names.add(trg_upper)

            current_layer = next_layer

        # Extract metadata of related objects found reusing connection
        if all_related_names:
            rel_cfg = config.model_copy()
            rel_cfg.schemas = [target_schema]
            rel_cfg.include = list(all_related_names)
            rel_meta_schema = fetch_schema_metadata(rel_cfg, schema_name=target_schema, connection=connection)
            result.related_tables = rel_meta_schema.tables
            result.related_views = rel_meta_schema.views
            result.related_code_objects = rel_meta_schema.code_objects
            result.related_triggers = rel_meta_schema.triggers

        return result
    finally:
        if should_close:
            connection.close()
