"""Safe installer for the workflow kit.

Installs the business-requirement-to-TDD flow (``/prd``, ``/flow``, ``/implement-ticket``,
``/push-tickets`` and the ``vibe-flow`` skill with its ``check_trace.py`` validator) into the
Claude Code and OpenCode config dirs, each only if it already exists.

Templates live in ``templates/workflow/{claude,opencode}/`` (target-specific prose) and
``templates/workflow/shared/`` (files identical for every target). A file listed in
``manifest.json`` is taken from the target's own directory when present, else from ``shared``.

``/trd`` and the ``vibe-engineering`` skill belong to the claude-code and opencode kits; this
kit chains them, and ``doctor`` warns when they are missing.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from agents import installer_core as core

MANIFEST_FILE = core.MANIFEST_FILE
KIT_NAME = "workflow"
TARGETS = [("claude", "Claude Code"), ("opencode", "OpenCode")]
# Owned by the claude-code / opencode kits; the flow chains them.
UPSTREAM = [
    ("commands/trd.md", "/trd command"),
    ("skills/vibe-engineering/SKILL.md", "vibe-engineering skill"),
]


@dataclass(frozen=True)
class KitPaths:
    manifest_dir: Path
    manifest_path: Path
    template_dir: Path
    agent_dirs: dict[str, Path]


def _template_dir() -> Path:
    return Path(__file__).resolve().parent / "templates" / "workflow"


def _paths(home: str | None = None) -> KitPaths:
    if home:
        base = Path(home).expanduser()
        agent_dirs = {"claude": base / ".claude", "opencode": base / "opencode"}
    else:
        base = Path.home()
        xdg = os.environ.get("XDG_CONFIG_HOME")
        agent_dirs = {
            "claude": base / ".claude",
            "opencode": (Path(xdg).expanduser() if xdg else base / ".config") / "opencode",
        }
    manifest_dir = base / ".vibe-workflow"
    return KitPaths(
        manifest_dir=manifest_dir,
        manifest_path=manifest_dir / MANIFEST_FILE,
        template_dir=_template_dir(),
        agent_dirs=agent_dirs,
    )


def _managed_rels(paths: KitPaths) -> list[str]:
    return core.load_manifest(paths.template_dir)["managed_files"]


def _source(paths: KitPaths, key: str, rel: str) -> Path:
    variant = paths.template_dir / key / rel
    return variant if variant.exists() else paths.template_dir / "shared" / rel


def _present(paths: KitPaths) -> list[tuple[str, str, Path]]:
    return [(key, label, paths.agent_dirs[key]) for key, label in TARGETS if paths.agent_dirs[key].is_dir()]


def _prune_empty_dirs(agent_dir: Path) -> None:
    """Remove the skill dirs this kit created, if now empty; never touch commands/ or skills/."""
    for sub in ("skills/vibe-flow/scripts", "skills/vibe-flow"):
        try:
            (agent_dir / sub).rmdir()
        except OSError:
            pass


def install(home: str | None = None, dry_run: bool = False, yes: bool = False, **kwargs) -> int:
    paths = _paths(home)
    present = _present(paths)
    for key, label in TARGETS:
        if paths.agent_dirs[key].is_dir():
            continue
        print(f"skipping {label} (no {paths.agent_dirs[key]})")
    if not present:
        print("no supported agent config directories found (Claude Code, OpenCode); nothing installed")
        return 1

    rels = _managed_rels(paths)
    for key, label, agent_dir in present:
        print(f"{label} ({agent_dir}):")
        for rel in rels:
            dst = agent_dir / rel
            src_text = core.read_text(_source(paths, key, rel))
            state = "create" if not dst.exists() else "unchanged" if core.read_text(dst) == src_text else "update"
            print(f"  {state} {rel}")
    print(f"write {paths.manifest_path}")
    if dry_run:
        print("dry run: no files written")
        return 0
    if not core.confirm("Install/update the workflow kit?", yes=yes):
        print("aborted")
        return 1

    managed: set[str] = set()
    existing = core.load_existing_install_manifest(paths.manifest_path)
    if existing:
        managed.update(existing.get("managed_files", []))
    for key, _label, agent_dir in present:
        for rel in rels:
            if core.install_copy_style_file(_source(paths, key, rel), agent_dir / rel, agent_dir):
                print(f"installed {key}/{rel}")
            managed.add(f"{key}/{rel}")

    core.write_text(paths.manifest_path, json.dumps(core.manifest_state(KIT_NAME, managed), indent=2) + "\n")
    print(f"wrote {paths.manifest_path}")
    return 0


def diff_kit(home: str | None = None) -> int:
    paths = _paths(home)
    any_diff = False
    for key, _label, agent_dir in _present(paths):
        for rel in _managed_rels(paths):
            dst = agent_dir / rel
            if dst.exists() and core.diff_copy_style(_source(paths, key, rel), dst, f"{key}/{rel}"):
                any_diff = True
    if not any_diff:
        print("managed files match kit templates")
    return 0


def doctor(home: str | None = None) -> int:
    paths = _paths(home)
    ok = True
    rels = _managed_rels(paths)
    for key, label in TARGETS:
        agent_dir = paths.agent_dirs[key]
        if not agent_dir.is_dir():
            print(f"{label}: not present ({agent_dir})")
            continue
        installed = sum((agent_dir / rel).exists() for rel in rels)
        print(f"{label}: {installed}/{len(rels)} files installed")
        for rel, name in UPSTREAM:
            if not (agent_dir / rel).exists():
                print(f"  warning: {name} not found in {agent_dir}; install the claude-code/opencode kit so /flow can chain it")
    print("manifest: installed" if core.load_existing_install_manifest(paths.manifest_path) else "manifest: not installed")
    missing = [(key, rel) for key, _ in TARGETS for rel in rels if not _source(paths, key, rel).exists()]
    for key, rel in missing:
        ok = False
        print(f"missing template: {key}/{rel}")
    if not missing:
        print("templates: ok")
    return 0 if ok else 1


def uninstall(home: str | None = None, dry_run: bool = False, yes: bool = False) -> int:
    paths = _paths(home)
    manifest = core.load_existing_install_manifest(paths.manifest_path)
    if not manifest:
        print(f"no {MANIFEST_FILE} found; nothing to uninstall")
        return 0
    files = manifest.get("managed_files", [])
    for entry in files:
        print(f"remove if unchanged {entry}")
    print(f"remove {paths.manifest_path}")
    if dry_run:
        print("dry run: no files removed")
        return 0
    if not core.confirm("Uninstall the workflow kit?", yes=yes):
        print("aborted")
        return 1

    removed = 0
    for entry in files:
        key, _, rel = entry.partition("/")
        agent_dir = paths.agent_dirs.get(key)
        if agent_dir is None or not (agent_dir / rel).exists():
            continue
        if core.uninstall_unchanged_file(_source(paths, key, rel), agent_dir / rel):
            removed += 1
            print(f"removed {entry}")
        else:
            print(f"kept modified file {entry}")
    for agent_dir in paths.agent_dirs.values():
        _prune_empty_dirs(agent_dir)
    paths.manifest_path.unlink(missing_ok=True)
    try:
        paths.manifest_dir.rmdir()
    except OSError:
        pass
    print(f"removed {removed} files")
    return 0
