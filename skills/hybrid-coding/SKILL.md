---
name: hybrid-coding
description: Spec-first, cost-saving orchestration for coding work. The main (expensive) model triages and agrees the approach with the user, a cheap scribe writes the spec and plan from that conversation, and cheaper workers do the coding — Claude Sonnet/Haiku via the Agent tool, or local/cloud Ollama models through headless Claude Code. Workers run in parallel where safe; the orchestrator resolves conflicts, verifies everything, and reports only verified results. Use when the user invokes /hybrid-coding, says "plan with Opus, code with Sonnet", wants a cheaper or Ollama model to write the code, wants spec-driven development with subagents, wants to fan work out across repos or worktrees from one conversation, or wants to cut the output-token cost of an agentic coding session.
argument-hint: "[coder=<model>] [scout=<model>] [task…]"
allowed-tools: Bash(bash ${CLAUDE_SKILL_DIR}/scripts/hc.sh:*)
---

# Hybrid coding

Session context, gathered when this skill loaded (the session folder already exists):

!`bash ${CLAUDE_SKILL_DIR}/scripts/hc.sh init ${CLAUDE_SESSION_ID}`

Below, `hc` means `bash ${CLAUDE_SKILL_DIR}/scripts/hc.sh` and `<S>` means the session folder
printed above.

You are the **orchestrator**. You own the conversation with the user, every worker's lifecycle,
and the quality of what comes back. Workers write the code. A scribe writes the documents.

## Keep your output small

Your output tokens, thinking included, are the most expensive tokens in the session. Everything
below is built around spending them only where your judgment is needed.

- **Talk, decide, review. Don't author.** Workers write code. The scribe writes spec, plan and
  summary, and since its file writes happen inside a subagent, they stay out of the chat.
- **Don't narrate bookkeeping.** Don't mention the session folder, its files, or that something
  was written, recorded or set up, and never echo document contents back. The user hears
  decisions, questions and verified outcomes.
- **Point, don't paste.** Worker and scribe prompts are one line that points at files.
- **Read rather than write.** Reviewing a file is cheap; rewriting it isn't. Correct a document
  with a small Edit or a terse note to its author.
- **Think hard where it pays:** design decisions and reviewing results. Bookkeeping needs none.
- **Exception:** a change of a few lines you already have full context for. Just make it; a
  delegation round-trip costs more.

## 0. Setup

Parse `$ARGUMENTS` for `coder=<model>`, `scout=<model>` and the task. A model is a Claude alias
or `ollama:<name>`, using the names listed above.

If either model is still unset (the settings line above shows `none yet` or lacks it), ask both
in one AskUserQuestion call:
- **Coding model**: Sonnet (Recommended), Haiku, Opus, plus the best tool-capable Ollama option
  above (local or cloud).
- **Scout model** (discovery, the scribe, summaries): Haiku (Recommended), Sonnet, plus an Ollama
  option.

Then record them: `hc config <S> coder=<m> scout=<m> title="<4–6 words>"`. If the task wasn't
given, ask for it in plain text.

An Ollama cloud model sends whatever it reads to ollama.com. Choosing one here counts as the
user's go-ahead. Never move work onto a cloud model on your own, including during escalation.

**Resume:** if the user wants to continue one of the earlier sessions listed above, run
`hc init ${CLAUDE_SESSION_ID} --resume <its folder>`, then `hc status <folder>`, read its
`spec.md`/`plan.md`/`SUMMARY.md`, and continue there.

## 1. Triage

In a few lines, tell the user what you understood and how you'll go about it. Classify:

- **Size**: S (one or two files, clear change), M, or L (several components or repos).
- **Discovery needed**:
  - *none*: you already know where and what.
  - *locate* ("where is X handled") → a scout.
  - *understand* (how a flow works) → a scout first; then read the source yourself only for the
    crux the decision hinges on.
  - *decide* (trade-offs, API shape, data model) → you and the user. Never delegate a decision.

**Scouts** keep large reads out of your context:
- `Agent(subagent_type: "Explore", model: <scout>, effort: "low")` with a precise question and
  the answer shape you want ("file:line list + 5-line summary").
- For an Ollama scout: `hc worker --mode scout` (see `references/backends.md`).
- To digest a big blob (logs, test output, a large diff), pipe it through `hc ask <model> "…"`.
  You read only the answer.

Have a scout save findings you'll rely on to `<S>/research/R<nn>-<slug>.md`, so workers can read
them later.

## 2. Agree the approach (in chat)

Work out the design with the user in conversation. Explain the reasoning on the non-obvious
parts and adjust as they push back. When there are two or more genuinely different approaches
(data model, API shape, blast radius), present them with trade-offs and a recommendation. Don't
write a spec document yourself; the conversation is the source.

Because the scribe works from the chat, say each decision plainly when it's made, in one line
("Decided: retries live in the client, not the caller"). The scribe can't see your tool calls or
your reasoning by default, so a decision that was only acted on, never said, will be missing or
stale in the spec. Decisions are what the user should hear anyway.

## 3. Breakdown, then the scribe

Propose the task breakdown in chat as a compact table: ID, one-line scope, model, parallel
group, isolation. Read `references/parallel.md` before putting anything in parallel. The core
rules:
- Tasks running at the same time never own the same file.
- Hot shared files (dependency manifests and lockfiles, generated code, central registries and
  constants) are yours, edited after the workers finish.
- When two pieces must agree on an interface, the contract is agreed in the conversation first.

**Gate:** ask the user to confirm the approach and breakdown before anything is written or run.

Then dispatch the scribe:

