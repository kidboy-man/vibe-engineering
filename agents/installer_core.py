"""Shared installer primitives for vibe-engineering kits.

This module extracts the duplicated file I/O, manifest, backup, diff,
install, and uninstall logic that is identical across kit installers.
Kit-specific behaviour (settings merge, AGENTS.md markers, binary checks)
stays in the individual kit modules.
"""

from __future__ import annotations

import difflib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

MANIFEST_FILE = ".vibe-engineering-manifest.json"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def backup(path: Path, backup_base_dir: Path) -> Path | None:
    if not path.exists():
        return None
    rel = path.relative_to(backup_base_dir)
    backup_path = backup_base_dir / "backups" / "vibe-engineering" / timestamp() / rel
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup_path)
    return backup_path


def load_manifest(template_dir: Path) -> dict:
    with (template_dir / "manifest.json").open("r", encoding="utf-8") as fh:
        return json.load(fh)


def target_files(template_dir: Path, target_dir: Path, manifest: dict) -> list[tuple[Path, Path, str]]:
    files: list[tuple[Path, Path, str]] = []
    for rel in manifest["managed_files"]:
        files.append((template_dir / rel, target_dir / rel, rel))
    return files


def manifest_state(kit_name: str, managed_files: Iterable[str]) -> dict:
    return {
        "tool": "vibe-engineering",
        "kit": kit_name,
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "managed_files": sorted(managed_files),
        "notes": "Only files listed here are managed by vibe. Uninstall removes unchanged managed files and leaves modified files in place.",
    }


def load_existing_install_manifest(manifest_path: Path) -> dict | None:
    if not manifest_path.exists():
        return None
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def confirm(prompt: str, yes: bool) -> bool:
    if yes:
        return True
    answer = input(f"{prompt} [y/N] ").strip().lower()
    return answer in {"y", "yes"}


def planned_changes_copy_style(target_files_list: list[tuple[Path, Path, str]]) -> list[str]:
    """Return planned-change descriptions for copy-style managed files."""
    changes: list[str] = []
    for src, dst, rel in target_files_list:
        if not dst.exists():
            changes.append(f"create {rel}")
        elif read_text(src) != read_text(dst):
            changes.append(f"update {rel}")
        else:
            changes.append(f"unchanged {rel}")
    return changes


def install_copy_style_file(src: Path, dst: Path, backup_base_dir: Path) -> bool:
    """Install a copy-style managed file.

    Returns *True* when the file was written or updated, *False* when it was
    already identical and left untouched.
    """
    content = read_text(src)
    if dst.exists() and read_text(dst) == content:
        return False
    if dst.exists():
        backup(dst, backup_base_dir)
    write_text(dst, content)
    return True


def uninstall_unchanged_file(src: Path, dst: Path) -> bool:
    """Remove a copy-style managed file if it is still identical to the template.

    Returns *True* when the file was removed, *False* when it was kept
    (either because it does not exist or because it was modified).
    """
    if not dst.exists():
        return False
    if src.exists() and read_text(src) == read_text(dst):
        dst.unlink()
        return True
    return False


def diff_copy_style(src: Path, dst: Path, rel: str) -> bool:
    """Print a unified diff for a copy-style managed file.

    Returns *True* when the files differ, *False* when they are identical.
    """
    src_text = read_text(src).splitlines(keepends=True)
    dst_text = read_text(dst).splitlines(keepends=True) if dst.exists() else []
    if src_text == dst_text:
        return False
    print(f"--- {rel} (installed)")
    print(f"+++ {rel} (kit)")
    print("".join(difflib.unified_diff(dst_text, src_text, fromfile=f"installed/{rel}", tofile=f"kit/{rel}")), end="")
    return True
