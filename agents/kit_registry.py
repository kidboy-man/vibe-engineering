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
from agents.kits.opencode.installer import (
    diff_kit as opencode_diff,
    doctor as opencode_doctor,
    install as opencode_install,
    uninstall as opencode_uninstall,
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
}
