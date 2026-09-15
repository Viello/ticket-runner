"""Adapter for installing and verifying the pre-push git hook guardrail."""

import os
from pathlib import Path
import stat


class PrePushHookInstaller:
    """Manages the installation and verification of the pre-push git hook."""

    BEGIN_SIGNATURE: str = "# BEGIN TICKET RUNNER GUARDRAIL"
    END_SIGNATURE: str = "# END TICKET RUNNER GUARDRAIL"

    GUARDRAIL_SNIPPET: str = (
        f"{BEGIN_SIGNATURE}\n"
        'current_branch=$(git symbolic-ref --short HEAD 2>/dev/null)\n'
        'if [ "$current_branch" = "agent/ticket-runner" ]; then\n'
        '  echo "ERROR: Direct git push is blocked on agent/ticket-runner branch." >&2\n'
        "  exit 1\n"
        "fi\n"
        f"{END_SIGNATURE}"
    )

    DEFAULT_STANDALONE_HOOK: str = (
        "#!/bin/sh\n"
        f"{GUARDRAIL_SNIPPET}\n"
        "exit 0\n"
    )

    @classmethod
    def is_installed(cls, git_dir: Path | None = None) -> bool:
        """Check if the pre-push hook is installed and contains the guardrail signature.

        Args:
            git_dir: Path to the .git directory. Defaults to Path(".git").

        Returns:
            True if the pre-push hook exists and contains the signature delimiters,
            False otherwise.
        """
        target_git_dir = git_dir or Path(".git")
        hook_path = target_git_dir / "hooks" / "pre-push"
        if not hook_path.is_file():
            return False

        try:
            content = hook_path.read_text(encoding="utf-8")
            return cls.BEGIN_SIGNATURE in content and cls.END_SIGNATURE in content
        except OSError:
            return False

    @classmethod
    def install(
        cls,
        git_dir: Path | None = None,
        template_path: Path | None = None,
    ) -> bool:
        """Install or update the pre-push hook with the guardrail block.

        If the hook does not exist, creates it using the template or default content
        and grants executable permissions (0o755).
        If the hook exists without the signature, appends the guardrail snippet non-destructively.
        If already installed, does nothing (idempotent).

        Args:
            git_dir: Path to the .git directory. Defaults to Path(".git").
            template_path: Optional path to the pre-push shell script template.
                          Defaults to scripts/pre-push.sh.

        Returns:
            True upon successful verification/installation.
        """
        target_git_dir = git_dir or Path(".git")
        hooks_dir = target_git_dir / "hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)
        hook_path = hooks_dir / "pre-push"

        if cls.is_installed(target_git_dir):
            return True

        template_file = template_path or Path("scripts/pre-push.sh")

        if hook_path.exists():
            existing_content = hook_path.read_text(encoding="utf-8")
            separator = "\n" if not existing_content.endswith("\n") and existing_content else ""
            new_content = f"{existing_content}{separator}\n{cls.GUARDRAIL_SNIPPET}\n"
            hook_path.write_text(new_content, encoding="utf-8", newline="\n")
        else:
            if template_file.is_file():
                template_content = template_file.read_text(encoding="utf-8")
            else:
                template_content = cls.DEFAULT_STANDALONE_HOOK
            hook_path.write_text(template_content, encoding="utf-8", newline="\n")

        # Set executable permissions (0o755)
        try:
            current_mode = hook_path.stat().st_mode
            hook_path.chmod(
                current_mode
                | stat.S_IRUSR
                | stat.S_IWUSR
                | stat.S_IXUSR
                | stat.S_IRGRP
                | stat.S_IXGRP
                | stat.S_IROTH
                | stat.S_IXOTH
            )
        except OSError:
            pass

        return True
