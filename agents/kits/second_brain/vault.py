"""Vault scaffolding: seed pages, .gitignore merge, git init, foreign-file scan."""

from __future__ import annotations

import subprocess
from pathlib import Path
from agents.kits.second_brain.paths import GITIGNORE_ENTRIES


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
