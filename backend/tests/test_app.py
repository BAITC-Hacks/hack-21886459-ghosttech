from fastapi.testclient import TestClient

from app.main import app


def test_app_flow(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.sqlite3"))
    with TestClient(app) as client:
        assert client.get("/api/health").json() == {"status": "ok", "database": "sqlite"}
        assert client.get("/").status_code == 200
        assert client.get("/static/app.js").status_code == 200
        assert client.get("/static/styles.css").status_code == 200
        assert client.post("/api/notes", json={"text": "   "}).status_code == 422
        response = client.post("/api/notes", json={"text": "  Проверка SQLite  "})
        assert response.status_code == 201
        note = response.json()
        assert note["text"] == "Проверка SQLite"
        assert client.get("/api/notes").json() == [note]

    # A new application lifespan must keep data saved by the previous one.
    with TestClient(app) as client:
        assert client.get("/api/notes").json() == [note]
        assert client.delete(f"/api/notes/{note['id']}").status_code == 204
        assert client.get("/api/notes").json() == []
        assert client.delete(f"/api/notes/{note['id']}").status_code == 404
