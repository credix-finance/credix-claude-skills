#!/usr/bin/env python3
"""Create one worktree per task in swarm.json. Idempotent.

Usage:
    python setup_worktrees.py <swarm.json>

Behavior:
  - Verifies cwd is inside a git repo.
  - `git fetch origin <trunk>` so worktrees are cut from latest.
  - Adds `.swarm/` to .gitignore if missing.
  - For each task, ensures a worktree at `<repo>/.swarm/worktrees/<id>/` exists
    on branch `swarm/<id>`, cut from `origin/<trunk>`.
  - Skips existing worktrees. Existing-branch-no-worktree → add on existing
    branch. Neither exists → create with `-b`.
"""
import json
import subprocess
import sys
from pathlib import Path


def run(args, check=True, capture=True) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        check=check,
        capture_output=capture,
        text=True,
    )


def die(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def repo_root() -> Path:
    r = run(["git", "rev-parse", "--is-inside-work-tree"], check=False)
    if r.returncode != 0 or r.stdout.strip() != "true":
        die("not inside a git repo")
    r = run(["git", "rev-parse", "--show-toplevel"])
    return Path(r.stdout.strip())


def list_worktree_paths() -> set:
    r = run(["git", "worktree", "list", "--porcelain"])
    paths = set()
    for line in r.stdout.splitlines():
        if line.startswith("worktree "):
            paths.add(line.split(" ", 1)[1].strip())
    return paths


def branch_exists(name: str) -> bool:
    r = run(
        ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{name}"],
        check=False,
    )
    return r.returncode == 0


def ensure_gitignore(root: Path) -> None:
    gi = root / ".gitignore"
    entry = ".swarm/"
    if gi.exists():
        lines = gi.read_text().splitlines()
        if any(line.strip() == entry or line.strip() == ".swarm" for line in lines):
            return
        with gi.open("a") as f:
            if lines and lines[-1] != "":
                f.write("\n")
            f.write(f"{entry}\n")
    else:
        gi.write_text(f"{entry}\n")
    print(f"  [.gitignore] added `{entry}`")


def ensure_worktree(root: Path, task_id: str, trunk: str) -> str:
    """Return a short status tag: 'skip', 'add', or 'create'."""
    branch = f"swarm/{task_id}"
    wt_path = root / ".swarm" / "worktrees" / task_id

    existing_paths = list_worktree_paths()
    if str(wt_path.resolve()) in {str(Path(p).resolve()) for p in existing_paths}:
        return "skip"

    wt_path.parent.mkdir(parents=True, exist_ok=True)

    if branch_exists(branch):
        r = run(
            ["git", "worktree", "add", str(wt_path), branch],
            check=False,
        )
        if r.returncode != 0:
            die(f"failed to add worktree for {task_id} on existing branch {branch}: {r.stderr.strip()}")
        return "add"

    r = run(
        ["git", "worktree", "add", "-b", branch, str(wt_path), f"origin/{trunk}"],
        check=False,
    )
    if r.returncode != 0:
        die(f"failed to create worktree for {task_id}: {r.stderr.strip()}")
    return "create"


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: setup_worktrees.py <swarm.json>", file=sys.stderr)
        sys.exit(1)

    path = Path(sys.argv[1])
    if not path.exists():
        die(f"file not found: {path}")
    data = json.loads(path.read_text())
    tasks = data.get("tasks") or []
    if not tasks:
        die("no tasks in swarm.json")
    trunk = data.get("trunk", "main")

    root = repo_root()

    print(f"Fetching origin/{trunk}...")
    r = run(["git", "fetch", "origin", trunk], check=False)
    if r.returncode != 0:
        die(f"git fetch origin {trunk} failed: {r.stderr.strip()}")

    ensure_gitignore(root)

    print(f"Setting up {len(tasks)} worktree(s) under {root / '.swarm' / 'worktrees'}/ ...")
    for t in tasks:
        tid = t["id"]
        status = ensure_worktree(root, tid, trunk)
        wt_path = root / ".swarm" / "worktrees" / tid
        print(f"  [{status:<6}] {tid:<30} swarm/{tid} @ {wt_path.relative_to(root)}")

    print("Done.")


if __name__ == "__main__":
    main()
