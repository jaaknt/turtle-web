"""Runtime configuration from the environment."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from TURTLE_WEB_* environment variables and api/.env.

    There is no TOML and no profiles: a server has one deployment shape.
    """

    model_config = SettingsConfigDict(env_prefix="TURTLE_WEB_", env_file=".env")

    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "trading"
    db_user: str = "turtle_web"
    db_password: str  # no default: a missing secret fails at startup, never falls back
    benchmark_symbol: str = "SPY.US"
    signal_strategy: str = "bk50d_s12_v2.0"  # the baseline label the nightly run persists
    signal_ranking_strategy: str = "qullamaggie"  # the gate of 44 is only meaningful on this scale
    static_dir: Path | None = None  # web/dist in production; None in dev, where Vite serves the UI
