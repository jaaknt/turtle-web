# turtle-web

A read-only web dashboard over the [turtle-backtest](https://github.com/jaaknt/turtle-backtest)
PostgreSQL database: portfolio value and P&L, transactions, price charts with your fills marked,
and the signals the baseline strategy fired.

- **Backend:** FastAPI, sync SQLAlchemy Core, raw SQL, read-only `turtle_web` database role
- **Frontend:** Vue 3 + Vite + TypeScript, PrimeVue tables
- **Charts:** [TradingView Lightweight Charts™](https://www.tradingview.com/lightweight-charts/)

> **Status:** scaffold only. The build guide is
> [`docs/specs/web.md`](https://github.com/jaaknt/turtle-backtest/blob/main/docs/specs/web.md) in
> turtle-backtest; this repository follows it step by step.

## No real data, ever

This repository is public. It must never contain real market or account data:

- **No exported `daily_bars` rows** or any other EODHD data. EODHD's terms forbid redistribution.
- **No real positions or transactions** in fixtures, tests, screenshots or issues.
- **No secrets.** Configuration comes from `TURTLE_WEB_*` environment variables. `.env` and
  `*.env` are gitignored; only `.env.example` is committed.

Tests, screenshots and local development use the synthetic demo database (`db/`), never a copy of
the real one.

## Licence

MIT — see [LICENSE](LICENSE). The charts are TradingView Lightweight Charts™ (Apache-2.0); see
[NOTICE](NOTICE) for attribution.
