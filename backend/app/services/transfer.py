from __future__ import annotations

import json
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.orm import Session

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

SCHEMA_VERSION = "1.0"
MANIFEST_NAME = "manifest.json"
DATA_NAME = "project.json"


def _iso(value: datetime) -> str:
    return value.isoformat()


def _project_document(
    project: Project, operations: list[Operation] | None = None
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "project": {
            "id": project.id,
            "name": project.name,
            "description": project.description,
            "language": project.language,
            "status": project.status,
            "created_at": _iso(project.created_at),
            "updated_at": _iso(project.updated_at),
            "volumes": [
                {
                    "id": volume.id,
                    "title": volume.title,
                    "position": volume.position,
                    "created_at": _iso(volume.created_at),
                    "updated_at": _iso(volume.updated_at),
                    "chapters": [
                        {
                            "id": chapter.id,
                            "title": chapter.title,
                            "position": chapter.position,
                            "status": chapter.status,
                            "content": chapter.content,
                            "content_hash": chapter.content_hash,
                            "word_count": chapter.word_count,
                            "created_at": _iso(chapter.created_at),
                            "updated_at": _iso(chapter.updated_at),
                            "revisions": [
                                {
                                    "id": revision.id,
                                    "parent_id": revision.parent_id,
                                    "content": revision.content,
                                    "content_hash": revision.content_hash,
                                    "source": revision.source,
                                    "operation_id": revision.operation_id,
                                    "created_at": _iso(revision.created_at),
                                }
                                for revision in chapter.revisions
                            ],
                        }
                        for chapter in volume.chapters
                    ],
                }
                for volume in project.volumes
            ],
            "entities": [
                {
                    "id": entity.id,
                    "kind": entity.kind,
                    "name": entity.name,
                    "aliases": entity.aliases,
                    "description": entity.description,
                    "attributes": entity.attributes,
                    "status": entity.status,
                    "created_at": _iso(entity.created_at),
                    "updated_at": _iso(entity.updated_at),
                }
                for entity in project.entities
            ],
            "notes": [
                {
                    "id": note.id,
                    "title": note.title,
                    "content": note.content,
                    "tags": note.tags,
                    "created_at": _iso(note.created_at),
                    "updated_at": _iso(note.updated_at),
                }
                for note in project.notes
            ],
            "operations": [
                {
                    "id": operation.id,
                    "target_type": operation.target_type,
                    "target_id": operation.target_id,
                    "type": operation.type,
                    "payload": operation.payload,
                    "old_hash": operation.old_hash,
                    "status": operation.status,
                    "source": operation.source,
                    "idempotency_key": operation.idempotency_key,
                    "created_at": _iso(operation.created_at),
                    "applied_at": _iso(operation.applied_at) if operation.applied_at else None,
                }
                for operation in (operations or [])
            ],
        },
    }


def export_json(project: Project, operations: list[Operation] | None = None) -> bytes:
    return json.dumps(_project_document(project, operations), ensure_ascii=False, indent=2).encode(
        "utf-8"
    )


def export_zip(project: Project, operations: list[Operation] | None = None) -> bytes:
    document = export_json(project, operations)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "format": "novel-workbench-project",
        "data": DATA_NAME,
        "attachments": [],
    }
    with tempfile.SpooledTemporaryFile(max_size=4 * 1024 * 1024) as output:
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False, indent=2))
            archive.writestr(DATA_NAME, document)
            archive.writestr("attachments/.gitkeep", "")
        output.seek(0)
        return output.read()


def _required(value: Any, name: str, kind: type | tuple[type, ...] = str) -> Any:
    if not isinstance(value, kind):
        raise HTTPException(422, detail={"code": "invalid_import", "message": f"{name} is invalid"})
    return value


