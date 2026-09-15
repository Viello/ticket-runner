# Global Gotchas & Lessons Learned

A chronological record of runtime quirks, platform pitfalls, and architectural lessons discovered during ticket implementations. Subsequent ticket sessions ingest these lessons to prevent recurring mistakes.

---

### Windows Subprocess Executable Resolution
- **Problem**: Calling `asyncio.create_subprocess_exec` on Windows fails with `FileNotFoundError` when executing scripts or binary names without explicit file extensions (`.exe`, `.cmd`, `.bat`).
- **Solution**: Resolve the binary path beforehand using `shutil.which(cmd[0])` before dispatching to `create_subprocess_exec`, and ensure the process runs on `asyncio.ProactorEventLoop`.

### Windows Subprocess Standard Handle Duplication
- **Problem**: Running `subprocess.run(..., capture_output=True)` inside background tasks or PowerShell subshells on Windows can raise `OSError: [WinError 6] The handle is invalid` when Python attempts to duplicate an unassigned `stdin` handle.
- **Solution**: Always pass `stdin=subprocess.DEVNULL` explicitly to `subprocess.run` or `subprocess.Popen` whenever standard input is not actively consumed.

### POSIX Shell Hook Newlines on Windows
- **Problem**: Git for Windows bundled `sh.exe` fails with syntax parsing errors or `/bin/sh^M: bad interpreter` when executing shell scripts that contain Windows CRLF (`\r\n`) line endings.
- **Solution**: Author and write all shell scripts and git hook templates with explicit POSIX LF (`\n`) line endings via `write_text(..., encoding="utf-8", newline="\n")`.

### Non-Destructive Git Hook Preservation
- **Problem**: Overwriting existing hook files in `.git/hooks/` destroys pre-existing developer or repository hook logic.
- **Solution**: Check for unique signature delimiters (`# BEGIN TICKET RUNNER GUARDRAIL` and `# END TICKET RUNNER GUARDRAIL`) before writing; if missing, non-destructively append the guardrail block to the end of the existing file and ensure executable permissions (`0o755`).
