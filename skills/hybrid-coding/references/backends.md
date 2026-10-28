# Worker backends

`hc` = `bash ${CLAUDE_SKILL_DIR}/scripts/hc.sh`; `<S>` = the session folder.

| Backend | Use for | Tools | Lifecycle |
|---|---|---|---|
| Claude subagent (Agent tool) | Claude coders and scouts — the default | full (or read-only via `Explore`) | background; notification on finish; SendMessage to continue |
| Headless Claude CLI (`hc worker`) | Ollama models; a Claude model under a different permission profile | allowlisted | Bash `run_in_background`; exit notification; `--resume` to continue |
| Tool-less Ollama (`hc ask`) | summarizing or classifying text you pipe in | none | synchronous |

## 1. Claude subagent (Agent tool)

```
Agent(
  description: "T03 add retry to sync client",
  subagent_type: "general-purpose",     # "Explore" for read-only scouts
  model: "sonnet",                      # sonnet | haiku | opus | fable
  effort: "medium",                     # scouts: "low"
  isolation: "worktree",                # only when the plan says so — see parallel.md
  prompt: <the pointer prompt from SKILL.md>
)
```

- Runs in the background; you're notified with its final message and token usage.
- **Fix rounds:** SendMessage to the same agent with the defect list — it keeps its context, so
  this is much cheaper than a fresh worker.
- With `isolation: "worktree"`, the result includes the worktree path when there were changes.
  Integrate it with `hc integrate`.

## 2. Headless Claude CLI worker — `hc worker`

```bash
hc worker \
  --session <S> --task T03 --model ollama:qwen3-coder \
  --cwd <repo-or-worktree> --allow-bash "go build:*,go test:*"
```

Launch it with Bash `run_in_background: true`. It:
- uses a one-line prompt (override with `--message`) and puts `<S>/WORKER.md` in the system prompt;
- runs `claude -p --output-format json` in `--cwd` with edits auto-accepted and Bash limited to
  read-only git plus the `--allow-bash` patterns (also anything your settings.json already allows);
  `--mode scout` removes edit tools and saves the final answer as the report;
- writes `tasks/T03/result.json` (final message, `session_id`, `total_cost_usd`, `num_turns`) and
  `worker.log`, and prints one summary line, which is what your exit notification shows.

Fix round: `hc worker --session … --task T03 --model … --cwd … --resume <session_id>
--message "Fix: …"` (the previous result.json is kept with a timestamp suffix). Stop a running
worker with TaskStop on its background Bash task.

Give every Bash pattern the task's *Done when* commands need via `--allow-bash`; a worker that
can't run its checks will report `partial`.

## 3. Claude Code over Ollama

`hc worker` does this automatically for a model written `ollama:<name>` (or `--backend
ollama`): it points Claude Code at the local Ollama server's Anthropic-compatible API —

```
ANTHROPIC_BASE_URL=http://localhost:11434   # or $OLLAMA_HOST
ANTHROPIC_AUTH_TOKEN=ollama
ANTHROPIC_API_KEY=""
ANTHROPIC_DEFAULT_{OPUS,SONNET,HAIKU}_MODEL=<name>   # internal side calls stay on Ollama too
CLAUDE_CODE_SUBAGENT_MODEL=<name>
```

— which is the same thing `ollama launch claude --model <name>` sets up interactively.

Local and cloud models use the same path. A cloud model (`gemma4:31b-cloud`,
`glm-5.3:cloud`, …) is still addressed through the local server at `localhost:11434`, which
forwards it to ollama.com. Nothing about the worker changes except the model name.

**Before the first Ollama dispatch, check (the script also fails fast on the first two):**
1. The server is up: `curl -s localhost:11434/api/tags`. If not, ask the user to start the Ollama
   app or `ollama serve`. Don't start long-lived daemons yourself without saying so.
2. The model resolves: `ollama show <name>`.
   - *Local*: it must be pulled (`ollama list`). Pulling is a multi-GB download, so ask before
     `ollama pull`.
   - *Cloud*: no pull needed. The user must be signed in (`ollama signin`; `curl -s -X POST
     localhost:11434/api/me` shows the account and `plan`). The free plan covers only some
     models and has usage limits. If a model is retired or outside the plan, `ollama show` says so
     and usually names an alternative.
3. The model can use tools: `ollama show <name>` should list `tools` under Capabilities. Without
   it, the model can't drive Claude Code. Use it only through `hc ask`.
4. *Local only*, the context is large enough: Claude Code's system prompt and tool definitions take
   a big chunk of context, and a small default context window silently truncates them, which
   shows up as erratic, tool-confused behaviour. Run the server with a large context
   (`OLLAMA_CONTEXT_LENGTH=65536 ollama serve`, or the app's setting) if the machine allows it.
   Cloud models run at their full context length (shown by `ollama show`).

**Cloud models are a third party.** Everything the worker reads, including repo code, specs and
command output, goes to ollama.com. Use them only when the user chose one, and never escalate
a task onto a cloud model without asking.

Harmless lines in `worker.log` for Ollama runs: "claude.ai connectors are disabled because …
another auth source is set" (workers don't need connectors) and `unrecognized_model` (telemetry
note).

**Measured on a laptop** (qwen3.5:9b, Apple Silicon, 24 GB):
- **Speed:** reading input runs at about 270 tokens/s, so a 30k-token diff takes about 2 minutes
  before the first output word.
- **One request at a time.** Parallel requests queue: 8 at once took 8× as long and gave no
  throughput gain. Don't fan out several Ollama workers on one local model.
- **Coding:** it completed a small coding task through Claude Code, with tests passing (27 turns,
  about 6 minutes). But it overfitted the tests and silently accepted malformed input, so
  review its work hard.
- **Extraction:** it listed a diff's 23 changed files exactly, but it miscounted log lines,
  with or without thinking. Count with `grep`, never with a model.
- **Heat:** sustained runs heat a laptop noticeably, so keep local workers to short jobs.

**What to expect from local models:** they're noticeably weaker at long, multi-step tool use than
Claude models. Give them narrow, fully specified tasks — one or two owned files, exact signatures,
a pattern to copy with file:line — and verify harder. Allow one fix round, then escalate to a
Claude model. The `total_cost_usd` in `result.json` is meaningless for Ollama runs; log the turn
count instead.

## 4. Tool-less Ollama — `hc ask`

```bash
go test ./... 2>&1 | hc ask qwen3-coder \
  "List each failing test with the one-line reason. No preamble."
```

The input goes through stdin and never enters your context. Only the answer does. This is useful
for huge logs, test output, a big diff you only need an outline of, or classifying a long list.
The model sees only what you pipe in, so it can't look anything up. Set `OLLAMA_NUM_CTX` (default
32768) for larger inputs. Treat the answer as a lead to confirm, not as ground truth.

## Choosing quickly

- Coding, model is Claude → Agent tool.
- Coding, model is Ollama → `hc worker`.
- Discovery that needs to search the repo → Explore agent on the scout model (or `hc worker
  --mode scout` for an Ollama scout).
- "Read this huge blob and tell me X" → `hc ask` if a local model is configured, otherwise
  a Claude scout given the file path.
