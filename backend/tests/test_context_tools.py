from test_domain import setup_tree


def test_context_package_priority_budget_and_message_snapshot(client):
    project, _, chapter = setup_tree(client)
    client.patch(
        f"/api/v1/projects/{project['id']}",
        json={"description": "作品规则和背景"},
    )
    client.post(
        f"/api/v1/projects/{project['id']}/entities",
        json={"kind": "character", "name": "林默", "description": "船员"},
    ).json()
    client.post(
        f"/api/v1/projects/{project['id']}/notes",
        json={"title": "线索", "content": "港口有一盏不熄的灯"},
    )
    package = client.post(
        "/api/v1/context/build",
        json={
            "project_id": project["id"],
            "chapter_id": chapter["id"],
            "selected_text": "选区" * 1000,
            "user_instruction": "请保持悬疑节奏",
            "budget_tokens": 256,
        },
    )
    assert package.status_code == 200
    body = package.json()
    assert body["used_tokens"] <= body["budget_tokens"] + 20
    assert body["fragments"][0]["source"] == "user_instruction"
    assert body["fragments"][0]["priority"] > body["fragments"][1]["priority"]
    assert body["digest"]
    assert body["truncated_count"] >= 1

    provider = client.post(
        "/api/v1/providers",
        json={"name": "演示", "base_url": "mock://writer", "model": "demo-1"},
    ).json()
    session = client.post(
        "/api/v1/ai/sessions",
        json={"project_id": project["id"], "provider_id": provider["id"]},
    ).json()
    accepted = client.post(
        f"/api/v1/ai/sessions/{session['id']}/messages",
        json={"content": "检查", "chapter_id": chapter["id"], "context_budget": 300},
    )
    assert accepted.status_code == 202
    client.get(f"/api/v1/ai/sessions/{session['id']}/events")
    context = client.get(
        f"/api/v1/ai/sessions/{session['id']}/messages/{accepted.json()['message_id']}/context"
    )
    assert context.status_code == 200
    assert context.json()["digest"]
    assert context.json()["package"]["fragments"]


def test_context_tools_are_project_scoped_and_write_tools_are_approval_safe(client):
    project, _, chapter = setup_tree(client)
    other, _, _ = setup_tree(client)
    read = client.post(
        "/api/v1/tools/read_chapter",
        json={"project_id": other["id"], "chapter_id": chapter["id"]},
    )
    assert read.status_code == 200
    assert read.json()["success"] is False
    entity = client.post(
        f"/api/v1/projects/{project['id']}/entities",
        json={"kind": "character", "name": "林默"},
    ).json()
    found = client.post(
        "/api/v1/tools/read_entity",
        json={"project_id": project["id"], "entity_id": entity["id"]},
    )
    assert found.json()["success"] is True
    search = client.post(
        "/api/v1/tools/search_project",
        json={"project_id": project["id"], "query": "旧内容"},
    )
    assert search.json()["success"] is True
    note = client.post(
        "/api/v1/tools/create_note",
        json={"project_id": project["id"], "title": "工具笔记", "content": "记录"},
    )
    assert note.json()["success"] is True
    proposed = client.post(
        "/api/v1/tools/propose_text_operation",
        json={
            "project_id": project["id"],
            "chapter_id": chapter["id"],
            "type": "append",
            "payload": {"new_text": "建议"},
            "old_hash": chapter["content_hash"],
        },
    )
    assert proposed.json()["success"] is True
    assert proposed.json()["data"]["status"] == "pending"
    assert client.get(f"/api/v1/chapters/{chapter['id']}").json()["content"] == "旧内容"
    entity_update = client.post(
        "/api/v1/tools/update_entity",
        json={
            "project_id": project["id"],
            "entity_id": entity["id"],
            "changes": {"description": "新的描述"},
        },
    )
    assert entity_update.json()["success"] is True
    assert entity_update.json()["data"]["requires_approval"] is True
    operation_id = entity_update.json()["data"]["operation_id"]
    assert client.post(f"/api/v1/operations/{operation_id}/approve").status_code == 200
    entities = client.get(f"/api/v1/projects/{project['id']}/entities").json()
    assert entities[0]["description"] == "新的描述"
