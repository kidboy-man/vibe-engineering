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
import subprocess
from dataclasses import dataclass
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
    if backup_path.exists():
        return backup_path
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


def resolve_home(home: str | None) -> Path:
    return Path(home).expanduser() if home else Path.home()


def prune_empty_dirs(*dirs: Path) -> None:
    """rmdir each dir in order (deepest first), stopping at the first missing or non-empty one."""
    for directory in dirs:
        try:
            directory.rmdir()
        except OSError:
            return


def confirm(prompt: str, yes: bool) -> bool:
    """Ask y/N; non-interactive stdin (EOF) counts as no."""
    if yes:
        return True
    try:
        answer = input(f"{prompt} [y/N] ").strip().lower()
    except EOFError:
        return False
    return answer in {"y", "yes"}


def report_binary(binary: str, missing_message: str) -> bool:
    """Print where *binary* lives and its version; return False when unusable."""
    found = shutil.which(binary)
    if not found:
        print(missing_message)
        return False
    print(f"{binary}: {found}")
    try:
        result = subprocess.run([found, "--version"], check=False, text=True, capture_output=True, timeout=10)
    except Exception as exc:  # pragma: no cover - environment dependent
        print(f"{binary} version check failed: {exc}")
        return False
    print(f"{binary} version: {(result.stdout or result.stderr).strip()}")
    return True


def report_manifest(manifest: dict | None) -> None:
    if manifest:
        print(f"manifest: installed kit={manifest.get('kit')} files={len(manifest.get('managed_files', []))}")
    else:
        print("manifest: not installed")


@dataclass(frozen=True)
class Change:
    """One planned action on a copy-style managed file."""

    kind: str  # "create" | "update" | "unchanged"
    rel: str
    src: Path
    dst: Path

    def describe(self) -> str:
        return f"{self.kind} {self.rel}"


def plan_copy_files(target_files_list: list[tuple[Path, Path, str]]) -> list[Change]:
    """Classify each managed file against what is installed. Reads only; never writes."""
    plan: list[Change] = []
    for src, dst, rel in target_files_list:
        if not dst.exists():
            kind = "create"
        elif read_text(src) != read_text(dst):
            kind = "update"
        else:
            kind = "unchanged"
        plan.append(Change(kind, rel, src, dst))
    return plan


def planned_changes_copy_style(target_files_list: list[tuple[Path, Path, str]]) -> list[str]:
    """Return planned-change descriptions for copy-style managed files."""
    return [change.describe() for change in plan_copy_files(target_files_list)]


def apply_copy_plan(plan: list[Change], backup_base_dir: Path) -> None:
    """Execute a plan from plan_copy_files: back up then overwrite updates, create the rest."""
    for change in plan:
        if change.kind == "unchanged":
            continue
        if change.kind == "update":
            backup(change.dst, backup_base_dir)
        write_text(change.dst, read_text(change.src))
        print(f"installed {change.rel}")


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


@dataclass(frozen=True)
class CopyKit:
    """Declarative description of a kit that only copies managed files."""

    kit_name: str
    label: str  # human name used in prompts, e.g. "Codex CLI"
    template_dir: Path
    target_subdir: str  # directory under home, e.g. ".codex"
    binary: str
    missing_binary_message: str
    missing_binary_is_failure: bool = True
    ensure_subdir: str = ""  # created on install (relative to the target dir)
    extra_doctor_dirs: tuple[tuple[str, str], ...] = ()  # (label, subdir) lines
    doctor_footer: str | None = None


def _copy_kit_files(kit: CopyKit, home: str | None) -> tuple[Path, Path, list[tuple[Path, Path, str]]]:
    home_path = resolve_home(home)
    target_dir = home_path / kit.target_subdir
    files = target_files(kit.template_dir, target_dir, load_manifest(kit.template_dir))
    return home_path, target_dir, files


def copy_kit_install(kit: CopyKit, home: str | None = None, dry_run: bool = False, yes: bool = False) -> int:
    _home, target_dir, files = _copy_kit_files(kit, home)
    plan = plan_copy_files(files)
    for change in [*(c.describe() for c in plan), f"write {MANIFEST_FILE}"]:
        print(change)
    if dry_run:
        print("dry run: no files written")
        return 0
    if not confirm(f"Install/update the {kit.label} kit?", yes=yes):
        print("aborted")
        return 1

    (target_dir / kit.ensure_subdir).mkdir(parents=True, exist_ok=True)
    apply_copy_plan(plan, target_dir)

    manifest_path = target_dir / MANIFEST_FILE
    managed = [change.rel for change in plan]
    write_text(manifest_path, json.dumps(manifest_state(kit.kit_name, managed), indent=2) + "\n")
    print(f"wrote {manifest_path}")
    return 0


def copy_kit_diff(kit: CopyKit, home: str | None = None) -> int:
    _home, _target, files = _copy_kit_files(kit, home)
    pending = [change for change in plan_copy_files(files) if change.kind != "unchanged"]
    for change in pending:
        diff_copy_style(change.src, change.dst, change.rel)
    if not pending:
        print("managed files match kit templates")
    return 0


def copy_kit_doctor(kit: CopyKit, home: str | None = None) -> int:
    home_path, target_dir, files = _copy_kit_files(kit, home)
    print(f"home: {home_path}")
    print(f"{kit.kit_name} dir: {target_dir}")
    for label, subdir in kit.extra_doctor_dirs:
        print(f"{label}: {target_dir / subdir}")
    binary_ok = report_binary(kit.binary, kit.missing_binary_message)
    ok = binary_ok or not kit.missing_binary_is_failure

    report_manifest(load_existing_install_manifest(target_dir / MANIFEST_FILE))

    missing_templates = [rel for src, _dst, rel in files if not src.exists()]
    if missing_templates:
        ok = False
        for rel in missing_templates:
            print(f"missing template: {rel}")
    else:
        print("templates: ok")
    if kit.doctor_footer:
        print(kit.doctor_footer)
    return 0 if ok else 1


def copy_kit_uninstall(kit: CopyKit, home: str | None = None, dry_run: bool = False, yes: bool = False) -> int:
    _home, target_dir, _files = _copy_kit_files(kit, home)
    manifest_path = target_dir / MANIFEST_FILE
    manifest = load_existing_install_manifest(manifest_path)
    if not manifest:
        print(f"no {MANIFEST_FILE} found; nothing to uninstall")
        return 0
    rels = manifest.get("managed_files", [])
    for rel in rels:
        print(f"remove if unchanged {rel}")
    print(f"remove {MANIFEST_FILE}")
    if dry_run:
        print("dry run: no files removed")
        return 0
    if not confirm(f"Uninstall managed {kit.label} kit files?", yes=yes):
        print("aborted")
        return 1

    removed = 0
    for rel in rels:
        src = kit.template_dir / rel
        dst = target_dir / rel
        if not dst.exists():
            continue
        if uninstall_unchanged_file(src, dst):
            removed += 1
            print(f"removed {rel}")
        else:
            print(f"kept modified file {rel}")
    if manifest_path.exists():
        manifest_path.unlink()
    print(f"removed {removed} files")
    return 0
