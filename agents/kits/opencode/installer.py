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
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

MANIFEST_FILE = ".vibe-engineering-manifest.json"
KIT_NAME = "opencode"

# Markers used to delimit the persona section injected into a pre-existing
# AGENTS.md. Re-installs replace only the content between the markers; the
# user's own content is preserved untouched.
AGENTS_BEGIN_MARKER = "<!-- vibe-engineering-kit:begin -->\n"
AGENTS_END_MARKER = "<!-- vibe-engineering-kit:end -->\n"
AGENTS_MD = "AGENTS.md"

# Top-level opencode.jsonc keys the kit will NEVER overwrite. These are
# machine/account-specific by design (model selection, MCP servers, plugin
# list, environment, tool permissions, etc.).
LOCAL_ONLY_KEYS = {
    "model",
    "provider",
    "plugin",
    "mcp",
    "tools",
    "tool",
    "permission",
    "env",
    "agent",
    "experimental",
    "theme",
    "share",
    "autoupdate",
    "instructions",
}

# Substrings that, if found in any top-level key, mark it as a secret
# and force the installer to leave it alone.
SECRET_KEY_SUBSTRINGS = ("token", "key", "secret", "password", "auth", "credential")


def _is_secret_key(name: str) -> bool:
    lowered = name.lower()
    return any(sub in lowered for sub in SECRET_KEY_SUBSTRINGS)


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
    with (paths.template_dir / "manifest.json").open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _target_files(paths: KitPaths) -> list[tuple[Path, Path, str]]:
    manifest = _load_manifest(paths)
    files: list[tuple[Path, Path, str]] = []
    for rel in manifest["managed_files"]:
        files.append((paths.template_dir / rel, paths.config_dir / rel, rel))
    return files


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _backup(path: Path, paths: KitPaths) -> Path | None:
    if not path.exists():
        return None
    rel = path.relative_to(paths.config_dir)
    backup_path = paths.config_dir / "backups" / "vibe-engineering" / _timestamp() / rel
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup_path)
    return backup_path


def _merge_agents_md(template: str, existing: str | None) -> tuple[str, str]:
    """Return (merged_content, action) for AGENTS.md install.

    The template is always wrapped in begin/end markers before being written
    to disk so that the on-disk format is uniform across fresh installs and
    re-installs, and so uninstall can always strip the marked section.

    Actions:
      - 'create': file did not exist; the merged content equals the wrapped template.
      - 'merge':  file existed and the merged content differs from existing.
      - 'unchanged': file existed and the merged content equals existing.

    Merge rules:
      - Existing markers present: replace content between them; keep before
        and after verbatim.
      - No existing markers: prepend the marked section; keep the user's
        existing content untouched below the markers.
    """
    wrapped = AGENTS_BEGIN_MARKER + template + AGENTS_END_MARKER
    if existing is None:
        return wrapped, "create"
    if AGENTS_BEGIN_MARKER in existing and AGENTS_END_MARKER in existing:
        before, _, rest = existing.partition(AGENTS_BEGIN_MARKER)
        _, _, after = rest.partition(AGENTS_END_MARKER)
        merged = before + AGENTS_BEGIN_MARKER + template + AGENTS_END_MARKER + after
    else:
        merged = wrapped + existing
    if merged == existing:
        return merged, "unchanged"
    return merged, "merge"


def _strip_agents_md_section(existing: str) -> tuple[str | None, bool]:
    """Return (remaining_content, fully_owned).

    - remaining_content: file with our section removed (None if file should be
      deleted entirely).
    - fully_owned: True if the entire file was our injected section (i.e. the
      caller can safely delete the file). False if user content remains.
    """
    if AGENTS_BEGIN_MARKER not in existing or AGENTS_END_MARKER not in existing:
        return existing, False
    before, _, rest = existing.partition(AGENTS_BEGIN_MARKER)
    _, _, after = rest.partition(AGENTS_END_MARKER)
    remaining = (before + after).strip()
    if not remaining:
        return None, True
    if not remaining.endswith("\n"):
        remaining += "\n"
    return remaining, False


