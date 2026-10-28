# Investigation: Live Terminal Dashboard Swallowing Interactive Prompts & agy Model/Effort CLI Conflict

- **Discovered**: 2026-10-16 during live execution of `py -3 D:\Projects\ticket_runner.py --project-dir D:\Repos\agent-skills start --local-only` on Ticket `T101`.
- **Target Project**: `D:\Repos\agent-skills` (Clean tree, branch `agent/ticket-runner`).
- **Severity**: High (Blocks operator intervention, causes indefinite silent hangs with frozen UI).

---

## 1. Problem

During interactive live testing of the Ticket Runner in an interactive console (`cmd.exe` / Windows Terminal), two compounding failure modes were observed:

### Problem A: Terminal Dashboard Swallowing Interactive Prompts (`input()`)
1. **Hidden Escalation Prompts**:
   When an escalation or recovery confirmation is triggered:
   - `TerminalInterventionGateway.prompt_escalation` prompts: `Run /diagnosing-bugs? [Y/n]`
   - `HandoffCoordinator.default_recovery_confirmation` prompts: `Synthesize emergency checkpoint and resume with a fresh session? [Y/n]: `
   Neither prompt is rendered on the terminal screen.
2. **Frozen Dashboard & Blind Input**:
   The user's console remains frozen showing the Rich split dashboard (`status: WORKING`, `attempt: 0 / 3`, `tokens: 0`). The user sees no prompt, cursor indicator, or indication that the process is waiting on input.
   Only after the operator types a character (e.g. `n`) and presses Enter does the prompt text suddenly flush and appear on the console in a broken format.
3. **Indefinite Silent Hang**:
   If the operator does not realize a prompt was emitted, the Python process (e.g. `PID 24344`) remains blocked indefinitely in `sys.stdin.readline()` (kernel thread state: `Wait Executive` on `NtReadFile`) with 0% CPU and zero child processes, giving the false illusion that the Runner is executing work.

### Problem B: Fatal CLI Argument Conflict in `agy` (`--model` vs `--effort`)
1. **Crash on Startup**:
   Ticket `T101` defines `Reasoning: medium` in frontmatter, and the Runner was configured with model `gemini-3.8-flash-high`.
   When `AntigravityWorker.build_run_command` assembled the command tokens, it passed both `--model gemini-3.8-flash-high` and `--effort medium`.
2. **Immediate Rejection**:
   `agy` failed instantly with exit code `1`:
   ```text
   error: invalid model selection (--model "gemini-3.8-flash-high" --effort "medium"): --model gemini-3.8-flash-high conflicts with --effort=medium
   ```
   Because `gemini-3.8-flash-high` already encodes the effort tier (`high`) in its name, passing `--effort medium` is an illegal argument combination.
3. **Triggered Crash Escalation**:
   The immediate crash of `agy` caused `HandoffCoordinator` to trigger emergency recovery (`default_recovery_confirmation`), which invoked Problem A (`input()` swallowed under Rich Live), leaving the Runner stuck on line 1 for 45+ minutes.

---

## 2. Hypothesis

### Hypothesis 1: Terminal Display Buffer Deadlock on Standard Input
- **Hypothesis**: `RichTerminalDisplay` runs `rich.live.Live` with continuous buffer redrawing on standard output. Calling Python's standard `input(prompt)` or `sys.stdin.readline()` while `Live` is running writes the prompt outside `Live`'s virtual buffer and leaves stdout un-flushed or overwritten by the next layout refresh tick. Stdin then blocks on the Windows console handle without any prompt visible to the operator.
- **Verification**: Confirmed via thread inspection of `PID 24344`. The main thread `TID 16684` was suspended in `NtReadFile` on `CONIN$`. A direct reproduction in Python showed that calling `input()` while `Live(refresh_per_second=4).start()` is active completely swallows the prompt until Enter is pressed.

### Hypothesis 2: Silent Supervisor Exit or Subprocess Failure on Ticket Startup
- **Hypothesis**: The Worker subprocess (`agy.exe`) either failed to spawn, or spawned and terminated immediately due to an unhandled exception or CLI argument validation error, without streaming any JSONL events to `.agent/logs/`.
- **Verification**: Confirmed by directly executing `AntigravityWorker.build_run_command(prompt="...", variant="medium", model_id="gemini-3.8-flash-high")` in `D:\Repos\agent-skills`. `agy` exited with status `1` within 400ms printing:
  `error: invalid model selection (--model "gemini-3.8-flash-high" --effort "medium"): --model gemini-3.8-flash-high conflicts with --effort=medium`.

