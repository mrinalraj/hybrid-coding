# Evaluations for hybrid-coding

This directory contains evaluation suites designed to verify both the deterministic orchestration scripts and the LLM agent behaviors for `hybrid-coding`.

## Architecture

The eval suite is split into two complementary tiers:

```
evals/
├── deterministic/                  # Tier 1: Unit & integration tests ($0, fast, CI-ready)
│   ├── test_hc_lifecycle.py       # init, config, status, transcript extraction
│   ├── test_hc_ready_teardown.py  # ready gating (discrepancies, open worktrees, stale summary) & teardown
│   ├── test_make_worktree.py      # detached worktree creation, uncommitted & untracked seeding
│   └── test_integrate_worktree.py # patch application, 3-way merge fallback, conflict markers
├── behavioral/                     # Tier 2: Agentic & workflow evals (LLM-in-the-loop)
│   ├── fixtures/sample_repo/      # Target fixture repository (calculator with unit tests)
│   ├── scenarios/                 # Scenario specifications (Class S bugfix, Class M parallel, etc.)
│   ├── grader.py                  # Policy checks & token efficiency calculators
│   └── run_behavioral_eval.py     # Evaluation runner (dry-run simulation & live Claude Code execution)
├── run_all.sh                      # Unified test runner
└── README.md
```

---

## 1. Running Deterministic Harness Evals (Tier 1)

These tests exercise the entire script interface (`hc.sh`, `hc.py`, `make_worktree.sh`, `integrate_worktree.sh`) against isolated temporary Git repositories:

```bash
python3 -m pytest evals/deterministic/ -v
```

### What is tested:
- **Session Lifecycle:** `init` creates `.hybrid/<sid>`, excludes `.hybrid/` in `.git/info/exclude`, and renders instructions with template path replacements.
- **Ready Gate:** `hc ready` blocks completion if:
  - Any task worktree is unmerged/open.
  - A CLI worker is still running or marked `partial`/`blocked`.
  - `SUMMARY.md` is missing or older than task reports.
  - `SUMMARY.md` lists discrepancies other than `none`.
- **Worktree Seeding:** `make_worktree.sh --seed` copies uncommitted modifications and untracked files into the worktree baseline.
- **3-Way Merging:** `integrate_worktree.sh` tries clean patch apply, falls back to `git merge-file` 3-way merge when both target and worker modified different lines of the same file, and writes conflict markers if changes collide.

---

## 2. Running Behavioral & Agentic Evals (Tier 2)

### A. Dry-Run / CI Simulation
Verifies scenario definitions, acceptance assertions, and git commit policies without incurring LLM token costs:

```bash
python3 evals/behavioral/run_behavioral_eval.py
```

### B. Live Claude Code Execution
Runs real Claude Code headlessly against the fixture repository using the `/hybrid-coding` skill:

```bash
python3 evals/behavioral/run_behavioral_eval.py --live --coder=sonnet --scout=haiku
```

### Scored Policies & Metrics:
1. **Orchestrator Code Authoring Violation:** Checks that the orchestrator did **not** run `Edit` or `Write` on application source files (delegation contract).
2. **Commit Policy:** Checks that workers did not commit changes to git.
3. **Clean Merge Policy:** Asserts no unresolved merge conflict markers remain in the code.
4. **Acceptance Test:** Runs the scenario's specified test command (e.g., `pytest`).
5. **Token Cost Breakdown:** Computes the ratio of Orchestrator output tokens vs worker tokens.

---

## 3. Running All Evals

To execute all automated suites:

```bash
./evals/run_all.sh
```
