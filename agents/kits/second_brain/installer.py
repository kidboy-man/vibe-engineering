"""Second-brain kit installer: public entry points and install orchestration.

The implementation is split into sibling modules (paths, vault, skills, mcp,
agent_configs, hooks, personas, qmd, doctor_cmd, diff_cmd, uninstall_cmd).
Names tests patch (`_confirm`, `_setup_qmd`, `shutil`, `subprocess`, `core`)
and the registry imports resolve here, so this module is the stable surface.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib  # type: ignore[no-redef]

from agents import installer_core as core
from agents import merge_strategies as ms

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


from agents.kits.second_brain.doctor_cmd import (  # noqa: F401
    doctor,
)


from agents.kits.second_brain.diff_cmd import (  # noqa: F401
    diff_kit,
)


from agents.kits.second_brain.uninstall_cmd import (  # noqa: F401
    uninstall,
)
