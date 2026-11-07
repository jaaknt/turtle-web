-- turtle-web demo schema: exactly the turtle tables and columns the API reads.
--
-- This is the contract with turtle-backtest, copied by hand from its Alembic migrations
-- (https://github.com/jaaknt/turtle-backtest, db/migrations/). A column rename over there must be
-- mirrored here. It is a subset: production tables carry more columns than the API needs.
--
-- Loaded by docker-compose.yml on first start and by CI; seeded by db/seed_demo.py.

CREATE SCHEMA turtle;

CREATE TABLE turtle.daily_bars (
    symbol TEXT NOT NULL, date DATE NOT NULL,
    open DOUBLE PRECISION, high DOUBLE PRECISION, low DOUBLE PRECISION,
    close DOUBLE PRECISION, adjusted_close DOUBLE PRECISION, volume BIGINT,
    CONSTRAINT pk_daily_bars PRIMARY KEY (symbol, date)
);

CREATE TABLE turtle.ticker (code TEXT PRIMARY KEY, name TEXT);

CREATE TABLE turtle.signal (
    id BIGINT PRIMARY KEY, trading_strategy TEXT NOT NULL, ranking_strategy TEXT NOT NULL,
    symbol TEXT NOT NULL, signal_date DATE NOT NULL, ranking SMALLINT, signal_close DOUBLE PRECISION,
    parameters JSONB NOT NULL DEFAULT '{}'
);

CREATE TABLE turtle.lightyear_transaction (
    reference TEXT PRIMARY KEY, transacted_at TIMESTAMP NOT NULL, ticker_code TEXT NOT NULL,
    transaction_type TEXT NOT NULL, quantity NUMERIC NOT NULL, currency TEXT NOT NULL,
    price NUMERIC NOT NULL, gross_amount NUMERIC, fee NUMERIC NOT NULL DEFAULT 0,
    tax NUMERIC NOT NULL DEFAULT 0, net_amount NUMERIC, signal_id BIGINT
);