def validate_document(document: Any) -> dict[str, Any]:
    if not isinstance(document, dict) or document.get("schema_version") != SCHEMA_VERSION:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "unsupported_schema",
                "message": "unsupported or missing schema_version",
            },
        )
    project = document.get("project")
    if not isinstance(project, dict):
        raise HTTPException(
            422, detail={"code": "invalid_import", "message": "project is required"}
        )
    _required(project.get("name"), "project.name")
    for key in ("volumes", "entities", "notes"):
        if not isinstance(project.get(key), list):
            raise HTTPException(
                422, detail={"code": "invalid_import", "message": f"project.{key} must be a list"}
            )
    if not isinstance(project.get("operations", []), list):
        raise HTTPException(
            422,
            detail={"code": "invalid_import", "message": "project.operations must be a list"},
        )
    for volume in project["volumes"]:
        if not isinstance(volume, dict):
            raise HTTPException(
                422, detail={"code": "invalid_import", "message": "volume must be an object"}
            )
        _required(volume.get("title"), "volume.title")
        if not isinstance(volume.get("chapters"), list):
            raise HTTPException(
                422, detail={"code": "invalid_import", "message": "volume.chapters must be a list"}
            )
        for chapter in volume["chapters"]:
            if not isinstance(chapter, dict):
                raise HTTPException(
                    422, detail={"code": "invalid_import", "message": "chapter must be an object"}
                )
            _required(chapter.get("title"), "chapter.title")
            _required(chapter.get("content"), "chapter.content")
            if not isinstance(chapter.get("revisions", []), list):
                raise HTTPException(
                    422,
                    detail={
                        "code": "invalid_import",
                        "message": "chapter.revisions must be a list",
                    },
                )
    for entity in project["entities"]:
        if not isinstance(entity, dict) or not isinstance(entity.get("name"), str):
            raise HTTPException(
                422, detail={"code": "invalid_import", "message": "entity.name is required"}
            )
    for note in project["notes"]:
        if not isinstance(note, dict) or not isinstance(note.get("title"), str):
            raise HTTPException(
                422, detail={"code": "invalid_import", "message": "note.title is required"}
            )
    for operation in project.get("operations", []):
        if not isinstance(operation, dict):
            raise HTTPException(
                422, detail={"code": "invalid_import", "message": "operation must be an object"}
            )
    return document


def decode_import_bytes(
    raw: bytes, filename: str | None = None, content_type: str | None = None
) -> dict[str, Any]:
    is_zip = filename and filename.lower().endswith(".zip")
    is_zip = is_zip or content_type == "application/zip" or raw[:2] == b"PK"
    if not is_zip:
        try:
            return validate_document(json.loads(raw.decode("utf-8")))
        except UnicodeDecodeError as exc:
            raise HTTPException(
                422, detail={"code": "invalid_import", "message": "JSON must be UTF-8"}
            ) from exc
        except json.JSONDecodeError as exc:
            raise HTTPException(
                422, detail={"code": "invalid_import", "message": "invalid JSON"}
            ) from exc

    try:
        with tempfile.TemporaryDirectory(prefix="novel-workbench-import-") as directory:
            path = Path(directory) / "project.zip"
            path.write_bytes(raw)
            with zipfile.ZipFile(path) as archive:
                names = set(archive.namelist())
                if MANIFEST_NAME not in names or DATA_NAME not in names:
                    raise HTTPException(
                        422,
                        detail={
                            "code": "invalid_package",
                            "message": "manifest.json and project.json are required",
                        },
                    )
                if any(name.startswith("/") or ".." in Path(name).parts for name in names):
                    raise HTTPException(
                        422, detail={"code": "invalid_package", "message": "unsafe archive path"}
                    )
                try:
                    manifest = json.loads(archive.read(MANIFEST_NAME).decode("utf-8"))
                    imported_document = json.loads(archive.read(DATA_NAME).decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise HTTPException(
                        422,
                        detail={"code": "invalid_package", "message": "package JSON is invalid"},
                    ) from exc
                if (
                    manifest.get("schema_version") != SCHEMA_VERSION
                    or manifest.get("data") != DATA_NAME
                ):
                    raise HTTPException(
                        422,
                        detail={
                            "code": "unsupported_schema",
                            "message": "invalid package manifest",
                        },
                    )
                return validate_document(imported_document)
    except zipfile.BadZipFile as exc:
        raise HTTPException(
            422, detail={"code": "invalid_package", "message": "invalid ZIP package"}
        ) from exc


def _parse_datetime(value: Any, fallback: datetime) -> datetime:
    if not value:
        return fallback
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            422, detail={"code": "invalid_import", "message": "invalid timestamp"}
        ) from exc


