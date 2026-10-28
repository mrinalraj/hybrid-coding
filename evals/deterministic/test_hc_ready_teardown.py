import json
import os
import subprocess
import time
import pytest

def run_hc(scripts_dir, cwd, *args):
    cmd = ["bash", os.path.join(scripts_dir, "hc.sh"), *args]
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)

def setup_ready_session(scripts_dir, repo_root, sid):
    """Helper to set up a clean, passing session directory."""
    run_hc(scripts_dir, repo_root, "init", sid)
    session_dir = os.path.join(repo_root, ".hybrid", sid)
    
    # Task T01 done
    t1_dir = os.path.join(session_dir, "tasks", "T01")
    os.makedirs(t1_dir, exist_ok=True)
    with open(os.path.join(t1_dir, "report.md"), "w") as f:
        f.write("status: done\nfiles: file.py\nverification: pass\n")
    with open(os.path.join(t1_dir, "result.json"), "w") as f:
        json.dump({"total_cost_usd": 0.01, "num_turns": 2}, f)
        
    time.sleep(0.05)
    # Summary current with no discrepancies
    summary_path = os.path.join(session_dir, "SUMMARY.md")
    with open(summary_path, "w") as f:
        f.write("# Summary: Test\n\n## Discrepancies\nnone\n\n## Outcome\nAll works.")
        
    return session_dir

def test_ready_fails_when_worktree_open(temp_git_repo, skill_scripts_dir):
    sid = "test-ready-wt"
    session_dir = setup_ready_session(skill_scripts_dir, temp_git_repo, sid)
    
    # Add an unintegrated worktree directory
    os.makedirs(os.path.join(session_dir, "wt", "T01"), exist_ok=True)
    
    res = run_hc(skill_scripts_dir, temp_git_repo, "ready", session_dir)
    assert res.returncode == 1
    assert "NOT READY" in res.stdout
    assert "worktrees not integrated: T01" in res.stdout

def test_ready_fails_when_worker_running(temp_git_repo, skill_scripts_dir):
    sid = "test-ready-running"
    session_dir = setup_ready_session(skill_scripts_dir, temp_git_repo, sid)
    
    # Add task T02 with model file but missing result.json
    t2_dir = os.path.join(session_dir, "tasks", "T02")
    os.makedirs(t2_dir, exist_ok=True)
    with open(os.path.join(t2_dir, "model"), "w") as f:
        f.write("ollama:qwen3-coder")
        
    res = run_hc(skill_scripts_dir, temp_git_repo, "ready", session_dir)
    assert res.returncode == 1
    assert "T02: CLI worker still running" in res.stdout

def test_ready_fails_when_task_status_not_done(temp_git_repo, skill_scripts_dir):
    sid = "test-ready-status"
    session_dir = setup_ready_session(skill_scripts_dir, temp_git_repo, sid)
    
    # Overwrite report with status partial
    with open(os.path.join(session_dir, "tasks", "T01", "report.md"), "w") as f:
        f.write("status: partial\nneeds: helper.py\n")
        
    res = run_hc(skill_scripts_dir, temp_git_repo, "ready", session_dir)
    assert res.returncode == 1
    assert "T01: status partial" in res.stdout

def test_ready_fails_when_summary_missing(temp_git_repo, skill_scripts_dir):
    sid = "test-ready-no-summary"
    session_dir = setup_ready_session(skill_scripts_dir, temp_git_repo, sid)
    os.remove(os.path.join(session_dir, "SUMMARY.md"))
    
    res = run_hc(skill_scripts_dir, temp_git_repo, "ready", session_dir)
    assert res.returncode == 1
    assert "no SUMMARY.md" in res.stdout

def test_ready_fails_when_summary_stale(temp_git_repo, skill_scripts_dir):
    sid = "test-ready-stale-summary"
    session_dir = setup_ready_session(skill_scripts_dir, temp_git_repo, sid)
    
    # Update report.md timestamp to be newer than summary
    time.sleep(0.05)
    with open(os.path.join(session_dir, "tasks", "T01", "report.md"), "a") as f:
        f.write("# update\n")
        
    res = run_hc(skill_scripts_dir, temp_git_repo, "ready", session_dir)
    assert res.returncode == 1
    assert "SUMMARY.md is older than a task report" in res.stdout

def test_ready_fails_when_discrepancies_listed(temp_git_repo, skill_scripts_dir):
    sid = "test-ready-discrepancies"
    session_dir = setup_ready_session(skill_scripts_dir, temp_git_repo, sid)
    
    with open(os.path.join(session_dir, "SUMMARY.md"), "w") as f:
        f.write("# Summary\n\n## Discrepancies\n- T01 modified an unowned file\n\n## Outcome\nDone.")
        
    res = run_hc(skill_scripts_dir, temp_git_repo, "ready", session_dir)
    assert res.returncode == 1
    assert "SUMMARY.md lists discrepancies" in res.stdout

def test_ready_passes(temp_git_repo, skill_scripts_dir):
    sid = "test-ready-pass"
    session_dir = setup_ready_session(skill_scripts_dir, temp_git_repo, sid)
    
    res = run_hc(skill_scripts_dir, temp_git_repo, "ready", session_dir)
    assert res.returncode == 0
    assert "READY" in res.stdout.strip()

def test_teardown_strips_temporary_assets(temp_git_repo, skill_scripts_dir):
    sid = "test-teardown"
    session_dir = setup_ready_session(skill_scripts_dir, temp_git_repo, sid)
    
    # Add files that should be preserved vs stripped
    with open(os.path.join(session_dir, "spec.md"), "w") as f:
        f.write("# Spec")
    with open(os.path.join(session_dir, "plan.md"), "w") as f:
        f.write("# Plan")
        
    res = run_hc(skill_scripts_dir, temp_git_repo, "teardown", session_dir)
    assert res.returncode == 0
    assert "kept:" in res.stdout
    
    # Stripped items
    assert not os.path.exists(os.path.join(session_dir, "tasks"))
    assert not os.path.exists(os.path.join(session_dir, "plan.md"))
    assert not os.path.exists(os.path.join(session_dir, "WORKER.md"))
    assert not os.path.exists(os.path.join(session_dir, "SCRIBE.md"))
    
    # Preserved items
    assert os.path.exists(os.path.join(session_dir, "session.md"))
    assert os.path.exists(os.path.join(session_dir, "spec.md"))
    assert os.path.exists(os.path.join(session_dir, "SUMMARY.md"))

def test_teardown_purge(temp_git_repo, skill_scripts_dir):
    sid = "test-teardown-purge"
    session_dir = setup_ready_session(skill_scripts_dir, temp_git_repo, sid)
    
    res = run_hc(skill_scripts_dir, temp_git_repo, "teardown", session_dir, "--purge")
    assert res.returncode == 0
    assert not os.path.exists(session_dir)
