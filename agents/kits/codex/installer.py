"""Safe installer for the portable Codex CLI kit.

Manages only portable files: AGENTS.md with embedded engineering persona, rules,
and specialist role descriptions. Never copies API keys, auth tokens, or
machine-specific configuration.
"""

from __future__ import annotations

from pathlib import Path

from agents import installer_core as core

MANIFEST_FILE = core.MANIFEST_FILE
KIT_NAME = "codex"

KIT = core.CopyKit(
    kit_name=KIT_NAME,
    label="Codex CLI",
    template_dir=Path(__file__).resolve().parent / "templates" / "codex",
    target_subdir=".codex",
    binary="codex",
    missing_binary_message="codex: not found (install the OpenAI Codex CLI)",
)


def install(home: str | None = None, dry_run: bool = False, yes: bool = False, **kwargs) -> int:
    return core.copy_kit_install(KIT, home=home, dry_run=dry_run, yes=yes)


def diff_kit(home: str | None = None) -> int:
    return core.copy_kit_diff(KIT, home=home)


def doctor(home: str | None = None) -> int:
    return core.copy_kit_doctor(KIT, home=home)


def uninstall(home: str | None = None, dry_run: bool = False, yes: bool = False) -> int:
    return core.copy_kit_uninstall(KIT, home=home, dry_run=dry_run, yes=yes)
