"""Static registry for Vibe Engineering kit specs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol

from agents.kits.claude_code.installer import (
    diff_kit as claude_diff,
    doctor as claude_doctor,
    install as claude_install,
    uninstall as claude_uninstall,
)
from agents.kits.codex.installer import (
    diff_kit as codex_diff,
    doctor as codex_doctor,
    install as codex_install,
    uninstall as codex_uninstall,
)
from agents.kits.cursor.installer import (
    diff_kit as cursor_diff,
    doctor as cursor_doctor,
    install as cursor_install,
    uninstall as cursor_uninstall,
)
from agents.kits.gemini.installer import (
    diff_kit as gemini_diff,
    doctor as gemini_doctor,
    install as gemini_install,
    uninstall as gemini_uninstall,
)
from agents.kits.guardrails.installer import (
    diff_kit as guardrails_diff,
    doctor as guardrails_doctor,
    install as guardrails_install,
    uninstall as guardrails_uninstall,
)
from agents.kits.opencode.installer import (
    diff_kit as opencode_diff,
    doctor as opencode_doctor,
    install as opencode_install,
    uninstall as opencode_uninstall,
)
from agents.kits.workflow.installer import (
    diff_kit as workflow_diff,
    doctor as workflow_doctor,
    install as workflow_install,
    uninstall as workflow_uninstall,
)
from agents.kits.second_brain.installer import (
    diff_kit as second_brain_diff,
    doctor as second_brain_doctor,
    enable_hook as second_brain_enable_hook,
    install as second_brain_install,
    uninstall as second_brain_uninstall,
)


class InstallFn(Protocol):
    """install(home, dry_run, yes, **declared options) -> exit code."""

    def __call__(self, home: str | None = None, dry_run: bool = False, yes: bool = False, **options: bool) -> int: ...


class UninstallFn(Protocol):
    def __call__(self, home: str | None = None, dry_run: bool = False, yes: bool = False) -> int: ...


class HomeFn(Protocol):
    """diff / doctor: read-only commands that only need the target home."""

    def __call__(self, home: str | None = None) -> int: ...


@dataclass(frozen=True)
class InstallOption:
    """One optional ``install`` flag and the installer kwarg it controls."""

    flag: str
    kwarg: str
    help: str
    negated: bool = True  # --no-x flags pass kwarg = not flag

    @property
    def dest(self) -> str:
        return self.flag.lstrip("-").replace("-", "_")

    def value_from(self, args) -> bool:
        value = getattr(args, self.dest)
        return not value if self.negated else value


# Keyed by the names used in KitSpec.install_options. Order is the order the
# flags appear in --help, so keep it stable.
INSTALL_OPTIONS: Mapping[str, InstallOption] = {
    "settings": InstallOption("--no-settings", "merge_settings", "Do not merge the safe settings fragment"),
    "setup_deps": InstallOption("--no-setup-deps", "setup_deps", "Do not auto-install qmd or other dependencies"),
    "hooks": InstallOption("--no-hooks", "enable_hooks", "Skip the proactive SessionStart hook / CLAUDE.md prompt"),
    "with_verify": InstallOption(
        "--with-verify", "with_verify", "Also register the opt-in gofmt check after Claude Code edits", negated=False
    ),
}


@dataclass(frozen=True)
class KitSpec:
    name: str
    help: str
    install: InstallFn
    diff: HomeFn
    doctor: HomeFn
    uninstall: UninstallFn
    enable_hook: UninstallFn | None = None
    install_options: frozenset[str] = frozenset()

    def options(self) -> list[InstallOption]:
        return [opt for key, opt in INSTALL_OPTIONS.items() if key in self.install_options]


KITS: dict[str, KitSpec] = {
    "claude-code": KitSpec(
        name="claude-code",
        help="Manage the Claude Code kit",
        install=claude_install,
        diff=claude_diff,
        doctor=claude_doctor,
        uninstall=claude_uninstall,
        install_options=frozenset({"settings"}),
    ),
    "opencode": KitSpec(
        name="opencode",
        help="Manage the OpenCode kit",
        install=opencode_install,
        diff=opencode_diff,
        doctor=opencode_doctor,
        uninstall=opencode_uninstall,
        install_options=frozenset({"settings"}),
    ),
    "second-brain": KitSpec(
        name="second-brain",
        help="Manage the second-brain kit — safe scaffold of vault at VIBE_SECOND_BRAIN_PATH",
        install=second_brain_install,
        diff=second_brain_diff,
        doctor=second_brain_doctor,
        uninstall=second_brain_uninstall,
        enable_hook=second_brain_enable_hook,
        install_options=frozenset({"settings", "setup_deps", "hooks"}),
    ),
    "gemini": KitSpec(
        name="gemini",
        help="Manage the Gemini CLI kit",
        install=gemini_install,
        diff=gemini_diff,
        doctor=gemini_doctor,
        uninstall=gemini_uninstall,
    ),
    "codex": KitSpec(
        name="codex",
        help="Manage the Codex CLI kit",
        install=codex_install,
        diff=codex_diff,
        doctor=codex_doctor,
        uninstall=codex_uninstall,
    ),
    "cursor": KitSpec(
        name="cursor",
        help="Manage the Cursor IDE kit",
        install=cursor_install,
        diff=cursor_diff,
        doctor=cursor_doctor,
        uninstall=cursor_uninstall,
    ),
    "guardrails": KitSpec(
        name="guardrails",
        help="Manage the guardrails kit — hooks that block destructive commands and secret access",
        install=guardrails_install,
        diff=guardrails_diff,
        doctor=guardrails_doctor,
        uninstall=guardrails_uninstall,
        install_options=frozenset({"with_verify"}),
    ),
    "workflow": KitSpec(
        name="workflow",
        help="Manage the workflow kit — business requirement to PRD, TRD, tickets, and TDD implementation",
        install=workflow_install,
        diff=workflow_diff,
        doctor=workflow_doctor,
        uninstall=workflow_uninstall,
    ),
}
