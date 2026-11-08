"""Runtime configuration from the environment."""

from pathlib import Path
from typing import Annotated

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from TURTLE_WEB_* environment variables and api/.env.

    There is no TOML and no profiles: a server has one deployment shape.
    """

    model_config = SettingsConfigDict(env_prefix="TURTLE_WEB_", env_file=".env", populate_by_name=True)

    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "trading"
    db_user: str = "turtle_web"
    db_password: str  # no default: a missing secret fails at startup, never falls back
    # Comma-separated in the environment: TURTLE_WEB_BENCHMARK_SYMBOLS=SPY.US,QQQ.US. The first one's
    # trading days form the ledger's calendar. The old singular TURTLE_WEB_BENCHMARK_SYMBOL still
    # works (the plural wins if both are set), so an older .env neither fails nor goes ignored.
    benchmark_symbols: Annotated[list[str], NoDecode] = Field(
        default=["SPY.US", "QQQ.US"],
        validation_alias=AliasChoices("TURTLE_WEB_BENCHMARK_SYMBOLS", "TURTLE_WEB_BENCHMARK_SYMBOL"),
    )
    signal_strategy: str = "bk50d_s12_v2.0"  # the baseline label the nightly run persists
    signal_ranking_strategy: str = "qullamaggie"  # the gate of 44 is only meaningful on this scale
    static_dir: Path | None = None  # web/dist in production; None in dev, where Vite serves the UI

    @field_validator("benchmark_symbols", mode="before")
    @classmethod
    def _clean_symbols(cls, value: object) -> object:
        """Split a comma-separated string; strip, drop blanks and repeats from a string or a list."""
        if isinstance(value, str):
            value = value.split(",")
        if isinstance(value, list):
            stripped = [s.strip() if isinstance(s, str) else s for s in value]
            value = list(dict.fromkeys(s for s in stripped if s != ""))
            if not value:
                raise ValueError("at least one benchmark symbol is required")
        return value
