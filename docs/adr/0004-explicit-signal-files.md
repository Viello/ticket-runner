# Explicit Signal Files for State Transitions

We chose to use explicit, file-based signals in `.agent/signals/` and `.agent/questions/` for Worker-to-Runner notifications (such as clarification questions, pauses, and Gatekeeper verification requests) rather than parsing freeform stdout logs. File-based signals provide durable state across unexpected process exits, eliminate conversational text parsing ambiguity, and create an easily inspectable file-based audit trail.
