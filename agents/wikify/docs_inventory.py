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
EXCLUDED_NAMES = {"agents.md", "claude.md", "gemini.md", "skill.md"}  # casefolded
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
    lines = citations.read_control_lines(Path(root) / INCLUDES_REL)
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
    regular = gitview.regular_tracked(root)
    if regular is None:  # fail closed: modes unknown, so no path can be trusted
        return Inventory([], [Skip("", "could not read file modes")])
    includes = load_includes(root)
    ignore = citations.load_ignore(root)
    candidates: list[str] = []
    skipped: list[Skip] = []
    for path in sorted(regular):
        if not path.lower().endswith(SUFFIXES):
            continue
        if not (_default_eligible(path) or citations.is_ignored(path, includes)):
            continue
        if (
            path.rsplit("/", 1)[-1].casefold() in EXCLUDED_NAMES
            or path.startswith(WIKI_DIR)
            or is_secret_path(path)
            or citations.is_ignored(path, ignore)
        ):
            continue
        if UNCITABLE.search(path):
            skipped.append(Skip(path, "path not citable"))
        else:
            candidates.append(path)
    docs: list[str] = []
    for n, path in enumerate(candidates):
        if len(docs) >= MAX_DOCS:  # stop reading; the rest are only reported
            skipped.extend(Skip(p, f"over {MAX_DOCS} docs") for p in candidates[n:])
            break
        text = gitview.show_head(root, path)
        if text is None:
            reason = "unreadable at HEAD (not committed?)"
        elif not text.strip():
            reason = "empty"
        elif len(text.encode("utf-8")) > MAX_DOC_BYTES:
            reason = "larger than 1 MiB"
        elif "\ufffd" in text:
            # show_head decodes with replacement, so a literal U+FFFD lands here too
            reason = "not valid UTF-8"
        else:
            docs.append(path)
            continue
        skipped.append(Skip(path, reason))
    return Inventory(docs, sorted(skipped, key=lambda s: s.path))
