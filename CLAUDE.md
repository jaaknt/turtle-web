# CLAUDE.md

Read-only web dashboard over the turtle-backtest PostgreSQL database: FastAPI + sync SQLAlchemy
Core in `api/`, Vue 3 + Vite + TypeScript in `web/`, synthetic demo database in `db/`.

## Specs

The project is built step by step from two specs. Read the relevant one before changing behaviour,
and mark a step **Done** (with the date) when it lands:

- [docs/specs/web.md](docs/specs/web.md): the dashboard, its API, the P&L model, CI and deploy.
- [docs/specs/portfolio.md](docs/specs/portfolio.md): the Analytics page, its time-weighted
  return model and metric definitions.

When code and spec disagree, fix one of them in the same commit. Keep `PnlCaveats.vue` and
`AnalyticsCaveats.vue` in step with the caveats in the specs.

## Rules

- **The repo is public: no real data, ever.** No `daily_bars` exports, no real positions or
  transactions in fixtures, tests or screenshots, no secrets. Use the demo database.
- **Read-only.** The API runs as the `turtle_web` role and only SELECTs; SQL lives in
  `api/turtleweb/sql.py`.
- **Arithmetic in the backend.** The frontend formats and draws. Every `*_pct` and return field is
  a fraction (0.05 is 5%).
- **No new dependencies** in `api/` or `web/` without asking.
- Simplicity first: the minimum change that solves the problem, matching existing style. Don't
  refactor or reformat code you weren't asked to touch.

## Commands

| Task | Command |
| --- | --- |
| Demo database | `docker compose up -d --wait`, then `uv run db/seed_demo.py` (`cp .env.example api/.env` once) |
| API checks (from `api/`) | `uv run ruff check && uv run ruff format --check && uv run mypy && uv run pytest` |
| API dev server (from `api/`) | `uv run uvicorn --factory turtleweb.main:create_app --reload` |
| Web dev server (from `web/`) | `npm run dev` (proxies `/api` to :8000) |
| Web checks (from `web/`) | `npm run build` (runs `vue-tsc` first) |
| After a response-model change | `npm run gen:api` in `web/`, and commit `openapi.json` and `src/api/schema.d.ts` (CI checks) |
| Markdown lint | `npx markdownlint-cli2@0.24.0` |

## Reviews

`/code-review` and `/simplify` read `git diff`, which leaves out untracked files: `git add -N` the
change's new files first. When applying their findings, check each claim against the code (and in
a browser for a disputed layout claim), never undo a decision the user made earlier, and when two
reviews conflict, keep the user's last decision and name the trade-off.

## Git

Trunk-based: commit directly to `main`, no branches or pull requests. Push only when asked.
Releases are annotated tags `vX.Y.Z` (`git tag -a v0.5.1 -m "v0.5.1: …"`); pushing one runs
`release.yml`, which re-runs CI and publishes `web-dist.tgz` for the VPS. Never move, delete or
force-push a published tag without asking: the VPS may already have deployed it.
