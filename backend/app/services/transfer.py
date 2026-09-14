from __future__ import annotations

import hashlib
import html
import json
import re
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
    EntityRevision,
    EntitySourceLink,
    Foreshadow,
    ForeshadowLink,
    Note,
    Operation,
    Project,
    Revision,
    StoryBranch,
    TimelineEvent,
    Volume,
    content_hash,
)

SCHEMA_VERSION = "1.1"
SUPPORTED_SCHEMA_VERSIONS = {"1.0", SCHEMA_VERSION}
MANIFEST_NAME = "manifest.json"
DATA_NAME = "project.json"


def _iso(value: datetime) -> str:
    return value.isoformat()


def _project_document(
    project: Project,
    operations: list[Operation] | None = None,
    db: Session | None = None,
) -> dict[str, Any]:
    story_graph: dict[str, list[dict[str, Any]]] = {
        "entity_sources": [],
        "entity_revisions": [],
        "timeline_events": [],
        "story_branches": [],
        "foreshadows": [],
        "foreshadow_links": [],
    }
    if db is not None:
        story_graph["entity_sources"] = [
            {
                "id": item.id,
                "entity_id": item.entity_id,
                "chapter_id": item.chapter_id,
                "evidence": item.evidence,
                "created_at": _iso(item.created_at),
            }
            for item in db.query(EntitySourceLink)
            .filter(EntitySourceLink.project_id == project.id)
            .all()
        ]
        story_graph["entity_revisions"] = [
            {
                "id": item.id,
                "entity_id": item.entity_id,
                "snapshot": item.snapshot,
                "source": item.source,
                "operation_id": item.operation_id,
                "created_at": _iso(item.created_at),
            }
            for item in db.query(EntityRevision)
            .filter(EntityRevision.project_id == project.id)
            .all()
        ]
        story_graph["timeline_events"] = [
            {
                "id": item.id,
                "title": item.title,
                "description": item.description,
                "absolute_time": item.absolute_time,
                "relative_order": item.relative_order,
                "time_status": item.time_status,
                "chapter_ids": item.chapter_ids,
                "entity_ids": item.entity_ids,
                "created_at": _iso(item.created_at),
                "updated_at": _iso(item.updated_at),
            }
            for item in db.query(TimelineEvent).filter(TimelineEvent.project_id == project.id).all()
        ]
        story_graph["story_branches"] = [
            {
                "id": item.id,
                "parent_id": item.parent_id,
                "name": item.name,
                "trigger_condition": item.trigger_condition,
                "chapter_ids": item.chapter_ids,
                "status": item.status,
                "created_at": _iso(item.created_at),
                "updated_at": _iso(item.updated_at),
            }
            for item in db.query(StoryBranch).filter(StoryBranch.project_id == project.id).all()
        ]
        story_graph["foreshadows"] = [
            {
                "id": item.id,
                "title": item.title,
                "description": item.description,
                "status": item.status,
                "planted_chapter_ids": item.planted_chapter_ids,
                "resolved_chapter_ids": item.resolved_chapter_ids,
                "created_at": _iso(item.created_at),
                "updated_at": _iso(item.updated_at),
            }
            for item in db.query(Foreshadow).filter(Foreshadow.project_id == project.id).all()
        ]
        story_graph["foreshadow_links"] = [
            {
                "id": item.id,
                "foreshadow_id": item.foreshadow_id,
                "source_type": item.source_type,
                "source_id": item.source_id,
                "evidence": item.evidence,
                "link_kind": item.link_kind,
                "created_at": _iso(item.created_at),
            }
            for item in db.query(ForeshadowLink)
            .filter(ForeshadowLink.project_id == project.id)
            .all()
        ]
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
                    "tags": entity.tags,
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
                    "target_version_hash": operation.target_version_hash,
                    "diff": operation.diff,
                    "permission": operation.permission,
                    "undo_operation_id": operation.undo_operation_id,
                }
                for operation in (operations or [])
            ],
            "story_graph": story_graph,
        },
    }


def export_json(
    project: Project, operations: list[Operation] | None = None, db: Session | None = None
) -> bytes:
    return json.dumps(
        _project_document(project, operations, db), ensure_ascii=False, indent=2
    ).encode("utf-8")


