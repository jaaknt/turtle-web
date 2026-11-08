# Design: `turtle-web` — a FastAPI + Vue + Lightweight Charts dashboard

> **Status:** Being implemented step by step; each step is marked **Done** as it lands. Step 0,
> the one precondition in [turtle-backtest](https://github.com/jaaknt/turtle-backtest), is done:
> the `turtle_web` role is in its `db/init.sh` and exists on both the VPS and the local database
> (validated 2026-11-08). The signal persistence this spec used to describe has shipped; see
> [the appendix](#appendix--what-shipped-from-the-previous-draft). This spec moved here from
> turtle-backtest's `docs/specs/web.md` on 2026-11-08; paths such as `db/init.sh`,
> `docs/implementation.md` and `deploy/eodhd-download-daily.service` refer to turtle-backtest
> unless they are under `api/`, `web/` or this repository's `db/` and `deploy/` trees.

## Context

`turtle-backtest` produces everything through CLIs that print to stdout. To see what you hold,
what it is worth, or a chart with your own fills marked on it, you run a script and read a
fixed-width table in a terminal.

This document is a **step-by-step guide** to building a separate, open-source, read-only
dashboard over the `turtle` schema. It covers five things:

1. **Portfolio** — current value, cost basis, unrealized and realized P&L, per-position table.
2. **Portfolio over time** — holdings value vs cost basis, and P&L vs a benchmark.
3. **Transactions** — every Lightyear fill, joined to the signal it was bought off.
4. **Price history** — candlestick chart for any symbol, with your fills and average cost marked.
5. **Signals** — what the baseline algorithm fired over the last 3 months, how each has moved since
   entry, and which ones you actually bought.

### Decisions

| Decision | Choice |
| --- | --- |
| Repo | New **public** GitHub repo `turtle-web`, MIT licence. Does **not** import `turtlex` |
| Backend | FastAPI, sync SQLAlchemy Core with raw SQL strings, no ORM |
| Frontend | Vue 3 + Vite + TypeScript, `vue-router`, PrimeVue `DataTable` for tables |
| Charts | TradingView **Lightweight Charts v5** from npm (Apache-2.0) |
| Price data | Served from `turtle.daily_bars` — the library ships no data of its own |
| Portfolio | **Real** Lightyear transactions, not the simulated backtest portfolio |
| Access | Strictly read-only: `turtle_web` role with `default_transaction_read_only = on` |
| Serving | FastAPI serves the built SPA from `web/dist` — one process, one systemd unit, same origin, no CORS |
| Build | GitHub Actions builds the frontend; the VPS never runs Node |
| Deployment | Hetzner VPS, bound to the Tailscale IP, no TLS or auth |

### What changed from the previous draft

The previous draft recommended FastAPI + Jinja2 with no npm and no build step, and rejected a
JS-framework frontend as "a second toolchain for a page only you can reach". Two things moved
that trade-off:

- **The repo is public.** A familiar SPA stack and a clean JSON API are what make an
  open-source project something others can run, read and contribute to.
- **GitHub Actions removes the toolchain objection.** CI builds `dist/`; the VPS downloads a
  release artifact and never needs Node.

The React-specific trap the old draft cited (StrictMode double-mounting two overlaid charts)
does not exist in Vue: `onMounted` runs once and `onBeforeUnmount` is the single cleanup point.

## Architecture

```text
GitHub: turtle-web (public)
├── api/   FastAPI ── sync Engine (turtle_web, read-only) ──SELECT──> PostgreSQL turtle schema
├── web/   Vue 3 + Vite + TS + lightweight-charts ──fetch /api/*──> api
└── db/    schema.sql (the columns we read) + seed_demo.py (synthetic data)

Dev:   Vite :5173 ──proxy /api──> uvicorn :8000 ──> docker-compose Postgres :5433 (demo data)
Prod:  Browser ──Tailscale──> uvicorn :8080 ├── /api/*  JSON
                                            └── /*      web/dist (SPA, index.html fallback)
CI:    lint + type-check + test (against demo DB) → on tag: release web-dist.tgz
```

Two layers of logic, nothing more:

- **SQL** (`api/turtleweb/sql.py`) fetches rows. Six statements, all index-bounded.
- **The ledger** (`api/turtleweb/ledger.py`) turns transactions + closes into positions, P&L and
  a daily history. Pure Python, no I/O, fully unit-tested. Average-cost accounting is
  sequential, which is awkward in SQL and twenty clear lines in Python — and the data is tiny
  (22 transactions, ~2,100 close rows).

No repository classes, no service layer, no Pinia store: six queries and four pages do not
need them.

## The P&L model

These definitions are the contract every page follows. Put them in the README and in a page
footer.

| Quantity | Definition |
| --- | --- |
| Buy cost | `price × quantity + fee + tax`. Verified: equals `gross_amount` on every live buy |
| Sell proceeds | `price × quantity − fee − tax` — **unverified**, there are no sells yet (see caveats) |
| Cost basis | Average-cost method. A sell removes `cost × (sold / held)`; the per-share average is unchanged |
| Realized P&L | Σ over sells of `proceeds − cost removed` |
| Market value | `units × adjusted_close`, where each fill adds `units += quantity / f` and `f = adjusted_close / close` on the fill date |
| Unrealized P&L | `market value − cost basis` |
| Total P&L | `unrealized + realized` |
| Benchmark P&L | A shadow portfolio: every buy spends the same cash on the benchmark (default `SPY.US`), every sell sells the same fraction of that position's shadow |

**Why `units` instead of `shares × close`.** The Lightyear importer keeps only Buy/Sell rows, so a
split never appears as a transaction. `shares × close` would show a 2:1 split as a 50% loss.
`units` expresses the position in `adjusted_close` terms, so splits cancel exactly and dividends
paid since the fill are included (total return). `f` is recomputed from current data on every
request. EODHD rewrites `adjusted_close` retroactively, but it rewrites both ends of the ratio, so
the result stays correct.

**Caveats the page must state:**

- **Not an equity curve.** Deposits, withdrawals, dividends and FX are never imported, so cash
  is unknowable. Label the chart "Holdings value vs cost basis", never "Equity".
- **USD only.** The importer keeps USD rows only.
- **Dividends sit inside market value.** `adjusted_close` folds dividends into the price, while
  Lightyear pays them out as cash that the importer never sees. Total P&L therefore tracks the
  broker's position value plus dividends received, so a per-position value reads slightly above
  Lightyear's.
- **Shares follow the broker.** A split while a position is held rescales its share count
  (detected from the bars, as there is no split table), so the Shares column matches Lightyear's.
  Market value never depends on it.
- **Sell semantics are unverified.** When the first sell lands, check the proceeds formula
  against the statement's `gross_amount`/`net_amount` and add that row as a ledger test fixture.
- **Prices are forward-filled.** A symbol with no bar on a given day (halt, delisting) keeps its
  last close. Each position reports `last_date`, so staleness is visible rather than silent.

## Step-by-step build

### Step 0 — Read-only role (in `turtle-backtest`)

The only change in turtle-backtest: a `turtle_web` role that mirrors the `claude` role, plus four
role-level settings that role lacks. `claude` is an MCP client; this one is a network service. The
SQL lives in turtle-backtest's **[`db/init.sh`](https://github.com/jaaknt/turtle-backtest/blob/main/db/init.sh)** (the `turtle_web` block), the single source this section describes
rather than copies:

- `GRANT SELECT` on every existing `turtle` table, and default privileges for tables `alembic`
  creates later.
- `default_transaction_read_only = on`, `statement_timeout = '10s'` (one bad query can't wedge a
  worker), `idle_in_transaction_session_timeout = '30s'`, and `jit = off`.
- The password comes from `DB_WEB_PASSWORD`. `init.sh` refuses to run if it is unset or empty,
  and binds it with `\getenv` so a quote in the password is harmless.

- **`GRANT SELECT` is the barrier; `default_transaction_read_only = on` is a guard rail.** The
  session default turns an accidental write from app code into an immediate, explicit error.
  But it is only a default: any session can `SET default_transaction_read_only = off` or
  `BEGIN READ WRITE`. It does **not** protect against the role's grants being widened later.
  Never grant `turtle_web` anything beyond `SELECT`.
- **`jit = off` is not cosmetic.** Measured on this database, JIT compilation was 352 ms of a
  1,472 ms query. Row-count misestimates on small results routinely trip the JIT threshold
  here, and every query in this app returns few rows.

**Done.** Applied by hand to the VPS and local databases and validated on 2026-11-08 (see below).
The role is in turtle-backtest's `db/init.sh` for fresh installs, with its password in
`DB_WEB_PASSWORD` (`docker-compose.yml`, `.env.example`). A database that already exists — the
VPS, or a local Docker volume — needs it added once, as `postgres` and not through MCP. The command
is in turtle-backtest's [`docs/implementation.md`](https://github.com/jaaknt/turtle-backtest/blob/main/docs/implementation.md), §"Add the `turtle_web` role to an existing database".

Verified on a throwaway Postgres 17 container, both from a fresh `init.sh` and by applying the
documented command to a database initialised without the role:

- SELECT works, on tables that existed before the role and on a table `alembic` creates afterwards.
- An INSERT fails with *cannot execute INSERT in a read-only transaction*.
- After `SET default_transaction_read_only = off` or `BEGIN READ WRITE`, the INSERT still fails,
  with *permission denied for table*.
- The role reports `default_transaction_read_only = on`, `statement_timeout = 10s`,
  `idle_in_transaction_session_timeout = 30s` and `jit = off`.

Validated live on 2026-11-08 against both the VPS (over Tailscale, with SSL) and the local
database, by logging in as `turtle_web` and reading the catalogs:

- Login works with `DB_WEB_PASSWORD`.
- The role is not superuser and cannot create databases or roles, replicate, or bypass row-level
  security. It belongs to no other role and owns no objects.
- SELECT on all 9 `turtle` tables, and no other table privilege anywhere.
- `turtle_web=r/alembic` in the `turtle` default privileges, so future migration tables are readable.
- The session settings read `on | 10s | 30s | off`.
- Both INSERT checks were rejected with the expected errors.

**Verify:** run the verification block in turtle-backtest's `docs/implementation.md`, §"Add the `turtle_web` role
to an existing database". It works the same after a fresh `init.sh`. It checks that reads work,
that the four settings read `on | 10s | 30s | off`, that an INSERT is rejected as *read-only*, and
that the INSERT is still rejected as *permission denied* once the read-only default is
overridden. Both INSERTs run inside a rolled-back transaction.

### Step 1 — Create the repository

**Done.** [`jaaknt/turtle-web`](https://github.com/jaaknt/turtle-web) created 2026-11-08 (the repo
itself was made in the GitHub UI, since the fine-grained token cannot create repositories).

```bash
gh repo create turtle-web --public --license mit --gitignore Python --clone
cd turtle-web
mkdir -p api/turtleweb api/tests db deploy .github/workflows
npm create vite@latest web -- --template vue-ts
```

Then, before the first real commit:

1. **Extend `.gitignore`:** `.env`, `*.env`, `web/node_modules/`, `web/dist/`, `*.dump`, `*.csv`.
2. **Enable secret scanning and push protection** (repo Settings → Code security — both are free
   for public repos). Enable **Dependabot** for `pip`, `npm` and `github-actions`.
3. **Add `NOTICE`** crediting TradingView Lightweight Charts (Apache-2.0 requires it). If you turn
   off the chart's `attributionLogo`, you must credit TradingView visibly in the UI instead. Put a
   link in the page footer either way.
4. **README rule — no real data, ever.** No exported `daily_bars` rows (EODHD's terms forbid
   redistribution), no real positions in fixtures, screenshots or issues. Screenshots come from
   the demo database.

Target layout:

```text
turtle-web/
├── LICENSE  NOTICE  README.md  docker-compose.yml  .env.example
├── db/
│   ├── schema.sql            # DDL for exactly the columns the API reads
│   └── seed_demo.py          # deterministic synthetic data
├── api/
│   ├── pyproject.toml  uv.lock
│   ├── turtleweb/
│   │   ├── settings.py       # pydantic-settings, env only
│   │   ├── db.py             # Engine factory
│   │   ├── sql.py            # every SQL string — the whole data layer
│   │   ├── ledger.py         # transactions + closes -> positions, P&L, history
│   │   ├── models.py         # pydantic response models (-> OpenAPI -> TS types)
│   │   ├── routes.py         # /api/* endpoints
│   │   └── main.py           # create_app(): lifespan, router, SPA static mount
│   └── tests/{test_main.py,test_ledger.py,test_routes.py,test_sql_plans.py}
├── web/
│   ├── package.json  package-lock.json  vite.config.ts
│   └── src/
│       ├── main.ts  router.ts  format.ts
│       ├── api/{client.ts,schema.d.ts}   # schema.d.ts generated, committed
│       ├── components/{PriceChart.vue,LineChart.vue,KpiTile.vue}
│       └── views/{PortfolioView.vue,TransactionsView.vue,ChartView.vue,SignalsView.vue}
├── deploy/{turtle-web.service,deploy.sh}
└── .github/workflows/{ci.yml,release.yml}
```

**Verify:** the repo is public, push protection is on, and `git status` is clean after `npm install`.

### Step 2 — Demo database

**Done.** Implemented in `turtle-web` 2026-11-08.

A public repo is only runnable if it doesn't need your database. `db/schema.sql` is the
**contract**: the subset of `turtle` tables and columns the API reads, copied by hand from
`turtle-backtest`'s migrations. A column rename over there must be mirrored here.

```sql
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
```

`db/seed_demo.py` is a standalone [uv script](https://docs.astral.sh/uv/guides/scripts/) with
inline dependencies (`psycopg`), so it runs before `api/` exists and needs no venv:
`uv run db/seed_demo.py`. Its generator is seeded, so the same `--end-date` (default: today)
always produces identical rows. It truncates its four tables, so it first refuses to run if the
target holds any non-demo symbol or transaction reference.

- **Symbols:** 8 synthetic tickers (`DEMOA.US` … `DEMOH.US`) plus `BENCH.US` as the benchmark.
  Use made-up names, so no real company's price is implied.
- **Bars:** about 750 business days of a geometric random walk. `high`/`low` sit a random 0–3%
  outside `open`/`close`, and `volume` is random.
- **One 2:1 split** in `DEMOC.US`, a few months after its buy. From the split date, raw
  OHLC halves while `adjusted_close` stays continuous (earlier `adjusted_close = close / 2`).
  This is what proves the ledger is split-safe.
- **Transactions:** 8 buys and **one partial sell**, with `fee = 1.00`, exercising every branch of
  the ledger.
- **Signals:** about 40 rows labelled `bk50d_s12_v2.0` / `qullamaggie` over the last 90 days, with `ranking` spread
  across 30–80, and `parameters` carrying `next_open`, `pct_vs_sma50` and `adr_pct`. Include
  **one signal at exactly 44**, so the `>= 44` gate is tested at its boundary. Also include a signal
  from the last day with no `next_open` yet, as the nightly run produces. Link most buys to a
  signal; leave one buy unlinked (`signal_id NULL`), as real ones can be.

`docker-compose.yml` — port **5433** so it never collides with a local `turtle` Postgres on 5432:

```yaml
services:
  db:
    image: postgres:17
    environment:
      POSTGRES_DB: trading
      POSTGRES_PASSWORD: demo
    ports: ["5433:5432"]
    volumes:
      - ./db/schema.sql:/docker-entrypoint-initdb.d/01-schema.sql:ro
    healthcheck:   # lets `docker compose up --wait` return only once Postgres accepts connections
      test: ["CMD-SHELL", "pg_isready -U postgres -d trading"]
      interval: 2s
      timeout: 3s
      retries: 30
```

`.env.example` (copied to `api/.env` for dev):

```dotenv
TURTLE_WEB_DB_HOST=localhost
TURTLE_WEB_DB_PORT=5433
TURTLE_WEB_DB_USER=postgres
TURTLE_WEB_DB_PASSWORD=demo
TURTLE_WEB_BENCHMARK_SYMBOL=BENCH.US
```

**Verify:** `docker compose up -d --wait && uv run db/seed_demo.py`, then
`SELECT count(*) FROM turtle.daily_bars` returns about 6,750 rows (9 symbols × ~750 days).

### Step 3 — API skeleton

**Done.** Implemented in `turtle-web` 2026-11-08.

```bash
cd api
uv init --package --name turtleweb --python 3.14
uv add fastapi "uvicorn[standard]" sqlalchemy "psycopg[binary,pool]" pydantic-settings
uv add --dev pytest httpx2 ruff mypy
```

`uv init --package` creates a `src/` layout. Move the package to `api/turtleweb/` to match the
target layout, and set `[tool.uv.build-backend] module-root = ""`. The test client needs
`httpx2`, not `httpx`: Starlette deprecated `httpx` for its `TestClient`.

Use `fastapi`, **not** `fastapi[standard]`. The extra pulls in the CLI, `email-validator` and
`python-multipart`, none of which a GET-only API uses. Polars, pandas and numpy are also
deliberately absent: the data volume is tiny, and pure Python keeps the dependency list short
for contributors.

`turtleweb/settings.py`: environment only. There is no TOML and no profiles, because a server
has one deployment shape:

```python
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from TURTLE_WEB_* environment variables and api/.env."""

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
```

`turtleweb/db.py`: engine-level guards, applied once. The `options` repeat the role settings so
the demo database (where you connect as `postgres`) is read-only too:

```python
def make_engine(s: Settings) -> sa.Engine:
    """Build the read-only connection pool."""
    url = sa.URL.create(
        "postgresql+psycopg", username=s.db_user, password=s.db_password, host=s.db_host, port=s.db_port, database=s.db_name
    )
    return sa.create_engine(
        url,
        pool_size=2,
        max_overflow=2,
        pool_pre_ping=True,
        connect_args={"options": "-c default_transaction_read_only=on -c statement_timeout=10000 -c jit=off"},
    )
```

`turtleweb/main.py`: an app factory, so tests and the OpenAPI export can build the app without
a database:

```python
class SpaStaticFiles(StaticFiles):
    """Serve web/dist; unknown non-API paths get index.html so deep links like /chart/AAPL.US work."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404 or path.startswith("api/"):
                raise
            return await super().get_response("index.html", scope)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI app; settings default to the environment."""
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = make_engine(settings)
        app.state.engine = engine
        app.state.settings = settings
        app.state.symbols = None  # loaded on first /api/symbols request, see Step 4
        yield
        engine.dispose()

    app = FastAPI(title="turtle-web", lifespan=lifespan)
    app.include_router(router, prefix="/api")
    if settings.static_dir:
        app.mount("/", SpaStaticFiles(directory=settings.static_dir, html=True), name="spa")  # last
    return app
```

**Startup must not touch the database.** `create_engine` connects lazily, and nothing in the
lifespan queries. That matters on this VPS: after a reboot Postgres refuses connections until it
is restarted. An app that queried at startup would exhaust systemd's restart limit and stay down
after Postgres recovered. Instead, the first request after recovery simply succeeds.
`/api/healthz` likewise answers without a query.

Write every endpoint as plain `def`, **not** `async def`. The engine is sync, and FastAPI runs
`def` endpoints in a threadpool. An `async def` endpoint calling a sync engine blocks the event
loop.

**Verify:** `uv run uvicorn --factory turtleweb.main:create_app --reload` returns 200 on
`curl localhost:8000/api/healthz`.

### Step 4 — The SQL module

**Done.** Implemented in `turtle-web` 2026-11-08, with the plans re-checked on the live database
(see Verify).

Put every statement in `turtleweb/sql.py` as module-level constants; that module *is* the data
layer. Cast money to `float8` in SQL. Pydantic serialises `Decimal` as a JSON **string**, which
would make every number on the frontend a string.

```sql
-- TRANSACTIONS: every fill, with the signal it was bought off (22 rows today)
SELECT t.reference, t.transacted_at, t.ticker_code AS symbol, tk.name, t.transaction_type AS side,
       t.quantity::float8, t.price::float8, t.fee::float8, t.tax::float8, t.currency,
       t.signal_id, s.signal_date, s.ranking,
       (s.parameters->>'next_open')::float8 AS next_open
FROM turtle.lightyear_transaction t
LEFT JOIN turtle.ticker tk ON tk.code = t.ticker_code
LEFT JOIN turtle.signal s  ON s.id = t.signal_id
ORDER BY t.transacted_at;

-- CLOSES: everything the ledger needs, in one query — 14 ms on the live DB
SELECT symbol, date, close::float8, adjusted_close::float8
FROM turtle.daily_bars
WHERE symbol = ANY(:symbols) AND date >= :start AND close > 0 AND adjusted_close > 0
ORDER BY date, symbol;

-- BARS: one symbol's chart — ~1 ms
SELECT date, open::float8, high::float8, low::float8, close::float8,
       adjusted_close::float8, volume
FROM turtle.daily_bars
WHERE symbol = :symbol AND date >= :start
  AND open > 0 AND high > 0 AND low > 0 AND close > 0 AND adjusted_close > 0
ORDER BY date;

-- SIGNALS: the signals page — 8 ms on the live DB for 63 rows (90 days, R >= 44)
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
ORDER BY s.signal_date DESC, s.ranking DESC;
```

Notes on SIGNALS:

- **The indicators are read, not re-derived.** `turtle.signal.parameters` freezes `pct_vs_sma50`
  and `adr_pct` as of the signal date ([persist-signal.md](https://github.com/jaaknt/turtle-backtest/blob/main/docs/specs/persist-signal.md)). The earlier draft
  re-computed them in a window-function lateral that cost 92 ms with a mandatory 130-day bound,
  and 2,851 ms without it. That lateral, its bound, and its dividend-drift caveat are all gone.
- **The gate is `>= 44`, not `> 44`.** Signals are stored ungated, so the reader applies the
  gate. Three live signals in the window score exactly 44.
- **Filter on `ranking_strategy` too.** `turtle.signal`'s unique key leaves it out, so a re-run
  under another ranking scheme overwrites `ranking` in place. Gate values are scheme-relative,
  so `>= 44` applied to another scheme's scores would silently select the wrong rows.
- **`entry_*` is NULL until the bar after `signal_date` is loaded**, i.e. for signals from the
  last trading day. Render it as "pending", not 0. It comes from `daily_bars`, not from
  `next_open`. The two can disagree for about a day: `next_open` is only filled when the nightly
  7-day re-scan next runs, so a signal can have an `entry_price` while `next_open` is still
  absent. The transactions page's slippage uses `next_open` and shows "—" until it lands.
- **Every bar filter in SIGNALS matches turtlex's** (`close > 0 AND adjusted_close > 0 AND
  volume > 0`). A bad row with `adjusted_close = 0` would otherwise show a −100% change. CLOSES
  deliberately keeps zero-volume days, so a held position still has a price on a halted day.
- **Both laterals are bounded.** `signal_date + 10` and `CURRENT_DATE - 400` keep each one to a
  single index probe. The plan shows `Index Scan using pk_daily_bars` for the entry bar and
  `Index Scan Backward` for the latest bar, each with a `date` bound in `Index Cond`.
- **`turtle.signal` is seq-scanned** (306 rows today). Once it reaches tens of thousands of rows,
  consider an index on `(trading_strategy, signal_date)` in a turtle-backtest migration, not here.

`:symbols` for CLOSES is the distinct transaction symbols plus the benchmark. `:start` is the
first transaction date minus 7 days. The ledger seeds its last-known prices from those earlier
closes (Step 5), so a fill on a day its symbol has no bar still has a prior close. psycopg adapts
a Python `list[str]` to a Postgres array for `ANY(:symbols)`. The plan is
`Index Scan using pk_daily_bars` with both `symbol = ANY(...)` and `date >=` in the
`Index Cond`.

**SYMBOLS — about 105 ms warm, loaded on the first `/api/symbols` request.** The obvious
`SELECT DISTINCT symbol FROM daily_bars` is a full 20M-row seq scan (1,472 ms). Use a loose index
scan instead. It is index-only and needs no new index:

```sql
WITH RECURSIVE syms AS (
    (SELECT min(symbol) AS symbol FROM turtle.daily_bars)
    UNION ALL
    SELECT (SELECT min(b.symbol) FROM turtle.daily_bars b WHERE b.symbol > s.symbol)
    FROM syms s WHERE s.symbol IS NOT NULL
)
SELECT s.symbol, t.name
FROM syms s LEFT JOIN turtle.ticker t ON t.code = s.symbol
WHERE s.symbol IS NOT NULL
ORDER BY s.symbol;  -- the recursion yields ascending order, but only ORDER BY guarantees it (~3 ms)
```

PostgreSQL 17 has no native skip scan. The recursive CTE does about 5,600 `min(symbol) WHERE
symbol > ?` index probes instead of reading 20 million index entries. Load it on the first
`/api/symbols` request and keep it in `app.state.symbols` (not in the lifespan — see Step 3). Two
concurrent first requests may both load it, which is harmless. About 180 KB raw, about 60 KB
gzipped, fetched once by the chart page.

**Verify:** run each statement under `EXPLAIN` as `turtle_web` against the live database. Every
`daily_bars` access must show `Index Scan using pk_daily_bars` with both a `symbol` and a `date`
bound.

`tests/test_sql_plans.py` holds the demo database to the same rule. The demo tables are tiny, so
the planner would seq-scan them; the test turns off sequential and bitmap scans and then asserts
that every `daily_bars` node is an index scan on `pk_daily_bars` with a `symbol` and `date` bound.
SYMBOLS is only checked for the index scan itself: its probes have a `symbol` bound and no `date`
bound by design, and its first `min()` has no bound at all. If the latest demo bar is more than
7 days old, the database tests fail and ask you to re-seed, because the queries use
`CURRENT_DATE` windows.

Live re-check, 2026-11-08: SIGNALS returned 63 rows in 8 ms, CLOSES in 14 ms, and BARS
took under 1 ms, each with the expected plan. SYMBOLS took 105 ms warm and 1.2 s on a cold cache.
Its index-only scans still did 5,270 heap fetches, because autovacuum had not run on `daily_bars`
since 2026-07-19 and the visibility map was stale (Open item 6).

### Step 5 — The ledger

**Done.** Implemented in `turtle-web` 2026-11-08.

`turtleweb/ledger.py` is the heart of the app and the part most worth testing. It is a pure
function from transactions and closes to positions and history.

```python
@dataclass(frozen=True)
class Fill:
    date: date
    symbol: str
    side: str  # 'buy' | 'sell'
    quantity: float
    price: float
    fee: float
    tax: float


@dataclass(frozen=True)
class Close:
    symbol: str
    date: date
    close: float
    adjusted_close: float


@dataclass
class _Position:
    shares: float = 0.0  # as the broker counts them: rescaled by every split while held
    units: float = 0.0  # shares in adjusted_close terms: sum of quantity / f at each fill
    cost: float = 0.0  # open cost basis, average-cost method, fees and tax included
    realized: float = 0.0
    bench_units: float = 0.0  # shadow position in the benchmark
    bench_realized: float = 0.0
    first_buy: date | None = None


def build(fills: list[Fill], closes: list[Close], benchmark: str) -> Ledger:
    """Replay fills over the benchmark's trading calendar.

    Args:
        fills: Every transaction, in any order; applied by date, stable within a day.
        closes: Daily closes for every traded symbol and the benchmark.
        benchmark: Symbol whose dates (plus any fill date after its last bar) form the calendar,
            and which the shadow portfolio buys.

    Returns:
        Ledger: Open positions as of the last day, totals, and one history point per day.
    """
```

The calendar is the benchmark's dates from the first fill on, **plus any fill date after the
benchmark's last bar**. A fill imported before that day's bars are loaded would otherwise drop
out; with its own day it counts, valued at the previous close. Earlier fill dates are not added:
an after-hours fill whose UTC date rolls into a Saturday lands on Monday instead of creating a
weekend point.

The loop, per calendar day `d`:

1. Take in every close dated `≤ d` into `last[symbol]`. Missing days keep the previous close
   (forward fill), and on the first day this seeds prices from the 7-day lookback CLOSES fetches,
   so a first fill on a day its symbol has no bar (a halt) still has a prior close. **On a split,
   rescale `shares`** of a held symbol (see below).
2. Apply every fill dated `≤ d` not yet applied, using `f = last[s].adjusted_close / last[s].close`
   and `b = last[benchmark].adjusted_close`:
   - **buy:** `amount = q·price + fee + tax`; `shares += q`; `units += q / f`; `cost += amount`;
     `bench_units += amount / b`.
   - **sell:** `frac = q / shares`; `cost_out = cost · frac`;
     `realized += (q·price − fee − tax) − cost_out`; `bench_realized += bench_units·frac·b − cost_out`;
     then scale `shares`, `units`, `cost`, `bench_units` down by `frac`.
3. Record a point: `market_value = Σ units · last[s].adjusted_close`, `cost_basis = Σ cost`,
   `realized = Σ realized`, `total_pnl = market_value − cost_basis + realized`,
   `benchmark_pnl = Σ bench_units · b − cost_basis + Σ bench_realized`.

**Splits.** The broker quotes sells in post-split shares, so `shares` must follow splits, or a sell
after one is checked against the wrong count. There is no split table, but the bars show splits:
between two consecutive closes of a symbol, `f` jumps by the split ratio (×2 for 2:1), while an
ex-dividend day moves it about 1–2%. A change of more than 25% counts as a split. The ratio snaps to
the nearest "N for M" with `M ≤ 4`, through its inverse for a reverse split, so a same-day dividend
or float noise cannot leave a ghost fraction. That gives 2, 3/2, 1/20 and 1/50. `cost` is unchanged,
so `avg_cost = cost / shares` stays comparable with the raw price. A split smaller than 25% (5:4)
goes undetected. On live data, 2026-11-08: no false split; the largest day-over-day move in `f`
across the held symbols' bars was 1.05%.

**Dividends are total return.** Only buys and sells are imported, never dividends. So
`units · adjusted_close` counts dividends as reinvested, the same basis as the benchmark's adjusted
close. After a split and no dividend, `units · adjusted_close == shares · close`. The two differ
only by dividends.

Raise `LedgerError` (a `ValueError` subclass) naming the symbol and date if a fill's symbol or the benchmark has no close by
the day the fill is applied, and if a sell exceeds the shares held. A ledger that silently drops a
position is worse than a loud 500 that tells you which ticker's bars are missing. Share counts are
compared with a tolerance of `1e-9`, so fractional shares (0.1 + 0.2 sold as 0.3) neither raise a
false oversell nor leave a ghost position.

`first_buy` is the first buy of the current holding period: selling down to zero clears it, and
the next buy starts a new one, so `days_held` never counts a time the position was flat.

The shadow benchmark invests the whole buy amount, fee and tax included, and pays neither on
either side. So with an identical price series it **leads by the fees and tax paid**, plus what
that cash earned in the benchmark. That is intended: it is the cost of trading single stocks
instead of the index.

`tests/test_ledger.py`: hand-built fixtures, no database. Each test pins one rule:

| Test | Asserts |
| --- | --- |
| Single buy, flat price | `unrealized == −fee`, `realized == 0` |
| 2:1 split while held (raw close halves, adjusted continuous) | `market_value` unchanged across the split date; `shares` doubles |
| Sell all 20 post-split shares of a 10-share buy | Position closed, no error |
| Sell 10 of the 20 post-split shares | Half the shares and half the cost remain |
| 3:2, 1:20 and 1:50 splits; 2:1 with a 1% dividend the same day | Shares rescale by exactly the split ratio |
| Ex-dividend day (`f` moves 2%) | Shares unchanged; `market_value` counts the dividend as reinvested |
| Buy 10 @ 100, buy 10 @ 120, sell 10 @ 130, fee 1 each | Cost 2,202 → `cost_out` 1,101; `realized == 1,299 − 1,101 == 198`; remaining `cost == 1,101` |
| Benchmark identical to the stock, no fees | `benchmark_pnl == total_pnl` every day |
| Same at flat prices, with fees and tax | `benchmark_pnl − total_pnl` equals the fees and tax paid so far |
| Fill dated after the last bar | Counted, valued at the previous close |
| Fill dated on a Saturday | Applied on Monday; no weekend history point |
| Sell larger than the position | `LedgerError` |
| Buy 0.1 and 0.2, sell 0.3 | No ghost position |
| Buy then sell everything | No row in `positions`; `totals.realized` keeps the gain |
| Holding with a missing bar mid-window | That day's value uses the previous close; no exception |
| First fill on a day its symbol has no bar, prior close in the lookback | Uses the seeded prior close; no exception |
| Fill with no close anywhere on or before its date | `LedgerError` naming the symbol |
| No benchmark bars | `LedgerError` naming the benchmark |

**Verify:** `uv run pytest tests/test_ledger.py` passes, and the ex-dividend test fails if
`units · adjusted_close` is replaced with `shares · close` in the history point. The split test no
longer catches that swap, because split-rescaled shares make the two equal without dividends. Try
it once to prove the test has teeth.

### Step 6 — Endpoints and response models

**Done.** Implemented in `turtle-web` 2026-11-08. Decisions made while implementing:

- **Every `*_pct` field is a fraction** (0.05 is 5%), because `pct_vs_sma50` and `adr_pct` are
  stored that way. SIGNALS' `change_pct` dropped its `100.0 *` to match; the frontend formats.
- **`avg_cost` on the chart comes from the ledger**, not from `Σ (price·q + fee + tax) / Σ q`
  over the symbol's fills. Summing fills would be wrong after a split. The ledger's value is
  split-aware, fee-inclusive, handles a closed-and-reopened position, and equals the positions
  page's by construction. The cost is the TRANSACTIONS query, plus CLOSES (14 ms live) and a
  replay of every fill, on each chart of a symbol that has fills.
- **The chart's fill markers come from the TRANSACTIONS rows** it already loads for the ledger,
  so there is no separate FILLS query.
- **A ledger error on the chart drops only the cost line.** The replay covers every ticker, so a
  buy imported before its bars would otherwise break every held symbol's chart. The chart logs a
  warning and returns `avg_cost: null`; `/api/portfolio` still fails loudly.
- **Ledger errors are a 500 with the message.** `ledger.LedgerError` subclasses `ValueError`; an
  exception handler returns `{"detail": "no close for X.US on or before …"}`. Other exceptions
  stay a bare 500, so nothing internal leaks.
- **`Portfolio.totals` is a `HistoryPoint`** (the last day's), `None` before the first fill, when
  `positions` and `history` are empty too. `days_held` runs from the current holding period's
  first buy to that last ledger day.
- **`unrealized_pct` is `None` when the cost basis is 0**, rather than a division error.
- **An unknown chart symbol is a 404** (BARS returned nothing), not an empty chart. The chart's
  `name` is looked up in the symbol cache; on a cold cache the first chart request loads it.
- **The symbol cache reloads after an hour**, matching `/api/symbols`' `max-age`, so a ticker the
  nightly load adds gets its name without a restart.

Every endpoint declares a Pydantic `response_model`. That gives FastAPI an exact OpenAPI schema,
which generates the frontend's TypeScript types in Step 7.

| Route | Response | Built from |
| --- | --- | --- |
| `GET /api/healthz` | `{"status": "ok"}` | — |
| `GET /api/portfolio` | `Portfolio` = `totals` + `positions[]` + `history[]` | TRANSACTIONS + CLOSES → `ledger.build` |
| `GET /api/transactions` | `Transaction[]` | TRANSACTIONS, plus `slippage_pct = price / next_open − 1` for linked buys |
| `GET /api/symbols` | `Symbol[]` | SYMBOLS, cached in `app.state.symbols` for an hour |
| `GET /api/chart/{symbol}?start=&adjusted=false` | `ChartData` | BARS, plus TRANSACTIONS + CLOSES → `ledger.build` for `avg_cost` |
| `GET /api/signals?days=90&min_ranking=44` | `SignalRow[]` | SIGNALS, `:strategy` / `:ranking_strategy` from `settings.signal_strategy` / `signal_ranking_strategy` |

Key models (`turtleweb/models.py`):

```python
class Position(BaseModel):
    symbol: str
    name: str | None
    shares: float
    avg_cost: float  # cost basis / shares, fees included
    last_close: float  # raw, comparable with fill prices
    last_date: date  # staleness is visible
    market_value: float
    cost_basis: float
    unrealized: float
    unrealized_pct: float | None  # None when cost basis is 0
    realized: float
    first_buy: date
    days_held: int


class HistoryPoint(BaseModel):
    date: date
    market_value: float
    cost_basis: float
    realized: float
    total_pnl: float
    benchmark_pnl: float


class Bar(BaseModel):
    time: str  # 'YYYY-MM-DD' — what Lightweight Charts expects; never a datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class ChartData(BaseModel):
    symbol: str
    name: str | None
    adjusted: bool
    bars: list[Bar]
    fills: list[ChartFill]  # time, side, quantity, price (raw)
    avg_cost: float | None  # the open position's, from the ledger; None when flat or adjusted


class SignalRow(BaseModel):
    id: int
    symbol: str
    name: str | None
    signal_date: date
    ranking: int
    next_open: float | None  # absent until a bar after signal_date is loaded
    pct_vs_sma50: float | None
    adr_pct: float | None
    entry_date: date | None
    entry_price: float | None
    curr_price: float | None
    curr_date: date | None
    change_pct: float | None
    bought: bool
```

Validate the signals query parameters at the edge, so a bad URL is a 422 and never a slow query:
`days: int = Query(90, ge=1, le=366)` and `min_ranking: int = Query(44, ge=0, le=100)`.

Chart endpoint details:

- **`start` defaults to three years back.** That is about 750 bars. A full 2000-to-today history
  is about 6,700 bars, roughly 400 KB of JSON or 70 KB gzipped — also fine if asked for.
- **`adjusted=false` is the default**, because the page's job is to show your fills against the
  prices you actually paid. With `adjusted=true`, multiply O/H/L/C by `adjusted_close / close`
  per bar, divide volume by it (so neither shows the split), and return `avg_cost = None`: a raw
  cost line on adjusted candles would be wrong.
- **Fill markers need no price adjustment.** They are drawn `belowBar`/`aboveBar`, positioned by
  time only.
- **`avg_cost`** is the open position's `cost / shares` from the ledger (see the decisions at the
  top of this step): fees included, split-aware, equal to the positions page's.
- **Enable gzip** with `app.add_middleware(GZipMiddleware, minimum_size=1024)`.
- **Set `Cache-Control: max-age=3600`** on `/api/symbols` only: the symbol list changes once a
  night. `/api/chart` is not cached, because its fills and `avg_cost` change as soon as a
  statement is imported.

`tests/test_routes.py` runs against the seeded demo database through `TestClient`. It asserts
response shapes, that `bars[0].time` matches `^\d{4}-\d{2}-\d{2}$`, that `/api/portfolio`
`totals.market_value` and `totals.cost_basis` equal the sums over `positions`, and that the demo
split symbol's market value has no discontinuity. Do **not** assert the same for `realized`:
the totals include fully closed positions, which have no row in `positions`. For signals: `min_ranking=44` includes the seeded 44-point row and `min_ranking=45`
excludes it; every row has `ranking >= min_ranking`; and the last-day signal comes back with
`entry_price: null`.

Added while implementing: the split symbol shows post-split `shares` with `market_value ==
shares · last_close` (true only because the demo has no dividends) and the ledger's `avg_cost`; day-over-day `total_pnl` never moves more than
5% of the book (2.5% is the demo's largest; a mishandled split would jump ~7%); the raw chart shows
the 2:1 drop and the adjusted one does not, and adjusted volume keeps dollar volume; the chart is
gzipped and uncached; the symbol cache reloads once stale; an unknown symbol is a 404;
out-of-range signal parameters are a 422; a ledger error is a 500 naming the ticker on
`/api/portfolio`, while the chart still returns, without its cost line.

**Verify:** `/docs` (FastAPI's Swagger UI) lists all six routes with typed schemas, and
`uv run pytest && uv run mypy` passes.

### Step 7 — Frontend scaffold

```bash
cd web
npm install vue-router lightweight-charts
npm install --save-exact primevue@4.5.5 @primeuix/themes@2.0.3
npm install -D openapi-typescript
```

`openapi-typescript` 7.x declares a `typescript@^5` peer while the scaffold ships TypeScript 6, so
`package.json` carries an override (rather than `--legacy-peer-deps`, which plain `npm ci` in CI
would not inherit):

```json
"overrides": { "openapi-typescript": { "typescript": "$typescript" } }
```

Pin exact versions in `package-lock.json` and let Dependabot move them.

**PrimeVue stays on 4.x.** PrimeVue 5 (with `@primeuix/themes` 3) is no longer MIT: it is a
commercial "PrimeUI" product that needs a licence key and shows an "Invalid PrimeUI License"
badge on every page without one. The free Community key needs yearly renewal and would sit in
this public repo. 4.5.5 / 2.0.3 are the last MIT releases, so they are pinned exactly, and
`.github/dependabot.yml` ignores all updates to both (a later 4.x could ship under the new licence too). Lightweight Charts
must be **v5**: the code below uses the v5 `addSeries(SeriesType, options, paneIndex)` and
`createSeriesMarkers` API, which v4 lacks.

`vite.config.ts`: the dev proxy is why the API needs no CORS middleware:

```ts
export default defineConfig({
  plugins: [vue()],
  server: { proxy: { '/api': 'http://localhost:8000' } },
})
```

`src/router.ts`: history mode works in production because of `SpaStaticFiles`'s index.html fallback:

```ts
export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: () => import('./views/PortfolioView.vue') },
    { path: '/transactions', component: () => import('./views/TransactionsView.vue') },
    { path: '/chart/:symbol?', component: () => import('./views/ChartView.vue'), props: true },
    { path: '/signals', component: () => import('./views/SignalsView.vue') },
  ],
})
```

**Generated types are the API contract.** Add to `package.json`:

```json
"scripts": {
  "gen:api": "(cd ../api && uv run python -c \"import json; from turtleweb.main import create_app; from turtleweb.settings import Settings; print(json.dumps(create_app(Settings(db_password='x')).openapi()))\") > openapi.json && openapi-typescript openapi.json -o src/api/schema.d.ts",
  "type-check": "vue-tsc -b --noEmit"
}
```

The subshell matters: without it the `cd ../api` is still in effect when `openapi-typescript` runs,
and `schema.d.ts` lands in `api/src/api/`. `-b` matters too: the root `tsconfig.json` is a
solution file (`"files": []` plus references), so a plain `vue-tsc --noEmit` checks nothing and
always passes.

Commit `src/api/schema.d.ts` (and `openapi.json`). CI regenerates both and fails on a diff
(Step 10), so a backend model change can never silently break the frontend.

`src/api/client.ts`: native `fetch`, no axios:

```ts
import type { components } from './schema'

export type Portfolio = components['schemas']['Portfolio']
export type Transaction = components['schemas']['Transaction']
export type ChartData = components['schemas']['ChartData']
export type SymbolRow = components['schemas']['Symbol']
export type SignalRow = components['schemas']['SignalRow']

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`/api${path}`)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} — ${path}`)
  return res.json() as Promise<T>
}

export const api = {
  portfolio: () => get<Portfolio>('/portfolio'),
  transactions: () => get<Transaction[]>('/transactions'),
  symbols: () => get<SymbolRow[]>('/symbols'),
  chart: (symbol: string, adjusted = false) =>
    get<ChartData>(`/chart/${encodeURIComponent(symbol)}?adjusted=${adjusted}`),
  signals: (days = 90, minRanking = 44) =>
    get<SignalRow[]>(`/signals?days=${days}&min_ranking=${minRanking}`),
}
```

