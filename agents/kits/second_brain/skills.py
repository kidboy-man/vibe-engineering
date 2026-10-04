"""Skill discovery and sync for the second-brain kit (~/.agents and ~/.claude skill dirs)."""

from __future__ import annotations
from pathlib import Path
from agents.kits.second_brain.paths import KitPaths, SKILL_ROOT_REL


def _skill_source_dirs(paths: KitPaths) -> list[Path]:
    root = paths.template / SKILL_ROOT_REL
    return sorted(path.parent for path in root.glob("*/SKILL.md"))


def _skill_root_targets(paths: KitPaths) -> list[Path]:
    return [paths.home_root / ".agents" / "skills", paths.claude_dir / "skills"]


def _skill_targets(paths: KitPaths) -> list[Path]:
    return [
        root / source_dir.name / "SKILL.md"
        for root in _skill_root_targets(paths)
        for source_dir in _skill_source_dirs(paths)
    ]


def _skill_source_for_target(paths: KitPaths, target: Path) -> Path:
    return paths.template / SKILL_ROOT_REL / target.parent.name


def _skill_dir_status(paths: KitPaths, source_dir: Path, target_dir: Path) -> str:
    if not target_dir.exists():
        return "missing"
    expected = {
        source.relative_to(source_dir)
        for source in source_dir.rglob("*")
        if source.is_file()
    }
    actual = {
        target.relative_to(target_dir)
        for target in target_dir.rglob("*")
        if target.is_file()
    }
    if actual - expected:
        return "modified"
    for source in source_dir.rglob("*"):
        if source.is_file():
            target = target_dir / source.relative_to(source_dir)
            if not target.exists():
                return "incomplete"
            if target.read_text(encoding="utf-8") != source.read_text(encoding="utf-8"):
                return "modified"
    return "up to date"


def _install_skill(paths: KitPaths) -> None:
    """Install portable skill directories without overwriting user changes."""
    for root in _skill_root_targets(paths):
        for source_dir in _skill_source_dirs(paths):
            target_dir = root / source_dir.name
            status = _skill_dir_status(paths, source_dir, target_dir)
            if status == "up to date":
                continue
            if status != "missing":
                print(f"kept {status} second-brain skill: {target_dir}")
                continue
            for source in source_dir.rglob("*"):
                if source.is_file():
                    target = target_dir / source.relative_to(source_dir)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"installed second-brain skill: {target_dir / 'SKILL.md'}")


def _skill_status(paths: KitPaths, target: Path) -> str:
    return _skill_dir_status(paths, _skill_source_for_target(paths, target), target.parent)