def export_zip(
    project: Project, operations: list[Operation] | None = None, db: Session | None = None
) -> bytes:
    document = export_json(project, operations, db)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "format": "novel-workbench-project",
        "data": DATA_NAME,
        "attachments": [],
        "files": {DATA_NAME: hashlib.sha256(document).hexdigest()},
    }
    with tempfile.SpooledTemporaryFile(max_size=4 * 1024 * 1024) as output:
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False, indent=2))
            archive.writestr(DATA_NAME, document)
            archive.writestr("attachments/.gitkeep", "")
        output.seek(0)
        return output.read()


def _safe_slug(value: str, fallback: str) -> str:
    slug = re.sub(r"[^\w\-\.]+", "-", value, flags=re.UNICODE).strip("-.")
    return slug[:100] or fallback


def export_markdown_zip(
    project: Project, operations: list[Operation] | None = None, db: Session | None = None
) -> bytes:
    files: dict[str, bytes] = {
        "project.md": f"# {project.name}\n\n{project.description or ''}\n".encode("utf-8")
    }
    for volume in project.volumes:
        volume_name = f"{volume.position + 1:02d}-{_safe_slug(volume.title, 'volume')}"
        for chapter in volume.chapters:
            name = f"{chapter.position + 1:02d}-{_safe_slug(chapter.title, 'chapter')}.md"
            files[f"{volume_name}/{name}"] = f"# {chapter.title}\n\n{chapter.content}".encode(
                "utf-8"
            )
    for entity in project.entities:
        files[f"entities/{_safe_slug(entity.name, 'entity')}.md"] = (
            f"# {entity.name}\n\n{entity.description}\n\n"
            f"- 类型：{entity.kind}\n- 状态：{entity.status}\n"
        ).encode("utf-8")
    for note in project.notes:
        files[f"notes/{_safe_slug(note.title, 'note')}.md"] = (
            f"# {note.title}\n\n{note.content}\n"
        ).encode("utf-8")
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "format": "novel-workbench-markdown",
        "files": {name: hashlib.sha256(value).hexdigest() for name, value in files.items()},
    }
    with tempfile.SpooledTemporaryFile(max_size=4 * 1024 * 1024) as output:
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False, indent=2))
            for name, value in files.items():
                archive.writestr(name, value)
        output.seek(0)
        return output.read()


def export_docx(
    project: Project, operations: list[Operation] | None = None, db: Session | None = None
) -> bytes:
    _ = operations, db
    paragraphs: list[str] = [project.name]
    for volume in project.volumes:
        paragraphs.append(volume.title)
        for chapter in volume.chapters:
            paragraphs.extend([chapter.title, *chapter.content.splitlines()])
    body = "".join(
        f'<w:p><w:r><w:t xml:space="preserve">{html.escape(text)}</w:t></w:r></w:p>'
        for text in paragraphs
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}<w:sectPr/></w:body></w:document>"
    ).encode("utf-8")
    content_types = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>"""  # noqa: E501
    rels = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>"""  # noqa: E501
    with tempfile.SpooledTemporaryFile(max_size=4 * 1024 * 1024) as output:
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", content_types)
            archive.writestr("_rels/.rels", rels)
            archive.writestr("word/document.xml", document)
        output.seek(0)
        return output.read()


