---
name: ship-task
description: Orchestrate a single engineering task through a sequential planner → implementer → reviewer pipeline using Claude Code Agent Teams. The lead routes clarifying questions and plan approval through the user; the implementer ships the PR; the reviewer sends findings directly to the implementer (no GitHub review round-trip) until sign-off. TRIGGER on phrases like "ship this task", "ship this ticket", "run the planner/implementer/reviewer pipeline", "plan + implement + review this", or any time the user wants ONE refined task taken end-to-end with separate plan, implement, and review phases. Requires Claude Code ≥2.1.32 with Agent Teams enabled (CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1) and the `gh` CLI authed. Do NOT use for batches of tasks (use `swarm` instead), single-step work that doesn't need a plan, or exploratory research.
argument-hint: issue id (e.g. "ENG-1234"), a plan/spec file path, or a description
---

# Ship Task

Orchestrate a single refined engineering task through three sequential
teammates: a `planner` writes and gets approval for the plan, an
`implementer` builds it and opens the PR, and a `reviewer` reviews the diff
and sends findings directly to the implementer until sign-off. The lead
(this skill) is the bridge between the team and the user — it forwards
clarifying questions, plan-approval requests, and escalations to the user
and relays answers back.

The whole point of the team is that **the reviewer talks to the implementer
directly via in-team messages**, not via GitHub PR comments. The PR is the
ship vehicle and the human's final approval surface; everything in between
happens in the message log.

## When to use

- ONE refined task that benefits from a separate plan + approval before
  implementation (anything non-trivial, anything touching unfamiliar code,
  anything where the spec has open questions).
