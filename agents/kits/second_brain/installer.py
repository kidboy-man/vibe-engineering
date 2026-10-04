"""Second-brain kit installer — vault scaffold, seed pages, .gitignore, git init,
and agent config adapters (Claude Code, OpenCode, Codex CLI)."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib  # type: ignore[no-redef]

from agents import installer_core as core
from agents import merge_strategies as ms
from agents.secret_policies import LOCAL_ONLY_KEYS, is_secret_key

from agents.kits.second_brain.paths import (  # noqa: F401
    KIT_NAME,
    MANIFEST_FILE,
    VAULT_DIRS,
    SEED_PAGES,
    GITIGNORE_ENTRIES,
    HOOK_SCRIPT_REL,
    SESSIONSTART_EVENT,
    CURSOR_SESSIONSTART_EVENT,
    CURSOR_RULE_REL,
    SKILL_ROOT_REL,
    QMD_MIN_NODE_MAJOR,
    QMD_COLLECTION_NAME,
    CLAUDE_MD_BEGIN_MARKER,
    CLAUDE_MD_END_MARKER,
    CODEX_INSTRUCTIONS_BEGIN_MARKER,
    CODEX_INSTRUCTIONS_END_MARKER,
    OPENCODE_AGENTS_BEGIN_MARKER,
    OPENCODE_AGENTS_END_MARKER,
    KitPaths,
    _template_dir,
    _paths,
)


def _validate_configs(
    paths: KitPaths, merge_settings: bool, enable_hooks: bool
) -> bool:
    """Preflight every config this install would modify before writing anything."""
    targets: list[tuple[Path, Callable[[str], object]]] = []
    if merge_settings:
        targets.extend(
            [
                (paths.claude_dir / "settings.json", json.loads),
                (paths.opencode_config_dir / "opencode.jsonc", ms.parse_jsonc),
                (paths.codex_dir / "config.toml", tomllib.loads),
                (paths.cursor_dir / "mcp.json", json.loads),
            ]
        )
    if enable_hooks:
        targets.extend(
            [
                (paths.claude_dir / "settings.json", json.loads),
                (paths.codex_dir / "config.toml", tomllib.loads),
                (paths.cursor_dir / "hooks.json", json.loads),
            ]
        )

    checked: set[Path] = set()
    for path, parse in targets:
        if path in checked or not path.exists():
            continue
        checked.add(path)
        try:
            value = parse(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError, tomllib.TOMLDecodeError):
            print(f"invalid {path.name}")
            return False
        if not isinstance(value, dict):
            print(f"invalid {path.name}: root is not an object")
            return False
    return True


def _print_dry_run(paths: KitPaths) -> None:
    """Print planned actions without creating anything."""
    print(f"home: {paths.home_root}")
    print(f"vault: {paths.vault}")
    print(f"template: {paths.template}")
    print()
    print("would create vault directories:")
    for d in VAULT_DIRS:
        print(f"  {d}")
    print()
    print("would seed pages (create-if-absent):")
    for rel in SEED_PAGES:
        target = paths.vault / rel
        status = "create" if not target.exists() else "skip (exists)"
        print(f"  {rel} [{status}]")
    print()
    exists, new_entries = _gitignore_diff(paths.vault)
    if not exists:
        print("would create .gitignore:")
        for e in GITIGNORE_ENTRIES:
            print(f"  {e}")
    elif new_entries:
        print("would append to .gitignore:")
        for e in new_entries:
            print(f"  + {e}")
    else:
        print(".gitignore: all entries already present")
    print()
    if not (paths.vault / ".git").exists():
        print(f"would git init in {paths.vault}")
    else:
        print("git already initialized")
    print()
    print("second-brain skill:")
    for target in _skill_targets(paths):
        status = _skill_status(paths, target)
        print(f"  {target} [{'would install' if status == 'missing' else status}]")
    print()
    print(f"would write manifest: {paths.manifest}")
    print()
    print("dry run: no files written")


from agents.kits.second_brain.vault import (  # noqa: F401
    _seed_page,
    _gitignore_diff,
    _merge_gitignore,
    _git_init,
    _vault_foreign_files,
)


def _confirm(prompt: str) -> bool:
    """Prompt for y/N. Returns False on EOF (non-interactive stdin)."""
    try:
        return input(prompt).strip().lower() in ("y", "yes")
    except EOFError:
        return False


from agents.kits.second_brain.qmd import (  # noqa: F401
    _check_min_version,
    _qmd_collection_status,
)


def _setup_qmd(vault_path: Path, yes: bool = False) -> int:
    """Ensure qmd, the vault collection, and its BM25 index are ready."""
    if not shutil.which("qmd"):
        ok_node, msg_node = _check_min_version("node", ["--version"], QMD_MIN_NODE_MAJOR)
        if not ok_node:
            print(f"[second-brain] {msg_node}")
            print(f"  Install Node.js {QMD_MIN_NODE_MAJOR}+ before installing qmd.")
            return 1
        npm = shutil.which("npm")
        if not npm:
            print("[second-brain] qmd not found and npm not available.")
            print(f"  Install Node.js {QMD_MIN_NODE_MAJOR}+, then: npm install -g @tobilu/qmd")
            return 1
        print("[second-brain] qmd not found (required for search).")
        print("  Install now? Runs 'npm install -g @tobilu/qmd' (network + global install).")
        if not yes and not _confirm("  Proceed? [y/N] "):
            print("  Skipped. Run manually: npm install -g @tobilu/qmd")
            return 1
        r = subprocess.run([npm, "install", "-g", "@tobilu/qmd"], check=False)
        if r.returncode != 0:
            print("[second-brain] npm install failed. Run manually: npm install -g @tobilu/qmd")
            return 1

    collection_match, collection_error = _qmd_collection_status(vault_path)
    if collection_error:
        print("[second-brain] qmd collection inspection failed.")
        print(f"  {collection_error}")
        return 1

    wiki_path = (vault_path / "wiki").resolve()
    if not collection_match:
        added = subprocess.run(
            ["qmd", "collection", "add", str(wiki_path), "--name", QMD_COLLECTION_NAME],
            check=False,
            capture_output=True,
            text=True,
        )
        if added.returncode != 0:
            print("[second-brain] qmd collection add failed.")
            if added.stderr:
                print(f"  {added.stderr.strip()}")
            return 1

    updated = subprocess.run(
        ["qmd", "update"], check=False, capture_output=True, text=True
    )
    if updated.returncode != 0:
        print("[second-brain] qmd update failed.")
        if updated.stderr:
            print(f"  {updated.stderr.strip()}")
        return 1
    return 0


from agents.kits.second_brain.skills import (  # noqa: F401
    _skill_source_dirs,
    _skill_root_targets,
    _skill_targets,
    _skill_source_for_target,
    _skill_dir_status,
    _install_skill,
    _skill_status,
)


from agents.kits.second_brain.mcp import (  # noqa: F401
    QMD_MCP_SNIPPET_JSON,
    OPENCODE_QMD_MCP_ENTRY,
    _is_legacy_kit_owned_qmd_mcp,
    _is_expected_opencode_qmd_mcp,
    _merge_opencode_qmd_mcp,
    CODEX_TOML_SECTION,
    CODEX_TOML_BODY,
    _strip_qmd_mcp,
    _strip_opencode_qmd_mcp,
)


from agents.kits.second_brain.agent_configs import (  # noqa: F401
    CLAUDE_SECRET_KEYS,
    _merge_claude_config,
    _merge_opencode_config,
    _merge_cursor_config,
    _merge_codex_config,
)


from agents.kits.second_brain.hooks import (  # noqa: F401
    HookAgent,
    _install_hook_script_file,
    _json_hook_already_installed,
    _hook_command,
    _codex_hook_command,
    _cursor_hook_command,
    _hook_already_installed,
    _codex_hook_block,
    _codex_hook_identity,
    _codex_hook_already_installed,
    _cursor_hook_already_installed,
    CLAUDE_HOOK_AGENT,
    CODEX_HOOK_AGENT,
    CURSOR_HOOK_AGENT,
    HOOK_AGENTS,
    _install_session_hook,
    _install_codex_hook,
    _install_cursor_hook,
    _install_cursor_rule,
    _cursor_rule_up_to_date,
)


from agents.kits.second_brain.personas import (  # noqa: F401
    PersonaSection,
    _merge_persona_section,
    CLAUDE_PERSONA_SECTION,
    CODEX_PERSONA_SECTION,
    OPENCODE_PERSONA_SECTION,
    PERSONA_SECTIONS,
    _merge_claude_md_section,
    _merge_codex_instructions_section,
    _merge_opencode_agents_section,
    _marked_section_present,
    _section_dry_run_label,
)


def _all_proactive_context_installed(paths: KitPaths) -> bool:
    """True only when every supported agent's hook/section is already wired."""
    return (
        all(agent.already_installed_fn(paths) for agent in HOOK_AGENTS)
        and all(_marked_section_present(spec.path_fn(paths), spec.begin_marker) for spec in PERSONA_SECTIONS)
        and _cursor_rule_up_to_date(paths)
    )


