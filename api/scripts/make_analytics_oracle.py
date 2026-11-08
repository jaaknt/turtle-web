"""Write tests/analytics_oracle.json: quantstats' figures on a fixed, seeded synthetic series.

Run from the repository root (docs/specs/portfolio.md, Step 4a):

    uv run --no-project --python 3.14 --with quantstats==0.0.86 python api/scripts/make_analytics_oracle.py
"""

import json
import random
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import quantstats as qs

sys.path.insert(0, str(Path(__file__).parent.parent))  # turtleweb, without installing the project
from turtleweb.analytics import Returns

QUANTSTATS = "0.0.86"
OUT = Path(__file__).parent.parent / "tests" / "analytics_oracle.json"


def check_version() -> None:
    if qs.__version__ != QUANTSTATS:
        raise SystemExit(f"quantstats {qs.__version__} found, {QUANTSTATS} expected")


def to_series(r: Returns) -> pd.Series:
    return pd.Series(r.values, index=pd.DatetimeIndex(r.dates))


def figures(r: Returns, benchmark: Returns) -> dict[str, float]:
    """quantstats' value for every analytics.Metrics field."""
    s, ret, b = qs.stats, to_series(r), to_series(benchmark)
    details = s.drawdown_details(s.to_drawdown_series(ret))
    expected = {
        "cumulative_return": s.comp(ret),
        "cagr": s.cagr(ret),
        "volatility": s.volatility(ret),
        "sharpe": s.sharpe(ret),
        "sortino": s.sortino(ret),
        "max_drawdown": s.max_drawdown(ret),
        "calmar": s.calmar(ret),
        "longest_drawdown_days": details["days"].max() if len(details) else 0,
        "best_day": s.best(ret),
        "worst_day": s.worst(ret),
        "best_month": s.best(ret, aggregate="ME"),
        "worst_month": s.worst(ret, aggregate="ME"),
        "win_rate_days": s.win_rate(ret),
        "win_rate_months": s.win_rate(ret, aggregate="ME"),
        "beta": s.greeks(ret, b)["beta"],
        "correlation": ret.corr(b),
    }
    return {k: float(v) for k, v in expected.items()}


def synthetic() -> tuple[Returns, Returns]:
    """300 business days: starts with a gain, has zero days and many recovering drawdowns, and ends under
    water a little above its low, so the open drawdown's valley is not its last day."""
    rng = random.Random(20261108)
    dates = [d.date() for d in pd.bdate_range(date(2025, 1, 2), periods=300)]
    returns: list[float] = []
    bench: list[float] = []
    for i in range(len(dates)):
        r = rng.gauss(0.0015, 0.012)
        if i == 0:
            r = 0.012  # quantstats misses a drawdown that starts on day one: start with a gain
        elif i % 37 == 0:
            r = 0.0  # zero days: left out of win rates
        elif i >= len(dates) - 5:
            r = 0.003  # a small bounce: the open drawdown's valley comes before the end
        elif i >= len(dates) - 20:
            r = -abs(r) - 0.004  # end under water: an ongoing drawdown
        returns.append(r)
        bench.append(0.6 * r + rng.gauss(0.0003, 0.007))
    return Returns(dates, returns), Returns(dates, bench)


def main() -> None:
    check_version()
    r, b = synthetic()
    details = qs.stats.drawdown_details(qs.stats.to_drawdown_series(to_series(r)))
    drawdowns = [  # by start date, as quantstats lists them; depth as a fraction, not a percentage
        {
            "start": str(row["start"])[:10],
            "valley": str(row["valley"])[:10],
            "end": str(row["end"])[:10],
            "days": int(row["days"]),
            "depth": float(row["max drawdown"]) / 100,
        }
        for _, row in details.iterrows()
    ]
    last = r.dates[-1].isoformat()
    recovered = [d for d in drawdowns if d["end"] != last and d["days"] >= 5]
    open_dd = drawdowns[-1]
    if len(recovered) < 3 or open_dd["end"] != last or open_dd["valley"] == last:
        raise SystemExit("the series needs 3+ recovered drawdowns and an open one whose valley is before its end")
    monthly = qs.utils.aggregate_returns(to_series(r), "ME")
    yearly = qs.utils.aggregate_returns(to_series(r), "YE")
    oracle = {
        "quantstats": QUANTSTATS,
        "dates": [d.isoformat() for d in r.dates],
        "returns": r.values,
        "benchmark": b.values,
        "metrics": figures(r, b),
        "monthly": [[int(y), int(m), float(v)] for (y, m), v in monthly.items()],
        "yearly": [[int(y), float(v)] for y, v in yearly.items()],
        "drawdowns": drawdowns,
    }
    OUT.write_text(json.dumps(oracle, indent=1) + "\n")
    print(f"wrote {OUT}: {len(r.dates)} days, {len(drawdowns)} drawdowns")


if __name__ == "__main__":
    main()