- Agent Teams is enabled (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`) and
  Claude Code is ≥ 2.1.32.
- `gh` CLI is installed and authed against the target repo.
- You want a real draft PR opened, CI watched, and review findings
  addressed before handing back to the human for merge.

## When NOT to use

- A batch of tasks — use `swarm` instead (parallel PRs).
- A trivial one-step change — just edit it in this session.
- Exploratory research or open-ended design — use subagents or a planning
  session.
- An unrefined or ambiguous task — refine it first. The planner can ask
  clarifying questions, but it shouldn't be guessing the goal.

## The flow

`INGEST → SETUP → SPAWN PLANNER → APPROVE PLAN → SPAWN IMPLEMENTER →
SPAWN REVIEWER → LOOP → DONE`

### Critical: teammates, not plain subagents

Every agent spawned by this skill MUST be a **teammate**, not a plain
subagent. Teammates are addressable, persist across turns, and can
`SendMessage` each other directly — which is what makes the
reviewer↔implementer loop in step 7 possible without the lead acting as a
go-between.

When calling the `Agent` tool, you MUST pass BOTH `team_name` AND `name`
(in addition to `subagent_type` and `prompt`). Omitting either parameter
silently downgrades the spawn to a plain subagent — the agent runs inline,
returns one result, cannot be messaged, and the entire review loop
collapses. There is no warning when this happens; the only symptom is that
the UI does not open a new terminal split / status-bar entry.

| Param | Required | Value |
|---|---|---|
| `team_name` | yes | the task `id` (e.g. `pe-1234`) — same for all three spawns |
| `name` | yes | unique per role (`<id>-planner`, `<id>`, `<id>-reviewer`) |
| `subagent_type` | yes | `planner`, `implementer`, or `reviewer` |
| `prompt` | yes | Template P / I / R below, with placeholders filled |
| `model` | optional | only if the user pins a specific model |

If the user reports "I didn't see a new split open" or "the status bar
looks normal", the spawn was downgraded. Stop, tear down, and re-spawn
correctly with both `team_name` and `name`.

### 1. Ingest

Determine the input from `$ARGUMENTS`.

- **Linear issue id** (`XX-1234`) — fetch the issue via the Linear MCP.
  Read the description, comments, parent project description, and any
  linked documents. Use the issue id as the task `id` (lowercased, e.g.
  `pe-1234`). Use the issue title as the task `title`.
- **File path** — read it. If it's a plan (has steps, files, tests),
  treat it as a plan and skip the planner phase. If it's a spec
  (description + acceptance criteria), treat it as a spec.
- **Plain description** — use it as the spec. Synthesize a short `id`
  from the user's wording (e.g. `add-csv-export`).
- **No argument** — ask the user what to ship. Do NOT guess.

Show the user the task summary (id, title, spec excerpt, source) and the
proposed plan-vs-spec routing. Get explicit confirmation before
proceeding.

### 2. Setup

Decide where the work happens:

- **Default: work in the current branch.** If we're on `main`/`master`,
  create a feature branch first. Branch name follows the project's
  convention (Linear's suggested branch name if the input was an issue
  id; otherwise `<user>/<short-id>`).
- **Optional: worktree.** If the user prefers isolation (or the current
  branch has uncommitted work that conflicts), spawn teammates with
  `isolation: "worktree"` so Claude Code creates the worktree in its
  default managed location. Do NOT invent a custom skill-specific path
  (no `.ship-task/worktrees/...` or similar). Let the harness own the
  worktree path; capture and reuse whatever path it returns. The branch
  for the worktree should be cut from `origin/<trunk>`.

Record the chosen working directory — every teammate gets spawned with
it as their cwd.

### 3. Create the team and spawn the planner

Create an agent team for this task with `TeamCreate`. The team name is the
task `id` (e.g. `pe-1234`) — reuse it for every subsequent spawn so all
three teammates share the same team context.

Spawn the `planner` teammate via the `Agent` tool. **All five parameters
below are required** — omitting `team_name` or `name` downgrades the
spawn to a plain subagent and breaks the review loop (see the "Critical"
note above).

- **`team_name`:** the task `id` (e.g. `pe-1234`).
- **`name`:** the task `id` plus `-planner` (e.g. `pe-1234-planner`).
- **`subagent_type`:** `planner` (defined at `agents/planner.md`).
- **`prompt`:** Template P (below). Paste the spec **verbatim** in the
  prompt — do NOT deliver the spec via a post-spawn message.
- Working directory: the chosen working directory from step 2 (passed in
  the prompt body so the teammate `cd`s there before working).
- Model: inherits from the lead's settings unless the user pins one.

Wait for one of:

- `QUESTION <id>: ...` → ask the user (use AskUserQuestion when there are
  discrete options; plain text otherwise), then reply to the planner with
  the answers. May repeat.
- `PLAN <id>: ...` → proceed to step 4.
- `BLOCKED <id>: ...` or `ESCALATE <id>: ...` → surface to the user.
  The user decides whether to revise the spec, cancel, or override.

### 4. Get the plan approved by the user

Read the plan file the planner produced. Forward it to the user —
preferably as a brief summary plus the file path so the user can open it.
Ask explicitly:

> Approve the plan, request revisions (with feedback), or cancel?

Use `AskUserQuestion` for the choice. On the user's reply:

- **Approve** → reply to the planner: `APPROVED <id>: proceed`. The
  planner commits the plan, opens a draft PR, and sends
  `DONE-PLAN <id>: ...`. Continue to step 5.
- **Revise** → reply to the planner: `REVISE <id>: <user's feedback>`.
  Wait for the next `PLAN <id>: revised ...` and re-loop step 4.
- **Cancel** → reply to the planner: `CANCEL <id>: <reason>`. Tear the
  team down (or leave it for the user to clean up) and report to the
  user. Done — no implementation.

### 5. Spawn the implementer

After `DONE-PLAN <id>: Plan committed at <path>. Draft PR #<n> opened`:

Spawn via the `Agent` tool. **`team_name` AND `name` are both required** —
see the "Critical" note above.

- **`team_name`:** the task `id` (same value used in step 3).
- **`name`:** the task `id` (e.g. `pe-1234`) — the bare id, no suffix, so
  the reviewer can `message <id>` directly per Template R.
- **`subagent_type`:** `implementer` (defined at `agents/implementer.md`).
- **`prompt`:** Template I (below). Include the `approved_plan_path` so
  the implementer skips its internal planning step. Paste the spec
  verbatim.
- Working directory: same as the planner's.
- Model: inherits from the lead's settings unless the user pins one.

The implementer runs `/implement-plan` (which detects the existing draft
PR opened by the planner) and signals `READY <id>: PR #<n>` when the PR
is marked ready for review.

If the implementer messages `BLOCKED <id>: ...` (spec ambiguity discovered
mid-implement, out-of-scope review request) or `ESCALATE <id>: ...`,
surface it to the user.

### 6. Spawn the reviewer on `READY`

When the implementer sends `READY <id>: PR #<n> ready for review`:

Spawn via the `Agent` tool. **`team_name` AND `name` are both required**
— without them the reviewer cannot `SendMessage` the implementer and the
whole review loop collapses into the lead intermediating.

- **`team_name`:** the task `id` (same value used in steps 3 and 5).
- **`name`:** the task `id` plus `-reviewer` (e.g. `pe-1234-reviewer`).
- **`subagent_type`:** `reviewer` (defined at `agents/reviewer.md`).
- **`prompt`:** Template R (below). Include the implementer teammate's
  name so the reviewer can `message <implementer-name>` directly with
  findings. Include the approved plan path and the spec.
- Working directory: the implementer's working directory (so the reviewer
  can Read/Grep files alongside `gh pr diff`). If you're not using a
  worktree, the repo root is fine.
