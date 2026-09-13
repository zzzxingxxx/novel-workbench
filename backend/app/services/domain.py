from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.domain import (
    Chapter,
    Entity,
    Operation,
    Project,
    Revision,
    Volume,
    content_hash,
)
from app.schemas.domain import OperationCreate


def _not_found(kind: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"{kind} not found")


def get_project(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise _not_found("project")
    return project


def get_volume(db: Session, volume_id: str) -> Volume:
    volume = db.get(Volume, volume_id)
    if not volume:
        raise _not_found("volume")
    return volume


def get_chapter(db: Session, chapter_id: str) -> Chapter:
    chapter = db.get(Chapter, chapter_id)
    if not chapter:
        raise _not_found("chapter")
    return chapter


def validate_operation_payload(db: Session, chapter: Chapter, data: OperationCreate) -> None:
    if data.target_type == "entity" and data.type != "update_entity":
        raise HTTPException(
            422,
            detail={
                "code": "invalid_operation",
                "message": "entity operations must use update_entity",
            },
        )
    if data.target_type == "chapter" and data.type == "update_entity":
        raise HTTPException(
            422,
            detail={
                "code": "invalid_operation",
                "message": "update_entity requires an entity target",
            },
        )
    payload = data.payload
    if data.type == "append":
        if not isinstance(payload.get("new_text"), str):
            raise HTTPException(
                422, detail={"code": "invalid_operation", "message": "append requires new_text"}
            )
    elif data.type == "replace_range":
        start, end, new_text = payload.get("from"), payload.get("to"), payload.get("new_text")
        if (
            not isinstance(start, int)
            or not isinstance(end, int)
            or not isinstance(new_text, str)
            or start < 0
            or end < start
            or end > len(chapter.content)
        ):
            raise HTTPException(
                422,
                detail={
                    "code": "invalid_operation",
                    "message": "replace_range requires valid from, to and new_text",
                },
            )
    elif data.type == "restore_revision":
        revision_id = payload.get("revision_id")
        revision = db.get(Revision, revision_id) if isinstance(revision_id, str) else None
        if not revision or revision.chapter_id != chapter.id:
            raise HTTPException(
                422,
                detail={
                    "code": "invalid_operation",
                    "message": "revision does not belong to chapter",
                },
            )
    elif data.type == "update_entity":
        if data.target_type != "entity":
            raise HTTPException(
                422,
                detail={"code": "invalid_operation", "message": "update_entity targets an entity"},
            )
        entity = db.get(Entity, data.target_id)
        if (
            not entity
            or entity.project_id != data.project_id
            or not isinstance(data.payload.get("changes"), dict)
        ):
            raise HTTPException(
                422, detail={"code": "invalid_operation", "message": "entity changes are invalid"}
            )


def create_revision(
    db: Session, chapter: Chapter, source: str, operation_id: str | None = None
) -> Revision:
    previous = db.scalar(
        select(Revision)
        .where(Revision.chapter_id == chapter.id)
        .order_by(Revision.created_at.desc())
    )
    revision = Revision(
        chapter_id=chapter.id,
        parent_id=previous.id if previous else None,
        content=chapter.content,
        content_hash=chapter.content_hash,
        source=source,
        operation_id=operation_id,
    )
    db.add(revision)
    return revision


def create_operation(db: Session, data: OperationCreate) -> Operation:
    if data.idempotency_key:
        existing = db.scalar(
            select(Operation).where(Operation.idempotency_key == data.idempotency_key)
        )
        if existing:
            if (existing.project_id, existing.target_id, existing.type, existing.payload) != (
                data.project_id,
                data.target_id,
                data.type,
                data.payload,
            ):
                raise HTTPException(
                    409,
                    detail={
                        "code": "idempotency_conflict",
                        "message": "idempotency key was already used for another operation",
                    },
                )
            return existing
    get_project(db, data.project_id)
    chapter = None
    if data.target_type == "chapter":
        chapter = get_chapter(db, data.target_id)
        if chapter.volume.project_id != data.project_id:
            raise HTTPException(status_code=400, detail="target does not belong to project")
        validate_operation_payload(db, chapter, data)
    else:
        entity = db.get(Entity, data.target_id)
        if not entity or entity.project_id != data.project_id:
            raise HTTPException(status_code=400, detail="target does not belong to project")
        validate_operation_payload(db, chapter, data)
    operation = Operation(
        project_id=data.project_id,
        target_type=data.target_type,
        target_id=data.target_id,
        type=data.type,
        payload=data.payload,
        old_hash=data.old_hash,
        source=data.source,
        idempotency_key=data.idempotency_key,
    )
    current_hash = chapter.content_hash if chapter is not None else None
    if data.old_hash is not None and data.old_hash != current_hash:
        operation.status = "conflict"
    db.add(operation)
    db.commit()
    db.refresh(operation)
    if operation.status == "conflict":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "content_conflict",
                "current_hash": current_hash,
                "operation_id": operation.id,
            },
        )
    return operation


def approve_operation(db: Session, operation_id: str) -> Operation:
    operation = db.get(Operation, operation_id)
    if not operation:
        raise _not_found("operation")
    if operation.status != "pending":
        return operation
    if operation.target_type == "entity":
        entity = db.get(Entity, operation.target_id)
        if not entity or entity.project_id != operation.project_id:
            operation.status = "conflict"
            db.commit()
            raise HTTPException(
                status_code=409, detail={"code": "content_conflict", "operation_id": operation.id}
            )
        if operation.type == "update_entity":
            changes = operation.payload.get("changes", {})
            for key in ("name", "description", "aliases", "attributes", "status"):
                if key in changes:
                    setattr(entity, key, changes[key])
        operation.status = "applied"
        operation.applied_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(operation)
        return operation
    chapter = get_chapter(db, operation.target_id)
    if operation.old_hash is not None and operation.old_hash != chapter.content_hash:
        operation.status = "conflict"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "content_conflict",
                "current_hash": chapter.content_hash,
                "operation_id": operation.id,
            },
        )
    old_content = chapter.content
    if operation.type == "replace_range":
        start = operation.payload.get("from")
        end = operation.payload.get("to")
        new_text = operation.payload.get("new_text")
        chapter.content = old_content[:start] + new_text + old_content[end:]
    elif operation.type == "append":
        new_text = operation.payload.get("new_text")
        chapter.content = old_content + new_text
    elif operation.type == "restore_revision":
        revision_id = operation.payload.get("revision_id")
        revision = db.get(Revision, revision_id) if isinstance(revision_id, str) else None
        chapter.content = revision.content
    chapter.word_count = len(chapter.content)
    chapter.content_hash = content_hash(chapter.content)
    if chapter.content != old_content:
        create_revision(db, chapter, operation.source, operation.id)
    operation.status = "applied"
    operation.applied_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(operation)
    return operation


def reject_operation(db: Session, operation_id: str) -> Operation:
    operation = db.get(Operation, operation_id)
    if not operation:
        raise _not_found("operation")
    if operation.status == "pending":
        operation.status = "rejected"
        db.commit()
        db.refresh(operation)
    return operation
