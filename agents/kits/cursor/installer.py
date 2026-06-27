"""Safe installer for the portable Cursor IDE kit.

Manages rule files under ~/.cursor/rules/ — one .mdc file per engineering rule
plus a persona rule. Never modifies Cursor settings, extensions, or credentials.

Note: Cursor also supports project-local rules at .cursor/rules/ (preferred for
per-project behavior). This kit installs global user-level rules that apply
across all projects unless overridden locally.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from agents import installer_core as core

MANIFEST_FILE = core.MANIFEST_FILE
KIT_NAME = "cursor"


@dataclass(frozen=True)
class KitPaths:
    home: Path
    cursor_dir: Path
    rules_dir: Path
    manifest_path: Path
    template_dir: Path


def _template_dir() -> Path:
    return Path(__file__).resolve().parent / "templates" / "cursor"


def _paths(home: str | None = None) -> KitPaths:
    home_path = Path(home).expanduser() if home else Path.home()
    cursor_dir = home_path / ".cursor"
    return KitPaths(
        home=home_path,
        cursor_dir=cursor_dir,
        rules_dir=cursor_dir / "rules",
        manifest_path=cursor_dir / MANIFEST_FILE,
        template_dir=_template_dir(),
    )


def _load_manifest(paths: KitPaths) -> dict:
    return core.load_manifest(paths.template_dir)


def _target_files(paths: KitPaths) -> list[tuple[Path, Path, str]]:
    manifest = _load_manifest(paths)
    return core.target_files(paths.template_dir, paths.cursor_dir, manifest)


def _manifest_state(paths: KitPaths, managed_files: Iterable[str]) -> dict:
    return core.manifest_state(KIT_NAME, managed_files)


def _load_existing_install_manifest(paths: KitPaths) -> dict | None:
    return core.load_existing_install_manifest(paths.manifest_path)


def _confirm(prompt: str, yes: bool) -> bool:
    return core.confirm(prompt, yes)


def install(
    home: str | None = None,
    dry_run: bool = False,
    yes: bool = False,
    merge_settings: bool = True,
    **kwargs,
) -> int:
    paths = _paths(home)
    changes = [*core.planned_changes_copy_style(_target_files(paths)), f"write {MANIFEST_FILE}"]
    for change in changes:
        print(change)
    if dry_run:
        print("dry run: no files written")
        return 0
    if not _confirm("Install/update the Cursor IDE kit?", yes=yes):
        print("aborted")
        return 1

    paths.rules_dir.mkdir(parents=True, exist_ok=True)
    managed: list[str] = []
    for src, dst, rel in _target_files(paths):
        managed.append(rel)
        if core.install_copy_style_file(src, dst, paths.cursor_dir):
            print(f"installed {rel}")

    core.write_text(
        paths.manifest_path,
        json.dumps(_manifest_state(paths, managed), indent=2) + "\n",
    )
    print(f"wrote {paths.manifest_path}")
    return 0


def diff_kit(home: str | None = None) -> int:
    paths = _paths(home)
    any_diff = False
    for src, dst, rel in _target_files(paths):
        if core.diff_copy_style(src, dst, rel):
            any_diff = True
    if not any_diff:
        print("managed files match kit templates")
    return 0


def doctor(home: str | None = None) -> int:
    paths = _paths(home)
    ok = True
    print(f"home: {paths.home}")
    print(f"cursor dir: {paths.cursor_dir}")
    print(f"rules dir: {paths.rules_dir}")
    cursor_bin = shutil.which("cursor")
    if cursor_bin:
        print(f"cursor: {cursor_bin}")
        try:
            result = subprocess.run(
                [cursor_bin, "--version"],
                check=False,
                text=True,
                capture_output=True,
                timeout=10,
            )
            print(f"cursor version: {(result.stdout or result.stderr).strip()}")
        except Exception as exc:  # pragma: no cover - environment dependent
            print(f"cursor version check failed: {exc}")
    else:
        print("cursor: not found in PATH (Cursor may be installed as a GUI app)")

    manifest = _load_existing_install_manifest(paths)
    if manifest:
        print(f"manifest: installed kit={manifest.get('kit')} files={len(manifest.get('managed_files', []))}")
    else:
        print("manifest: not installed")

    missing_templates = [rel for src, _dst, rel in _target_files(paths) if not src.exists()]
    if missing_templates:
        ok = False
        for rel in missing_templates:
            print(f"missing template: {rel}")
    else:
        print("templates: ok")

    print("note: for per-project rules, copy .mdc files to .cursor/rules/ in each project")
    return 0 if ok else 1


def uninstall(home: str | None = None, dry_run: bool = False, yes: bool = False) -> int:
    paths = _paths(home)
    manifest = _load_existing_install_manifest(paths)
    if not manifest:
        print(f"no {MANIFEST_FILE} found; nothing to uninstall")
        return 0
    files = manifest.get("managed_files", [])
    for rel in files:
        print(f"remove if unchanged {rel}")
    print(f"remove {MANIFEST_FILE}")
    if dry_run:
        print("dry run: no files removed")
        return 0
    if not _confirm("Uninstall managed Cursor IDE kit files?", yes=yes):
        print("aborted")
        return 1

    removed = 0
    for rel in files:
        src = paths.template_dir / rel
        dst = paths.cursor_dir / rel
        if not dst.exists():
            continue
        if core.uninstall_unchanged_file(src, dst):
            removed += 1
            print(f"removed {rel}")
        else:
            print(f"kept modified file {rel}")
    if paths.manifest_path.exists():
        paths.manifest_path.unlink()
    print(f"removed {removed} files")
    return 0
