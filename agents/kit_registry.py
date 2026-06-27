"""Static registry for Vibe Engineering kit specs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

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
from agents.kits.opencode.installer import (
    diff_kit as opencode_diff,
    doctor as opencode_doctor,
    install as opencode_install,
    uninstall as opencode_uninstall,
)
from agents.kits.second_brain.installer import (
    diff_kit as second_brain_diff,
    doctor as second_brain_doctor,
    install as second_brain_install,
    uninstall as second_brain_uninstall,
)


@dataclass(frozen=True)
class KitSpec:
    name: str
    help: str
    install: Callable
    diff: Callable
    doctor: Callable
    uninstall: Callable


KITS: dict[str, KitSpec] = {
    "claude-code": KitSpec(
        name="claude-code",
        help="Manage the Claude Code kit",
        install=claude_install,
        diff=claude_diff,
        doctor=claude_doctor,
        uninstall=claude_uninstall,
    ),
    "opencode": KitSpec(
        name="opencode",
        help="Manage the OpenCode kit",
        install=opencode_install,
        diff=opencode_diff,
        doctor=opencode_doctor,
        uninstall=opencode_uninstall,
    ),
    "second-brain": KitSpec(
        name="second-brain",
        help="Manage the second-brain kit — safe scaffold of vault at VIBE_SECOND_BRAIN_PATH",
        install=second_brain_install,
        diff=second_brain_diff,
        doctor=second_brain_doctor,
        uninstall=second_brain_uninstall,
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
}
