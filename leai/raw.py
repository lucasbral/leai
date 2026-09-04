from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

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


def _construct_column(data: dict[str, Any]) -> ColumnMeta:
    return ColumnMeta.model_construct(
        name=data.get("name", ""),
        data_type=data.get("data_type", ""),
        nullable=bool(data.get("nullable", False)),
        default=data.get("default"),
        comment=data.get("comment"),
    )


def _construct_foreign_key(data: dict[str, Any]) -> ForeignKeyMeta:
    return ForeignKeyMeta.model_construct(
        name=data.get("name", ""),
        column=data.get("column", ""),
        referenced_table=data.get("referenced_table", ""),
        referenced_column=data.get("referenced_column", ""),
    )


def _construct_table(data: dict[str, Any]) -> TableMeta:
    columns = [_construct_column(c) if isinstance(c, dict) else c for c in data.get("columns", [])]
    foreign_keys = [_construct_foreign_key(fk) if isinstance(fk, dict) else fk for fk in data.get("foreign_keys", [])]
    return TableMeta.model_construct(
        name=data.get("name", ""),
        comment=data.get("comment"),
        columns=columns,
        primary_keys=list(data.get("primary_keys", [])),
        foreign_keys=foreign_keys,
        created_at=data.get("created_at"),
        last_ddl_time=data.get("last_ddl_time"),
        last_modified_by=data.get("last_modified_by"),
    )


def _construct_view(data: dict[str, Any]) -> ViewMeta:
    columns = [_construct_column(c) if isinstance(c, dict) else c for c in data.get("columns", [])]
    return ViewMeta.model_construct(
        name=data.get("name", ""),
        text=data.get("text"),
        comment=data.get("comment"),
        columns=columns,
        created_at=data.get("created_at"),
        last_ddl_time=data.get("last_ddl_time"),
        last_modified_by=data.get("last_modified_by"),
    )


def _construct_mview(data: dict[str, Any]) -> MaterializedViewMeta:
    columns = [_construct_column(c) if isinstance(c, dict) else c for c in data.get("columns", [])]
    return MaterializedViewMeta.model_construct(
        name=data.get("name", ""),
        query=data.get("query"),
        refresh_mode=data.get("refresh_mode"),
        refresh_type=data.get("refresh_type"),
        updatable=bool(data.get("updatable", False)),
        comment=data.get("comment"),
        columns=columns,
        created_at=data.get("created_at"),
        last_ddl_time=data.get("last_ddl_time"),
        last_modified_by=data.get("last_modified_by"),
    )


def _construct_subprogram(data: dict[str, Any]) -> SubprogramMeta:
    return SubprogramMeta.model_construct(
        package_name=data.get("package_name", ""),
        name=data.get("name", ""),
        subprogram_type=data.get("subprogram_type", ""),
        source=data.get("source"),
        comment=data.get("comment"),
        created_at=data.get("created_at"),
        last_ddl_time=data.get("last_ddl_time"),
        last_modified_by=data.get("last_modified_by"),
    )


def _construct_code_object(data: dict[str, Any]) -> CodeObjectMeta:
    subprograms = [_construct_subprogram(sp) if isinstance(sp, dict) else sp for sp in data.get("subprograms", [])]
    return CodeObjectMeta.model_construct(
        name=data.get("name", ""),
        object_type=data.get("object_type", ""),
        source=data.get("source"),
        comment=data.get("comment"),
        subprograms=subprograms,
        created_at=data.get("created_at"),
        last_ddl_time=data.get("last_ddl_time"),
        last_modified_by=data.get("last_modified_by"),
    )


def _construct_trigger(data: dict[str, Any]) -> TriggerMeta:
    return TriggerMeta.model_construct(
        name=data.get("name", ""),
        table_name=data.get("table_name"),
        trigger_type=data.get("trigger_type"),
        triggering_event=data.get("triggering_event"),
        status=data.get("status"),
        trigger_body=data.get("trigger_body"),
        created_at=data.get("created_at"),
        last_ddl_time=data.get("last_ddl_time"),
        last_modified_by=data.get("last_modified_by"),
    )


def _construct_sequence(data: dict[str, Any]) -> SequenceMeta:
    return SequenceMeta.model_construct(
        name=data.get("name", ""),
        min_value=data.get("min_value"),
        max_value=data.get("max_value"),
        increment_by=data.get("increment_by"),
        last_number=data.get("last_number"),
        created_at=data.get("created_at"),
        last_ddl_time=data.get("last_ddl_time"),
        last_modified_by=data.get("last_modified_by"),
    )


def _construct_index(data: dict[str, Any]) -> IndexMeta:
    return IndexMeta.model_construct(
        name=data.get("name", ""),
        table_name=data.get("table_name", ""),
        uniqueness=data.get("uniqueness", "NONUNIQUE"),
        columns=list(data.get("columns", [])),
        created_at=data.get("created_at"),
        last_ddl_time=data.get("last_ddl_time"),
        last_modified_by=data.get("last_modified_by"),
    )


def _construct_synonym(data: dict[str, Any]) -> SynonymMeta:
    return SynonymMeta.model_construct(
        name=data.get("name", ""),
        table_owner=data.get("table_owner"),
        table_name=data.get("table_name"),
        db_link=data.get("db_link"),
        created_at=data.get("created_at"),
        last_ddl_time=data.get("last_ddl_time"),
        last_modified_by=data.get("last_modified_by"),
    )


