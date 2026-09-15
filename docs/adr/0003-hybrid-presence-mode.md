# Hybrid Presence Mode with Inactivity Escalation

We chose a hybrid Presence Mode (`nearby` vs `away`) where the Runner defaults to terminal interaction and automatically escalates unanswered prompts to Discord after a 3-minute idle timeout. This avoids notification fatigue when the user is actively working at their terminal, while guaranteeing unattended tickets are never blocked indefinitely if the user steps away.
