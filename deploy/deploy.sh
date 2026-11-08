#!/usr/bin/env bash
# Deploy a tagged release on the VPS:  ~/turtle-web/deploy/deploy.sh <tag>, such as v0.3.4
#
# One-time setup comes first (docs/specs/web.md, Step 11). What a deploy does:
#
#   1. Checks, before anything changes: secrets.env readable with a BIND_HOST, the tag exists,
#      the checkout has no local changes.
#   2. Downloads the release's web-dist.tgz into web/releases/<tag>/ (via a hidden temp dir, so
#      a half-extracted release never has that name): the public download URL first, then, if
#      GitHub keeps failing that one, the same asset through the REST API. A missing release or
#      asset stops here, with a message naming which.
#   3. Checks out the tag and syncs the API's dependencies.
#   4. Points the web/dist symlink at the new release (one rename(2), so there is never a moment
#      without a web/dist) and restarts the service straight after, so new frontend and old API
#      overlap only for the restart itself.
#   5. Waits up to 30 s for /api/healthz.
#
# If any of 3-5 fails, it rolls back: the previous commit, its dependencies, the previous
# release's web/dist, a restart, and a second health check. The old process keeps running
# through steps 3-4, so the site stays up unless the restart itself fails. The newest three
# releases stay on disk.
set -euo pipefail

# The body is functions, called on the last line: bash parses all of it before running any,
# so the `git checkout` below can rewrite this very file without changing what runs.

repo="$HOME/turtle-web"
secrets="$HOME/.config/turtle-web/secrets.env"
releases_kept=3

die() {
  echo "deploy: $*" >&2
  exit 1
}

# BIND_HOST from secrets.env, tolerant of how a hand-edited file tends to look: the last
# assignment wins (as in systemd), and whitespace around `=` and the value, a CR line ending and
# one pair of quotes are dropped. Never `source` the file: a password with spaces or `$` would
# run as shell.
read_bind_host() {
  sed -n 's/^[[:space:]]*BIND_HOST[[:space:]]*=[[:space:]]*//p' "$secrets" | tail -n 1 | tr -d '\r' \
    | sed -e 's/[[:space:]]*$//' -e 's/^"\(.*\)"$/\1/' -e "s/^'\(.*\)'\$/\1/"
}

