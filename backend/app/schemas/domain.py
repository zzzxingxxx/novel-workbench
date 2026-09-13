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


class ProviderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: Literal["openai_compatible"] = "openai_compatible"
    base_url: str = Field(min_length=1, max_length=500)
    model: str = Field(min_length=1, max_length=200)
    api_key: str | None = Field(default=None, max_length=500)
    enabled: bool = True
    timeout_seconds: int = Field(default=90, ge=5, le=600)


class ProviderPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    base_url: str | None = Field(default=None, min_length=1, max_length=500)
    model: str | None = Field(default=None, min_length=1, max_length=200)
    api_key: str | None = Field(default=None, max_length=500)
    enabled: bool | None = None
    timeout_seconds: int | None = Field(default=None, ge=5, le=600)


class ProviderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    kind: str
    base_url: str
    model: str
    enabled: bool
    timeout_seconds: int
    has_api_key: bool
    created_at: datetime
    updated_at: datetime


PromptScope = Literal["global", "project", "agent", "workflow", "session"]


class PromptVariable(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    type: Literal["string", "number", "boolean"] = "string"
    required: bool = False


class PromptTemplateCreate(BaseModel):
    scope: PromptScope
    project_id: str | None = None
    owner_id: str | None = None
    name: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1, max_length=100_000)
    variables: list[PromptVariable] = Field(default_factory=list)
    enabled: bool = True
    created_by: str | None = Field(default=None, max_length=120)


class PromptTemplatePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    enabled: bool | None = None
    active_version_id: str | None = None
    content: str | None = Field(default=None, min_length=1, max_length=100_000)
    variables: list[PromptVariable] | None = None
    created_by: str | None = Field(default=None, max_length=120)


class PromptVersionCreate(BaseModel):
    content: str = Field(min_length=1, max_length=100_000)
    variables: list[PromptVariable] = Field(default_factory=list)
    created_by: str | None = Field(default=None, max_length=120)


class PromptVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    template_id: str
    version: int
    content: str
    variables: list[dict[str, Any]]
    created_by: str | None
    created_at: datetime


class PromptTemplateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str | None
    scope: PromptScope
    owner_id: str | None
    name: str
    enabled: bool
    active_version_id: str | None
    created_at: datetime
    updated_at: datetime


class PromptPreviewRequest(BaseModel):
    project_id: str
    agent_id: str | None = None
    workflow_id: str | None = None
    session_prompt: str | None = None
    variables: dict[str, Any] = Field(default_factory=dict)


class PromptPreviewSection(BaseModel):
    scope: PromptScope
    template_id: str | None
    version_id: str | None
    version: int | None
    name: str
    content: str


class PromptPreviewRead(BaseModel):
    prompt: str
    version_ids: list[str]
    sections: list[PromptPreviewSection]
    estimated_tokens: int
    digest: str


class AiSessionCreate(BaseModel):
    project_id: str
    provider_id: str | None = None
    model: str | None = Field(default=None, max_length=200)
    system_prompt: str | None = None
    agent_id: str | None = None
    workflow_id: str | None = None
    prompt_variables: dict[str, Any] = Field(default_factory=dict)


class AiSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    provider_id: str | None
    model: str | None
    status: str
    system_prompt: str | None
    agent_id: str | None
    workflow_id: str | None
    prompt_variables: dict[str, Any]
    prompt_version_ids: list[str]
    prompt_snapshot: list[dict[str, Any]]
    prompt_digest: str | None
    created_at: datetime
    updated_at: datetime


class AiMessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=100_000)
    chapter_id: str | None = None
    selected_text: str | None = None
    idempotency_key: str | None = Field(default=None, max_length=200)


class AiMessageAccepted(BaseModel):
    message_id: str
    session_id: str
    status: str


class AiMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    session_id: str
    role: str
    content: str
    status: str
    prompt_tokens: int | None
    completion_tokens: int | None
    created_at: datetime
    completed_at: datetime | None


class AiEventRead(BaseModel):
    id: int
    session_id: str
    type: str
    data: dict[str, Any]
    created_at: datetime