def _enable_proactive_context(paths: KitPaths, dry_run: bool = False) -> int:
    """Install hook + persona-section wiring for all supported agents (idempotent).

    Claude Code, Codex CLI, and Cursor each get a SessionStart-equivalent
    hook plus a persona/instructions section; OpenCode gets an AGENTS.md
    section only (no session-start context-injection API is documented for
    OpenCode). Each agent's config is handled independently — one agent's
    invalid config never blocks the others.
    """
    if dry_run:
        for agent, spec in ((CLAUDE_HOOK_AGENT, CLAUDE_PERSONA_SECTION), (CODEX_HOOK_AGENT, CODEX_PERSONA_SECTION)):
            hook_state = "already registered" if agent.already_installed_fn(paths) else "would register"
            print(f"{agent.label} {agent.event_label} hook: {hook_state}")
            print(f"{spec.label} second-brain section: {_section_dry_run_label(spec.path_fn(paths), spec.begin_marker)}")

        cursor_hook_state = "already registered" if CURSOR_HOOK_AGENT.already_installed_fn(paths) else "would register"
        print(f"{CURSOR_HOOK_AGENT.label} {CURSOR_HOOK_AGENT.event_label} hook: {cursor_hook_state}")
        print(f"Cursor rule file: {'up to date' if _cursor_rule_up_to_date(paths) else 'would create/update'}")

        print(
            f"{OPENCODE_PERSONA_SECTION.label} second-brain section: "
            + _section_dry_run_label(OPENCODE_PERSONA_SECTION.path_fn(paths), OPENCODE_PERSONA_SECTION.begin_marker)
        )
        return 0

    _install_session_hook(paths)
    _merge_claude_md_section(paths)

    _install_codex_hook(paths)
    _merge_codex_instructions_section(paths)

    _install_cursor_hook(paths)
    _install_cursor_rule(paths)

    _merge_opencode_agents_section(paths)
    return 0


