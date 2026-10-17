"""Inbound references to docs that ``vibe wikify adopt`` may move (read-only).

A reference is either a ``link`` (a relative markdown link that resolves to the
doc) or a ``path`` (the repo-relative path written out, e.g. in a Makefile or a
source comment). Rewriting is a separate, opt-in step; this module never edits.
"""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass
from pathlib import Path

from agents.wikify import gitview
from agents.wikify.state import WIKI_DIR

MAX_FILE_BYTES = 1 << 20
CONFIG_SUFFIXES = (".toml", ".json", ".yaml", ".yml", ".cfg", ".ini", ".mk", ".in")
CONFIG_NAMES = {"makefile", "dockerfile", "justfile"}
_LINK = re.compile(r"\]\(<?([^()\s#<>]+)")


@dataclass(frozen=True)
class Ref:
    file: str
    line: int
    kind: str  # link | path


def is_config(path: str) -> bool:
    name = path.rsplit("/", 1)[-1].casefold()
    return name in CONFIG_NAMES or name.endswith(CONFIG_SUFFIXES)


def _read(root: Path, rel: str) -> str | None:
    path = root / rel
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
            return None
        return path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def scan(root: Path, sources: list[str]) -> dict[str, list[Ref]]:
    """Source doc -> references from other tracked text files, sorted by (file, line)."""
    root = Path(root)
    wanted = set(sources)
    patterns = {s: re.compile(r"(?<![\w./-])" + re.escape(s) + r"(?![\w/])") for s in sources}
    out: dict[str, set[Ref]] = {s: set() for s in sources}
    for rel in gitview.tracked_files(root):
        if rel.startswith(WIKI_DIR):
            continue
        text = _read(root, rel)
        if text is None:
            continue
        is_md = rel.lower().endswith((".md", ".markdown"))
        base = posixpath.dirname(rel)
        lines = text.split("\n")
        for src in sources:
            if src == rel or src not in text:
                continue
            for n, line in enumerate(lines, 1):
                if src in line and patterns[src].search(line):
                    out[src].add(Ref(rel, n, "path"))
        if is_md and "](" in text:
            for n, line in enumerate(lines, 1):
                for m in _LINK.finditer(line):
                    target = m.group(1)
                    if "://" in target or target.startswith(("/", "mailto:")):
                        continue
                    resolved = posixpath.normpath(posixpath.join(base, target))
                    if resolved in wanted and resolved != rel:
                        out[resolved].add(Ref(rel, n, "link"))
    return {s: sorted(refs, key=lambda r: (r.file, r.line, r.kind)) for s, refs in out.items()}