def export_epub(
    project: Project, operations: list[Operation] | None = None, db: Session | None = None
) -> bytes:
    _ = operations, db
    chapters: list[tuple[str, str]] = []
    for volume in project.volumes:
        for chapter in volume.chapters:
            slug = _safe_slug(chapter.id, "chapter")
            paragraphs = "".join(
                f"<p>{html.escape(line)}</p>"
                for line in chapter.content.splitlines()
                if line.strip()
            )
            chapters.append((slug, f"<h1>{html.escape(chapter.title)}</h1>{paragraphs}"))
    manifest_items = "".join(
        f'<item id="{slug}" href="{slug}.xhtml" media-type="application/xhtml+xml"/>'
        for slug, _ in chapters
    )
    spine_items = "".join(f'<itemref idref="{slug}"/>' for slug, _ in chapters)
    nav_items = "".join(
        f'<li><a href="{slug}.xhtml">{html.escape(slug)}</a></li>' for slug, _ in chapters
    )
    opf = f"""<?xml version="1.0" encoding="UTF-8"?><package xmlns="http://www.idpf.org/2007/opf" unique-identifier="bookid" version="3.0"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="bookid">{html.escape(project.id)}</dc:identifier><dc:title>{html.escape(project.name)}</dc:title><dc:language>{html.escape(project.language)}</dc:language></metadata><manifest>{manifest_items}<item id="nav" properties="nav" href="nav.xhtml" media-type="application/xhtml+xml"/></manifest><spine>{spine_items}</spine></package>""".encode(  # noqa: E501
        "utf-8"
    )
    nav = f"""<?xml version="1.0" encoding="UTF-8"?><html xmlns="http://www.w3.org/1999/xhtml"><head><title>{html.escape(project.name)}</title></head><body><nav epub:type="toc" xmlns:epub="http://www.idpf.org/2007/ops"><ol>{nav_items}</ol></nav></body></html>""".encode(  # noqa: E501
        "utf-8"
    )
    container = b"""<?xml version="1.0" encoding="UTF-8"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/package.opf" media-type="application/oebps-package+xml"/></rootfiles></container>"""  # noqa: E501
    with tempfile.SpooledTemporaryFile(max_size=4 * 1024 * 1024) as output:
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
            archive.writestr("META-INF/container.xml", container)
            archive.writestr("OEBPS/package.opf", opf)
            archive.writestr("OEBPS/nav.xhtml", nav)
            for slug, body in chapters:
                archive.writestr(
                    f"OEBPS/{slug}.xhtml",
                    f'<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml"><head><title>{html.escape(slug)}</title></head><body>{body}</body></html>',  # noqa: E501
                )
        output.seek(0)
        return output.read()


def _required(value: Any, name: str, kind: type | tuple[type, ...] = str) -> Any:
    if not isinstance(value, kind):
        raise HTTPException(422, detail={"code": "invalid_import", "message": f"{name} is invalid"})
    return value


def validate_document(document: Any) -> dict[str, Any]:
    if (
        not isinstance(document, dict)
        or document.get("schema_version") not in SUPPORTED_SCHEMA_VERSIONS
    ):
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
    migrate_document(document)
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


def migrate_document(document: dict[str, Any]) -> dict[str, Any]:
    """Upgrade portable documents in memory before validation/import."""
    version = document.get("schema_version")
    if version == "1.0":
        project = document.setdefault("project", {})
        project.setdefault("story_graph", {})
        project["story_graph"].setdefault("entity_sources", [])
        project["story_graph"].setdefault("entity_revisions", [])
        project["story_graph"].setdefault("timeline_events", [])
        project["story_graph"].setdefault("story_branches", [])
        project["story_graph"].setdefault("foreshadows", [])
        project["story_graph"].setdefault("foreshadow_links", [])
        for entity in project.get("entities", []):
            entity.setdefault("tags", [])
        document["schema_version"] = SCHEMA_VERSION
    project = document.setdefault("project", {})
    project.setdefault("story_graph", {})
    for key in (
        "entity_sources",
        "entity_revisions",
        "timeline_events",
        "story_branches",
        "foreshadows",
        "foreshadow_links",
    ):
        project["story_graph"].setdefault(key, [])
    return document


