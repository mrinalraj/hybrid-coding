# Parallel work and conflicts

`hc` = `bash ${CLAUDE_SKILL_DIR}/scripts/hc.sh`; `<S>` = the session folder.

Parallelism saves wall-clock time, not tokens, and it creates integration work that lands on
you. Split only when the pieces are truly independent.

## When to split

Good splits:
- **Different repos** (e.g. backend and frontend). These are naturally isolated: give each worker
  its own `cwd`.
- **Same repo, disjoint files** with no build-time interaction (two unrelated handlers, separate
  packages).
- **Layers that meet at an interface,** once the interface is written into the spec (types,
  endpoint shape, message schema). Each side codes against the contract, not against the other
  worker's in-progress code.

Don't split:
- tasks that edit the same file;
- B needs A's code to compile or test (run them in sequence, or have A land the interface stub
  first);
- tiny tasks, where a brief costs more than the work.

## File ownership

Every task lists the files it owns. Tasks that run at the same time never share an owned file.
Some files nearly every task wants to touch. Reserve them for yourself or for a single integration
task that runs last:

- dependency manifests and lockfiles (`go.mod`/`go.sum`, `package.json`, lockfiles,
  `requirements*.txt`, `pyproject.toml`);
- generated code, plus anything that triggers codegen;
- central registries and constant tables: route/nav registries, DI wiring, label and type
  constants, schema declarations;
- shared config and CI files.

If a worker reports something under *needs* in one of these, you make that edit once, for
everyone.

## Isolation: shared tree vs worktree

| Situation | Choice |
|---|---|
| Different repos | none needed: separate `cwd` |
| Same repo, disjoint files, and builds/tests don't write into the tree | **shared tree** (simplest; no integration step) |
| Same repo, ownership might blur, or the build/codegen/`npm install` writes into the tree, or long-running processes would collide (ports, DB fixtures) | **worktree** |

In a shared tree, Go's build cache is safe to share; `npm install`, codegen and anything else
that rewrites tracked or shared files is not. Run those one at a time, or do them yourself.

### Worktrees only see committed state

`Agent(isolation: "worktree")` branches from **HEAD**. It does not include uncommitted changes in
your tree, and that includes work you integrated earlier in this session. If a task depends on
uncommitted state, create a seeded worktree instead:

```bash
hc wt <S> T04 --seed   # prints the worktree path
```

That copies the current uncommitted changes (untracked files included) into
`<session>/wt/T04` and stages them as the baseline, so integration later carries back only the
worker's own changes. Then dispatch the worker without `isolation`, telling it to work only in
that path (the pointer-prompt addendum in SKILL.md), or pass the path as `--cwd` to
`hc worker`. Go tooling skips the `.hybrid` dot-directory, so these nested worktrees don't
leak into `./...` patterns. Check this for other toolchains that glob the repo.

## Integration

Apply worktree results one at a time, in the plan's integration order:

```bash
hc integrate <worker-wt> [<target-wt>] --save <S>/tasks/T04/T04.patch
```

- It never commits and never touches either index. It tries a clean patch apply first, then
  falls back to a per-file 3-way merge (`git merge-file`). The fallback works even when the
  target has uncommitted edits to the same files, which is normal mid-session, and writes
  conflict markers where both sides changed the same lines. Binary files and delete-vs-edit
  cases are listed as skipped for you to handle.
- Build and run the relevant tests after **each** apply, so a breakage points at one task.
- **Conflicts:** the script lists the conflicted files. Small conflicts you resolve yourself:
  you have the spec and both task sections, so you know what each side intended. For large
  ones, dispatch a resolver worker whose brief includes both task sections and the conflicted
  files, with "preserve both intents" as the goal, and then verify it like any other task.
- `--remove` deletes the worker worktree after a successful apply.

Once everything is in, do the reserved shared-file edits, then run the spec's full acceptance
checks yourself. Parallel tasks that each pass alone can still fail together.
