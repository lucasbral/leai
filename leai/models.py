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
