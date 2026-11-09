#!/usr/bin/env bash
# PostToolUse (Edit|Write). After Claude edits a Python file under api/:
#   - ruff check --fix and ruff format the file, then mypy the package, so lint and type errors
#     come back on the edit that caused them rather than at commit time. F401 (unused import) is
#     left to pre-commit and CI: an import added in one edit is often used only in the next;
#   - after main.py, models.py or routes.py, regenerate web/openapi.json and src/api/schema.d.ts,
#     which CI's web job checks for drift.
# Exit 2 hands stderr back to Claude; other files exit 0 untouched.
set -uo pipefail
export UV_LOCKED=1 # as in CI: fail on a stale uv.lock rather than rewrite it

f=$(jq -r '.tool_input.file_path // empty') || { echo "api-after-edit.sh: jq is missing" >&2; exit 2; }
root=${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel)}
case "$f" in "$root"/api/*.py) ;; *) exit 0 ;; esac

cd "$root/api" || exit 0
out=$({
  uv run -q ruff check --fix --extend-ignore F401 "$f" && uv run -q ruff format -q "$f" && uv run -q mypy
} 2>&1) || { printf '%s\n' "$out" >&2; exit 2; }

case "$f" in */api/turtleweb/main.py | */api/turtleweb/models.py | */api/turtleweb/routes.py)
  cd "$root/web" || exit 0
  out=$(npm run -s gen:api 2>&1) || { printf 'npm run gen:api failed:\n%s\n' "$out" >&2; exit 2; }
  ;;
esac