def _markdown_document(raw: dict[str, bytes]) -> dict[str, Any]:
    project_file = next(
        (value for name, value in raw.items() if name.lower().endswith("project.md")), b""
    )
    project_text = project_file.decode("utf-8", errors="replace")
    heading = re.search(r"^#\s+(.+)$", project_text, re.MULTILINE)
    name = heading.group(1).strip() if heading else "导入作品"
    volumes: dict[str, dict[str, Any]] = {}
    entities: list[dict[str, Any]] = []
    notes: list[dict[str, Any]] = []
    for path, content in sorted(raw.items()):
        if not path.lower().endswith(".md") or path.lower().endswith("project.md"):
            continue
        parts = Path(path).parts
        text = content.decode("utf-8", errors="replace")
        title_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else Path(path).stem
        body = re.sub(r"^#\s+.+?\n+", "", text, count=1, flags=re.MULTILINE).strip()
        if parts[0].lower() == "entities":
            entities.append(
                {
                    "name": title,
                    "kind": "other",
                    "description": body,
                    "aliases": [],
                    "attributes": {},
                    "tags": [],
                }
            )
        elif parts[0].lower() == "notes":
            notes.append({"title": title, "content": body, "tags": []})
        else:
            volume_title = parts[-2] if len(parts) > 1 else "导入内容"
            volume = volumes.setdefault(
                volume_title, {"title": volume_title, "position": len(volumes), "chapters": []}
            )
            volume["chapters"].append(
                {
                    "title": title,
                    "position": len(volume["chapters"]),
                    "content": body,
                    "status": "draft",
                    "revisions": [],
                }
            )
    document = {
        "schema_version": SCHEMA_VERSION,
        "project": {
            "name": name,
            "description": "",
            "language": "zh-CN",
            "status": "active",
            "volumes": list(volumes.values()),
            "entities": entities,
            "notes": notes,
            "operations": [],
            "story_graph": {},
        },
    }
    return migrate_document(document)


