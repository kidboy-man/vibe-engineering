"""Second-brain kit installer — vault scaffold, seed pages, .gitignore, git init,
and agent config adapters (Claude Code, OpenCode, Codex CLI)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path

from agents import installer_core as core
from agents import merge_strategies as ms

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


@dataclass(frozen=True)
class KitPaths:
    home_root: Path
    vault: Path
    template: Path
    manifest: Path
    claude_dir: Path
    opencode_config_dir: Path
    codex_dir: Path


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
    gitignore = paths.vault / ".gitignore"
    if gitignore.exists():
        existing_lines = set(gitignore.read_text(encoding="utf-8").splitlines())
        new_entries = [e for e in GITIGNORE_ENTRIES if e not in existing_lines]
        if new_entries:
            print("would append to .gitignore:")
            for e in new_entries:
                print(f"  + {e}")
        else:
            print(".gitignore: all entries already present")
    else:
        print("would create .gitignore:")
        for e in GITIGNORE_ENTRIES:
            print(f"  {e}")
    print()
    if not (paths.vault / ".git").exists():
        print(f"would git init in {paths.vault}")
    else:
        print("git already initialized")
    print()
    print(f"would write manifest: {paths.manifest}")
    print()
    print("dry run: no files written")


def _confirm(prompt: str, yes: bool) -> bool:
    return core.confirm(prompt, yes)


def _seed_page(src: Path, dst: Path) -> bool:
    """Copy seed page from template if target does not exist. Never overwrite."""
    if dst.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(src.read_bytes())
    return True


def _merge_gitignore(vault: Path) -> None:
    """Write or merge .gitignore entries. Append missing; never duplicate."""
    gitignore = vault / ".gitignore"
    if gitignore.exists():
        content = gitignore.read_text(encoding="utf-8")
        lines = content.splitlines()
        for entry in GITIGNORE_ENTRIES:
            if entry not in lines:
                if not content.endswith("\n"):
                    content += "\n"
                content += entry + "\n"
    else:
        content = "\n".join(GITIGNORE_ENTRIES) + "\n"
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


QMD_MCP_SNIPPET_JSON: dict = {
    "mcpServers": {
        "qmd": {
            "type": "stdio",
            "command": "qmd",
            "args": ["mcp"],
        }
    }
}

CODEX_TOML_SECTION = "[mcp_servers.qmd]"
CODEX_TOML_BODY = 'type = "stdio"\ncommand = "qmd"\nargs = ["mcp"]\n'

# Mirrors agents/kits/opencode/installer.py:35-50 — keys the kit never overwrites.
OPENCODE_LOCAL_ONLY_KEYS = {
    "model",
    "provider",
    "plugin",
    "mcp",
    "tools",
    "tool",
    "permission",
    "env",
    "agent",
    "experimental",
    "theme",
    "share",
    "autoupdate",
    "instructions",
}

OPENCODE_SECRET_SUBSTRINGS = ("token", "key", "secret", "password", "auth", "credential")

CLAUDE_SECRET_KEYS = {"env"}


def _is_secret_jsonc_key(key: str) -> bool:
    return any(sub in key.lower() for sub in OPENCODE_SECRET_SUBSTRINGS)


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

    merged, changed = ms.jsonc_defaults_strategy(
        QMD_MCP_SNIPPET_JSON, current, OPENCODE_LOCAL_ONLY_KEYS, _is_secret_jsonc_key
    )
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


def _manifest_state(managed_files: list[str]) -> dict:
    return core.manifest_state(KIT_NAME, managed_files)


def install(
    home: str | None = None,
    dry_run: bool = False,
    yes: bool = False,
    merge_settings: bool = True,
) -> int:
    paths = _paths(home)

    # Preflight: validate existing agent configs before any writes.
    if not _validate_configs(paths):
        return 1

    if dry_run:
        _print_dry_run(paths)
        if merge_settings:
            print("would merge qmd MCP into agent configs (Claude, OpenCode, Codex)")
            print("  Cursor and Hermes: no config mutation")
        return 0

    if not _confirm("Install/update the second-brain kit?", yes=yes):
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

    print("\n-- vault directories --")
    missing_dirs = [d for d in VAULT_DIRS if not (vault_path / d).is_dir()]
    if missing_dirs:
        print("✗ missing directories:")
        for d in missing_dirs:
            print(f"  {d}")
        problems = True
    else:
        print("✓ all directories present")

    print("\n-- seed pages --")
    missing_pages = [p for p in SEED_PAGES if not (vault_path / p).is_file()]
    if missing_pages:
        print("✗ missing seed pages:")
        for p in missing_pages:
            print(f"  {p}")
        problems = True
    else:
        print("✓ all seed pages present")

    print("\n-- qmd --")
    qmd_path = shutil.which("qmd")
    collection_match = False
    if not qmd_path:
        print("✗ qmd not found")
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
    ]:
        found = shutil.which(binary)
        if found:
            print(f"✓ {binary} ({label}): {found}")
        else:
            print(f"⚠ {binary}: not found ({label})")

    print("\n-- other agents --")
    print("ℹ hermes: config path unverified (docs/sample only)")
    print("ℹ cursor: project-local .cursor/rules/*.mdc recommended")

    print("\n-- agent configs --")
    settings_json = paths.claude_dir / "settings.json"
    if settings_json.exists():
        try:
            json.loads(settings_json.read_text(encoding="utf-8"))
            print("✓ settings.json: valid")
        except json.JSONDecodeError as exc:
            print(f"✗ settings.json: invalid JSON ({exc})")
            problems = True
    else:
        print("ℹ settings.json: absent")

    opencode_jsonc = paths.opencode_config_dir / "opencode.jsonc"
    if opencode_jsonc.exists():
        try:
            ms.parse_jsonc(opencode_jsonc.read_text(encoding="utf-8"))
            print("✓ opencode.jsonc: valid")
        except (json.JSONDecodeError, ValueError) as exc:
            print(f"✗ opencode.jsonc: invalid ({exc})")
            problems = True
    else:
        print("ℹ opencode.jsonc: absent")

    codex_toml = paths.codex_dir / "config.toml"
    if codex_toml.exists():
        try:
            tomllib.loads(codex_toml.read_text(encoding="utf-8"))
            print("✓ config.toml: valid")
        except Exception as exc:
            print(f"✗ config.toml: invalid TOML ({exc})")
            problems = True
    else:
        print("ℹ config.toml: absent")

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
    gitignore = paths.vault / ".gitignore"
    if gitignore.exists():
        existing_lines = set(gitignore.read_text(encoding="utf-8").splitlines())
        new_entries = [e for e in GITIGNORE_ENTRIES if e not in existing_lines]
        if new_entries:
            print(".gitignore: would add entries:")
            for e in new_entries:
                print(f"  + {e}")
        else:
            print(".gitignore: all entries already present")
    else:
        print(".gitignore: would create with:")
        for e in GITIGNORE_ENTRIES:
            print(f"  {e}")
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
            mcps = opencode_config.get("mcpServers", {})
            if isinstance(mcps, dict) and "qmd" in mcps:
                print("  opencode.jsonc: qmd MCP already present")
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

    # Manifest
    manifest = paths.manifest
    if manifest.exists():
        print(f"manifest: exists at {manifest}")
    else:
        print(f"manifest: would create at {manifest}")
    print()

    return 0


def _strip_qmd_from_json_config(text: str) -> tuple[str | None, bool]:
    """Remove qmd mcpServer entry from a JSON config string.

    Returns (remaining_text_or_None, was_stripped).
    - If qmd was the only mcpServer and mcpServers is now empty,
      remove the mcpServers key entirely.
    - If no qmd entry found, returns (text, False).
    """
    config = json.loads(text)
    mcps = config.get("mcpServers")
    if not isinstance(mcps, dict) or "qmd" not in mcps:
        return text, False

    del mcps["qmd"]
    if not mcps:
        del config["mcpServers"]

    return json.dumps(config, indent=2) + "\n", True


def _strip_qmd_from_jsonc_config(text: str) -> tuple[str | None, bool]:
    """Remove qmd mcpServer entry from a JSONC config string.

    Same semantics as _strip_qmd_from_json_config but handles JSONC comments.
    """
    config = ms.parse_jsonc(text)
    mcps = config.get("mcpServers")
    if not isinstance(mcps, dict) or "qmd" not in mcps:
        return text, False

    del mcps["qmd"]
    if not mcps:
        del config["mcpServers"]

    return json.dumps(config, indent=2) + "\n", True


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

    # Build list of actions
    actions: list[tuple[str, Path]] = []

    # Claude settings.json
    settings_path = paths.claude_dir / "settings.json"
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            mcps = settings.get("mcpServers")
            if isinstance(mcps, dict) and "qmd" in mcps:
                actions.append(("claude", settings_path))
        except json.JSONDecodeError:
            pass

    # OpenCode opencode.jsonc
    opencode_path = paths.opencode_config_dir / "opencode.jsonc"
    if opencode_path.exists():
        try:
            opencode_config = ms.parse_jsonc(
                opencode_path.read_text(encoding="utf-8")
            )
            mcps = opencode_config.get("mcpServers")
            if isinstance(mcps, dict) and "qmd" in mcps:
                actions.append(("opencode", opencode_path))
        except (json.JSONDecodeError, ValueError):
            pass

    # Codex config.toml
    codex_path = paths.codex_dir / "config.toml"
    if codex_path.exists():
        content = codex_path.read_text(encoding="utf-8")
        if CODEX_TOML_SECTION in content:
            actions.append(("codex", codex_path))

    # Manifest
    if paths.manifest.exists():
        actions.append(("manifest", paths.manifest))

    if not actions:
        print("nothing to uninstall")
        return 0

    # Dry-run: print planned actions only
    if dry_run:
        for kind, _path in actions:
            if kind == "claude":
                print("would strip qmd MCP from settings.json")
            elif kind == "opencode":
                print("would strip qmd MCP from opencode.jsonc")
            elif kind == "codex":
                print("would strip qmd MCP section from config.toml")
            elif kind == "manifest":
                print(f"would remove {_path}")
        print("dry run: no files modified")
        return 0

    if not _confirm("Uninstall second-brain kit managed snippets?", yes=yes):
        print("aborted")
        return 1

    for kind, path in actions:
        if kind == "claude":
            current = path.read_text(encoding="utf-8")
            stripped, _changed = _strip_qmd_from_json_config(current)
            if stripped is not None:
                path.write_text(stripped, encoding="utf-8")
            print("stripped qmd MCP from settings.json")
        elif kind == "opencode":
            current = path.read_text(encoding="utf-8")
            stripped, _changed = _strip_qmd_from_jsonc_config(current)
            if stripped is not None:
                path.write_text(stripped, encoding="utf-8")
            print("stripped qmd MCP from opencode.jsonc")
        elif kind == "codex":
            current = path.read_text(encoding="utf-8")
            remaining, fully_owned = ms.strip_toml_block(current, CODEX_TOML_SECTION)
            if fully_owned:
                path.unlink()
                print("removed config.toml (was entirely qmd MCP section)")
            elif remaining is not None:
                path.write_text(remaining, encoding="utf-8")
                print("stripped qmd MCP section from config.toml")
        elif kind == "manifest":
            path.unlink()
            print(f"removed {path}")

    return 0
