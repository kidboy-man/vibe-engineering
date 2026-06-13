"""Safe installer for the portable Claude Code kit.

The installer intentionally manages only portable files: CLAUDE.md, rules,
agents, commands, selected skills, and a tiny non-secret settings fragment.
It never copies credentials, auth tokens, router/proxy configuration, histories,
caches, backups, project transcripts, or local machine state.
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
KIT_NAME = "claude-code"
SECRET_SETTING_KEYS = {
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
}


@dataclass(frozen=True)
class KitPaths:
    home: Path
    claude_dir: Path
    manifest_path: Path
    template_dir: Path


def _template_dir() -> Path:
    return Path(__file__).resolve().parent / "templates" / "claude"


def _paths(home: str | None = None) -> KitPaths:
    home_path = Path(home).expanduser() if home else Path.home()
    claude_dir = home_path / ".claude"
    return KitPaths(
        home=home_path,
        claude_dir=claude_dir,
        manifest_path=claude_dir / MANIFEST_FILE,
        template_dir=_template_dir(),
    )


def _load_manifest(paths: KitPaths) -> dict:
    return core.load_manifest(paths.template_dir)


def _target_files(paths: KitPaths) -> list[tuple[Path, Path, str]]:
    manifest = _load_manifest(paths)
    return core.target_files(paths.template_dir, paths.claude_dir, manifest)


def _read_text(path: Path) -> str:
    return core.read_text(path)


def _write_text(path: Path, content: str) -> None:
    core.write_text(path, content)


def _backup(path: Path, paths: KitPaths) -> Path | None:
    return core.backup(path, paths.claude_dir)


def _manifest_state(paths: KitPaths, managed_files: Iterable[str]) -> dict:
    return core.manifest_state(KIT_NAME, managed_files)


def _load_existing_install_manifest(paths: KitPaths) -> dict | None:
    return core.load_existing_install_manifest(paths.manifest_path)


def _merge_settings(paths: KitPaths, dry_run: bool) -> tuple[str, bool]:
    from agents.merge_strategies import json_defaults_strategy

    fragment_path = paths.template_dir / "settings.fragment.json"
    fragment = json.loads(fragment_path.read_text(encoding="utf-8"))
    settings_path = paths.claude_dir / "settings.json"
    current: dict = {}
    if settings_path.exists():
        current = json.loads(settings_path.read_text(encoding="utf-8"))

    # Never write portable env/proxy/token settings. Preserve any existing local env as-is.
    fragment.pop("env", None)
    merged, changed = json_defaults_strategy(fragment, current, SECRET_SETTING_KEYS)

    if not changed:
        return "settings.json unchanged", False

    if not dry_run:
        _backup(settings_path, paths)
        _write_text(settings_path, json.dumps(merged, indent=2, sort_keys=True) + "\n")
    return "settings.json merged safe non-secret defaults", True


def _confirm(prompt: str, yes: bool) -> bool:
    return core.confirm(prompt, yes)


def _planned_changes(paths: KitPaths) -> list[str]:
    changes = core.planned_changes_copy_style(_target_files(paths))
    changes.append("merge settings.json safe fragment")
    changes.append(f"write {MANIFEST_FILE}")
    return changes


def install(home: str | None = None, dry_run: bool = False, yes: bool = False, merge_settings: bool = True) -> int:
    paths = _paths(home)

    # Validate existing settings.json before any operations so we abort safely
    # without partial writes.
    settings_path = paths.claude_dir / "settings.json"
    if settings_path.exists():
        try:
            json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print("invalid settings.json")
            return 1

    changes = _planned_changes(paths)
    for change in changes:
        print(change)
    if dry_run:
        print("dry run: no files written")
        return 0
    if not _confirm("Install/update the Claude Code kit?", yes=yes):
        print("aborted")
        return 1

    paths.claude_dir.mkdir(parents=True, exist_ok=True)
    managed: list[str] = []
    for src, dst, rel in _target_files(paths):
        managed.append(rel)
        if core.install_copy_style_file(src, dst, paths.claude_dir):
            print(f"installed {rel}")

    if merge_settings:
        message, changed = _merge_settings(paths, dry_run=False)
        print(message)
        if changed:
            managed.append("settings.json")

    _write_text(paths.manifest_path, json.dumps(_manifest_state(paths, managed), indent=2) + "\n")
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
    print(f"claude dir: {paths.claude_dir}")
    claude = shutil.which("claude")
    if claude:
        print(f"claude: {claude}")
        try:
            result = subprocess.run([claude, "--version"], check=False, text=True, capture_output=True, timeout=10)
            print(f"claude version: {(result.stdout or result.stderr).strip()}")
        except Exception as exc:  # pragma: no cover - environment dependent
            print(f"claude version check failed: {exc}")
            ok = False
    else:
        print("claude: missing (install with: npm install -g @anthropic-ai/claude-code)")
        ok = False

    manifest = _load_existing_install_manifest(paths)
    if manifest:
        print(f"manifest: installed kit={manifest.get('kit')} files={len(manifest.get('managed_files', []))}")
    else:
        print("manifest: not installed")

    missing_templates = [rel for src, _dst, rel in _target_files(paths) if not src.exists()]
    if missing_templates:
        ok = False
        print("missing templates:")
        for rel in missing_templates:
            print(f"  {rel}")
    else:
        print("templates: ok")

    settings_path = paths.claude_dir / "settings.json"
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            env = settings.get("env", {}) if isinstance(settings, dict) else {}
            secretish = sorted(k for k in env if k in SECRET_SETTING_KEYS or "TOKEN" in k or "KEY" in k)
            if secretish:
                print(f"settings env: preserved local-only keys present ({', '.join(secretish)}); kit will not overwrite them")
            else:
                print("settings env: no known secret/proxy keys")
        except json.JSONDecodeError:
            print("settings.json: invalid JSON")
            ok = False
    else:
        print("settings.json: absent")

    return 0 if ok else 1


def uninstall(home: str | None = None, dry_run: bool = False, yes: bool = False) -> int:
    paths = _paths(home)
    manifest = _load_existing_install_manifest(paths)
    if not manifest:
        print(f"no {MANIFEST_FILE} found; nothing to uninstall")
        return 0
    files = [rel for rel in manifest.get("managed_files", []) if rel != "settings.json"]
    for rel in files:
        print(f"remove if unchanged {rel}")
    print(f"remove {MANIFEST_FILE}")
    if dry_run:
        print("dry run: no files removed")
        return 0
    if not _confirm("Uninstall managed Claude Code kit files?", yes=yes):
        print("aborted")
        return 1

    removed = 0
    for rel in files:
        src = paths.template_dir / rel
        dst = paths.claude_dir / rel
        if not dst.exists():
            continue
        if core.uninstall_unchanged_file(src, dst):
            removed += 1
            print(f"removed {rel}")
        else:
            print(f"kept modified file {rel}")
    if paths.manifest_path.exists():
        paths.manifest_path.unlink()
    print(f"removed {removed} files; settings.json was preserved")
    return 0
