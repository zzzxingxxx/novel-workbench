from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    language: str = "zh-CN"


class ProjectRead(ProjectCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    status: str
    created_at: datetime
    updated_at: datetime


class ProjectPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    language: str | None = Field(default=None, max_length=20)
    status: str | None = Field(default=None, max_length=30)


class VolumeCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    position: int = Field(default=0, ge=0)


class VolumeRead(VolumeCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    created_at: datetime
    updated_at: datetime


class VolumePatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    position: int | None = Field(default=None, ge=0)


class ChapterCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    position: int = Field(default=0, ge=0)
    content: str = ""


class ChapterPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    status: str | None = Field(default=None, max_length=30)


class ChapterRead(ChapterCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    volume_id: str
    status: str
    content_hash: str
    word_count: int
    created_at: datetime
    updated_at: datetime


class EntityCreate(BaseModel):
    kind: str = Field(min_length=1, max_length=30)
    name: str = Field(min_length=1, max_length=200)
    aliases: list[str] = Field(default_factory=list)
    description: str = ""
    attributes: dict[str, Any] = Field(default_factory=dict)


class EntityRead(EntityCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    status: str
    created_at: datetime
    updated_at: datetime


class EntityPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    aliases: list[str] | None = None
    description: str | None = None
    attributes: dict[str, Any] | None = None
    status: str | None = Field(default=None, max_length=30)


class NoteCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = ""
    tags: list[str] = Field(default_factory=list)


class NoteRead(NoteCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    created_at: datetime
    updated_at: datetime


class NotePatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    content: str | None = None
    tags: list[str] | None = None


class OperationCreate(BaseModel):
    project_id: str
    target_type: Literal["chapter"] = "chapter"
    target_id: str
    type: Literal["replace_range", "append", "restore_revision"]
    payload: dict[str, Any] = Field(default_factory=dict)
    old_hash: str | None = None
    source: Literal["user", "ai"] = "user"
    idempotency_key: str | None = Field(default=None, max_length=200)


class OperationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    target_type: str
    target_id: str
    type: str
    payload: dict[str, Any]
    old_hash: str | None
    status: str
    source: str
    idempotency_key: str | None
    created_at: datetime
    applied_at: datetime | None


class RevisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    chapter_id: str
    parent_id: str | None
    content: str
    content_hash: str
    source: str
    operation_id: str | None
    created_at: datetime


class PageMeta(BaseModel):
    page: int
    page_size: int
    total: int
    has_next: bool


class ProjectPage(BaseModel):
    items: list[ProjectRead]
    meta: PageMeta


class VolumePage(BaseModel):
    items: list[VolumeRead]
    meta: PageMeta


class ChapterPage(BaseModel):
    items: list[ChapterRead]
    meta: PageMeta


class EntityPage(BaseModel):
    items: list[EntityRead]
    meta: PageMeta


class NotePage(BaseModel):
    items: list[NoteRead]
    meta: PageMeta
