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

    merged, changed = ms.jsonc_defaults_strategy(
        QMD_MCP_SNIPPET_JSON,
        current,
        LOCAL_ONLY_KEYS,
        is_secret_key,
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
    setup_deps: bool = True,
    **kwargs,
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
    ]:
        found = shutil.which(binary)
        if found:
            print(f"✓ {binary} ({label}): {found}")
        else:
            print(f"⚠ {binary}: not found ({label})")

    print("\n-- other agents --")
    print("ℹ hermes: config path unverified (docs/sample only)")
    print("ℹ cursor: project-local .cursor/rules/*.mdc recommended")

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
            mcps = ms.parse_jsonc(opencode_path.read_text(encoding="utf-8")).get("mcpServers")
        except (json.JSONDecodeError, ValueError):
            mcps = None
        if isinstance(mcps, dict) and "qmd" in mcps:

            def _mutate_opencode(text: str) -> tuple[str | None, bool]:
                new = _strip_qmd_mcp(text, ms.parse_jsonc)
                return (None, False) if new is None else (new, False)

            specs.append((opencode_path, "qmd MCP from opencode.jsonc", _mutate_opencode))

    codex_path = paths.codex_dir / "config.toml"
    if codex_path.exists() and CODEX_TOML_SECTION in codex_path.read_text(encoding="utf-8"):
        specs.append((codex_path, "qmd MCP section", _strip_codex))

    if paths.manifest.exists():
        specs.append((paths.manifest, "kit manifest", None))

    if not specs:
        print("nothing to uninstall")
        return 0

    if dry_run:
        for _path, label, _fn in specs:
            print(f"would remove {label}")
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
    return 0
