from __future__ import annotations

import re
from collections import defaultdict
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


def _detect_catalog_prefix(cursor: oracledb.Cursor) -> str:
    try:
        cursor.execute("SELECT 1 FROM dba_tables WHERE ROWNUM = 1")
        cursor.fetchone()
        return "dba"
    except Exception:
        return "all"


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
    for table_name, column_name in _fetch_in_table_chunks(cursor, pks_sql, config.schema_name, table_names):
        if table_name in tables:
            tables[table_name].primary_keys.append(column_name)

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

    code_objs: list[CodeObjectMeta] = []
    seen = set()
    for obj_name, obj_type in raw_objs:
        if obj_type not in target_types:
            continue
        # Se existe PACKAGE BODY ou TYPE BODY, priorizar o BODY para obter a implementação completa
        if obj_type == "PACKAGE" and obj_name in pkg_bodies and "PACKAGE BODY" in target_types:
            continue
        if obj_type == "TYPE" and obj_name in type_bodies and "TYPE BODY" in target_types:
            continue
        if (obj_name, obj_type) in seen:
            continue
        if not _should_include(obj_name, config):
            continue
        seen.add((obj_name, obj_type))

        cursor.execute(
            f"""
            SELECT text
            FROM {prefix}_source
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


ORACLE_SYSTEM_SCHEMAS = {
    "ANONYMOUS", "APEX_040000", "APEX_040200", "APEX_050000", "APEX_180000",
    "APEX_190000", "APEX_200000", "APEX_210000", "APEX_220000", "APEX_230000",
    "APEX_PUBLIC_USER", "APPQOSSYS", "AUDSYS", "AUTODDL", "CTXSYS", "DBSNMP",
    "DIP", "DVF", "DVSYS", "EXFSYS", "GSMADMIN_INTERNAL", "GSMCATUSER",
    "GSMUSER", "LBACSYS", "LEAI", "MDSYS", "OASYS", "ORACLE_OCM", "ORDDATA",
    "ORDPLUGINS", "ORDSYS", "OUTLN", "PDBADMIN", "REMOTE_SCHEDULER_AGENT",
    "SI_INFORMTN_SCHEMA", "SYS", "SYS$UMF", "SYSBACKUP", "SYSDG", "SYSKM",
    "SYSRAC", "SYSTEM", "TESTE", "WMSYS", "XDB", "XS$NULL", "ZABBIX"
}


def fetch_available_schemas(connection: oracledb.Connection, config: LeaiConfig) -> list[str]:
    if config.is_all_schemas or "ALL" in config.schemas:
        cursor = connection.cursor()
        prefix = _detect_catalog_prefix(cursor)
        cursor.execute(f"SELECT username FROM {prefix}_users ORDER BY username")
        all_users = [row[0].upper() for row in cursor.fetchall()]
        return [u for u in all_users if u not in ORACLE_SYSTEM_SCHEMAS]
    return config.schemas


from typing import Callable


def _fetch_object_timestamps(cursor: oracledb.Cursor, owner: str, prefix: str = "all") -> dict[tuple[str, str], tuple[str, str, str]]:
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
    for obj_name, obj_type, created_at, last_ddl, owner_name in cursor.fetchall():
        timestamps[(str(obj_name).upper(), str(obj_type).upper())] = (
            str(created_at) if created_at else "",
            str(last_ddl) if last_ddl else "",
            str(owner_name) if owner_name else "",
        )
    return timestamps


def fetch_schema_metadata(
    config: LeaiConfig,
    schema_name: str | None = None,
    callback: Callable[[str, int, int, int], None] | None = None,
) -> SchemaMetadata:
    target_schema = (schema_name or config.schema_name).upper()
    connection = oracledb.connect(**_build_connect_kwargs(config.dsn))
    try:
        cursor = connection.cursor()
        prefix = _detect_catalog_prefix(cursor)
        schema_meta = SchemaMetadata(schema_name=target_schema)
        types = set(config.object_types)

        # Criar uma config temporária apontando para target_schema para reutilizar os fetchers internos
        temp_config = config.model_copy()
        temp_config.schemas = [target_schema]

        code_target_types = set()
        if "procedures" in types:
            code_target_types.add("PROCEDURE")
        if "functions" in types:
            code_target_types.add("FUNCTION")
        if "packages" in types:
            code_target_types.update({"PACKAGE", "PACKAGE BODY"})
        if "types" in types:
            code_target_types.update({"TYPE", "TYPE BODY"})

        # Calcular número total de etapas ativas para percentual intra-schema
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
            schema_meta.tables = _fetch_tables(cursor, temp_config, prefix=prefix)
            current_step += 1
            if callback:
                callback("Tabelas", len(schema_meta.tables), current_step, total_steps)

        if "views" in types:
            schema_meta.views = _fetch_views(cursor, temp_config, prefix=prefix)
            current_step += 1
            if callback:
                callback("Views", len(schema_meta.views), current_step, total_steps)

        if "mviews" in types:
            schema_meta.mviews = _fetch_mviews(cursor, temp_config, prefix=prefix)
            current_step += 1
            if callback:
                callback("Materialized Views", len(schema_meta.mviews), current_step, total_steps)

        if code_target_types:
            schema_meta.code_objects = _fetch_code_objects(cursor, temp_config, code_target_types, prefix=prefix)
            current_step += 1
            if callback:
                callback("Code Objects", len(schema_meta.code_objects), current_step, total_steps)

        if "triggers" in types:
            schema_meta.triggers = _fetch_triggers(cursor, temp_config, prefix=prefix)
            current_step += 1
            if callback:
                callback("Triggers", len(schema_meta.triggers), current_step, total_steps)

        if "sequences" in types:
            schema_meta.sequences = _fetch_sequences(cursor, temp_config, prefix=prefix)
            current_step += 1
            if callback:
                callback("Sequences", len(schema_meta.sequences), current_step, total_steps)

        if "indexes" in types:
            schema_meta.indexes = _fetch_indexes(cursor, temp_config, prefix=prefix)
            current_step += 1
            if callback:
                callback("Índices", len(schema_meta.indexes), current_step, total_steps)

        if "synonyms" in types:
            schema_meta.synonyms = _fetch_synonyms(cursor, temp_config, prefix=prefix)
            current_step += 1
            if callback:
                callback("Sinônimos", len(schema_meta.synonyms), current_step, total_steps)

        # Enriquecer os objetos com os metadados de auditoria (CREATED, LAST_DDL_TIME, OWNER)
        try:
            timestamps = _fetch_object_timestamps(cursor, target_schema, prefix=prefix)
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
                    else:
                        for (o_name, t_type), (c_at, l_ddl, l_by) in timestamps.items():
                            if o_name == item.name.upper() and (t_type == otype or not default_type):
                                item.created_at = c_at
                                item.last_ddl_time = l_ddl
                                item.last_modified_by = l_by
                                break
        except Exception:
            pass

        return schema_meta
    finally:
        connection.close()


def fetch_focal_trace(
    config: LeaiConfig,
    object_name: str,
    schema_name: str | None = None,
    max_depth: int = 1,
) -> ObjectTraceResult:
    target_schema = (schema_name or config.schema_name).upper()
    target_upper = object_name.strip().upper()
    connection = oracledb.connect(**_build_connect_kwargs(config.dsn))
    try:
        cursor = connection.cursor()
        prefix = _detect_catalog_prefix(cursor)

        # 1. Descobrir tipo do objeto focal
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
            raise ValueError(f"Objeto '{target_upper}' não encontrado no schema '{target_schema}'.")

        focal_type = types_found[0]
        if "PACKAGE BODY" in types_found or "PACKAGE" in types_found:
            focal_type = "PACKAGE"

        # Carregar metadados do objeto focal
        focal_cfg = config.model_copy()
        focal_cfg.schemas = [target_schema]
        focal_cfg.include = [target_upper]
        focal_meta_schema = fetch_schema_metadata(focal_cfg, schema_name=target_schema)

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

            for curr_name in current_layer:
                # A) ALL_DEPENDENCIES
                cursor.execute(
                    f"""
                    SELECT name, type, referenced_name, referenced_type
                    FROM {prefix}_dependencies
                    WHERE (referenced_owner = :owner AND referenced_name = :target)
                       OR (owner = :owner AND name = :target)
                    ORDER BY type, name
                    """,
                    owner=target_schema,
                    target=curr_name,
                )
                for s_name, s_type, r_name, r_type in cursor.fetchall():
                    s_upper = s_name.upper()
                    r_upper = r_name.upper()
                    if s_upper == curr_name:
                        link_key = (curr_name, r_upper, "DEPENDS_ON")
                        if link_key not in seen_links:
                            seen_links.add(link_key)
                            result.dependencies.append(
                                DependencyLink(
                                    source_name=curr_name,
                                    source_type=s_type,
                                    target_name=r_upper,
                                    target_type=r_type,
                                    relation_type="DEPENDS_ON",
                                    details=f"{curr_name} referencia {r_type} {r_upper}",
                                    depth=current_depth,
                                )
                            )
                        if r_upper not in visited_nodes:
                            visited_nodes.add(r_upper)
                            next_layer.add(r_upper)
                            all_related_names.add(r_upper)
                    else:
                        link_key = (s_upper, curr_name, "REFERENCED_BY")
                        if link_key not in seen_links:
                            seen_links.add(link_key)
                            result.dependencies.append(
                                DependencyLink(
                                    source_name=s_upper,
                                    source_type=s_type,
                                    target_name=curr_name,
                                    target_type=r_type,
                                    relation_type="REFERENCED_BY",
                                    details=f"{s_type} {s_upper} depende de {curr_name}",
                                    depth=current_depth,
                                )
                            )
                        if s_upper not in visited_nodes:
                            visited_nodes.add(s_upper)
                            next_layer.add(s_upper)
                            all_related_names.add(s_upper)

                # B) Foreign Keys e Triggers (se for tabela)
                cursor.execute(
                    f"""
                    SELECT c.table_name, cc.column_name, c.constraint_name, rcc.column_name AS ref_column
                    FROM {prefix}_constraints c
                    JOIN {prefix}_cons_columns cc ON cc.owner = c.owner AND cc.constraint_name = c.constraint_name
                    JOIN {prefix}_constraints rc ON rc.owner = c.r_owner AND rc.constraint_name = c.r_constraint_name
                    JOIN {prefix}_cons_columns rcc ON rcc.owner = rc.owner AND rcc.constraint_name = rc.constraint_name AND rcc.position = cc.position
                    WHERE c.constraint_type = 'R'
                      AND rc.owner = :owner
                      AND rc.table_name = :target
                    ORDER BY c.table_name, c.constraint_name
                    """,
                    owner=target_schema,
                    target=curr_name,
                )
                for child_table, child_col, c_name, parent_col in cursor.fetchall():
                    child_upper = child_table.upper()
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

                cursor.execute(
                    f"""
                    SELECT trigger_name, trigger_type, triggering_event
                    FROM {prefix}_triggers
                    WHERE owner = :owner AND table_name = :target
                    """,
                    owner=target_schema,
                    target=curr_name,
                )
                for trg_name, trg_type, trg_ev in cursor.fetchall():
                    trg_upper = trg_name.upper()
                    link_key = ("TRIGGER", trg_upper, curr_name)
                    if link_key not in seen_links:
                        seen_links.add(link_key)
                        result.dependencies.append(
                            DependencyLink(
                                source_name=trg_upper,
                                source_type="TRIGGER",
                                target_name=curr_name,
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

        # Extrair metadados dos objetos relacionados encontrados
        if all_related_names:
            rel_cfg = config.model_copy()
            rel_cfg.schemas = [target_schema]
            rel_cfg.include = list(all_related_names)
            rel_meta_schema = fetch_schema_metadata(rel_cfg, schema_name=target_schema)
            result.related_tables = rel_meta_schema.tables
            result.related_views = rel_meta_schema.views
            result.related_code_objects = rel_meta_schema.code_objects
            result.related_triggers = rel_meta_schema.triggers

        return result
    finally:
        connection.close()


