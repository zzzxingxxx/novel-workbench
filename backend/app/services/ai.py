from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any, Protocol

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import SessionLocal
from app.models.domain import AiEvent, AiMessage, AiSession, Chapter, Provider, new_id
from app.services.context import build_context_package, context_text
from app.services.prompts import build_prompt


class ChatProvider(Protocol):
    async def stream(self, messages: list[dict[str, str]], model: str) -> AsyncIterator[str]: ...

    async def test(self, model: str) -> dict[str, Any]: ...


_cancel_events: dict[str, asyncio.Event] = {}
_session_loops: dict[str, asyncio.AbstractEventLoop] = {}
_tasks: set[asyncio.Task[None]] = set()


def schedule_message(
    session_id: str, message_id: str, chapter_id: str | None, selected_text: str | None
) -> None:
    task = asyncio.create_task(run_message(session_id, message_id, chapter_id, selected_text))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


def _secret() -> bytes:
    import hashlib

    value = settings.provider_secret or f"{settings.app_name}:{settings.database_url}"
    return hashlib.sha256(value.encode("utf-8")).digest()


def _fernet() -> Fernet:
    import base64

    return Fernet(base64.urlsafe_b64encode(_secret()))


def encrypt_api_key(value: str | None) -> str | None:
    if not value:
        return None
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_api_key(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError, ValueError):
        return None


