"""Agent map grammar for docs/wiki/index.md (pure: no git, no file IO).

The map is a delimited block of one-line navigation entries. Entries are
untrusted text written by an agent; the strict grammar keeps them inert: a
link target can never be an ``@`` import (Claude Code expands those eagerly),
a URL, or an escape from the wiki directory.

Reachability follows only plain ``[text](path.md)`` and ``[text](path.md#anchor)``
links; titled (``"t"``), angle (``<a.md>``) and reference-style links are not
recognised and fail closed (the page stays unreachable).
"""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass

from agents.wikify.citations import human_spans

MAP_BEGIN = "<!-- wikify:map -->"
MAP_END = "<!-- /wikify:map -->"
MAX_ENTRIES = 60
MAX_BYTES = 6144
MAX_TITLE = 60
MAX_HINT = 80
ENTRY = re.compile(r"^- \[([^\[\]()\n]{1,60})\]\(([^\s()\[\]<>]+)\) — ([^\[\]()\n]{1,80})$")
# Brackets, parens and whitespace are excluded from the target so a match attempt
# never scans past the next delimiter: the whole scan stays linear on hostile text.
LINK = re.compile(r"\]\(([^()\[\]\s#]+\.md)(?:#[^()\[\]\s]*)?\)", re.I)
MAX_LINKS = 5000  # per page: bounds a hostile page of links
_FORBIDDEN_PATHS = {"index.md", "WIKIFY.md"}  # exact case: matches the control-file exemptions


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
    out: list[str] = []
    last = 0
    for start, end in human_spans(text):
        out.append(text[last:start])
        out.append(re.sub(r"[^\n]", " ", text[start:end]))
        last = end
    out.append(text[last:])
    return "".join(out)


def _markup_error(title: str, hint: str) -> str | None:
    """Title and hint stay inert: no '@' import, no HTML or comments, no URLs."""
    for where, value in (("title", title), ("hint", hint)):
        for token in ("@", "<!--", "-->", "<", ">", "://"):
            if token in value:
                return f"'{token}' in {where}"
        if "www." in value.lower():  # GFM autolinks www. without a scheme
            return f"'www.' in {where}"
    return None


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
    if path in _FORBIDDEN_PATHS:
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
    line_start = masked.rfind("\n", 0, begins[0]) + 1
    if masked[line_start : begins[0]].strip():
        errors.append(f"index.md:{first_line}: text before map begin marker")
    if len(begins) > 1:
        errors.append(f"index.md:{_line(masked, begins[1])}: more than one map block")
    found = _first_block(masked)
    if found is None:
        errors.append(f"index.md:{first_line}: unterminated map block")
        return MapBlock(entries, errors, len(begins), first_line)
    _, body_start, end = found
    body = masked[body_start:end]
    tail = masked.find("\n", end)
    if masked[end + len(MAP_END) : len(masked) if tail < 0 else tail].strip():
        errors.append(f"index.md:{_line(masked, end)}: text after map end marker")
    line, last = 1, 0
    for start, _ in human_spans(text):  # one pass: counting from 0 each time is quadratic
        line += text.count("\n", last, start)
        last = start
        if body_start <= start < end:
            errors.append(f"index.md:{line}: human block inside map")
    if len(body.encode("utf-8")) > MAX_BYTES:
        errors.append(f"index.md:{first_line}: map exceeds {MAX_BYTES} bytes")
    pieces = body.split("\n")
    for i, raw in enumerate(pieces):
        line = raw.rstrip("\r")
        if not line.strip():
            continue
        n = first_line + i
        if i == 0:
            errors.append(f"index.md:{n}: text after map begin marker")
            continue
        if i == len(pieces) - 1:
            errors.append(f"index.md:{n}: text before map end marker")
            continue
        m = ENTRY.match(line)
        if not m:
            errors.append(f"index.md:{n}: invalid map entry")
            continue
        markup = _markup_error(m.group(1), m.group(3))
        if markup:
            errors.append(f"index.md:{n}: invalid map entry: {markup}")
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


def page_links(page_rel: str, text: str) -> set[str]:
    """Wiki-relative ``.md`` pages that ``text`` links to; human blocks are ignored."""
    base = posixpath.dirname(page_rel)
    out: set[str] = set()
    for n, m in enumerate(LINK.finditer(_mask(text))):
        if n >= MAX_LINKS:
            break
        raw = m.group(1)
        if raw.startswith("/") or ":" in raw or "\\" in raw:
            continue
        target = posixpath.normpath(posixpath.join(base, raw))
        if ".." in target.split("/") or target in ("index.md", page_rel):
            continue
        out.add(target)
    return out


def reachable_pages(listed: set[str], texts: dict[str, str], depth: int = 2) -> set[str]:
    """``listed`` plus pages in ``texts`` linked within ``depth`` hops of a listed page."""
    seen = set(listed)
    frontier = list(listed)
    for _ in range(depth):
        nxt: list[str] = []
        for rel in frontier:
            if rel not in texts:
                continue
            for target in page_links(rel, texts[rel]):
                if target in texts and target not in seen:
                    seen.add(target)
                    nxt.append(target)
        frontier = nxt
    return seen


def validate_map(
    block: MapBlock, pages: set[str], reachable: set[str] | None = None
) -> list[str]:
    """Page-level errors; parse errors stay in ``block.errors``. Empty without a block.

    ``reachable`` (see ``reachable_pages``) widens the orphan rule from "listed" to
    "listed or linked from a reachable page"; duplicates still compare entries only.
    """
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
    covered = seen | (reachable or set())
    for rel in sorted(pages - covered - {"index.md"}):
        errors.append(f"index.md:{block.begin_line}: page not reachable from the map: {rel}")
    return errors