def decode_import_bytes(
    raw: bytes, filename: str | None = None, content_type: str | None = None
) -> dict[str, Any]:
    if (filename and filename.lower().endswith(".md")) or content_type == "text/markdown":
        return _markdown_document({filename or "chapter.md": raw})
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
                if MANIFEST_NAME not in names:
                    raise HTTPException(
                        422,
                        detail={
                            "code": "invalid_package",
                            "message": "manifest.json is required",
                        },
                    )
                if any(name.startswith("/") or ".." in Path(name).parts for name in names):
                    raise HTTPException(
                        422, detail={"code": "invalid_package", "message": "unsafe archive path"}
                    )
                try:
                    manifest = json.loads(archive.read(MANIFEST_NAME).decode("utf-8"))
                    imported_document = (
                        json.loads(archive.read(DATA_NAME).decode("utf-8"))
                        if DATA_NAME in names
                        else None
                    )
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise HTTPException(
                        422,
                        detail={"code": "invalid_package", "message": "package JSON is invalid"},
                    ) from exc
                if manifest.get("format") == "novel-workbench-markdown":
                    files = {
                        name: archive.read(name) for name in names if name.lower().endswith(".md")
                    }
                    checksums = manifest.get("files", {})
                    for name, expected in checksums.items():
                        if name not in files:
                            raise HTTPException(
                                422,
                                detail={"code": "missing_file", "message": f"missing file: {name}"},
                            )
                        if hashlib.sha256(files[name]).hexdigest() != expected:
                            raise HTTPException(
                                422,
                                detail={
                                    "code": "checksum_mismatch",
                                    "message": f"checksum mismatch: {name}",
                                },
                            )
                    return _markdown_document(files)
                if DATA_NAME not in names:
                    raise HTTPException(
                        422,
                        detail={"code": "invalid_package", "message": "project.json is required"},
                    )
                if (
                    manifest.get("schema_version") not in SUPPORTED_SCHEMA_VERSIONS
                    or manifest.get("data") != DATA_NAME
                ):
                    raise HTTPException(
                        422,
                        detail={
                            "code": "unsupported_schema",
                            "message": "invalid package manifest",
                        },
                    )
                for name, expected in manifest.get("files", {}).items():
                    if name not in names:
                        raise HTTPException(
                            422, detail={"code": "missing_file", "message": f"missing file: {name}"}
                        )
                    if (
                        name == DATA_NAME
                        and hashlib.sha256(archive.read(name)).hexdigest() != expected
                    ):
                        raise HTTPException(
                            422,
                            detail={
                                "code": "checksum_mismatch",
                                "message": f"checksum mismatch: {name}",
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
    db.flush()
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
                tags=entity_raw.get("tags", []),
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
                target_version_hash=operation_raw.get("target_version_hash"),
                diff=operation_raw.get("diff", {}),
                permission=operation_raw.get("permission", "approval_required"),
                undo_operation_id=None,
            )
        )
    graph = raw.get("story_graph", {})
    graph_id_map = id_map
    for item in graph.get("entity_sources", []):
        entity_id = graph_id_map.get(item.get("entity_id"))
        chapter_id = graph_id_map.get(item.get("chapter_id"))
        if entity_id and chapter_id:
            db.add(
                EntitySourceLink(
                    project_id=project_id,
                    entity_id=entity_id,
                    chapter_id=chapter_id,
                    evidence=item.get("evidence", ""),
                    created_at=_parse_datetime(item.get("created_at"), now),
                )
            )
    for item in graph.get("entity_revisions", []):
        entity_id = graph_id_map.get(item.get("entity_id"))
        if entity_id:
            db.add(
                EntityRevision(
                    project_id=project_id,
                    entity_id=entity_id,
                    snapshot=item.get("snapshot", {}),
                    source=item.get("source", "user"),
                    operation_id=None,
                    created_at=_parse_datetime(item.get("created_at"), now),
                )
            )
    for item in graph.get("timeline_events", []):
        db.add(
            TimelineEvent(
                project_id=project_id,
                title=item.get("title", "事件"),
                description=item.get("description", ""),
                absolute_time=item.get("absolute_time"),
                relative_order=item.get("relative_order"),
                time_status=item.get("time_status", "unknown"),
                chapter_ids=[
                    graph_id_map.get(value, value) for value in item.get("chapter_ids", [])
                ],
                entity_ids=[graph_id_map.get(value, value) for value in item.get("entity_ids", [])],
                created_at=_parse_datetime(item.get("created_at"), now),
                updated_at=_parse_datetime(item.get("updated_at"), now),
            )
        )
    branch_map: dict[str, str] = {}
    for index, item in enumerate(graph.get("story_branches", [])):
        old_id = item.get("id") or f"__branch_{index}"
        branch_map[old_id] = str(uuid4())
    for index, item in enumerate(graph.get("story_branches", [])):
        old_id = item.get("id") or f"__branch_{index}"
        db.add(
            StoryBranch(
                id=branch_map[old_id],
                project_id=project_id,
                parent_id=branch_map.get(item.get("parent_id")),
                name=item.get("name", "分支"),
                trigger_condition=item.get("trigger_condition", ""),
                chapter_ids=[
                    graph_id_map.get(value, value) for value in item.get("chapter_ids", [])
                ],
                status=item.get("status", "active"),
                created_at=_parse_datetime(item.get("created_at"), now),
                updated_at=_parse_datetime(item.get("updated_at"), now),
            )
        )
    foreshadow_map: dict[str, str] = {}
    for item in graph.get("foreshadows", []):
        new_foreshadow_id = str(uuid4())
        foreshadow_map[item.get("id", new_foreshadow_id)] = new_foreshadow_id
        db.add(
            Foreshadow(
                project_id=project_id,
                id=new_foreshadow_id,
                title=item.get("title", "伏笔"),
                description=item.get("description", ""),
                status=item.get("status", "draft"),
                planted_chapter_ids=[
                    graph_id_map.get(value, value) for value in item.get("planted_chapter_ids", [])
                ],
                resolved_chapter_ids=[
                    graph_id_map.get(value, value) for value in item.get("resolved_chapter_ids", [])
                ],
                created_at=_parse_datetime(item.get("created_at"), now),
                updated_at=_parse_datetime(item.get("updated_at"), now),
            )
        )
    for item in graph.get("foreshadow_links", []):
        foreshadow_id = foreshadow_map.get(item.get("foreshadow_id"))
        source_id = graph_id_map.get(item.get("source_id"), item.get("source_id"))
        if foreshadow_id and source_id:
            db.add(
                ForeshadowLink(
                    project_id=project_id,
                    foreshadow_id=foreshadow_id,
                    source_type=item.get("source_type", "chapter"),
                    source_id=source_id,
                    evidence=item.get("evidence", ""),
                    link_kind=item.get("link_kind", "evidence"),
                    created_at=_parse_datetime(item.get("created_at"), now),
                )
            )
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(project)
    return project
