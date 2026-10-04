"""Safe installer for the wikify kit.

Installs the wikify push-gate hook script and registers it as a pre-tool-use
hook for each agent whose config directory already exists (Claude Code, Codex
CLI, Cursor). Never creates an agent's config directory, never overwrites
unrelated hooks or settings, and uninstall removes only what this kit
registered. Orchestration is deliberately parallel to the guardrails kit.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from agents import installer_core as core
from agents import merge_strategies as ms

MANIFEST_FILE = core.MANIFEST_FILE
KIT_NAME = "wikify"
GUARD_REL = "hooks/vibe-wikify/wikify_guard.py"

CLAUDE_MATCHER = "Bash"
CODEX_MATCHER = "^Bash$"


@dataclass(frozen=True)
class KitPaths:
    home: Path
    manifest_dir: Path
    manifest_path: Path
    template_dir: Path


@dataclass(frozen=True)
class Agent:
    label: str
    dirname: str
    config_name: str
    kind: str  # "claude" | "codex" | "cursor"

    def dir(self, paths: KitPaths) -> Path:
        return paths.home / self.dirname

    def present(self, paths: KitPaths) -> bool:
        return self.dir(paths).is_dir()


AGENTS = [
    Agent("Claude Code", ".claude", "settings.json", "claude"),
    Agent("Codex CLI", ".codex", "config.toml", "codex"),
    Agent("Cursor", ".cursor", "hooks.json", "cursor"),
]


def _template_dir() -> Path:
    return Path(__file__).resolve().parent / "templates" / "wikify"


def _paths(home: str | None = None) -> KitPaths:
    home_path = Path(home).expanduser() if home else Path.home()
    manifest_dir = home_path / ".vibe-wikify"
    return KitPaths(
        home=home_path,
        manifest_dir=manifest_dir,
        manifest_path=manifest_dir / MANIFEST_FILE,
        template_dir=_template_dir(),
    )


def _command(paths: KitPaths, agent: Agent) -> str:
    """Byte-stable command string; also the identity used to dedupe and uninstall.

    Cursor treats empty stdout from a permission hook as invalid output and blocks,
    so its command carries --format=cursor to always print permission JSON.
    """
    suffix = " --format=cursor" if agent.kind == "cursor" else ""
    return f'python3 "{agent.dir(paths) / GUARD_REL}"{suffix}'


def _json_registrations(paths: KitPaths, agent: Agent) -> list[tuple[str, str | None, str]]:
    """(event, matcher, command) triples registered in a JSON-shaped config."""
    command = _command(paths, agent)
    if agent.kind == "claude":
        return [("PreToolUse", CLAUDE_MATCHER, command)]
    return [("beforeShellExecution", None, command)]


def _merge_fn(agent: Agent) -> Callable[..., tuple[dict, bool]]:
    return ms.hook_command_merge_strategy if agent.kind == "claude" else ms.cursor_hook_merge_strategy


def _strip_fn(agent: Agent) -> Callable[..., tuple[dict, bool]]:
    return ms.strip_hook_command if agent.kind == "claude" else ms.strip_cursor_hook


def _codex_block(paths: KitPaths, agent: Agent) -> str:
    return (
        "[[hooks.PreToolUse]]\n"
        f'matcher = "{CODEX_MATCHER}"\n\n'
        "[[hooks.PreToolUse.hooks]]\n"
        'type = "command"\n'
        f"command = '{_command(paths, agent)}'\n"
    )


def _codex_identity(paths: KitPaths, agent: Agent) -> str:
    return f"command = '{_command(paths, agent)}'"


def _load_json_config(path: Path) -> dict | None:
    """Current config, {} if absent, None if unreadable as a JSON object."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _register(paths: KitPaths, agent: Agent) -> None:
    config_path = agent.dir(paths) / agent.config_name
    if agent.kind == "codex":
        current = config_path.read_text(encoding="utf-8") if config_path.exists() else None
        merged, action = ms.codex_hook_block_merge_strategy(
            _codex_block(paths, agent), _codex_identity(paths, agent), current
        )
        if action != "unchanged":
            core.backup(config_path, agent.dir(paths))
            core.write_text(config_path, merged)
            print(f"registered PreToolUse hook in {agent.label} {agent.config_name}")
        return

    current = _load_json_config(config_path)
    if current is None:
        print(f"skipping invalid {agent.config_name} for {agent.label} (hook not registered)")
        return
    merged, changed = current, False
    for event, matcher, command in _json_registrations(paths, agent):
        merged, did_change = _merge_fn(agent)(merged, event, command, matcher=matcher)
        changed = changed or did_change
    if changed:
        core.backup(config_path, agent.dir(paths))
        core.write_text(config_path, json.dumps(merged, indent=2) + "\n")
        print(f"registered hooks in {agent.label} {agent.config_name}")


