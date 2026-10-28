import json
import os
import subprocess
import pytest

def run_hc(scripts_dir, cwd, *args):
    """Helper to run hc.sh."""
    cmd = ["bash", os.path.join(scripts_dir, "hc.sh"), *args]
    res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return res

def test_init_fresh_session(temp_git_repo, skill_scripts_dir):
    sid = "test-session-001"
    res = run_hc(skill_scripts_dir, temp_git_repo, "init", sid)
    assert res.returncode == 0
    resolved_repo = os.path.realpath(temp_git_repo)
    assert f"session: {os.path.join(resolved_repo, '.hybrid', sid)} (new)" in res.stdout
    assert "branch main" in res.stdout

    # Check .hybrid/sid contents
    session_dir = os.path.join(temp_git_repo, ".hybrid", sid)
    assert os.path.isdir(session_dir)
    assert os.path.isfile(os.path.join(session_dir, "session.md"))
    assert os.path.isfile(os.path.join(session_dir, "WORKER.md"))
    assert os.path.isfile(os.path.join(session_dir, "SCRIBE.md"))

    # Verify placeholder replacement
    worker_text = open(os.path.join(session_dir, "WORKER.md")).read()
    assert "{{SESSION}}" not in worker_text
    assert session_dir in worker_text

    # Verify git exclude
    exclude_file = os.path.join(temp_git_repo, ".git", "info", "exclude")
    assert os.path.exists(exclude_file)
    assert ".hybrid/\n" in open(exclude_file).read()

def test_config(temp_git_repo, skill_scripts_dir):
    sid = "test-config-002"
    run_hc(skill_scripts_dir, temp_git_repo, "init", sid)
    session_dir = os.path.join(temp_git_repo, ".hybrid", sid)

    res = run_hc(skill_scripts_dir, temp_git_repo, "config", session_dir, "coder=sonnet", "scout=haiku", "title=Test Task")
    assert res.returncode == 0
    assert "ok" in res.stdout

    settings_file = os.path.join(session_dir, "session.md")
    content = open(settings_file).read()
    assert "coder: sonnet" in content
    assert "scout: haiku" in content
    assert "title: Test Task" in content

def test_status_empty(temp_git_repo, skill_scripts_dir):
    sid = "test-status-003"
    run_hc(skill_scripts_dir, temp_git_repo, "init", sid)
    session_dir = os.path.join(temp_git_repo, ".hybrid", sid)

    res = run_hc(skill_scripts_dir, temp_git_repo, "status", session_dir)
    assert res.returncode == 0
    assert "no tasks yet" in res.stdout

def test_status_with_task_and_worktree(temp_git_repo, skill_scripts_dir):
    sid = "test-status-004"
    run_hc(skill_scripts_dir, temp_git_repo, "init", sid)
    session_dir = os.path.join(temp_git_repo, ".hybrid", sid)

    # Mock a task directory
    task_dir = os.path.join(session_dir, "tasks", "T01")
    os.makedirs(task_dir)
    with open(os.path.join(task_dir, "report.md"), "w") as f:
        f.write("status: done\nfiles: app.py\n")
    with open(os.path.join(task_dir, "result.json"), "w") as f:
        json.dump({"total_cost_usd": 0.042, "num_turns": 4, "session_id": "sub-123"}, f)
    with open(os.path.join(task_dir, "model"), "w") as f:
        f.write("sonnet")

    # Mock open worktree directory
    wt_dir = os.path.join(session_dir, "wt", "T01")
    os.makedirs(wt_dir)

    res = run_hc(skill_scripts_dir, temp_git_repo, "status", session_dir)
    assert res.returncode == 0
    assert "T01: report=done" in res.stdout
    assert "cost=$0.0420" in res.stdout
    assert "open worktrees:" in res.stdout
    assert "T01" in res.stdout

def test_transcript_parsing(temp_git_repo, skill_scripts_dir, monkeypatch):
    sid = "dummy-transcript-session"
    fake_config = os.path.join(temp_git_repo, "claude_home")
    proj_dir = os.path.join(fake_config, "projects", "fake_project")
    os.makedirs(proj_dir, exist_ok=True)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", fake_config)

    transcript_path = os.path.join(proj_dir, sid + ".jsonl")
    records = [
        {"type": "user", "message": {"content": "Hello, need help"}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "Sure, let's use hybrid-coding"},
                                                      {"type": "tool_use", "id": "t1", "name": "Skill", "input": {"skill": "hybrid-coding"}}]}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "I will coordinate the tasks."}]}},
        {"type": "user", "message": {"content": "Sounds good!"}}
    ]
    with open(transcript_path, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    res = run_hc(skill_scripts_dir, temp_git_repo, "transcript", sid)
    assert res.returncode == 0
    assert "Hello, need help" in res.stdout
    assert "I will coordinate the tasks." in res.stdout
    assert "Sounds good!" in res.stdout
