"""Safe installer for the guardrails kit.

Installs a pre-tool-use guard script and registers it as a hook for each agent
whose config directory already exists (Claude Code, Codex CLI, Cursor). Never
creates an agent's config directory, never overwrites unrelated hooks or
settings, and uninstall removes only what this kit registered.

Blocking contract: the guard exits 2 with a reason on stderr, which all three
agents treat as "deny". See hooks/vibe-guardrails/guard.py for the rules.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from agents import installer_core as core
from agents import merge_strategies as ms

MANIFEST_FILE = core.MANIFEST_FILE
KIT_NAME = "guardrails"
GUARD_REL = "hooks/vibe-guardrails/guard.py"
VERIFY_REL = "hooks/vibe-guardrails/verify.py"

CLAUDE_GUARD_MATCHER = "Bash|Read|Edit|Write|MultiEdit|NotebookEdit"
CLAUDE_VERIFY_MATCHER = "Edit|Write|MultiEdit"
CODEX_GUARD_MATCHER = "^(Bash|apply_patch)$"


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
    return Path(__file__).resolve().parent / "templates" / "guardrails"


def _paths(home: str | None = None) -> KitPaths:
    home_path = Path(home).expanduser() if home else Path.home()
    manifest_dir = home_path / ".vibe-guardrails"
    return KitPaths(
        home=home_path,
        manifest_dir=manifest_dir,
        manifest_path=manifest_dir / MANIFEST_FILE,
        template_dir=_template_dir(),
    )


def _command(paths: KitPaths, agent: Agent, rel: str) -> str:
    """Byte-stable command string; also the identity used to dedupe and uninstall.

    Cursor treats empty stdout from a permission hook as invalid output and blocks,
    so its guard command carries --format=cursor to always print permission JSON.
    """
    suffix = " --format=cursor" if agent.kind == "cursor" and rel == GUARD_REL else ""
    return f'python3 "{agent.dir(paths) / rel}"{suffix}'


def _json_registrations(paths: KitPaths, agent: Agent, with_verify: bool) -> list[tuple[str, str | None, str]]:
    """(event, matcher, command) triples registered in a JSON-shaped config."""
    guard = _command(paths, agent, GUARD_REL)
    if agent.kind == "claude":
        regs = [("PreToolUse", CLAUDE_GUARD_MATCHER, guard)]
        if with_verify:
            regs.append(("PostToolUse", CLAUDE_VERIFY_MATCHER, _command(paths, agent, VERIFY_REL)))
        return regs
    # Cursor: shell and read have documented payloads; Write goes through preToolUse.
    return [
        ("beforeShellExecution", None, guard),
        ("beforeReadFile", None, guard),
        ("preToolUse", "Write", guard),
    ]


def _all_json_registrations(paths: KitPaths, agent: Agent) -> list[tuple[str, str | None, str]]:
    return _json_registrations(paths, agent, with_verify=True)


def _merge_fn(agent: Agent) -> Callable[..., tuple[dict, bool]]:
    return ms.hook_command_merge_strategy if agent.kind == "claude" else ms.cursor_hook_merge_strategy


def _strip_fn(agent: Agent) -> Callable[..., tuple[dict, bool]]:
    return ms.strip_hook_command if agent.kind == "claude" else ms.strip_cursor_hook


def _codex_block(paths: KitPaths, agent: Agent) -> str:
    return (
        "[[hooks.PreToolUse]]\n"
        f'matcher = "{CODEX_GUARD_MATCHER}"\n\n'
        "[[hooks.PreToolUse.hooks]]\n"
        'type = "command"\n'
        f"command = '{_command(paths, agent, GUARD_REL)}'\n"
    )


def _codex_identity(paths: KitPaths, agent: Agent) -> str:
    return f"command = '{_command(paths, agent, GUARD_REL)}'"


def _load_json_config(path: Path) -> dict | None:
    """Current config, {} if absent, None if unreadable as a JSON object."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _script_rels(agent: Agent, with_verify: bool) -> list[str]:
    rels = [GUARD_REL]
    if with_verify and agent.kind == "claude":
        rels.append(VERIFY_REL)
    return rels


def _register(paths: KitPaths, agent: Agent, with_verify: bool) -> None:
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
    for event, matcher, command in _json_registrations(paths, agent, with_verify):
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
    for event, _matcher, command in _all_json_registrations(paths, agent):
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
    guard_regs = _json_registrations(paths, agent, with_verify=False)
    return all(not _merge_fn(agent)(current, event, command, matcher=matcher)[1] for event, matcher, command in guard_regs)


def _prune_empty_dirs(*dirs: Path) -> None:
    """rmdir each dir in order, stopping at the first that is missing or non-empty."""
    for directory in dirs:
        try:
            directory.rmdir()
        except OSError:
            return


def install(
    home: str | None = None,
    dry_run: bool = False,
    yes: bool = False,
    with_verify: bool = False,
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
        for rel in _script_rels(agent, with_verify):
            print(f"install {agent.dirname}/{rel}")
        print(f"register hooks in {agent.dirname}/{agent.config_name}")
    print(f"write {paths.manifest_path}")
    if dry_run:
        print("dry run: no files written")
        return 0
    if not core.confirm("Install/update the guardrails kit?", yes=yes):
        print("aborted")
        return 1

    managed: set[str] = set()
    existing = core.load_existing_install_manifest(paths.manifest_path)
    if existing:
        managed.update(existing.get("managed_files", []))
    for agent in present:
        for rel in _script_rels(agent, with_verify):
            if core.install_copy_style_file(paths.template_dir / rel, agent.dir(paths) / rel, agent.dir(paths)):
                print(f"installed {agent.dirname}/{rel}")
            managed.add(f"{agent.dirname}/{rel}")
        _register(paths, agent, with_verify)

    core.write_text(paths.manifest_path, json.dumps(core.manifest_state(KIT_NAME, managed), indent=2) + "\n")
    print(f"wrote {paths.manifest_path}")
    return 0


def diff_kit(home: str | None = None) -> int:
    paths = _paths(home)
    any_diff = False
    for agent in AGENTS:
        for rel in (GUARD_REL, VERIFY_REL):
            dst = agent.dir(paths) / rel
            if dst.exists() and core.diff_copy_style(paths.template_dir / rel, dst, f"{agent.dirname}/{rel}"):
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
            print(f"{agent.label}: guard not installed")
        elif _is_registered(paths, agent):
            print(f"{agent.label}: guard installed, hook registered")
            if agent.kind == "codex":
                print("  note: Codex skips new or changed hooks until you review and trust them once via /hooks")
        else:
            print(f"{agent.label}: guard installed, hook NOT registered (rerun install)")
    if core.load_existing_install_manifest(paths.manifest_path):
        print("manifest: installed")
    else:
        print("manifest: not installed")
    missing = [rel for rel in (GUARD_REL, VERIFY_REL) if not (paths.template_dir / rel).exists()]
    for rel in missing:
        ok = False
        print(f"missing template: {rel}")
    if not missing:
        print("templates: ok")
    print("note: bypass for one session with VIBE_GUARDRAILS=off; the guard is a heuristic speed bump, not a sandbox")
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
    if not core.confirm("Uninstall the guardrails kit?", yes=yes):
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
            _prune_empty_dirs(agent.dir(paths) / "hooks" / "vibe-guardrails", agent.dir(paths) / "hooks")
    paths.manifest_path.unlink(missing_ok=True)
    try:
        paths.manifest_dir.rmdir()
    except OSError:
        pass
    print(f"removed {removed} files")
    return 0
