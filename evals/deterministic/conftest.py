import os
import shutil
import subprocess
import tempfile
import pytest

@pytest.fixture
def temp_git_repo():
    """Create a temporary initialized git repository for testing."""
    temp_dir = tempfile.mkdtemp(prefix="hc_test_repo_")
    subprocess.run(["git", "init", "-b", "main", temp_dir], check=True, capture_output=True)
    subprocess.run(["git", "-C", temp_dir, "config", "user.name", "Test User"], check=True)
    subprocess.run(["git", "-C", temp_dir, "config", "user.email", "test@example.com"], check=True)
    
    # Create initial commit
    readme = os.path.join(temp_dir, "README.md")
    with open(readme, "w") as f:
        f.write("# Test Repo\n")
    subprocess.run(["git", "-C", temp_dir, "add", "README.md"], check=True)
    subprocess.run(["git", "-C", temp_dir, "commit", "-m", "Initial commit"], check=True)
    
    yield temp_dir
    
    shutil.rmtree(temp_dir, ignore_errors=True)

@pytest.fixture
def skill_scripts_dir():
    """Return the absolute path to skills/hybrid-coding/scripts."""
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    return os.path.join(repo_root, "skills", "hybrid-coding", "scripts")
