# Spawn prompts

Three templates the lead uses when spawning teammates. Paste the spec verbatim
into the spawn prompt — never rely on post-spawn messages to deliver spec
content.

All templates share these conventions:

- The teammate's name is the task `id`.
- The teammate's working directory is `.swarm/worktrees/<id>/`.
- The teammate's subagent type is `implementer`.
- The teammate opens the PR against `<trunk>` with title `"<id>: <title>"`.
- The teammate follows the 7-step loop defined in the plugin's
  `implementer` subagent (see `agents/implementer.md` in the plugin root).

---

## Template A — no dependencies

Use for tasks with `depends_on: []`.

```
You are the implementer teammate for task `<id>`.

Working directory: .swarm/worktrees/<id>/  (already on branch swarm/<id>)
Target branch: <trunk>
PR title: "<id>: <title>"

Your task spec:
-----
<full spec verbatim from swarm.json>
-----

Follow the 7-step loop defined in the `implementer` subagent:
read spec → implement → push + open PR → watch CI → wait for review →
address comments → done.

Stop conditions:
- 3 consecutive CI failures on the same test name → ESCALATE.
- 2 rounds of the same unresolved review comment → ESCALATE.

Message the lead when you are done or escalating. Do NOT merge your own PR.
```

---

## Template B — with already-merged dependencies

Use when `depends_on` is non-empty and all deps have merged. The lead has
rebased this worktree onto the fresh trunk before spawning.

```
You are the implementer teammate for task `<id>`.

Working directory: .swarm/worktrees/<id>/  (already on branch swarm/<id>,
  rebased onto latest <trunk>)
Target branch: <trunk>
PR title: "<id>: <title>"

Your task spec:
-----
<full spec verbatim from swarm.json>
-----

Dependencies — these are ALREADY in your base branch. Do not reimplement
their changes; build on top of them.
  - <dep-id-1>: PR #<pr-number>, merged at <merge-sha>
  - <dep-id-2>: PR #<pr-number>, merged at <merge-sha>
  ...

Follow the 7-step loop defined in the `implementer` subagent.

Stop conditions:
- 3 consecutive CI failures on the same test name → ESCALATE.
- 2 rounds of the same unresolved review comment → ESCALATE.

Message the lead when you are done or escalating. Do NOT merge your own PR.
```

---

## Template C — requires plan approval

Use when `requires_plan: true`. Wraps A or B (include dependency context if
there are merged deps) and appends a plan-mode preamble.

```
<Template A or B body>

BEFORE IMPLEMENTING: start in plan mode. Produce a plan covering:
  - Files you intend to create or modify.
  - Test strategy (which tests, what they cover, happy path + edge cases).
  - Risks, unknowns, and how you'll handle them.

Submit the plan to the lead for approval. Do not write any code until the
plan is approved. If the lead requests changes, revise and resubmit. Stay in
plan mode until approval.

Once approved, exit plan mode and proceed with the 7-step loop.
```

---

## How the lead constructs dependency context

After each dep PR merges:

```bash
# record for the dep's spawn context of downstream tasks
gh pr view <dep-pr-number> --json number,mergeCommit
#   → number: integer PR number
#   → mergeCommit.oid: the merge SHA
```

Before spawning a dependent teammate, rebase its worktree:

```bash
cd .swarm/worktrees/<dependent-id>/
git fetch origin <trunk>
git rebase origin/<trunk>
```

If rebase fails with conflicts, **do not force-push or discard**. Message the
human; this usually means the dep changed files the dependent didn't declare
in `scope_files`. Let the human decide whether to adjust the spec or cancel.

Only spawn Template B after the rebase succeeds.

## Anti-patterns

- **Do not paste the spec in a post-spawn message.** The spec belongs in the
  spawn prompt. Post-spawn messages are for nudges, approvals, answers to
  specific questions — not spec delivery.
- **Do not spawn parallel teammates for tasks sharing `scope_files`.** Either
  declare a dependency (one waits for the other) or ship as a single PR.
- **Do not give teammates merge authority.** The human merges. Teammates
  signal `DONE` and go idle; they do not run `gh pr merge`.
- **Do not broadcast the full spec to the whole team.** Broadcast costs scale
  with team size; direct `message <id>` is almost always what you want.
- **Do not reuse a teammate for a second task.** One teammate, one task, one
  PR. If a task cancels, spawn a fresh teammate for any replacement.
