"""Constants, markers and path resolution for the second-brain kit.

The string constants here are an on-disk contract: newer versions locate and
remove what older versions wrote by matching them byte-for-byte."""

from __future__ import annotations

import os
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

HOOK_SCRIPT_REL = "hooks/second-brain-context.py"

SESSIONSTART_EVENT = "SessionStart"

CURSOR_SESSIONSTART_EVENT = "sessionStart"

CURSOR_RULE_REL = "rules/second-brain.mdc"

SKILL_ROOT_REL = "skills"

QMD_MIN_NODE_MAJOR = 22

QMD_COLLECTION_NAME = "second-brain"

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
