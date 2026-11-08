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


def test_spa_fallback_serves_index_for_deep_links_but_not_for_api_or_assets(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<!doctype html><title>spa</title>")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app-abc123.js").write_text("console.log(1)")
    settings = Settings(db_password="x", db_port=1, static_dir=tmp_path)
    with TestClient(create_app(settings)) as client:
        assert client.get("/").text.startswith("<!doctype html>")
        assert client.get("/assets/app-abc123.js").text == "console.log(1)"
        assert client.get("/chart/DEMOA.US").text.startswith("<!doctype html>")
        assert client.get("/api/no-such-endpoint").status_code == 404
        # A chunk from a previous release: a real 404, never index.html served as JavaScript.
        assert client.get("/assets/ChartView-old999.js").status_code == 404


def test_static_dir_may_be_a_symlink_swapped_while_running(tmp_path: Path) -> None:
    # deploy.sh points web/dist at web/releases/<tag> and swaps the link while the app runs.
    for tag in ("v1", "v2"):
        (tmp_path / tag).mkdir()
        (tmp_path / tag / "index.html").write_text(f"<!doctype html><title>{tag}</title>")
    dist = tmp_path / "dist"
    dist.symlink_to("v1")
    settings = Settings(db_password="x", db_port=1, static_dir=dist)
    with TestClient(create_app(settings)) as client:
        assert "v1" in client.get("/").text
        (tmp_path / "next").symlink_to("v2")
        (tmp_path / "next").replace(dist)  # rename(2) over the old link, as `mv -T` does
        assert "v2" in client.get("/").text