def _unregister(paths: KitPaths, agent: Agent) -> None:
    config_path = agent.dir(paths) / agent.config_name
    if not config_path.exists():
        return
    if agent.kind == "codex":
        text = config_path.read_text(encoding="utf-8")
        remaining, _ = ms.strip_codex_hook_block(text, _codex_block(paths, agent))
        if remaining == text:
            if _codex_identity(paths, agent) in text:
                print(f"kept edited hook block in {agent.label} {agent.config_name}")
            return
        core.backup(config_path, agent.dir(paths))
        if remaining is None:
            config_path.unlink()
        else:
            core.write_text(config_path, remaining)
        print(f"removed hook from {agent.label} {agent.config_name}")
        return

    current = _load_json_config(config_path)
    if current is None:
        print(f"skipping invalid {agent.config_name} for {agent.label} (hook not removed)")
        return
    merged, changed = current, False
    for event, _matcher, command in _json_registrations(paths, agent):
        merged, did_change = _strip_fn(agent)(merged, event, command)
        changed = changed or did_change
    if changed:
        core.backup(config_path, agent.dir(paths))
        core.write_text(config_path, json.dumps(merged, indent=2) + "\n")
        print(f"removed hooks from {agent.label} {agent.config_name}")


def _is_registered(paths: KitPaths, agent: Agent) -> bool:
    config_path = agent.dir(paths) / agent.config_name
    if not config_path.exists():
        return False
    if agent.kind == "codex":
        return _codex_identity(paths, agent) in config_path.read_text(encoding="utf-8")
    current = _load_json_config(config_path)
    if current is None:
        return False
    return all(
        not _merge_fn(agent)(current, event, command, matcher=matcher)[1]
        for event, matcher, command in _json_registrations(paths, agent)
    )


def install(
    home: str | None = None,
    dry_run: bool = False,
    yes: bool = False,
    **kwargs,
) -> int:
    paths = _paths(home)
    present = [agent for agent in AGENTS if agent.present(paths)]
    for agent in AGENTS:
        if agent not in present:
            print(f"skipping {agent.label} (no ~/{agent.dirname})")
    if not present:
        print("no supported agent config directories found (~/.claude, ~/.codex, ~/.cursor); nothing installed")
        return 1

    for agent in present:
        print(f"install {agent.dirname}/{GUARD_REL}")
        print(f"register hooks in {agent.dirname}/{agent.config_name}")
    print(f"write {paths.manifest_path}")
    if dry_run:
        print("dry run: no files written")
        return 0
    if not core.confirm("Install/update the wikify kit?", yes=yes):
        print("aborted")
        return 1

    managed: set[str] = set()
    existing = core.load_existing_install_manifest(paths.manifest_path)
    if existing:
        managed.update(existing.get("managed_files", []))
    for agent in present:
        if core.install_copy_style_file(paths.template_dir / GUARD_REL, agent.dir(paths) / GUARD_REL, agent.dir(paths)):
            print(f"installed {agent.dirname}/{GUARD_REL}")
        managed.add(f"{agent.dirname}/{GUARD_REL}")
        _register(paths, agent)

    core.write_text(paths.manifest_path, json.dumps(core.manifest_state(KIT_NAME, managed), indent=2) + "\n")
    print(f"wrote {paths.manifest_path}")
    return 0