- Model: inherits from the lead's settings.

### 7. The review loop

The reviewer and implementer now talk **directly**:

- `reviewer` sends `REVIEW <id> round 1: ...` to `<implementer-name>`
  with severity-grouped findings.
- `implementer` pauses `/watch-pr`, addresses critical + warning items,
  commits/pushes, replies `ADDRESSED <id> round 1: <new-sha>`.
- `reviewer` verifies (round 2 if anything remains). Capped at 2 rounds.
- If clean: `reviewer` sends `LGTM <id>: ...` to the implementer and
  `DONE <id>-reviewer: ...` to the lead.
- If unresolved after round 2: `reviewer` sends
  `ESCALATE <id>-reviewer: ...` to the lead. The lead surfaces it to the
  user; the user decides.

The lead does NOT intermediate the review traffic — it lives in the
message log between the two teammates. The lead only intervenes on
ESCALATE and on lead-prefixed messages.

Meanwhile, the implementer's `/watch-pr` loop continues monitoring CI.
CI failures are handled per `/watch-pr` (auto-fix up to 3 attempts on the
same check, then escalate).

### 8. Done

When BOTH of these arrive:

- `DONE <id>-reviewer: Sign-off sent to <implementer-name>. PR #<n>
  ready for human approval.`
- `DONE <id>: PR #<n>. CI green, reviewer signed off. Ready for human
  approval and merge.`

…report to the user:

- The PR number and URL.
- The plan file path.
- A one-line review verdict from the reviewer's DONE message.
- A reminder that **the lead does not merge** — the human merges.

The lead does NOT auto-clean the team. The user decides when with
`clean up the team`.

## Spawn-prompt templates

### Template P — planner

```
You are the planner teammate for task `<id>`.

Working directory: <cwd>  (branch: <branch-name>)
Target branch: <trunk>
Task id: <id>
Title: <title>
Linear issue: <id-or-null>

Your task spec:
-----
<full spec verbatim>
-----

Follow the flow defined in the `planner` subagent: gather context, surface
any clarifying questions to the lead bundled into one QUESTION message,
write the plan to `docs/implementation-plans/<YYYY-MM-DD>-<short>.md`,
and submit it as `PLAN <id>: <one-line>. Full plan at <path>. Awaiting
approval.`

On the lead's reply:
  APPROVED <id>: proceed → commit the plan, push, open a draft PR, then
    message `DONE-PLAN <id>: ...` and go idle.
  REVISE <id>: <feedback> → revise and resubmit as `PLAN <id>: revised. ...`.
  CANCEL <id>: <reason> → message `BLOCKED <id>: plan cancelled` and idle.

You do NOT implement code. A separate implementer teammate takes over after
your plan is approved.
```

### Template I — implementer

```
You are the implementer teammate for task `<id>`.

Working directory: <cwd>  (branch: <branch-name>)
Target branch: <trunk>
Task id: <id>
Title: <title>
requires_plan: true
approved_plan_path: <path returned by the planner>

Your task spec (for cross-reference; the contract is the approved plan):
-----
<full spec verbatim>
-----

A separate planner teammate has already produced the approved plan at the
path above and opened a draft PR. Read the plan, then run `/implement-plan`
with it. `/implement-plan` will detect the existing draft PR, implement in
logical units with quality gates, fill out the PR description, mark it
ready, and hand off to `/watch-pr`.

Signal `READY <id>: PR #<n> ready for review. Head SHA: <sha>.` once the
PR is marked ready. A `reviewer` teammate named `<id>-reviewer` will message
you DIRECTLY with `REVIEW <id> round <n>: ...` findings — address them per
section 5 of the implementer subagent and reply `ADDRESSED <id> round <n>:
<new-sha>` to the reviewer. Repeat until you receive `LGTM <id>: ...`.

