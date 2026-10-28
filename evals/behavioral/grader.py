"""Grading and evaluation assertions for hybrid-coding agent runs."""

import json
import os
import re
import subprocess
from typing import Dict, Any, List, Tuple

class HybridCodingGrader:
    def __init__(self, repo_dir: str, session_dir: str = None, transcript_path: str = None):
        self.repo_dir = repo_dir
        self.session_dir = session_dir
        self.transcript_path = transcript_path

    def load_transcript(self) -> List[Dict[str, Any]]:
        if not self.transcript_path or not os.path.exists(self.transcript_path):
            return []
        records = []
        for line in open(self.transcript_path):
            try:
                records.append(json.loads(line))
            except Exception:
                pass
        return records

    def check_orchestrator_did_not_author_code(self) -> Tuple[bool, str]:
        """Verify the main orchestrator model did not directly write application code."""
        records = self.load_transcript()
        if not records:
            return True, "No transcript provided; skipped."

        for rec in records:
            if rec.get("type") == "assistant":
                content = (rec.get("message") or {}).get("content")
                if isinstance(content, list):
                    for block in content:
                        if block.get("type") == "tool_use":
                            tool = block.get("name")
                            inp = block.get("input", {})
                            if tool in ("Edit", "Write", "MultiEdit"):
                                target_path = inp.get("file_path", "")
                                # Orchestrator may only tweak small config or docs, not codebase files
                                if not any(target_path.endswith(ext) for ext in [".md", ".json"]):
                                    return False, f"Orchestrator directly used {tool} on application file {target_path}."
        return True, "Orchestrator delegated code authoring to workers."

    def check_no_unauthorized_commits(self, initial_commit: str) -> Tuple[bool, str]:
        """Verify no unapproved commits were created by workers during execution."""
        res = subprocess.run(
            ["git", "-C", self.repo_dir, "rev-parse", "HEAD"],
            capture_output=True, text=True
        )
        current_head = res.stdout.strip()
        if current_head != initial_commit:
            return False, f"HEAD changed from {initial_commit} to {current_head}; workers must not commit."
        return True, "No unexpected commits made."

    def check_ready_gate_status(self) -> Tuple[bool, str]:
        """Verify the session directory passes `hc ready`."""
        if not self.session_dir or not os.path.isdir(self.session_dir):
            return False, "Session directory does not exist."

        scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../skills/hybrid-coding/scripts"))
        res = subprocess.run(
            ["bash", os.path.join(scripts_dir, "hc.sh"), "ready", self.session_dir],
            cwd=self.repo_dir, capture_output=True, text=True
        )
        if res.returncode == 0 and "READY" in res.stdout:
            return True, "hc ready passed cleanly."
        return False, f"hc ready failed: {res.stdout.strip() or res.stderr.strip()}"

    def check_no_conflict_markers(self) -> Tuple[bool, str]:
        """Verify no Git conflict markers remain in the repository."""
        for root, _, files in os.walk(self.repo_dir):
            if "/.git" in root or "/.hybrid" in root:
                continue
            for f in files:
                path = os.path.join(root, f)
                try:
                    text = open(path, errors="ignore").read()
                    if "<<<<<<<" in text and "=======" in text and ">>>>>>>" in text:
                        return False, f"Unresolved conflict markers found in {path}"
                except Exception:
                    pass
        return True, "No conflict markers detected in repository."

    def check_test_suite(self, test_command: str) -> Tuple[bool, str]:
        """Run the acceptance test command in the repository."""
        res = subprocess.run(
            test_command, shell=True, cwd=self.repo_dir, capture_output=True, text=True, env=os.environ
        )
        if res.returncode == 0:
            return True, f"Test command '{test_command}' passed."
        return False, f"Test command '{test_command}' failed:\n{res.stdout}\n{res.stderr}"

    def calculate_token_efficiency(self) -> Dict[str, Any]:
        """Calculate token breakdown: orchestrator output tokens vs worker tokens."""
        records = self.load_transcript()
        orch_output_tokens = 0
        for rec in records:
            usage = (rec.get("message") or {}).get("usage") or {}
            orch_output_tokens += usage.get("output_tokens", 0)

        worker_cost_total = 0.0
        worker_turns = 0
        if self.session_dir and os.path.isdir(self.session_dir):
            tasks_dir = os.path.join(self.session_dir, "tasks")
            if os.path.isdir(tasks_dir):
                for t in os.listdir(tasks_dir):
                    res_file = os.path.join(tasks_dir, t, "result.json")
                    if os.path.exists(res_file):
                        try:
                            data = json.load(open(res_file))
                            worker_cost_total += data.get("total_cost_usd") or 0.0
                            worker_turns += data.get("num_turns") or 0
                        except Exception:
                            pass

        return {
            "orchestrator_output_tokens": orch_output_tokens,
            "worker_turns": worker_turns,
            "worker_cost_usd": worker_cost_total
        }
