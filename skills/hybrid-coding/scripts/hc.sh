#!/usr/bin/env bash
# Single entry point for the hybrid-coding skill, so one allowed-tools rule covers
# every helper. Run without arguments for the command list.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)

usage() {
  cat >&2 <<'EOF'
usage: hc.sh <command> [args]          (S = session folder path or session id)
  init SID [--resume DIR]         create/locate the session folder, print backends (runs at skill load)
  config S key=value…             record settings: coder=, scout=, title=
  status S                        task states, worker costs, open worktrees
  ready S                         gate before "done"/commit: nothing running, all done, summary current, no discrepancies
  transcript SID [--all]          main-session dialogue since the skill started (for the scribe)
  worker …                        headless Claude Code worker, Anthropic or Ollama (run_worker.sh)
  ask MODEL "instruction"         tool-less Ollama call on stdin (ollama_ask.sh)
  wt S TASK [--seed] [--repo D]   worker worktree under S/wt/TASK (make_worktree.sh)
  integrate WT [TARGET] …         carry a worktree's changes back (integrate_worktree.sh)
  teardown S [--purge] [--force]  strip S to spec + summary + research, or delete it
EOF
  exit 2
}

resolve() {
  case $1 in
    /*) echo "$1" ;;
    *) echo "$(git rev-parse --show-toplevel 2>/dev/null || pwd)/.hybrid/$1" ;;
  esac
}

teardown() {
  [ $# -ge 1 ] || usage
  local dir purge=0 force=0
  dir=$(resolve "$1"); shift
  while [ $# -gt 0 ]; do
    case $1 in --purge) purge=1 ;; --force) force=1 ;; *) usage ;; esac
    shift
  done
  [ -d "$dir" ] || { echo "no session at $dir" >&2; exit 1; }

  local wts=() w
  for w in "$dir"/wt/*/; do [ -d "$w" ] && wts+=("${w%/}"); done
  if [ ${#wts[@]} -gt 0 ] && [ $force -eq 0 ]; then
    echo "worktrees not yet integrated/removed (integrate them, or --force to discard):" >&2
    printf '  %s\n' "${wts[@]}" >&2
    exit 1
  fi
  if [ $purge -eq 0 ] && [ $force -eq 0 ]; then
    python3 "$here/hc.py" ready "$dir" >&2 || { echo "teardown refused (or --force / --purge)" >&2; exit 1; }
  fi
  for w in ${wts[@]+"${wts[@]}"}; do
    common=$(git -C "$w" rev-parse --path-format=absolute --git-common-dir)
    git --git-dir="$common" worktree remove --force "$w"
    git --git-dir="$common" worktree prune
  done

  if [ $purge -eq 1 ]; then
    rm -rf "$dir"
    rmdir "$(dirname "$dir")" 2>/dev/null || true
    echo "removed $dir"
  else
    rm -rf "$dir/tasks" "$dir/wt" "$dir/plan.md" "$dir/WORKER.md" "$dir/SCRIBE.md"
    echo "kept: $(cd "$dir" && ls | tr '\n' ' ')"
  fi
}

[ $# -ge 1 ] || usage
cmd=$1; shift
case $cmd in
  init|config|status|ready|transcript) exec python3 "$here/hc.py" "$cmd" "$@" ;;
  worker) exec bash "$here/run_worker.sh" "$@" ;;
  ask) exec bash "$here/ollama_ask.sh" "$@" ;;
  wt) [ $# -ge 1 ] || usage; s=$(resolve "$1"); shift; exec bash "$here/make_worktree.sh" "$s" "$@" ;;
  integrate) exec bash "$here/integrate_worktree.sh" "$@" ;;
  teardown) teardown "$@" ;;
  *) usage ;;
esac
