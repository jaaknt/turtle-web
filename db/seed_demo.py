# /// script
# requires-python = ">=3.12"
# dependencies = ["psycopg[binary]>=3.2"]
# ///
"""Seed the turtle-web demo database with deterministic synthetic data.

Run against the docker-compose database (schema already loaded from db/schema.sql):

    docker compose up -d --wait && uv run db/seed_demo.py

Everything is synthetic: made-up tickers (DEMOA.US ... DEMOH.US) with made-up names, and BENCH.US
as the benchmark. No real market or account data may ever enter this repository.

The data ends on the last weekday on or before --end-date (default: today), because the API's
queries are relative to CURRENT_DATE (signals from the last 90 days, the latest bar). With the
same --end-date, two runs produce identical rows: the random generator is seeded.

What it exercises, per docs/specs/web.md Step 2:
    - ~750 business days of bars per symbol, a geometric random walk
    - a 2:1 split in DEMOC.US while it is held: raw OHLC halves on the split date,
      adjusted_close stays continuous (before the split, adjusted_close = close / 2)
    - 8 buys and 1 partial sell, fee 1.00 each; one buy has no signal
    - ~40 signals in the last 90 days, ranking 30-80, exactly one scoring 44 (the gate
      boundary), and one on the last day with no next_open yet

Connection settings come from the same TURTLE_WEB_DB_* variables the API uses, defaulting to
the demo database. The script empties and refills its five tables, so it refuses to run against
a database that holds anything other than demo data.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal

import psycopg

SEED = 42
TRADING_DAYS = 750
BENCHMARK = "BENCH.US"
STRATEGY = "bk50d_s12_v2.0"
RANKING_STRATEGY = "qullamaggie"
GATE = 44
FEE = Decimal("1.00")
TAX = Decimal(0)

SYMBOLS = {
    "DEMOA.US": "Aurora Demo Holdings",
    "DEMOB.US": "Birch Demo Systems",
    "DEMOC.US": "Cobalt Demo Industries",
    "DEMOD.US": "Dune Demo Labs",
    "DEMOE.US": "Ember Demo Energy",
    "DEMOF.US": "Fjord Demo Logistics",
    "DEMOG.US": "Garnet Demo Health",
    "DEMOH.US": "Harbor Demo Software",
    BENCHMARK: "Demo Broad Market Index",
}

# GICS sector names, as the live turtle.company holds. DEMOF.US has no company row, as some live
# tickers have none.
SECTORS = {
    "DEMOA.US": "Financials",
    "DEMOB.US": "Information Technology",
    "DEMOC.US": "Industrials",
    "DEMOD.US": "Health Care",
    "DEMOE.US": "Energy",
    "DEMOG.US": "Health Care",
    "DEMOH.US": "Information Technology",
}
SPLIT_SYMBOL = "DEMOC.US"
SPLIT_DAYS_BEFORE_END = 60  # the split lands while DEMOC.US is held (bought 120 days before end)

# (symbol, trading days before the last day) for each buy; the buy fills at that day's open
BUYS = [
    ("DEMOA.US", 140),
    ("DEMOC.US", 120),
    ("DEMOB.US", 110),
    ("DEMOD.US", 80),
    ("DEMOE.US", 60),
    ("DEMOF.US", 45),
    ("DEMOG.US", 30),
    ("DEMOH.US", 12),
]
UNLINKED_BUY = "DEMOF.US"  # bought without a signal, as two of the live buys are
SELL = ("DEMOA.US", 20)  # sells half of the position

SIGNALS_IN_WINDOW = 40  # signals dated within the last 90 calendar days
WINDOW_CALENDAR_DAYS = 90


@dataclass
class Bar:
    """One daily bar, raw prices plus the split/dividend-adjusted close."""

    date: date
    open: float
    high: float
    low: float
    close: float
    adjusted_close: float
    volume: int


def business_days(end: date, count: int) -> list[date]:
    """Return the last `count` weekdays ending on or before `end`, oldest first.

    Args:
        end: Latest date allowed; rolled back to Friday if it falls on a weekend.
        count: Number of weekdays to return.

    Returns:
        list[date]: Ascending weekdays. Market holidays are ignored; this is demo data.
    """
    days: list[date] = []
    d = end
    while len(days) < count:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    return days[::-1]


def random_walk(rng: random.Random, days: list[date], split_index: int | None) -> list[Bar]:
    """Generate one symbol's bars as a geometric random walk.

    Args:
        rng: Seeded generator, shared across symbols so the whole dataset is reproducible.
        days: Trading calendar, oldest first.
        split_index: Index of a 2:1 split date, or None. Before it, raw prices are twice the
            adjusted series; from it on, raw equals adjusted.

    Returns:
        list[Bar]: One bar per day.
    """
    adjusted = rng.uniform(20, 150)
    drift = rng.uniform(-0.0002, 0.0012)
    vol = rng.uniform(0.012, 0.03)
    bars: list[Bar] = []
    prev_close = adjusted
    for i, d in enumerate(days):
        adjusted *= math.exp(rng.gauss(drift, vol))
        open_ = prev_close * (1 + rng.gauss(0, vol / 3))
        high = max(open_, adjusted) * (1 + rng.uniform(0, 0.03))
        low = min(open_, adjusted) * (1 - rng.uniform(0, 0.03))
        factor = 2.0 if split_index is not None and i < split_index else 1.0
        bars.append(
            Bar(
                date=d,
                open=round(open_ * factor, 4),
                high=round(high * factor, 4),
                low=round(low * factor, 4),
                close=round(adjusted * factor, 4),
                adjusted_close=round(adjusted, 4),
                volume=rng.randint(200_000, 5_000_000),
            )
        )
        prev_close = adjusted
    return bars


def benchmark_walk(rng: random.Random, days: list[date]) -> list[Bar]:
    """Generate the benchmark: lower volatility, steady upward drift, no split."""
    level = 400.0
    bars: list[Bar] = []
    prev = level
    for d in days:
        level *= math.exp(rng.gauss(0.0004, 0.01))
        open_ = prev * (1 + rng.gauss(0, 0.003))
        high = max(open_, level) * (1 + rng.uniform(0, 0.008))
        low = min(open_, level) * (1 - rng.uniform(0, 0.008))
        bars.append(
            Bar(d, round(open_, 4), round(high, 4), round(low, 4), round(level, 4), round(level, 4), rng.randint(50_000_000, 90_000_000))
        )
        prev = level
    return bars


def indicators(bars: list[Bar], i: int) -> dict[str, float]:
    """Signal-date indicators, matching the persisted keys in turtle.signal.parameters.

    pct_vs_sma50 compares the adjusted close with the mean of the 50 previous adjusted closes
    (the strategy's shift-1 SMA); adr_pct is the mean (high - low) / low over the 20 previous bars.

    Args:
        bars: One symbol's bars.
        i: Index of the signal date; needs at least 50 earlier bars.

    Returns:
        dict[str, float]: pct_vs_sma50 and adr_pct as fractions.
    """
    sma50 = sum(b.adjusted_close for b in bars[i - 50 : i]) / 50
    adr = sum((b.high - b.low) / b.low for b in bars[i - 20 : i]) / 20
    return {"pct_vs_sma50": bars[i].adjusted_close / sma50 - 1, "adr_pct": adr}


def money(x: float) -> Decimal:
    """Round to cents as a Decimal, so NUMERIC columns get exact values."""
    return Decimal(f"{x:.2f}")


def build(end: date) -> tuple[dict[str, list[Bar]], list[tuple], list[tuple]]:
    """Generate every row: bars per symbol, signals, and transactions.

    Args:
        end: Last date of the dataset.

    Returns:
        tuple: (bars by symbol, signal rows, transaction rows), ready to insert.
    """
    rng = random.Random(SEED)
    days = business_days(end, TRADING_DAYS)
    last = len(days) - 1
    split_index = last - SPLIT_DAYS_BEFORE_END

    bars = {s: random_walk(rng, days, split_index if s == SPLIT_SYMBOL else None) for s in SYMBOLS if s != BENCHMARK}
    bars[BENCHMARK] = benchmark_walk(rng, days)
    traded = [s for s in SYMBOLS if s != BENCHMARK]

    # Signals: (symbol, index, ranking). A linked buy fills the day after its signal.
    signals: list[tuple[str, int, int]] = []
    for symbol, before in BUYS:
        if symbol != UNLINKED_BUY:
            signals.append((symbol, last - before - 1, rng.randint(GATE + 1, 80)))

    window_start = end - timedelta(days=WINDOW_CALENDAR_DAYS)
    in_window = sum(1 for _, i, _ in signals if days[i] >= window_start)
    taken = {(s, i) for s, i, _ in signals}
    first_window_index = next(i for i, d in enumerate(days) if d >= window_start)

    # One signal on the last day (no next bar yet, so no next_open) and one exactly at the gate
    extras: list[tuple[str, int, int]] = [(traded[0], last, rng.randint(50, 80)), (traded[1], last - 15, GATE)]
    while in_window + len(extras) < SIGNALS_IN_WINDOW:
        symbol, i = rng.choice(traded), rng.randint(first_window_index, last - 1)
        ranking = rng.randint(30, 80)
        if (symbol, i) in taken or ranking == GATE or any(e[:2] == (symbol, i) for e in extras):
            continue
        extras.append((symbol, i, ranking))
    signals.extend(extras)
    signals.sort(key=lambda s: (s[1], s[0]))

    signal_rows: list[tuple] = []
    signal_id_by_key: dict[tuple[str, int], int] = {}
    for n, (symbol, i, ranking) in enumerate(signals, start=1):
        b = bars[symbol]
        params = indicators(b, i)
        if i < last:
            params["next_open"] = b[i + 1].open  # absent, never null, until the next bar exists
        signal_rows.append((n, STRATEGY, RANKING_STRATEGY, symbol, days[i], ranking, b[i].close, json.dumps(params)))
        signal_id_by_key[(symbol, i)] = n

    # Transactions, Lightyear conventions: buy net = qty * price, gross = net + fee;
    # sell gross = qty * price, net = gross - fee.
    txs: list[tuple] = []
    quantities: dict[str, int] = {}
    for symbol, before in BUYS:
        i = last - before
        price = money(bars[symbol][i].open * (1 + rng.uniform(-0.003, 0.006)))
        qty = max(1, int(1000 / float(price)))
        quantities[symbol] = qty
        net = price * qty
        signal_id = None if symbol == UNLINKED_BUY else signal_id_by_key[(symbol, i - 1)]
        at = datetime.combine(days[i], time(14, 30)) + timedelta(minutes=rng.randint(0, 300))
        txs.append((at, symbol, "buy", qty, "USD", price, net + FEE, FEE, TAX, net, signal_id))

    symbol, before = SELL
    i = last - before
    price = money(bars[symbol][i].open * (1 + rng.uniform(-0.003, 0.006)))
    qty = quantities[symbol] // 2
    gross = price * qty
    at = datetime.combine(days[i], time(14, 30)) + timedelta(minutes=rng.randint(0, 300))
    txs.append((at, symbol, "sell", qty, "USD", price, gross, FEE, TAX, gross - FEE, None))

    # References run in fill order, as the broker's do
    tx_rows = [(f"OR-DEMO{n:06d}", *tx) for n, tx in enumerate(sorted(txs), start=1)]

    return bars, signal_rows, tx_rows


def refuse_unless_demo(cur: psycopg.Cursor) -> None:
    """Raise if the target database holds anything but demo data.

    The seed truncates its tables. Pointing TURTLE_WEB_DB_HOST at the real database by mistake
    must fail here, before a single row is deleted.
    """
    cur.execute(
        "SELECT EXISTS (SELECT 1 FROM turtle.daily_bars WHERE symbol <> ALL(%s)),"
        "       EXISTS (SELECT 1 FROM turtle.lightyear_transaction WHERE reference NOT LIKE 'OR-DEMO%%')",
        (list(SYMBOLS),),
    )
    real_bars, real_tx = cur.fetchone()
    if real_bars or real_tx:
        raise SystemExit(
            "Refusing to seed: this database holds non-demo data. Point TURTLE_WEB_DB_* at the demo database (docker-compose.yml)."
        )


def main() -> None:
    """Parse arguments, generate the dataset, and replace the demo tables' contents."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--end-date", type=date.fromisoformat, default=date.today(), help="last date of the data (default: today)")
    args = parser.parse_args()

    bars, signal_rows, tx_rows = build(args.end_date)

    conninfo = {
        "host": os.environ.get("TURTLE_WEB_DB_HOST", "localhost"),
        "port": int(os.environ.get("TURTLE_WEB_DB_PORT", "5433")),
        "dbname": os.environ.get("TURTLE_WEB_DB_NAME", "trading"),
        "user": os.environ.get("TURTLE_WEB_DB_USER", "postgres"),
        "password": os.environ.get("TURTLE_WEB_DB_PASSWORD", "demo"),
    }
    with psycopg.connect(**conninfo) as conn, conn.cursor() as cur:
        refuse_unless_demo(cur)
        cur.execute("TRUNCATE turtle.daily_bars, turtle.ticker, turtle.company, turtle.signal, turtle.lightyear_transaction")
        cur.executemany("INSERT INTO turtle.ticker (code, name) VALUES (%s, %s)", list(SYMBOLS.items()))
        cur.executemany("INSERT INTO turtle.company (ticker_code, sector) VALUES (%s, %s)", list(SECTORS.items()))
        cur.executemany(
            "INSERT INTO turtle.daily_bars (symbol, date, open, high, low, close, adjusted_close, volume) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            [(s, b.date, b.open, b.high, b.low, b.close, b.adjusted_close, b.volume) for s, rows in bars.items() for b in rows],
        )
        cur.executemany(
            "INSERT INTO turtle.signal (id, trading_strategy, ranking_strategy, symbol, signal_date, ranking, signal_close, parameters)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            signal_rows,
        )
        cur.executemany(
            "INSERT INTO turtle.lightyear_transaction (reference, transacted_at, ticker_code, transaction_type, quantity, currency,"
            " price, gross_amount, fee, tax, net_amount, signal_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            tx_rows,
        )

    n_bars = sum(len(rows) for rows in bars.values())
    print(f"Seeded {conninfo['host']}:{conninfo['port']}/{conninfo['dbname']} through {bars[BENCHMARK][-1].date}:")
    print(f"  {len(SYMBOLS)} tickers, {n_bars} bars, {len(signal_rows)} signals, {len(tx_rows)} transactions")


if __name__ == "__main__":
    main()
