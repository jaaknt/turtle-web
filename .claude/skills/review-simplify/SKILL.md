---
name: review-simplify
description: Run /code-review, apply its findings, then run /simplify over the result, one after the other. Pass an optional review level and target, e.g. `/review-simplify high` or `/review-simplify medium HEAD~2`. Does not commit.
argument-hint: "[level] [target]"
disable-model-invocation: true
---

# Code review, then simplify

Follow CLAUDE.md's Reviews rules throughout.

1. **Fix the scope.** `git add -N` the change's untracked files, so both reviews see them. On a
   clean tree with no target, `/code-review` reviews the last commit: say so.

2. **Run `/code-review`** with the Skill tool, passing `$ARGUMENTS` (optional level, then optional
   target). It runs in the background; wait for its completion notification before step 3.

3. **Apply the review**: fix each finding or skip it with a one-line reason.

4. **Run `/simplify`** with the Skill tool, with no arguments, so its scope is the working tree:
   the original change plus the step-3 fixes. It edits files itself; check its edits against the
   Reviews rules and revert any that break them.

5. **Run the CLAUDE.md checks** for what changed, then **report** in one summary what each pass
   fixed, what was skipped and why, and the checks that passed. Leave the changes uncommitted;
   `/commit-push` or `/commit-push-tag` commits them.
