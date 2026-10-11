"""Agent map grammar for docs/wiki/index.md (pure: no git, no file IO).

The map is a delimited block of one-line navigation entries. Entries are
untrusted text written by an agent; the strict grammar keeps them inert: a
link target can never be an ``@`` import (Claude Code expands those eagerly),
a URL, or an escape from the wiki directory.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from agents.wikify.citations import HUMAN

MAP_BEGIN = "<!-- wikify:map -->"
MAP_END = "<!-- /wikify:map -->"
MAX_ENTRIES = 60
MAX_BYTES = 6144
MAX_TITLE = 60
MAX_HINT = 80
ENTRY = re.compile(r"^- \[([^\[\]()\n]{1,60})\]\(([^\s()\[\]]+)\) — ([^\[\]()\n]{1,80})$")
_FORBIDDEN_PATHS = {"index.md", "wikify.md"}  # compared case-insensitively


@dataclass(frozen=True)
class Entry:
    path: str
    title: str
    hint: str
    line: int


@dataclass(frozen=True)
class MapBlock:
    entries: list[Entry]
    errors: list[str]  # "index.md:<line>: <reason>"
    blocks: int
    begin_line: int = 1  # line of the first begin marker; anchors page-level errors


def _mask(text: str) -> str:
    """Blank human blocks to spaces, keeping offsets and newlines intact."""
    return HUMAN.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)


def _path_error(path: str) -> str | None:
    if path.startswith("/"):
        return "absolute path"
    if "@" in path:
        return "'@' in path"
    if ":" in path:
        return "scheme or ':' in path"
    if "\\" in path:
        return "backslash in path"
    if ".." in path.split("/"):
        return "'..' segment in path"
    if not path.lower().endswith(".md"):
        return "not a markdown page"
    if path.lower() in _FORBIDDEN_PATHS:
        return "reserved page"
    return None


def _line(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _first_block(masked: str) -> tuple[int, int, int] | None:
    """(begin_start, body_start, end_start) of the first delimited block, if any."""
    begin = masked.find(MAP_BEGIN)
    if begin < 0:
        return None
    body = begin + len(MAP_BEGIN)
    end = masked.find(MAP_END, body)
    return (begin, body, end) if end >= 0 else None


def parse_map(text: str) -> MapBlock:
    masked = _mask(text)
    begins = [m.start() for m in re.finditer(re.escape(MAP_BEGIN), masked)]
    if not begins:
        return MapBlock([], [], 0)
    errors: list[str] = []
    entries: list[Entry] = []
    first_line = _line(masked, begins[0])
    if len(begins) > 1:
        errors.append(f"index.md:{_line(masked, begins[1])}: more than one map block")
    found = _first_block(masked)
    if found is None:
        errors.append(f"index.md:{first_line}: unterminated map block")
        return MapBlock(entries, errors, len(begins), first_line)
    _, body_start, end = found
    body = masked[body_start:end]
    if len(body.encode("utf-8")) > MAX_BYTES:
        errors.append(f"index.md:{first_line}: map exceeds {MAX_BYTES} bytes")
    for i, raw in enumerate(body.split("\n")):
        line = raw.rstrip("\r")
        if not line.strip():
            continue
        n = first_line + i
        m = ENTRY.match(line)
        if not m:
            errors.append(f"index.md:{n}: invalid map entry")
            continue
        reason = _path_error(m.group(2))
        if reason:
            errors.append(f"index.md:{n}: invalid map entry path: {reason}")
            continue
        entries.append(Entry(m.group(2), m.group(1), m.group(3), n))
    if len(entries) > MAX_ENTRIES:
        errors.append(f"index.md:{first_line}: map exceeds {MAX_ENTRIES} entries")
    return MapBlock(entries, errors, len(begins), first_line)


def strip_map(text: str) -> str:
    """Replace the first delimited block with the same number of newlines."""
    found = _first_block(_mask(text))
    if found is None:
        return text
    begin, _, end = found
    stop = end + len(MAP_END)
    return text[:begin] + "\n" * text.count("\n", begin, stop) + text[stop:]


def validate_map(block: MapBlock, pages: set[str]) -> list[str]:
    """Page-level errors; parse errors stay in ``block.errors``. Empty without a block."""
    if block.blocks == 0:
        return []
    errors: list[str] = []
    seen: set[str] = set()
    for e in block.entries:
        if e.path in seen:
            errors.append(f"index.md:{e.line}: duplicate entry: {e.path}")
        seen.add(e.path)
        if e.path not in pages:
            errors.append(f"index.md:{e.line}: link target missing: {e.path}")
    for rel in sorted(pages - seen - {"index.md"}):
        errors.append(f"index.md:{block.begin_line}: page not reachable from the map: {rel}")
    return errors
