#!/usr/bin/env bash
# Create a detached worker worktree at <session>/wt/<task>. With --seed, copy the
# current uncommitted changes (untracked files included) into it and stage them
# as the baseline, so integrate_worktree.sh later carries back only the worker's
# own changes. Prints the worktree path.
set -euo pipefail

[ $# -ge 2 ] || { echo "usage: make_worktree.sh <session-dir> <task> [--seed] [--repo DIR]" >&2; exit 2; }
session=$1 task=$2; shift 2
seed=0 repo=$PWD
while [ $# -gt 0 ]; do
  case $1 in
    --seed) seed=1; shift ;;
    --repo) repo=$2; shift 2 ;;
    *) echo "unknown arg $1" >&2; exit 2 ;;
  esac
done

repo=$(git -C "$repo" rev-parse --show-toplevel)
wt="$(cd "$session" && pwd)/wt/$task"
[ -e "$wt" ] && { echo "$wt already exists" >&2; exit 1; }
mkdir -p "$(dirname "$wt")"
git -C "$repo" worktree add --detach --quiet "$wt" HEAD

if [ $seed -eq 1 ]; then
  if ! git -C "$repo" diff --quiet HEAD; then
    git -C "$repo" diff --binary HEAD | git -C "$wt" apply --whitespace=nowarn
  fi
  (cd "$repo" && git ls-files --others --exclude-standard -z) |
    while IFS= read -r -d '' f; do
      case "$f" in .hybrid/*) continue ;; esac
      [ -f "$repo/$f" ] || continue
      mkdir -p "$wt/$(dirname "$f")"
      cp -p "$repo/$f" "$wt/$f"
    done
  git -C "$wt" add -A
  touch "$(git -C "$wt" rev-parse --absolute-git-dir)/hybrid-seeded"
fi
echo "$wt"
