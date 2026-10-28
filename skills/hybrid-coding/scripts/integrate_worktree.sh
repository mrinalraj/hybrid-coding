#!/usr/bin/env bash
# Carry a worker worktree's changes (new files included) into the target
# worktree without committing or touching the index on either side. Clean patch
# apply first; otherwise a per-file 3-way merge (git merge-file) that works even
# when the target has uncommitted edits, leaving conflict markers where the two
# sides collide. Exit 1 = conflicts (or skipped files) left to resolve.
set -euo pipefail

usage() { echo "usage: integrate_worktree.sh <worker-wt> [<target-wt>] [--save PATCH] [--remove]" >&2; exit 2; }
src="" dst="" save="" remove=0
while [ $# -gt 0 ]; do
  case $1 in
    --save) save=$2; shift 2 ;;
    --remove) remove=1; shift ;;
    -*) usage ;;
    *) if [ -z "$src" ]; then src=$1; elif [ -z "$dst" ]; then dst=$1; else usage; fi; shift ;;
  esac
done
[ -n "$src" ] || usage
src=$(cd "$src" && pwd)
dst=$(cd "${dst:-$PWD}" && git rev-parse --show-toplevel)
patch=${save:-$(mktemp "${TMPDIR:-/tmp}/hybrid-patch.XXXXXX")}

git -C "$src" add -N -- .
if [ -f "$(git -C "$src" rev-parse --absolute-git-dir)/hybrid-seeded" ]; then
  # Seeded worktree: the staged index is the baseline the worker started from.
  range=()
else
  # Diff from the fork point, so commits a worker made anyway are carried too.
  range=("$(git -C "$src" merge-base HEAD "$(git -C "$dst" rev-parse HEAD)")")
fi
git -C "$src" diff --binary ${range[@]+"${range[@]}"} > "$patch"

cleanup() {
  if [ $remove -eq 1 ]; then git -C "$dst" worktree remove --force "$src" && echo "removed $src"; fi
  return 0
}

if [ ! -s "$patch" ]; then
  echo "no changes in $src"
  cleanup
  exit 0
fi

if git -C "$dst" apply --check "$patch" 2>/dev/null; then
  git -C "$dst" apply "$patch"
  echo "applied cleanly: $(grep -c '^diff --git' "$patch") file(s) (patch: $patch)"
  cleanup
  exit 0
fi

base_of() {  # print the worker's baseline version of a path (empty if it didn't exist)
  if [ ${#range[@]} -eq 0 ]; then git -C "$src" show ":$1" 2>/dev/null || true
  else git -C "$src" show "${range[0]}:$1" 2>/dev/null || true; fi
}

tmp=$(mktemp -d "${TMPDIR:-/tmp}/hybrid-merge.XXXXXX")
merged=() conflicted=() skipped=()
while IFS=$'\t' read -r status path; do
  case $status in
    D)
      if [ -f "$dst/$path" ] && [ "$(base_of "$path" | git hash-object --stdin)" = "$(git hash-object "$dst/$path")" ]; then
        rm "$dst/$path"; merged+=("$path (deleted)")
      elif [ -f "$dst/$path" ]; then
        skipped+=("$path (worker deleted it, target changed it)")
      fi
      continue ;;
  esac
  if git -C "$src" diff --binary ${range[@]+"${range[@]}"} -- "$path" | grep -qF "GIT binary patch"; then
    skipped+=("$path (binary)"); continue
  fi
  base_of "$path" > "$tmp/base"
  if [ -f "$dst/$path" ]; then cp "$dst/$path" "$tmp/ours"; else : > "$tmp/ours"; fi
  set +e
  git merge-file -L target -L base -L "worker" "$tmp/ours" "$tmp/base" "$src/$path"
  rc=$?
  set -e
  [ $rc -lt 0 ] || [ $rc -gt 127 ] && { skipped+=("$path (merge-file error)"); continue; }
  mkdir -p "$(dirname "$dst/$path")"
  cp "$tmp/ours" "$dst/$path"
  if [ $rc -eq 0 ]; then merged+=("$path"); else conflicted+=("$path"); fi
done < <(git -C "$src" diff --name-status --no-renames ${range[@]+"${range[@]}"})
rm -rf "$tmp"

echo "3-way merged per file (patch: $patch)"
[ ${#merged[@]} -gt 0 ] && printf '  merged: %s\n' "${merged[@]}"
[ ${#conflicted[@]} -gt 0 ] && printf '  CONFLICT (markers written): %s\n' "${conflicted[@]}"
[ ${#skipped[@]} -gt 0 ] && printf '  SKIPPED, resolve by hand: %s\n' "${skipped[@]}"
if [ ${#conflicted[@]} -eq 0 ] && [ ${#skipped[@]} -eq 0 ]; then
  cleanup
  exit 0
fi
exit 1
