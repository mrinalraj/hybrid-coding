#!/usr/bin/env python3
"""Runner for hybrid-coding behavioral evaluations.

Can be run in two modes:
  1. Dry-run / Validation mode (default or --dry-run):
     Validates scenario definitions, sets up a temporary fixture environment,
     simulates a compliant hybrid-coding run, and verifies that the grader accurately scores it.
  2. Live mode (--live):
     Invokes `claude -p` headlessly on the fixture repo with the scenario prompt,
     parses the resulting transcript and git state, and outputs the eval score card.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from grader import HybridCodingGrader

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCENARIOS_DIR = os.path.join(BASE_DIR, "scenarios")
FIXTURES_DIR = os.path.join(BASE_DIR, "fixtures")

def setup_fixture_repo(fixture_name: str = "sample_repo") -> str:
    """Copies the fixture repo to a clean temporary git repository."""
    src_dir = os.path.join(FIXTURES_DIR, fixture_name)
    temp_dir = tempfile.mkdtemp(prefix="hc_eval_run_")
    
    # Copy files
    for item in os.listdir(src_dir):
        s = os.path.join(src_dir, item)
        d = os.path.join(temp_dir, item)
        if os.path.isdir(s):
            shutil.copytree(s, d)
        else:
            shutil.copy2(s, d)
            
    # Init git repo
    subprocess.run(["git", "init", "-b", "main", temp_dir], check=True, capture_output=True)
    subprocess.run(["git", "-C", temp_dir, "config", "user.name", "Eval Runner"], check=True)
    subprocess.run(["git", "-C", temp_dir, "config", "user.email", "eval@example.com"], check=True)
    subprocess.run(["git", "-C", temp_dir, "add", "-A"], check=True)
    subprocess.run(["git", "-C", temp_dir, "commit", "-m", "Initial commit for eval"], check=True)
    return temp_dir

def run_dry_run_scenario(scenario_path: str):
    """Simulates a scenario execution and verifies grader logic."""
    scenario = json.load(open(scenario_path))
    print(f"\n[EVAL] Running Scenario: {scenario['name']} ({scenario['id']})")
    print(f"       Prompt: {scenario['task_prompt']}")
    
    temp_repo = setup_fixture_repo("sample_repo")
    try:
        initial_commit = subprocess.run(
            ["git", "-C", temp_repo, "rev-parse", "HEAD"],
            capture_output=True, text=True
        ).stdout.strip()
        
        # Simulate worker changes based on scenario id
        sc_id = scenario.get("id")
        if sc_id == "scenario_01_single_worker_bugfix":
            calc_path = os.path.join(temp_repo, "calc.py")
            content = open(calc_path).read()
            fixed = content.replace("return 0  # Bug: should raise ZeroDivisionError(\"division by zero\")",
                                    "raise ZeroDivisionError(\"division by zero\")")
            with open(calc_path, "w") as f:
                f.write(fixed)
        elif sc_id == "scenario_02_multi_worker_parallel":
            # Simulate worker 1 creating math_ops.py
            with open(os.path.join(temp_repo, "math_ops.py"), "w") as f:
                f.write("def power(b, e): return b ** e\n")
            # Simulate worker 2 creating advanced_ops.py
            with open(os.path.join(temp_repo, "advanced_ops.py"), "w") as f:
                f.write("import math\ndef factorial(n): return math.factorial(n)\n")
            # Create test_ops.py
            with open(os.path.join(temp_repo, "test_ops.py"), "w") as f:
                f.write("import math_ops, advanced_ops\n"
                        "def test_power(): assert math_ops.power(2, 3) == 8\n"
                        "def test_factorial(): assert advanced_ops.factorial(4) == 24\n")
        elif sc_id == "scenario_03_conflict_resolution":
            # Pass calc.py test
            calc_path = os.path.join(temp_repo, "calc.py")
            content = open(calc_path).read()
            fixed = content.replace("return 0  # Bug: should raise ZeroDivisionError(\"division by zero\")",
                                    "raise ZeroDivisionError(\"division by zero\")")
            with open(calc_path, "w") as f:
                f.write(fixed)
            
        grader = HybridCodingGrader(repo_dir=temp_repo)
        
        # 1. Test suite check
        passed, msg = grader.check_test_suite(scenario.get("test_command", "pytest"))
        print(f"  ✓ Acceptance Check: {msg if passed else 'FAIL: ' + msg}")
        assert passed, f"Acceptance check failed: {msg}"
        
        # 2. No unauthorized commits check
        passed, msg = grader.check_no_unauthorized_commits(initial_commit)
        print(f"  ✓ Git Commit Policy: {msg}")
        assert passed, f"Git policy violated: {msg}"
        
        # 3. No conflict markers check
        passed, msg = grader.check_no_conflict_markers()
        print(f"  ✓ Clean Merge Policy: {msg}")
        assert passed, f"Conflict markers found: {msg}"
        
        print(f"  ⭐ Result: PASS (Compliant)")
    finally:
        shutil.rmtree(temp_repo, ignore_errors=True)

def run_live_scenario(scenario_path: str, model_coder: str = "sonnet", model_scout: str = "haiku", main_model: str = "sonnet"):
    """Runs real headless Claude Code against the scenario."""
    scenario = json.load(open(scenario_path))
    print(f"\n[LIVE EVAL] Scenario: {scenario['name']}")
    
    temp_repo = setup_fixture_repo("sample_repo")
    try:
        initial_commit = subprocess.run(
            ["git", "-C", temp_repo, "rev-parse", "HEAD"],
            capture_output=True, text=True
        ).stdout.strip()
        
        skill_prompt = f"/hybrid-coding coder={model_coder} scout={model_scout} {scenario['task_prompt']}"
        print(f"Invoking Claude Code with main model [{main_model}]: {skill_prompt}")
        
        cmd = [
            "claude", "-p", skill_prompt,
            "--model", main_model,
            "--output-format", "json",
            "--permission-mode", "acceptEdits"
        ]
        res = subprocess.run(cmd, cwd=temp_repo, capture_output=True, text=True)
        print(f"Claude exited with status {res.returncode}")
        
        grader = HybridCodingGrader(repo_dir=temp_repo)
        passed, msg = grader.check_test_suite(scenario.get("test_command", "pytest"))
        print(f"Acceptance test: {'PASS' if passed else 'FAIL'} - {msg}")
        
        tokens = grader.calculate_token_efficiency()
        print(f"Token Breakdown: {json.dumps(tokens, indent=2)}")
    finally:
        shutil.rmtree(temp_repo, ignore_errors=True)

def main():
    parser = argparse.ArgumentParser(description="Run hybrid-coding evals.")
    parser.add_argument("--scenario", help="Path to scenario JSON. If omitted, runs all.")
    parser.add_argument("--live", action="store_true", help="Run live Claude Code execution.")
    parser.add_argument("--main-model", default="sonnet", help="Main orchestrator model (e.g. sonnet, haiku, opus).")
    parser.add_argument("--coder", default="sonnet", help="Coder model for live runs.")
    parser.add_argument("--scout", default="haiku", help="Scout model for live runs.")
    args = parser.parse_args()

    scenarios = [os.path.join(SCENARIOS_DIR, f) for f in os.listdir(SCENARIOS_DIR) if f.endswith(".json")]
    if args.scenario:
        scenarios = [args.scenario]

    for sc in sorted(scenarios):
        if args.live:
            run_live_scenario(sc, model_coder=args.coder, model_scout=args.scout, main_model=args.main_model)
        else:
            run_dry_run_scenario(sc)

if __name__ == "__main__":
    main()