wait_healthy() {
  local deadline=$((SECONDS + 30))
  while ((SECONDS < deadline)); do
    if curl -fsS --max-time 2 "http://$bind_host:8080/api/healthz" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

# Point web/dist at web/releases/<name> in one rename(2).
activate() {
  ln -sfn "releases/$1" web/.dist-next && mv -Tf web/.dist-next web/dist
}

# Steps 3-5; any failure returns non-zero (set -e does not apply inside an `if` condition).
install_and_start() {
  git -c advice.detachedHead=false checkout --quiet "$tag" || return 1
  uv sync --project api --frozen --no-dev || return 1
  systemctl --user daemon-reload || return 1 # the unit is linked from this checkout
  activate "$tag" || return 1
  systemctl --user restart turtle-web || return 1
  wait_healthy
}

rollback() {
  echo "deploy: $tag failed; rolling back to ${prev_release:-no release} at ${prev_head:0:12}" >&2
  git -c advice.detachedHead=false checkout --quiet "$prev_head" &&
    uv sync --project api --frozen --no-dev &&
    systemctl --user daemon-reload &&
    { [ -z "$prev_release" ] || activate "$prev_release"; } &&
    systemctl --user restart turtle-web &&
    wait_healthy &&
    { echo "deploy: rolled back; the previous version is serving" >&2; return 0; }
  echo "deploy: rollback did not come up healthy either; see: journalctl --user -u turtle-web -n 50" >&2
}

# Download the release's web-dist.tgz to the file $2. Both routes are public: no gh login on the VPS.
#
# To a file, never `curl | tar`: when curl retries after a partial transfer it writes the body
# again, and a pipe would hand tar the broken first attempt followed by the second.
#
# Every attempt has a hard time limit (--max-time), so a transfer that stalls mid-way fails and
# retries instead of hanging the deploy. Retries back off 1, 2, 4, 8, 16 s (no fixed
# --retry-delay, which would turn that off) and include refused connections. Worst case for the
# whole function is about 5 minutes; a missing release or asset fails in seconds with a message
# that says so.
download_asset() {
  local tag="$1" out="$2" release_json api_url
  local transfer=(--retry 5 --retry-connrefused --retry-max-time 120 --connect-timeout 10 --max-time 60)
  local lookup=(--retry 3 --retry-connrefused --retry-max-time 30 --connect-timeout 10 --max-time 15)

  # 1. The release download URL. github.com has been seen answering 504 for hours on some assets
  #    while serving others, so a failure here is not the end.
  if curl -fsSL "${transfer[@]}" -o "$out" "https://github.com/jaaknt/turtle-web/releases/download/$tag/web-dist.tgz"; then
    return 0
  fi
  echo "deploy: the release download URL failed; trying the GitHub API" >&2

  # 2. The same asset through the REST API: look up its API URL by tag, then fetch the bytes.
  #    Unauthenticated, which allows 60 API requests an hour: plenty for a deploy.
  if ! release_json="$(curl -fsSL "${lookup[@]}" -H "Accept: application/vnd.github+json" \
      "https://api.github.com/repos/jaaknt/turtle-web/releases/tags/$tag")"; then
    echo "deploy: no GitHub release for $tag, or the GitHub API is unreachable" >&2
    return 1
  fi
  # JSON through uv's Python (uv is already required, for `uv sync`), not a system python3.
  api_url="$(printf '%s' "$release_json" | uv run --no-project --quiet python -c '
import json, sys
tag = sys.argv[1]
try:
    assets = json.load(sys.stdin)["assets"]
except (ValueError, KeyError, TypeError):
    sys.exit(f"deploy: unexpected GitHub API response for the {tag} release")
urls = [a["url"] for a in assets if a.get("name") == "web-dist.tgz"]
if not urls:
    sys.exit(f"deploy: the {tag} release has no web-dist.tgz (did release.yml finish?)")
print(urls[0])
' "$tag")" || return 1
  curl -fsSL "${transfer[@]}" -H "Accept: application/octet-stream" -o "$out" "$api_url"
}

prune_releases() {
  local name kept=0
  # Newest first by modification time; the active release always survives, plus the next
  # (releases_kept - 1) newest. Hidden .incoming-* temp dirs are not releases.
  while IFS= read -r name; do
    if [ "$name" = "$tag" ]; then
      continue
    elif ((kept < releases_kept - 1)); then
      kept=$((kept + 1))
    else
      rm -rf "web/releases/$name"
    fi
  done < <(find web/releases -mindepth 1 -maxdepth 1 -type d ! -name '.*' -printf '%T@ %f\n' | sort -rn | cut -d' ' -f2-)
}

main() {
  tag="${1:?usage: deploy.sh <tag>}"
  cd "$repo"

  # 1. Checks.
  [ -r "$secrets" ] || die "cannot read $secrets"
  bind_host="$(read_bind_host)"
  [ -n "$bind_host" ] || die "no BIND_HOST in $secrets"
  git fetch --quiet --tags --force origin
  git rev-parse --quiet --verify "refs/tags/$tag^{commit}" >/dev/null || die "no such tag: $tag"
  [ -z "$(git status --porcelain --untracked-files=no)" ] || die "$repo has local changes; refusing to deploy over them"
  prev_head="$(git rev-parse HEAD)"
  prev_release=""
  if [ -L web/dist ]; then
    prev_release="$(basename "$(readlink web/dist)")"
  elif [ -e web/dist ]; then
    rm -rf web/dist # a plain directory from before the symlink layout; nothing serves it yet
  fi

  # 2. The frontend. A release asset never changes, so a tag already on disk is reused.
  mkdir -p web/releases
  if [ ! -f "web/releases/$tag/index.html" ]; then
    # Leftovers of a deploy that was killed outright (SIGKILL, reboot), whose EXIT trap never ran.
    # One deploy runs at a time, so anything .incoming-* now is stale.
    rm -rf web/releases/.incoming-*
    tmp="$(mktemp -d web/releases/.incoming-XXXXXX)"
    trap 'rm -rf "$tmp" "$tmp.tgz"' EXIT
    download_asset "$tag" "$tmp.tgz" || die "could not download web-dist.tgz for $tag"
    tar -xzf "$tmp.tgz" -C "$tmp"
    rm -f "$tmp.tgz" # not needed past this point; do not hold it through the restart
    [ -f "$tmp/index.html" ] || die "web-dist.tgz for $tag has no index.html"
    chmod 755 "$tmp" # mktemp makes it 0700
    rm -rf "web/releases/$tag"
    mv "$tmp" "web/releases/$tag"
  fi

  # 3-5, with rollback.
  if install_and_start; then
    prune_releases
    echo "deployed $tag on http://$bind_host:8080"
  else
    rollback
    exit 1
  fi
}

main "$@"
