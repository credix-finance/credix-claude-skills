#!/usr/bin/env bash
# TeammateIdle hook for the swarm skill.
#
# Keeps a teammate working if its PR still has pending CI or reviewer changes.
# Reads Claude Code hook JSON payload from stdin.
#
# Exit 0 - allow idle.
# Exit 2 - keep the teammate working; message on stderr nudges them.
set -euo pipefail

payload="$(cat || true)"

if [[ -z "$payload" ]]; then
  exit 0
fi

if ! command -v jq >/dev/null 2>&1; then
  exit 0
fi

task_id="$(printf '%s' "$payload" | jq -r '
  .task_id //
  .task.id //
  .teammate_name //
  .teammate.name //
  .agent_name //
  empty
')"

if [[ -z "$task_id" || "$task_id" == "null" ]]; then
  exit 0
fi

branch="swarm/${task_id}"

if ! command -v gh >/dev/null 2>&1; then
  exit 0
fi

pr_json="$(gh pr view "$branch" --json state,mergeable,reviewDecision,statusCheckRollup 2>/dev/null || true)"

if [[ -z "$pr_json" ]]; then
  # No PR yet — teammate is probably still implementing. Don't nudge.
  exit 0
fi

state="$(printf '%s' "$pr_json" | jq -r '.state // empty')"
case "$state" in
  MERGED|CLOSED)
    exit 0
    ;;
esac

ci_running="$(printf '%s' "$pr_json" | jq -r '
  [.statusCheckRollup[]? | .status // empty] | map(select(. == "IN_PROGRESS" or . == "QUEUED")) | length
')"
if [[ "${ci_running:-0}" != "0" ]]; then
  echo "CI is still running on PR for ${task_id}. Keep watching — do not go idle yet." >&2
  exit 2
fi

ci_failed="$(printf '%s' "$pr_json" | jq -r '
  [.statusCheckRollup[]? | .conclusion // empty] | map(select(. == "FAILURE")) | length
')"
if [[ "${ci_failed:-0}" != "0" ]]; then
  echo "CI is failing on PR for ${task_id}. Diagnose and push a fix, or ESCALATE if you've hit the 3-failure stop condition." >&2
  exit 2
fi

decision="$(printf '%s' "$pr_json" | jq -r '.reviewDecision // empty')"
if [[ "$decision" == "CHANGES_REQUESTED" ]]; then
  echo "Reviewer requested changes on PR for ${task_id}. Address the comments or ESCALATE if out of scope." >&2
  exit 2
fi

# Otherwise: no CI pending, no failures, no changes requested. Probably
# awaiting review — let the teammate idle; the loop will re-poll.
exit 0