def _construct_schema_metadata(data: dict[str, Any], schema_name: str = "") -> SchemaMetadata:
    return SchemaMetadata.model_construct(
        schema_name=schema_name,
        tables=[_construct_table(t) if isinstance(t, dict) else t for t in data.get("tables", [])],
        views=[_construct_view(v) if isinstance(v, dict) else v for v in data.get("views", [])],
        mviews=[_construct_mview(mv) if isinstance(mv, dict) else mv for mv in data.get("mviews", [])],
        code_objects=[_construct_code_object(co) if isinstance(co, dict) else co for co in data.get("code_objects", [])],
        triggers=[_construct_trigger(trg) if isinstance(trg, dict) else trg for trg in data.get("triggers", [])],
        sequences=[_construct_sequence(s) if isinstance(s, dict) else s for s in data.get("sequences", [])],
        indexes=[_construct_index(idx) if isinstance(idx, dict) else idx for idx in data.get("indexes", [])],
        synonyms=[_construct_synonym(syn) if isinstance(syn, dict) else syn for syn in data.get("synonyms", [])],
    )


def save_raw_schema(
    schema: SchemaMetadata,
    raw_path: Path,
    multi_schema: bool = False,
    storage: Any = None,
    local_cache: bool = True,
    force_upload: bool = False,
) -> list[Path]:
    saved_files: list[Path] = []

    if local_cache:
        target_path = (raw_path / schema.schema_name) if (multi_schema and schema.schema_name) else raw_path
        target_path.mkdir(parents=True, exist_ok=True)

        def _write_json(file_path: Path, data: dict) -> Path:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            return file_path

        # 1. Tables
        for table in schema.tables:
            p = target_path / "tables" / f"{table.name}.json"
            saved_files.append(_write_json(p, table.model_dump()))

        # 2. Views
        for view in schema.views:
            p = target_path / "views" / f"{view.name}.json"
            saved_files.append(_write_json(p, view.model_dump()))

        # 3. Materialized Views
        for mview in schema.mviews:
            p = target_path / "mviews" / f"{mview.name}.json"
            saved_files.append(_write_json(p, mview.model_dump()))

        # 4. Code Objects
        for code_obj in schema.code_objects:
            obj_folder = code_obj.object_type.lower().replace(" ", "_") + "s"
            p = target_path / obj_folder / f"{code_obj.name}.json"
            saved_files.append(_write_json(p, code_obj.model_dump()))

        # 5. Triggers
        for trigger in schema.triggers:
            p = target_path / "triggers" / f"{trigger.name}.json"
            saved_files.append(_write_json(p, trigger.model_dump()))

        # 6. Sequences
        for sequence in schema.sequences:
            p = target_path / "sequences" / f"{sequence.name}.json"
            saved_files.append(_write_json(p, sequence.model_dump()))

        # 7. Indexes
        for index in schema.indexes:
            p = target_path / "indexes" / f"{index.name}.json"
            saved_files.append(_write_json(p, index.model_dump()))

        # 8. Synonyms
        for synonym in schema.synonyms:
            p = target_path / "synonyms" / f"{synonym.name}.json"
            saved_files.append(_write_json(p, synonym.model_dump()))

        # 9. Consolidated Schema Snapshot (written for fast TUI/CLI startup cache)
        snapshot_path = target_path / "_schema.json"
        _write_json(snapshot_path, schema.model_dump())

    if storage is not None:
        try:
            storage.save_raw_schema(schema, multi_schema=multi_schema, force=force_upload)
        except Exception as exc:
            import sys

            print(f"Warning: Failed to upload schema to SeaweedFS: {exc}", file=sys.stderr)

    return saved_files


def _is_snapshot_fresh(snapshot_file: Path, raw_path: Path) -> bool:
    """Checks if _schema.json exists and its mtime is newer than or equal to all granular subdirectories and files."""
    if not snapshot_file.exists():
        return False
    try:
        snapshot_mtime = snapshot_file.stat().st_mtime
        subfolders = [
            "tables",
            "views",
            "mviews",
            "procedures",
            "functions",
            "packages",
            "package_bodys",
            "types",
            "type_bodys",
            "triggers",
            "sequences",
            "indexes",
            "synonyms",
        ]
        for sub in subfolders:
            sub_dir = raw_path / sub
            if sub_dir.exists():
                if sub_dir.stat().st_mtime > snapshot_mtime:
                    return False
                for entry in sub_dir.iterdir():
                    if entry.is_file() and entry.suffix == ".json" and entry.stat().st_mtime > snapshot_mtime:
                        return False
        return True
    except Exception:
        return False