def _manifest_state(paths: KitPaths, managed_files: Iterable[str]) -> dict:
    return {
        "tool": "vibe-engineering",
        "kit": KIT_NAME,
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "managed_files": sorted(managed_files),
        "notes": "Only files listed here are managed by vibe. Uninstall removes unchanged managed files and leaves modified files in place.",
    }


def _load_existing_install_manifest(paths: KitPaths) -> dict | None:
    if not paths.manifest_path.exists():
        return None
    try:
        return json.loads(paths.manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _strip_jsonc_comments(text: str) -> str:
    """Strip // and /* */ comments and trailing commas from a JSONC text.

    This is intentionally minimal — it handles the common cases produced by
    OpenCode's own config examples. It does not handle comments inside strings
    containing '//' or '/*' as literal content; OpenCode config does not
    produce such cases.
    """
    out: list[str] = []
    i = 0
    n = len(text)
    in_string = False
    string_quote = ""
    while i < n:
        ch = text[i]
        if in_string:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == string_quote:
                in_string = False
            i += 1
            continue
        if ch in ("'", '"'):
            in_string = True
            string_quote = ch
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            # line comment
            while i < n and text[i] != "\n":
                i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            # block comment
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(ch)
        i += 1
    cleaned = "".join(out)
    # Remove trailing commas before } or ]
    cleaned = re.sub(r",(\s*[}\]])", r"\1", cleaned)
    return cleaned


def _parse_jsonc(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return json.loads(_strip_jsonc_comments(text))


def _merge_settings(paths: KitPaths, dry_run: bool) -> tuple[str, bool]:
    fragment_path = paths.template_dir / "opencode.fragment.jsonc"
    fragment_text = _read_text(fragment_path)
    fragment = _parse_jsonc(fragment_text)

    # The fragment is JSONC with possible comments. Strip them before we use
    # the parsed dict (we only read keys from it).
    settings_path = paths.config_dir / "opencode.jsonc"
    current: dict = {}
    if settings_path.exists():
        current = _parse_jsonc(_read_text(settings_path))

    # Never write portable local-only or secret keys. Preserve any existing
    # local config as-is.
    safe_fragment: dict = {}
    for key, value in fragment.items():
        if key in LOCAL_ONLY_KEYS:
            continue
        if _is_secret_key(key):
            continue
        safe_fragment[key] = value

    changed = False
    merged = dict(current)
    for key, value in safe_fragment.items():
        if key not in merged:
            merged[key] = value
            changed = True

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
    if yes:
        return True
    answer = input(f"{prompt} [y/N] ").strip().lower()
    return answer in {"y", "yes"}


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


def install(home: str | None = None, dry_run: bool = False, yes: bool = False, merge_settings: bool = True) -> int:
    paths = _paths(home)
    paths.config_dir.mkdir(parents=True, exist_ok=True)
    changes = _planned_changes(paths)
    for change in changes:
        print(change)
    if dry_run:
        print("dry run: no files written")
        return 0
    if not _confirm("Install/update the OpenCode kit?", yes=yes):
        print("aborted")
        return 1

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
        content = _read_text(src)
        if dst.exists() and _read_text(dst) == content:
            continue
        if dst.exists():
            _backup(dst, paths)
        _write_text(dst, content)
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
        src_text = _read_text(src).splitlines(keepends=True)
        dst_text = _read_text(dst).splitlines(keepends=True) if dst.exists() else []
        if src_text == dst_text:
            continue
        any_diff = True
        print(f"--- {rel} (installed)")
        print(f"+++ {rel} (kit)")
        print("".join(difflib.unified_diff(dst_text, src_text, fromfile=f"installed/{rel}", tofile=f"kit/{rel}")), end="")
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
            secretish = sorted(k for k in settings if _is_secret_key(k))
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
        if src.exists() and _read_text(src) == _read_text(dst):
            dst.unlink()
            removed += 1
            print(f"removed {rel}")
        else:
            print(f"kept modified file {rel}")
    if paths.manifest_path.exists():
        paths.manifest_path.unlink()
    print(f"removed {removed} files; opencode.jsonc was preserved")
    return 0
