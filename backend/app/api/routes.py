from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.domain import (
    Chapter,
    Entity,
    Note,
    Operation,
    Project,
    Revision,
    Volume,
    content_hash,
)
from app.schemas.domain import (
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
    RevisionRead,
    VolumeCreate,
    VolumePage,
    VolumePatch,
    VolumeRead,
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