`src/format.ts`: one place for `Intl.NumberFormat` money and percentage formatters, plus a
`pnlClass(v)` that returns `'pos'`/`'neg'` for green/red.

**Verify:** `npm run dev` with the API running shows the router shell, and `npm run type-check`
passes.

### Step 8 — The price chart component

Lightweight Charts is touched only in `src/components/` (`PriceChart.vue`, `LineChart.vue`) and
`src/charts.ts`, which holds the shared lifecycle (`useChart`: create on mount, remove on unmount)
and the light/dark theme read from the page's CSS variables. The block below is the core of
`PriceChart.vue`; the shipped file differs as listed after it.

```vue
<script setup lang="ts">
import { onBeforeUnmount, onMounted, useTemplateRef, watch } from 'vue'
import {
  CandlestickSeries, HistogramSeries, LineStyle, createChart, createSeriesMarkers,
  type IChartApi, type IPriceLine, type ISeriesApi, type ISeriesMarkersPluginApi,
  type SeriesMarker, type Time,
} from 'lightweight-charts'
import type { ChartData } from '../api/client'

const props = defineProps<{ data: ChartData }>()
const el = useTemplateRef<HTMLDivElement>('el')

// Plain variables, NOT ref()/reactive(): Vue's deep proxy over the chart instance
// breaks it and slows every redraw. This is the #1 Vue + Lightweight Charts mistake.
let chart: IChartApi | undefined
let candles: ISeriesApi<'Candlestick'> | undefined
let volume: ISeriesApi<'Histogram'> | undefined
let markers: ISeriesMarkersPluginApi<Time> | undefined
let costLine: IPriceLine | undefined

function render(d: ChartData): void {
  if (!chart || !candles || !volume || !markers) return
  candles.setData(d.bars)
  volume.setData(d.bars.map((b) => ({ time: b.time, value: b.volume })))
  markers.setMarkers(
    d.fills.map((f): SeriesMarker<Time> =>
      f.side === 'buy'
        ? { time: f.time, position: 'belowBar', shape: 'arrowUp', color: '#26a69a', text: `B ${f.quantity}@${f.price}` }
        : { time: f.time, position: 'aboveBar', shape: 'arrowDown', color: '#ef5350', text: `S ${f.quantity}@${f.price}` },
    ),
  )
  if (costLine) candles.removePriceLine(costLine)
  costLine = d.avg_cost == null ? undefined
    : candles.createPriceLine({ price: d.avg_cost, title: 'avg cost', lineStyle: LineStyle.Dashed, color: '#888' })
  chart.timeScale().fitContent()
}

onMounted(() => {
  chart = createChart(el.value!, { autoSize: true })
  candles = chart.addSeries(CandlestickSeries, { upColor: '#26a69a', downColor: '#ef5350', borderVisible: false })
  volume = chart.addSeries(HistogramSeries, { priceFormat: { type: 'volume' } }, 1) // 3rd arg = paneIndex
  markers = createSeriesMarkers(candles, [])
  render(props.data)
})
watch(() => props.data, render) // /chart/A -> /chart/B reuses this instance
onBeforeUnmount(() => chart?.remove()) // frees the canvas and ResizeObserver
</script>

<template><div ref="el" class="price-chart" /></template>

<style scoped>
.price-chart { height: 520px; }
</style>
```

