#!/usr/bin/env bash
# Install the hybrid-coding skill and its subagent types (scout, scribe, worker) into Claude Code.
set -euo pipefail

usage() {
  cat <<'EOF'
usage: ./install.sh [--link] [--project <dir>] [--agents-only] [--force]

  --link         symlink instead of copying, so edits in this repo take effect directly
  --project DIR  install into DIR/.claude instead of ~/.claude
  --agents-only  install only the agents (the skill came from `npx skills add` or a plugin)
  --force        replace existing files that differ
EOF
}

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
dest="$HOME/.claude"
link=0 agents_only=0 force=0

while [ $# -gt 0 ]; do
  case "$1" in
    --link) link=1 ;;
    --project) dest="$(cd "${2:?--project needs a directory}" && pwd)/.claude"; shift ;;
    --agents-only) agents_only=1 ;;
    --force) force=1 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
  shift
done

# place SRC DST: copy or link SRC to DST. An existing DST is left alone unless it's
# already ours (same content or a link to SRC) or --force is given.
place() {
  local src="$1" dst="$2"
  if [ -e "$dst" ] || [ -L "$dst" ]; then
    if [ "$(readlink "$dst" 2>/dev/null)" = "$src" ] || { [ "$link" = 0 ] && diff -rq "$src" "$dst" >/dev/null 2>&1; }; then
      echo "  up to date  $dst"; return
    fi
    if [ "$force" = 0 ]; then
      echo "  skipped     $dst (exists and differs; use --force to replace)"; return
    fi
    rm -rf "$dst"
  fi
  if [ "$link" = 1 ]; then ln -s "$src" "$dst"; else cp -R "$src" "$dst"; fi
  echo "  installed   $dst"
}

echo "Installing into $dest"
mkdir -p "$dest/agents"
for f in "$repo"/agents/*.md; do
  place "$f" "$dest/agents/$(basename "$f")"
done
if [ "$agents_only" = 0 ]; then
  mkdir -p "$dest/skills"
  place "$repo/skills/hybrid-coding" "$dest/skills/hybrid-coding"
fi
echo "Done. Run /agents in Claude Code to check that scout, scribe and worker are listed."
