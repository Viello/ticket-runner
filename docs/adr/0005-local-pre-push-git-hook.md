# Local Pre-Push Git Hook Guardrails

We chose to enforce git push restrictions on the autonomous runner branch (`agent/ticket-runner`) using a local `.git/hooks/pre-push` script in addition to prompt instructions. Autonomous LLM coding agents running with automated tool approvals can hallucinate or accidentally trigger remote repository pushes, so a deterministic git hook provides an unbypassable safety barrier.
