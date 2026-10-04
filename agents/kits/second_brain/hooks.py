"""SessionStart hook installation and detection for Claude Code, Codex and Cursor.

Hook command strings are byte-stable: they double as the identity used to
detect and remove entries written by older versions."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from agents import installer_core as core
from agents import merge_strategies as ms
from agents.kits.second_brain.paths import CURSOR_RULE_REL, CURSOR_SESSIONSTART_EVENT, HOOK_SCRIPT_REL, KitPaths, SESSIONSTART_EVENT


@dataclass(frozen=True)
class HookAgent:
    """A SessionStart-equivalent hook target (Claude Code, Codex CLI, Cursor)."""

    label: str
    event_label: str
    registered_where: str
    script_dir_fn: Callable[[KitPaths], Path]
    already_installed_fn: Callable[[KitPaths], bool]


def _install_hook_script_file(script_dir: Path, template: Path) -> None:
    """Copy the context-injector script into *script_dir* if changed."""
    script_src = template / HOOK_SCRIPT_REL
    script_dst = script_dir / HOOK_SCRIPT_REL
    script_dst.parent.mkdir(parents=True, exist_ok=True)
    content = script_src.read_text(encoding="utf-8")
    if not script_dst.exists() or script_dst.read_text(encoding="utf-8") != content:
        script_dst.write_text(content, encoding="utf-8")
        print(f"installed {script_dst}")


def _json_hook_already_installed(
    config_path: Path,
    merge_fn: Callable[[dict, str, str], tuple[dict, bool]],
    event: str,
    command: str,
) -> bool:
    """Read-only check shared by JSON-shaped hook configs (Claude, Cursor)."""
    if not config_path.exists():
        return False
    try:
        current = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    _, changed = merge_fn(current, event, command)
    return not changed


def _hook_command(paths: KitPaths) -> str:
    """Byte-stable command string for the kit-owned SessionStart hook entry."""
    return f'python3 "{paths.claude_dir / HOOK_SCRIPT_REL}"'


def _codex_hook_command(paths: KitPaths) -> str:
    """Byte-stable command string for the kit-owned Codex SessionStart hook entry."""
    return f'python3 "{paths.codex_dir / HOOK_SCRIPT_REL}"'


def _cursor_hook_command(paths: KitPaths) -> str:
    """Byte-stable command string for the kit-owned Cursor sessionStart hook entry."""
    return f'python3 "{paths.cursor_dir / HOOK_SCRIPT_REL}" --format=cursor'


def _hook_already_installed(paths: KitPaths) -> bool:
    """Read-only check: is our SessionStart hook already registered?"""
    return _json_hook_already_installed(
        paths.claude_dir / "settings.json", ms.hook_command_merge_strategy, SESSIONSTART_EVENT, _hook_command(paths)
    )


def _codex_hook_block(paths: KitPaths) -> str:
    """Literal Codex config.toml array-of-tables block for our SessionStart hook."""
    return (
        "[[hooks.SessionStart]]\n\n"
        "[[hooks.SessionStart.hooks]]\n"
        'type = "command"\n'
        f"command = '{_codex_hook_command(paths)}'\n"
    )


def _codex_hook_identity(paths: KitPaths) -> str:
    return f"command = '{_codex_hook_command(paths)}'"


def _codex_hook_already_installed(paths: KitPaths) -> bool:
    """Read-only check: is our SessionStart hook block already in config.toml?

    config.toml is never parsed — dedupe is a literal substring check,
    matching the existing qmd MCP TOML-block merge in this same file.
    """
    config_path = paths.codex_dir / "config.toml"
    if not config_path.exists():
        return False
    return _codex_hook_identity(paths) in config_path.read_text(encoding="utf-8")


def _cursor_hook_already_installed(paths: KitPaths) -> bool:
    """Read-only check: is our sessionStart hook already registered?"""
    return _json_hook_already_installed(
        paths.cursor_dir / "hooks.json",
        ms.cursor_hook_merge_strategy,
        CURSOR_SESSIONSTART_EVENT,
        _cursor_hook_command(paths),
    )


CLAUDE_HOOK_AGENT = HookAgent(
    "Claude Code", "SessionStart", "settings.json", lambda p: p.claude_dir, _hook_already_installed
)

CODEX_HOOK_AGENT = HookAgent(
    "Codex CLI", "SessionStart", "config.toml", lambda p: p.codex_dir, _codex_hook_already_installed
)

CURSOR_HOOK_AGENT = HookAgent(
    "Cursor", "sessionStart", "hooks.json", lambda p: p.cursor_dir, _cursor_hook_already_installed
)

HOOK_AGENTS = [CLAUDE_HOOK_AGENT, CODEX_HOOK_AGENT, CURSOR_HOOK_AGENT]

def _install_session_hook(paths: KitPaths) -> None:
    """Copy the SessionStart context-injector script and register it.

    Idempotent: identical script content is not rewritten; an already
    registered command is not duplicated.
    """
    _install_hook_script_file(paths.claude_dir, paths.template)
    settings_path = paths.claude_dir / "settings.json"
    current: dict = {}
    if settings_path.exists():
        try:
            current = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print("skipping invalid settings.json (hook not registered)")
            return
    merged, changed = ms.hook_command_merge_strategy(current, SESSIONSTART_EVENT, _hook_command(paths))
    if changed:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        core.backup(settings_path, paths.claude_dir)
        settings_path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
        print("registered SessionStart hook in settings.json")


def _install_codex_hook(paths: KitPaths) -> None:
    """Copy the SessionStart context-injector script and register it in config.toml.

    Idempotent: identical script content is not rewritten; an already
    registered command is not duplicated.
    """
    _install_hook_script_file(paths.codex_dir, paths.template)
    config_path = paths.codex_dir / "config.toml"
    current = config_path.read_text(encoding="utf-8") if config_path.exists() else None
    merged, action = ms.codex_hook_block_merge_strategy(_codex_hook_block(paths), _codex_hook_identity(paths), current)
    if action == "unchanged":
        return
    config_path.parent.mkdir(parents=True, exist_ok=True)
    core.backup(config_path, paths.codex_dir)
    config_path.write_text(merged, encoding="utf-8")
    if action == "create":
        print(f"created {config_path} with SessionStart hook")
    else:
        print("registered SessionStart hook in config.toml")


def _install_cursor_hook(paths: KitPaths) -> None:
    """Copy the sessionStart context-injector script and register it in hooks.json.

    Idempotent: identical script content is not rewritten; an already
    registered command is not duplicated.
    """
    _install_hook_script_file(paths.cursor_dir, paths.template)
    hooks_path = paths.cursor_dir / "hooks.json"
    current: dict = {}
    if hooks_path.exists():
        try:
            current = json.loads(hooks_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print("skipping invalid hooks.json (hook not registered)")
            return
    merged, changed = ms.cursor_hook_merge_strategy(current, CURSOR_SESSIONSTART_EVENT, _cursor_hook_command(paths))
    if changed:
        hooks_path.parent.mkdir(parents=True, exist_ok=True)
        core.backup(hooks_path, paths.cursor_dir)
        hooks_path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
        print("registered sessionStart hook in hooks.json")


def _install_cursor_rule(paths: KitPaths) -> None:
    """Install the fully kit-owned Cursor rule file (create/update-if-differs)."""
    rule_src = paths.template / CURSOR_RULE_REL
    rule_dst = paths.cursor_dir / CURSOR_RULE_REL
    content = rule_src.read_text(encoding="utf-8")
    if not rule_dst.exists() or rule_dst.read_text(encoding="utf-8") != content:
        rule_dst.parent.mkdir(parents=True, exist_ok=True)
        rule_dst.write_text(content, encoding="utf-8")
        print(f"installed {rule_dst}")


def _cursor_rule_up_to_date(paths: KitPaths) -> bool:
    rule_dst = paths.cursor_dir / CURSOR_RULE_REL
    if not rule_dst.exists():
        return False
    rule_src = paths.template / CURSOR_RULE_REL
    return rule_dst.read_text(encoding="utf-8") == rule_src.read_text(encoding="utf-8")
