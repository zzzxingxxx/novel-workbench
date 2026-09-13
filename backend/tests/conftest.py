from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    database = tmp_path / "test.db"
    monkeypatch.setenv("NOVEL_WORKBENCH_DATABASE_URL", f"sqlite:///{database}")
    from app.config import settings
    from app.db import session

    settings.database_url = f"sqlite:///{database}"
    session.engine.dispose()
    from sqlalchemy import create_engine

    session.engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
    session.SessionLocal.configure(bind=session.engine)
    from sqlalchemy import event

    @event.listens_for(session.engine, "connect")
    def _pragmas(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    from app.models import domain  # noqa: F401

    session.Base.metadata.create_all(session.engine)
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
    session.Base.metadata.drop_all(session.engine)
