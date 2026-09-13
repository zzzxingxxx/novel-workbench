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
