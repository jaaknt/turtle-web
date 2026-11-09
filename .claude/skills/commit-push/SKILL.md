---
name: commit-push
description: Commit work to main and push it to GitHub. Runs the checks CI runs for the parts that changed, stages only the change's own files, and confirms the CI workflow passes on the pushed commit. Use when the user asks to commit and push, or to ship changes without a release tag.
---

# Commit and push to main

1. **Check the branch.** Work is committed straight to `main`. If `git branch --show-current` is
   not `main`, stop and ask.

2. **Run the gate**, which mirrors CI's `api`, `web` and `docs` jobs (`.github/workflows/ci.yml`).
   For what changed (`git status --porcelain`), run the matching rows of CLAUDE.md's Commands
   table, as parallel Bash calls since they share nothing:

   - `api/` or `db/`: the API checks, with the demo database up.
   - `api/turtleweb/models.py` or `routes.py`: `gen:api` before the web build; regenerated
     `openapi.json` and `src/api/schema.d.ts` belong in this commit.
   - `web/`: the web build.
   - A tracked `.md`: the markdown lint.

   Any failure stops here: report it and fix it.

3. **Stage deliberately.** Name the paths that belong to the change (new files marked with
   `git add -N` for a review count too, and still need a real `git add`); `git add -A` only after
   reading the status list and finding every entry belongs. Leave anything else unstaged and
   mention it in the summary. The repo is public: if a staged file holds real market or account
   data, a `.env` or a secret, stop and say so. Then read `git diff --cached`, so the message
   describes what is actually staged.

4. **Commit** with a heredoc, in the history's style (`git log --oneline -10`): a short imperative
   subject, then `-` bullets saying what changed and why. If the change lands a spec step, mark it
   **Done** in the spec in the same commit and name it in the subject
   (`Analytics Step 8: documentation`).

   ```bash
   git commit -F - <<'EOF'
   Short imperative subject

   - What changed, and why

   Co-Authored-By: <the attribution line Claude Code currently supplies>
   EOF
   ```

5. **Push**: `git push origin main`.

6. **Confirm CI passed** on the pushed commit. Watch it in the background (`run_in_background`);
   the run takes a few seconds to register, and the wait gives up after three minutes:

   ```bash
   gh auth status >/dev/null || { echo "gh not authenticated: CI not verified"; exit 1; }
   sha=$(git rev-parse HEAD)
   for _ in $(seq 36); do
     run=$(gh run list --workflow ci.yml --commit "$sha" --json databaseId,url \
       --jq '.[0] | select(.) | "\(.databaseId) \(.url)"') && [ -n "$run" ] && break
     sleep 5
   done
   [ -n "$run" ] || { echo "no CI run registered for $sha"; exit 1; }
   echo "$run"; gh run watch "${run%% *}" --exit-status
   ```

   Report the outcome with the run URL. On failure, show `gh run view <id> --log-failed` and
   diagnose it. CodeQL also runs on push; it is slow and not a gate, so don't wait for it.
