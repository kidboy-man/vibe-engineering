"""qmd MCP entries and the pure merge/strip helpers for agent configs.

No I/O here: callers read and write the files. The entry dicts and the
legacy-entry matchers are an on-disk contract with older installs."""

from __future__ import annotations

import json

from agents import merge_strategies as ms


QMD_MCP_SNIPPET_JSON: dict = {
    "mcpServers": {
        "qmd": {
            "type": "stdio",
            "command": "qmd",
            "args": ["mcp"],
        }
    }
}

OPENCODE_QMD_MCP_ENTRY: dict = {
    "type": "local",
    "command": "qmd",
    "args": ["mcp"],
    "enabled": True,
}

def _is_legacy_kit_owned_qmd_mcp(entry: object) -> bool:
    """Conservative matcher — True when entry looks like kit-installed qmd MCP.

    Catches Claude-format (type=stdio) and OpenCode-format (type=local) entries
    the kit may have written, while rejecting entries where enabled is not a
    boolean or the command/args don't match.
    """
    if not isinstance(entry, dict):
        return False
    if entry.get("command") != "qmd":
        return False
    if entry.get("args") != ["mcp"]:
        return False
    if entry.get("type") not in (None, "stdio", "local"):
        return False
    if "enabled" in entry and not isinstance(entry["enabled"], bool):
        return False
    return True


def _is_expected_opencode_qmd_mcp(entry: object) -> bool:
    """True ONLY when entry is an exact match for OPENCODE_QMD_MCP_ENTRY.

    enabled: False, extra keys, missing keys, different type/command/args → False.
    """
    return isinstance(entry, dict) and entry == OPENCODE_QMD_MCP_ENTRY


def _merge_opencode_qmd_mcp(current: object) -> tuple[object, bool, list[str]]:
    """Merge qmd MCP entry into parsed opencode.jsonc content.

    Adds ``mcp.qmd`` when absent; preserves custom ``mcp.qmd`` entries;
    removes legacy kit-owned ``mcpServers.qmd`` entries via the conservative
    ``_is_legacy_kit_owned_qmd_mcp`` matcher.

    Returns ``(merged, changed, warnings)`` where ``merged`` is the result
    (same object as ``current`` when unchanged), ``changed`` is True when any
    mutation occurred, and ``warnings`` collects non-fatal diagnostic messages.
    """
    warnings: list[str] = []

    if not isinstance(current, dict):
        return (current, False, ["opencode.jsonc root is not an object"])

    merged = dict(current)
    changed = False

    if "mcp" not in merged:
        merged["mcp"] = {}
        changed = True

    mcp = merged["mcp"]
    if not isinstance(mcp, dict):
        return (current, False, ["existing mcp is not an object"])

    if "qmd" not in mcp:
        mcp["qmd"] = dict(OPENCODE_QMD_MCP_ENTRY)
        changed = True
    elif not _is_expected_opencode_qmd_mcp(mcp["qmd"]):
        warnings.append("qmd MCP present (custom; not overwritten)")
    if isinstance(current.get("mcpServers"), dict):
        qmd_val = current["mcpServers"].get("qmd")
        if qmd_val is not None and _is_legacy_kit_owned_qmd_mcp(qmd_val):
            changed = True
            remaining = {
                k: v for k, v in current["mcpServers"].items() if k != "qmd"
            }
            if remaining:
                merged["mcpServers"] = remaining
            else:
                merged.pop("mcpServers", None)

    return (merged, changed, warnings)


CODEX_TOML_SECTION = "[mcp_servers.qmd]"

CODEX_TOML_BODY = 'type = "stdio"\ncommand = "qmd"\nargs = ["mcp"]\n'

def _strip_qmd_mcp(text: str, parse) -> str | None:
    """Remove qmd mcpServer entry. Returns new text or None if not present.

    parse: callable that takes raw text and returns a dict (json.loads or ms.parse_jsonc).
    If qmd was the only mcpServer, drops the mcpServers key entirely.
    """
    config = parse(text)
    mcps = config.get("mcpServers")
    if not isinstance(mcps, dict) or "qmd" not in mcps:
        return None

    del mcps["qmd"]
    if not mcps:
        del config["mcpServers"]

    return json.dumps(config, indent=2) + "\n"


def _strip_opencode_qmd_mcp(text: str) -> str | None:
    """Remove kit-owned qmd MCP entries from opencode.jsonc content.

    Removes new-format ``mcp.qmd`` (via ``_is_expected_opencode_qmd_mcp``)
    and legacy-format ``mcpServers.qmd`` (via ``_is_legacy_kit_owned_qmd_mcp``).
    Deletes empty parent objects after removal.
    Returns new JSONC string or None if nothing was removed.
    Preserves custom qmd entries, ``mcp.other``, ``mcpServers.other``, etc.
    """
    config = ms.parse_jsonc(text)
    changed = False

    mcp = config.get("mcp")
    if isinstance(mcp, dict) and "qmd" in mcp:
        if _is_expected_opencode_qmd_mcp(mcp["qmd"]):
            del mcp["qmd"]
            changed = True
            if not mcp:
                del config["mcp"]

    mcps = config.get("mcpServers")
    if isinstance(mcps, dict) and "qmd" in mcps:
        if _is_legacy_kit_owned_qmd_mcp(mcps["qmd"]):
            del mcps["qmd"]
            changed = True
            if not mcps:
                del config["mcpServers"]

    if not changed:
        return None

    return json.dumps(config, indent=2) + "\n"
