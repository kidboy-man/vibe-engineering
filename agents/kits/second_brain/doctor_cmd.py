"""second-brain doctor: read-only health report."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib  # type: ignore[no-redef]

from agents import installer_core as core
from agents import merge_strategies as ms
from agents.kits.second_brain.hooks import CLAUDE_HOOK_AGENT, CODEX_HOOK_AGENT, CURSOR_HOOK_AGENT, HookAgent, _cursor_rule_up_to_date
from agents.kits.second_brain.personas import CLAUDE_PERSONA_SECTION, CODEX_PERSONA_SECTION, OPENCODE_PERSONA_SECTION, PersonaSection, _marked_section_present
from agents.kits.second_brain.mcp import CODEX_TOML_SECTION, _is_expected_opencode_qmd_mcp, _is_legacy_kit_owned_qmd_mcp
from agents.kits.second_brain.paths import CURSOR_RULE_REL, HOOK_SCRIPT_REL, QMD_MIN_NODE_MAJOR, SEED_PAGES, VAULT_DIRS, _paths
from agents.kits.second_brain.qmd import _check_min_version, _qmd_collection_status
from agents.kits.second_brain.skills import _skill_status, _skill_targets


def doctor(home: str | None = None) -> int:
    """Read-only health check for the second-brain kit and its dependencies.

    Returns 1 when the kit or a hard dependency is unhealthy;
    returns 0 with warnings when only optional components are missing.
    """
    paths = _paths(home)
    problems = False

    vault_path = paths.vault.resolve()

    print(f"home: {paths.home_root}")
    print(f"vault: {vault_path}")
    print()

    if not vault_path.is_dir():
        print("✗ vault missing")
        return 1
    print("✓ vault exists")

    manifest = core.load_existing_install_manifest(paths.manifest)
    if manifest and manifest.get("status") == "incomplete":
        phase = manifest.get("phase", "unknown")
        print(f"⚠ install incomplete during {phase} setup")
        print("  fix: vibe kits second-brain install --yes")
        problems = True

    def _check_paths(label: str, items: list[str], is_file: bool) -> None:
        nonlocal problems
        check = (Path.is_file if is_file else Path.is_dir)
        print(f"\n-- {label} --")
        missing = [i for i in items if not check(vault_path / i)]
        if missing:
            print(f"✗ missing {label}:")
            for m in missing:
                print(f"  {m}")
            problems = True
        else:
            print(f"✓ all {label} present")

    print("\n-- prerequisites --")
    if not shutil.which("git"):
        print("✗ git: not found")
        print("  fix: sudo apt install git  # macOS: brew install git")
        return 1
    print("✓ git: found")

    _check_paths("vault directories", VAULT_DIRS, is_file=False)
    _check_paths("seed pages", SEED_PAGES, is_file=True)

    print("\n-- git --")
    if (vault_path / ".git").is_dir():
        print("✓ git repo present")
    else:
        print("✗ git repo not found")
        print("  fix: re-run install to initialize the vault git repository")

    print("\n-- qmd --")
    qmd_path = shutil.which("qmd")
    collection_match = False
    if not qmd_path:
        ok_node, msg_node = _check_min_version("node", ["--version"], QMD_MIN_NODE_MAJOR)
        if not ok_node:
            print(f"✗ {msg_node}")
            print(f"  fix: install Node.js {QMD_MIN_NODE_MAJOR}+ via nvm or https://nodejs.org")
            return 1
        ok_npm, msg_npm = _check_min_version("npm", ["--version"], 9)
        if not ok_npm:
            print(f"✗ {msg_npm}")
            print(f"  fix: upgrade Node.js (npm is bundled); nvm: nvm install {QMD_MIN_NODE_MAJOR}")
            return 1
        print("✗ qmd not found")
        print("  fix: npm install -g @tobilu/qmd")
    else:
        print(f"✓ qmd: {qmd_path}")
        try:
            collection_match, collection_error = _qmd_collection_status(vault_path)
            if collection_error:
                print("✗ qmd collection inspection failed")
                print(f"  stderr: {collection_error}")
            else:
                wiki_collection_path = (vault_path / "wiki").resolve()
                if collection_match:
                    print(f"✓ qmd collection matches {wiki_collection_path}")
                else:
                    print(f"✗ no qmd collection matches {wiki_collection_path}")
        except Exception as exc:
            print(f"✗ qmd collection inspection error: {exc}")

        print("\n-- qmd runtime --")
        try:
            runtime = subprocess.run(
                ["qmd", "doctor"], capture_output=True, text=True, timeout=30
            )
            details = "\n".join(
                part.strip() for part in (runtime.stdout, runtime.stderr) if part.strip()
            )
            if runtime.returncode != 0:
                print("⚠ qmd runtime unavailable")
            if details:
                print(details)
                if "readonly database" in details.lower():
                    print("  note: re-run qmd doctor from your normal host shell if an AI sandbox mounts its cache read-only")
            elif runtime.returncode == 0:
                print("✓ qmd runtime diagnostics completed")
        except Exception as exc:
            print(f"⚠ qmd runtime unavailable: {exc}")

    if not qmd_path or not collection_match:
        wiki_path = vault_path / "wiki"
        print(f"  fix: qmd collection add {wiki_path} --name second-brain")
        problems = True

    knowledge_pages = [
        path for path in (vault_path / "wiki").rglob("*.md")
        if path.relative_to(vault_path).as_posix() not in SEED_PAGES
    ]
    if not knowledge_pages:
        print("ℹ curated wiki is empty; capture or promote a durable outcome to begin")

    print("\n-- obsidian --")
    if shutil.which("obsidian"):
        print("✓ obsidian available")
    else:
        print("⚠ obsidian not found (visual client; optional)")

    print("\n-- memory compiler --")
    if (paths.home_root / ".qmd" / "config.yaml").exists():
        print("✓ memory compiler configured")
    else:
        print("ℹ memory compiler: not configured (optional)")

    print("\n-- agent binaries --")
    for binary, label in [
        ("claude", "Claude Code"),
        ("opencode", "OpenCode"),
        ("codex", "Codex CLI"),
        ("cursor", "Cursor"),
    ]:
        found = shutil.which(binary)
        if found:
            print(f"✓ {binary} ({label}): {found}")
        else:
            print(f"⚠ {binary}: not found ({label})")

    print("\n-- other agents --")
    print("ℹ hermes: config path unverified (docs/sample only)")

    def _check_config(label: str, path: Path, parse) -> None:
        nonlocal problems
        if not path.exists():
            print(f"ℹ {label}: absent")
            return
        try:
            parse(path.read_text(encoding="utf-8"))
            print(f"✓ {label}: valid")
        except Exception as exc:
            print(f"✗ {label}: invalid ({exc})")
            problems = True

    print("\n-- agent configs --")
    _check_config("settings.json", paths.claude_dir / "settings.json", json.loads)
    _check_config(
        "opencode.jsonc",
        paths.opencode_config_dir / "opencode.jsonc",
        ms.parse_jsonc,
    )
    _check_config("config.toml", paths.codex_dir / "config.toml", tomllib.loads)
    _check_config("hooks.json", paths.cursor_dir / "hooks.json", json.loads)

    # OpenCode MCP status (non-fatal warnings)
    opencode_path = paths.opencode_config_dir / "opencode.jsonc"
    if opencode_path.exists():
        try:
            opencode_config = ms.parse_jsonc(
                opencode_path.read_text(encoding="utf-8")
            )
            if isinstance(opencode_config.get("mcpServers"), dict) and "qmd" in opencode_config["mcpServers"]:
                if _is_legacy_kit_owned_qmd_mcp(opencode_config["mcpServers"]["qmd"]):
                    print(
                        "  opencode.jsonc: legacy mcpServers.qmd found;"
                        " install/diff will migrate to mcp.qmd"
                    )
            mcp = opencode_config.get("mcp")
            if mcp is not None and not isinstance(mcp, dict):
                print(
                    "  opencode.jsonc: mcp is not an object;"
                    " qmd MCP cannot be added"
                )
            elif isinstance(mcp, dict) and "qmd" in mcp:
                if not _is_expected_opencode_qmd_mcp(mcp["qmd"]):
                    print(
                        "  opencode.jsonc: qmd MCP is custom"
                        " (will not be overwritten)"
                    )
        except Exception:
            pass  # _check_config already reported parse failures

    def _has_qmd_entry(entries: object) -> bool:
        return isinstance(entries, dict) and "qmd" in entries

    print("\n-- qmd MCP registration --")

    claude_has_qmd = False
    claude_settings_path = paths.claude_dir / "settings.json"
    if claude_settings_path.exists():
        try:
            claude_has_qmd = _has_qmd_entry(
                json.loads(claude_settings_path.read_text(encoding="utf-8")).get("mcpServers")
            )
        except json.JSONDecodeError:
            pass
    print(f"{'✓' if claude_has_qmd else 'ℹ'} Claude Code: {'registered' if claude_has_qmd else 'not registered'} (settings.json)")

    codex_config_path = paths.codex_dir / "config.toml"
    codex_has_qmd = codex_config_path.exists() and CODEX_TOML_SECTION in codex_config_path.read_text(encoding="utf-8")
    print(f"{'✓' if codex_has_qmd else 'ℹ'} Codex CLI: {'registered' if codex_has_qmd else 'not registered'} (config.toml)")

    cursor_mcp_path = paths.cursor_dir / "mcp.json"
    cursor_has_qmd = False
    if cursor_mcp_path.exists():
        try:
            cursor_has_qmd = _has_qmd_entry(
                json.loads(cursor_mcp_path.read_text(encoding="utf-8")).get("mcpServers")
            )
        except json.JSONDecodeError:
            pass
    print(f"{'✓' if cursor_has_qmd else 'ℹ'} Cursor: {'registered' if cursor_has_qmd else 'not registered'} (mcp.json)")

    opencode_has_qmd = False
    if opencode_path.exists():
        try:
            oc_config = ms.parse_jsonc(opencode_path.read_text(encoding="utf-8"))
            opencode_has_qmd = _has_qmd_entry(oc_config.get("mcp")) or _has_qmd_entry(oc_config.get("mcpServers"))
        except Exception:
            pass
    print(f"{'✓' if opencode_has_qmd else 'ℹ'} OpenCode: {'registered' if opencode_has_qmd else 'not registered'} (opencode.jsonc)")

    def _doctor_print_hook(agent: HookAgent) -> None:
        script_path = agent.script_dir_fn(paths) / HOOK_SCRIPT_REL
        if script_path.is_file():
            print(f"✓ {agent.event_label} hook script: {script_path}")
        else:
            print(f"ℹ {agent.event_label} hook script: not installed (optional; enable via 'vibe kits second-brain enable-hook')")
        if agent.already_installed_fn(paths):
            print(f"✓ {agent.event_label} hook registered in {agent.registered_where}")
        else:
            print(f"ℹ {agent.event_label} hook: not registered in {agent.registered_where}")

    def _doctor_print_section(spec: PersonaSection) -> None:
        path = spec.path_fn(paths)
        if _marked_section_present(path, spec.begin_marker):
            print(f"✓ {spec.label} second-brain section present")
        elif path.exists():
            print(f"⚠ {spec.label} exists but second-brain section is missing (fix: vibe kits second-brain enable-hook)")
        else:
            print(f"ℹ {spec.label}: absent (second-brain section not installed)")

    print("\n-- proactive context (Claude Code) --")
    _doctor_print_hook(CLAUDE_HOOK_AGENT)
    _doctor_print_section(CLAUDE_PERSONA_SECTION)

    print("\n-- proactive context (Codex CLI) --")
    _doctor_print_hook(CODEX_HOOK_AGENT)
    _doctor_print_section(CODEX_PERSONA_SECTION)

    print("\n-- proactive context (Cursor) --")
    _doctor_print_hook(CURSOR_HOOK_AGENT)
    if _cursor_rule_up_to_date(paths):
        print(f"✓ rule file up to date: {paths.cursor_dir / CURSOR_RULE_REL}")
    elif (paths.cursor_dir / CURSOR_RULE_REL).exists():
        print("⚠ rule file present but stale (fix: vibe kits second-brain enable-hook)")
    else:
        print("ℹ rule file: not installed (optional)")

    print("\n-- proactive context (OpenCode) --")
    print("ℹ OpenCode has no session-start context-injection API; AGENTS.md section only, no hook")
    _doctor_print_section(OPENCODE_PERSONA_SECTION)

    print("\n-- second-brain skill --")
    for target in _skill_targets(paths):
        status = _skill_status(paths, target)
        icon = "✓" if status == "up to date" else "⚠"
        print(f"{icon} {target}: {status}")

    vault_str = str(vault_path)
    if "\\\\wsl$" in vault_str or vault_str.startswith("/mnt/"):
        print("\n⚠ WSL2 detected: paths may behave differently across OS boundaries")

    return 1 if problems else 0
