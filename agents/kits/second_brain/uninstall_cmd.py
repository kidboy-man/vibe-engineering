"""second-brain uninstall: remove only what this kit wrote, keep modified files."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from agents import installer_core as core
from agents import merge_strategies as ms
from agents.kits.second_brain.paths import CLAUDE_MD_BEGIN_MARKER, CLAUDE_MD_END_MARKER, CODEX_INSTRUCTIONS_BEGIN_MARKER, CODEX_INSTRUCTIONS_END_MARKER, CURSOR_RULE_REL, CURSOR_SESSIONSTART_EVENT, HOOK_SCRIPT_REL, OPENCODE_AGENTS_BEGIN_MARKER, OPENCODE_AGENTS_END_MARKER, SESSIONSTART_EVENT, _paths
from agents.kits.second_brain.mcp import CODEX_TOML_SECTION, _is_expected_opencode_qmd_mcp, _is_legacy_kit_owned_qmd_mcp, _strip_opencode_qmd_mcp, _strip_qmd_mcp
from agents.kits.second_brain.hooks import _codex_hook_already_installed, _codex_hook_block, _cursor_hook_already_installed, _cursor_hook_command, _hook_already_installed, _hook_command
from agents.kits.second_brain.personas import _marked_section_present
from agents.kits.second_brain.skills import _skill_dir_status, _skill_root_targets, _skill_source_dirs


def uninstall(
    home: str | None = None,
    dry_run: bool = False,
    yes: bool = False,
) -> int:
    """Uninstall kit-owned snippets and manifest.

    Removes only:
    - qmd MCP snippets from Claude/OpenCode/Codex agent configs
    - Runtime manifest at <vault>/.vibe-engineering-manifest.json

    NEVER deletes:
    - Vault directory, .git, seed pages, .gitignore, raw/, wiki/, output/
    - Any user content under the vault
    - User-added config entries around kit snippets
    """
    paths = _paths(home)

    def _strip_codex(text: str) -> tuple[str | None, bool]:
        remaining, fully_owned = ms.strip_toml_block(text, CODEX_TOML_SECTION)
        return remaining, fully_owned

    specs: list[tuple[Path, str, Callable[[str], tuple[str | None, bool]] | None]] = []

    settings_path = paths.claude_dir / "settings.json"
    if settings_path.exists():
        try:
            mcps = json.loads(settings_path.read_text(encoding="utf-8")).get("mcpServers")
        except json.JSONDecodeError:
            mcps = None
        if isinstance(mcps, dict) and "qmd" in mcps:

            def _mutate_claude(text: str) -> tuple[str | None, bool]:
                new = _strip_qmd_mcp(text, json.loads)
                return (None, False) if new is None else (new, False)

            specs.append((settings_path, "qmd MCP from settings.json", _mutate_claude))

    opencode_path = paths.opencode_config_dir / "opencode.jsonc"
    if opencode_path.exists():
        try:
            config = ms.parse_jsonc(opencode_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            config = None

        has_new_format = (
            isinstance(config, dict)
            and isinstance(config.get("mcp"), dict)
            and "qmd" in config["mcp"]
            and _is_expected_opencode_qmd_mcp(config["mcp"]["qmd"])
        )
        has_legacy = (
            isinstance(config, dict)
            and isinstance(config.get("mcpServers"), dict)
            and "qmd" in config["mcpServers"]
            and _is_legacy_kit_owned_qmd_mcp(config["mcpServers"]["qmd"])
        )

        if has_new_format or has_legacy:

            def _mutate_opencode(text: str) -> tuple[str | None, bool]:
                new = _strip_opencode_qmd_mcp(text)
                return (None, False) if new is None else (new, False)

            specs.append((opencode_path, "qmd MCP from opencode.jsonc", _mutate_opencode))

    codex_path = paths.codex_dir / "config.toml"
    if codex_path.exists() and CODEX_TOML_SECTION in codex_path.read_text(encoding="utf-8"):
        specs.append((codex_path, "qmd MCP section", _strip_codex))

    if settings_path.exists() and _hook_already_installed(paths):

        def _mutate_claude_hooks(text: str) -> tuple[str | None, bool]:
            current = json.loads(text)
            merged, changed = ms.strip_hook_command(
                current, SESSIONSTART_EVENT, _hook_command(paths)
            )
            if not changed:
                return None, False
            return json.dumps(merged, indent=2) + "\n", False

        specs.append((settings_path, "SessionStart hook from settings.json", _mutate_claude_hooks))

    hook_script_path = paths.claude_dir / HOOK_SCRIPT_REL
    if hook_script_path.exists():
        specs.append((hook_script_path, "second-brain SessionStart hook script", None))

    claude_md_path = paths.claude_dir / "CLAUDE.md"
    if claude_md_path.exists() and CLAUDE_MD_BEGIN_MARKER in claude_md_path.read_text(encoding="utf-8"):

        def _mutate_claude_md(text: str) -> tuple[str | None, bool]:
            return ms.strip_marked_section(text, CLAUDE_MD_BEGIN_MARKER, CLAUDE_MD_END_MARKER)

        specs.append((claude_md_path, "second-brain section from CLAUDE.md", _mutate_claude_md))

    codex_config_path = paths.codex_dir / "config.toml"
    if codex_config_path.exists() and _codex_hook_already_installed(paths):

        def _mutate_codex_hook(text: str) -> tuple[str | None, bool]:
            return ms.strip_codex_hook_block(text, _codex_hook_block(paths))

        specs.append((codex_config_path, "SessionStart hook from config.toml", _mutate_codex_hook))

    codex_hook_script_path = paths.codex_dir / HOOK_SCRIPT_REL
    if codex_hook_script_path.exists():
        specs.append((codex_hook_script_path, "second-brain SessionStart hook script (codex)", None))

    codex_agents_path = paths.codex_dir / "AGENTS.md"
    if _marked_section_present(codex_agents_path, CODEX_INSTRUCTIONS_BEGIN_MARKER):

        def _mutate_codex_agents(text: str) -> tuple[str | None, bool]:
            return ms.strip_marked_section(text, CODEX_INSTRUCTIONS_BEGIN_MARKER, CODEX_INSTRUCTIONS_END_MARKER)

        specs.append((codex_agents_path, "second-brain section from AGENTS.md", _mutate_codex_agents))

    legacy_codex_instructions_path = paths.codex_dir / "instructions.md"
    if _marked_section_present(legacy_codex_instructions_path, CODEX_INSTRUCTIONS_BEGIN_MARKER):

        def _mutate_legacy_codex_instructions(text: str) -> tuple[str | None, bool]:
            return ms.strip_marked_section(text, CODEX_INSTRUCTIONS_BEGIN_MARKER, CODEX_INSTRUCTIONS_END_MARKER)

        specs.append((legacy_codex_instructions_path, "legacy second-brain section from instructions.md", _mutate_legacy_codex_instructions))

    cursor_hooks_path = paths.cursor_dir / "hooks.json"
    if cursor_hooks_path.exists() and _cursor_hook_already_installed(paths):

        def _mutate_cursor_hooks(text: str) -> tuple[str | None, bool]:
            current = json.loads(text)
            merged, changed = ms.strip_cursor_hook(
                current, CURSOR_SESSIONSTART_EVENT, _cursor_hook_command(paths)
            )
            if not changed:
                return None, False
            return json.dumps(merged, indent=2) + "\n", False

        specs.append((cursor_hooks_path, "sessionStart hook from hooks.json", _mutate_cursor_hooks))

    cursor_mcp_path = paths.cursor_dir / "mcp.json"
    if cursor_mcp_path.exists():
        try:
            mcps = json.loads(cursor_mcp_path.read_text(encoding="utf-8")).get("mcpServers")
        except json.JSONDecodeError:
            mcps = None
        if isinstance(mcps, dict) and "qmd" in mcps:

            def _mutate_cursor_mcp(text: str) -> tuple[str | None, bool]:
                new = _strip_qmd_mcp(text, json.loads)
                return (None, False) if new is None else (new, False)

            specs.append((cursor_mcp_path, "qmd MCP from mcp.json", _mutate_cursor_mcp))

    cursor_hook_script_path = paths.cursor_dir / HOOK_SCRIPT_REL
    if cursor_hook_script_path.exists():
        specs.append((cursor_hook_script_path, "second-brain sessionStart hook script (cursor)", None))

    opencode_agents_path = paths.opencode_config_dir / "AGENTS.md"
    if _marked_section_present(opencode_agents_path, OPENCODE_AGENTS_BEGIN_MARKER):

        def _mutate_opencode_agents(text: str) -> tuple[str | None, bool]:
            return ms.strip_marked_section(text, OPENCODE_AGENTS_BEGIN_MARKER, OPENCODE_AGENTS_END_MARKER)

        specs.append((opencode_agents_path, "second-brain section from OpenCode AGENTS.md", _mutate_opencode_agents))

    if paths.manifest.exists():
        specs.append((paths.manifest, "kit manifest", None))

    # Cursor's rule file is handled separately: unlike the other kit-owned
    # snippets above (which are merged into shared user files), this file is
    # fully kit-owned but may still have been hand-edited — delete only if it
    # still matches the template, matching every other kit's copy-style
    # uninstall (core.uninstall_unchanged_file). A hand-edited file is kept.
    cursor_rule_dst = paths.cursor_dir / CURSOR_RULE_REL
    cursor_rule_src = paths.template / CURSOR_RULE_REL
    remove_cursor_rule = cursor_rule_dst.exists()
    skill_dirs = [
        (source_dir, root / source_dir.name)
        for root in _skill_root_targets(paths)
        for source_dir in _skill_source_dirs(paths)
        if (root / source_dir.name).exists()
    ]

    if not specs and not remove_cursor_rule and not skill_dirs:
        print("nothing to uninstall")
        return 0

    if dry_run:
        for _path, label, _fn in specs:
            print(f"would remove {label}")
        if remove_cursor_rule:
            print(f"would remove {CURSOR_RULE_REL} (if unchanged from template)")
        for _source_dir, target_dir in skill_dirs:
            print(f"would remove second-brain skill {target_dir / 'SKILL.md'} (if unchanged from template)")
        print("dry run: no files modified")
        return 0

    if not core.confirm("Uninstall second-brain kit managed snippets?", yes=yes):
        print("aborted")
        return 1

    for path, label, mutate in specs:
        if mutate is None:
            path.unlink()
            print(f"removed {label}")
        else:
            new_text, delete_file = mutate(path.read_text(encoding="utf-8"))
            if new_text is None and not delete_file:
                continue
            if delete_file:
                path.unlink()
                print(f"removed {path.name} (was entirely {label})")
            else:
                path.write_text(new_text or "", encoding="utf-8")
                print(f"stripped {label}")

    if remove_cursor_rule:
        if core.uninstall_unchanged_file(cursor_rule_src, cursor_rule_dst):
            print(f"removed {CURSOR_RULE_REL}")
        else:
            print(f"kept modified file {CURSOR_RULE_REL}")

    for source_dir, target_dir in skill_dirs:
        if _skill_dir_status(paths, source_dir, target_dir) != "up to date":
            print(f"kept modified second-brain skill {target_dir}")
            continue
        for source in source_dir.rglob("*"):
            if source.is_file():
                (target_dir / source.relative_to(source_dir)).unlink()
        for path in sorted(target_dir.rglob("*"), key=lambda item: len(item.parts), reverse=True):
            if path.is_dir():
                path.rmdir()
        target_dir.rmdir()
        print(f"removed second-brain skill {target_dir / 'SKILL.md'}")

    return 0
