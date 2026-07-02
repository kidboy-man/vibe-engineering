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

KIT_NAME = "second-brain"
MANIFEST_FILE = core.MANIFEST_FILE

VAULT_DIRS = [
    "raw/assets",
    "inbox",
    "wiki/sources/learning",
    "wiki/sources/journal",
    "wiki/entities/projects",
    "wiki/concepts/backend",
    "wiki/concepts/ai-engineering",
    "wiki/concepts/pkm",
    "wiki/concepts/personal",
    "wiki/synthesis",
    "output",
    ".claude",
]

SEED_PAGES = [
    "wiki/index.md",
    "wiki/log.md",
    "wiki/hot.md",
]

GITIGNORE_ENTRIES = [
    "node_modules/",
    ".qmd/",
    ".claude/settings.local.json",
]

HOOK_SCRIPT_REL = "hooks/second-brain-context.py"
SESSIONSTART_EVENT = "SessionStart"
CURSOR_SESSIONSTART_EVENT = "sessionStart"
CURSOR_RULE_REL = "rules/second-brain.mdc"

CLAUDE_MD_BEGIN_MARKER = "<!-- vibe-engineering second-brain:begin -->\n"
CLAUDE_MD_END_MARKER = "<!-- vibe-engineering second-brain:end -->\n"

CODEX_INSTRUCTIONS_BEGIN_MARKER = "<!-- vibe-engineering second-brain (codex):begin -->\n"
CODEX_INSTRUCTIONS_END_MARKER = "<!-- vibe-engineering second-brain (codex):end -->\n"

OPENCODE_AGENTS_BEGIN_MARKER = "<!-- vibe-engineering second-brain (opencode):begin -->\n"
OPENCODE_AGENTS_END_MARKER = "<!-- vibe-engineering second-brain (opencode):end -->\n"


@dataclass(frozen=True)
class KitPaths:
    home_root: Path
    vault: Path
    template: Path
    manifest: Path
    claude_dir: Path
    opencode_config_dir: Path
    codex_dir: Path
    cursor_dir: Path


def _template_dir() -> Path:
    return Path(__file__).resolve().parent / "templates" / "second_brain"


def _paths(home: str | None = None) -> KitPaths:
    home_path = Path(home).expanduser() if home else Path.home()

    vault_env = os.environ.get("VIBE_SECOND_BRAIN_PATH")
    vault = Path(vault_env) if vault_env else home_path / "second-brain"

    template = _template_dir()

    return KitPaths(
        home_root=home_path,
        vault=vault,
        template=template,
        manifest=vault / MANIFEST_FILE,
        claude_dir=home_path / ".claude",
        opencode_config_dir=home_path / ".config" / "opencode",
        codex_dir=home_path / ".codex",
        cursor_dir=home_path / ".cursor",
    )


