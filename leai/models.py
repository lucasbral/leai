from __future__ import annotations

from pydantic import BaseModel, Field


class ColumnMeta(BaseModel):
    name: str
    data_type: str
    nullable: bool
    default: str | None = None
    comment: str | None = None


class ForeignKeyMeta(BaseModel):
    name: str
    column: str
    referenced_table: str
    referenced_column: str


class TableMeta(BaseModel):
    name: str
    comment: str | None = None
    columns: list[ColumnMeta] = Field(default_factory=list)
    primary_keys: list[str] = Field(default_factory=list)
    foreign_keys: list[ForeignKeyMeta] = Field(default_factory=list)
    created_at: str | None = None
    last_ddl_time: str | None = None
    last_modified_by: str | None = None


class ViewMeta(BaseModel):
    name: str
    text: str | None = None
    comment: str | None = None
    columns: list[ColumnMeta] = Field(default_factory=list)
    created_at: str | None = None
    last_ddl_time: str | None = None
    last_modified_by: str | None = None


class MaterializedViewMeta(BaseModel):
    name: str
    query: str | None = None
    refresh_mode: str | None = None
    refresh_type: str | None = None
    updatable: bool = False
    comment: str | None = None
    columns: list[ColumnMeta] = Field(default_factory=list)
    created_at: str | None = None
    last_ddl_time: str | None = None
    last_modified_by: str | None = None


class SubprogramMeta(BaseModel):
    package_name: str
    name: str
    subprogram_type: str  # PROCEDURE or FUNCTION
    source: str | None = None
    comment: str | None = None
    created_at: str | None = None
    last_ddl_time: str | None = None
    last_modified_by: str | None = None


class CodeObjectMeta(BaseModel):
    name: str
    object_type: str  # PROCEDURE, FUNCTION, PACKAGE, PACKAGE BODY
    source: str | None = None
    comment: str | None = None
    subprograms: list[SubprogramMeta] = Field(default_factory=list)
    created_at: str | None = None
    last_ddl_time: str | None = None
    last_modified_by: str | None = None


class TriggerMeta(BaseModel):
    name: str
    table_name: str | None = None
    trigger_type: str | None = None
    triggering_event: str | None = None
    status: str | None = None
    trigger_body: str | None = None
    created_at: str | None = None
    last_ddl_time: str | None = None
    last_modified_by: str | None = None


class SequenceMeta(BaseModel):
    name: str
    min_value: int | float | str | None = None
    max_value: int | float | str | None = None
    increment_by: int | None = None
    last_number: int | float | None = None
    created_at: str | None = None
    last_ddl_time: str | None = None
    last_modified_by: str | None = None


class IndexMeta(BaseModel):
    name: str
    table_name: str
    uniqueness: str = "NONUNIQUE"
    columns: list[str] = Field(default_factory=list)
    created_at: str | None = None
    last_ddl_time: str | None = None
    last_modified_by: str | None = None


class SynonymMeta(BaseModel):
    name: str
    table_owner: str | None = None
    table_name: str | None = None
    db_link: str | None = None
    created_at: str | None = None
    last_ddl_time: str | None = None
    last_modified_by: str | None = None


class ObjectAnnotation(BaseModel):
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    business_rules: list[str] = Field(default_factory=list)
    use_cases: list[str] = Field(default_factory=list)
    related_objects: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    columns: dict[str, str] = Field(default_factory=dict)


class GlossaryTerm(BaseModel):
    term: str
    definition: str
    primary_table: str | None = None
    canonical_filter: str | None = None
    related_tables: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)


class BusinessGlossary(BaseModel):
    terms: list[GlossaryTerm] = Field(default_factory=list)


class SchemaMetadata(BaseModel):
    schema_name: str = ""
    tables: list[TableMeta] = Field(default_factory=list)
    views: list[ViewMeta] = Field(default_factory=list)
    mviews: list[MaterializedViewMeta] = Field(default_factory=list)
    code_objects: list[CodeObjectMeta] = Field(default_factory=list)
    triggers: list[TriggerMeta] = Field(default_factory=list)
    sequences: list[SequenceMeta] = Field(default_factory=list)
    indexes: list[IndexMeta] = Field(default_factory=list)
    synonyms: list[SynonymMeta] = Field(default_factory=list)


class DependencyLink(BaseModel):
    source_name: str
    source_type: str  # TABLE, VIEW, PROCEDURE, PACKAGE, TRIGGER, etc.
    target_name: str
    target_type: str
    relation_type: str  # 'FK_REFERENCES', 'READS/SELECTS', 'MODIFIES/DML', 'CALLS', 'TRIGGER_ON'
    details: str | None = None
    depth: int = 1


class ObjectTraceResult(BaseModel):
    focal_name: str
    focal_type: str
    focal_object: (
        TableMeta
        | ViewMeta
        | MaterializedViewMeta
        | CodeObjectMeta
        | TriggerMeta
        | SequenceMeta
        | IndexMeta
        | SynonymMeta
        | SubprogramMeta
        | None
    ) = None
    dependencies: list[DependencyLink] = Field(default_factory=list)
    related_tables: list[TableMeta] = Field(default_factory=list)
    related_views: list[ViewMeta] = Field(default_factory=list)
    related_code_objects: list[CodeObjectMeta] = Field(default_factory=list)
    related_triggers: list[TriggerMeta] = Field(default_factory=list)
    extracted_notes: list[str] = Field(default_factory=list)
    extracted_tasks: list[str] = Field(default_factory=list)
