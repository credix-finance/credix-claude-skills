# Credix Claude Skills

A Claude Code plugin providing reusable development workflow skills.

## Skills

| Skill | Description |
|-------|-------------|
| `plan-task` | Write implementation plans from Linear issues, files, or descriptions |
| `implement-plan` | Execute implementation plans with quality gates, commits, and PR management |
| `review-code` | Self-review code changes for correctness, completeness, and quality |
| `watch-pr` | Monitor PR CI and review comments, auto-fix failures and respond to feedback |

## Installation

Add this plugin to your Claude Code configuration:

```bash
claude plugin install credix-claude-skills@<marketplace>
```

Or for local development:

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
```

## Workflow

These skills form an integrated development workflow:

1. **Plan** — `/plan-task` gathers context, writes a plan, creates a branch and draft PR
2. **Implement** — `/implement-plan` executes the plan step by step with quality gates
3. **Review** — `/review-code` self-reviews the implementation (also called automatically by implement-plan)
4. **Watch** — `/watch-pr` monitors CI and review comments until the PR is ready

## Requirements

- [GitHub CLI](https://cli.github.com/) (`gh`) for PR operations
- [Linear MCP](https://github.com/anthropics/linear-mcp) for Linear issue integration (optional)

## License

MIT