What the shipped `PriceChart.vue` adds to the block above:

- **`useChart` replaces the hand-written mount/unmount**, and themes the chart: background, text,
  grid, borders and the pane separator follow `prefers-color-scheme`, live. The avg-cost line
  takes `--muted` and is redrawn on a scheme change.
- **Fills are filtered to the bars' date range.** `/chart` returns every fill but only
  `CHART_YEARS` of bars, and the library snaps an out-of-range marker onto the nearest candle,
  which would draw an old buy on the wrong day.
- **On adjusted candles, marker labels drop the price** (`B 5`, not `B 5@186.7`): fill prices are
  raw and would contradict the adjusted scale.
- **Volume:** the pane gets a fifth of the height (`setStretchFactor(0.25)`; the default split is
  50/50), and each bar takes its candle's up/down colour. Quantities and prices in labels go
  through `num()`.

`src/components/LineChart.vue` uses the same `useChart` lifecycle. It takes
`series: { name, color, points: { time, value }[] }[]` and draws one `LineSeries` per entry. Use
`LineSeries` rather than `AreaSeries`: with a few dozen points, an area fill reads as a
placeholder.

**Verify:** on the demo data, `DEMOC.US` raw shows the split cliff, and `?adjusted=true`
removes it. Buy arrows sit under their fill-date candles, and the dashed average-cost line
matches the buy price (on `DEMOC.US`, whose split comes after the buy, it sits at about half
of it: 93.45 against a 186.70 buy, since the ledger rescales held shares). Switching symbols leaves exactly one chart on the page (check the DOM for
a single `<canvas>` set).

