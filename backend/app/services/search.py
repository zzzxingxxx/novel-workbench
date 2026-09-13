from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.models.domain import Chapter, Entity, Note, Volume

INDEX_VERSION = "fts5-v1"
_HAN = re.compile(r"[\u4e00-\u9fff]+")
_PARTS = re.compile(r"[\u4e00-\u9fff]+|[a-zA-Z0-9_]+")


def ensure_search_index(db: Session) -> None:
    db.execute(
        text(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS search_index_fts USING fts5(
                project_id UNINDEXED,
                source_type UNINDEXED,
                source_id UNINDEXED,
                volume_id UNINDEXED,
                chapter_id UNINDEXED,
                title,
                body,
                aliases,
                tags,
                tokenize='unicode61'
            )
            """
        )
    )
    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS search_index_meta (
                project_id TEXT PRIMARY KEY,
                source_stamp TEXT NOT NULL,
                indexed_at TEXT NOT NULL
            )
            """
        )
    )


def _project_stamp(db: Session, project_id: str) -> str:
    values: list[str] = []
    for model in (Chapter, Entity, Note):
        if model is Chapter:
            query = (
                db.query(func.count(Chapter.id), func.max(Chapter.updated_at))
                .join(Volume, Chapter.volume_id == Volume.id)
                .filter(Volume.project_id == project_id)
            )
        else:
            query = db.query(func.count(model.id), func.max(model.updated_at)).filter(
                model.project_id == project_id
            )
        count, updated = query.one()
        values.extend([str(count or 0), updated.isoformat() if updated else ""])
    return "|".join(values)


def _tokens(value: str) -> list[str]:
    result: list[str] = []
    for part in _PARTS.findall(value.lower()):
        if _HAN.fullmatch(part):
            result.extend(part)
            if len(part) > 1:
                result.extend(part[index : index + 2] for index in range(len(part) - 1))
        else:
            result.append(part)
    return result


def _search_text(*values: str) -> str:
    return " ".join(_tokens(" ".join(value for value in values if value)))


def _query(value: str) -> str:
    tokens = _tokens(value)
    if not tokens:
        raise HTTPException(
            422, detail={"code": "empty_search_query", "message": "query is required"}
        )
    return " AND ".join(f'"{token.replace(chr(34), "")}"' for token in dict.fromkeys(tokens))


def _clear_project(db: Session, project_id: str) -> None:
    db.execute(
        text("DELETE FROM search_index_fts WHERE project_id = :project_id"),
        {"project_id": project_id},
    )


def _insert(
    db: Session,
    project_id: str,
    source_type: str,
    source_id: str,
    volume_id: str | None,
    chapter_id: str | None,
    title: str,
    body: str,
    aliases: str = "",
    tags: str = "",
) -> None:
    db.execute(
        text(
            """
            INSERT INTO search_index_fts
                (project_id, source_type, source_id, volume_id, chapter_id,
                 title, body, aliases, tags)
            VALUES (:project_id, :source_type, :source_id, :volume_id, :chapter_id,
                    :title, :body, :aliases, :tags)
            """
        ),
        {
            "project_id": project_id,
            "source_type": source_type,
            "source_id": source_id,
            "volume_id": volume_id,
            "chapter_id": chapter_id,
            "title": title,
            "body": _search_text(title, body),
            "aliases": _search_text(aliases),
            "tags": _search_text(tags),
        },
    )


