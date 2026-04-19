#!/usr/bin/env bash
# TaskCompleted hook for the swarm skill.
#
# Refuses to mark a swarm task completed unless its PR is actually MERGED.
# Reads Claude Code hook JSON payload from stdin.
#
# Exit 0 - allow completion.
# Exit 2 - block completion; message on stderr is shown to the teammate.
set -euo pipefail

payload="$(cat || true)"

if [[ -z "$payload" ]]; then
  exit 0
fi

if ! command -v jq >/dev/null 2>&1; then
  # Without jq we cannot safely parse the payload; do not interfere.
  exit 0
fi

# Pull task id from likely fields. Agent Teams payload shape may vary; try
# several paths and fall back.
task_id="$(printf '%s' "$payload" | jq -r '
  .task_id //
  .task.id //
  .teammate_name //
  .teammate.name //
  .agent_name //
  empty
')"

if [[ -z "$task_id" || "$task_id" == "null" ]]; then
  # Not a swarm task we can identify; do not block unrelated completions.
  exit 0
fi

branch="swarm/${task_id}"

if ! command -v gh >/dev/null 2>&1; then
  echo "verify_terminal: gh CLI not installed; cannot verify PR state for ${task_id}." >&2
  exit 2
fi

state="$(gh pr view "$branch" --json state -q .state 2>/dev/null || true)"

case "$state" in
  MERGED)
    exit 0
    ;;
  OPEN)
    echo "PR for ${task_id} is still OPEN. Keep working: watch CI, address review comments, and wait for the human to merge. Do NOT mark the task completed yet." >&2
    exit 2
    ;;
  CLOSED)
    echo "PR for ${task_id} was CLOSED without merging. Escalate to the lead instead of marking completed." >&2
    exit 2
    ;;
  "")
    echo "No PR found for branch ${branch}. Have you pushed and run 'gh pr create'?" >&2
    exit 2
    ;;
  *)
    echo "Unexpected PR state '${state}' for ${task_id}. Investigate before marking completed." >&2
    exit 2
    ;;
esac
