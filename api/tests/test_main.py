"""App factory tests that need no database."""

from pathlib import Path

from fastapi.testclient import TestClient

from turtleweb.main import create_app
from turtleweb.settings import Settings


def test_healthz_answers_without_a_database() -> None:
    # Port 1 refuses connections: the test passes only because neither startup nor /healthz queries.
    settings = Settings(db_password="x", db_port=1)
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_spa_fallback_serves_index_for_deep_links_but_not_for_api(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<!doctype html><title>spa</title>")
    (tmp_path / "app.js").write_text("console.log(1)")
    settings = Settings(db_password="x", db_port=1, static_dir=tmp_path)
    with TestClient(create_app(settings)) as client:
        assert client.get("/").text.startswith("<!doctype html>")
        assert client.get("/app.js").text == "console.log(1)"
        assert client.get("/chart/DEMOA.US").text.startswith("<!doctype html>")
        assert client.get("/api/no-such-endpoint").status_code == 404