### Step 9 — The four pages

**`PortfolioView.vue`** (`/`): one `api.portfolio()` call.

- **KPI row** (`KpiTile.vue`): market value, cost basis, unrealized P&L ($ and %), realized P&L,
  total P&L vs benchmark P&L, open positions count, and the as-of date (the last history point).
  `totals` is `null` before the first fill: show an empty state, not a row of zeros.
  `unrealized_pct` can be `null` too.
- **Positions table:** a PrimeVue `DataTable` sorted by `unrealized_pct` descending. A Sector
  column follows Name, from `turtle.company.sector` (EODHD fundamentals; "—" when a ticker has no
  company row). The symbol
  cell is a `RouterLink` to `/chart/:symbol`. A `last_date` older than the as-of date renders as
  a warning badge.
- **Two `LineChart`s:** "Holdings value vs cost basis" (`market_value`, `cost_basis`) and
  "P&L vs benchmark" (`total_pnl`, `benchmark_pnl`).
- **Footer:** the caveats from [The P&L model](#the-pl-model), in `PnlCaveats.vue`; keep the two
  in step. The sell caveat drops its note to developers (add a ledger fixture), which is not for
  the page.

```vue
<DataTable :value="portfolio.positions" sortField="unrealized_pct" :sortOrder="-1" size="small" stripedRows>
  <Column field="symbol" header="Symbol" sortable>
    <template #body="{ data }"><RouterLink :to="`/chart/${data.symbol}`">{{ data.symbol }}</RouterLink></template>
  </Column>
  <Column field="shares" header="Shares" sortable />
  <Column field="avg_cost" header="Avg cost" sortable>
    <template #body="{ data }">{{ money(data.avg_cost) }}</template>
  </Column>
  <!-- last_close, market_value, unrealized, unrealized_pct (with pnlClass), days_held … -->
</DataTable>
```

**`TransactionsView.vue`** (`/transactions`): one `api.transactions()` call. A `DataTable` with
columns date, symbol (linked to the chart), side, quantity, price, fee, amount, signal date,
ranking, `next_open`, and slippage %. Unlinked buys show "—" for the signal columns, not 0.
Default sort is newest first.

**`ChartView.vue`** (`/chart/:symbol?`):

- **Symbol picker:** an `<input list="symbols">` with a native `<datalist>` filled from
  `api.symbols()`, fetched once. That gives autocomplete over about 5,600 symbols with no
  search endpoint, no debounce and no request races. Submitting calls `router.push`.
- **Raw/adjusted toggle**, stored in the query string.
- **`<PriceChart :data="chart" />`**, with a loading state and a visible error for unknown symbols.

**`SignalsView.vue`** (`/signals`): one `api.signals(days, minRanking)` call.

- **Controls:** a days selector (30 / 90 / 180) and a minimum-ranking number input, defaulting to
  90 and 44. Both live in the query string (`/signals?days=90&min_ranking=44`), so a filtered view
  can be bookmarked; changing either re-fetches.
- **Table:** a `DataTable` with columns signal date, symbol (linked to `/chart/:symbol`), name,
  ranking, % vs SMA50, ADR %, entry date, entry price, current price, change %, and bought.
  Default sort is `signal_date` descending, then `ranking` descending, matching the SQL.
- **`bought` rows are highlighted** (`:rowClass`), so the signals you took stand out from the ones
  you passed on.
- **Pending entries:** signals from the last trading day show "pending" in the entry and change
  columns.
- **Summary line above the table:** count of signals, count bought, and the median change % of
  bought vs not-bought signals, computed client-side from the rows.
- **Footer:** "Change % is a total return from the next-day open, split- and dividend-adjusted.
  Prices shown are raw."

**Verify:** all four pages render from the demo DB. The market value and cost basis KPIs equal
the column sums of the positions table. Realized P&L can exceed the table's sum, since it includes
closed positions. Each transaction's chart link opens that symbol with its arrow on the right date. The signals
page's row count changes as `min_ranking` moves across 44, and bought rows match the transactions
page's linked buys.

### Step 10 — CI

`.github/workflows/ci.yml`, on push and pull request:

```yaml
jobs:
  api:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:17
        env: { POSTGRES_DB: trading, POSTGRES_PASSWORD: demo }
        ports: ["5433:5432"]
        options: --health-cmd pg_isready --health-interval 5s --health-retries 10
    env:
      TURTLE_WEB_DB_PORT: "5433"
      TURTLE_WEB_DB_USER: postgres
      TURTLE_WEB_DB_PASSWORD: demo
      TURTLE_WEB_BENCHMARK_SYMBOL: BENCH.US
      PGPASSWORD: demo
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      - run: psql -h localhost -p 5433 -U postgres -d trading -f db/schema.sql
      - run: uv run db/seed_demo.py
      - working-directory: api
        run: uv run ruff check && uv run ruff format --check && uv run mypy && uv run pytest

  web:
    runs-on: ubuntu-latest
    defaults: { run: { working-directory: web } }
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      - uses: actions/setup-node@v4
        with: { node-version: 22, cache: npm, cache-dependency-path: web/package-lock.json }
      - run: npm ci
      - run: npm run gen:api && git diff --exit-code -- openapi.json src/api/schema.d.ts
      - run: npm run type-check && npm run build
```

`.github/workflows/release.yml`, on a `v*` tag: build `web/` and attach it to a GitHub Release
as `web-dist.tgz` (`tar -czf web-dist.tgz -C web/dist .` then `gh release create "$GITHUB_REF_NAME" web-dist.tgz`).

The shipped workflows differ from the sketch above in these ways:

- **Actions are pinned to commit SHAs** with the version in a comment (`checkout` v7.0.1,
  `setup-node` v7.1.0, `setup-uv` v10.3.3 at the time of writing); Dependabot's
  `github-actions` updates move both. `setup-uv` has published no floating major tag since v8, so
  `@v10` does not even resolve.
- **Every uv invocation is locked** (`UV_LOCKED=1` for the whole workflow): `api/uv.lock` covers the
  API and `gen:api`, and `db/seed_demo.py.lock` (from `uv lock --script db/seed_demo.py`) covers the
  seed script's inline dependencies. A lock out of step with what it locks fails CI rather than
  re-resolving on the runner. Re-run `uv lock --script` after editing the script's `dependencies`;
  Dependabot does not track that lock.
- `psql` runs with `-v ON_ERROR_STOP=1`, so a broken `schema.sql` fails the step.
- `ci.yml` runs on pushes to `main` and on pull requests, with `contents: read` and in-progress PR
  runs cancelled by newer pushes.
- The `web` job runs `npm run build` only: it starts with `vue-tsc -b`, so a separate
  `type-check` step would check everything twice.
- **`release.yml` gates the release:** it fails unless the tagged commit is on `main`, then runs
  the whole of `ci.yml` (as a reusable workflow) on that commit, and only then builds and runs
  `gh release create --verify-tag --generate-notes`. Only that last job gets `contents: write`, and
  it builds without the npm cache, so a cache saved by a less-trusted run never reaches a job
  holding a write token.

**Verify:** a PR that changes a response model without re-running `gen:api` fails the `web`
job. A tag produces a release with `web-dist.tgz` attached.

### Step 11 — Deploy to the VPS

The files are [`deploy/deploy.sh`](../../deploy/deploy.sh) and
[`deploy/turtle-web.service`](../../deploy/turtle-web.service), a systemd **user** service modelled on
turtle-backtest's `deploy/eodhd-download-daily.service`.

One-time setup, as the deploying user:

```bash
git clone https://github.com/jaaknt/turtle-web.git ~/turtle-web
mkdir -p ~/.config/turtle-web
# write ~/.config/turtle-web/secrets.env (below), then:
chmod 600 ~/.config/turtle-web/secrets.env
loginctl enable-linger "$USER"   # user services start at boot, without an SSH login
systemctl --user enable ~/turtle-web/deploy/turtle-web.service   # links the unit; does not start it
~/turtle-web/deploy/deploy.sh v0.2.0   # first deploy: sync, web/dist, start
```

`~/.config/turtle-web/secrets.env`:

```dotenv
TURTLE_WEB_DB_PASSWORD=...
TURTLE_WEB_STATIC_DIR=/home/<user>/turtle-web/web/dist
BIND_HOST=<output of: tailscale ip -4>
```

Use **absolute paths** here. systemd expands specifiers like `%h` in unit directives, but never
inside an `EnvironmentFile`. A literal `%h/...` would reach `StaticFiles`, which raises on a
missing directory, and the unit would crash-loop.

The first deploy needs a tag that contains `deploy/` (`v0.2.0` or later): checking out `v0.1.0`
would delete the unit file that `systemctl` links to.

Every later release is `~/turtle-web/deploy/deploy.sh <tag>`. **Its header comment is the
reference** for what it does and guarantees; in short: every check and the download happen before
anything changes, and the download falls back to the GitHub REST API when the release URL keeps
failing (as it did, with 504s, for `v0.3.0`). Each release's frontend lives in
`web/releases/<tag>/`, with `web/dist` a symlink switched by one `rename(2)` right before the
restart. A failed `uv sync`, restart or health check rolls back to the previous commit and
release, and the newest three releases are kept. `TURTLE_WEB_STATIC_DIR` stays `.../web/dist`;
Starlette resolves the link on every request.

A tab left open across a deploy asks for chunks that no longer exist. The API answers missing
`/assets/*` with a real 404 (not the SPA's `index.html`), and `web/src/staleChunks.ts` turns the
failed lazy import into one reload of the page the user was opening.

- **`--frozen --no-sync` on `uv run`.** Plain `uv run` syncs the default groups, dev included,
  before it starts. That would undo the `--no-dev` sync and need PyPI reachable at boot.
  `deploy.sh` owns the sync; the unit only runs what is already installed.
- **`RestartSec=10`.** Without it, systemd's default limit (5 starts in 10 s) gives up on a
  transient failure within seconds. Startup no longer depends on Postgres (Step 3), so this is
  belt and braces.
- **Bind to the Tailscale IP, never `0.0.0.0`.** The Hetzner firewall allows inbound SSH from one
  IP only (turtle-backtest's `docs/implementation.md`). Binding explicitly means a later firewall change can never
  expose the site.
- **No `After=tailscaled.service`.** A user manager cannot order against system units, so that
  line would do nothing. If the Tailscale IP is not up at boot, uvicorn fails to bind and
  `Restart=on-failure` retries every 10 s until it is, with `StartLimitIntervalSec=0` making the
  retries unlimited on purpose; item 8 below is the test.
- **`WantedBy=default.target`, not `timers.target`.** This is a persistent service, unlike every
  `Type=oneshot` unit in `turtle-backtest/deploy/`.
- **Slowness is probably Tailscale relaying, not the app.** With all inbound UDP blocked,
  Tailscale cannot set up a direct peer connection and relays through DERP. Adding an inbound
  rule for **UDP 41641** enables the direct path.

**Verify:** see [Verification](#verification) items 5–8.

## Verification

### Known-good anchors (live Hetzner DB, measured 2026-11-07)

These move as new transactions and bars arrive. The check is that the page and a hand-run query
agree. Account figures (totals, counts of fills or holdings) are deliberately not written down:
this repository is public.

| Check | Expected |
| --- | --- |
| `lightyear_transaction` rows | `/api/transactions` returns the same count as `SELECT count(*)` |
| Linked to a signal | The rows with a `signal_id` match a hand-run count |
| Total cost basis, fees included | `totals.cost_basis` equals `Σ gross_amount` on buys, while there are no sells |
| Fees reached the cost basis | `Σ gross_amount − Σ price × quantity` on buys equals `Σ fee + Σ tax`, and is non-zero. This is the cleanest check |
| CLOSES query, traded symbols + SPY since the first fill | ~13 ms, `Index Scan using pk_daily_bars` |
| Latest `SPY.US` bar | 2026-11-06 |
| `turtle.signal` | 306 rows for `bk50d_s12_v2.0`, 2026-06-01 → 2026-11-06 |
| `/api/signals?days=90&min_ranking=44` | 63 rows (148 ungated); **3** score exactly 44; `bought` matches the transactions linked to those signals; ~22 ms |
| SYMBOLS row count | ~5,600 |

### End-to-end checks

1. `psql -U turtle_web` can SELECT. An INSERT fails with the read-only-transaction error (Step 0).
2. CI is green on `main`: ruff, mypy, pytest against the demo DB, vue-tsc, build, and the
   OpenAPI drift check.
3. `/api/portfolio` `totals.cost_basis` equals `Σ gross_amount` on buys from a hand-run query, while there are no sells.
4. The split fixture: the demo `DEMOC.US` market value is continuous across its split date.
5. `curl http://<tailscale-ip>:8080/api/healthz` returns 200. From the public IP,
   `curl --max-time 5 http://<public-ip>:8080/` times out or is refused.
6. A deep link `http://<tailscale-ip>:8080/chart/AAPL.US` loads directly (SPA fallback), and
   `/api/nope` returns 404 JSON, not index.html.
7. A held symbol's chart shows its buy arrow on the fill date and the average-cost line at the
   fill price. `/signals` shows 63 rows (as of 2026-11-07), with the bought ones highlighted.
8. Reboot the VPS and confirm the site returns without an SSH login. This is what actually
   tests `enable-linger`, the classic silent failure.

## Index recommendations: add nothing to `daily_bars`

The only index on `turtle.daily_bars` is `pk_daily_bars` (955 MB against a 3,471 MB heap). Every
query here is `symbol = ? AND date >= ?` or `symbol = ANY(?) AND date >= ?`, which is a perfect
prefix match.

| Candidate | Verdict |
| --- | --- |
| `daily_bars (date)` | **No.** ~500 MB, slows the nightly bulk insert, and no query filters by date without a symbol |
| `daily_bars (symbol) INCLUDE (…)` | **No.** Redundant with the PK's leading column |
| `ticker` trigram / `text_pattern_ops` | **No.** The startup symbol cache plus `<datalist>` makes search moot |

## Appendix — What shipped from the previous draft

The earlier draft of this document was organised into numbered sections. They map as follows:

| Old section | Outcome |
| --- | --- |
| §1.1 New table, §1.2 Write repository, §1.3 `--persist` | Shipped in turtle-backtest as specified in [persist-signal.md](https://github.com/jaaknt/turtle-backtest/blob/main/docs/specs/persist-signal.md): surrogate `id`, `trading_strategy`/`ranking_strategy`, `signal_close`, `parameters` jsonb |
| §1.4 Nightly run | Shipped as a second `ExecStart=` in `deploy/eodhd-download-daily.service`, chained after the history download (05:00 Europe/Tallinn, Mon–Sat), with a 7-day window so `next_open` backfills |
| §1.5 Read-only role | Done — now [Step 0](#step-0--read-only-role-in-turtle-backtest); in `db/init.sh` and applied on the VPS and locally |
| Workstream 2 (FastAPI + Jinja) | Replaced by this FastAPI + Vue design |
| §"Signals, last 3 months" | Simplified into the SIGNALS query ([Step 4](#step-4--the-sql-module)) using the persisted indicators; page in [Step 9](#step-9--the-four-pages) |

## Open items

1. ~~**Licence `turtle-backtest`.**~~ Done: MIT, matching `turtle-web`.
2. ~~**Apply Step 0 on the VPS.**~~ Done 2026-11-08, on the VPS and locally. Remaining: put the
   same `DB_WEB_PASSWORD` in turtle-web's `secrets.env` (Step 11).
3. **Verify sell semantics** against the first real sell statement, and add it as a ledger fixture.
4. **Pick the Tailscale bind address** for `BIND_HOST`.
5. **Benchmark choice:** `SPY.US` by default. An equal-weight or small-cap benchmark may suit a
   momentum book better; it is a one-line setting.
6. **Vacuum `daily_bars` (turtle-backtest).** As of 2026-11-08, autovacuum last ran on
   `turtle.daily_bars` on 2026-07-19: the ~430k rows inserted nightly since then stay far below the
   default insert threshold (20% of 20M rows). The stale visibility map turns SYMBOLS' index-only
   scans into heap fetches. Fix it in turtle-backtest, either with a `VACUUM (ANALYZE)
   turtle.daily_bars` after the nightly download, or with a lower
   `autovacuum_vacuum_insert_scale_factor` on the table through an Alembic migration.
