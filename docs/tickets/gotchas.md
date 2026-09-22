# Global Gotchas & Lessons Learned

A chronological record of runtime quirks, platform pitfalls, and architectural lessons discovered during ticket implementations. Subsequent ticket sessions ingest these lessons to prevent recurring mistakes.

---

## Discord Snowflake Validation & Config Loader Defaults

- **Problem:** Discord snowflake IDs (like `guild_id` and `notify_user_id`) can be up to 20 digits and can be loaded from YAML either as quoted strings or unquoted numbers (integers). Applying integer length constraints or strict string typing without coercion in the loader breaks valid configurations, while mutating fields in a `frozen=True` dataclass fails.
- **Solution:** Handle type coercion and strip whitespace in the loader adapter (`str(val).strip() if val is not None else ""`), validate snowflake IDs using `str.isdigit()` in `DiscordConfig.__post_init__` for non-empty values, and provide empty string defaults so omitting optional fields maintains backward compatibility.

---

## RuntimePaths Containment Resolution & Smoke Log Fallbacks

- **Problem:** `RuntimePaths` root directory can be instantiated either as relative (`Path(".agent")`) or absolute (e.g. `tmp_path / ".agent"` in test harnesses). Performing path containment checks without resolving paths, or performing cross-drive checks on Windows, can lead to unexpected `ValueError` exceptions. Furthermore, `ReadySignal.scope` can be empty or omitted by workers, risking missing or malformed log paths.
- **Solution:** In `RuntimePaths.smoke_log_path`, sanitize the spec slug by replacing non-alphanumeric, non-hyphen characters with underscores and check `target.resolve().is_relative_to(root_resolved)` within a guarded `try/except (ValueError, RuntimeError)` block. In `VerificationLoop._append_smoke_log`, explicitly fallback to `ticket.id` when `ready_signal.scope` is empty or None before delegating to `smoke_log_path`.

---

## PromptBuilder Template Escaping & Command-Line Length Ceilings

- **Problem:** Python f-string prompt templates in `PromptBuilder.build` require literal JSON schema curly braces to be escaped as `{{` and `}}` to avoid KeyError interpolation failures. Additionally, as `AGENTS.md` invariants and prompt schema instructions expand, total Windows command length must be monitored to ensure it stays well below the 32,767-character Windows subprocess ceiling.
- **Solution:** Always double JSON schema braces (`{{` and `}}`) in prompt builder templates, and ensure unit tests for command length assertions accommodate new invariants while maintaining generous safety margins beneath the OS ceiling.


