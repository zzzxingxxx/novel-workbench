import asyncio
import json
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal, get_db
from app.models.domain import (
    AiEvent,
    AiMessage,
    AiSession,
    Chapter,
    Entity,
    EntityRevision,
    EntitySourceLink,
    EvaluationCase,
    EvaluationRun,
    Foreshadow,
    ForeshadowLink,
    Job,
    Note,
    Operation,
    Project,
    PromptTemplate,
    PromptVersion,
    Provider,
    Revision,
    StoryBranch,
    TimelineEvent,
    Volume,
    content_hash,
)
from app.schemas.domain import (
    AiMessageAccepted,
    AiMessageCreate,
    AiMessageRead,
    AiSessionCreate,
    AiSessionRead,
    ChapterCreate,
    ChapterPage,
    ChapterPatch,
    ChapterRead,
    ContextBuildRequest,
    CreateNoteToolRequest,
    EntityCreate,
    EntityPage,
    EntityPatch,
    EntityRead,
    EntityRevisionRead,
    EntitySourceLinkCreate,
    EntitySourceLinkRead,
    EvaluationCaseCreate,
    EvaluationCaseRead,
    EvaluationRunRead,
    ForeshadowCreate,
    ForeshadowLinkCreate,
    ForeshadowLinkRead,
    ForeshadowRead,
    JobCreate,
    JobRead,
    NoteCreate,
    NotePage,
    NotePatch,
    NoteRead,
    OperationCreate,
    OperationRead,
    PageMeta,
    ProjectCreate,
    ProjectPage,
    ProjectPatch,
    ProjectRead,
    PromptPreviewRead,
    PromptPreviewRequest,
    PromptTemplateCreate,
    PromptTemplatePatch,
    PromptTemplateRead,
    PromptVersionCreate,
    PromptVersionRead,
    ProposeTextOperationToolRequest,
    ProviderCreate,
    ProviderPatch,
    ProviderRead,
    ReadChapterToolRequest,
    ReadEntityToolRequest,
    RevisionRead,
    SearchProjectRequest,
    SearchProjectToolRequest,
    StoryBranchCreate,
    StoryBranchRead,
    TimelineEventCreate,
    TimelineEventRead,
    ToolResult,
    UpdateEntityToolRequest,
    VolumeCreate,
    VolumePage,
    VolumePatch,
    VolumeRead,
)
from app.services.ai import (
    cancel_session,
    create_message,
    create_session,
    encrypt_api_key,
    provider_for,
    session_or_404,
)
from app.services.context import (
    build_context_package,
    tool_create_note,
    tool_propose_operation,
    tool_read_chapter,
    tool_read_entity,
    tool_search_project,
    tool_update_entity,
)
from app.services.domain import (
    approve_operation,
    create_revision,
    get_chapter,
    get_project,
    get_volume,
    reject_operation,
    undo_operation,
)
from app.services.domain import create_operation as create_operation_service
from app.services.jobs import run_job
from app.services.prompts import build_prompt, validate_prompt
from app.services.search import rebuild_project_index, search_project
from app.services.transfer import decode_import_bytes, export_json, export_zip, import_project

router = APIRouter(prefix="/api/v1")


def _prompt_template_read(template: PromptTemplate) -> dict[str, object]:
    return {
        "id": template.id,
        "project_id": template.project_id,
        "scope": template.scope,
        "owner_id": template.owner_id,
        "name": template.name,
        "enabled": template.enabled,
        "active_version_id": template.active_version_id,
        "created_at": template.created_at,
        "updated_at": template.updated_at,
    }


def _validate_template_scope(data: PromptTemplateCreate | PromptTemplatePatch, db: Session) -> None:
    scope = getattr(data, "scope", None)
    if scope == "project" and not getattr(data, "project_id", None):
        raise HTTPException(
            422,
            detail={
                "code": "invalid_prompt_scope",
                "message": "project prompt requires project_id",
            },
        )
    if scope in {"agent", "workflow"} and not getattr(data, "owner_id", None):
        raise HTTPException(
            422,
            detail={
                "code": "invalid_prompt_scope",
                "message": "scoped prompt requires owner_id",
            },
        )
    project_id = getattr(data, "project_id", None)
    if project_id and not db.get(Project, project_id):
        raise HTTPException(
            404, detail={"code": "project_not_found", "message": "project not found"}
        )


@router.post("/prompts", response_model=PromptTemplateRead, status_code=status.HTTP_201_CREATED)
def create_prompt_template(data: PromptTemplateCreate, db: Session = Depends(get_db)):
    _validate_template_scope(data, db)
    variables = [item.model_dump() for item in data.variables]
    validate_prompt(data.content, variables)
    template = PromptTemplate(
        scope=data.scope,
        project_id=data.project_id,
        owner_id=data.owner_id,
        name=data.name,
        enabled=data.enabled,
    )
    db.add(template)
    db.flush()
    version = PromptVersion(
        template_id=template.id,
        version=1,
        content=data.content,
        variables=variables,
        created_by=data.created_by,
    )
    db.add(version)
    db.flush()
    template.active_version_id = version.id
    db.commit()
    db.refresh(template)
    return _prompt_template_read(template)


