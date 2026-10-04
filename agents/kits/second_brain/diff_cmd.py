"""second-brain diff: read-only comparison of managed state against the kit."""

from __future__ import annotations

import json

from agents import merge_strategies as ms
from agents.kits.second_brain.hooks import CLAUDE_HOOK_AGENT, CODEX_HOOK_AGENT, CURSOR_HOOK_AGENT, HookAgent, _cursor_rule_up_to_date
from agents.kits.second_brain.personas import CLAUDE_PERSONA_SECTION, CODEX_PERSONA_SECTION, OPENCODE_PERSONA_SECTION, PersonaSection, _marked_section_present
from agents.kits.second_brain.mcp import CODEX_TOML_SECTION, _is_expected_opencode_qmd_mcp, _is_legacy_kit_owned_qmd_mcp
from agents.kits.second_brain.paths import CURSOR_RULE_REL, GITIGNORE_ENTRIES, HOOK_SCRIPT_REL, SEED_PAGES, VAULT_DIRS, _paths
from agents.kits.second_brain.vault import _gitignore_diff
from agents.kits.second_brain.skills import _skill_status, _skill_targets


def diff_kit(home: str | None = None) -> int:
    """Show planned differences without making any changes.

    Reports:
    - Vault directories that would be created vs already exist
    - Seed pages that would be seeded vs preserved (never overwritten)
    - .gitignore entries that would be added vs already present
    - Agent config snippet status for Claude/OpenCode/Codex
    - Manifest state
    """
    paths = _paths(home)

    print(f"home: {paths.home_root}")
    print(f"vault: {paths.vault}")
    print(f"template: {paths.template}")
    print()

    # Vault directories
    print("vault directories:")
    for d in VAULT_DIRS:
        target = paths.vault / d
        status = "exists" if target.is_dir() else "would create"
        print(f"  {d} [{status}]")
    print()

    # Seed pages
    template_vault = paths.template / "vault"
    print("seed pages:")
    for rel in SEED_PAGES:
        target = paths.vault / rel
        if target.exists():
            print(f"  {rel} [preserved existing user file]")
        else:
            print(f"  {rel} [would create from template]")
    print()

    # .gitignore
    exists, new_entries = _gitignore_diff(paths.vault)
    if not exists:
        print(".gitignore: would create with:")
        for e in GITIGNORE_ENTRIES:
            print(f"  {e}")
    elif new_entries:
        print(".gitignore: would add entries:")
        for e in new_entries:
            print(f"  + {e}")
    else:
        print(".gitignore: all entries already present")
    print()

    # Git init
    if not (paths.vault / ".git").exists():
        print(f"would git init in {paths.vault}")
    else:
        print("git already initialized")
    print()

    # Agent configs
    print("agent configs:")

    # Claude Code
    settings_path = paths.claude_dir / "settings.json"
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            mcps = settings.get("mcpServers", {})
            if isinstance(mcps, dict) and "qmd" in mcps:
                print("  settings.json: qmd MCP already present")
            else:
                print("  settings.json: would add qmd MCP")
        except json.JSONDecodeError:
            print("  settings.json: invalid (would skip)")
    else:
        print("  settings.json: would create with qmd MCP")

    # OpenCode
    opencode_path = paths.opencode_config_dir / "opencode.jsonc"
    if opencode_path.exists():
        try:
            opencode_config = ms.parse_jsonc(
                opencode_path.read_text(encoding="utf-8")
            )
            if not isinstance(opencode_config, dict):
                print(
                    "  opencode.jsonc: root is not an object"
                    " (would skip)"
                )
            else:
                has_legacy = (
                    isinstance(opencode_config.get("mcpServers"), dict)
                    and "qmd" in opencode_config["mcpServers"]
                    and _is_legacy_kit_owned_qmd_mcp(
                        opencode_config["mcpServers"]["qmd"]
                    )
                )
                mcp = opencode_config.get("mcp")
                if mcp is None:
                    if has_legacy:
                        print(
                            "  opencode.jsonc: would migrate legacy"
                            " mcpServers.qmd to mcp.qmd"
                        )
                    else:
                        print("  opencode.jsonc: would add qmd MCP")
                elif not isinstance(mcp, dict):
                    print(
                        "  opencode.jsonc: mcp is not an object;"
                        " qmd MCP cannot be added"
                    )
                elif "qmd" in mcp:
                    if _is_expected_opencode_qmd_mcp(mcp["qmd"]):
                        print("  opencode.jsonc: qmd MCP already present")
                    else:
                        print(
                            "  opencode.jsonc: qmd MCP present"
                            " (custom; not overwritten)"
                        )
                else:
                    if has_legacy:
                        print(
                            "  opencode.jsonc: would migrate legacy"
                            " mcpServers.qmd to mcp.qmd"
                        )
                    else:
                        print("  opencode.jsonc: would add qmd MCP")
        except (json.JSONDecodeError, ValueError):
            print("  opencode.jsonc: invalid (would skip)")
    else:
        print("  opencode.jsonc: would create with qmd MCP")

    # Codex CLI
    codex_path = paths.codex_dir / "config.toml"
    if codex_path.exists():
        content = codex_path.read_text(encoding="utf-8")
        if CODEX_TOML_SECTION in content:
            print("  config.toml: qmd MCP section already present")
        else:
            print("  config.toml: would add qmd MCP section")
    else:
        print("  config.toml: would create with qmd MCP section")
    print()

    # Proactive context: SessionStart-equivalent hooks + persona sections
    def _diff_print_hook(agent: HookAgent, script_prefix: str = "") -> None:
        script_path = agent.script_dir_fn(paths) / HOOK_SCRIPT_REL
        template_content = (paths.template / HOOK_SCRIPT_REL).read_text(encoding="utf-8")
        if script_path.is_file():
            status = "up to date" if script_path.read_text(encoding="utf-8") == template_content else "present, would update (content differs from template)"
        else:
            status = "would create"
        print(f"  {script_prefix}{HOOK_SCRIPT_REL}: {status}")
        state = "already registered" if agent.already_installed_fn(paths) else "would register"
        print(f"  {agent.registered_where} {agent.event_label} hook: {state}")

    def _diff_print_section(spec: PersonaSection) -> None:
        path = spec.path_fn(paths)
        if _marked_section_present(path, spec.begin_marker):
            print(f"  {spec.label} second-brain section: already present")
        elif path.exists():
            print(f"  {spec.label} second-brain section: would create file (existing content preserved)")
        else:
            print(f"  {spec.label} second-brain section: would create file")

    print("proactive context:")
    _diff_print_hook(CLAUDE_HOOK_AGENT)
    _diff_print_section(CLAUDE_PERSONA_SECTION)

    _diff_print_hook(CODEX_HOOK_AGENT, "codex ")
    _diff_print_section(CODEX_PERSONA_SECTION)

    _diff_print_hook(CURSOR_HOOK_AGENT, "cursor ")
    if _cursor_rule_up_to_date(paths):
        print(f"  {CURSOR_RULE_REL}: up to date")
    elif (paths.cursor_dir / CURSOR_RULE_REL).exists():
        print(f"  {CURSOR_RULE_REL}: present, would update (content differs from template)")
    else:
        print(f"  {CURSOR_RULE_REL}: would create")

    _diff_print_section(OPENCODE_PERSONA_SECTION)
    print()

    print("second-brain skill:")
    for target in _skill_targets(paths):
        print(f"  {target}: {_skill_status(paths, target)}")
    print()

    # Manifest
    manifest = paths.manifest
    if manifest.exists():
        print(f"manifest: exists at {manifest}")
    else:
        print(f"manifest: would create at {manifest}")
    print()

    return 0
