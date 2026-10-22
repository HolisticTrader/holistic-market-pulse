#!/usr/bin/env bash
# Commit and push bot state safely, even when several workflows push at the same moment.
# Usage: save_state.sh "<bot name>" "<commit message>" <paths...>
set -u
name="$1"; msg="$2"; shift 2
git config user.name "$name"
git config user.email "actions@users.noreply.github.com"
git add "$@" 2>/dev/null || true
git diff --cached --quiet && { echo "no state change"; exit 0; }
git commit -q -m "$msg"
for i in 1 2 3 4 5 6; do
  # -X theirs keeps THIS run's version of a state file if two runs touched it
  if git pull -q --rebase -X theirs origin "${GITHUB_REF_NAME:-main}" && git push -q; then echo "state saved"; exit 0; fi
  git rebase --abort 2>/dev/null || true
  echo "push collided with another run, retry $i"; sleep $((i * 3 + RANDOM % 5))
done
echo "::warning::Could not save state after 6 tries; next run will catch up"
exit 0