class OpenAICompatibleProvider:
    def __init__(self, provider: Provider):
        self.provider = provider
        self.base_url = provider.base_url.rstrip("/")
        self.api_key = decrypt_api_key(provider.api_key_encrypted)

    async def stream(self, messages: list[dict[str, str]], model: str) -> AsyncIterator[str]:
        if self.base_url.startswith("mock://"):
            prompt = messages[-1]["content"] if messages else ""
            response = (
                "我会先保留这一段的叙事节奏，再让角色通过一个具体动作暴露新的信息。"
                if "检查" in prompt or "改写" not in prompt
                else "雾里的灯又亮了一次。林默没有回头，只把那封信折进外套内袋。"
            )
            for chunk in response:
                await asyncio.sleep(0.005)
                yield chunk
            return

        headers = {"Accept": "text/event-stream", "Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {"model": model, "messages": messages, "stream": True}
        timeout = httpx.Timeout(self.provider.timeout_seconds, connect=15.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST", f"{self.base_url}/chat/completions", headers=headers, json=payload
            ) as response:
                if response.status_code >= 400:
                    detail = (await response.aread())[:500].decode("utf-8", errors="replace")
                    raise RuntimeError(f"provider returned {response.status_code}: {detail}")
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        event = json.loads(data)
                        delta = event.get("choices", [{}])[0].get("delta", {}).get("content")
                    except (IndexError, json.JSONDecodeError, TypeError) as exc:
                        raise RuntimeError("provider returned invalid streaming JSON") from exc
                    if isinstance(delta, str) and delta:
                        yield delta

    async def test(self, model: str) -> dict[str, Any]:
        started = time.perf_counter()
        first = ""
        async for chunk in self.stream([{"role": "user", "content": "ping"}], model):
            first = chunk
            break
        return {
            "ok": True,
            "model": model,
            "first_delta": first,
            "latency_ms": round((time.perf_counter() - started) * 1000),
        }


def provider_for(provider: Provider) -> ChatProvider:
    if provider.kind != "openai_compatible":
        raise HTTPException(422, detail={"code": "unsupported_provider", "message": provider.kind})
    return OpenAICompatibleProvider(provider)


def session_or_404(db: Session, session_id: str) -> AiSession:
    session = db.get(AiSession, session_id)
    if not session:
        raise HTTPException(
            404, detail={"code": "session_not_found", "message": "AI session not found"}
        )
    return session


def append_event(db: Session, session_id: str, event_type: str, data: dict[str, Any]) -> AiEvent:
    last = db.scalar(select(func.max(AiEvent.sequence)).where(AiEvent.session_id == session_id))
    event = AiEvent(
        id=new_id(),
        session_id=session_id,
        sequence=(last or 0) + 1,
        event_type=event_type,
        data=data,
        created_at=datetime.now(timezone.utc),
    )
    db.add(event)
    db.commit()
    return event


def create_session(
    db: Session,
    project_id: str,
    provider_id: str | None,
    model: str | None,
    system_prompt: str | None,
    agent_id: str | None = None,
    workflow_id: str | None = None,
    prompt_variables: dict[str, Any] | None = None,
) -> AiSession:
    from app.services.domain import get_project

    get_project(db, project_id)
    provider = db.get(Provider, provider_id) if provider_id else None
    if provider_id and not provider:
        raise HTTPException(
            404, detail={"code": "provider_not_found", "message": "provider not found"}
        )
    if provider and not provider.enabled:
        raise HTTPException(
            409, detail={"code": "provider_disabled", "message": "provider is disabled"}
        )
    rendered = build_prompt(
        db,
        project_id,
        agent_id=agent_id,
        workflow_id=workflow_id,
        session_prompt=system_prompt,
        variables=prompt_variables or {},
    )
    session = AiSession(
        project_id=project_id,
        provider_id=provider_id,
        model=model or (provider.model if provider else None),
        system_prompt=rendered["prompt"],
        agent_id=agent_id,
        workflow_id=workflow_id,
        prompt_variables=prompt_variables or {},
        prompt_version_ids=rendered["version_ids"],
        prompt_snapshot=rendered["sections"],
        prompt_digest=rendered["digest"],
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def create_message(
    db: Session,
    session: AiSession,
    content: str,
    chapter_id: str | None,
    selected_text: str | None,
    idempotency_key: str | None,
    context_budget: int = 6000,
    search_query: str | None = None,
    search_limit: int = 8,
) -> tuple[AiMessage, bool]:
    if idempotency_key:
        existing = db.scalar(select(AiMessage).where(AiMessage.idempotency_key == idempotency_key))
        if existing:
            if existing.session_id != session.id or existing.content != content:
                raise HTTPException(
                    409,
                    detail={
                        "code": "idempotency_conflict",
                        "message": "idempotency key was already used",
                    },
                )
            return existing, False
    if chapter_id:
        chapter = db.get(Chapter, chapter_id)
        if not chapter or chapter.volume.project_id != session.project_id:
            raise HTTPException(
                400,
                detail={
                    "code": "invalid_chapter",
                    "message": "chapter does not belong to session project",
                },
            )
    message = AiMessage(
        session_id=session.id,
        role="user",
        content=content,
        status="queued",
        idempotency_key=idempotency_key,
        context_budget=context_budget,
        retrieval_query=search_query,
        retrieval_limit=search_limit,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message, True


def cancel_session(db: Session, session_id: str) -> AiSession:
    session = session_or_404(db, session_id)
    session.status = "cancelled"
    db.commit()
    event = _cancel_events.get(session_id)
    if event:
        loop = _session_loops.get(session_id)
        if loop and loop.is_running():
            loop.call_soon_threadsafe(event.set)
        else:
            event.set()
    append_event(db, session_id, "assistant.cancelled", {"reason": "user_requested"})
    return session


async def run_message(
    session_id: str, message_id: str, chapter_id: str | None, selected_text: str | None
) -> None:
    db = SessionLocal()
    cancel_event = asyncio.Event()
    _cancel_events[session_id] = cancel_event
    _session_loops[session_id] = asyncio.get_running_loop()
    try:
        started_at = time.perf_counter()
        session = db.get(AiSession, session_id)
        message = db.get(AiMessage, message_id)
        if not session or not message:
            return
        provider = db.get(Provider, session.provider_id) if session.provider_id else None
        if not provider:
            raise RuntimeError("no provider configured for this session")
        providers = [provider]
        # A deterministic first enabled provider is the documented backup path.
        providers.extend(
            p
            for p in db.scalars(
                select(Provider)
                .where(Provider.enabled, Provider.id != provider.id)
                .order_by(Provider.created_at)
            )
            if p.id != provider.id
        )
        session.status = "running"
        message.status = "streaming"
        db.commit()
        append_event(
            db,
            session_id,
            "session.started",
            {
                "message_id": message_id,
                "model": session.model or provider.model,
                "prompt_version_ids": session.prompt_version_ids,
                "prompt_digest": session.prompt_digest,
            },
        )
        package = build_context_package(
            db,
            project_id=session.project_id,
            user_instruction=message.content,
            chapter_id=chapter_id,
            selected_text=selected_text,
            search_query=message.retrieval_query,
            search_limit=message.retrieval_limit,
            system_prompt=session.system_prompt,
            budget_tokens=message.context_budget,
        )
        message.context_package = package
        message.context_digest = package["digest"]
        message.context_tokens = package["used_tokens"]
        db.commit()
        append_event(
            db,
            session_id,
            "context.ready",
            {
                "chapter_id": chapter_id,
                "selected_text": selected_text,
                "digest": package["digest"],
                "used_tokens": package["used_tokens"],
                "budget_tokens": package["budget_tokens"],
                "truncated_count": package["truncated_count"],
                "fragment_count": len(package["fragments"]),
            },
        )
        prompt = context_text(package)
        messages: list[dict[str, str]] = []
        if session.system_prompt:
            messages.append({"role": "system", "content": session.system_prompt})
        messages.append({"role": "user", "content": prompt})
        chunks: list[str] = []
        last_error: Exception | None = None
        actual_provider = provider
        for candidate in providers:
            try:
                adapter = provider_for(candidate)
                actual_provider = candidate
                async for chunk in adapter.stream(messages, session.model or candidate.model):
                    if cancel_event.is_set() or session.status == "cancelled":
                        return
                    chunks.append(chunk)
                    append_event(
                        db, session_id, "assistant.delta", {"message_id": message_id, "text": chunk}
                    )
                if chunks or candidate is providers[-1]:
                    break
            except Exception as exc:
                last_error = exc
                append_event(
                    db,
                    session_id,
                    "provider.fallback",
                    {"from_provider_id": candidate.id, "reason": str(exc)[:300]},
                )
                continue
        if not chunks and last_error:
            raise last_error
        answer = "".join(chunks)
        message.prompt_tokens = max(1, len(prompt) // 4)
        message.completion_tokens = max(1, len(answer) // 4) if answer else 0
        message.latency_ms = round((time.perf_counter() - started_at) * 1000)
        message.provider_id_used = actual_provider.id
        message.model_used = session.model or actual_provider.model
        assistant_message = AiMessage(
            session_id=session_id,
            role="assistant",
            content=answer,
            status="completed",
            completion_tokens=message.completion_tokens,
            completed_at=datetime.now(timezone.utc),
        )
        db.add(assistant_message)
        message.status = "completed"
        message.completed_at = datetime.now(timezone.utc)
        session.status = "completed"
        db.commit()
        append_event(
            db,
            session_id,
            "assistant.completed",
            {
                "message_id": message_id,
                "content": answer,
                "provider_id": actual_provider.id,
                "model": session.model or actual_provider.model,
            },
        )
        if chapter_id and answer:
            chapter = db.get(Chapter, chapter_id)
            if chapter and chapter.volume.project_id == session.project_id:
                from app.schemas.domain import OperationCreate
                from app.services.domain import create_operation

                if selected_text and selected_text in chapter.content:
                    start = chapter.content.index(selected_text)
                    operation_type = "replace_range"
                    payload = {"from": start, "to": start + len(selected_text), "new_text": answer}
                else:
                    operation_type = "append"
                    payload = {"new_text": answer}
                operation = create_operation(
                    db,
                    OperationCreate(
                        project_id=session.project_id,
                        target_id=chapter.id,
                        type=operation_type,
                        payload=payload,
                        old_hash=chapter.content_hash,
                        source="ai",
                    ),
                )
                append_event(
                    db,
                    session_id,
                    "assistant.operation_preview",
                    {
                        "operation_id": operation.id,
                        "type": operation.type,
                        "target_id": operation.target_id,
                        "payload": operation.payload,
                    },
                )
    except Exception as exc:
        db.rollback()
        session = db.get(AiSession, session_id)
        message = db.get(AiMessage, message_id)
        if session:
            session.status = "failed"
        if message:
            message.status = "failed"
            message.completed_at = datetime.now(timezone.utc)
        db.commit()
        append_event(
            db,
            session_id,
            "assistant.failed",
            {"message_id": message_id, "code": "provider_error", "message": str(exc)[:500]},
        )
    finally:
        _cancel_events.pop(session_id, None)
        _session_loops.pop(session_id, None)
        db.close()
