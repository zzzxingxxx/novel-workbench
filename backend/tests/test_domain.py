def setup_tree(client):
    project = client.post("/api/v1/projects", json={"name": "测试作品"}).json()
    volume = client.post(
        f"/api/v1/projects/{project['id']}/volumes", json={"title": "第一卷"}
    ).json()
    chapter = client.post(
        f"/api/v1/volumes/{volume['id']}/chapters", json={"title": "第一章", "content": "旧内容"}
    ).json()
    return project, volume, chapter


def test_project_chapter_and_revision_flow(client):
    project, volume, chapter = setup_tree(client)
    assert project["name"] == "测试作品"
    assert chapter["word_count"] == 3
    revisions = client.get(f"/api/v1/chapters/{chapter['id']}/revisions").json()
    assert len(revisions) == 1
    operation = client.post(
        "/api/v1/operations",
        json={
            "project_id": project["id"],
            "target_id": chapter["id"],
            "type": "append",
            "payload": {"new_text": "追加"},
            "old_hash": chapter["content_hash"],
            "idempotency_key": "op-1",
        },
    )
    assert operation.status_code == 201
    assert operation.json()["status"] == "pending"
    assert client.post(f"/api/v1/operations/{operation.json()['id']}/approve").status_code == 200
    updated = client.get(f"/api/v1/chapters/{chapter['id']}").json()
    assert updated["content"] == "旧内容追加"
    assert updated["word_count"] == 5
    assert len(client.get(f"/api/v1/chapters/{chapter['id']}/revisions").json()) == 2


def test_old_hash_conflict_does_not_overwrite(client):
    project, _, chapter = setup_tree(client)
    first = {
        "project_id": project["id"],
        "target_id": chapter["id"],
        "type": "append",
        "payload": {"new_text": "A"},
        "old_hash": chapter["content_hash"],
    }
    first_operation = client.post("/api/v1/operations", json=first)
    assert first_operation.status_code == 201
    assert (
        client.post(f"/api/v1/operations/{first_operation.json()['id']}/approve").status_code == 200
    )
    second = {
        "project_id": project["id"],
        "target_id": chapter["id"],
        "type": "append",
        "payload": {"new_text": "B"},
        "old_hash": chapter["content_hash"],
    }
    conflict = client.post("/api/v1/operations", json=second)
    assert conflict.status_code == 409
    assert client.get(f"/api/v1/chapters/{chapter['id']}").json()["content"] == "旧内容A"


def test_restore_revision(client):
    project, _, chapter = setup_tree(client)
    original_revision = client.get(f"/api/v1/chapters/{chapter['id']}/revisions").json()[0]
    operation = client.post(
        "/api/v1/operations",
        json={
            "project_id": project["id"],
            "target_id": chapter["id"],
            "type": "append",
            "payload": {"new_text": "修改"},
            "old_hash": chapter["content_hash"],
        },
    )
    assert operation.status_code == 201
    assert client.post(f"/api/v1/operations/{operation.json()['id']}/approve").status_code == 200
    current = client.get(f"/api/v1/chapters/{chapter['id']}").json()
    restored = client.post(
        "/api/v1/operations",
        json={
            "project_id": project["id"],
            "target_id": chapter["id"],
            "type": "restore_revision",
            "payload": {"revision_id": original_revision["id"]},
            "old_hash": current["content_hash"],
        },
    )
    assert restored.status_code == 201
    assert client.post(f"/api/v1/operations/{restored.json()['id']}/approve").status_code == 200
    assert client.get(f"/api/v1/chapters/{chapter['id']}").json()["content"] == "旧内容"


def test_entities_and_notes_are_project_scoped(client):
    project, _, _ = setup_tree(client)
    entity = client.post(
        f"/api/v1/projects/{project['id']}/entities", json={"kind": "character", "name": "林默"}
    ).json()
    note = client.post(
        f"/api/v1/projects/{project['id']}/notes", json={"title": "灵感", "content": "一场雨"}
    ).json()
    assert client.get(f"/api/v1/projects/{project['id']}/entities").json()[0]["id"] == entity["id"]
    assert client.get(f"/api/v1/projects/{project['id']}/notes").json()[0]["id"] == note["id"]


def test_reject_operation_keeps_content_unchanged(client):
    project, _, chapter = setup_tree(client)
    operation = client.post(
        "/api/v1/operations",
        json={
            "project_id": project["id"],
            "target_id": chapter["id"],
            "type": "append",
            "payload": {"new_text": "不会写入"},
            "old_hash": chapter["content_hash"],
        },
    ).json()
    response = client.post(f"/api/v1/operations/{operation['id']}/reject")
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert client.get(f"/api/v1/chapters/{chapter['id']}").json()["content"] == "旧内容"


