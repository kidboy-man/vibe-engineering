"""Second-brain kit installer — vault scaffold, seed pages, .gitignore, git init."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from agents import installer_core as core

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


def _manifest_state(managed_files: list[str]) -> dict:
    return core.manifest_state(KIT_NAME, managed_files)


def install(
    home: str | None = None,
    dry_run: bool = False,
    yes: bool = False,
    merge_settings: bool = True,  # noqa: ARG001 — reserved for future agent config adapters
) -> int:
    paths = _paths(home)

    # Preflight: validate existing agent configs before any writes.
    if not _validate_configs(paths):
        return 1

    if dry_run:
        _print_dry_run(paths)
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

    # Write runtime manifest.
    core.write_text(paths.manifest, json.dumps(_manifest_state(managed), indent=2) + "\n")
    print(f"wrote {paths.manifest}")
    return 0


def doctor(home: str | None = None) -> int:
    paths = _paths(home)
    if not paths.vault.is_dir():
        return 1
    return 0


def diff_kit(home: str | None = None) -> int:
    return 0


def uninstall(
    home: str | None = None,
    dry_run: bool = False,  # noqa: ARG001
    yes: bool = False,  # noqa: ARG001
) -> int:
    return 0
