"""Daily Autonomous Committer for Huginn-and-Muninn.
Runs daily in the background to create real, incremental commits and push to GitHub.
"""
import os
import sys
import subprocess
import datetime
from pathlib import Path

REPO_DIR = Path(r"E:\taknee-ide").resolve()
LOG_FILE = REPO_DIR / ".taknee" / "committer.log"

def log(msg: str):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

def run_cmd(cmd: list[str], cwd=REPO_DIR) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)

def has_changes() -> bool:
    r = run_cmd(["git", "status", "--porcelain"])
    return bool(r.stdout.strip())

def get_modified_files() -> list[str]:
    r = run_cmd(["git", "status", "--porcelain"])
    files = []
    for line in r.stdout.splitlines():
        if line.strip():
            # strip status prefix (e.g., ' M ', '?? ', 'M  ')
            parts = line[3:].strip()
            if parts:
                files.append(parts)
    return files

def group_files_to_commit(files: list[str]) -> list[dict]:
    """Group changed files into small, atomic, logical commits."""
    groups = []
    # 1. Docs
    docs = [f for f in files if f.startswith("docs/") or f.endswith(".md")]
    if docs:
        groups.append({"files": docs, "msg": "docs: update documentation and roadmap specs"})
    
    # 2. Tests
    tests = [f for f in files if f.startswith("tests/") and f not in docs]
    if tests:
        groups.append({"files": tests, "msg": "test: expand test coverage and assertions"})
    
    # 3. Router & catalog
    router = [f for f in files if any(x in f for x in ("router", "catalog", "providers", "settings")) and f not in docs and f not in tests]
    if router:
        groups.append({"files": router, "msg": "feat(router): optimize multi-provider routing and settings"})
        
    # 4. Engine & Tools
    core = [f for f in files if any(x in f for x in ("orchestrator", "tools", "patches", "store", "compaction", "retrieval", "research", "plugins")) and f not in docs and f not in tests and f not in router]
    if core:
        groups.append({"files": core, "msg": "feat(engine): refine kernel execution and tool harness"})
        
    # 5. Extension & Apps
    apps = [f for f in files if (f.startswith("apps/") or f.startswith(".vscode/")) and f not in docs and f not in tests]
    if apps:
        groups.append({"files": apps, "msg": "feat(extension): update editor panels and client bindings"})
        
    # 6. Remaining files
    claimed = set(sum([g["files"] for g in groups], []))
    remaining = [f for f in files if f not in claimed]
    if remaining:
        groups.append({"files": remaining, "msg": "chore: project maintenance and configuration updates"})
        
    return groups

def run_daily_cycle():
    log("Starting daily committer cycle...")
    os.chdir(REPO_DIR)
    
    # 1. Check if git status has changes
    files = get_modified_files()
    if not files:
        log("Working tree clean. No pending uncommitted changes.")
        # Optional: try to push any unpushed commits
        push_r = run_cmd(["git", "push", "origin", "main"])
        if push_r.returncode == 0:
            log("Git push successful.")
        else:
            log(f"Git push status: {push_r.stderr.strip() or push_r.stdout.strip() or 'OK'}")
        return

    log(f"Found {len(files)} modified/untracked files.")
    groups = group_files_to_commit(files)
    
    # Process one or small batches per daily run
    for group in groups:
        log(f"Staging group: {group['msg']} ({len(group['files'])} files)")
        for f in group["files"]:
            run_cmd(["git", "add", f])
            
        # Verify anything staged
        diff_r = run_cmd(["git", "diff", "--cached", "--quiet"])
        if diff_r.returncode != 0:
            commit_r = run_cmd(["git", "commit", "-m", group["msg"]])
            if commit_r.returncode == 0:
                log(f"Committed: {group['msg']}")
            else:
                log(f"Commit error: {commit_r.stderr.strip()}")
                
    # Push to origin
    log("Pushing commits to remote origin main...")
    push_r = run_cmd(["git", "push", "origin", "main"])
    if push_r.returncode == 0:
        log("Successfully pushed daily commits to GitHub!")
    else:
        log(f"Push output: {push_r.stderr.strip() or push_r.stdout.strip()}")

if __name__ == "__main__":
    run_daily_cycle()
