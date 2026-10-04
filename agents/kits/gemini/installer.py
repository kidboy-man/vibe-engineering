"""Safe installer for the portable Gemini CLI kit.

Manages only portable files: GEMINI.md with embedded engineering persona, rules,
and specialist role descriptions. Never copies credentials, auth tokens, or
machine-specific configuration.
"""

from __future__ import annotations

from pathlib import Path

from agents import installer_core as core

MANIFEST_FILE = core.MANIFEST_FILE
KIT_NAME = "gemini"

KIT = core.CopyKit(
    kit_name=KIT_NAME,
    label="Gemini CLI",
    template_dir=Path(__file__).resolve().parent / "templates" / "gemini",
    target_subdir=".gemini",
    binary="gemini",
    missing_binary_message="gemini: not found (install the Google Gemini CLI)",
)


def install(home: str | None = None, dry_run: bool = False, yes: bool = False, **kwargs) -> int:
    return core.copy_kit_install(KIT, home=home, dry_run=dry_run, yes=yes)


def diff_kit(home: str | None = None) -> int:
    return core.copy_kit_diff(KIT, home=home)


def doctor(home: str | None = None) -> int:
    return core.copy_kit_doctor(KIT, home=home)


def uninstall(home: str | None = None, dry_run: bool = False, yes: bool = False) -> int:
    return core.copy_kit_uninstall(KIT, home=home, dry_run=dry_run, yes=yes)