def _validate_configs(paths: KitPaths) -> bool:
    """Preflight: parse existing agent configs to catch invalid JSON/JSONC early."""
    settings_json = paths.claude_dir / "settings.json"
    if settings_json.exists():
        try:
            json.loads(settings_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print("invalid settings.json")
            return False

    opencode_jsonc = paths.opencode_config_dir / "opencode.jsonc"
    if opencode_jsonc.exists():
        from agents.merge_strategies import parse_jsonc
        try:
            parse_jsonc(opencode_jsonc.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            print("invalid opencode.jsonc")
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
    print(f"would write manifest: {paths.manifest}")
    print()
    print("dry run: no files written")


def _seed_page(src: Path, dst: Path) -> bool:
    """Copy seed page from template if target does not exist. Never overwrite."""
    if dst.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(src.read_bytes())
    return True


def _gitignore_diff(vault: Path) -> tuple[bool, list[str]]:
    """Return (gitignore_exists, entries_to_add). Empty list = nothing to add."""
    gitignore = vault / ".gitignore"
    if not gitignore.exists():
        return False, list(GITIGNORE_ENTRIES)
    existing = set(gitignore.read_text(encoding="utf-8").splitlines())
    return True, [e for e in GITIGNORE_ENTRIES if e not in existing]


def _merge_gitignore(vault: Path) -> None:
    """Write or merge .gitignore entries. Append missing; never duplicate."""
    exists, new_entries = _gitignore_diff(vault)
    gitignore = vault / ".gitignore"
    if not exists:
        gitignore.write_text("\n".join(GITIGNORE_ENTRIES) + "\n", encoding="utf-8")
        return
    content = gitignore.read_text(encoding="utf-8")
    for entry in new_entries:
        if not content.endswith("\n"):
            content += "\n"
        content += entry + "\n"
    gitignore.write_text(content, encoding="utf-8")


def _git_init(vault: Path) -> None:
    """Initialize git repo if .git does not exist. Idempotent, no network."""
    git_dir = vault / ".git"
    if git_dir.exists():
        return
    subprocess.run(
        ["git", "init", "-q", str(vault)],
        check=False,
        capture_output=True,
    )


def _vault_foreign_files(vault_path: Path, manifest_path: Path) -> list[Path]:
    """Return sample of files in vault when manifest is absent (foreign vault)."""
    if not vault_path.exists():
        return []
    if manifest_path.exists():
        return []  # our vault — idempotent re-install, no warning
    _SKIP = {".git", "node_modules"}
    files: list[Path] = []
    for p in vault_path.rglob("*"):
        if any(part in _SKIP for part in p.parts):
            continue
        if p.is_file():
            files.append(p)
            if len(files) == 5:
                break
    return files


def _confirm(prompt: str) -> bool:
    """Prompt for y/N. Returns False on EOF (non-interactive stdin)."""
    try:
        return input(prompt).strip().lower() in ("y", "yes")
    except EOFError:
        return False


def _check_min_version(binary: str, args: list[str], min_major: int) -> tuple[bool, str]:
    """Return (ok, message). ok=False when binary missing or major version < min_major."""
    if not shutil.which(binary):
        return False, f"{binary}: not found"
    try:
        out = subprocess.run([binary] + args, capture_output=True, text=True, timeout=5)
        m = re.search(r"(\d+)\.", out.stdout + out.stderr)
        if m and int(m.group(1)) < min_major:
            return False, f"{binary}: major version {m.group(1)} < {min_major}"
    except Exception:
        pass
    return True, ""


def _setup_qmd(vault_path: Path, yes: bool = False) -> int:
    """Install qmd via npm if absent, then register the wiki collection."""
    if shutil.which("qmd"):
        return 0  # already installed — silent
    npm = shutil.which("npm")
    if not npm:
        print("[second-brain] qmd not found and npm not available.")
        print("  Install Node.js 20+, then: npm install -g @tobilu/qmd")
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
    wiki_path = vault_path / "wiki"
    subprocess.run(["qmd", "collection", "add", str(wiki_path), "--name", "second-brain"], check=False)
    subprocess.run(["qmd", "update"], check=False)
    return 0


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
    config_path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    print("merged qmd MCP into opencode.jsonc")


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
    config_path.write_text(merged, encoding="utf-8")
    if action == "create":
        print(f"created {config_path} with qmd MCP section")
    else:
        print("merged qmd MCP into config.toml")


@dataclass(frozen=True)
class HookAgent:
    """A SessionStart-equivalent hook target (Claude Code, Codex CLI, Cursor)."""

    label: str
    event_label: str
    registered_where: str
    script_dir_fn: Callable[[KitPaths], Path]
    already_installed_fn: Callable[[KitPaths], bool]


@dataclass(frozen=True)
class PersonaSection:
    """A marked-section merge target (persona/instructions file)."""

    label: str
    path_fn: Callable[[KitPaths], Path]
    fragment_name: str
    begin_marker: str
    end_marker: str


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


def _merge_persona_section(paths: KitPaths, spec: PersonaSection) -> None:
    path = spec.path_fn(paths)
    fragment = (paths.template / spec.fragment_name).read_text(encoding="utf-8")
    existing = path.read_text(encoding="utf-8") if path.exists() else None
    merged, action = ms.marked_section_strategy(fragment, existing, spec.begin_marker, spec.end_marker)
    if action == "unchanged":
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(merged, encoding="utf-8")
    verb = "created" if action == "create" else "merged"
    print(f"{verb} second-brain section in {spec.label}")


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


CLAUDE_PERSONA_SECTION = PersonaSection(
    "CLAUDE.md", lambda p: p.claude_dir / "CLAUDE.md", "claude_md_section.md", CLAUDE_MD_BEGIN_MARKER, CLAUDE_MD_END_MARKER
)
CODEX_PERSONA_SECTION = PersonaSection(
    "instructions.md",
    lambda p: p.codex_dir / "instructions.md",
    "codex_instructions_section.md",
    CODEX_INSTRUCTIONS_BEGIN_MARKER,
    CODEX_INSTRUCTIONS_END_MARKER,
)
OPENCODE_PERSONA_SECTION = PersonaSection(
    "opencode AGENTS.md",
    lambda p: p.opencode_config_dir / "AGENTS.md",
    "opencode_agents_section.md",
    OPENCODE_AGENTS_BEGIN_MARKER,
    OPENCODE_AGENTS_END_MARKER,
)
PERSONA_SECTIONS = [CLAUDE_PERSONA_SECTION, CODEX_PERSONA_SECTION, OPENCODE_PERSONA_SECTION]

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


def _merge_claude_md_section(paths: KitPaths) -> None:
    """Merge the second-brain marked section into ~/.claude/CLAUDE.md."""
    _merge_persona_section(paths, CLAUDE_PERSONA_SECTION)


def _merge_codex_instructions_section(paths: KitPaths) -> None:
    """Merge the second-brain marked section into ~/.codex/instructions.md."""
    _merge_persona_section(paths, CODEX_PERSONA_SECTION)


def _merge_opencode_agents_section(paths: KitPaths) -> None:
    """Merge the second-brain marked section into OpenCode's AGENTS.md.

    Uses a marker distinct from the ``opencode`` kit's own persona-section
    marker, so both kits' merges coexist in the same file.
    """
    _merge_persona_section(paths, OPENCODE_PERSONA_SECTION)


def _marked_section_present(path: Path, begin_marker: str) -> bool:
    return path.exists() and begin_marker in path.read_text(encoding="utf-8")


def _section_dry_run_label(path: Path, begin_marker: str) -> str:
    return "already present" if _marked_section_present(path, begin_marker) else "would create/merge"


def _cursor_rule_up_to_date(paths: KitPaths) -> bool:
    rule_dst = paths.cursor_dir / CURSOR_RULE_REL
    if not rule_dst.exists():
        return False
    rule_src = paths.template / CURSOR_RULE_REL
    return rule_dst.read_text(encoding="utf-8") == rule_src.read_text(encoding="utf-8")


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


def _manifest_state(managed_files: list[str]) -> dict:
    return core.manifest_state(KIT_NAME, managed_files)


def install(
    home: str | None = None,
    dry_run: bool = False,
    yes: bool = False,
    merge_settings: bool = True,
    setup_deps: bool = True,
    enable_hooks: bool = True,
    **kwargs,
) -> int:
    paths = _paths(home)

    # Preflight: validate existing agent configs before any writes.
    if not _validate_configs(paths):
        return 1

    print(
        "second-brain: "
        + ("existing installation detected, updating" if paths.manifest.exists() else "fresh install")
    )
    print(f"hook: {'already installed' if _all_proactive_context_installed(paths) else 'not installed'}")

    if dry_run:
        _print_dry_run(paths)
        if merge_settings:
            print("would merge qmd MCP into agent configs (Claude, OpenCode, Codex)")
            print("  Cursor and Hermes: no config mutation")
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

    if merge_settings:
        _merge_claude_config(paths)
        _merge_opencode_config(paths)
        _merge_codex_config(paths)
        if enable_hooks:
            _offer_proactive_context(paths, yes=yes)
        else:
            print("hooks: skipped (--no-hooks)")

    if setup_deps:
        _setup_qmd(paths.vault, yes=yes)

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
        ok_node, msg_node = _check_min_version("node", ["--version"], 20)
        if not ok_node:
            print(f"✗ {msg_node}")
            print("  fix: install Node.js 20+ via nvm or https://nodejs.org")
            return 1
        ok_npm, msg_npm = _check_min_version("npm", ["--version"], 9)
        if not ok_npm:
            print(f"✗ {msg_npm}")
            print("  fix: upgrade Node.js (npm is bundled); nvm: nvm install 20")
            return 1
        print("✗ qmd not found")
        print("  fix: npm install -g @tobilu/qmd")
    else:
        print(f"✓ qmd: {qmd_path}")
        try:
            result = subprocess.run(
                ["qmd", "collection", "list"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                print("✗ qmd collection list failed")
                print(f"  stderr: {(result.stderr or '').strip()}")
            else:
                wiki_collection_str = str(vault_path / "wiki")
                if wiki_collection_str in result.stdout:
                    print(f"✓ qmd collection matches {wiki_collection_str}")
                    collection_match = True
                else:
                    print(f"✗ no qmd collection matches {wiki_collection_str}")
        except Exception as exc:
            print(f"✗ qmd collection list error: {exc}")

    if not qmd_path or not collection_match:
        wiki_path = vault_path / "wiki"
        print(f"  fix: qmd collection add {wiki_path} --name second-brain")
        return 1

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

    # Manifest
    manifest = paths.manifest
    if manifest.exists():
        print(f"manifest: exists at {manifest}")
    else:
        print(f"manifest: would create at {manifest}")
    print()

    return 0


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

    codex_instructions_path = paths.codex_dir / "instructions.md"
    if _marked_section_present(codex_instructions_path, CODEX_INSTRUCTIONS_BEGIN_MARKER):

        def _mutate_codex_instructions(text: str) -> tuple[str | None, bool]:
            return ms.strip_marked_section(text, CODEX_INSTRUCTIONS_BEGIN_MARKER, CODEX_INSTRUCTIONS_END_MARKER)

        specs.append((codex_instructions_path, "second-brain section from instructions.md", _mutate_codex_instructions))

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

    if not specs and not remove_cursor_rule:
        print("nothing to uninstall")
        return 0

    if dry_run:
        for _path, label, _fn in specs:
            print(f"would remove {label}")
        if remove_cursor_rule:
            print(f"would remove {CURSOR_RULE_REL} (if unchanged from template)")
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

    return 0
