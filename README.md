# Credix Claude Skills

A Claude Code plugin providing reusable development workflow skills.

## Skills

| Skill | Description |
|-------|-------------|
| `plan-task` | Write implementation plans from Linear issues, files, or descriptions |
| `implement-plan` | Execute implementation plans with quality gates, commits, and PR management |
| `review-code` | Self-review code changes for correctness, completeness, and quality |
| `watch-pr` | Monitor PR CI and review comments, auto-fix failures and respond to feedback |
| `ship-task` | Orchestrate one task end-to-end via a planner → implementer → reviewer Agent Teams pipeline |
| `swarm` | Burn down a batch of refined tasks as parallel PRs using Agent Teams |

## Agents

These ship with the plugin and are auto-loaded; they're meant to be spawned by
`ship-task` or `swarm`, not invoked manually:

| Agent | Role |
|-------|------|
| `planner` | Writes the implementation plan, surfaces questions through the lead, submits for user approval |
| `implementer` | Builds the task, opens the PR, addresses review findings received as direct teammate messages |
| `reviewer` | Reviews the PR and sends findings **directly to the implementer** via team messages (no GitHub review comments). Never approves; the human approves. |

## Installation

Add the Credix marketplace and install the plugin:

```
/plugin marketplace add credix-finance/credix-claude-skills
/plugin install credix-claude-skills@credix-plugins
```

For local development:

```bash
claude --plugin-dir /path/to/credix-claude-skills
```

## Usage

Once installed, the skills are available as slash commands:

```
/credix-claude-skills:plan-task PE-1234
/credix-claude-skills:implement-plan PE-1234
/credix-claude-skills:review-code
/credix-claude-skills:watch-pr
/credix-claude-skills:ship-task PE-1234
/credix-claude-skills:swarm PE-1234 PE-1235 PE-1236
```

## Workflow

There are two ways to use these skills, depending on how much you want to
drive yourself:

**Manual** — invoke the skills one at a time:

1. **Plan** — `/plan-task` gathers context, writes a plan, creates a branch and draft PR
2. **Implement** — `/implement-plan` executes the plan step by step with quality gates
3. **Review** — `/review-code` self-reviews the implementation (also called automatically by implement-plan)
4. **Watch** — `/watch-pr` monitors CI and review comments until the PR is ready

**Orchestrated** — let one skill drive a multi-agent pipeline:

- **One task** → `/ship-task` spawns a `planner`, gets your approval on the
  plan, hands off to an `implementer`, then spawns a `reviewer` that sends
  findings directly to the implementer (no GitHub round-trip) until sign-off.
- **A batch of tasks** → `/swarm` parallelizes the same flow across many
  refined tickets at once, opening one PR per task.

Both orchestrators require Claude Code ≥ 2.1.32 with Agent Teams enabled
(`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`).

## Requirements

- [GitHub CLI](https://cli.github.com/) (`gh`) for PR operations
- [Linear MCP](https://github.com/anthropics/linear-mcp) for Linear issue integration (optional)
