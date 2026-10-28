import os
import subprocess
import pytest

def run_make_wt(scripts_dir, cwd, *args):
    cmd = ["bash", os.path.join(scripts_dir, "make_worktree.sh"), *args]
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)

def test_make_worktree_basic(temp_git_repo, skill_scripts_dir):
    session_dir = os.path.join(temp_git_repo, ".hybrid", "sess-wt-1")
    os.makedirs(session_dir, exist_ok=True)
    
    res = run_make_wt(skill_scripts_dir, temp_git_repo, session_dir, "T01")
    assert res.returncode == 0
    wt_path = res.stdout.strip()
    assert wt_path == os.path.join(session_dir, "wt", "T01")
    assert os.path.isdir(wt_path)
    
    # Check it's a valid detached worktree
    git_status = subprocess.run(["git", "-C", wt_path, "status"], capture_output=True, text=True)
    assert git_status.returncode == 0
    # In git, detached HEAD appears as "HEAD detached" or "Not currently on any branch"
    assert ("HEAD detached" in git_status.stdout) or ("Not currently on any branch" in git_status.stdout)

def test_make_worktree_duplicate_fails(temp_git_repo, skill_scripts_dir):
    session_dir = os.path.join(temp_git_repo, ".hybrid", "sess-wt-2")
    os.makedirs(session_dir, exist_ok=True)
    
    res1 = run_make_wt(skill_scripts_dir, temp_git_repo, session_dir, "T01")
    assert res1.returncode == 0
    
    res2 = run_make_wt(skill_scripts_dir, temp_git_repo, session_dir, "T01")
    assert res2.returncode == 1
    assert "already exists" in res2.stderr

def test_make_worktree_seeded(temp_git_repo, skill_scripts_dir):
    session_dir = os.path.join(temp_git_repo, ".hybrid", "sess-wt-seeded")
    os.makedirs(session_dir, exist_ok=True)
    
    # 1. Modify an existing tracked file in main repo without committing
    readme = os.path.join(temp_git_repo, "README.md")
    with open(readme, "a") as f:
        f.write("\nUncommitted addition to readme.\n")
        
    # 2. Add an untracked file
    untracked = os.path.join(temp_git_repo, "new_helper.py")
    with open(untracked, "w") as f:
        f.write("# Untracked helper\n")
        
    # 3. Create seeded worktree
    res = run_make_wt(skill_scripts_dir, temp_git_repo, session_dir, "T02", "--seed")
    assert res.returncode == 0
    wt_path = res.stdout.strip()
    
    # Verify uncommitted and untracked files are copied into the worktree
    wt_readme = os.path.join(wt_path, "README.md")
    wt_untracked = os.path.join(wt_path, "new_helper.py")
    assert os.path.exists(wt_readme)
    assert "Uncommitted addition to readme" in open(wt_readme).read()
    assert os.path.exists(wt_untracked)
    
    # Verify they are staged in the worktree
    diff_cached = subprocess.run(["git", "-C", wt_path, "diff", "--cached", "--name-only"], capture_output=True, text=True)
    assert "README.md" in diff_cached.stdout
    assert "new_helper.py" in diff_cached.stdout
    
    # Verify hybrid-seeded marker exists
    git_dir = subprocess.run(["git", "-C", wt_path, "rev-parse", "--absolute-git-dir"], capture_output=True, text=True).stdout.strip()
    assert os.path.isfile(os.path.join(git_dir, "hybrid-seeded"))
