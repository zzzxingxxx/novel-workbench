from test_domain import setup_tree


def test_request_id_and_diagnostics_export(client):
    health = client.get("/health")
    request_id = health.headers.get("x-request-id")
    assert request_id
    _, _, _ = setup_tree(client)
    response = client.get("/api/v1/diagnostics/summary")
    assert response.status_code == 200
    summary = response.json()
    assert summary["requests"] >= 2
    export = client.get("/api/v1/diagnostics/export")
    assert export.status_code == 200
    assert request_id in export.text
    assert "正文" not in export.text
    assert "Prompt" not in export.text
    assert "stage11-secret" not in export.text


def test_auth_session_is_open_by_default(client):
    response = client.get("/api/v1/auth/session")
    assert response.status_code == 200
    assert response.json() == {"mode": "open", "authenticated": True}


def test_configured_local_token_protects_api(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "local_token", "stage11-secret")
    denied = client.get("/api/v1/projects")
    assert denied.status_code == 401
    allowed = client.get("/api/v1/projects", headers={"X-Novel-Workbench-Token": "stage11-secret"})
    assert allowed.status_code == 200