def diff_kit(home: str | None = None) -> int:
    paths = _paths(home)
    any_diff = False
    for agent in AGENTS:
        dst = agent.dir(paths) / GUARD_REL
        if dst.exists() and core.diff_copy_style(paths.template_dir / GUARD_REL, dst, f"{agent.dirname}/{GUARD_REL}"):
            any_diff = True
    if not any_diff:
        print("managed files match kit templates")
    return 0


def doctor(home: str | None = None) -> int:
    paths = _paths(home)
    ok = True
    print(f"home: {paths.home}")
    for agent in AGENTS:
        if not agent.present(paths):
            print(f"{agent.label}: not present (no ~/{agent.dirname})")
        elif not (agent.dir(paths) / GUARD_REL).exists():
            print(f"{agent.label}: hook not installed")
        elif _is_registered(paths, agent):
            print(f"{agent.label}: hook installed, registered")
            if agent.kind == "codex":
                print("  note: Codex skips new or changed hooks until you review and trust them once via /hooks")
        else:
            print(f"{agent.label}: hook installed, NOT registered (rerun install)")
    if core.load_existing_install_manifest(paths.manifest_path):
        print("manifest: installed")
    else:
        print("manifest: not installed")
    if (paths.template_dir / GUARD_REL).exists():
        print("templates: ok")
    else:
        ok = False
        print(f"missing template: {GUARD_REL}")
    print(
        "note: this is a convenience gate, not a security control; pushes typed in a plain terminal "
        "are not covered and the hook fails open on errors"
    )
    print("note: bypass for one session with VIBE_WIKIFY=off")
    scanner = next((name for name in ("gitleaks", "trufflehog") if shutil.which(name)), None)
    if scanner:
        print(
            f"scan: {scanner} found on PATH "
            "(informational; wikify's built-in scan is a floor, not a complete scanner)"
        )
    else:
        print("scan: no external scanner on PATH (built-in scan only; it is a floor, not a complete scanner)")
    return 0 if ok else 1


def uninstall(home: str | None = None, dry_run: bool = False, yes: bool = False) -> int:
    paths = _paths(home)
    manifest = core.load_existing_install_manifest(paths.manifest_path)
    if not manifest:
        print(f"no {MANIFEST_FILE} found; nothing to uninstall")
        return 0
    files = manifest.get("managed_files", [])
    for rel in files:
        print(f"remove if unchanged {rel}")
    for agent in AGENTS:
        if agent.present(paths):
            print(f"unregister hooks from {agent.dirname}/{agent.config_name}")
    print(f"remove {paths.manifest_path}")
    if dry_run:
        print("dry run: no files removed")
        return 0
    if not core.confirm("Uninstall the wikify kit?", yes=yes):
        print("aborted")
        return 1

    removed = 0
    for rel in files:
        template_rel = rel.partition("/")[2]
        dst = paths.home / rel
        if dst.exists():
            if core.uninstall_unchanged_file(paths.template_dir / template_rel, dst):
                removed += 1
                print(f"removed {rel}")
            else:
                print(f"kept modified file {rel}")
    for agent in AGENTS:
        if agent.present(paths):
            _unregister(paths, agent)
            core.prune_empty_dirs(agent.dir(paths) / "hooks" / "vibe-wikify", agent.dir(paths) / "hooks")
    paths.manifest_path.unlink(missing_ok=True)
    try:
        paths.manifest_dir.rmdir()
    except OSError:
        pass
    print(f"removed {removed} files")
    return 0
