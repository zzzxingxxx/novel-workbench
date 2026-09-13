from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.domain import Chapter, Foreshadow, Job, Volume


def _now() -> datetime:
    return datetime.now(timezone.utc)


def chapter_metrics(chapter: Chapter) -> dict[str, Any]:
    text = chapter.content or ""
    sentences = [s for s in re.split(r"[。！？!?\\n]+", text) if s.strip()]
    dialogue = len(re.findall(r"[“\"「『].*?[”\"」』]", text, re.S))
    words = len(text)
    phrases = re.findall(r"[\u4e00-\u9fff]{4,8}", text)
    counts: dict[str, int] = {}
    for phrase in phrases:
        counts[phrase] = counts.get(phrase, 0) + 1
    return {
        "chapter_id": chapter.id,
        "title": chapter.title,
        "words": words,
        "sentences": len(sentences),
        "dialogue_ratio": round(dialogue / max(words, 1), 4),
        "scene_count": max(1, len(re.findall(r"(?:场景|地点|\n\n)", text))),
        "repeated_phrases": sorted(
            (k for k, v in counts.items() if v > 1), key=lambda x: (-counts[x], x)
        )[:20],
    }


def analyze_project(
    db: Session, project_id: str, chapter_ids: list[str] | None = None
) -> dict[str, Any]:
    query = select(Chapter).join(Volume).where(Volume.project_id == project_id)
    chapters = list(db.scalars(query.order_by(Volume.position, Chapter.position)))
    if chapter_ids:
        chapters = [c for c in chapters if c.id in chapter_ids]
    metrics = [chapter_metrics(c) for c in chapters]
    foreshadows = list(db.scalars(select(Foreshadow).where(Foreshadow.project_id == project_id)))
    resolved = sum(1 for item in foreshadows if item.status == "resolved")
    return {
        "chapters": metrics,
        "totals": {
            "chapters": len(metrics),
            "words": sum(m["words"] for m in metrics),
            "average_words": round(sum(m["words"] for m in metrics) / max(len(metrics), 1)),
            "foreshadow_count": len(foreshadows),
            "foreshadow_resolution_rate": round(resolved / max(len(foreshadows), 1), 4),
            "unresolved_questions": sum(
                1 for item in foreshadows if item.status in {"planted", "developing"}
            ),
        },
    }


def review_project(
    db: Session, project_id: str, chapter_ids: list[str] | None = None
) -> dict[str, Any]:
    analysis = analyze_project(db, project_id, chapter_ids)
    issues: list[dict[str, Any]] = []
    for chapter in analysis["chapters"]:
        if chapter["words"] == 0:
            issues.append(
                {
                    "severity": "warning",
                    "code": "empty_chapter",
                    "chapter_id": chapter["chapter_id"],
                    "evidence": "章节没有正文",
                }
            )
        if chapter["dialogue_ratio"] > 0.65:
            issues.append(
                {
                    "severity": "info",
                    "code": "dialogue_heavy",
                    "chapter_id": chapter["chapter_id"],
                    "evidence": f"对话比例 {chapter['dialogue_ratio']:.0%}",
                }
            )
        for phrase in chapter["repeated_phrases"][:5]:
            issues.append(
                {
                    "severity": "info",
                    "code": "repeated_phrase",
                    "chapter_id": chapter["chapter_id"],
                    "evidence": phrase,
                }
            )
    return {"issues": issues, "analysis": analysis, "automatically_modified": False}


def run_job(db: Session, job: Job) -> Job:
    job.status = "running"
    job.progress = {"completed": 0, "total": 1}
    db.commit()
    try:
        ids = job.input_snapshot.get("chapter_ids")
        if job.job_type == "analysis":
            result = analyze_project(db, job.project_id, ids)
        elif job.job_type == "batch_review":
            result = review_project(db, job.project_id, ids)
        else:
            from app.services.search import rebuild_project_index

            result = rebuild_project_index(db, job.project_id)
        job.output = result
        job.progress = {"completed": 1, "total": 1}
        job.status = "completed"
        job.completed_at = _now()
    except Exception as exc:
        job.status = "failed"
        job.error = str(exc)[:500]
    db.commit()
    db.refresh(job)
    return job