### Hypothesis 3: Embedded Reasoning Tier Suffix in Antigravity Model Identifiers
- **Hypothesis**: All models exposed by the Antigravity CLI (`agy models`) already embed their reasoning tier as a suffix (`-high`, `-medium`, `-low`, `-xhigh`, `-max`). Passing an explicit `--effort` flag alongside these models is rejected by `agy` as a contradictory or redundant option.
- **Verification**: Confirmed via `agy models`:
  ```text
  gemini-4-argon-medium
  gemini-4-argon-high
  gemini-4-argon-low
  gemini-3.8-flash-high
  gemini-3.8-flash-medium
  gemini-3.8-flash-low
  claude-opus-5-5-high
  claude-sonnet-5-5-high
  ```
  Running `agy -p "hello" --output-format stream-json --model gemini-3.8-flash-high --print-timeout 0` (WITHOUT `--effort`) ran successfully, spawned, streamed turns, and exited with status 0.

---

## 3. Root Cause Analysis & Empirical Evidence

### Root Cause 1: Unpaused `rich.live.Live` Around `input()` Calls
In `runner/adapters/ui/terminal.py`, `RichTerminalDisplay` wraps standard output with a `rich.live.Live` context:
```python
self._live = Live(self._layout, console=self._console, refresh_per_second=4, auto_refresh=False)
self._live.start(refresh=True)
```
When an escalation occurs, two separate components invoke standard Python `input()` without pausing the Live display:
1. `runner/adapters/ui/terminal_prompts.py:127`:
   `TerminalInterventionGateway.prompt_escalation` -> `input(prompt)`
2. `runner/application/handoff_coordinator.py:126`:
   `default_recovery_confirmation` -> `input(prompt)`

Because the Live display holds raw terminal control, `input()` prompts are hidden until keystrokes are received.

### Root Cause 2: Naive `--effort` Appending in `AntigravityWorker`
In `runner/adapters/antigravity/antigravity_worker.py`:
```python
if variant is not None:
    clean_variant = variant.strip()
    if clean_variant:
        cmd.extend(["--effort", clean_variant])
```
When `ticket.reasoning` (or `default_reasoning`) provides `"medium"`, this block appends `--effort medium` even if `--model gemini-3.8-flash-high` is already present. `agy` forbids specifying both if the model has a fixed effort tier.

### Root Cause 3: Malformed Quoted Path in Telemetry Hook Configuration
`agy` execution logs revealed that every tool call emitted by `agy` generates an internal hook warning:
```text
Error: Cannot find module 'C:\Users\Acer\.gemini\config\plugins\googlecloudtools.datacloud_telemetry\"C:\Users\Acer\.gemini\config\plugins\googlecloudtools.datacloud_telemetry\telemetry_hook_bundle.js"'
```
The plugin hook configuration in `C:\Users\Acer\.gemini\config\plugins\googlecloudtools.datacloud_telemetry` contains embedded escaped quotes (`"\"...\""`), causing pre-tool hook failures in `agy`.

---

## 4. Accepted Fix Behavior

### 1. Terminal Display Pause & Prompt Isolation
- **Contract**: Before any component reads standard input from the interactive terminal (`input()`, `sys.stdin.readline()`), the active `RichTerminalDisplay` MUST be suspended/stopped so the terminal is restored to normal cooking mode.
- **Behavior**:
  ```python
  if display is not None and getattr(display, "is_active", False):
      display.stop()
      try:
          return input(prompt)
      finally:
          display.start()
  ```
- **Seams Requiring the Guard**:
  - `TerminalInterventionGateway._read_line` in `runner/adapters/ui/terminal_prompts.py`
  - `default_recovery_confirmation` in `runner/application/handoff_coordinator.py`
  - Any future interactive prompt gateways.

### 2. Antigravity CLI Model/Effort Compatibility Guard
- **Contract**: `AntigravityWorker.build_run_command` must only pass `--effort` when it does not conflict with the chosen `--model`.
- **Behavior**:
  - Inspect `model_id`.
  - If `model_id` contains a known effort tier suffix (`-high`, `-medium`, `-low`, `-xhigh`, `-max`), suppress `--effort` from the generated command line.
  - If `model_id` does NOT specify an effort tier, or is omitted, pass `--effort <variant>` as requested by the ticket or configuration.
  - This guarantees `agy` receives non-conflicting arguments for all models in `agy models`.

### 3. Clean Escalation Recovery & State Transitions
- **Contract**: If the operator responds `n` (decline) to an escalation recovery prompt:
  - The Runner must cleanly transition the state back to `IDLE` or `FAILED`, release the queue lock, and present a readable summary.
  - The Runner must never leave the process dangling in a headless wait state.

### 4. Telemetry Hook Path Sanitization
- **Contract**: The hook definition in `C:\Users\Acer\.gemini\config\plugins\googlecloudtools.datacloud_telemetry` must use clean relative or unquoted paths so that `agy` tool execution proceeds without `MODULE_NOT_FOUND` warnings.
