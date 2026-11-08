"""Compare analytics.py with quantstats on the real portfolio (docs/specs/portfolio.md, Step 4b).

Reads the database the API is configured for (TURTLE_WEB_* variables or api/.env). Run from api/:

    uv run --with quantstats==0.0.86 python scripts/compare_quantstats.py [--html /tmp/tearsheet.html]
"""

import argparse
import math
import sys

import quantstats as qs
from make_analytics_oracle import check_version, figures, to_series

from turtleweb import db, sql
from turtleweb.analytics import benchmark_returns, metrics, portfolio_returns
from turtleweb.settings import Settings


def same(ours: float | None, theirs: float) -> bool:
    if ours is None:  # a ratio over a zero denominator: quantstats gives NaN, 0 or ±inf there
        return math.isnan(theirs) or math.isinf(theirs) or theirs == 0
    return math.isclose(ours, theirs, rel_tol=1e-9, abs_tol=1e-12)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--html", help="also write quantstats' tear sheet here (outside the repository)")
    args = parser.parse_args()
    check_version()

    settings = Settings()
    engine = db.make_engine(settings)
    try:
        ledger = db.replay(engine, db.fetch(engine, sql.TRANSACTIONS), settings.benchmark_symbols)
    finally:
        engine.dispose()
    benchmark = settings.benchmark_symbols[0]  # Settings requires at least one
    returns, bench = portfolio_returns(ledger), benchmark_returns(ledger, benchmark)
    if len(returns.values) < 2:
        print("fewer than 2 days of returns: nothing to compare")
        return 0

    ours = metrics(returns, bench)
    print(f"{len(returns.values)} days, {returns.dates[0]} to {returns.dates[-1]}, beta and correlation vs {benchmark}\n")
    print(f"{'metric':<24}{'turtle-web':>16}{'quantstats':>16}  status")
    # quantstats' drawdown_details misses a drawdown that starts on day one (the spec's Step 4), and
    # a first day from fill price to close is often a loss: then only the longest drawdown may differ.
    day_one_loss = returns.values[0] < 0
    failed = []
    for name, theirs in figures(returns, bench).items():
        value = getattr(ours, name)
        if same(value, theirs):
            status = "ok"
        elif name == "longest_drawdown_days" and day_one_loss:
            status = "known: quantstats misses a drawdown starting on day one"
        else:
            status = "DIFFERS"
            failed.append(name)
        shown = "—" if value is None else f"{value:.10g}"
        print(f"{name:<24}{shown:>16}{theirs:>16.10g}  {status}")

    if args.html:
        qs.reports.html(to_series(returns), benchmark=to_series(bench), output=args.html, title="turtle-web portfolio")
        print(f"\ntear sheet: {args.html}")
    if failed:
        print(f"\n{len(failed)} metric(s) differ: {', '.join(failed)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
