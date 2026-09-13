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
