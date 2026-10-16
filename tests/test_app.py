from fastapi.testclient import TestClient

from memory.app import app

client = TestClient(app)


def test_health_reports_falkordb():
    body = client.get("/health").json()
    assert body["falkordb"] is True
    assert "ollama" in body  # version string, or None when the tunnel is down


def test_create_world_is_idempotent(world_id):
    first = client.post(f"/worlds/{world_id}")
    assert first.status_code == 200
    assert first.json()["graph"] == f"world_{world_id}"
    assert len(first.json()["indexes_created"]) == 9
    assert client.post(f"/worlds/{world_id}").json()["indexes_created"] == []
    assert world_id in client.get("/worlds").json()["worlds"]


def test_create_world_rejects_bad_id():
    assert client.post("/worlds/bad%20id").status_code == 422
