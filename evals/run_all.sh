#!/usr/bin/env bash
# Run all hybrid-coding evaluations
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
REPO_ROOT=$(cd "$HERE/.." && pwd)

echo "=========================================================="
echo " Running Tier 1: Deterministic Harness & Script Evals"
echo "=========================================================="
python3 -m pytest "$HERE/deterministic" -v

echo ""
echo "=========================================================="
echo " Running Tier 2: Behavioral Grader & Scenario Verifications"
echo "=========================================================="
python3 "$HERE/behavioral/run_behavioral_eval.py"

echo ""
echo "=========================================================="
echo " All automated test suites passed successfully!"
echo " To run live LLM agentic evaluations with Claude Code, run:"
echo "   python3 evals/behavioral/run_behavioral_eval.py --live"
echo "=========================================================="