When CI is green AND the reviewer has signed off, message:
    DONE <id>: PR #<n>. CI green, reviewer signed off. Ready for human
    approval and merge.

Reminder: do NOT run `gh pr merge`. The human merges.
```

### Template R — reviewer

```
You are the reviewer teammate for task `<id>`. You do one thorough review
of PR #<n>, send findings DIRECTLY to the implementer teammate via in-team
messages (NOT GitHub review comments), verify their fixes in a round-2 pass,
and sign off. You NEVER approve on GitHub. You NEVER post --request-changes.
The human is the final approver.

PR: #<n>
Branch: <branch-name>
Target branch: <trunk>
Task id: <id>
Implementer teammate name: <id>   (use `message <id>` to talk to them)

Approved plan: <path>

Original task spec (for context):
-----
<full spec verbatim>
-----

Follow the flow defined in the `reviewer` subagent:
  1. Load PR diff + plan + CLAUDE.md.
  2. Run /review-code methodology against the spec+plan contract.
  3. Send ONE structured `REVIEW <id> round 1: ...` message to <id> with
     severity-grouped findings and a one-line verdict.
  4. Wait for `ADDRESSED <id> round 1: <new-sha>`, verify the new commits,
     send round 2 if needed (capped at 2 rounds total).
  5. On clean: `LGTM <id>: ...` to the implementer, then
     `DONE <id>-reviewer: ...` to the lead. Go idle.
  6. On unresolved-after-2-rounds or unrecoverable issue:
     `ESCALATE <id>-reviewer: ...` to the lead. Go idle.

Do NOT post findings to GitHub. The whole point of this team is that you
can talk to the implementer directly.
```

## Hooks (pre-wired)

The plugin's existing hooks apply here too:

- `TaskCompleted` → `skills/swarm/hooks/verify_terminal.sh`. Refuses to
  mark a teammate's task completed unless its PR is actually `MERGED`.
- `TeammateIdle` → `skills/swarm/hooks/nudge_if_pending.sh`. Keeps the
  implementer working if CI is still running or the reviewer is mid-loop.

No user-side `settings.json` wiring is required.

## Files in this skill

```
<plugin root>/
├── agents/
│   ├── planner.md       planner subagent (auto-loaded)
│   ├── implementer.md   implementer subagent (auto-loaded)
│   └── reviewer.md      reviewer subagent (auto-loaded)
└── skills/ship-task/
    └── SKILL.md         (this file)
```

The orchestrator deliberately stays in a single file — it's much smaller
than `swarm` (no DAG, no waves, no scope-overlap analysis).

## Common failure modes

- **Silent subagent downgrade:** the lead spawns via `Agent` without
  `team_name` and `name`, so the planner/implementer/reviewer come up as
  plain subagents instead of teammates. Symptom: no new terminal split,
  no status-bar entry, and the reviewer can't `SendMessage` the
  implementer (the review loop in step 7 collapses). Fix: re-spawn with
  both parameters set per steps 3 / 5 / 6.
- **False "READY":** implementer says READY before CI has even started.
  The reviewer spawns anyway and reviews the diff; CI failures are handled
  in parallel by `/watch-pr`.
- **Reviewer + implementer ping-pong forever:** the 2-round cap on the
  reviewer side prevents this. After round 2, escalate.
- **Plan approved but spec turns out wrong:** the implementer surfaces
  `BLOCKED <id>: ...` mid-implement. The lead asks the user; the user can
  send guidance, or cancel and re-plan.
- **Forgotten worktree leftover:** if the user picks the worktree mode,
  Claude Code manages the worktree path. If the agent exits without
  changes the harness cleans it up; otherwise the worktree path is
  returned in the agent result. Tell the user the returned path so they
  can `git worktree remove <path>` when they're done.

## Assumptions baked in

- `gh` CLI is installed and authenticated against the target repo.
- CI is GitHub Actions (or another provider visible via `gh pr checks`).
- Trunk defaults to `main`; the user can override at ingest time.
- One PR per task. No stacked PRs in v1.
- Teammates inherit the lead's model from user settings. The user can pin
  a stronger model (e.g. `claude-opus-4-7[1m]`) per teammate if they ask.
- The lead never merges. The human merges.
- The reviewer NEVER posts findings as native GitHub review comments. If
  the user explicitly wants an audit-trail PR comment, the reviewer can
  post ONE short summary AFTER sign-off — but not the full findings list.
