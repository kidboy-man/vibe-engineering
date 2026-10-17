"""Agent-map entries and folder indexes for adopted pages (pure: text in, text out)."""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass

from agents.wikify import agentmap

_HEADING = re.compile(r"^ {0,3}#{1,6}[ \t]+(.+?)[ \t#]*$", re.M)
_STRIP = re.compile(r"[\[\]()`]")


@dataclass(frozen=True)
class Page:
    dest: str  # wiki-relative
    source: str
    body: str


def _clean(value: str, limit: int) -> str:
    return " ".join(_STRIP.sub("", value).split())[:limit].strip()


def _ok(title: str, hint: str) -> bool:
    return bool(title and hint) and agentmap._markup_error(title, hint) is None


def entry_for(page: Page) -> str:
    m = _HEADING.search(page.body)
    stem = posixpath.splitext(posixpath.basename(page.dest))[0]
    hint = _clean(f"imported from {page.source}", agentmap.MAX_HINT)
    for title in (_clean(m.group(1), agentmap.MAX_TITLE) if m else "", _clean(stem, agentmap.MAX_TITLE), "doc"):
        for h in (hint, "imported doc"):
            if _ok(title, h):
                return f"- [{title}]({page.dest}) — {h}"
    raise ValueError("no valid map entry")  # unreachable: "doc" / "imported doc" are always valid


def _group(pages: list[Page]) -> dict[str, list[Page]]:
    groups: dict[str, list[Page]] = {}
    for p in pages:
        groups.setdefault(p.dest.split("/", 1)[0], []).append(p)
    return groups


def folder_index(folder: str, pages: list[Page]) -> tuple[str, str]:
    """(wiki-relative path, text) of a link-only index page for ``folder``."""
    lines = [f"# {_clean(folder, agentmap.MAX_TITLE) or 'adopted'}", ""]
    for p in sorted(pages, key=lambda p: p.dest):
        title = entry_for(p).split("](", 1)[0][3:]
        lines.append(f"- [{title}]({p.dest[len(folder) + 1:]})")
    return f"{folder}/index.md", "\n".join(lines) + "\n"


def _block_text(entries: list[str]) -> str:
    return agentmap.MAP_BEGIN + "\n" + "\n".join(entries) + "\n" + agentmap.MAP_END + "\n"


def plan_map(index_text: str, pages: list[Page]) -> tuple[str, dict[str, str]] | str:
    """(new index.md text, extra index pages) or an error string; never edits outside the map."""
    block = agentmap.parse_map(index_text)
    if block.errors:
        return "index.md map is invalid: " + block.errors[0]
    listed = {e.path for e in block.entries}
    todo = [p for p in pages if p.dest not in listed]
    if not todo:
        return index_text, {}
    lines = index_text.split("\n")
    current = [lines[e.line - 1].rstrip("\r") for e in block.entries]
    direct = [entry_for(p) for p in todo]
    extra: dict[str, str] = {}
    entries = current + direct
    if len(entries) > agentmap.MAX_ENTRIES or len("\n".join(entries).encode()) > agentmap.MAX_BYTES:
        entries = list(current)
        for folder, group in sorted(_group(todo).items()):
            rel, text = folder_index(folder, group)
            if rel in listed:
                return f"{rel} is already mapped; group adopted pages by hand"
            extra[rel] = text
            entries.append(f"- [{_clean(folder, agentmap.MAX_TITLE) or 'adopted'}]({rel}) — {len(group)} adopted pages")
        if len(entries) > agentmap.MAX_ENTRIES or len("\n".join(entries).encode()) > agentmap.MAX_BYTES:
            return "map is over its caps even with folder indexes; trim the map by hand"
    return _replace_block(index_text, entries), extra


def _replace_block(text: str, entries: list[str]) -> str:
    start = text.find(agentmap.MAP_BEGIN)
    if start < 0:
        return text.rstrip("\n") + ("\n\n" if text.strip() else "") + _block_text(entries)
    stop = text.find(agentmap.MAP_END, start) + len(agentmap.MAP_END)
    tail = text[stop:]
    return text[:start] + _block_text(entries).rstrip("\n") + (tail if tail.startswith("\n") else "\n" + tail)


def drop_entries(index_text: str, paths: set[str]) -> str:
    """``index_text`` without the map entries that point at ``paths`` (removed pages)."""
    block = agentmap.parse_map(index_text)
    dead = {e.line - 1 for e in block.entries if e.path in paths}
    if not dead:
        return index_text
    return "\n".join(ln for i, ln in enumerate(index_text.split("\n")) if i not in dead)
