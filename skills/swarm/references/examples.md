# Worked examples

Four examples of the swarm in action, plus one anti-example showing when NOT
to use it.

---

## Example 1 — Three independent tasks

`swarm.json`:

```json
{
  "trunk": "main",
  "tasks": [
    {"id": "add-health-endpoint", "title": "Add GET /health",
     "spec": "…", "depends_on": [],
     "scope_files": ["src/api/health.py", "tests/api/test_health.py"]},
    {"id": "bump-python", "title": "Bump Python to 3.12 in CI",
     "spec": "…", "depends_on": [],
     "scope_files": [".github/workflows/ci.yml", "pyproject.toml"]},
    {"id": "fix-typo-readme", "title": "Fix typos in README",
     "spec": "…", "depends_on": [],
     "scope_files": ["README.md"]}
  ]
}
```

Plan output:

```
Wave 0 (3 tasks, parallel):
  - add-health-endpoint   (sonnet)     deps: []
  - bump-python           (sonnet)     deps: []
  - fix-typo-readme       (sonnet)     deps: []

No scope overlap warnings.
```

All three spawn simultaneously with Template A. Three PRs open in parallel.
The human reviews and merges each as they go green. The lead reports
`3/3 merged` and waits for cleanup instructions.

---

## Example 2 — Chained dependency

A must merge before B: B builds on A's schema change.

```json
{
  "trunk": "main",
  "tasks": [
    {"id": "add-orders-table", "title": "Add orders table",
     "spec": "…", "depends_on": [],
     "scope_files": ["migrations/**", "src/models/order.py"]},
    {"id": "add-orders-api", "title": "Add /orders list endpoint",
     "spec": "…", "depends_on": ["add-orders-table"],
     "scope_files": ["src/api/orders.py", "tests/api/test_orders.py"]}
  ]
}
```

Plan output:

```
Wave 0: add-orders-table  (sonnet)    deps: []
Wave 1: add-orders-api    (sonnet)    deps: [add-orders-table]
```

Flow:

1. Lead spawns `add-orders-table` with Template A.
2. Teammate loops, PR #501 opens, CI green, human reviews and merges.
3. Lead records: `add-orders-table → PR #501, merge SHA abc1234`.
4. Lead runs `scripts/wave.py swarm.json` → prints `add-orders-api`.
5. Lead rebases `add-orders-api` worktree:

   ```bash
   cd .swarm/worktrees/add-orders-api/
   git fetch origin main
   git rebase origin/main
   ```

6. Lead spawns `add-orders-api` with Template B, passing
   `add-orders-table: PR #501, merge SHA abc1234` as dependency context.
7. PR #502 opens, loops to green+approved, human merges.

---

## Example 3 — Scope conflict without declared dependency

Two tasks touch the same file but have `depends_on: []` on both sides.

```json
{
  "tasks": [
    {"id": "add-retry-wrapper", "title": "Add exponential-backoff retry",
     "spec": "…", "depends_on": [],
     "scope_files": ["src/http/client.py"]},
    {"id": "add-timeout-default", "title": "Default 30s timeout on HTTP client",
     "spec": "…", "depends_on": [],
     "scope_files": ["src/http/client.py"]}
  ]
}
```

Plan output:

```
Wave 0 (2 tasks, parallel):
  - add-retry-wrapper      (sonnet)    deps: []
  - add-timeout-default    (sonnet)    deps: []

WARNINGS:
  - Scope overlap between `add-retry-wrapper` and `add-timeout-default` on
    `src/http/client.py` with no declared dependency. Rebase thrash likely.
```

Present three options to the user:

1. **Add `depends_on: ["add-retry-wrapper"]` to `add-timeout-default`.** Ship
   sequentially. Safest.
2. **Add `depends_on: ["add-timeout-default"]` to `add-retry-wrapper`.** Same
   idea, other order.
3. **Accept the risk and run parallel.** Second PR to reach CI will likely
   hit conflicts; teammate rebases once and retries. If it conflicts again,
   escalate.

Wait for the user's pick before spawning.

---

## Example 4 — Escalation walkthrough

Two tasks. One simple docs fix, one non-trivial change that hits a flaky test
three times.

```json
{
  "tasks": [
    {"id": "fix-docstring", "title": "Fix typo in order_total docstring",
     "spec": "…", "depends_on": [], "scope_files": ["src/billing.py"]},
    {"id": "refactor-billing", "title": "Refactor billing to split line-items",
     "spec": "…", "depends_on": [],
     "scope_files": ["src/billing/**", "tests/billing/**"]}
  ]
}
```

Timeline:

```
t=00:00  lead spawns both (wave 0)
t=00:04  fix-docstring: PR #611 opens, CI green
t=00:12  fix-docstring: human merges, teammate messages DONE, goes idle
          lead: record merged, state.json["fix-docstring"] = "merged"

t=00:20  refactor-billing: PR #612 opens, CI fails on
          `tests/billing/test_line_items.py::test_split_round_cents`
t=00:25  refactor-billing: fix #1 pushed, same test fails
t=00:32  refactor-billing: fix #2 pushed, same test fails
t=00:40  refactor-billing: escalates
          ESCALATE refactor-billing: CI failing 3x on test_split_round_cents.
            Tried: rounding mode change, Decimal context, explicit quantize.
            Suspected: test fixture uses locale-dependent comma, running
            under en_DE locale. PR: #612.
          state.json["refactor-billing"] = "escalated"
          teammate goes idle.

t=00:41  lead → human: "refactor-billing escalated (see diagnostic above).
          Other tasks: fix-docstring merged. No more pending waves."
          Lead does NOT try to fix. Lead does NOT clean up the team.

t=01:05  human investigates, confirms locale hypothesis, messages teammate
          directly: "Force LC_NUMERIC=C in conftest.py and retry."
          Teammate resumes its loop from step 4.

t=01:08  refactor-billing: PR #612 CI green, approved, human merges.
          state.json["refactor-billing"] = "merged"

t=01:09  lead reports: 2/2 merged. Waits for cleanup instruction.
```

---

## Anti-example — three tasks on the same file

**Do not use the swarm for this.**

```json
{
  "tasks": [
    {"id": "user-add-phone", "scope_files": ["src/models/user.py"], "depends_on": []},
    {"id": "user-add-avatar", "scope_files": ["src/models/user.py"], "depends_on": []},
    {"id": "user-add-locale", "scope_files": ["src/models/user.py"], "depends_on": []}
  ]
}
```

Why swarm is wrong here:

- All three teammates will hit merge conflicts against each other.
- Whoever merges first forces the other two to rebase, rerun CI, re-request
  review. Repeat for the second merger. The third teammate rebases twice.
- Each rebase may re-trigger the full CI run and review cycle.
- Net result: 3 serialized PRs with maximum coordination overhead, ~3x the
  token cost of doing it in one session.

**Do this instead:** one session, one PR, three commits. Ship each piece as
a commit inside a single PR, or just three sequential PRs in one session
without the team overhead.