def _offer_proactive_context(paths: KitPaths, yes: bool) -> None:
    """Detect current hook state and prompt (unless already installed/``yes``)."""
    if _all_proactive_context_installed(paths):
        print("hook: already installed")
        _enable_proactive_context(paths)
        return
    print("hook: not installed")
    prompt = (
        "Enable proactive second-brain context? Adds a SessionStart-equivalent "
        "hook (auto-loads hot.md/index.md every session) plus a persona-file "
        "section for Claude Code, Codex CLI, and Cursor, and an AGENTS.md "
        "section for OpenCode (no hook API is available for OpenCode)."
    )
    if not yes and not _confirm(f"{prompt} [y/N] "):
        print("skipped hook/context wiring; enable later via: vibe kits second-brain enable-hook")
        return
    _enable_proactive_context(paths)


def enable_hook(
    home: str | None = None,
    dry_run: bool = False,
    yes: bool = False,
    **kwargs,
) -> int:
    """Standalone verb: enable proactive context wiring for all supported agents.

    Works independently of vault install/presence — hook scripts tolerate a
    missing vault at runtime. Each agent's config is validated independently
    inside its own install function; one agent's invalid config never blocks
    the others.
    """
    paths = _paths(home)

    if dry_run:
        return _enable_proactive_context(paths, dry_run=True)

    _offer_proactive_context(paths, yes=yes)
    return 0


