"""Safe installer for the portable Cursor IDE kit.

Manages rule files under ~/.cursor/rules/ — one .mdc file per engineering rule
plus a persona rule. Never modifies Cursor settings, extensions, or credentials.

Note: Cursor also supports project-local rules at .cursor/rules/ (preferred for
per-project behavior). This kit installs global user-level rules that apply
across all projects unless overridden locally.
"""

from __future__ import annotations

from pathlib import Path

from agents import installer_core as core

MANIFEST_FILE = core.MANIFEST_FILE
KIT_NAME = "cursor"

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
    doctor_footer="note: for per-project rules, copy .mdc files to .cursor/rules/ in each project",
)


def install(home: str | None = None, dry_run: bool = False, yes: bool = False, **kwargs) -> int:
    return core.copy_kit_install(KIT, home=home, dry_run=dry_run, yes=yes)


def diff_kit(home: str | None = None) -> int:
    return core.copy_kit_diff(KIT, home=home)


def doctor(home: str | None = None) -> int:
    return core.copy_kit_doctor(KIT, home=home)


def uninstall(home: str | None = None, dry_run: bool = False, yes: bool = False) -> int:
    return core.copy_kit_uninstall(KIT, home=home, dry_run=dry_run, yes=yes)
