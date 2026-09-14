import hashlib
import io
import json
import zipfile

from test_domain import setup_tree


def test_export_formats_and_zip_checksum(client):
    project, _, _ = setup_tree(client)
    for format_name in ("json", "zip", "markdown", "docx", "epub"):
        response = client.get(f"/api/v1/projects/{project['id']}/export?format={format_name}")
        assert response.status_code == 200
        assert response.content
    package = client.get(f"/api/v1/projects/{project['id']}/export?format=zip")
    with zipfile.ZipFile(io.BytesIO(package.content)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["schema_version"] == "1.1"
        assert (
            manifest["files"]["project.json"]
            == hashlib.sha256(archive.read("project.json")).hexdigest()
        )


def test_markdown_export_can_be_imported(client):
    project, _, chapter = setup_tree(client)
    package = client.get(f"/api/v1/projects/{project['id']}/export?format=markdown")
    imported = client.post(
        "/api/v1/projects/import",
        content=package.content,
        headers={"content-type": "application/zip", "x-filename": "backup-markdown.zip"},
    )
    assert imported.status_code == 201
    tree = client.get(f"/api/v1/projects/{imported.json()['id']}/tree").json()
    assert tree["volumes"][0]["chapters"][0]["title"] == chapter["title"]
    assert tree["volumes"][0]["chapters"][0]["id"] != chapter["id"]


def test_schema_10_document_is_migrated(client):
    document = {
        "schema_version": "1.0",
        "project": {
            "name": "旧版包",
            "volumes": [{"title": "卷一", "position": 0, "chapters": []}],
            "entities": [],
            "notes": [],
        },
    }
    response = client.post("/api/v1/projects/import", json=document)
    assert response.status_code == 201
    assert response.json()["name"] == "旧版包"


def test_story_graph_is_kept_in_json_backup(client):
    project, _, chapter = setup_tree(client)
    entity = client.post(
        f"/api/v1/projects/{project['id']}/entities",
        json={"kind": "character", "name": "林默", "tags": ["主角"]},
    ).json()
    client.post(
        f"/api/v1/entities/{entity['id']}/sources",
        json={"chapter_id": chapter["id"], "evidence": "首次出现"},
    )
    client.post(
        f"/api/v1/projects/{project['id']}/foreshadows",
        json={"title": "潮汐倒流", "status": "planted"},
    )
    exported = client.get(f"/api/v1/projects/{project['id']}/export?format=json")
    document = exported.json()
    assert document["schema_version"] == "1.1"
    assert document["project"]["story_graph"]["entity_sources"]
    restored = client.post(
        "/api/v1/projects/import",
        content=exported.content,
        headers={"content-type": "application/json"},
    )
    assert restored.status_code == 201
    restored_id = restored.json()["id"]
    assert (
        client.get(f"/api/v1/projects/{restored_id}/foreshadows").json()[0]["title"] == "潮汐倒流"
    )
