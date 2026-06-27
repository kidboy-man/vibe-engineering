"""Safe installer for the portable OpenCode kit.

The installer intentionally manages only portable files: AGENTS.md, rules,
agents, commands, selected skills, and a tiny non-secret opencode.jsonc fragment.
It never copies credentials, auth tokens, plugin/MCP config, histories,
caches, backups, project transcripts, or local machine state.
"""

from __future__ import annotations

import difflib
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from agents import installer_core as core
from agents.secret_policies import LOCAL_ONLY_KEYS, SECRET_KEY_SUBSTRINGS, is_secret_key

MANIFEST_FILE = core.MANIFEST_FILE
KIT_NAME = "opencode"

# Markers used to delimit the persona section injected into a pre-existing
# AGENTS.md. Re-installs replace only the content between the markers; the
# user's own content is preserved untouched.
AGENTS_BEGIN_MARKER = "<!-- vibe-engineering-kit:begin -->\n"
AGENTS_END_MARKER = "<!-- vibe-engineering-kit:end -->\n"
AGENTS_MD = "AGENTS.md"

def _xdg_config_home() -> Path:
    env = os.environ.get("XDG_CONFIG_HOME")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".config"


def _template_dir() -> Path:
    return Path(__file__).resolve().parent / "templates" / "opencode"


@dataclass(frozen=True)
class KitPaths:
    home: Path
    config_dir: Path
    manifest_path: Path
    template_dir: Path


def _paths(home: str | None = None) -> KitPaths:
    base = Path(home).expanduser() if home else _xdg_config_home()
    config_dir = base / "opencode"
    return KitPaths(
        home=base,
        config_dir=config_dir,
        manifest_path=config_dir / MANIFEST_FILE,
        template_dir=_template_dir(),
    )


def _load_manifest(paths: KitPaths) -> dict:
    return core.load_manifest(paths.template_dir)


def _target_files(paths: KitPaths) -> list[tuple[Path, Path, str]]:
    manifest = _load_manifest(paths)
    return core.target_files(paths.template_dir, paths.config_dir, manifest)


def _read_text(path: Path) -> str:
    return core.read_text(path)


def _write_text(path: Path, content: str) -> None:
    core.write_text(path, content)


def _backup(path: Path, paths: KitPaths) -> Path | None:
    return core.backup(path, paths.config_dir)


def _merge_agents_md(template: str, existing: str | None) -> tuple[str, str]:
    from agents.merge_strategies import marked_section_strategy
    return marked_section_strategy(template, existing, AGENTS_BEGIN_MARKER, AGENTS_END_MARKER)


def _strip_agents_md_section(existing: str) -> tuple[str | None, bool]:
    from agents.merge_strategies import strip_marked_section
    return strip_marked_section(existing, AGENTS_BEGIN_MARKER, AGENTS_END_MARKER)


def _manifest_state(paths: KitPaths, managed_files: Iterable[str]) -> dict:
    return core.manifest_state(KIT_NAME, managed_files)


def _load_existing_install_manifest(paths: KitPaths) -> dict | None:
    return core.load_existing_install_manifest(paths.manifest_path)


def _parse_jsonc(text: str) -> dict:
    from agents.merge_strategies import parse_jsonc
    return parse_jsonc(text)


def _merge_settings(paths: KitPaths, dry_run: bool) -> tuple[str, bool]:
    from agents.merge_strategies import jsonc_defaults_strategy, parse_jsonc

    fragment_path = paths.template_dir / "opencode.fragment.jsonc"
    fragment_text = _read_text(fragment_path)
    fragment = parse_jsonc(fragment_text)

    # The fragment is JSONC with possible comments. Strip them before we use
    # the parsed dict (we only read keys from it).
    settings_path = paths.config_dir / "opencode.jsonc"
    current: dict = {}
    if settings_path.exists():
        current = parse_jsonc(_read_text(settings_path))

    merged, changed = jsonc_defaults_strategy(fragment, current, LOCAL_ONLY_KEYS, is_secret_key)

    if not changed:
        return "opencode.jsonc unchanged", False

    if not dry_run:
        _backup(settings_path, paths)
        # Write as JSON. JSONC comments in the original are not preserved
        # when we add a key, but the values are preserved verbatim and the
        # structure remains valid for OpenCode (which accepts both .json and
        # .jsonc).
        _write_text(settings_path, json.dumps(merged, indent=2, sort_keys=True) + "\n")
    return "opencode.jsonc merged safe non-secret defaults", True


def _confirm(prompt: str, yes: bool) -> bool:
    return core.confirm(prompt, yes)


def _planned_changes(paths: KitPaths) -> list[str]:
    changes: list[str] = []
    for src, dst, rel in _target_files(paths):
        if rel == AGENTS_MD:
            template = _read_text(src)
            existing = _read_text(dst) if dst.exists() else None
            _, action = _merge_agents_md(template, existing)
            changes.append(f"{action} {rel}")
            continue
        if not dst.exists():
            changes.append(f"create {rel}")
        elif _read_text(src) != _read_text(dst):
            changes.append(f"update {rel}")
        else:
            changes.append(f"unchanged {rel}")
    changes.append("merge opencode.jsonc safe fragment")
    changes.append(f"write {MANIFEST_FILE}")
    return changes


