"""Persona sections injected into agent instruction files (CLAUDE.md, AGENTS.md)."""

from __future__ import annotations
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from agents import merge_strategies as ms
from agents.kits.second_brain.paths import CLAUDE_MD_BEGIN_MARKER, CLAUDE_MD_END_MARKER, CODEX_INSTRUCTIONS_BEGIN_MARKER, CODEX_INSTRUCTIONS_END_MARKER, KitPaths, OPENCODE_AGENTS_BEGIN_MARKER, OPENCODE_AGENTS_END_MARKER


@dataclass(frozen=True)
class PersonaSection:
    """A marked-section merge target (persona/instructions file)."""

    label: str
    path_fn: Callable[[KitPaths], Path]
    fragment_name: str
    begin_marker: str
    end_marker: str


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


CLAUDE_PERSONA_SECTION = PersonaSection(
    "CLAUDE.md", lambda p: p.claude_dir / "CLAUDE.md", "claude_md_section.md", CLAUDE_MD_BEGIN_MARKER, CLAUDE_MD_END_MARKER
)

CODEX_PERSONA_SECTION = PersonaSection(
    "AGENTS.md",
    lambda p: p.codex_dir / "AGENTS.md",
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

def _merge_claude_md_section(paths: KitPaths) -> None:
    """Merge the second-brain marked section into ~/.claude/CLAUDE.md."""
    _merge_persona_section(paths, CLAUDE_PERSONA_SECTION)


def _merge_codex_instructions_section(paths: KitPaths) -> None:
    """Merge the second-brain marked section into ~/.codex/AGENTS.md."""
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