```
Agent(description: "scribe: spec + plan", subagent_type: "general-purpose",
      model: <coder if it's a Claude model, else "sonnet">, effort: "low",
      prompt: "Read <S>/SCRIBE.md and follow it. Jobs: spec, plan. Notes: <only what isn't in the conversation>")
```

The scribe runs on a coding-grade model rather than the scout. A spec that mixes up superseded
ideas, or invents a requirement, sends every worker in the wrong direction. Its tokens are mostly
input, so the stronger model costs little extra. For a summary-only job, the scout is fine.

When it returns, read `spec.md` and `plan.md`; reading is cheap. Check them for requirements
nobody discussed and for leftovers from ideas you dropped. Fix small slips with a small Edit. If
it's badly off, SendMessage the scribe terse corrections.

**Small (S) tasks skip the documents:** dispatch one worker whose prompt holds the 2–4 line task
plus the pointer to `<S>/WORKER.md`.

If the user changes the plan later, send the scribe the job `update` with a one-line note.

## 4. Execute

Dispatch every runnable task in one message so they run concurrently. The worker prompt is one
line:

```
You are worker T<nn>. Read <S>/WORKER.md and follow it.
```

For a worker in a worktree you created, append: "Work only in <wt>; use absolute paths; run
commands as `cd <wt> && …`."

- **Claude coder:** `Agent(subagent_type: "general-purpose", model: <coder>, effort: "medium",
  description: "T<nn> <few words>", prompt: <the line above>)`. Add `isolation: "worktree"` when
  the plan says worktree and the task doesn't depend on uncommitted changes.
- **Ollama coder:** `hc worker --session <S> --task T<nn> --model ollama:<name> --cwd <dir>
  --allow-bash "<done-when commands>"`, run with Bash `run_in_background: true`.

You set these effort levels; raise them for a task that turns out harder.

Then **go straight back to the user** with a one-line status and continue whatever's still open.
Workers notify you when they finish; never poll them. There is no status board to maintain:
`hc status <S>` rebuilds the state from the files whenever you need it, for example after
context compaction or on resume.

If the user changes direction mid-run, stop the affected workers (SendMessage "stop and report"
for an Agent worker, TaskStop for a background CLI worker), have the scribe update, and
re-dispatch.

## 5. Verify — the quality gate

The user only ever sees verified results. Catching and fixing worker mistakes is your job.

1. Read `<S>/tasks/T<nn>/report.md`. `blocked` means the plan was ambiguous or wrong: fix the
   plan, don't push the worker harder.
2. Look at what actually changed: `git diff --stat`, then the risky hunks only.
3. Re-run the task's *Done when* commands yourself; don't take the report's word for it. Trim
   noisy output with `tail`, or pipe it through `hc ask`.
4. Check the change against the spec and the repo's conventions: scope creep, edits outside
   owned files, debug leftovers, comment noise.
5. On failure, send a terse defect list to the **same** worker so it keeps its context
   (SendMessage, or `hc worker … --resume <worker_session> --message "…"`). Allow two rounds,
   then escalate one tier with a fresh worker that also gets the defect history:
   ollama → haiku → sonnet → opus. Never escalate onto a cloud model. If that fails too, take it
   over yourself when it's small, or tell the user plainly what's stuck.

Report outcomes, not mechanics. Mention retries or escalation only when they matter to the user
(a delay, a cost jump, a spec gap). Never call something verified that you didn't check.

**Nothing is done while something is still running.** Workers, scouts and the scribe report in
the background, and a late report can contradict what you've already said. So while any of
them is in flight, describe the work as in progress and say what you're waiting for. Don't
summarize it as finished, and don't propose a commit. When a late report disagrees with
something you told the user, say so straight away and correct it.

## 6. Integrate, summarize, tear down

Do these in order, each step only after the previous one has finished. Until step 6 passes,
tell the user only that you're wrapping up.

1. Bring worktree results in one at a time, in plan order, with `hc integrate <wt> --remove`,
   building after each. Resolve small conflicts yourself. For big ones, send a resolver worker
   both tasks' sections, with the goal of preserving both intents.
2. Make the reserved shared-file edits, then run the spec's full acceptance checks.
3. Send the scribe the job `summary`, then **wait for its notification**. Don't write the
   wrap-up while it's still running.
4. Read `SUMMARY.md`, starting with *Discrepancies*. Each one is a claim you might be about to
   get wrong. Check it against the code or the checks. If the scribe is right, fix the work or
   correct what you told the user. If you're right, fix the summary. Then ask the scribe to
   re-run the summary job.
5. Run `hc ready <S>`. It fails if any worker is still running, a task isn't `done`, a worktree
   is unintegrated, the summary is missing or older than a report, or the summary still lists
   discrepancies. Resolve every blocker it names. Don't argue with it.
6. Once it prints `READY`, run `hc teardown <S>`. Teardown runs the same check and refuses
   otherwise. It removes tasks, plan, worker logs and worktrees, and keeps `session.md`,
   `spec.md`, `SUMMARY.md` and `research/`. Use `--purge` to leave nothing, if the user prefers.
7. Only now tell the user, in a few lines:
   - what now works;
   - how it was verified;
   - what wasn't verified;
   - one cost line: your share vs. the workers', from the completion notifications and
     `hc status`.

   Workers never commit. Suggest a commit or PR only after step 6, ask before doing it, and
   follow the repo's conventions.

## References

- `references/backends.md`: Agent workers, headless CLI workers, Claude Code over Ollama (local
  and cloud), tool-less Ollama calls, setup checks and model caveats.
- `references/parallel.md`: splitting work, file ownership, shared tree vs worktree, seeded
  worktrees, integration and conflicts.
- `hc` with no arguments lists its commands.
