#!/bin/sh
# BEGIN TICKET RUNNER GUARDRAIL
current_branch=$(git symbolic-ref --short HEAD 2>/dev/null)
if [ "$current_branch" = "agent/ticket-runner" ]; then
  echo "ERROR: Direct git push is blocked on agent/ticket-runner branch." >&2
  exit 1
fi
# END TICKET RUNNER GUARDRAIL
exit 0
