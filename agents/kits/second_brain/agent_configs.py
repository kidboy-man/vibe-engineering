"""Per-agent qmd MCP config merges (Claude Code, OpenCode, Cursor, Codex).

Each reads the agent's config, merges the qmd entry, backs up and writes."""

from __future__ import annotations

import json

from agents import installer_core as core
from agents import merge_strategies as ms
from agents.kits.second_brain.mcp import CODEX_TOML_BODY, CODEX_TOML_SECTION, QMD_MCP_SNIPPET_JSON, _merge_opencode_qmd_mcp
from agents.kits.second_brain.paths import KitPaths


CLAUDE_SECRET_KEYS = {"env"}

def _merge_claude_config(paths: KitPaths) -> None:
    settings_path = paths.claude_dir / "settings.json"
    current: dict = {}
    if settings_path.exists():
        try:
            current = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print("skipping invalid settings.json")
            return

    merged, changed = ms.json_defaults_strategy(
        QMD_MCP_SNIPPET_JSON, current, CLAUDE_SECRET_KEYS
    )
    if not changed:
        return

    settings_path.parent.mkdir(parents=True, exist_ok=True)
    core.backup(settings_path, paths.claude_dir)
    settings_path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    print("merged qmd MCP into settings.json")


def _merge_opencode_config(paths: KitPaths) -> None:
    config_path = paths.opencode_config_dir / "opencode.jsonc"
    current: dict = {}
    if config_path.exists():
        try:
            current = ms.parse_jsonc(config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            print("skipping invalid opencode.jsonc")
            return

    merged, changed, warnings = _merge_opencode_qmd_mcp(current)

    for w in warnings:
        print(w)

    if not changed:
        return

    config_path.parent.mkdir(parents=True, exist_ok=True)
    core.backup(config_path, paths.opencode_config_dir)
    config_path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    print("merged qmd MCP into opencode.jsonc")


def _merge_cursor_config(paths: KitPaths) -> None:
    """Merge qmd MCP entry into ~/.cursor/mcp.json.

    Nested merge (not json_defaults_strategy's shallow top-level merge):
    an existing unrelated mcpServers.* entry must not block adding qmd.
    """
    config_path = paths.cursor_dir / "mcp.json"
    current: dict = {}
    if config_path.exists():
        try:
            current = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print("skipping invalid mcp.json")
            return

    if not isinstance(current, dict):
        print("skipping mcp.json: root is not an object")
        return

    mcps = current.get("mcpServers")
    if not isinstance(mcps, dict):
        mcps = {}
    if "qmd" in mcps:
        return

    merged = dict(current)
    merged["mcpServers"] = {
        **mcps,
        "qmd": dict(QMD_MCP_SNIPPET_JSON["mcpServers"]["qmd"]),
    }

    config_path.parent.mkdir(parents=True, exist_ok=True)
    core.backup(config_path, paths.cursor_dir)
    config_path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    print("merged qmd MCP into mcp.json")


def _merge_codex_config(paths: KitPaths) -> None:
    config_path = paths.codex_dir / "config.toml"
    current: str | None = None
    if config_path.exists():
        current = config_path.read_text(encoding="utf-8")

    merged, action = ms.toml_block_merge_strategy(
        CODEX_TOML_SECTION, CODEX_TOML_BODY, current
    )
    if action == "unchanged":
        return

    config_path.parent.mkdir(parents=True, exist_ok=True)
    core.backup(config_path, paths.codex_dir)
    config_path.write_text(merged, encoding="utf-8")
    if action == "create":
        print(f"created {config_path} with qmd MCP section")
    else:
        print("merged qmd MCP into config.toml")