def test_project_tree_and_rename(client):
    project, volume, chapter = setup_tree(client)
    assert (
        client.patch(f"/api/v1/projects/{project['id']}", json={"name": "新名称"}).json()["name"]
        == "新名称"
    )
    tree = client.get(f"/api/v1/projects/{project['id']}/tree").json()
    assert tree["volumes"][0]["id"] == volume["id"]
    assert tree["volumes"][0]["chapters"][0]["id"] == chapter["id"]


def test_pagination_and_chapter_listing(client):
    project, volume, _ = setup_tree(client)
    client.post(
        f"/api/v1/volumes/{volume['id']}/chapters", json={"title": "第二章", "content": "更多"}
    )
    page = client.get("/api/v1/projects?page=1&page_size=1")
    assert page.status_code == 200
    assert page.json()["meta"] == {"page": 1, "page_size": 1, "total": 1, "has_next": False}
    chapters = client.get(f"/api/v1/volumes/{volume['id']}/chapters?page=1&page_size=1").json()
    assert chapters["meta"]["total"] == 2
    assert len(chapters["items"]) == 1
    assert client.get(f"/api/v1/projects/{project['id']}/volumes?page_size=101").status_code == 422


def test_json_and_zip_round_trip(client):
    project, _, chapter = setup_tree(client)
    client.post(
        f"/api/v1/projects/{project['id']}/entities", json={"kind": "character", "name": "林默"}
    )
    json_export = client.get(f"/api/v1/projects/{project['id']}/export?format=json")
    assert json_export.status_code == 200
    assert json_export.headers["content-type"].startswith("application/json")
    imported = client.post(
        "/api/v1/projects/import",
        content=json_export.content,
        headers={"content-type": "application/json"},
    )
    assert imported.status_code == 201
    imported_id = imported.json()["id"]
    imported_tree = client.get(f"/api/v1/projects/{imported_id}/tree").json()
    assert imported_tree["volumes"][0]["chapters"][0]["id"] != chapter["id"]
    assert imported_tree["volumes"][0]["chapters"][0]["title"] == "第一章"

    zip_export = client.get(f"/api/v1/projects/{project['id']}/export?format=zip")
    assert zip_export.status_code == 200
    restored = client.post(
        "/api/v1/projects/import",
        content=zip_export.content,
        headers={"content-type": "application/zip"},
    )
    assert restored.status_code == 201


def test_invalid_import_does_not_change_existing_projects(client):
    setup_tree(client)
    before = len(client.get("/api/v1/projects").json())
    invalid = {
        "schema_version": "1.0",
        "project": {
            "name": "坏包",
            "volumes": [
                {
                    "title": "重复位置",
                    "position": 0,
                    "chapters": [
                        {"title": "一", "position": 0, "content": "a"},
                        {"title": "二", "position": 0, "content": "b"},
                    ],
                }
            ],
            "entities": [],
            "notes": [],
        },
    }
    response = client.post(
        "/api/v1/projects/import",
        json=invalid,
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "unique_constraint"
    assert len(client.get("/api/v1/projects").json()) == before


def test_operation_validation_and_idempotency_conflict(client):
    project, _, chapter = setup_tree(client)
    invalid = client.post(
        "/api/v1/operations",
        json={
            "project_id": project["id"],
            "target_id": chapter["id"],
            "type": "append",
            "payload": {},
        },
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "invalid_operation"
    operation = client.post(
        "/api/v1/operations",
        json={
            "project_id": project["id"],
            "target_id": chapter["id"],
            "type": "append",
            "payload": {"new_text": "A"},
            "idempotency_key": "same-key",
        },
    )
    duplicate = client.post(
        "/api/v1/operations",
        json={
            "project_id": project["id"],
            "target_id": chapter["id"],
            "type": "append",
            "payload": {"new_text": "B"},
            "idempotency_key": "same-key",
        },
    )
    assert operation.status_code == 201
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "idempotency_conflict"


def test_data_survives_engine_reconnect(client):
    from app.db import session

    project, _, _ = setup_tree(client)
    session.engine.dispose()
    response = client.get(f"/api/v1/projects/{project['id']}")
    assert response.status_code == 200
    assert response.json()["name"] == "测试作品"
