# Subprocess JSON Event Streaming for OpenCode Orchestration

We chose to invoke OpenCode as a managed CLI subprocess using `opencode run --format json` rather than running a persistent headless server daemon (`opencode serve`) or an interactive PTY wrapper. Subprocess execution isolates session lifetimes cleanly, allows direct streaming interception of token metrics and tool events without network state, and simplifies crash recovery across restarts.
