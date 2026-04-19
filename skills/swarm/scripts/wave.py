#!/usr/bin/env python3
"""Print task ids that are ready to spawn: pending and all deps merged.

Usage:
    python wave.py <swarm.json>

Reads .swarm/state.json (absent = empty dict). Status values:
    pending   — default (unspawned)
    spawned   — teammate is running
    merged    — PR merged (terminal)
    escalated — hit a stop condition (teammate idle)
    cancelled — human-cancelled (terminal)

Terminal statuses: merged, cancelled. (escalated tasks may resume after
human intervention; they are NOT treated as terminal for downstream gating —
downstream tasks still wait for merged, full stop.)

A task is ready if:
  - its current status is `pending` (or absent), AND
  - every id in its `depends_on` has status `merged`.

The lead maintains .swarm/state.json:
  - on spawn:     state["<id>"] = "spawned"
  - on PR merge:  state["<id>"] = "merged"
  - on escalate:  state["<id>"] = "escalated"
  - on cancel:    state["<id>"] = "cancelled"
"""
import json
import sys
from pathlib import Path


def die(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: wave.py <swarm.json>", file=sys.stderr)
        sys.exit(1)

    sp = Path(sys.argv[1])
    if not sp.exists():
        die(f"file not found: {sp}")
    data = json.loads(sp.read_text())
    tasks = data.get("tasks") or []

    state_path = Path(".swarm") / "state.json"
    state = {}
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text())
        except json.JSONDecodeError as e:
            die(f"malformed {state_path}: {e}")
        if not isinstance(state, dict):
            die(f"{state_path} must be a JSON object")

    def status(tid: str) -> str:
        return state.get(tid, "pending")

    for t in tasks:
        tid = t["id"]
        if status(tid) != "pending":
            continue
        deps = t.get("depends_on") or []
        if all(status(d) == "merged" for d in deps):
            print(tid)


if __name__ == "__main__":
    main()
