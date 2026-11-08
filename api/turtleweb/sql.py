"""Every SQL statement the API runs: this module is the whole data layer.

Money is cast to float8 in SQL. Pydantic serialises Decimal as a JSON string, which would make
every number on the frontend a string.

Every daily_bars access is `symbol = ? AND date >= ?` (or `symbol = ANY(?)`), a prefix match on
pk_daily_bars, the table's only index. tests/test_sql_plans.py holds them to that.
"""

import sqlalchemy as sa

# Every fill, with the signal it was bought off
TRANSACTIONS = sa.text("""
SELECT t.reference, t.transacted_at, t.ticker_code AS symbol, tk.name, t.transaction_type AS side,
       t.quantity::float8 AS quantity, t.price::float8 AS price, t.fee::float8 AS fee, t.tax::float8 AS tax,
       t.currency, t.signal_id, s.signal_date, s.ranking,
       (s.parameters->>'next_open')::float8 AS next_open
FROM turtle.lightyear_transaction t
LEFT JOIN turtle.ticker tk ON tk.code = t.ticker_code
LEFT JOIN turtle.signal s  ON s.id = t.signal_id
ORDER BY t.transacted_at
""")

# Everything the ledger needs, in one query. :symbols is the distinct transaction symbols plus the
# benchmark (psycopg adapts a list[str] to an array); :start is the first transaction date minus
# 7 days, so the ledger can seed last-known prices for a fill on a day without a bar.
CLOSES = sa.text("""
SELECT symbol, date, close::float8 AS close, adjusted_close::float8 AS adjusted_close
FROM turtle.daily_bars
WHERE symbol = ANY(:symbols) AND date >= :start AND close > 0 AND adjusted_close > 0
ORDER BY date, symbol
""")

# One symbol's chart. Every price must be positive: a NULL open/high/low would break the candle,
# and a 0 adjusted_close would put a raw price into an adjusted series.
BARS = sa.text("""
SELECT date, open::float8 AS open, high::float8 AS high, low::float8 AS low, close::float8 AS close,
       adjusted_close::float8 AS adjusted_close, volume
FROM turtle.daily_bars
WHERE symbol = :symbol AND date >= :start
  AND open > 0 AND high > 0 AND low > 0 AND close > 0 AND adjusted_close > 0
ORDER BY date
""")

# The signals page. The indicators are read from parameters, frozen as of the signal date, never
# re-derived. The gate is `>= :min_ranking`: signals are stored ungated, and a signal scoring
# exactly the gate is kept. ranking_strategy is filtered too, because gate values only mean
# something on one scheme's scale. entry_* stays NULL until the bar after signal_date is loaded.
# Bar filters match turtlex's, so a bad adjusted_close = 0 row never shows as a -100% change.
# Both laterals are date-bounded, which keeps each to a single index probe.
SIGNALS = sa.text("""
SELECT s.id, s.symbol, t.name, s.signal_date, s.ranking,
       (s.parameters->>'next_open')::float8    AS next_open,
       (s.parameters->>'pct_vs_sma50')::float8 AS pct_vs_sma50,
       (s.parameters->>'adr_pct')::float8      AS adr_pct,
       e.entry_date, e.entry_price,                                  -- RAW open: recognisable
       last.close AS curr_price, last.date AS curr_date,             -- RAW close; staleness visible
       last.adj_close / e.entry_adj - 1.0 AS change_pct,             -- ADJUSTED: split-safe total return, a fraction
       EXISTS (SELECT 1 FROM turtle.lightyear_transaction lt WHERE lt.signal_id = s.id) AS bought
FROM turtle.signal s
LEFT JOIN turtle.ticker t ON t.code = s.symbol
LEFT JOIN LATERAL (
    SELECT b.date AS entry_date, b.open::float8 AS entry_price,
           b.open * b.adjusted_close / b.close AS entry_adj
    FROM turtle.daily_bars b
    WHERE b.symbol = s.symbol AND b.date > s.signal_date AND b.date <= s.signal_date + 10
      AND b.close > 0 AND b.adjusted_close > 0 AND b.volume > 0
    ORDER BY b.date LIMIT 1
) e ON TRUE
LEFT JOIN LATERAL (
    SELECT b.date, b.close::float8 AS close, b.adjusted_close AS adj_close
    FROM turtle.daily_bars b
    WHERE b.symbol = s.symbol AND b.date > CURRENT_DATE - 400
      AND b.close > 0 AND b.adjusted_close > 0 AND b.volume > 0
    ORDER BY b.date DESC LIMIT 1
) last ON TRUE
WHERE s.trading_strategy = :strategy
  AND s.ranking_strategy = :ranking_strategy
  AND s.signal_date >= CURRENT_DATE - CAST(:days AS int)
  AND s.ranking >= :min_ranking
ORDER BY s.signal_date DESC, s.ranking DESC
""")

# Every symbol with bars, for the chart page's search. SELECT DISTINCT would read the whole table;
# this loose index scan does one `min(symbol) WHERE symbol > ?` index probe per symbol instead
# (PostgreSQL 17 has no native skip scan). Loaded on first use and cached for an hour.
SYMBOLS = sa.text("""
WITH RECURSIVE syms AS (
    (SELECT min(symbol) AS symbol FROM turtle.daily_bars)
    UNION ALL
    SELECT (SELECT min(b.symbol) FROM turtle.daily_bars b WHERE b.symbol > s.symbol)
    FROM syms s WHERE s.symbol IS NOT NULL
)
SELECT s.symbol, t.name
FROM syms s LEFT JOIN turtle.ticker t ON t.code = s.symbol
WHERE s.symbol IS NOT NULL
ORDER BY s.symbol
""")