def rebuild_project_index(db: Session, project_id: str) -> dict[str, Any]:
    ensure_search_index(db)
    _clear_project(db, project_id)
    chapters = list(
        db.query(Chapter, Volume)
        .join(Volume, Chapter.volume_id == Volume.id)
        .filter(Volume.project_id == project_id)
        .all()
    )
    for chapter, volume in chapters:
        _insert(
            db,
            project_id,
            "chapter",
            chapter.id,
            volume.id,
            chapter.id,
            chapter.title,
            chapter.content,
        )
    entities = db.query(Entity).filter(Entity.project_id == project_id).all()
    for entity in entities:
        _insert(
            db,
            project_id,
            "entity",
            entity.id,
            None,
            None,
            entity.name,
            entity.description,
            ",".join(entity.aliases or []),
        )
    notes = db.query(Note).filter(Note.project_id == project_id).all()
    for note in notes:
        _insert(
            db,
            project_id,
            "note",
            note.id,
            None,
            None,
            note.title,
            note.content,
            tags=", ".join(note.tags or []),
        )
    db.commit()
    db.execute(
        text(
            """
            INSERT INTO search_index_meta(project_id, source_stamp, indexed_at)
            VALUES (:project_id, :source_stamp, :indexed_at)
            ON CONFLICT(project_id) DO UPDATE SET
                source_stamp = excluded.source_stamp,
                indexed_at = excluded.indexed_at
            """
        ),
        {
            "project_id": project_id,
            "source_stamp": _project_stamp(db, project_id),
            "indexed_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    db.commit()
    return {"project_id": project_id, "document_count": len(chapters) + len(entities) + len(notes)}


def search_project(
    db: Session,
    project_id: str,
    query: str,
    limit: int = 20,
    source_type: str | None = None,
    volume_id: str | None = None,
) -> dict[str, Any]:
    ensure_search_index(db)
    stamp = _project_stamp(db, project_id)
    indexed = db.execute(
        text("SELECT source_stamp FROM search_index_meta WHERE project_id = :project_id"),
        {"project_id": project_id},
    ).scalar_one_or_none()
    if indexed != stamp:
        rebuild_project_index(db, project_id)
    conditions = ["project_id = :project_id"]
    params: dict[str, Any] = {
        "project_id": project_id,
        "match_query": _query(query),
        "limit": limit,
    }
    if source_type:
        if source_type not in {"chapter", "entity", "note"}:
            raise HTTPException(
                422,
                detail={
                    "code": "invalid_source_type",
                    "message": "source_type must be chapter, entity or note",
                },
            )
        conditions.append("source_type = :source_type")
        params["source_type"] = source_type
    if volume_id:
        conditions.append("volume_id = :volume_id")
        params["volume_id"] = volume_id
    where = " AND ".join(conditions)
    rows = db.execute(
        text(
            f"""
            SELECT rowid, project_id, source_type, source_id, volume_id, chapter_id,
                   title, body, bm25(search_index_fts) AS rank,
                   snippet(search_index_fts, 6, '<mark>', '</mark>', '...', 28) AS snippet
            FROM search_index_fts
            WHERE search_index_fts MATCH :match_query AND {where}
            ORDER BY rank, source_type, title, source_id
            LIMIT :limit
            """
        ),
        params,
    ).mappings()
    items = []
    for row in rows:
        source_id = row["source_id"]
        original = ""
        if row["source_type"] == "chapter":
            original = db.get(Chapter, source_id).content
        elif row["source_type"] == "entity":
            entity = db.get(Entity, source_id)
            original = entity.description if entity else ""
        else:
            note = db.get(Note, source_id)
            original = note.content if note else ""
        offset = original.lower().find(query.lower()) if original else -1
        items.append(
            {
                "source_type": row["source_type"],
                "source_id": source_id,
                "project_id": row["project_id"],
                "volume_id": row["volume_id"],
                "chapter_id": row["chapter_id"],
                "title": row["title"],
                "snippet": row["snippet"],
                "highlight": row["snippet"],
                "score": round(float(-row["rank"]), 6),
                "match_start": offset,
                "match_end": offset + len(query) if offset >= 0 else None,
                "index_version": INDEX_VERSION,
                "citation": {
                    "source_id": source_id,
                    "source_type": row["source_type"],
                    "paragraph": (original[:offset].count("\n") + 1) if offset >= 0 else None,
                },
            }
        )
    return {
        "query": query,
        "project_id": project_id,
        "items": items,
        "total": len(items),
        "index_version": INDEX_VERSION,
        "searched_at": datetime.now(timezone.utc).isoformat(),
    }
