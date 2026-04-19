---
name: swarm
description: Run a batch of refined engineering tasks as parallel PRs using Claude Code Agent Teams. Each teammate owns one task end-to-end — opens a real PR, watches CI, addresses review comments, and loops until merged or escalates when stuck. TRIGGER on phrases like "run the swarm", "burn down the backlog", "ship these Linear tickets", "work through this list/batch", "parallelize these tasks", or any time the user hands over ≥2 already-specced tickets/issues/tasks to ship in parallel. Requires Claude Code ≥2.1.32 with Agent Teams enabled (CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1) and the `gh` CLI authed. Do NOT use for single-task work, exploratory research, unrefined/ambiguous tasks, or tasks that all touch the same files — those belong in a single session.
argument-hint: issue ids (e.g. "ENG-1234 ENG-1235") or a scope description (e.g. "all tasks on backlog", "everything in triage", "ready-to-ship issues in project X")
---

# Swarm

Orchestrate a list of refined engineering tasks as parallel PRs. Each teammate
loops on one task until CI is green and review comments are addressed. Stuck
teammates escalate to the human; the rest keep going.

## When to use

- ≥2 independent tasks that already have refined specs and acceptance criteria.
- Agent Teams is enabled (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`) and Claude
  Code is ≥2.1.32.
- `gh` CLI is installed and authed against the target repo.
- You want real PRs opened, CI watched, and review comments addressed — not a
  simulation.

## When NOT to use

- A single task — use a normal session.
- Exploratory research or open-ended design — use subagents or a review team.
- Unrefined tasks missing acceptance criteria — plan them first.
- Tasks that all touch the same files — rebase thrash dominates. Ship one PR.

## The flow

`INGEST → PLAN → SETUP → SPAWN → LOOP → ESCALATE → REPORT`

### 1. Ingest

Determine the input from `$ARGUMENTS` and assemble `swarm.json` at the repo
root.

- **A list of issue IDs** (one or more Linear issue identifiers, like
  `ENG-1234` or `ENG-1234, ENG-1235 ENG-1236`) — fetch each issue via the
  Linear MCP. For each issue, read the description, comments, parent project
  description, and any linked documents. Build one task per issue.
- **A scope description** (e.g. `"all tasks on backlog"`,
  `"everything in triage"`, `"ready-to-ship issues in project X"`) — query
  the Linear MCP for the matching issue set first, then fetch each matching
  issue exactly as above.
- **No argument** — ask the user which tickets to swarm before continuing.
  Do NOT guess.

For each task, assemble:

- `id` — the Linear issue id, lowercased (e.g. `eng-1234`). Becomes the
  teammate name and the branch suffix.
- `title` — the Linear issue title.
- `spec` — the full refined description plus any acceptance criteria.
  Include relevant comment context where it changes the spec.
- `depends_on` — default `[]`. **Do NOT infer dependencies.** If a Linear
  issue mentions a blocking or sub-issue relationship, surface it to the
  user and add an explicit edge only on confirmation.
- Optional `scope_files`, `requires_plan`, `model` — set only when the user
  asks or the issue is unambiguous about them.

Write `swarm.json` to the repo root and show the user the full file.
**Require explicit user confirmation of the ingested set** before moving to
Step 2.

See `references/schema.md` for the full schema and a worked example.
Top-level: `trunk` (default `"main"`), `tasks` (array).

Dependencies are **explicit only**. Never infer them. `depends_on: []` is the
declaration for an independent task.

### 2. Plan

```bash
python skills/swarm/scripts/plan.py swarm.json
```

Prints the DAG as waves (tasks that can run in parallel), flags scope-overlap
between tasks with no declared dependency, and refuses to continue on cycles,
missing deps, or malformed input. **Require explicit user approval of the plan
before spawning anything.** Present the waves and any warnings; let the user
add `depends_on` edges or drop tasks before proceeding.

### 3. Setup worktrees

```bash
python skills/swarm/scripts/setup_worktrees.py swarm.json
```

Creates `.swarm/worktrees/<task-id>/` on branch `swarm/<task-id>` cut from
`origin/<trunk>`. Idempotent — skips existing worktrees. Adds `.swarm/` to
`.gitignore`.

### 4. Spawn the team

Create the agent team. Spawn teammates in topological waves. For each task in
the current wave:

- **Name:** the task `id` (so `message <id>` works predictably).
- **Subagent type:** `implementer` — shipped with this plugin at
  `agents/implementer.md`, auto-loaded when the plugin is enabled.
- **Working directory:** the task's worktree at `.swarm/worktrees/<id>/`.
- **Model:** `sonnet` unless the task sets `"model": "opus"`.
- **Spawn prompt:** the task spec plus dependency context. Templates in
  `references/spawn_prompts.md`.

After spawning, write `"<id>": "spawned"` to `.swarm/state.json`. Do **not**
spawn tasks from wave N+1 until the lead is satisfied wave N is healthy; new
waves spawn on merge of their deps (see Escalate / Report).

For `requires_plan: true` tasks, the spawn prompt uses Template C (plan mode
first). Review the plan when the teammate submits it; approve or reject with
feedback.

### 5. The loop

The teammate runs the 7-step loop defined in the plugin's `agents/implementer.md`.
Summary:

1. Read the spec. If ambiguous, message the lead and go idle. Don't guess.
2. Implement. Run relevant local tests (not the whole suite).
3. Push and `gh pr create` against trunk with title `"<id>: <title>"`.
4. Watch CI via `gh pr checks <n> --watch`. On failure, read logs, fix, push.
   **Stop condition:** 3 consecutive failures on the same test name.
5. Wait for review. Poll `gh pr view <n> --json reviews,reviewDecision,comments`
   every 60s. After 30 min of no activity, send a non-urgent FYI to the lead.
6. Address review comments. In-scope → fix; out-of-scope → reply + message
   lead `BLOCKED`. **Stop condition:** 2 rounds on the same unresolved comment.
7. Done when CI green AND approved AND no unresolved threads. Message
   `DONE <id>: PR #<n> ready to merge`, go idle. **Do NOT run `gh pr merge`.**

**The skill uses `gh` CLI, not the GitHub MCP,** for the polling loop — tight
polling works better on `gh`.

### 6. Escalation

When a teammate hits a stop condition:

- Messages the lead: `ESCALATE <id>: <diagnostic>. PR: #<n>.`
- Sets its task status to `blocked` (writes `"<id>": "escalated"` to state).
- Goes idle.

The lead **logs the diagnostic to the human** and does NOT attempt to fix.
Other teammates keep running. The human either messages the teammate directly
with guidance (teammate resumes its loop) or tells the lead to cancel it.

### 7. Report

When the wave drains (all tasks either `merged`, `escalated`, or `cancelled`),
the lead reports:

- Merged count + PR numbers.
- Escalated count + per-task diagnostics.
- Cancelled count.
- What's still pending waves-wise (tasks awaiting upstream merges).

The lead does **not** merge PRs — the human does. After each merge, the lead
runs `scripts/wave.py swarm.json` to find newly-unblocked tasks, rebases their
worktrees onto the new trunk, and spawns them.

The lead does **not** clean up the team. The human decides when with
`clean up the team`.

## Hooks (pre-wired)

Two hooks ship with the plugin and activate automatically when it's enabled
(`hooks/hooks.json` at the plugin root):

- `TaskCompleted` → `skills/swarm/hooks/verify_terminal.sh`. Refuses to mark
  a swarm task completed unless its PR is actually `MERGED`.
- `TeammateIdle` → `skills/swarm/hooks/nudge_if_pending.sh`. Keeps a teammate
  working if CI is still running or reviewer changes are pending.

Both read the hook JSON payload on stdin, extract `task_id`/`teammate_name`,
and exit 2 with a nudge on stderr when the teammate tries to stop early. No
user-side `settings.json` wiring is required.

## Files in this plugin (swarm-related)

```
<plugin root>/
├── agents/
│   └── implementer.md          teammate subagent definition (auto-loaded)
├── hooks/
│   └── hooks.json              wires TaskCompleted + TeammateIdle
└── skills/swarm/
    ├── SKILL.md                (this file)
    ├── references/
    │   ├── schema.md           full swarm.json schema + example
    │   ├── spawn_prompts.md    three spawn templates + dep context recipe
    │   └── examples.md         four worked examples + one anti-example
    ├── scripts/
    │   ├── plan.py             validate + compute waves + scope warnings
    │   ├── setup_worktrees.py  create one worktree per task, idempotent
    │   └── wave.py             print currently-ready task ids
    └── hooks/
        ├── verify_terminal.sh  TaskCompleted guard: PR must be merged
        └── nudge_if_pending.sh TeammateIdle nudge: CI/review pending
```

## Common failure modes

- **False "done":** teammate says the PR is ready before CI/review actually
  settles. `verify_terminal.sh` catches this.
- **Mid-flight scope conflict:** two teammates both edit a file neither
  declared in `scope_files`. Rebase thrash. Mitigate with scope warnings at
  plan time; if it happens, the later PR to CI-fail rebases and retries once,
  then escalates.
- **Flaky CI:** three failures on the same test name escalate even if the
  test is flaky. Human triage decides whether to rerun, quarantine, or fix.
- **Out-of-scope review requests:** teammate replies on the PR explaining the
  boundary and messages the lead `BLOCKED`. Don't silently expand scope.
- **Linear sync:** not handled. If tickets came from Linear, update them
  yourself post-merge.

## Assumptions baked in

- `gh` CLI is installed and authenticated.
- CI is GitHub Actions (or another provider visible via `gh pr checks`).
- Trunk defaults to `main`; override per swarm in `swarm.json`.
- One PR per task. No stacked PRs in v1.
- Sonnet by default; Opus opt-in per task via `"model": "opus"`.
- The lead never merges. The human merges.
