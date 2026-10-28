import os
import subprocess
import pytest

def run_integrate(scripts_dir, cwd, *args):
    cmd = ["bash", os.path.join(scripts_dir, "integrate_worktree.sh"), *args]
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)

def run_make_wt(scripts_dir, cwd, *args):
    cmd = ["bash", os.path.join(scripts_dir, "make_worktree.sh"), *args]
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)

def test_integrate_clean_apply(temp_git_repo, skill_scripts_dir):
    session_dir = os.path.join(temp_git_repo, ".hybrid", "sess-int-1")
    os.makedirs(session_dir, exist_ok=True)
    
    # Create worktree
    res = run_make_wt(skill_scripts_dir, temp_git_repo, session_dir, "T01")
    wt_path = res.stdout.strip()
    
    # Worker creates a new file and edits existing
    with open(os.path.join(wt_path, "feature.py"), "w") as f:
        f.write("def do_something(): pass\n")
        
    # Integrate into temp_git_repo
    int_res = run_integrate(skill_scripts_dir, temp_git_repo, wt_path)
    assert int_res.returncode == 0
    assert "applied cleanly" in int_res.stdout
    
    # Check file exists in target repo uncommitted
    target_feature = os.path.join(temp_git_repo, "feature.py")
    assert os.path.exists(target_feature)
    assert open(target_feature).read() == "def do_something(): pass\n"

def test_integrate_seeded_worktree(temp_git_repo, skill_scripts_dir):
    session_dir = os.path.join(temp_git_repo, ".hybrid", "sess-int-seeded")
    os.makedirs(session_dir, exist_ok=True)
    
    # Initial file in main repo
    with open(os.path.join(temp_git_repo, "shared.py"), "w") as f:
        f.write("# line 1\n# line 2\n")
    subprocess.run(["git", "-C", temp_git_repo, "add", "shared.py"], check=True)
    subprocess.run(["git", "-C", temp_git_repo, "commit", "-m", "add shared.py"], check=True)
    
    # Main repo has uncommitted edit (baseline seed)
    with open(os.path.join(temp_git_repo, "shared.py"), "w") as f:
        f.write("# line 1 (baseline edit)\n# line 2\n")
        
    # Create seeded worktree
    res = run_make_wt(skill_scripts_dir, temp_git_repo, session_dir, "T02", "--seed")
    wt_path = res.stdout.strip()
    
    # Worker makes an additional edit
    with open(os.path.join(wt_path, "shared.py"), "a") as f:
        f.write("# line 3 (worker edit)\n")
        
    # Integrate back
    int_res = run_integrate(skill_scripts_dir, temp_git_repo, wt_path)
    assert int_res.returncode == 0
    
    final_content = open(os.path.join(temp_git_repo, "shared.py")).read()
    assert "# line 1 (baseline edit)" in final_content
    assert "# line 3 (worker edit)" in final_content

def test_integrate_three_way_merge(temp_git_repo, skill_scripts_dir):
    # Setup file with lines top and bottom
    app_py = os.path.join(temp_git_repo, "app.py")
    with open(app_py, "w") as f:
        f.write("line 1: header\nline 2: middle\nline 3: footer\n")
    subprocess.run(["git", "-C", temp_git_repo, "add", "app.py"], check=True)
    subprocess.run(["git", "-C", temp_git_repo, "commit", "-m", "initial app.py"], check=True)
    
    session_dir = os.path.join(temp_git_repo, ".hybrid", "sess-int-3way")
    os.makedirs(session_dir, exist_ok=True)
    
    res = run_make_wt(skill_scripts_dir, temp_git_repo, session_dir, "T03")
    wt_path = res.stdout.strip()
    
    # Worker edits header
    with open(os.path.join(wt_path, "app.py"), "w") as f:
        f.write("line 1: MODIFIED HEADER\nline 2: middle\nline 3: footer\n")
        
    # Meanwhile, main target repo uncommitted edit modifies footer
    with open(app_py, "w") as f:
        f.write("line 1: header\nline 2: middle\nline 3: MODIFIED FOOTER\n")
        
    # Integrate should trigger 3-way merge and succeed
    int_res = run_integrate(skill_scripts_dir, temp_git_repo, wt_path)
    assert int_res.returncode == 0
    assert "3-way merged per file" in int_res.stdout
    assert "merged: app.py" in int_res.stdout
    
    merged_content = open(app_py).read()
    assert "line 1: MODIFIED HEADER" in merged_content
    assert "line 3: MODIFIED FOOTER" in merged_content

def test_integrate_conflict_handling(temp_git_repo, skill_scripts_dir):
    app_py = os.path.join(temp_git_repo, "conflict.py")
    with open(app_py, "w") as f:
        f.write("COMMON BASELINE\n")
    subprocess.run(["git", "-C", temp_git_repo, "add", "conflict.py"], check=True)
    subprocess.run(["git", "-C", temp_git_repo, "commit", "-m", "conflict base"], check=True)
    
    session_dir = os.path.join(temp_git_repo, ".hybrid", "sess-int-conflict")
    os.makedirs(session_dir, exist_ok=True)
    
    res = run_make_wt(skill_scripts_dir, temp_git_repo, session_dir, "T04")
    wt_path = res.stdout.strip()
    
    # Worker changes line
    with open(os.path.join(wt_path, "conflict.py"), "w") as f:
        f.write("WORKER CHANGE\n")
        
    # Target changes same line differently
    with open(app_py, "w") as f:
        f.write("TARGET CHANGE\n")
        
    int_res = run_integrate(skill_scripts_dir, temp_git_repo, wt_path)
    assert int_res.returncode == 1
    assert "CONFLICT (markers written): conflict.py" in int_res.stdout
    
    content = open(app_py).read()
    assert "<<<<<<<" in content
    assert "TARGET CHANGE" in content
    assert "=======" in content
    assert "WORKER CHANGE" in content
    assert ">>>>>>>" in content

def test_integrate_remove_flag(temp_git_repo, skill_scripts_dir):
    session_dir = os.path.join(temp_git_repo, ".hybrid", "sess-int-remove")
    os.makedirs(session_dir, exist_ok=True)
    
    res = run_make_wt(skill_scripts_dir, temp_git_repo, session_dir, "T05")
    wt_path = res.stdout.strip()
    
    with open(os.path.join(wt_path, "mod.py"), "w") as f:
        f.write("# worker code\n")
        
    int_res = run_integrate(skill_scripts_dir, temp_git_repo, wt_path, "--remove")
    assert int_res.returncode == 0
    assert not os.path.exists(wt_path)
