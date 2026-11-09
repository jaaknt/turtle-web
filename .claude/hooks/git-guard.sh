#!/usr/bin/env bash
# PreToolUse (Bash). Blocks the git commands CLAUDE.md says need the user's explicit OK:
# force-pushes, deleting or moving tags (the VPS may already have deployed a published one), and
# skipping hooks. Exit 2 blocks the call and hands stderr back to Claude, which then asks the user;
# the user runs an approved command themselves with `! <command>`.
set -uo pipefail

block() {
  echo "Blocked by .claude/hooks/git-guard.sh: $1 needs the user's explicit OK (CLAUDE.md, Git)." >&2
  exit 2
}

cmd=$(jq -r '.tool_input.command // empty') || block "every command (jq is missing, so the guard can't read it)"
[[ $cmd == *git* ]] || exit 0 # most Bash calls: skip the greps below

# Drop quoted text with a space in it (commit messages, echo), so a message that names a flag isn't
# blocked; a quoted single token such as ":v1" stays visible.
cmd=$(sed -E "s/\"[^\"]* [^\"]*\"//g; s/'[^']* [^']*'//g" <<<"$cmd")
has() { grep -Eq -- "$1" <<<"$cmd"; }

# -f, -d or their long forms (also inside combined short flags such as -fu), --mirror, --prune,
# a +refspec (force) or a :refspec (deletes a remote ref)
has "\bgit\b[^|;&]*\bpush\b[^|;&]*( -[a-zA-Z]*[fd]| --force| --delete\b| --mirror\b| --prune\b| [\"']?[+:])" &&
  block "force-pushing or deleting a remote ref"
has '\bgit\b[^|;&]*\btag\b[^|;&]*( -[a-zA-Z]*[fd]| --force\b| --delete\b)' &&
  block "moving or deleting a tag"
has '--no-verify\b|-c core\.hooksPath|\bgit\b[^|;&]*\bcommit\b[^|;&]* -[a-zA-Z]*n' &&
  block "skipping git hooks"
exit 0
