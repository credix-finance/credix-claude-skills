#!/usr/bin/env python3
"""Validate a swarm.json file, compute parallel waves, and warn on scope overlap.

Usage:
    python plan.py <swarm.json>

Exit codes:
    0 - valid plan (warnings may be printed but are non-fatal)
    1 - fatal error (cycle, missing deps, malformed input, unknown model, etc.)
"""
import fnmatch
import json
import sys
from pathlib import Path


REQUIRED_FIELDS = ("id", "title", "spec", "depends_on")


def die(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def load(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        die(f"file not found: {path}")
    try:
        data = json.loads(p.read_text())
    except json.JSONDecodeError as e:
        die(f"invalid JSON in {path}: {e}")
    if not isinstance(data, dict):
        die("top-level must be a JSON object with a `tasks` array")
    if "tasks" not in data:
        die("top-level missing required `tasks` array")
    if not isinstance(data["tasks"], list):
        die("`tasks` must be an array")
    return data


def validate_tasks(tasks: list) -> None:
    ids = []
    for i, t in enumerate(tasks):
        if not isinstance(t, dict):
            die(f"task at index {i} is not an object")
        for f in REQUIRED_FIELDS:
            if f not in t:
                die(f"task at index {i} missing required field `{f}`")
        if not isinstance(t["id"], str) or not t["id"]:
            die(f"task at index {i} has invalid `id`")
        if not isinstance(t["title"], str) or not t["title"]:
            die(f"task `{t['id']}` has invalid `title`")
        if not isinstance(t["spec"], str) or not t["spec"]:
            die(f"task `{t['id']}` has invalid `spec`")
        if not isinstance(t["depends_on"], list):
            die(f"task `{t['id']}` `depends_on` must be an array")
        for dep in t["depends_on"]:
            if not isinstance(dep, str):
                die(f"task `{t['id']}` has non-string entry in `depends_on`")
        if "scope_files" in t and not isinstance(t["scope_files"], list):
            die(f"task `{t['id']}` `scope_files` must be an array of strings")
        if "requires_plan" in t and not isinstance(t["requires_plan"], bool):
            die(f"task `{t['id']}` `requires_plan` must be a boolean")
        if "model" in t and (not isinstance(t["model"], str) or not t["model"]):
            die(f"task `{t['id']}` has invalid `model` (must be a non-empty string)")
        ids.append(t["id"])

    seen = set()
    for tid in ids:
        if tid in seen:
            die(f"duplicate task id: `{tid}`")
        seen.add(tid)

    id_set = set(ids)
    for t in tasks:
        for dep in t["depends_on"]:
            if dep not in id_set:
                die(f"task `{t['id']}` depends on unknown id `{dep}`")
            if dep == t["id"]:
                die(f"task `{t['id']}` depends on itself")


def detect_cycle(tasks: list):
    """Three-color DFS. Returns a cycle path (list of ids) if found, else None."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {t["id"]: WHITE for t in tasks}
    deps = {t["id"]: list(t["depends_on"]) for t in tasks}
    parent = {}

    def dfs(u: str):
        color[u] = GRAY
        for v in deps[u]:
            if color[v] == GRAY:
                # Reconstruct cycle: v ... u v
                cycle = [v]
                cur = u
                while cur != v and cur in parent:
                    cycle.append(cur)
                    cur = parent[cur]
                cycle.append(v if cur == v else cur)
                cycle.reverse()
                return cycle
            if color[v] == WHITE:
                parent[v] = u
                found = dfs(v)
                if found:
                    return found
        color[u] = BLACK
        return None

    for tid in list(color.keys()):
        if color[tid] == WHITE:
            c = dfs(tid)
            if c:
                return c
    return None


def compute_waves(tasks: list) -> list:
    """Kahn's algorithm. Returns a list of waves; each wave is a list of task ids
    that can run in parallel after all previous waves complete."""
    deps = {t["id"]: set(t["depends_on"]) for t in tasks}
    remaining = dict(deps)
    waves = []
    while remaining:
        ready = sorted([tid for tid, d in remaining.items() if not d])
        if not ready:
            # Should have been caught by detect_cycle already.
            die("internal: no ready tasks but graph is non-empty (cycle?)")
        waves.append(ready)
        for tid in ready:
            del remaining[tid]
        for d in remaining.values():
            d.difference_update(ready)
    return waves


def _non_wildcard_prefix(glob: str) -> str:
    """Return the portion of a glob before the first wildcard char."""
    idx = len(glob)
    for i, ch in enumerate(glob):
        if ch in "*?[":
            idx = i
            break
    return glob[:idx]


def globs_overlap(a: str, b: str) -> bool:
    """Heuristic: could two globs match a common file path?"""
    if a == b:
        return True
    if fnmatch.fnmatch(a, b) or fnmatch.fnmatch(b, a):
        return True
    pa, pb = _non_wildcard_prefix(a), _non_wildcard_prefix(b)
    if pa and pb and (pa.startswith(pb) or pb.startswith(pa)):
        return True
    # Flat-file names with same basename pattern (e.g. "**/foo.py" vs "src/foo.py")
    if "/" not in a and "/" not in b and fnmatch.fnmatch(a, b):
        return True
    return False


def scope_overlap_warnings(tasks: list) -> list:
    """For each pair of tasks with no declared dependency edge between them,
    warn if their scope_files globs could match a common path."""
    by_id = {t["id"]: t for t in tasks}

    # Reachability via depends_on (transitive).
    reach = {tid: set() for tid in by_id}

    def collect(u, seen):
        for d in by_id[u]["depends_on"]:
            if d in seen:
                continue
            seen.add(d)
            collect(d, seen)

    for tid in by_id:
        collect(tid, reach[tid])

    def connected(a: str, b: str) -> bool:
        return b in reach[a] or a in reach[b]

    warnings = []
    ids = sorted(by_id.keys())
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a, b = ids[i], ids[j]
            if connected(a, b):
                continue
            ga = by_id[a].get("scope_files") or []
            gb = by_id[b].get("scope_files") or []
            hits = []
            for ga_glob in ga:
                for gb_glob in gb:
                    if globs_overlap(ga_glob, gb_glob):
                        hits.append((ga_glob, gb_glob))
            if hits:
                examples = ", ".join(f"`{x}` vs `{y}`" for x, y in hits[:2])
                warnings.append(
                    f"scope overlap: `{a}` and `{b}` have no declared dependency "
                    f"but share scope ({examples}). Rebase thrash likely."
                )
    return warnings


def print_plan(tasks: list, waves: list) -> None:
    by_id = {t["id"]: t for t in tasks}
    print("Plan:")
    for i, wave in enumerate(waves):
        parallel = " (parallel)" if len(wave) > 1 else ""
        print(f"  Wave {i} — {len(wave)} task{'s' if len(wave) != 1 else ''}{parallel}:")
        for tid in wave:
            t = by_id[tid]
            model = t.get("model")
            model_str = f"model={model}  " if model else ""
            badge = " [plan-required]" if t.get("requires_plan") else ""
            deps = t["depends_on"]
            deps_str = "[]" if not deps else "[" + ", ".join(deps) + "]"
            print(f"    - {tid:<30} {model_str}deps={deps_str}{badge}")


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: plan.py <swarm.json>", file=sys.stderr)
        sys.exit(1)

    data = load(sys.argv[1])
    tasks = data["tasks"]
    if not tasks:
        die("`tasks` is empty — nothing to plan")

    validate_tasks(tasks)

    cycle = detect_cycle(tasks)
    if cycle:
        die(f"cycle detected in depends_on: {' -> '.join(cycle)}")

    waves = compute_waves(tasks)
    print_plan(tasks, waves)

    warnings = scope_overlap_warnings(tasks)
    if warnings:
        print("\nWarnings:")
        for w in warnings:
            print(f"  - {w}")

    n_parallel = max((len(w) for w in waves), default=0)
    print(
        f"\nSummary: {len(tasks)} tasks across {len(waves)} wave(s); "
        f"max parallelism {n_parallel}; {len(warnings)} warning(s)."
    )


if __name__ == "__main__":
    main()
