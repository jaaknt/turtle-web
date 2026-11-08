"""Shared fixtures: a read-only engine on the seeded demo database."""

import os
from collections.abc import Iterator
from datetime import date, timedelta

import pytest
import sqlalchemy as sa

from turtleweb.db import make_engine
from turtleweb.settings import Settings

# The demo database from docker-compose.yml; TURTLE_WEB_* variables (CI sets them) take precedence.
DEMO_DEFAULTS = {
    "TURTLE_WEB_DB_HOST": "localhost",
    "TURTLE_WEB_DB_PORT": "5433",
    "TURTLE_WEB_DB_USER": "postgres",
    "TURTLE_WEB_DB_PASSWORD": "demo",
    "TURTLE_WEB_BENCHMARK_SYMBOLS": "BENCH.US,BENCHQ.US",
}


@pytest.fixture(scope="session")
def demo_settings() -> Settings:
    """Settings for the demo database, ignoring api/.env so a dev .env cannot redirect the tests."""
    env = {**DEMO_DEFAULTS, **{k: v for k, v in os.environ.items() if k.startswith("TURTLE_WEB_")}}
    return Settings(
        _env_file=None,
        db_host=env["TURTLE_WEB_DB_HOST"],
        db_port=int(env["TURTLE_WEB_DB_PORT"]),
        db_user=env["TURTLE_WEB_DB_USER"],
        db_password=env["TURTLE_WEB_DB_PASSWORD"],
        benchmark_symbols=env["TURTLE_WEB_BENCHMARK_SYMBOLS"],
    )


@pytest.fixture(scope="session")
def demo_engine(demo_settings: Settings) -> Iterator[sa.Engine]:
    """The app's read-only engine on the demo database; skips if it is not running.

    Start it with `docker compose up -d --wait && uv run db/seed_demo.py` from the repo root.
    Fails if the data is stale: the queries use CURRENT_DATE windows, so an old seed would make
    them return nothing for reasons unrelated to the code.
    """
    engine = make_engine(demo_settings)
    try:
        with engine.connect() as conn:
            latest = conn.execute(sa.text("SELECT max(date) FROM turtle.daily_bars")).scalar_one()
    except sa.exc.OperationalError as exc:
        engine.dispose()
        pytest.skip(f"demo database not running: {exc}")
    if latest is None or latest < date.today() - timedelta(days=7):
        engine.dispose()
        pytest.fail(f"demo data is missing or stale (latest bar {latest}): re-run `uv run db/seed_demo.py`")
    yield engine
    engine.dispose()