def load_raw_schema(raw_path: Path, schema_name: str = "") -> SchemaMetadata:
    if not raw_path.exists():
        return SchemaMetadata(schema_name=schema_name)

    snapshot_file = raw_path / "_schema.json"
    if _is_snapshot_fresh(snapshot_file, raw_path):
        try:
            raw_data = json.loads(snapshot_file.read_text(encoding="utf-8"))
            return _construct_schema_metadata(raw_data, schema_name=schema_name)
        except Exception:
            pass

    schema = SchemaMetadata(schema_name=schema_name)

    # 1. Tables
    tables_dir = raw_path / "tables"
    if tables_dir.exists():
        for p in sorted(tables_dir.glob("*.json")):
            try:
                raw_data = json.loads(p.read_text(encoding="utf-8"))
                schema.tables.append(_construct_table(raw_data))
            except Exception:
                pass

    # 2. Views
    views_dir = raw_path / "views"
    if views_dir.exists():
        for p in sorted(views_dir.glob("*.json")):
            try:
                raw_data = json.loads(p.read_text(encoding="utf-8"))
                schema.views.append(_construct_view(raw_data))
            except Exception:
                pass

    # 3. Materialized Views
    mviews_dir = raw_path / "mviews"
    if mviews_dir.exists():
        for p in sorted(mviews_dir.glob("*.json")):
            try:
                raw_data = json.loads(p.read_text(encoding="utf-8"))
                schema.mviews.append(_construct_mview(raw_data))
            except Exception:
                pass

    # 4. Code Objects
    for folder_name in ["procedures", "functions", "packages", "package_bodys", "types", "type_bodys"]:
        code_dir = raw_path / folder_name
        if code_dir.exists():
            for p in sorted(code_dir.glob("*.json")):
                try:
                    raw_data = json.loads(p.read_text(encoding="utf-8"))
                    schema.code_objects.append(_construct_code_object(raw_data))
                except Exception:
                    pass

    # 5. Triggers
    trig_dir = raw_path / "triggers"
    if trig_dir.exists():
        for p in sorted(trig_dir.glob("*.json")):
            try:
                raw_data = json.loads(p.read_text(encoding="utf-8"))
                schema.triggers.append(_construct_trigger(raw_data))
            except Exception:
                pass

    # 6. Sequences
    seq_dir = raw_path / "sequences"
    if seq_dir.exists():
        for p in sorted(seq_dir.glob("*.json")):
            try:
                raw_data = json.loads(p.read_text(encoding="utf-8"))
                schema.sequences.append(_construct_sequence(raw_data))
            except Exception:
                pass

    # 7. Indexes
    idx_dir = raw_path / "indexes"
    if idx_dir.exists():
        for p in sorted(idx_dir.glob("*.json")):
            try:
                raw_data = json.loads(p.read_text(encoding="utf-8"))
                schema.indexes.append(_construct_index(raw_data))
            except Exception:
                pass

    # 8. Synonyms
    syn_dir = raw_path / "synonyms"
    if syn_dir.exists():
        for p in sorted(syn_dir.glob("*.json")):
            try:
                raw_data = json.loads(p.read_text(encoding="utf-8"))
                schema.synonyms.append(_construct_synonym(raw_data))
            except Exception:
                pass

    # Automatically persist / refresh snapshot cache if any object was loaded
    has_objects = bool(
        schema.tables
        or schema.views
        or schema.mviews
        or schema.code_objects
        or schema.triggers
        or schema.sequences
        or schema.indexes
        or schema.synonyms
    )
    if has_objects:
        try:
            snapshot_file.write_text(
                json.dumps(schema.model_dump(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass

    return schema


def load_raw_schemas(
    raw_path: Path,
    target_schemas: list[str] | None = None,
    storage: Any = None,
    local_cache: bool = True,
) -> list[SchemaMetadata]:
    if storage is not None:
        try:
            remote_schemas = storage.load_raw_schemas(target_schemas=target_schemas)
            if remote_schemas:
                if local_cache:
                    for schema_name, meta in remote_schemas.items():
                        # Populate local cache without re-uploading to storage
                        save_raw_schema(meta, raw_path, multi_schema=True)
                return list(remote_schemas.values())
        except Exception as exc:
            import sys

            print(f"Warning: Failed to load schemas from SeaweedFS: {exc}. Falling back to local disk.", file=sys.stderr)

    if not raw_path.exists():
        return []

    # Check if raw_path contains subdirectories representing multiple schemas
    subdirs = [
        d
        for d in raw_path.iterdir()
        if d.is_dir()
        and d.name
        not in {
            "tables",
            "views",
            "mviews",
            "procedures",
            "functions",
            "packages",
            "package_bodys",
            "types",
            "type_bodys",
            "triggers",
            "sequences",
            "indexes",
            "synonyms",
            "chunks",
        }
    ]

    if subdirs:
        schemas: list[SchemaMetadata] = []
        target_set = {s.upper() for s in target_schemas} if target_schemas else None
        for d in sorted(subdirs, key=lambda x: x.name):
            if target_set and d.name.upper() not in target_set:
                continue
            schemas.append(load_raw_schema(d, schema_name=d.name))
        return schemas

    return [load_raw_schema(raw_path)]


ORACLE_RESERVED_WORDS = {
    "ACCESS",
    "ADD",
    "ALL",
    "ALTER",
    "AND",
    "ANY",
    "AS",
    "ASC",
    "AUDIT",
    "BETWEEN",
    "BY",
    "CHAR",
    "CHECK",
    "CLUSTER",
    "COLUMN",
    "COMMENT",
    "COMPRESS",
    "CONNECT",
    "CREATE",
    "CURRENT",
    "DATE",
    "DECIMAL",
    "DEFAULT",
    "DELETE",
    "DESC",
    "DISTINCT",
    "DROP",
    "ELSE",
    "EXCLUSIVE",
    "EXISTS",
    "FILE",
    "FLOAT",
    "FOR",
    "FROM",
    "GRANT",
    "GROUP",
    "HAVING",
    "IDENTIFIED",
    "IMMEDIATE",
    "IN",
    "INCREMENT",
    "INDEX",
    "INITIAL",
    "INSERT",
    "INTEGER",
    "INTERSECT",
    "INTO",
    "IS",
    "LEVEL",
    "LIKE",
    "LOCK",
    "LONG",
    "MAXEXTENTS",
    "MINUS",
    "MLSLABEL",
    "MODE",
    "MODIFY",
    "NOAUDIT",
    "NOCOMPRESS",
    "NOT",
    "NOWAIT",
    "NULL",
    "NUMBER",
    "OF",
    "OFFLINE",
    "ON",
    "ONLINE",
    "OPTION",
    "OR",
    "ORDER",
    "PCTFREE",
    "PRIOR",
    "PRIVILEGES",
    "PUBLIC",
    "RAW",
    "RENAME",
    "RESOURCE",
    "REVOKE",
    "ROW",
    "ROWID",
    "ROWNUM",
    "ROWS",
    "SELECT",
    "SESSION",
    "SET",
    "SHARE",
    "SIZE",
    "SMALLINT",
    "START",
    "SUCCESSFUL",
    "SYNONYM",
    "SYSDATE",
    "TABLE",
    "THEN",
    "TO",
    "TRIGGER",
    "UID",
    "UNION",
    "UNIQUE",
    "UPDATE",
    "USER",
    "VALIDATE",
    "VALUES",
    "VARCHAR",
    "VARCHAR2",
    "VIEW",
    "WHENEVER",
    "WHERE",
    "WITH",
    # PL/SQL specific keywords
    "BEGIN",
    "BODY",
    "BULK",
    "CALL",
    "CASE",
    "CLOSE",
    "COLLECT",
    "COMMIT",
    "CONSTANT",
    "CONTINUE",
    "COUNT",
    "CURSOR",
    "DECLARE",
    "DO",
    "ELSIF",
    "END",
    "EXCEPTION",
    "EXECUTE",
    "EXIT",
    "EXTEND",
    "FALSE",
    "FETCH",
    "FIRST",
    "FORALL",
    "FUNCTION",
    "GOTO",
    "IF",
    "INDEXBY",
    "LAST",
    "LIMIT",
    "LOOP",
    "NEXT",
    "OPEN",
    "OTHERS",
    "OUT",
    "PACKAGE",
    "PARTITION",
    "PRAGMA",
    "PROCEDURE",
    "RAISE",
    "RANGE",
    "RECORD",
    "REF",
    "RETURN",
    "RETURNING",
    "REVERSE",
    "ROLLBACK",
    "ROWTYPE",
    "SAVEPOINT",
    "SUBTYPE",
    "TRUNC",
    "TYPE",
    "TRUE",
    "WHEN",
    "WHILE",
    "MAX",
    "MIN",
    "SUM",
    "AVG",
    "NVL",
    "TO_CHAR",
    "TO_DATE",
    "TO_NUMBER",
    "UPPER",
    "LOWER",
    "SUBSTR",
    "INSTR",
}


def strip_comments_and_hints(code: str) -> str:
    """Removes block comments, hints (/*+ ... */), and line comments (-- ...) to isolate pure SQL/PLSQL code."""
    if not code:
        return ""
    c1 = re.sub(r"/\*.*?\*/", " ", code, flags=re.DOTALL)
    c2 = re.sub(r"--.*$", " ", c1, flags=re.MULTILINE)
    return c2


def extract_code_semantic_comments(code: str) -> tuple[list[str], list[str]]:
    """Extracts meaningful business rules, engineering explanations, and task tickets from code comments."""
    if not code:
        return [], []

    tasks: list[str] = []
    task_seen: set[str] = set()
    task_pattern = re.compile(r"\b((?:TAREFA|TASK|CHAMADO|BUG|JIRA|ISSUE|DEMANDA|CARD)[-:\s#]*[A-Za-z0-9_-]+)\b", re.IGNORECASE)

    for match in task_pattern.finditer(code):
        full_match = match.group(1).strip()
        canonical = full_match.upper()
        if canonical not in task_seen:
            task_seen.add(canonical)
            tasks.append(full_match)

    notes: list[str] = []
    lines = code.splitlines()
    current_block: list[str] = []

    for line in lines:
        stripped = line.strip()
        comment_text = None
        if "--" in stripped:
            idx = stripped.find("--")
            comment_text = stripped[idx + 2 :].strip()

        if comment_text:
            clean_comm = re.sub(r"^[-=*#/_\s]+|[-=*#/_\s]+$", "", comment_text).strip()
            if len(clean_comm) > 3 and not re.fullmatch(
                r"(?:TAREFA|TASK|CHAMADO|BUG|JIRA|ISSUE|DEMANDA|CARD)[-:\s#]*[A-Za-z0-9_-]+", clean_comm, re.IGNORECASE
            ):
                current_block.append(clean_comm)
            else:
                if current_block:
                    notes.append(" ".join(current_block))
                    current_block = []
        else:
            if current_block:
                notes.append(" ".join(current_block))
                current_block = []

    if current_block:
        notes.append(" ".join(current_block))

    unique_notes: list[str] = []
    seen_notes: set[str] = set()
    for n in notes:
        n_clean = n.strip()
        if n_clean and n_clean.lower() not in seen_notes:
            seen_notes.add(n_clean.lower())
            unique_notes.append(n_clean)

    return unique_notes, tasks


class RawDependencyIndex:
    """Pre-computed inverted index of database objects and dependencies for O(1) fast lookups."""

    def __init__(self, schemas: list[SchemaMetadata]) -> None:
        self.schemas = schemas
        self.raw_objects: dict[str, tuple[str, Any]] = {}
        self.incoming_fks: dict[str, list[tuple[str, ForeignKeyMeta]]] = defaultdict(list)
        self.table_triggers: dict[str, list[TriggerMeta]] = defaultdict(list)
        self.synonyms_by_target: dict[str, list[SynonymMeta]] = defaultdict(list)
        self.text_references: dict[str, list[tuple[str, str, str, str]]] = defaultdict(list)

        self.tables_map: dict[str, TableMeta] = {}
        self.views_map: dict[str, ViewMeta] = {}
        self.mviews_map: dict[str, MaterializedViewMeta] = {}
        self.code_map: dict[str, CodeObjectMeta] = {}
        self.triggers_map: dict[str, TriggerMeta] = {}
        self.synonyms_map: dict[str, SynonymMeta] = {}
        self.sequences_map: dict[str, SequenceMeta] = {}
        self.indexes_map: dict[str, IndexMeta] = {}
        self.packages_set: set[str] = set()
        self.subprograms_map: dict[str, SubprogramMeta] = {}

        token_pattern = re.compile(r"\b[A-Za-z0-9_#$]+\b")

        for s in schemas:
            s_name = (s.schema_name or "DEFAULT").upper()
            for t in s.tables:
                t_up = t.name.upper()
                self.raw_objects[t_up] = ("TABLE", t)
                self.raw_objects[f"{s_name}.{t_up}"] = ("TABLE", t)
                self.tables_map[t_up] = t
                self.tables_map[f"{s_name}.{t_up}"] = t
                for fk in t.foreign_keys:
                    if fk.referenced_table:
                        self.incoming_fks[fk.referenced_table.upper()].append((t_up, fk))

            for v in s.views:
                v_up = v.name.upper()
                self.raw_objects[v_up] = ("VIEW", v)
                self.raw_objects[f"{s_name}.{v_up}"] = ("VIEW", v)
                self.views_map[v_up] = v
                self.views_map[f"{s_name}.{v_up}"] = v

            for mv in s.mviews:
                mv_up = mv.name.upper()
                self.raw_objects[mv_up] = ("MATERIALIZED VIEW", mv)
                self.raw_objects[f"{s_name}.{mv_up}"] = ("MATERIALIZED VIEW", mv)
                self.mviews_map[mv_up] = mv
                self.mviews_map[f"{s_name}.{mv_up}"] = mv

            for co in s.code_objects:
                co_up = co.name.upper()
                self.raw_objects[co_up] = (co.object_type.upper(), co)
                self.raw_objects[f"{s_name}.{co_up}"] = (co.object_type.upper(), co)
                self.code_map[co_up] = co
                self.code_map[f"{s_name}.{co_up}"] = co
                if co.object_type.upper() in ("PACKAGE", "PACKAGE BODY"):
                    self.packages_set.add(co_up)
                    self.packages_set.add(f"{s_name}.{co_up}")
                    for sub in co.subprograms:
                        sub_full = f"{co_up}.{sub.name.upper()}"
                        self.subprograms_map[sub_full] = sub
                        self.subprograms_map[f"{s_name}.{sub_full}"] = sub

            for trg in s.triggers:
                trg_up = trg.name.upper()
                self.raw_objects[trg_up] = ("TRIGGER", trg)
                self.raw_objects[f"{s_name}.{trg_up}"] = ("TRIGGER", trg)
                self.triggers_map[trg_up] = trg
                self.triggers_map[f"{s_name}.{trg_up}"] = trg
                if trg.table_name:
                    self.table_triggers[trg.table_name.upper()].append(trg)

            for seq in s.sequences:
                seq_up = seq.name.upper()
                self.raw_objects[seq_up] = ("SEQUENCE", seq)
                self.raw_objects[f"{s_name}.{seq_up}"] = ("SEQUENCE", seq)
                self.sequences_map[seq_up] = seq
                self.sequences_map[f"{s_name}.{seq_up}"] = seq

            for idx in s.indexes:
                idx_up = idx.name.upper()
                self.raw_objects[idx_up] = ("INDEX", idx)
                self.raw_objects[f"{s_name}.{idx_up}"] = ("INDEX", idx)
                self.indexes_map[idx_up] = idx
                self.indexes_map[f"{s_name}.{idx_up}"] = idx

            for syn in s.synonyms:
                syn_up = syn.name.upper()
                # Do not overwrite real tables/views/packages with a synonym of the same name
                if syn_up not in self.raw_objects or self.raw_objects[syn_up][0] == "SYNONYM":
                    self.raw_objects[syn_up] = ("SYNONYM", syn)
                self.raw_objects[f"{s_name}.{syn_up}"] = ("SYNONYM", syn)
                self.synonyms_map[syn_up] = syn
                self.synonyms_map[f"{s_name}.{syn_up}"] = syn
                if syn.table_name:
                    self.synonyms_by_target[syn.table_name.upper()].append(syn)
                    if (syn.table_name or "").upper() in self.packages_set:
                        self.packages_set.add(syn_up)

        all_names = set(self.raw_objects.keys()) - ORACLE_RESERVED_WORDS
        self.all_names = all_names

        for s in schemas:
            for v in s.views:
                if v.text:
                    clean_code = strip_comments_and_hints(v.text)
                    words = {w.upper() for w in token_pattern.findall(clean_code)} - ORACLE_RESERVED_WORDS
                    v_name = v.name.upper()
                    for w in words & all_names:
                        if w != v_name:
                            self.text_references[w].append((v_name, "VIEW", "READS/SELECTS", "View executes SQL query against object"))

            for mv in s.mviews:
                if mv.query:
                    clean_code = strip_comments_and_hints(mv.query)
                    words = {w.upper() for w in token_pattern.findall(clean_code)} - ORACLE_RESERVED_WORDS
                    mv_name = mv.name.upper()
                    for w in words & all_names:
                        if w != mv_name:
                            self.text_references[w].append(
                                (mv_name, "MATERIALIZED VIEW", "READS/SELECTS", "Materialized View based on object")
                            )

            for co in s.code_objects:
                if co.source:
                    clean_code = strip_comments_and_hints(co.source)
                    words = {w.upper() for w in token_pattern.findall(clean_code)} - ORACLE_RESERVED_WORDS
                    co_name = co.name.upper()
                    for w in words & all_names:
                        if w != co_name:
                            self.text_references[w].append(
                                (
                                    co_name,
                                    co.object_type.upper(),
                                    "PLSQL_DEPENDENCY",
                                    f"Object {co.object_type} references {w} in source code",
                                )
                            )

            for trg in s.triggers:
                if trg.trigger_body:
                    clean_code = strip_comments_and_hints(trg.trigger_body)
                    words = {w.upper() for w in token_pattern.findall(clean_code)} - ORACLE_RESERVED_WORDS
                    trg_name = trg.name.upper()
                    for w in words & all_names:
                        if w != trg_name and w != (trg.table_name or "").upper():
                            self.text_references[w].append(
                                (trg_name, "TRIGGER", "PLSQL_DEPENDENCY", f"Trigger {trg.name} references {w} in trigger body")
                            )


def _find_raw_object(schemas: list[SchemaMetadata], name: str):
    name_upper = name.upper()
    for s in schemas:
        for t in s.tables:
            if t.name.upper() == name_upper:
                return "TABLE", t
        for v in s.views:
            if v.name.upper() == name_upper:
                return "VIEW", v
        for mv in s.mviews:
            if mv.name.upper() == name_upper:
                return "MATERIALIZED VIEW", mv
        for co in s.code_objects:
            if co.name.upper() == name_upper:
                return co.object_type.upper(), co
        for trg in s.triggers:
            if trg.name.upper() == name_upper:
                return "TRIGGER", trg
        for syn in s.synonyms:
            if syn.name.upper() == name_upper:
                return "SYNONYM", syn
    return "UNKNOWN", None


def trace_raw_dependencies(
    schemas: list[SchemaMetadata],
    target_object_name: str,
    max_depth: int = 1,
    index: RawDependencyIndex | None = None,
    expected_type: str | None = None,
    schema_name: str | None = None,
) -> ObjectTraceResult:
    try:
        max_depth = int(getattr(max_depth, "default", max_depth))
    except Exception:
        max_depth = 1

    idx = index or RawDependencyIndex(schemas)
    target_upper = target_object_name.strip().upper()

    focal_type = "UNKNOWN"
    focal_obj = None

    if schema_name:
        qualified_key = f"{schema_name.strip().upper()}.{target_upper}"
        if qualified_key in idx.raw_objects:
            focal_type, focal_obj = idx.raw_objects[qualified_key]

    if (not focal_obj or focal_type == "UNKNOWN") and expected_type:
        exp_up = expected_type.strip().upper()
        if exp_up in ("TABLE", "TABLES") and target_upper in idx.tables_map:
            focal_type, focal_obj = "TABLE", idx.tables_map[target_upper]
        elif exp_up in ("VIEW", "VIEWS") and target_upper in idx.views_map:
            focal_type, focal_obj = "VIEW", idx.views_map[target_upper]
        elif exp_up in ("MVIEW", "MVIEWS", "MATERIALIZED VIEW", "MATERIALIZED VIEWS") and target_upper in idx.mviews_map:
            focal_type, focal_obj = "MATERIALIZED VIEW", idx.mviews_map[target_upper]
        elif exp_up in ("PACKAGE", "PACKAGE BODY", "PROCEDURE", "FUNCTION", "TYPE", "TYPE BODY") and target_upper in idx.code_map:
            focal_type, focal_obj = idx.code_map[target_upper].object_type.upper(), idx.code_map[target_upper]
        elif exp_up in ("TRIGGER", "TRIGGERS") and target_upper in idx.triggers_map:
            focal_type, focal_obj = "TRIGGER", idx.triggers_map[target_upper]
        elif exp_up in ("SYNONYM", "SYNONYMS") and target_upper in idx.synonyms_map:
            focal_type, focal_obj = "SYNONYM", idx.synonyms_map[target_upper]

    if not focal_obj or focal_type == "UNKNOWN":
        focal_type, focal_obj = idx.raw_objects.get(target_upper, ("UNKNOWN", None))

    notes: list[str] = []
    tasks: list[str] = []
    source_to_scan = (
        getattr(focal_obj, "source", None)
        or getattr(focal_obj, "trigger_body", None)
        or getattr(focal_obj, "text", None)
        or getattr(focal_obj, "query", None)
    )
    if source_to_scan:
        notes, tasks = extract_code_semantic_comments(source_to_scan)

    result = ObjectTraceResult(
        focal_name=target_upper,
        focal_type=focal_type,
        focal_object=focal_obj,
        extracted_notes=notes,
        extracted_tasks=tasks,
    )

    all_related_names = set()
    visited_nodes = {target_upper}
    seen_links = set()
    current_layer = {target_upper}

    # If initial object is a Synonym, resolve to the actual target
    if focal_type == "SYNONYM" and focal_obj and getattr(focal_obj, "table_name", None):
        real_target = focal_obj.table_name.upper()
        if real_target != target_upper and real_target not in ORACLE_RESERVED_WORDS:
            details_str = f"Synonym points to {focal_obj.table_owner or ''}.{focal_obj.table_name}"
            if focal_obj.db_link:
                details_str += f"@{focal_obj.db_link}"
            result.dependencies.append(
                DependencyLink(
                    source_name=target_upper,
                    source_type="SYNONYM",
                    target_name=real_target,
                    target_type="TARGET",
                    relation_type="SYNONYM_FOR",
                    details=details_str,
                    depth=1,
                )
            )
            visited_nodes.add(real_target)
            current_layer.add(real_target)
            all_related_names.add(real_target)

    for current_depth in range(1, max(1, max_depth) + 1):
        if not current_layer:
            break
        next_layer = set()

        for curr_name in current_layer:
            curr_type, curr_obj = idx.raw_objects.get(curr_name, ("UNKNOWN", None))

            # 0) Synonyms pointing to current object
            for syn in idx.synonyms_by_target.get(curr_name, []):
                syn_name = syn.name.upper()
                if syn_name == curr_name or syn_name in ORACLE_RESERVED_WORDS:
                    continue
                link_key = ("SYNONYM", syn_name, curr_name)
                if link_key not in seen_links:
                    seen_links.add(link_key)
                    result.dependencies.append(
                        DependencyLink(
                            source_name=syn_name,
                            source_type="SYNONYM",
                            target_name=curr_name,
                            target_type=curr_type,
                            relation_type="SYNONYM_FOR",
                            details=f"Synonym {syn_name} points to {curr_name}",
                            depth=current_depth,
                        )
                    )
                if syn_name not in visited_nodes:
                    visited_nodes.add(syn_name)
                    next_layer.add(syn_name)
                    all_related_names.add(syn_name)

            # A) Outgoing Foreign Keys (if curr_obj is a Table)
            if isinstance(curr_obj, TableMeta):
                for fk in curr_obj.foreign_keys:
                    if fk.referenced_table:
                        ref_tbl = fk.referenced_table.upper()
                        if ref_tbl == curr_name or ref_tbl in ORACLE_RESERVED_WORDS:
                            continue
                        link_key = ("FK", curr_name, ref_tbl, (fk.column or "").upper())
                        if link_key not in seen_links:
                            seen_links.add(link_key)
                            result.dependencies.append(
                                DependencyLink(
                                    source_name=curr_name,
                                    source_type="TABLE",
                                    target_name=ref_tbl,
                                    target_type="TABLE",
                                    relation_type="FK_REFERENCES",
                                    details=f"Column {fk.column} -> {ref_tbl}.{fk.referenced_column} ({fk.name})",
                                    depth=current_depth,
                                )
                            )
                        if ref_tbl not in visited_nodes:
                            visited_nodes.add(ref_tbl)
                            next_layer.add(ref_tbl)
                            all_related_names.add(ref_tbl)

            # B) Incoming Foreign Keys
            for child_name, fk in idx.incoming_fks.get(curr_name, []):
                if child_name == curr_name or child_name in ORACLE_RESERVED_WORDS:
                    continue
                fk_key = ("FK", child_name, curr_name, (fk.column or "").upper())
                if fk_key not in seen_links:
                    seen_links.add(fk_key)
                    result.dependencies.append(
                        DependencyLink(
                            source_name=child_name,
                            source_type="TABLE",
                            target_name=curr_name,
                            target_type=curr_type,
                            relation_type="FK_REFERENCED_BY",
                            details=f"Child table {child_name}.{fk.column} references {curr_name}.{fk.referenced_column}",
                            depth=current_depth,
                        )
                    )
                if child_name not in visited_nodes:
                    visited_nodes.add(child_name)
                    next_layer.add(child_name)
                    all_related_names.add(child_name)

            # C) Attached Triggers
            for trg in idx.table_triggers.get(curr_name, []):
                trg_name = trg.name.upper()
                if trg_name == curr_name or trg_name in ORACLE_RESERVED_WORDS:
                    continue
                link_key = (trg_name, curr_name, "TRIGGER_ON")
                if link_key not in seen_links:
                    seen_links.add(link_key)
                    result.dependencies.append(
                        DependencyLink(
                            source_name=trg_name,
                            source_type="TRIGGER",
                            target_name=curr_name,
                            target_type=curr_type,
                            relation_type="TRIGGER_ON",
                            details=f"Trigger {trg.trigger_type} {trg.triggering_event}",
                            depth=current_depth,
                        )
                    )
                if trg_name not in visited_nodes:
                    visited_nodes.add(trg_name)
                    next_layer.add(trg_name)
                    all_related_names.add(trg_name)

            # D, E, F) Text References (Views, MViews, Code Objects, Triggers)
            for ref_name, ref_type, rel_type, details in idx.text_references.get(curr_name, []):
                if ref_name == curr_name or ref_name in ORACLE_RESERVED_WORDS:
                    continue
                link_key = (ref_name, curr_name, rel_type)
                if link_key not in seen_links:
                    seen_links.add(link_key)
                    result.dependencies.append(
                        DependencyLink(
                            source_name=ref_name,
                            source_type=ref_type,
                            target_name=curr_name,
                            target_type=curr_type,
                            relation_type=rel_type,
                            details=details,
                            depth=current_depth,
                        )
                    )
                if ref_name not in visited_nodes:
                    visited_nodes.add(ref_name)
                    next_layer.add(ref_name)
                    all_related_names.add(ref_name)

        current_layer = next_layer

    # Attach metadata of related objects in O(1) lookups
    for name in all_related_names:
        if name == target_upper:
            continue
        if name in idx.tables_map:
            result.related_tables.append(idx.tables_map[name])
        if name in idx.views_map:
            result.related_views.append(idx.views_map[name])
        if name in idx.code_map:
            result.related_code_objects.append(idx.code_map[name])
        if name in idx.triggers_map:
            result.related_triggers.append(idx.triggers_map[name])

    return result


QUALIFIED_CALL_PATTERN = re.compile(r"\b([A-Za-z0-9_#$]+)\.([A-Za-z0-9_#$]+)\b")


def trace_subprogram_dependencies(
    schemas: list[SchemaMetadata],
    sub: SubprogramMeta,
    index: RawDependencyIndex | None = None,
) -> ObjectTraceResult:
    idx = index or RawDependencyIndex(schemas)
    focal_name = f"{sub.package_name}.{sub.name}".upper()
    focal_type = sub.subprogram_type.upper()

    notes, tasks = extract_code_semantic_comments(sub.source or "")

    result = ObjectTraceResult(
        focal_name=focal_name,
        focal_type=focal_type,
        focal_object=sub,
        extracted_notes=notes,
        extracted_tasks=tasks,
    )

    token_pattern = re.compile(r"\b[A-Za-z0-9_#$]+\b")
    all_related_names = set()
    seen_links = set()
    resolved_packages = set()

    # 1. Outgoing dependencies from sub.source (without comments/hints)
    if sub.source:
        clean_code = strip_comments_and_hints(sub.source)
        pkg_upper = (sub.package_name or "").upper()

        # A) Extract qualified member calls: PACKAGE.ROUTINE
        for prefix, member in QUALIFIED_CALL_PATTERN.findall(clean_code):
            p_up = prefix.upper()
            m_up = member.upper()
            if m_up in ORACLE_RESERVED_WORDS:
                continue

            is_pkg = (
                p_up in idx.packages_set
                or p_up in idx.synonyms_map
                or p_up == pkg_upper
                or (p_up in idx.code_map and idx.code_map[p_up].object_type.upper() in ("PACKAGE", "PACKAGE BODY"))
            )

            if is_pkg:
                call_name = f"{p_up}.{m_up}"
                if call_name != focal_name:
                    link_key = (focal_name, call_name, "EXECUTES/CALLS")
                    if link_key not in seen_links:
                        seen_links.add(link_key)
                        result.dependencies.append(
                            DependencyLink(
                                source_name=focal_name,
                                source_type=focal_type,
                                target_name=call_name,
                                target_type="SUBPROGRAM",
                                relation_type="EXECUTES/CALLS",
                                details=f"Routine invokes {call_name}",
                                depth=1,
                            )
                        )
                        resolved_packages.add(p_up)

        # B) Extract standalone identifiers (tables, views, standalone procedures, remaining packages)
        words = {w.upper() for w in token_pattern.findall(clean_code)} - ORACLE_RESERVED_WORDS
        for w in words & idx.all_names:
            if w == pkg_upper or w == sub.name.upper() or w in ORACLE_RESERVED_WORDS or w in resolved_packages:
                continue
            target_type, target_obj = idx.raw_objects.get(w, ("UNKNOWN", None))

            if target_type == "SYNONYM" and target_obj and getattr(target_obj, "table_name", None):
                syn_target = (target_obj.table_name or "").upper()
                if syn_target in idx.tables_map or syn_target in idx.views_map or syn_target in idx.mviews_map:
                    rel_type = "READS/SELECTS"
                elif syn_target in idx.packages_set or syn_target in idx.code_map:
                    rel_type = "EXECUTES/CALLS"
                else:
                    rel_type = "DEPENDS_ON"
            else:
                rel_type = (
                    "READS/SELECTS"
                    if target_type in ("TABLE", "VIEW", "MATERIALIZED VIEW")
                    else ("EXECUTES/CALLS" if target_type in ("PROCEDURE", "FUNCTION", "PACKAGE", "PACKAGE BODY") else "DEPENDS_ON")
                )

            link_key = (focal_name, w, rel_type)
            if link_key not in seen_links:
                seen_links.add(link_key)
                result.dependencies.append(
                    DependencyLink(
                        source_name=focal_name,
                        source_type=focal_type,
                        target_name=w,
                        target_type=target_type,
                        relation_type=rel_type,
                        details=f"Routine accesses/executes {w}",
                        depth=1,
                    )
                )
                all_related_names.add(w)

    # 2. Incoming callers that reference this subprogram specifically
    for ref_name, ref_type, rel_type, details in idx.text_references.get(sub.name.upper(), []):
        if ref_name == (sub.package_name or "").upper() or ref_name == focal_name or ref_name in ORACLE_RESERVED_WORDS:
            continue
        link_key = (ref_name, focal_name, "CALLS_SUBPROGRAM")
        if link_key not in seen_links:
            seen_links.add(link_key)
            result.dependencies.append(
                DependencyLink(
                    source_name=ref_name,
                    source_type=ref_type,
                    target_name=focal_name,
                    target_type=focal_type,
                    relation_type="CALLS_SUBPROGRAM",
                    details=f"Objeto {ref_name} invoca a sub-rotina {focal_name}",
                    depth=1,
                )
            )
            all_related_names.add(ref_name)

    # Attach related objects in O(1)
    for name in all_related_names:
        if name in idx.tables_map:
            result.related_tables.append(idx.tables_map[name])
        if name in idx.views_map:
            result.related_views.append(idx.views_map[name])
        if name in idx.code_map:
            result.related_code_objects.append(idx.code_map[name])
        if name in idx.triggers_map:
            result.related_triggers.append(idx.triggers_map[name])

    return result
