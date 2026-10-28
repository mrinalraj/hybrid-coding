# hybrid-coding

## TL;DR

Think of it like building a treehouse with a team.

**The team**

- **The architect (the main model, e.g. Opus).** Very smart and very expensive: you pay for every
  word it says or writes. It's the only one you talk to.
- **The note-taker (the scribe).** A cheaper helper who listens to your conversation with the
  architect and writes up the blueprint. It's called the scribe because that's an old word for
  someone whose job is writing things down.
- **The scouts.** Cheap helpers who run around and check things, like "where's the strongest
  branch?", then come back with a short answer.
- **The builders (the workers, e.g. Sonnet or an Ollama model).** Cheaper helpers who do the
  actual hammering, meaning they write the code.

**How a job goes**

1. **You say what you want:** "I want a treehouse with a rope ladder."
2. **The architect thinks about it** and sends scouts to look around, so it doesn't have to climb
   every tree itself.
3. **You and the architect talk it over.** "Rope ladder or wooden steps?" "Rope." The architect
   says each decision out loud.
4. **The note-taker writes the blueprint** from that conversation. Writing is what costs the
   architect the most, so the architect never writes it out itself. It just reads the finished
   blueprint quickly to check it's right.
5. **The builders build.** Each one gets a different part, like the floor or the ladder, and two
   builders never work on the same part at once, so they don't bump into each other. They can
   work at the same time while the architect keeps chatting with you.
6. **The architect inspects everything.** If a builder got something wrong, the architect quietly
   sends them back to fix it. If they keep getting it wrong, it sends a better builder. You only
   hear "done, and I checked it" once it's actually right.
7. **Cleanup.** The note-taker writes a short "what we built" note, and the leftover scraps are
   thrown away. Only the blueprint and that note stay, in a hidden `.hybrid` folder.

**Why bother?** The architect costs a lot per word. With this setup, it only speaks for the parts
that need its brain: talking with you, making decisions and checking the work. The cheaper helpers
do all the writing, building and searching.

## Details

A Claude Code skill for spec-first, cost-saving agentic coding.

Output tokens from Opus-class models are the expensive part of an agentic coding session, so
this skill keeps the main model on work that needs its judgment and hands the rest to cheaper
models:

| Role | Model | Does |
|---|---|---|
| Orchestrator | your session model (e.g. Opus) | triage, design discussion with you, task breakdown, reviewing and verifying results |
| Scribe | scout model (e.g. Haiku) | writes the spec, plan and final summary from the conversation transcript |
| Scouts | scout model | codebase discovery, digesting large logs and diffs |
| Workers | coding model (e.g. Sonnet, or an Ollama model) | write the code, in parallel where safe |

You only talk to the orchestrator. It verifies each worker's output (diff review, re-running
builds and tests) and sends fixes back before reporting, so you see verified results rather than
worker mistakes.

## Install

As a Claude Code plugin:

```
/plugin marketplace add mrinalraj/hybrid-coding
/plugin install hybrid-coding@hybrid-coding
```

With the skills CLI:

```
npx skills add mrinalraj/hybrid-coding
```

Or manually: copy or symlink `skills/hybrid-coding` into `~/.claude/skills/`.

Requirements: Claude Code, `git`, `bash`, `python3`. Ollama is optional.

## Use

```
/hybrid-coding coder=sonnet scout=haiku add retry with backoff to the sync client
```

Any setting you leave out, it asks for. Then it:

1. **Sets up silently.** A per-session folder `.hybrid/<session-id>/` is created at load,
   kept out of git via `.git/info/exclude`. Available backends (Claude models, local Ollama
   models, Ollama cloud models when signed in) are detected at the same time.
2. **Triages** the request and sends scouts for discovery.
3. **Agrees the approach and task breakdown with you** in chat.
4. **Has the scribe write** `spec.md` and `plan.md` from the conversation, inside a subagent, so
   the documents never pass through the orchestrator's output.
5. **Dispatches workers**, in parallel where file ownership allows, using worktrees when needed,
   and stays available to you while they run.
6. **Verifies** each result and sends fixes back to the same worker, escalating the model tier
   if needed.
7. **Integrates** worktree results (3-way merge, no commits), runs the acceptance checks, has
   the scribe write `SUMMARY.md`, and **tears down** the session folder to just the spec,
   summary and research notes.

Workers never commit. The orchestrator asks you before committing.

## Ollama

- **Coding workers:** use `coder=ollama:<model>`. The worker runs headless Claude Code against
  Ollama's Anthropic-compatible API.
- **Cloud models** (`<name>-cloud` / `<name>:cloud`): work the same way after `ollama signin`,
  with nothing to pull. They send the code they read to ollama.com.
- **Local models:** need a tool-capable model and a large context window
  (`OLLAMA_CONTEXT_LENGTH=65536 ollama serve`).
- **Tool-less calls:** `hc ask` pipes a large blob to an Ollama model and returns only the answer.

See `skills/hybrid-coding/references/backends.md`.

## Layout

```
.claude-plugin/          plugin + marketplace manifests
skills/hybrid-coding/
  SKILL.md               orchestrator workflow
  assets/                worker contract, scribe instructions, spec/plan/summary templates
  references/            backends (Claude, Ollama), parallel work and conflict handling
  scripts/hc.sh          single entry point: init, config, status, transcript, worker, ask, wt, integrate, teardown
```

## License

MIT. See [LICENSE](LICENSE).