@router.get("/prompts", response_model=list[PromptTemplateRead])
def list_prompt_templates(
    project_id: str | None = None,
    scope: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    query = select(PromptTemplate).order_by(
        PromptTemplate.scope,
        PromptTemplate.created_at,
        PromptTemplate.id,
    )
    if project_id:
        query = query.where(
            (PromptTemplate.project_id == project_id) | (PromptTemplate.project_id.is_(None))
        )
    if scope:
        query = query.where(PromptTemplate.scope == scope)
    return [_prompt_template_read(item) for item in db.scalars(query)]


@router.post("/prompts/preview", response_model=PromptPreviewRead)
def preview_prompt(data: PromptPreviewRequest, db: Session = Depends(get_db)):
    get_project(db, data.project_id)
    return build_prompt(
        db,
        data.project_id,
        data.agent_id,
        data.workflow_id,
        data.session_prompt,
        data.variables,
    )


@router.get("/prompts/{template_id}", response_model=PromptTemplateRead)
def read_prompt_template(template_id: str, db: Session = Depends(get_db)):
    template = db.get(PromptTemplate, template_id)
    if not template:
        raise HTTPException(
            404,
            detail={
                "code": "prompt_not_found",
                "message": "prompt template not found",
            },
        )
    return _prompt_template_read(template)


@router.patch("/prompts/{template_id}", response_model=PromptTemplateRead)
def patch_prompt_template(
    template_id: str, data: PromptTemplatePatch, db: Session = Depends(get_db)
):
    template = db.get(PromptTemplate, template_id)
    if not template:
        raise HTTPException(
            404,
            detail={
                "code": "prompt_not_found",
                "message": "prompt template not found",
            },
        )
    values = data.model_dump(exclude_unset=True)
    content = values.pop("content", None)
    variables = values.pop("variables", None)
    created_by = values.pop("created_by", None)
    if "active_version_id" in values and values["active_version_id"]:
        version_query = select(PromptVersion).where(
            PromptVersion.id == values["active_version_id"],
            PromptVersion.template_id == template.id,
        )
        if not db.scalar(version_query):
            raise HTTPException(
                422,
                detail={
                    "code": "invalid_prompt_version",
                    "message": "version does not belong to template",
                },
            )
    if content is not None:
        variable_data = variables
        if variable_data is None:
            variable_data = template.versions[-1].variables if template.versions else []
        validate_prompt(content, variable_data)
        next_version = (
            db.scalar(
                select(func.max(PromptVersion.version)).where(
                    PromptVersion.template_id == template.id
                )
            )
            or 0
        ) + 1
        version = PromptVersion(
            template_id=template.id,
            version=next_version,
            content=content,
            variables=variable_data,
            created_by=created_by,
        )
        db.add(version)
        db.flush()
        template.active_version_id = version.id
    elif variables is not None:
        current = template.versions[-1] if template.versions else None
        if not current:
            raise HTTPException(
                422,
                detail={
                    "code": "invalid_prompt_version",
                    "message": "template has no version",
                },
            )
        validate_prompt(current.content, variables)
        next_version = (
            db.scalar(
                select(func.max(PromptVersion.version)).where(
                    PromptVersion.template_id == template.id
                )
            )
            or 0
        ) + 1
        version = PromptVersion(
            template_id=template.id,
            version=next_version,
            content=current.content,
            variables=variables,
            created_by=created_by,
        )
        db.add(version)
        db.flush()
        template.active_version_id = version.id
    for key, value in values.items():
        setattr(template, key, value)
    db.commit()
    db.refresh(template)
    return _prompt_template_read(template)


@router.delete("/prompts/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_prompt_template(template_id: str, db: Session = Depends(get_db)):
    template = db.get(PromptTemplate, template_id)
    if not template:
        raise HTTPException(
            404,
            detail={
                "code": "prompt_not_found",
                "message": "prompt template not found",
            },
        )
    db.delete(template)
    db.commit()


@router.get("/prompts/{template_id}/versions", response_model=list[PromptVersionRead])
def list_prompt_versions(template_id: str, db: Session = Depends(get_db)):
    template = db.get(PromptTemplate, template_id)
    if not template:
        raise HTTPException(
            404,
            detail={
                "code": "prompt_not_found",
                "message": "prompt template not found",
            },
        )
    return list(
        db.scalars(
            select(PromptVersion)
            .where(PromptVersion.template_id == template_id)
            .order_by(PromptVersion.version.desc())
        )
    )


@router.post(
    "/prompts/{template_id}/versions",
    response_model=PromptVersionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_prompt_version(
    template_id: str, data: PromptVersionCreate, db: Session = Depends(get_db)
):
    template = db.get(PromptTemplate, template_id)
    if not template:
        raise HTTPException(
            404, detail={"code": "prompt_not_found", "message": "prompt template not found"}
        )
    variables = [item.model_dump() for item in data.variables]
    validate_prompt(data.content, variables)
    next_version = (
        db.scalar(
            select(func.max(PromptVersion.version)).where(PromptVersion.template_id == template_id)
        )
        or 0
    ) + 1
    version = PromptVersion(
        template_id=template_id,
        version=next_version,
        content=data.content,
        variables=variables,
        created_by=data.created_by,
    )
    db.add(version)
    db.flush()
    template.active_version_id = version.id
    db.commit()
    db.refresh(version)
    return version


def _provider_read(provider: Provider) -> dict[str, object]:
    return {
        "id": provider.id,
        "name": provider.name,
        "kind": provider.kind,
        "base_url": provider.base_url,
        "model": provider.model,
        "enabled": provider.enabled,
        "timeout_seconds": provider.timeout_seconds,
        "has_api_key": bool(provider.api_key_encrypted),
        "created_at": provider.created_at,
        "updated_at": provider.updated_at,
    }


@router.post("/providers", response_model=ProviderRead, status_code=status.HTTP_201_CREATED)
def create_provider(data: ProviderCreate, db: Session = Depends(get_db)):
    provider = Provider(
        name=data.name,
        kind=data.kind,
        base_url=data.base_url,
        model=data.model,
        api_key_encrypted=encrypt_api_key(data.api_key),
        enabled=data.enabled,
        timeout_seconds=data.timeout_seconds,
    )
    db.add(provider)
    db.commit()
    db.refresh(provider)
    return _provider_read(provider)


@router.get("/providers", response_model=list[ProviderRead])
def list_providers(db: Session = Depends(get_db)):
    return [
        _provider_read(item) for item in db.scalars(select(Provider).order_by(Provider.created_at))
    ]


@router.get("/providers/{provider_id}", response_model=ProviderRead)
def read_provider(provider_id: str, db: Session = Depends(get_db)):
    provider = db.get(Provider, provider_id)
    if not provider:
        raise HTTPException(
            404, detail={"code": "provider_not_found", "message": "provider not found"}
        )
    return _provider_read(provider)


@router.patch("/providers/{provider_id}", response_model=ProviderRead)
def patch_provider(provider_id: str, data: ProviderPatch, db: Session = Depends(get_db)):
    provider = db.get(Provider, provider_id)
    if not provider:
        raise HTTPException(
            404, detail={"code": "provider_not_found", "message": "provider not found"}
        )
    values = data.model_dump(exclude_unset=True)
    if "api_key" in values:
        provider.api_key_encrypted = encrypt_api_key(values.pop("api_key"))
    for key, value in values.items():
        setattr(provider, key, value)
    db.commit()
    db.refresh(provider)
    return _provider_read(provider)


@router.delete("/providers/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_provider(provider_id: str, db: Session = Depends(get_db)):
    provider = db.get(Provider, provider_id)
    if not provider:
        raise HTTPException(
            404, detail={"code": "provider_not_found", "message": "provider not found"}
        )
    db.delete(provider)
    db.commit()


@router.post("/providers/{provider_id}/test")
async def test_provider(provider_id: str, db: Session = Depends(get_db)):
    provider = db.get(Provider, provider_id)
    if not provider:
        raise HTTPException(
            404, detail={"code": "provider_not_found", "message": "provider not found"}
        )
    try:
        return await provider_for(provider).test(provider.model)
    except Exception as exc:
        raise HTTPException(
            502, detail={"code": "provider_error", "message": str(exc)[:500]}
        ) from exc


@router.post("/context/build")
def build_context(data: ContextBuildRequest, db: Session = Depends(get_db)):
    session_prompt = None
    if data.session_id:
        session = session_or_404(db, data.session_id)
        if session.project_id != data.project_id:
            raise HTTPException(
                400,
                detail={"code": "invalid_session", "message": "session does not belong to project"},
            )
        session_prompt = session.system_prompt
    return build_context_package(
        db,
        project_id=data.project_id,
        user_instruction=data.user_instruction,
        chapter_id=data.chapter_id,
        selected_text=data.selected_text,
        search_query=data.search_query,
        search_limit=data.search_limit,
        system_prompt=session_prompt,
        budget_tokens=data.budget_tokens,
    )


@router.post("/search", response_model=dict[str, object])
def search_route(data: SearchProjectRequest, db: Session = Depends(get_db)):
    get_project(db, data.project_id)
    return search_project(
        db,
        data.project_id,
        data.query,
        data.limit,
        data.source_type,
        data.volume_id,
    )


@router.post("/projects/{project_id}/search/reindex")
def reindex_project_route(project_id: str, db: Session = Depends(get_db)):
    get_project(db, project_id)
    return {"ok": True, "index_version": "fts5-v1", **rebuild_project_index(db, project_id)}


@router.post("/tools/read_chapter", response_model=ToolResult)
def tool_read_chapter_route(data: ReadChapterToolRequest, db: Session = Depends(get_db)):
    return tool_read_chapter(db, data.project_id, data.chapter_id)


@router.post("/tools/search_project", response_model=ToolResult)
def tool_search_project_route(data: SearchProjectToolRequest, db: Session = Depends(get_db)):
    return tool_search_project(db, data.project_id, data.query, data.limit)


@router.post("/tools/read_entity", response_model=ToolResult)
def tool_read_entity_route(data: ReadEntityToolRequest, db: Session = Depends(get_db)):
    return tool_read_entity(db, data.project_id, data.entity_id)


@router.post("/tools/create_note", response_model=ToolResult)
def tool_create_note_route(data: CreateNoteToolRequest, db: Session = Depends(get_db)):
    return tool_create_note(db, data.project_id, data.title, data.content, data.tags)


@router.post("/tools/propose_text_operation", response_model=ToolResult)
def tool_propose_text_operation_route(
    data: ProposeTextOperationToolRequest, db: Session = Depends(get_db)
):
    return tool_propose_operation(
        db, data.project_id, data.chapter_id, data.type, data.payload, data.old_hash
    )


@router.post("/tools/update_entity", response_model=ToolResult)
def tool_update_entity_route(data: UpdateEntityToolRequest, db: Session = Depends(get_db)):
    return tool_update_entity(db, data.project_id, data.entity_id, data.changes)


@router.post("/ai/sessions", response_model=AiSessionRead, status_code=status.HTTP_201_CREATED)
def create_ai_session(data: AiSessionCreate, db: Session = Depends(get_db)):
    return create_session(
        db,
        data.project_id,
        data.provider_id,
        data.model,
        data.system_prompt,
        data.agent_id,
        data.workflow_id,
        data.prompt_variables,
    )


@router.get("/ai/sessions/{session_id}", response_model=AiSessionRead)
def read_ai_session(session_id: str, db: Session = Depends(get_db)):
    return session_or_404(db, session_id)


@router.get("/ai/sessions/{session_id}/messages", response_model=list[AiMessageRead])
def list_ai_messages(session_id: str, db: Session = Depends(get_db)):
    session_or_404(db, session_id)
    return list(
        db.scalars(
            select(AiMessage)
            .where(AiMessage.session_id == session_id)
            .order_by(AiMessage.created_at)
        )
    )


@router.post(
    "/ai/sessions/{session_id}/messages",
    response_model=AiMessageAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_ai_message(session_id: str, data: AiMessageCreate, db: Session = Depends(get_db)):
    session = session_or_404(db, session_id)
    message, created = create_message(
        db,
        session,
        data.content,
        data.chapter_id,
        data.selected_text,
        data.idempotency_key,
        data.context_budget,
        data.search_query,
        data.search_limit,
    )
    if created:
        from app.services.ai import schedule_message

        schedule_message(session.id, message.id, data.chapter_id, data.selected_text)
    return {"message_id": message.id, "session_id": session.id, "status": message.status}


@router.get("/ai/sessions/{session_id}/messages/{message_id}/context")
def read_message_context(session_id: str, message_id: str, db: Session = Depends(get_db)):
    session_or_404(db, session_id)
    message = db.get(AiMessage, message_id)
    if not message or message.session_id != session_id:
        raise HTTPException(
            404, detail={"code": "message_not_found", "message": "message not found"}
        )
    return {
        "message_id": message.id,
        "session_id": session_id,
        "package": message.context_package,
        "digest": message.context_digest,
        "used_tokens": message.context_tokens,
        "budget_tokens": message.context_budget,
    }


@router.get("/ai/sessions/{session_id}/events")
async def ai_events(
    session_id: str,
    request: Request,
    last_event_id: int | None = Query(default=None, alias="last_event_id", ge=0),
    db: Session = Depends(get_db),
):
    session_or_404(db, session_id)
    header_id = request.headers.get("last-event-id")
    if header_id and header_id.isdigit():
        last_event_id = int(header_id)

    async def event_stream():
        cursor = last_event_id or 0
        idle_rounds = 0
        while idle_rounds < 600:
            if await request.is_disconnected():
                return
            stream_db = SessionLocal()
            try:
                events = list(
                    stream_db.scalars(
                        select(AiEvent)
                        .where(AiEvent.session_id == session_id, AiEvent.sequence > cursor)
                        .order_by(AiEvent.sequence)
                    )
                )
                session_state = stream_db.get(AiSession, session_id)
            finally:
                stream_db.close()
            if events:
                idle_rounds = 0
                for event in events:
                    cursor = event.sequence
                    payload = {
                        "session_id": session_id,
                        "type": event.event_type,
                        "data": event.data,
                        "created_at": event.created_at.isoformat(),
                    }
                    encoded = json.dumps(payload, ensure_ascii=False)
                    yield f"id: {event.sequence}\nevent: {event.event_type}\ndata: {encoded}\n\n"
                if session_state and session_state.status in {"completed", "failed", "cancelled"}:
                    return
            else:
                idle_rounds += 1
                if session_state and session_state.status in {"completed", "failed", "cancelled"}:
                    return
                yield ": keep-alive\n\n"
            await asyncio.sleep(0.1)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/ai/sessions/{session_id}/cancel", response_model=AiSessionRead)
def cancel_ai_session(session_id: str, db: Session = Depends(get_db)):
    return cancel_session(db, session_id)


@router.post("/projects", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(data: ProjectCreate, db: Session = Depends(get_db)):
    project = Project(**data.model_dump())
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def _page(page: int, page_size: int, total: int) -> PageMeta:
    return PageMeta(page=page, page_size=page_size, total=total, has_next=page * page_size < total)


@router.get("/projects", response_model=list[ProjectRead] | ProjectPage)
def list_projects(
    page: int | None = Query(default=None, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    if page is None:
        return list(db.scalars(select(Project).order_by(Project.created_at.desc(), Project.id)))
    total = db.scalar(select(func.count()).select_from(Project)) or 0
    items = list(
        db.scalars(
            select(Project)
            .order_by(Project.created_at.desc(), Project.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return {"items": items, "meta": _page(page, page_size, total)}


@router.get("/projects/{project_id}", response_model=ProjectRead)
def read_project(project_id: str, db: Session = Depends(get_db)):
    return get_project(db, project_id)


@router.patch("/projects/{project_id}", response_model=ProjectRead)
def patch_project(project_id: str, data: ProjectPatch, db: Session = Depends(get_db)):
    project = get_project(db, project_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(project, key, value)
    db.commit()
    db.refresh(project)
    return project


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: str, db: Session = Depends(get_db)):
    project = get_project(db, project_id)
    db.delete(project)
    db.commit()


@router.post(
    "/projects/{project_id}/volumes", response_model=VolumeRead, status_code=status.HTTP_201_CREATED
)
def create_volume(project_id: str, data: VolumeCreate, db: Session = Depends(get_db)):
    get_project(db, project_id)
    values = data.model_dump()
    if (
        values["position"] == 0
        and (
            db.scalar(
                select(func.count()).select_from(Volume).where(Volume.project_id == project_id)
            )
            or 0
        )
        > 0
    ):
        max_position = db.scalar(
            select(func.max(Volume.position)).where(Volume.project_id == project_id)
        )
        values["position"] = (max_position if max_position is not None else -1) + 1
    volume = Volume(project_id=project_id, **values)
    db.add(volume)
    db.commit()
    db.refresh(volume)
    return volume


@router.get("/projects/{project_id}/volumes", response_model=list[VolumeRead] | VolumePage)
def list_volumes(
    project_id: str,
    page: int | None = Query(default=None, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    get_project(db, project_id)
    query = (
        select(Volume).where(Volume.project_id == project_id).order_by(Volume.position, Volume.id)
    )
    if page is None:
        return list(db.scalars(query))
    total = (
        db.scalar(select(func.count()).select_from(Volume).where(Volume.project_id == project_id))
        or 0
    )
    return {
        "items": list(db.scalars(query.offset((page - 1) * page_size).limit(page_size))),
        "meta": _page(page, page_size, total),
    }


@router.get("/projects/{project_id}/tree")
def project_tree(project_id: str, db: Session = Depends(get_db)):
    project = get_project(db, project_id)
    return {
        "project": ProjectRead.model_validate(project),
        "volumes": [
            {
                "id": volume.id,
                "title": volume.title,
                "position": volume.position,
                "chapters": [
                    {
                        "id": chapter.id,
                        "title": chapter.title,
                        "position": chapter.position,
                        "status": chapter.status,
                    }
                    for chapter in volume.chapters
                ],
            }
            for volume in project.volumes
        ],
    }


@router.delete("/volumes/{volume_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_volume(volume_id: str, db: Session = Depends(get_db)):
    volume = get_volume(db, volume_id)
    db.delete(volume)
    db.commit()


@router.patch("/volumes/{volume_id}", response_model=VolumeRead)
def patch_volume(volume_id: str, data: VolumePatch, db: Session = Depends(get_db)):
    volume = get_volume(db, volume_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(volume, key, value)
    db.commit()
    db.refresh(volume)
    return volume


@router.post(
    "/volumes/{volume_id}/chapters", response_model=ChapterRead, status_code=status.HTTP_201_CREATED
)
def create_chapter(volume_id: str, data: ChapterCreate, db: Session = Depends(get_db)):
    get_volume(db, volume_id)
    values = data.model_dump()
    if (
        values["position"] == 0
        and (
            db.scalar(
                select(func.count()).select_from(Chapter).where(Chapter.volume_id == volume_id)
            )
            or 0
        )
        > 0
    ):
        max_position = db.scalar(
            select(func.max(Chapter.position)).where(Chapter.volume_id == volume_id)
        )
        values["position"] = (max_position if max_position is not None else -1) + 1
    chapter = Chapter(volume_id=volume_id, **values)
    chapter.word_count = len(chapter.content)
    chapter.content_hash = content_hash(chapter.content)
    db.add(chapter)
    db.flush()
    create_revision(db, chapter, "user")
    db.commit()
    db.refresh(chapter)
    return chapter


@router.get("/chapters/{chapter_id}", response_model=ChapterRead)
def read_chapter(chapter_id: str, db: Session = Depends(get_db)):
    return get_chapter(db, chapter_id)


@router.get("/volumes/{volume_id}/chapters", response_model=list[ChapterRead] | ChapterPage)
def list_chapters(
    volume_id: str,
    page: int | None = Query(default=None, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    get_volume(db, volume_id)
    query = (
        select(Chapter).where(Chapter.volume_id == volume_id).order_by(Chapter.position, Chapter.id)
    )
    if page is None:
        return list(db.scalars(query))
    total = (
        db.scalar(select(func.count()).select_from(Chapter).where(Chapter.volume_id == volume_id))
        or 0
    )
    return {
        "items": list(db.scalars(query.offset((page - 1) * page_size).limit(page_size))),
        "meta": _page(page, page_size, total),
    }


@router.patch("/chapters/{chapter_id}", response_model=ChapterRead)
def patch_chapter(chapter_id: str, data: ChapterPatch, db: Session = Depends(get_db)):
    chapter = get_chapter(db, chapter_id)
    values = data.model_dump(exclude_unset=True)
    [setattr(chapter, k, v) for k, v in values.items()]
    db.commit()
    db.refresh(chapter)
    return chapter


@router.delete("/chapters/{chapter_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chapter(chapter_id: str, db: Session = Depends(get_db)):
    chapter = get_chapter(db, chapter_id)
    db.delete(chapter)
    db.commit()


@router.get("/chapters/{chapter_id}/revisions", response_model=list[RevisionRead])
def list_revisions(chapter_id: str, db: Session = Depends(get_db)):
    get_chapter(db, chapter_id)
    return list(
        db.scalars(
            select(Revision)
            .where(Revision.chapter_id == chapter_id)
            .order_by(Revision.created_at.desc())
        )
    )


@router.post("/operations", response_model=OperationRead, status_code=status.HTTP_201_CREATED)
def create_operation(data: OperationCreate, db: Session = Depends(get_db)):
    operation = create_operation_service(db, data)
    if operation.permission == "auto" and operation.status == "pending":
        operation = approve_operation(db, operation.id)
    return operation


@router.post("/operations/{operation_id}/approve", response_model=OperationRead)
def approve(operation_id: str, db: Session = Depends(get_db)):
    return approve_operation(db, operation_id)


@router.post("/operations/{operation_id}/reject", response_model=OperationRead)
def reject(operation_id: str, db: Session = Depends(get_db)):
    return reject_operation(db, operation_id)


@router.post("/operations/{operation_id}/undo", response_model=OperationRead, status_code=201)
def undo(operation_id: str, db: Session = Depends(get_db)):
    return undo_operation(db, operation_id)


@router.get("/operations/{operation_id}", response_model=OperationRead)
def read_operation(operation_id: str, db: Session = Depends(get_db)):
    operation = db.get(Operation, operation_id)
    if not operation:
        raise HTTPException(404, "operation not found")
    return operation


@router.post(
    "/projects/{project_id}/entities",
    response_model=EntityRead,
    status_code=status.HTTP_201_CREATED,
)
def create_entity(project_id: str, data: EntityCreate, db: Session = Depends(get_db)):
    get_project(db, project_id)
    entity = Entity(project_id=project_id, **data.model_dump())
    db.add(entity)
    db.commit()
    db.refresh(entity)
    return entity


@router.get("/projects/{project_id}/entities", response_model=list[EntityRead] | EntityPage)
def list_entities(
    project_id: str,
    page: int | None = Query(default=None, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    get_project(db, project_id)
    query = select(Entity).where(Entity.project_id == project_id).order_by(Entity.name, Entity.id)
    if page is None:
        return list(db.scalars(query))
    total = (
        db.scalar(select(func.count()).select_from(Entity).where(Entity.project_id == project_id))
        or 0
    )
    return {
        "items": list(db.scalars(query.offset((page - 1) * page_size).limit(page_size))),
        "meta": _page(page, page_size, total),
    }


@router.patch("/entities/{entity_id}", response_model=EntityRead)
def patch_entity(entity_id: str, data: EntityPatch, db: Session = Depends(get_db)):
    entity = db.get(Entity, entity_id)
    if not entity:
        raise HTTPException(404, "entity not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(entity, key, value)
    db.add(
        EntityRevision(
            project_id=entity.project_id,
            entity_id=entity.id,
            snapshot={
                "name": entity.name,
                "description": entity.description,
                "aliases": entity.aliases or [],
                "attributes": entity.attributes or {},
                "status": entity.status,
                "tags": entity.tags or [],
            },
            source="user",
        )
    )
    db.commit()
    db.refresh(entity)
    return entity


@router.delete("/entities/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entity(entity_id: str, db: Session = Depends(get_db)):
    entity = db.get(Entity, entity_id)
    if not entity:
        raise HTTPException(404, "entity not found")
    db.delete(entity)
    db.commit()


@router.post(
    "/projects/{project_id}/notes", response_model=NoteRead, status_code=status.HTTP_201_CREATED
)
def create_note(project_id: str, data: NoteCreate, db: Session = Depends(get_db)):
    get_project(db, project_id)
    note = Note(project_id=project_id, **data.model_dump())
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


@router.get("/projects/{project_id}/notes", response_model=list[NoteRead] | NotePage)
def list_notes(
    project_id: str,
    page: int | None = Query(default=None, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    get_project(db, project_id)
    query = (
        select(Note).where(Note.project_id == project_id).order_by(Note.created_at.desc(), Note.id)
    )
    if page is None:
        return list(db.scalars(query))
    total = (
        db.scalar(select(func.count()).select_from(Note).where(Note.project_id == project_id)) or 0
    )
    return {
        "items": list(db.scalars(query.offset((page - 1) * page_size).limit(page_size))),
        "meta": _page(page, page_size, total),
    }


@router.get("/projects/{project_id}/export")
def export_project(project_id: str, format: str = "json", db: Session = Depends(get_db)):
    project = get_project(db, project_id)
    operations = list(
        db.scalars(
            select(Operation)
            .where(Operation.project_id == project_id)
            .order_by(Operation.created_at)
        )
    )
    if format == "json":
        return Response(
            export_json(project, operations),
            media_type="application/json",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="novel-workbench-{project.id[:8]}.json"'
                )
            },
        )
    if format == "zip":
        return Response(
            export_zip(project, operations),
            media_type="application/zip",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="novel-workbench-{project.id[:8]}.zip"'
                )
            },
        )
    raise HTTPException(
        422, detail={"code": "invalid_format", "message": "format must be json or zip"}
    )


@router.post("/projects/import", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def import_project_route(request: Request, db: Session = Depends(get_db)):
    raw = await request.body()
    document = decode_import_bytes(
        raw, request.headers.get("x-filename"), request.headers.get("content-type")
    )
    return import_project(db, document)


@router.patch("/notes/{note_id}", response_model=NoteRead)
def patch_note(note_id: str, data: NotePatch, db: Session = Depends(get_db)):
    note = db.get(Note, note_id)
    if not note:
        raise HTTPException(404, "note not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(note, key, value)
    db.commit()
    db.refresh(note)
    return note


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(note_id: str, db: Session = Depends(get_db)):
    note = db.get(Note, note_id)
    if not note:
        raise HTTPException(404, "note not found")
    db.delete(note)
    db.commit()


@router.post("/projects/{project_id}/jobs", response_model=JobRead, status_code=202)
def create_job(project_id: str, data: JobCreate, db: Session = Depends(get_db)):
    get_project(db, project_id)
    job = Job(project_id=project_id, job_type=data.job_type, input_snapshot=data.input_snapshot)
    db.add(job)
    db.commit()
    db.refresh(job)
    # Jobs are persisted before execution, so a process restart can resume queued work.
    return run_job(db, job)


@router.get("/projects/{project_id}/jobs", response_model=list[JobRead])
def list_jobs(project_id: str, db: Session = Depends(get_db)):
    get_project(db, project_id)
    return list(
        db.scalars(select(Job).where(Job.project_id == project_id).order_by(Job.created_at.desc()))
    )


@router.get("/jobs/{job_id}", response_model=JobRead)
def read_job(job_id: str, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return job


@router.post("/jobs/{job_id}/pause", response_model=JobRead)
def pause_job(job_id: str, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "job not found")
    if job.status in {"queued", "running"}:
        job.status = "paused"
        db.commit()
        db.refresh(job)
    return job


@router.post("/jobs/{job_id}/resume", response_model=JobRead)
def resume_job(job_id: str, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "job not found")
    if job.status in {"paused", "failed"}:
        job.retry_count += 1
        job.error = None
        db.commit()
        return run_job(db, job)
    return job


@router.post("/jobs/{job_id}/cancel", response_model=JobRead)
def cancel_job(job_id: str, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "job not found")
    job.cancel_requested = True
    job.status = "cancelled"
    db.commit()
    db.refresh(job)
    return job


@router.get("/jobs/{job_id}/report")
def export_job_report(job_id: str, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return Response(
        json.dumps(job.output, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="review-{job.id[:8]}.json"'},
    )


@router.post(
    "/projects/{project_id}/evaluation-cases", response_model=EvaluationCaseRead, status_code=201
)
def create_evaluation_case(
    project_id: str, data: EvaluationCaseCreate, db: Session = Depends(get_db)
):
    get_project(db, project_id)
    case = EvaluationCase(project_id=project_id, **data.model_dump())
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


@router.get("/projects/{project_id}/evaluation-cases", response_model=list[EvaluationCaseRead])
def list_evaluation_cases(project_id: str, db: Session = Depends(get_db)):
    get_project(db, project_id)
    return list(
        db.scalars(
            select(EvaluationCase)
            .where(EvaluationCase.project_id == project_id)
            .order_by(EvaluationCase.created_at)
        )
    )


@router.post("/evaluation-cases/{case_id}/runs", response_model=EvaluationRunRead, status_code=201)
def run_evaluation(case_id: str, db: Session = Depends(get_db)):
    case = db.get(EvaluationCase, case_id)
    if not case:
        raise HTTPException(404, "evaluation case not found")
    actual = case.input_data.get("actual", case.input_data)
    expected = case.expected
    exact = actual == expected if expected else None
    run = EvaluationRun(
        project_id=case.project_id,
        case_id=case.id,
        result={"actual": actual, "expected": expected},
        metrics={
            "exact_match": exact,
            "human_score": None,
            "citation_accuracy": None,
            "tokens": 0,
            "latency_ms": 0,
            "cost": 0,
        },
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


@router.get("/projects/{project_id}/evaluation-runs", response_model=list[EvaluationRunRead])
def list_evaluation_runs(project_id: str, db: Session = Depends(get_db)):
    get_project(db, project_id)
    return list(
        db.scalars(
            select(EvaluationRun)
            .where(EvaluationRun.project_id == project_id)
            .order_by(EvaluationRun.created_at.desc())
        )
    )


@router.get("/entities/{entity_id}/sources", response_model=list[EntitySourceLinkRead])
def list_entity_sources(entity_id: str, db: Session = Depends(get_db)):
    entity = db.get(Entity, entity_id)
    if not entity:
        raise HTTPException(404, "entity not found")
    return list(
        db.scalars(
            select(EntitySourceLink)
            .where(EntitySourceLink.entity_id == entity_id)
            .order_by(EntitySourceLink.created_at)
        )
    )


@router.post("/entities/{entity_id}/sources", response_model=EntitySourceLinkRead, status_code=201)
def create_entity_source(
    entity_id: str, data: EntitySourceLinkCreate, db: Session = Depends(get_db)
):
    entity = db.get(Entity, entity_id)
    chapter = db.get(Chapter, data.chapter_id)
    if not entity or not chapter or chapter.volume.project_id != entity.project_id:
        raise HTTPException(400, "source does not belong to project")
    link = EntitySourceLink(project_id=entity.project_id, entity_id=entity.id, **data.model_dump())
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


@router.get("/entities/{entity_id}/revisions", response_model=list[EntityRevisionRead])
def list_entity_revisions(entity_id: str, db: Session = Depends(get_db)):
    if not db.get(Entity, entity_id):
        raise HTTPException(404, "entity not found")
    return list(
        db.scalars(
            select(EntityRevision)
            .where(EntityRevision.entity_id == entity_id)
            .order_by(EntityRevision.created_at.desc())
        )
    )


@router.get("/entities/{entity_id}/affected-chapters")
def affected_entity_chapters(entity_id: str, db: Session = Depends(get_db)):
    entity = db.get(Entity, entity_id)
    if not entity:
        raise HTTPException(404, "entity not found")
    chapters = db.scalars(
        select(Chapter)
        .join(EntitySourceLink, EntitySourceLink.chapter_id == Chapter.id)
        .where(EntitySourceLink.entity_id == entity_id)
        .order_by(Chapter.position, Chapter.id)
    )
    return [{"id": item.id, "title": item.title, "volume_id": item.volume_id} for item in chapters]


@router.post("/projects/{project_id}/timeline", response_model=TimelineEventRead, status_code=201)
def create_timeline_event(
    project_id: str, data: TimelineEventCreate, db: Session = Depends(get_db)
):
    get_project(db, project_id)
    event = TimelineEvent(project_id=project_id, **data.model_dump())
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


@router.get("/projects/{project_id}/timeline", response_model=list[TimelineEventRead])
def list_timeline_events(project_id: str, db: Session = Depends(get_db)):
    get_project(db, project_id)
    return list(
        db.scalars(
            select(TimelineEvent)
            .where(TimelineEvent.project_id == project_id)
            .order_by(
                TimelineEvent.relative_order.is_(None),
                TimelineEvent.relative_order,
                TimelineEvent.absolute_time,
                TimelineEvent.created_at,
            )
        )
    )


@router.patch("/timeline/{event_id}", response_model=TimelineEventRead)
def patch_timeline_event(event_id: str, data: dict[str, Any], db: Session = Depends(get_db)):
    event = db.get(TimelineEvent, event_id)
    if not event:
        raise HTTPException(404, "timeline event not found")
    for key in (
        "title",
        "description",
        "absolute_time",
        "relative_order",
        "time_status",
        "chapter_ids",
        "entity_ids",
    ):
        if key in data:
            setattr(event, key, data[key])
    db.commit()
    db.refresh(event)
    return event


@router.post("/projects/{project_id}/branches", response_model=StoryBranchRead, status_code=201)
def create_story_branch(project_id: str, data: StoryBranchCreate, db: Session = Depends(get_db)):
    get_project(db, project_id)
    if data.parent_id:
        parent = db.get(StoryBranch, data.parent_id)
        if not parent or parent.project_id != project_id:
            raise HTTPException(400, "parent does not belong to project")
    branch = StoryBranch(project_id=project_id, **data.model_dump())
    db.add(branch)
    db.commit()
    db.refresh(branch)
    return branch


@router.get("/projects/{project_id}/branches", response_model=list[StoryBranchRead])
def list_story_branches(project_id: str, db: Session = Depends(get_db)):
    get_project(db, project_id)
    return list(
        db.scalars(
            select(StoryBranch)
            .where(StoryBranch.project_id == project_id)
            .order_by(StoryBranch.created_at)
        )
    )


@router.patch("/branches/{branch_id}", response_model=StoryBranchRead)
def patch_story_branch(branch_id: str, data: dict[str, Any], db: Session = Depends(get_db)):
    branch = db.get(StoryBranch, branch_id)
    if not branch:
        raise HTTPException(404, "story branch not found")
    for key in ("name", "parent_id", "trigger_condition", "chapter_ids", "status"):
        if key in data:
            setattr(branch, key, data[key])
    db.commit()
    db.refresh(branch)
    return branch


@router.post("/projects/{project_id}/foreshadows", response_model=ForeshadowRead, status_code=201)
def create_foreshadow(project_id: str, data: ForeshadowCreate, db: Session = Depends(get_db)):
    get_project(db, project_id)
    item = Foreshadow(project_id=project_id, **data.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/projects/{project_id}/foreshadows", response_model=list[ForeshadowRead])
def list_foreshadows(project_id: str, db: Session = Depends(get_db)):
    get_project(db, project_id)
    return list(
        db.scalars(
            select(Foreshadow)
            .where(Foreshadow.project_id == project_id)
            .order_by(Foreshadow.status, Foreshadow.created_at)
        )
    )


@router.patch("/foreshadows/{foreshadow_id}", response_model=ForeshadowRead)
def patch_foreshadow(foreshadow_id: str, data: dict[str, Any], db: Session = Depends(get_db)):
    item = db.get(Foreshadow, foreshadow_id)
    if not item:
        raise HTTPException(404, "foreshadow not found")
    allowed = {"title", "description", "status", "planted_chapter_ids", "resolved_chapter_ids"}
    for key, value in data.items():
        if key in allowed:
            setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return item


@router.post(
    "/foreshadows/{foreshadow_id}/links", response_model=ForeshadowLinkRead, status_code=201
)
def create_foreshadow_link(
    foreshadow_id: str, data: ForeshadowLinkCreate, db: Session = Depends(get_db)
):
    item = db.get(Foreshadow, foreshadow_id)
    if not item:
        raise HTTPException(404, "foreshadow not found")
    link = ForeshadowLink(project_id=item.project_id, foreshadow_id=item.id, **data.model_dump())
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


@router.get("/foreshadows/{foreshadow_id}/links", response_model=list[ForeshadowLinkRead])
def list_foreshadow_links(foreshadow_id: str, db: Session = Depends(get_db)):
    if not db.get(Foreshadow, foreshadow_id):
        raise HTTPException(404, "foreshadow not found")
    return list(
        db.scalars(
            select(ForeshadowLink)
            .where(ForeshadowLink.foreshadow_id == foreshadow_id)
            .order_by(ForeshadowLink.created_at)
        )
    )
