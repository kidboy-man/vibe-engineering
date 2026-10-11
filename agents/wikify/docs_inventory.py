"""Inventory of existing markdown docs eligible for generated outline pages.

Eligible docs are tracked files read at HEAD only. Hard exclusions (instruction
files, the wiki itself, secret and ignored paths) are silent; shape or size
problems are reported as ``skipped`` so the user can see why a doc is absent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from agents.secret_policies import is_secret_path
from agents.wikify import citations, gitview
from agents.wikify.state import WIKI_DIR

INCLUDES_REL = WIKI_DIR + ".wikifydocs"
MAX_DOCS = 500
MAX_DOC_BYTES = 1 << 20
SUFFIXES = (".md", ".markdown")
EXCLUDED_NAMES = {"AGENTS.md", "CLAUDE.md", "GEMINI.md", "SKILL.md"}
DEFAULT_PREFIXES = ("readme", "contributing", "changelog", "architecture")
UNCITABLE = re.compile(r"[\s:`()]")


@dataclass(frozen=True)
class Skip:
    path: str
    reason: str


@dataclass(frozen=True)
class Inventory:
    docs: list[str]
    skipped: list[Skip]


def load_includes(root: Path) -> list[str]:
    """Extra include globs from the working-tree control file; missing -> []."""
    try:
        lines = (Path(root) / INCLUDES_REL).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return []
    globs = (line.strip() for line in lines)
    return [g for g in globs if g and not g.startswith("#")]


def _default_eligible(path: str) -> bool:
    base = path.rsplit("/", 1)[-1]
    return (
        "/" not in path
        or path.startswith("docs/")
        or base.lower().startswith(DEFAULT_PREFIXES)
    )


def inventory(root: Path) -> Inventory:
    root = Path(root)
    includes = load_includes(root)
    ignore = citations.load_ignore(root)
    docs: list[str] = []
    skipped: list[Skip] = []
    for path in sorted(gitview.tracked_files(root)):
        if not path.lower().endswith(SUFFIXES):
            continue
        if not (_default_eligible(path) or citations.is_ignored(path, includes)):
            continue
        if (
            path.rsplit("/", 1)[-1] in EXCLUDED_NAMES
            or path.startswith(WIKI_DIR)
            or is_secret_path(path)
            or citations.is_ignored(path, ignore)
        ):
            continue
        if UNCITABLE.search(path):
            skipped.append(Skip(path, "path not citable"))
            continue
        text = gitview.show_head(root, path)
        if text is None:
            reason = "unreadable"
        elif not text.strip():
            reason = "empty"
        elif len(text.encode("utf-8")) > MAX_DOC_BYTES:
            reason = "larger than 1 MiB"
        elif "�" in text:
            reason = "not valid UTF-8"
        else:
            docs.append(path)
            continue
        skipped.append(Skip(path, reason))
    for extra in docs[MAX_DOCS:]:
        skipped.append(Skip(extra, f"over {MAX_DOCS} docs"))
    return Inventory(docs[:MAX_DOCS], sorted(skipped, key=lambda s: s.path))
