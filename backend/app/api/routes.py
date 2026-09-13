import asyncio
import json

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
    Note,
    Operation,
    Project,
    Provider,
    Revision,
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
    EntityCreate,
    EntityPage,
    EntityPatch,
    EntityRead,
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
    ProviderCreate,
    ProviderPatch,
    ProviderRead,
    RevisionRead,
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
from app.services.domain import (
    approve_operation,
    create_revision,
    get_chapter,
    get_project,
    get_volume,
    reject_operation,
)
from app.services.domain import create_operation as create_operation_service
from app.services.transfer import decode_import_bytes, export_json, export_zip, import_project

router = APIRouter(prefix="/api/v1")


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


@router.post("/ai/sessions", response_model=AiSessionRead, status_code=status.HTTP_201_CREATED)
def create_ai_session(data: AiSessionCreate, db: Session = Depends(get_db)):
    return create_session(db, data.project_id, data.provider_id, data.model, data.system_prompt)


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
        db, session, data.content, data.chapter_id, data.selected_text, data.idempotency_key
    )
    if created:
        from app.services.ai import schedule_message

        schedule_message(session.id, message.id, data.chapter_id, data.selected_text)
    return {"message_id": message.id, "session_id": session.id, "status": message.status}


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
    return create_operation_service(db, data)


@router.post("/operations/{operation_id}/approve", response_model=OperationRead)
def approve(operation_id: str, db: Session = Depends(get_db)):
    return approve_operation(db, operation_id)


@router.post("/operations/{operation_id}/reject", response_model=OperationRead)
def reject(operation_id: str, db: Session = Depends(get_db)):
    return reject_operation(db, operation_id)


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