def import_project(db: Session, document: dict[str, Any]) -> Project:
    validate_document(document)
    raw = document["project"]
    now = datetime.now(timezone.utc)
    # Imports create an independent project so a backup can be restored beside its source.
    project_id = str(uuid4())
    project = Project(
        id=project_id,
        name=raw["name"],
        description=raw.get("description"),
        language=raw.get("language", "zh-CN"),
        status=raw.get("status", "active"),
        created_at=_parse_datetime(raw.get("created_at"), now),
        updated_at=_parse_datetime(raw.get("updated_at"), now),
    )
    db.add(project)
    volume_ids: set[str] = set()
    chapter_ids: set[str] = set()
    revision_ids: set[str] = set()
    id_map: dict[str, str] = {}
    for volume_raw in raw["volumes"]:
        old_volume_id = volume_raw.get("id")
        volume_id = str(uuid4())
        if old_volume_id:
            id_map[old_volume_id] = volume_id
        volume_ids.add(volume_id)
        volume = Volume(
            id=volume_id,
            project_id=project_id,
            title=volume_raw["title"],
            position=volume_raw.get("position", 0),
            created_at=_parse_datetime(volume_raw.get("created_at"), now),
            updated_at=_parse_datetime(volume_raw.get("updated_at"), now),
        )
        db.add(volume)
        for chapter_raw in volume_raw["chapters"]:
            old_chapter_id = chapter_raw.get("id")
            chapter_id = str(uuid4())
            if old_chapter_id:
                id_map[old_chapter_id] = chapter_id
            chapter_ids.add(chapter_id)
            content = chapter_raw["content"]
            chapter = Chapter(
                id=chapter_id,
                volume_id=volume_id,
                title=chapter_raw["title"],
                position=chapter_raw.get("position", 0),
                status=chapter_raw.get("status", "draft"),
                content=content,
                content_hash=content_hash(content),
                word_count=chapter_raw.get("word_count", len(content)),
                created_at=_parse_datetime(chapter_raw.get("created_at"), now),
                updated_at=_parse_datetime(chapter_raw.get("updated_at"), now),
            )
            db.add(chapter)
            for revision_raw in chapter_raw.get("revisions", []):
                old_revision_id = revision_raw.get("id")
                revision_id = str(uuid4())
                if old_revision_id:
                    id_map[old_revision_id] = revision_id
                revision_ids.add(revision_id)
                db.add(
                    Revision(
                        id=revision_id,
                        chapter_id=chapter_id,
                        parent_id=id_map.get(revision_raw.get("parent_id")),
                        content=revision_raw.get("content", content),
                        content_hash=content_hash(revision_raw.get("content", content)),
                        source=revision_raw.get("source", "user"),
                        operation_id=None,
                        created_at=_parse_datetime(revision_raw.get("created_at"), now),
                    )
                )
    for entity_raw in raw["entities"]:
        entity_id = str(uuid4())
        if entity_raw.get("id"):
            id_map[entity_raw["id"]] = entity_id
        db.add(
            Entity(
                project_id=project_id,
                id=entity_id,
                kind=entity_raw.get("kind", "other"),
                name=entity_raw["name"],
                aliases=entity_raw.get("aliases", []),
                description=entity_raw.get("description", ""),
                attributes=entity_raw.get("attributes", {}),
                status=entity_raw.get("status", "draft"),
                created_at=_parse_datetime(entity_raw.get("created_at"), now),
                updated_at=_parse_datetime(entity_raw.get("updated_at"), now),
            )
        )
    for note_raw in raw["notes"]:
        note_id = str(uuid4())
        if note_raw.get("id"):
            id_map[note_raw["id"]] = note_id
        db.add(
            Note(
                project_id=project_id,
                id=note_id,
                title=note_raw["title"],
                content=note_raw.get("content", ""),
                tags=note_raw.get("tags", []),
                created_at=_parse_datetime(note_raw.get("created_at"), now),
                updated_at=_parse_datetime(note_raw.get("updated_at"), now),
            )
        )
    for operation_raw in raw.get("operations", []):
        target_id = id_map.get(operation_raw.get("target_id"))
        if not target_id:
            continue
        db.add(
            Operation(
                id=str(uuid4()),
                project_id=project_id,
                target_type=operation_raw.get("target_type", "chapter"),
                target_id=target_id,
                type=operation_raw.get("type", "append"),
                payload=operation_raw.get("payload", {}),
                old_hash=operation_raw.get("old_hash"),
                status=operation_raw.get("status", "pending"),
                source=operation_raw.get("source", "user"),
                idempotency_key=None,
                created_at=_parse_datetime(operation_raw.get("created_at"), now),
                applied_at=_parse_datetime(operation_raw.get("applied_at"), now)
                if operation_raw.get("applied_at")
                else None,
            )
        )
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(project)
    return project
