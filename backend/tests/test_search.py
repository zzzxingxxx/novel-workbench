from test_domain import setup_tree


def test_fts_search_returns_citations_and_filters_project(client):
    project, volume, chapter = setup_tree(client)
    other, _, other_chapter = setup_tree(client)
    client.patch(
        f"/api/v1/chapters/{chapter['id']}",
        json={"title": "雾中信件"},
    )
    client.post(
        f"/api/v1/projects/{project['id']}/entities",
        json={"kind": "character", "name": "林默", "aliases": ["船员"]},
    )
    client.post(
        f"/api/v1/projects/{project['id']}/notes",
        json={"title": "线索", "content": "第七码头在雾中"},
    )
    client.post(
        f"/api/v1/projects/{other['id']}/notes",
        json={"title": "其他", "content": "第七码头"},
    )
    result = client.post(
        "/api/v1/search",
        json={"project_id": project["id"], "query": "第七码头", "limit": 10},
    )
    assert result.status_code == 200
    body = result.json()
    assert body["index_version"] == "fts5-v1"
    assert body["total"] >= 1
    assert all(item["project_id"] == project["id"] for item in body["items"])
    assert body["items"][0]["citation"]["source_id"] == body["items"][0]["source_id"]
    assert "<mark>" in body["items"][0]["highlight"] or body["items"][0]["highlight"]
    volume_only = client.post(
        "/api/v1/search",
        json={
            "project_id": project["id"],
            "query": "旧内容",
            "volume_id": volume["id"],
            "source_type": "chapter",
        },
    )
    assert volume_only.status_code == 200
    assert all(item["chapter_id"] == chapter["id"] for item in volume_only.json()["items"])
    assert other_chapter["id"] not in {item["source_id"] for item in body["items"]}
    alias_result = client.post(
        "/api/v1/search",
        json={
            "project_id": project["id"],
            "query": "船员",
            "source_type": "entity",
        },
    )
    assert alias_result.json()["items"][0]["source_type"] == "entity"
    tag_result = client.post(
        "/api/v1/search",
        json={
            "project_id": project["id"],
            "query": "线索",
            "source_type": "note",
        },
    )
    assert tag_result.json()["items"]


def test_fts_search_supports_chinese_ngram_and_reindex(client):
    project, _, _ = setup_tree(client)
    reindex = client.post(f"/api/v1/projects/{project['id']}/search/reindex")
    assert reindex.status_code == 200
    assert reindex.json()["index_version"] == "fts5-v1"
    found = client.post(
        "/api/v1/tools/search_project",
        json={"project_id": project["id"], "query": "内容"},
    )
    assert found.status_code == 200
    assert found.json()["success"] is True
    assert found.json()["data"]["items"]


def test_search_query_is_recorded_in_ai_context(client):
    project, _, chapter = setup_tree(client)
    client.post(
        f"/api/v1/projects/{project['id']}/notes",
        json={"title": "检索线索", "content": "第七码头的灯亮着"},
    )
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
        json={
            "content": "查找线索",
            "chapter_id": chapter["id"],
            "search_query": "第七码头",
            "search_limit": 3,
        },
    )
    assert accepted.status_code == 202
    events = client.get(f"/api/v1/ai/sessions/{session['id']}/events")
    assert "event: context.ready" in events.text
    context = client.get(
        f"/api/v1/ai/sessions/{session['id']}/messages/{accepted.json()['message_id']}/context"
    ).json()
    assert context["package"]["fragments"]
    assert any(
        fragment["source"] == "search_result" for fragment in context["package"]["fragments"]
    )
