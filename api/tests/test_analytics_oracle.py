"""analytics.py against quantstats' own figures on a fixed synthetic series (docs/specs/portfolio.md, Step 4a).

analytics_oracle.json is written by api/scripts/make_analytics_oracle.py; regenerate it when quantstats is upgraded.
"""

import json
from dataclasses import fields
from datetime import date
from pathlib import Path

import pytest

from turtleweb.analytics import Metrics, Returns, drawdown_periods, metrics, monthly, yearly

ORACLE = json.loads(Path(__file__).with_name("analytics_oracle.json").read_text())
DATES = [date.fromisoformat(d) for d in ORACLE["dates"]]
SERIES = Returns(DATES, ORACLE["returns"])
METRICS = metrics(SERIES, Returns(DATES, ORACLE["benchmark"]))


def close(expected: float) -> object:
    return pytest.approx(expected, rel=1e-9, abs=1e-12)


@pytest.mark.parametrize("name", [f.name for f in fields(Metrics)])
def test_metric_matches_quantstats(name: str) -> None:
    assert getattr(METRICS, name) == close(ORACLE["metrics"][name])


def test_monthly_returns_match_quantstats() -> None:
    assert [(p.year, p.month, p.value) for p in monthly(SERIES)] == [(y, m, close(v)) for y, m, v in ORACLE["monthly"]]


def test_yearly_returns_match_quantstats() -> None:
    assert [(p.year, p.value) for p in yearly(SERIES)] == [(y, close(v)) for y, v in ORACLE["yearly"]]


def test_drawdown_periods_match_quantstats() -> None:
    ours = sorted(drawdown_periods(SERIES), key=lambda p: p.start)
    expected = [
        (date.fromisoformat(d["start"]), date.fromisoformat(d["valley"]), date.fromisoformat(d["end"]), d["days"], close(d["depth"]))
        for d in ORACLE["drawdowns"]
    ]
    assert [(p.start, p.valley, p.end, p.days, p.depth) for p in ours] == expected
