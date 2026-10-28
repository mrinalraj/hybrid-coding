#!/usr/bin/env bash
# Run one hybrid-coding task with headless Claude Code, against Anthropic or an
# Ollama server. Launch with Bash run_in_background so the orchestrator gets an
# exit notification. Leaves result.json and worker.log in the task dir and prints
# a one-line summary.
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
usage: run_worker.sh --session DIR --task ID --model M [options]
  --model M              claude alias/id, or ollama:<name>
  --backend B            anthropic | ollama (default: inferred from --model)
  --cwd DIR              repo or worktree to work in (default: $PWD)
  --mode code|scout      scout = no edit tools (default: code)
  --allow-bash LIST      comma-separated Bash patterns, e.g. "go build:*,go test:*"
  --effort LEVEL         low | medium | high (anthropic backend only)
  --resume SESSION_ID    continue an earlier worker session (fix round)
  --message TEXT         prompt (default: the standard pointer to the plan section)
EOF
  exit 2
}

session="" task="" model="" backend="" cwd=$PWD mode=code allow_bash="" effort="" resume="" message=""
while [ $# -gt 0 ]; do
  case $1 in
    --session) session=$2; shift 2 ;;
    --task) task=$2; shift 2 ;;
    --model) model=$2; shift 2 ;;
    --backend) backend=$2; shift 2 ;;
    --cwd) cwd=$2; shift 2 ;;
    --mode) mode=$2; shift 2 ;;
    --allow-bash) allow_bash=$2; shift 2 ;;
    --effort) effort=$2; shift 2 ;;
    --resume) resume=$2; shift 2 ;;
    --message) message=$2; shift 2 ;;
    *) usage ;;
  esac
done
[ -n "$session" ] && [ -n "$task" ] && [ -n "$model" ] || usage
[ -n "$resume" ] && [ -z "$message" ] && { echo "--resume needs --message with the fix list" >&2; exit 2; }

session=$(cd "$session" && pwd)
task_dir="$session/tasks/$task"
mkdir -p "$task_dir"

case $model in
  ollama:*) model=${model#ollama:}; backend=${backend:-ollama} ;;
esac
backend=${backend:-anthropic}

tools=(Read Glob Grep "Bash(git status:*)" "Bash(git diff:*)" "Bash(git log:*)" "Bash(ls:*)")
disallowed=()
if [ "$mode" = scout ]; then
  disallowed=(Edit Write MultiEdit NotebookEdit)
  perm=default
else
  tools+=(Edit Write MultiEdit)
  perm=acceptEdits
fi
if [ -n "$allow_bash" ]; then
  IFS=',' read -r -a patterns <<< "$allow_bash"
  for p in "${patterns[@]}"; do
    p=$(echo "$p" | sed 's/^ *//; s/ *$//')
    [ -n "$p" ] && tools+=("Bash($p)")
  done
fi

if [ "$backend" = ollama ]; then
  host=${OLLAMA_HOST:-http://localhost:11434}
  case $host in http://*|https://*) ;; *) host="http://$host" ;; esac
  curl -fsS "$host/api/tags" >/dev/null 2>&1 || { echo "ollama not reachable at $host — start the Ollama app or 'ollama serve'" >&2; exit 3; }
  # Local models must be pulled; cloud models resolve remotely and need `ollama signin`.
  if ! err=$(ollama show "$model" 2>&1 >/dev/null); then
    echo "ollama model '$model' unavailable: $err" >&2
    exit 3
  fi
  export ANTHROPIC_BASE_URL=$host ANTHROPIC_AUTH_TOKEN=ollama ANTHROPIC_API_KEY=""
  # Claude Code makes side calls on alias models; keep those on Ollama too.
  export ANTHROPIC_DEFAULT_OPUS_MODEL=$model ANTHROPIC_DEFAULT_SONNET_MODEL=$model \
         ANTHROPIC_DEFAULT_HAIKU_MODEL=$model CLAUDE_CODE_SUBAGENT_MODEL=$model
  export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1
  effort=""
fi

contract="$session/WORKER.md"
[ -f "$contract" ] || { echo "$contract missing — run: hc.sh init <session-id>" >&2; exit 2; }
if [ "$mode" = scout ]; then
  message=${message:-"You are scout $task. Answer the question in section $task of $session/plan.md."}
  system="You are a read-only scout. Investigate and answer as your final message; it is saved for the orchestrator as $task_dir/report.md. Be concise: findings with file:line, no preamble."
else
  message=${message:-"You are worker $task. Follow the worker contract in your system prompt."}
  system=$(cat "$contract")
fi

args=(-p "$message" --model "$model" --output-format json --permission-mode "$perm"
      --append-system-prompt "$system"
      --allowedTools "${tools[@]}")
[ ${#disallowed[@]} -gt 0 ] && args+=(--disallowedTools "${disallowed[@]}")
[ -n "$effort" ] && args+=(--effort "$effort")
[ -n "$resume" ] && args+=(--resume "$resume")

echo "$backend:$model" > "$task_dir/model"
[ -f "$task_dir/result.json" ] && mv "$task_dir/result.json" "$task_dir/result.$(date +%s).json"

# The worker is a separate session, not a nested one.
unset CLAUDECODE CLAUDE_CODE_ENTRYPOINT

cd "$cwd"
set +e
"${CLAUDE_BIN:-claude}" "${args[@]}" < /dev/null > "$task_dir/result.json" 2>> "$task_dir/worker.log"
rc=$?
set -e

python3 - "$task_dir/result.json" "$rc" "$task" "$backend:$model" "$mode" <<'PY'
import json, os, sys
path, rc, task, model, mode = sys.argv[1:6]
try:
    r = json.load(open(path))
except Exception as e:
    print(f"{task} [{model}] exit={rc} — no parseable result ({e}); see worker.log")
    sys.exit(0)
if mode == "scout" and r.get("result"):
    with open(os.path.join(os.path.dirname(path), "report.md"), "w") as f:
        f.write("status: done\n\n" + r["result"].strip() + "\n")
cost = r.get("total_cost_usd")
cost = f"${cost:.4f}" if isinstance(cost, (int, float)) and not model.startswith("ollama:") else "n/a"
print(f"{task} [{model}] exit={rc} error={r.get('is_error')} turns={r.get('num_turns')} "
      f"cost={cost} session={r.get('session_id')}")
print("final:", (r.get("result") or "").strip()[:400])
PY
exit $rc
