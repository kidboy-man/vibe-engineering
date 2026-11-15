"""Safe installer for the portable Cursor IDE kit.

Manages rule files under ~/.cursor/rules/ — one .mdc file per engineering rule
plus a persona rule. Never modifies Cursor settings, extensions, or credentials.

Note: Cursor documents project rules at .cursor/rules/ and only partly supports
a global ~/.cursor/rules. Installing there prints a warning; for rules Cursor
reliably loads, install into a project with ``--home <repo>``.
"""

from __future__ import annotations

from pathlib import Path

from agents import installer_core as core

MANIFEST_FILE = core.MANIFEST_FILE
KIT_NAME = "cursor"

GLOBAL_INSTALL_NOTICE = (
    "warning: Cursor does not reliably load rules from ~/.cursor/rules (its docs only describe "
    "project rules in .cursor/rules). For rules Cursor will read, install per project: "
    "vibe kits cursor install --home <repo>"
)

KIT = core.CopyKit(
    kit_name=KIT_NAME,
    label="Cursor IDE",
    template_dir=Path(__file__).resolve().parent / "templates" / "cursor",
    target_subdir=".cursor",
    binary="cursor",
    missing_binary_message="cursor: not found in PATH (Cursor may be installed as a GUI app)",
    missing_binary_is_failure=False,
    ensure_subdir="rules",
    extra_doctor_dirs=(("rules dir", "rules"),),
    default_target_notice=GLOBAL_INSTALL_NOTICE,
)


def install(home: str | None = None, dry_run: bool = False, yes: bool = False, **kwargs) -> int:
    return core.copy_kit_install(KIT, home=home, dry_run=dry_run, yes=yes)


def diff_kit(home: str | None = None) -> int:
    return core.copy_kit_diff(KIT, home=home)


def doctor(home: str | None = None) -> int:
    return core.copy_kit_doctor(KIT, home=home)


def uninstall(home: str | None = None, dry_run: bool = False, yes: bool = False) -> int:
    return core.copy_kit_uninstall(KIT, home=home, dry_run=dry_run, yes=yes)
