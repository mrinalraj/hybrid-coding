#!/usr/bin/env bash
# One-shot, tool-less prompt to an Ollama model. The input comes on stdin, so big
# logs or diffs never pass through argv or the orchestrator's context.
#   <command producing text> | ollama_ask.sh MODEL "instruction"
# OLLAMA_NUM_CTX overrides the context size (by default the server's, which avoids
# reloading a model already in memory); OLLAMA_THINK=1 enables thinking.
set -euo pipefail

[ $# -eq 2 ] || { echo 'usage: <cmd> | ollama_ask.sh MODEL "instruction"' >&2; exit 2; }
model=${1#ollama:}
host=${OLLAMA_HOST:-http://localhost:11434}
case $host in http://*|https://*) ;; *) host="http://$host" ;; esac

python3 -c '
import json, os, sys
req = {
    "model": sys.argv[1],
    "stream": False,
    "think": os.environ.get("OLLAMA_THINK") == "1",
    "messages": [
        {"role": "system", "content": sys.argv[2]},
        {"role": "user", "content": sys.stdin.read()},
    ],
}
if os.environ.get("OLLAMA_NUM_CTX"):
    req["options"] = {"num_ctx": int(os.environ["OLLAMA_NUM_CTX"])}
print(json.dumps(req))' "$model" "$2" |
  curl -fsS "$host/api/chat" -H 'Content-Type: application/json' -d @- |
  python3 -c 'import json, sys; print(json.load(sys.stdin)["message"]["content"].strip())'
