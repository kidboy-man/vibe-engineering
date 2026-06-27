"""Safe installer for the portable Codex CLI kit.

Manages only portable files: instructions.md with embedded engineering persona,
rules, and specialist role descriptions. Never copies API keys, auth tokens, or
machine-specific configuration.
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
KIT_NAME = "codex"


@dataclass(frozen=True)
class KitPaths:
    home: Path
    codex_dir: Path
    manifest_path: Path
    template_dir: Path


def _template_dir() -> Path:
    return Path(__file__).resolve().parent / "templates" / "codex"


def _paths(home: str | None = None) -> KitPaths:
    home_path = Path(home).expanduser() if home else Path.home()
    codex_dir = home_path / ".codex"
    return KitPaths(
        home=home_path,
        codex_dir=codex_dir,
        manifest_path=codex_dir / MANIFEST_FILE,
        template_dir=_template_dir(),
    )


def _load_manifest(paths: KitPaths) -> dict:
    return core.load_manifest(paths.template_dir)


def _target_files(paths: KitPaths) -> list[tuple[Path, Path, str]]:
    manifest = _load_manifest(paths)
    return core.target_files(paths.template_dir, paths.codex_dir, manifest)


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
    if not _confirm("Install/update the Codex CLI kit?", yes=yes):
        print("aborted")
        return 1

    paths.codex_dir.mkdir(parents=True, exist_ok=True)
    managed: list[str] = []
    for src, dst, rel in _target_files(paths):
        managed.append(rel)
        if core.install_copy_style_file(src, dst, paths.codex_dir):
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
    print(f"codex dir: {paths.codex_dir}")
    codex_bin = shutil.which("codex")
    if codex_bin:
        print(f"codex: {codex_bin}")
        try:
            result = subprocess.run(
                [codex_bin, "--version"],
                check=False,
                text=True,
                capture_output=True,
                timeout=10,
            )
            print(f"codex version: {(result.stdout or result.stderr).strip()}")
        except Exception as exc:  # pragma: no cover - environment dependent
            print(f"codex version check failed: {exc}")
            ok = False
    else:
        print("codex: not found (install the OpenAI Codex CLI)")
        ok = False

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
    if not _confirm("Uninstall managed Codex CLI kit files?", yes=yes):
        print("aborted")
        return 1

    removed = 0
    for rel in files:
        src = paths.template_dir / rel
        dst = paths.codex_dir / rel
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
