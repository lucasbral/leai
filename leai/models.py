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


class ViewMeta(BaseModel):
    name: str
    text: str | None = None
    comment: str | None = None
    columns: list[ColumnMeta] = Field(default_factory=list)


class MaterializedViewMeta(BaseModel):
    name: str
    query: str | None = None
    refresh_mode: str | None = None
    refresh_type: str | None = None
    updatable: bool = False
    comment: str | None = None
    columns: list[ColumnMeta] = Field(default_factory=list)


class SubprogramMeta(BaseModel):
    package_name: str
    name: str
    subprogram_type: str  # PROCEDURE or FUNCTION
    source: str | None = None
    comment: str | None = None


class CodeObjectMeta(BaseModel):
    name: str
    object_type: str  # PROCEDURE, FUNCTION, PACKAGE, PACKAGE BODY
    source: str | None = None
    comment: str | None = None
    subprograms: list[SubprogramMeta] = Field(default_factory=list)


class TriggerMeta(BaseModel):
    name: str
    table_name: str | None = None
    trigger_type: str | None = None
    triggering_event: str | None = None
    status: str | None = None
    trigger_body: str | None = None


class SequenceMeta(BaseModel):
    name: str
    min_value: int | float | str | None = None
    max_value: int | float | str | None = None
    increment_by: int | None = None
    last_number: int | float | None = None


class IndexMeta(BaseModel):
    name: str
    table_name: str
    uniqueness: str = "NONUNIQUE"
    columns: list[str] = Field(default_factory=list)


class SynonymMeta(BaseModel):
    name: str
    table_owner: str | None = None
    table_name: str | None = None
    db_link: str | None = None


class ObjectAnnotation(BaseModel):
    description: str | None = None
    business_rules: list[str] = Field(default_factory=list)
    columns: dict[str, str] = Field(default_factory=dict)


class SchemaMetadata(BaseModel):
    tables: list[TableMeta] = Field(default_factory=list)
    views: list[ViewMeta] = Field(default_factory=list)
    mviews: list[MaterializedViewMeta] = Field(default_factory=list)
    code_objects: list[CodeObjectMeta] = Field(default_factory=list)
    triggers: list[TriggerMeta] = Field(default_factory=list)
    sequences: list[SequenceMeta] = Field(default_factory=list)
    indexes: list[IndexMeta] = Field(default_factory=list)
    synonyms: list[SynonymMeta] = Field(default_factory=list)
