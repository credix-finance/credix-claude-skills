---
name: implement-plan
description: Implement a task according to its implementation plan or spec, run quality gates, commit, ship, and monitor. Use this skill whenever the user wants to implement, execute, or build out a planned task — even if they just say "implement this", "build it", "implement PE-XXXX", or "implement the plan in <file>". Accepts a full plan when one exists, or a raw spec (e.g. a Linear issue description) when there isn't one.
argument-hint: issue-id, plan file path, or spec file path
---

# Implement Plan

Implement the work described by $ARGUMENTS, following either its full
implementation plan or (if no plan exists) its spec.

## 1. Load the plan or spec

Determine the input type and load the implementation contract:

- **Linear issue ID** (matches pattern like `XX-1234`):
  1. Check `docs/implementation-plans/` for a file whose frontmatter `issue`
     field matches. If found, treat as the plan.
  2. Otherwise, read the issue description, acceptance criteria, and
     relevant comments from Linear via the Linear MCP. Treat as the spec.
- **File path** — read the file. If its shape is a full plan (steps, files,
  tests, risks), use it as the plan. If it's a spec (description +
  acceptance criteria only), use it as the spec.
- **No argument** — ask the user for an issue ID or file path.

Use a sub-agent to parse the input and return a structured summary:

- For a **plan**: implementation steps with files to create/modify, testing
  strategy, risks/prerequisites. The plan is the contract.
- For a **spec**: the acceptance criteria and any scope boundaries. The spec
  is the contract; derive your own implementation steps from it.

Note throughout whether you're operating from a plan or a spec — the
difference matters for step 4 (plan deviations only apply when there is
a plan).

## 2. Verify preconditions

- Confirm we're on the correct feature branch (listed in the plan or in the
  Linear issue's branch field). If not, check it out.
- Ensure the branch is up to date with the base branch. Check `CLAUDE.md` for
  the project's base branch convention. If not specified, use `main`.
  ```bash
  git fetch origin <base-branch>
  git rebase origin/<base-branch>
  ```
  If the rebase has conflicts, stop and ask the user.
- Check whether a PR (draft or otherwise) exists for this branch:
  ```bash
  gh pr view --json number,isDraft,state 2>/dev/null
  ```
  - **PR exists** — record the number; proceed.
  - **No PR exists** — open a draft PR now with the title derived from the
    plan/spec and a minimal body (issue link + "implementation in progress;
    this PR body will be updated when done"). Step 7 will flesh it out.
    ```bash
    gh pr create --draft --base <base-branch> \
      --title "<title>" --body "<minimal body>"
    ```
    Record the PR number.

## 3. Update Linear issue status (if applicable)

If working from a Linear issue, move it to "In Progress" via the Linear MCP.

## 4. Implement

If working from a **plan**, work through its implementation steps in order.
If working from a **spec**, derive a lean sequence of logical units from
the acceptance criteria and work through them.

Read canonical example files referenced in the plan/spec or in `CLAUDE.md`
before writing code — match existing patterns exactly rather than inventing
new ones.

### Contract deviations

- **Plan path:** if you discover something in the plan won't work as written
  (e.g., an API changed, a dependency is missing, a type doesn't exist),
  stop and ask the user before adapting. Explain what's different and
  propose alternatives. The plan is the contract — don't silently deviate
  from it.
- **Spec path:** if the spec is ambiguous or contradictory, stop and ask the
  user before making the call. The acceptance criteria are the contract.

### Commit discipline

Each commit must leave the codebase in a releasable state — all quality gates
passing. This means:

- **Bundle tests with the code they cover** in the same commit. Never commit
  production code in one commit and its tests in another.
- **Group by logical unit.** A good commit boundary is one module, one service,
  or one schema — together with its tests and any config files it needs.
- **Validate before every commit** (see section 5).

If the plan has explicit implementation steps, use them as a guide for commit
boundaries, but merge steps when splitting them would break quality gates.
On the spec path, infer your own boundaries from the acceptance criteria.

## 5. Validate and commit

Run the project's quality gates before each commit. Check `CLAUDE.md` for
project-specific test commands, lint commands, and other validation steps.

After validation passes:

1. Stage the relevant files for this logical unit.
2. Commit using conventional commits format: `<type>(<scope>): <description>`
3. Push to the remote branch.

Repeat sections 4-5 for each logical unit until the full plan/spec is
implemented.

## 6. Self-review

Run `/review-code` to self-review the complete implementation against the
plan/spec. Fix any critical or warning issues found, run tests, and commit
the fixes.

## 7. Update the PR description

Review the current PR description. If it was opened as a stub in section 2
(or needs more context), fill it out now: summary, test plan, issue link,
and any design decisions or deviations worth noting for reviewers.

Keep any existing structure and issue links — add to them rather than
replacing them wholesale.

## 8. Mark PR as ready

Once all implementation is done, reviewed, and pushed:

```bash
gh pr ready
```

## 9. Watch the PR

Run `/watch-pr` to start the combined CI + review comment monitoring loop.
This will:

- Monitor CI checks and fix failures automatically
- Triage and respond to review comments
- Update the Linear issue status to "In Review" once everything is green
- Escalate to the user if it can't resolve something after retries

The implementation is complete when `/watch-pr` reports the PR is ready for
human review.