def install(home: str | None = None, dry_run: bool = False, yes: bool = False, merge_settings: bool = True, **kwargs) -> int:
    paths = _paths(home)

    # Validate existing opencode.jsonc before any operations so we abort safely
    # without partial writes.
    settings_path = paths.config_dir / "opencode.jsonc"
    if settings_path.exists():
        try:
            _parse_jsonc(_read_text(settings_path))
        except (json.JSONDecodeError, ValueError):
            print("invalid opencode.jsonc")
            return 1

    changes = _planned_changes(paths)
    for change in changes:
        print(change)
    if dry_run:
        print("dry run: no files written")
        return 0
    if not _confirm("Install/update the OpenCode kit?", yes=yes):
        print("aborted")
        return 1

    paths.config_dir.mkdir(parents=True, exist_ok=True)
    managed: list[str] = []
    for src, dst, rel in _target_files(paths):
        if rel == AGENTS_MD:
            template = _read_text(src)
            existing = _read_text(dst) if dst.exists() else None
            merged, action = _merge_agents_md(template, existing)
            if action == "unchanged":
                managed.append(rel)
                continue
            if action == "merge" and dst.exists():
                _backup(dst, paths)
            _write_text(dst, merged)
            managed.append(rel)
            print(f"{action} {rel}")
            continue

        managed.append(rel)
        if core.install_copy_style_file(src, dst, paths.config_dir):
            print(f"installed {rel}")

    if merge_settings:
        message, changed = _merge_settings(paths, dry_run=False)
        print(message)
        if changed:
            managed.append("opencode.jsonc")

    _write_text(paths.manifest_path, json.dumps(_manifest_state(paths, managed), indent=2) + "\n")
    print(f"wrote {paths.manifest_path}")
    return 0


def diff_kit(home: str | None = None) -> int:
    paths = _paths(home)
    any_diff = False
    for src, dst, rel in _target_files(paths):
        if rel == AGENTS_MD:
            template = _read_text(src)
            existing = _read_text(dst) if dst.exists() else None
            merged, _ = _merge_agents_md(template, existing)
            if existing is not None and merged == existing:
                continue
            any_diff = True
            print(f"--- {rel} (installed)")
            print(f"+++ {rel} (kit merge result)")
            dst_lines = existing.splitlines(keepends=True) if existing is not None else []
            merged_lines = merged.splitlines(keepends=True)
            print("".join(difflib.unified_diff(dst_lines, merged_lines, fromfile=f"installed/{rel}", tofile=f"kit-merged/{rel}")), end="")
            continue
        if core.diff_copy_style(src, dst, rel):
            any_diff = True
    if not any_diff:
        print("managed files match kit templates")
    return 0


def doctor(home: str | None = None) -> int:
    paths = _paths(home)
    ok = True
    print(f"config base: {paths.home}")
    print(f"opencode dir: {paths.config_dir}")
    opencode = shutil.which("opencode")
    if opencode:
        print(f"opencode: {opencode}")
        try:
            result = subprocess.run([opencode, "--version"], check=False, text=True, capture_output=True, timeout=10)
            print(f"opencode version: {(result.stdout or result.stderr).strip()}")
        except Exception as exc:  # pragma: no cover - environment dependent
            print(f"opencode version check failed: {exc}")
            ok = False
    else:
        print("opencode: missing (install with: curl -fsSL https://opencode.ai/install | bash)")
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

    settings_path = paths.config_dir / "opencode.jsonc"
    if settings_path.exists():
        try:
            settings = _parse_jsonc(_read_text(settings_path))
            local_only = sorted(k for k in settings if k in LOCAL_ONLY_KEYS)
            secretish = sorted(k for k in settings if is_secret_key(k))
            if local_only or secretish:
                preserved = ", ".join(local_only + secretish)
                print(f"opencode.jsonc: preserved local-only / secret-ish keys ({preserved}); kit will not overwrite them")
            else:
                print("opencode.jsonc: no known local-only or secret keys")
        except (json.JSONDecodeError, ValueError) as exc:
            print(f"opencode.jsonc: invalid JSONC ({exc})")
            ok = False
    else:
        print("opencode.jsonc: absent")

    return 0 if ok else 1


def uninstall(home: str | None = None, dry_run: bool = False, yes: bool = False) -> int:
    paths = _paths(home)
    manifest = _load_existing_install_manifest(paths)
    if not manifest:
        print(f"no {MANIFEST_FILE} found; nothing to uninstall")
        return 0
    files = [rel for rel in manifest.get("managed_files", []) if rel != "opencode.jsonc"]
    for rel in files:
        if rel == AGENTS_MD:
            print(f"strip {rel} persona section (keeps user content)")
        else:
            print(f"remove if unchanged {rel}")
    print(f"remove {MANIFEST_FILE}")
    if dry_run:
        print("dry run: no files removed")
        return 0
    if not _confirm("Uninstall managed OpenCode kit files?", yes=yes):
        print("aborted")
        return 1

    removed = 0
    for rel in files:
        src = paths.template_dir / rel
        dst = paths.config_dir / rel
        if not dst.exists():
            continue
        if rel == AGENTS_MD:
            existing = _read_text(dst)
            remaining, fully_owned = _strip_agents_md_section(existing)
            if fully_owned:
                dst.unlink()
                removed += 1
                print(f"removed {rel} (was entirely kit content)")
            elif remaining is not None and remaining != existing:
                _write_text(dst, remaining)
                removed += 1
                print(f"stripped {rel} persona section; user content kept")
            else:
                print(f"kept {rel} (no kit section to strip)")
            continue
        if core.uninstall_unchanged_file(src, dst):
            removed += 1
            print(f"removed {rel}")
        else:
            print(f"kept modified file {rel}")
    if paths.manifest_path.exists():
        paths.manifest_path.unlink()
    print(f"removed {removed} files; opencode.jsonc was preserved")
    return 0
