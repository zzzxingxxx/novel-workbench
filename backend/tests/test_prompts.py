def make_project(client, name="提示词作品"):
    return client.post("/api/v1/projects", json={"name": name}).json()


def test_prompt_template_versions_and_preview(client):
    project = make_project(client)
    created = client.post(
        "/api/v1/prompts",
        json={
            "scope": "global",
            "name": "基础规则",
            "content": "你是写作助手。作品：{{project.name}}。",
            "variables": [{"name": "project.name", "required": True}],
        },
    )
    assert created.status_code == 201
    template = created.json()
    versions = client.get(f"/api/v1/prompts/{template['id']}/versions").json()
    assert len(versions) == 1
    first_id = versions[0]["id"]
    updated = client.patch(
        f"/api/v1/prompts/{template['id']}",
        json={"content": "新版规则：{{project.name}}。"},
    )
    assert updated.status_code == 200
    assert updated.json()["active_version_id"] != first_id
    versions = client.get(f"/api/v1/prompts/{template['id']}/versions").json()
    assert [item["version"] for item in versions] == [2, 1]
    assert versions[1]["content"].startswith("你是写作助手")
    preview = client.post(
        "/api/v1/prompts/preview",
        json={"project_id": project["id"], "variables": {"project.name": project["name"]}},
    )
    assert preview.status_code == 200
    body = preview.json()
    assert "新版规则" in body["prompt"]
    assert updated.json()["active_version_id"] in body["version_ids"]
    assert body["estimated_tokens"] > 0
    assert body["digest"]


def test_prompt_scopes_order_disable_and_project_isolation(client):
    project_a = make_project(client, "A")
    project_b = make_project(client, "B")
    common = {"variables": []}
    global_prompt = client.post(
        "/api/v1/prompts",
        json={"scope": "global", "name": "全局", "content": "G", **common},
    ).json()
    client.post(
        "/api/v1/prompts",
        json={
            "scope": "project",
            "project_id": project_a["id"],
            "name": "项目",
            "content": "P",
            **common,
        },
    )
    client.post(
        "/api/v1/prompts",
        json={
            "scope": "agent",
            "project_id": project_a["id"],
            "owner_id": "writer",
            "name": "Agent",
            "content": "A",
            **common,
        },
    )
    client.post(
        "/api/v1/prompts",
        json={
            "scope": "workflow",
            "project_id": project_a["id"],
            "owner_id": "draft",
            "name": "Workflow",
            "content": "W",
            **common,
        },
    )
    preview = client.post(
        "/api/v1/prompts/preview",
        json={"project_id": project_a["id"], "agent_id": "writer", "workflow_id": "draft"},
    )
    assert [part["scope"] for part in preview.json()["sections"]] == [
        "global",
        "project",
        "agent",
        "workflow",
    ]
    assert preview.json()["prompt"].index("G") < preview.json()["prompt"].index("P")
    assert (
        "P"
        not in client.post("/api/v1/prompts/preview", json={"project_id": project_b["id"]}).json()[
            "prompt"
        ]
    )
    client.patch(f"/api/v1/prompts/{global_prompt['id']}", json={"enabled": False})
    assert (
        "G"
        not in client.post("/api/v1/prompts/preview", json={"project_id": project_a["id"]}).json()[
            "prompt"
        ]
    )


def test_prompt_validation_and_session_snapshot(client):
    project = make_project(client)
    unknown = client.post(
        "/api/v1/prompts",
        json={"scope": "global", "name": "坏变量", "content": "{{unknown}}"},
    )
    assert unknown.status_code == 422
    assert unknown.json()["error"]["code"] == "unknown_prompt_variable"
    missing = client.post(
        "/api/v1/prompts",
        json={
            "scope": "global",
            "name": "必填",
            "content": "{{project.name}}",
            "variables": [{"name": "project.name", "required": True}],
        },
    )
    assert missing.status_code == 201
    preview = client.post("/api/v1/prompts/preview", json={"project_id": project["id"]})
    assert preview.status_code == 200
    assert project["name"] in preview.json()["prompt"]
    provider = client.post(
        "/api/v1/providers",
        json={"name": "演示", "base_url": "mock://writer", "model": "demo-1"},
    ).json()
    session = client.post(
        "/api/v1/ai/sessions",
        json={
            "project_id": project["id"],
            "provider_id": provider["id"],
            "prompt_variables": {"project.name": "快照作品"},
        },
    )
    assert session.status_code == 201
    snapshot = session.json()
    assert snapshot["prompt_version_ids"]
    assert snapshot["prompt_digest"]
    assert "快照作品" in (snapshot["system_prompt"] or "")


def test_prompt_rejects_secret_like_content(client):
    response = client.post(
        "/api/v1/prompts",
        json={
            "scope": "global",
            "name": "不应保存密钥",
            "content": "api_key: sk-abcdefghijklmnopqrstuv",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "sensitive_prompt_content"
