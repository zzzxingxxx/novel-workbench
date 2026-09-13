# Novel Workbench

Windows-first local AI long-form writing workspace.

## Current scope

This initial implementation covers project initialization and the first domain/database slice:

- FastAPI local REST API
- SQLite with WAL mode and foreign keys
- SQLAlchemy 2 models and Alembic migrations
- Projects, volumes, chapters, revisions, entities, notes, and operations
- Optimistic `old_hash` protection for chapter edits
- Preview, approve, reject, and restore flows for operations
- JSON and ZIP project backup/export with schema validation and transactional import
- Optional paginated list responses (`?page=1&page_size=20`) with stable ordering
- Unified error responses (`{"error": {"code", "message", "details"}}`)

## Development

```powershell
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

The API is available at `http://127.0.0.1:8000/docs`.

Run tests:

```powershell
cd backend
uv run pytest
```

The default database is `backend/data/novel_workbench.db`. Set `NOVEL_WORKBENCH_DATABASE_URL` to use another SQLite path.

## Stage 1 API notes

List endpoints keep the original array response when no `page` query is supplied. Add `page`
(1-based) and optional `page_size` (1-100) to receive an object with `items` and `meta`.
Supported paginated resources are projects, project volumes, volume chapters, project entities,
and project notes. Sorting is deterministic: projects and notes by newest creation time, volumes
and chapters by position, and entities by name.

Export a project with `GET /api/v1/projects/{project_id}/export?format=json` or `format=zip`.
The ZIP contains `manifest.json` and `project.json` (with a reserved `attachments/` area).
Import the returned bytes with `POST /api/v1/projects/import` using `application/json` or
`application/zip`; ZIP requests may also send `X-Filename: backup.zip`. Imports are restored as
a new project with remapped IDs, and invalid packages are rejected before commit.

## Stage 3 AI API

Configure an OpenAI-compatible provider with `POST /api/v1/providers`. API keys are encrypted
at rest with a Fernet key derived from `NOVEL_WORKBENCH_PROVIDER_SECRET`; provider APIs only
return `has_api_key`. For local development, use `base_url: "mock://writer"` to exercise the
complete flow without an external model.

Create a session with `POST /api/v1/ai/sessions`, then submit a message to
`POST /api/v1/ai/sessions/{session_id}/messages`. The message endpoint returns `202`; consume
the persisted stream at `GET /api/v1/ai/sessions/{session_id}/events`. SSE `id` values are
session-scoped, and a `Last-Event-ID` header or `last_event_id` query resumes from that sequence.
AI output only creates a pending operation preview; it never changes chapter content until the
existing approve endpoint is called.

## Stage 4 system prompts

System prompts are managed as versioned templates through `/api/v1/prompts`. Templates support
the scopes `global`, `project`, `agent`, and `workflow`; a session-only prompt is appended at
runtime. Enabled templates are merged in that order, followed by the session prompt and a fixed
untrusted-data boundary. Project name and description are supplied automatically; other values
must be passed through the variable map.

Create a template with `POST /api/v1/prompts`, add immutable versions with
`POST /api/v1/prompts/{id}/versions`, or update content through `PATCH /api/v1/prompts/{id}`.
Use `POST /api/v1/prompts/preview` to inspect the rendered prompt, version IDs, SHA-256 digest,
sections, and an approximate token count before creating an AI session. Only the following
variables are accepted: `project.name`, `project.description`, `chapter.title`,
`chapter.content`, `selected_text`, `user.instruction`, and `session.prompt`.

Creating an AI session renders and freezes the prompt. `AiSessionRead` exposes the final prompt,
the selected version IDs, section snapshot, variables, and digest, so later template changes do
not alter historical calls. API keys and secret-like fields are rejected from prompt content.

## Stage 5 context and tools

Every AI message now builds and stores an auditable `ContextPackage`. Its default priority is
user instruction, selected text, current chapter, project rules, project summary, entities, and
notes. The package records source IDs, priority, token count, truncation flags, budget, used token
count, and a SHA-256 digest. `POST /api/v1/context/build` previews the package before a call;
`GET /api/v1/ai/sessions/{session_id}/messages/{message_id}/context` reads the frozen package.
Message requests accept `context_budget` from 256 to 20,000 tokens. Lower-priority truncatable
fragments are shortened or omitted when the budget is exceeded, while the package reports why.

The first tool set is available under `/api/v1/tools`: `read_chapter`, `search_project`,
`read_entity`, `create_note`, `propose_text_operation`, and `update_entity`. All responses use
`success`, `error_code`, `message`, `source_ids`, and `data`. Project ownership is checked for
every tool. Text and entity changes create pending operations and require the existing approve
endpoint; tools never write chapter text or entity fields directly.

## Stage 6 FTS5 search and citations

The project search endpoint is `POST /api/v1/search`. It indexes chapters, entities, and notes
in SQLite FTS5 and uses an application-side Chinese character n-gram fallback. Search requests
are scoped by `project_id` and can optionally filter by `source_type` (`chapter`, `entity`, or
`note`) and `volume_id`. Results include highlighted snippets, score, source IDs, chapter/volume
IDs, paragraph position when available, and `index_version` for citation replay.

Use `POST /api/v1/projects/{project_id}/search/reindex` to rebuild a project index explicitly.
The existing `search_project` tool uses the same service and response shape. AI message requests
may include `search_query` and `search_limit`; matching snippets are added to the ContextPackage
as low-priority, traceable `search_result` fragments. `0005_fts5_search` creates the FTS5 table
and records the retrieval query on each AI message. A per-project source stamp avoids rebuilding
the index when chapters, entities, and notes have not changed.