def _manifest_state(
    managed_files: list[str], status: str = "complete", phase: str | None = None
) -> dict:
    state = core.manifest_state(KIT_NAME, managed_files)
    state["status"] = status
    if phase is not None:
        state["phase"] = phase
    return state


def install(
    home: str | None = None,
    dry_run: bool = False,
    yes: bool = False,
    merge_settings: bool = True,
    setup_deps: bool = False,
    enable_hooks: bool = True,
    **kwargs,
) -> int:
    paths = _paths(home)

    # Preflight: validate existing agent configs before any writes.
    if not _validate_configs(paths, merge_settings, enable_hooks):
        return 1

    print(
        "second-brain: "
        + ("existing installation detected, updating" if paths.manifest.exists() else "fresh install")
    )
    print(f"hook: {'already installed' if _all_proactive_context_installed(paths) else 'not installed'}")

    if dry_run:
        _print_dry_run(paths)
        if merge_settings:
            print("would merge qmd MCP into agent configs (Claude, OpenCode, Codex, Cursor)")
            print("  Hermes: no config mutation")
        if enable_hooks:
            _enable_proactive_context(paths, dry_run=True)
        else:
            print("hooks: skipped (--no-hooks)")
        return 0

    # Warn when vault exists with foreign files (no manifest = not our vault).
    foreign = _vault_foreign_files(paths.vault, paths.manifest)
    if foreign:
        print(f"[second-brain] Vault at {paths.vault} already contains files:")
        for f in foreign:
            print(f"  {f.relative_to(paths.vault)}")
        print("Existing files are never overwritten.")
        print(
            f"To use a different path: "
            f"VIBE_SECOND_BRAIN_PATH=/other/path vibe kits second-brain install --yes"
        )
        if not yes and not _confirm("Continue with this vault? [y/N] "):
            return 1

    if not core.confirm("Install/update the second-brain kit?", yes=yes):
        print("aborted")
        return 1

    # Create vault directories.
    for rel in VAULT_DIRS:
        (paths.vault / rel).mkdir(parents=True, exist_ok=True)

    # Seed pages: create-if-absent only.
    template_vault = paths.template / "vault"
    managed: list[str] = []
    for rel in SEED_PAGES:
        src = template_vault / rel
        dst = paths.vault / rel
        if _seed_page(src, dst):
            managed.append(rel)
            print(f"seeded {rel}")

    # .gitignore merge.
    _merge_gitignore(paths.vault)
    managed.append(".gitignore")
    print("merged .gitignore")

    # Git init.
    _git_init(paths.vault)
    print("git repo ready")

    if setup_deps and _setup_qmd(paths.vault, yes=yes) != 0:
        state = _manifest_state(managed, status="incomplete", phase="qmd")
        core.write_text(paths.manifest, json.dumps(state, indent=2) + "\n")
        print("qmd setup incomplete; re-run install after resolving the error")
        return 1

    _install_skill(paths)

    if merge_settings:
        _merge_claude_config(paths)
        _merge_opencode_config(paths)
        _merge_codex_config(paths)
        _merge_cursor_config(paths)
    if enable_hooks:
        _offer_proactive_context(paths, yes=yes)
    else:
        print("hooks: skipped (--no-hooks)")

    # Write runtime manifest.
    core.write_text(paths.manifest, json.dumps(_manifest_state(managed), indent=2) + "\n")
    print(f"wrote {paths.manifest}")
    return 0


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
