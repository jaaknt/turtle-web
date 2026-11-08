"""Settings parsing that a hand-edited .env or secrets.env can get wrong."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from turtleweb.settings import Settings


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("TURTLE_WEB_BENCHMARK_SYMBOLS", "TURTLE_WEB_BENCHMARK_SYMBOL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("TURTLE_WEB_DB_PASSWORD", "x")


def test_benchmarks_default_to_spy_and_qqq() -> None:
    assert Settings(_env_file=None).benchmark_symbols == ["SPY.US", "QQQ.US"]


def test_benchmarks_are_split_stripped_and_deduplicated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TURTLE_WEB_BENCHMARK_SYMBOLS", " SPY.US, ,SPY.US,QQQ.US ")
    assert Settings(_env_file=None).benchmark_symbols == ["SPY.US", "QQQ.US"]


def test_a_list_is_cleaned_the_same_way() -> None:
    assert Settings(_env_file=None, benchmark_symbols=[" A.US", "", "A.US", "B.US"]).benchmark_symbols == ["A.US", "B.US"]


@pytest.mark.parametrize("value", ["", " , "])
def test_no_benchmark_fails_at_startup(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("TURTLE_WEB_BENCHMARK_SYMBOLS", value)
    with pytest.raises(ValidationError, match="at least one benchmark"):
        Settings(_env_file=None)


def test_the_old_singular_name_still_works(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TURTLE_WEB_BENCHMARK_SYMBOL", "IWM.US")
    assert Settings(_env_file=None).benchmark_symbols == ["IWM.US"]


def test_the_plural_name_wins_over_the_singular(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TURTLE_WEB_BENCHMARK_SYMBOL", "IWM.US")
    monkeypatch.setenv("TURTLE_WEB_BENCHMARK_SYMBOLS", "SPY.US")
    assert Settings(_env_file=None).benchmark_symbols == ["SPY.US"]


def test_the_old_singular_name_in_a_dotenv_file_is_not_an_extra_input(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("TURTLE_WEB_BENCHMARK_SYMBOL=BENCH.US\n")
    assert Settings(_env_file=env).benchmark_symbols == ["BENCH.US"]
