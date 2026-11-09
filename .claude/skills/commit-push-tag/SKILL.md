---
name: commit-push-tag
description: Commit work to main, push it, and tag a release, e.g. `/commit-push-tag v0.5.3`. Runs the commit-push workflow, then creates and pushes an annotated tag, which runs release.yml and publishes web-dist.tgz for the VPS.
argument-hint: <tag, e.g. v0.5.3>
disable-model-invocation: true
---

# Commit, push and tag a release

The tag is `$ARGUMENTS`; `<tag>` below means it after step 1.

1. **Check the tag before committing anything.** It must be `vMAJOR.MINOR.PATCH`: add a missing
   `v` (`release.yml` runs only on `v*` tags). After `git fetch --tags`, it must be higher than
   the latest tag (`git tag --sort=-v:refname | head -1`), which also means it does not exist yet.
   Otherwise stop and ask. No tag given: propose the next patch version and ask.

2. **Commit and push** by following [commit-push](../commit-push/SKILL.md), steps 1 to 5. If the
   working tree is clean, skip the commit and tag the current `HEAD`, once `git status -sb` shows
   nothing ahead of `origin/main`.

3. **Tag** the pushed commit, annotated, with the tag, a colon and what the release adds:

   ```bash
   git tag -a <tag> -m "<tag>: <what this release adds>"
   git push origin <tag>
   ```

4. **Confirm the release.** The tag runs `release.yml`: the CI suite on the tagged commit, then
   the `web-dist` job, which publishes the GitHub release. Watch it as in commit-push step 6, with
   `--workflow release.yml --branch <tag>` in place of `--workflow ci.yml --commit "$sha"`. Then:

   ```bash
   gh release view <tag> --json url,assets --jq '{url, assets: [.assets[].name]}'
   ```

   Done when the run is green and the release lists `web-dist.tgz`; report the release URL. On
   failure, diagnose it, and ask before moving or re-pushing the tag (CLAUDE.md, Git).
