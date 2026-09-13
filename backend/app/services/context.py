from __future__ import annotations

import hashlib
import json
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.domain import Chapter, Entity, Note, Project


def _tokens(value: str) -> int:
    return max(1, len(value) // 4) if value else 0


def _fragment(
    *,
    source: str,
    source_ids: list[str],
    priority: int,
    title: str,
    content: str,
    truncatable: bool,
) -> dict[str, Any]:
    return {
        "source": source,
        "source_ids": source_ids,
        "priority": priority,
        "title": title,
        "content": content,
        "token_count": _tokens(content),
        "truncatable": truncatable,
        "truncated": False,
        "truncation_reason": None,
    }


def build_context_package(
    db: Session,
    *,
    project_id: str,
    user_instruction: str | None = None,
    chapter_id: str | None = None,
    selected_text: str | None = None,
    search_query: str | None = None,
    search_limit: int = 8,
    system_prompt: str | None = None,
    budget_tokens: int = 6000,
) -> dict[str, Any]:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(
            404, detail={"code": "project_not_found", "message": "project not found"}
        )
    fragments: list[dict[str, Any]] = []
    if user_instruction:
        fragments.append(
            _fragment(
                source="user_instruction",
                source_ids=[],
                priority=100,
                title="用户指令",
                content=user_instruction,
                truncatable=False,
            )
        )
    if selected_text:
        fragments.append(
            _fragment(
                source="selected_text",
                source_ids=[chapter_id] if chapter_id else [],
                priority=95,
                title="当前选区",
                content=selected_text,
                truncatable=True,
            )
        )
    chapter = db.get(Chapter, chapter_id) if chapter_id else None
    if chapter:
        if chapter.volume.project_id != project_id:
            raise HTTPException(
                400,
                detail={"code": "invalid_chapter", "message": "chapter does not belong to project"},
            )
        fragments.append(
            _fragment(
                source="chapter",
                source_ids=[chapter.id],
                priority=90,
                title=f"当前章节：{chapter.title}",
                content=chapter.content,
                truncatable=True,
            )
        )
    if system_prompt:
        fragments.append(
            _fragment(
                source="project_rules",
                source_ids=[],
                priority=80,
                title="系统规则快照",
                content=system_prompt,
                truncatable=False,
            )
        )
    if project.description:
        fragments.append(
            _fragment(
                source="project",
                source_ids=[project.id],
                priority=75,
                title=f"作品：{project.name}",
                content=project.description,
                truncatable=True,
            )
        )
    entities = list(
        db.scalars(
            select(Entity)
            .where(Entity.project_id == project_id)
            .order_by(Entity.name, Entity.id)
            .limit(50)
        )
    )
    for entity in entities:
        attributes = json.dumps(entity.attributes or {}, ensure_ascii=False, sort_keys=True)
        content = (
            f"名称：{entity.name}\n类型：{entity.kind}\n"
            f"别名：{', '.join(entity.aliases or [])}\n"
            f"描述：{entity.description}\n属性：{attributes}"
        )
        fragments.append(
            _fragment(
                source="entity",
                source_ids=[entity.id],
                priority=60,
                title=f"实体：{entity.name}",
                content=content,
                truncatable=True,
            )
        )
    notes = list(
        db.scalars(
            select(Note)
            .where(Note.project_id == project_id)
            .order_by(Note.updated_at.desc(), Note.id)
            .limit(20)
        )
    )
    for note in notes:
        fragments.append(
            _fragment(
                source="note",
                source_ids=[note.id],
                priority=40,
                title=f"资料笔记：{note.title}",
                content=note.content,
                truncatable=True,
            )
        )

    if search_query:
        from app.services.search import search_project

        retrieval = search_project(db, project_id, search_query, limit=search_limit)
        for hit in retrieval["items"]:
            fragments.append(
                _fragment(
                    source="search_result",
                    source_ids=[hit["source_id"]],
                    priority=30,
                    title=f"检索：{hit['title']}",
                    content=hit["highlight"] or hit["snippet"],
                    truncatable=True,
                )
            )

    fragments.sort(key=lambda item: (-item["priority"], item["title"], item["source_ids"]))
    remaining = budget_tokens
    included: list[dict[str, Any]] = []
    truncated_count = 0
    over_budget = False
    for item in fragments:
        needed = item["token_count"]
        if needed <= remaining:
            remaining -= needed
            included.append(item)
            continue
        if not item["truncatable"]:
            included.append(item)
            remaining = 0
            over_budget = True
            continue
        if item["truncatable"] and remaining > 0:
            limit = remaining * 4
            item["content"] = item["content"][:limit]
            item["content"] += "\n[片段因预算被截断]"
            item["token_count"] = _tokens(item["content"])
            item["truncated"] = True
            item["truncation_reason"] = "context_budget"
            included.append(item)
            truncated_count += 1
            remaining = 0
        else:
            item["truncated"] = True
            item["truncation_reason"] = "context_budget"
            truncated_count += 1

    used_tokens = sum(item["token_count"] for item in included)
    package = {
        "version": 1,
        "budget_tokens": budget_tokens,
        "used_tokens": used_tokens,
        "over_budget": over_budget,
        "truncated_count": truncated_count,
        "fragments": included,
    }
    digest = hashlib.sha256(
        json.dumps(package, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    package["digest"] = digest
    return package


def context_text(package: dict[str, Any]) -> str:
    sections = []
    for fragment in package.get("fragments", []):
        if fragment.get("source") == "project_rules":
            continue
        sections.append(f"[{fragment['title']}]\n{fragment['content']}")
    return "\n\n".join(sections)


def tool_read_chapter(db: Session, project_id: str, chapter_id: str) -> dict[str, Any]:
    chapter = db.get(Chapter, chapter_id)
    if not chapter or chapter.volume.project_id != project_id:
        return {
            "success": False,
            "error_code": "chapter_not_found",
            "message": "chapter not found",
            "source_ids": [],
        }
    return {
        "success": True,
        "source_ids": [chapter.id],
        "data": {
            "id": chapter.id,
            "title": chapter.title,
            "content": chapter.content,
            "status": chapter.status,
        },
    }


def tool_search_project(db: Session, project_id: str, query: str, limit: int) -> dict[str, Any]:
    from app.services.search import search_project

    result = search_project(db, project_id, query, limit=limit)
    return {
        "success": True,
        "source_ids": [item["source_id"] for item in result["items"]],
        "data": result,
    }


def tool_read_entity(db: Session, project_id: str, entity_id: str) -> dict[str, Any]:
    entity = db.get(Entity, entity_id)
    if not entity or entity.project_id != project_id:
        return {
            "success": False,
            "error_code": "entity_not_found",
            "message": "entity not found",
            "source_ids": [],
        }
    return {
        "success": True,
        "source_ids": [entity.id],
        "data": {
            "id": entity.id,
            "kind": entity.kind,
            "name": entity.name,
            "aliases": entity.aliases,
            "description": entity.description,
            "attributes": entity.attributes,
        },
    }


def tool_create_note(
    db: Session, project_id: str, title: str, content: str, tags: list[str]
) -> dict[str, Any]:
    if not db.get(Project, project_id):
        return {
            "success": False,
            "error_code": "project_not_found",
            "message": "project not found",
            "source_ids": [],
        }
    note = Note(project_id=project_id, title=title, content=content, tags=tags)
    db.add(note)
    db.commit()
    db.refresh(note)
    return {"success": True, "source_ids": [note.id], "data": {"id": note.id, "title": note.title}}


def tool_propose_operation(
    db: Session,
    project_id: str,
    chapter_id: str,
    operation_type: str,
    payload: dict[str, Any],
    old_hash: str | None,
) -> dict[str, Any]:
    from app.schemas.domain import OperationCreate
    from app.services.domain import create_operation

    try:
        operation = create_operation(
            db,
            OperationCreate(
                project_id=project_id,
                target_id=chapter_id,
                type=operation_type,
                payload=payload,
                old_hash=old_hash,
                source="ai",
            ),
        )
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        return {
            "success": False,
            "error_code": detail.get("code", "operation_error"),
            "message": str(detail.get("message", exc.detail)),
            "source_ids": [chapter_id],
        }
    return {
        "success": True,
        "source_ids": [operation.id, chapter_id],
        "data": {
            "operation_id": operation.id,
            "status": operation.status,
            "type": operation.type,
            "payload": operation.payload,
        },
    }


def tool_update_entity(
    db: Session, project_id: str, entity_id: str, changes: dict[str, Any]
) -> dict[str, Any]:
    entity = db.get(Entity, entity_id)
    if not entity or entity.project_id != project_id:
        return {
            "success": False,
            "error_code": "entity_not_found",
            "message": "entity not found",
            "source_ids": [],
        }
    allowed = {"name", "description", "aliases", "attributes", "status"}
    if not set(changes).issubset(allowed):
        return {
            "success": False,
            "error_code": "invalid_entity_changes",
            "message": "unsupported entity fields",
            "source_ids": [entity_id],
        }
    from app.schemas.domain import OperationCreate
    from app.services.domain import create_operation

    try:
        operation = create_operation(
            db,
            OperationCreate(
                project_id=project_id,
                target_type="entity",
                target_id=entity_id,
                type="update_entity",
                payload={"changes": changes},
                source="ai",
            ),
        )
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        return {
            "success": False,
            "error_code": detail.get("code", "operation_error"),
            "message": str(detail.get("message", exc.detail)),
            "source_ids": [entity_id],
        }
    return {
        "success": True,
        "source_ids": [entity_id, operation.id],
        "data": {
            "requires_approval": True,
            "operation_id": operation.id,
            "status": operation.status,
            "operation": operation.payload,
        },
    }
