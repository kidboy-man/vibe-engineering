"""Imported pages: adopt-wrapped docs tracked by content hash.

Ceiling: a page is imported only once registered in .wikify.json.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from agents.wikify import adopt_plan, drift, gitview, state
from agents.wikify.pointer import _safe


def is_imported_shape(text: str) -> bool:
    """True when the whole page is exactly one ``adopt`` wrapper (no other human markers)."""
    wrapped = adopt_plan.unwrap(text)
    if wrapped is None:
        return False
    return adopt_plan.HUMAN_BEGIN not in wrapped[1] and adopt_plan.HUMAN_END not in wrapped[1]


def page_hash(text: str) -> str:
    """16 hex of sha256 over the page text; line endings are normalised so CRLF and LF agree."""
    body = text.replace("\r\n", "\n")
    return hashlib.sha256(body.encode("utf-8", "surrogateescape")).hexdigest()[:16]


def effective(pages: dict[str, str], st: dict) -> set[str]:
    """Registered pages that exist and still have the wrapper shape. A registration alone never
    makes a page imported, so a hand-edited state file cannot silence a genuine human block."""
    return {rel for rel in st["imported"] if rel in pages and is_imported_shape(pages[rel])}


def edited_pages(pages: dict[str, str], st: dict) -> tuple[list[str], list[str]]:
    """(edited, removed) imported pages, sorted: hash differs, or page gone."""
    live = effective(pages, st)
    edited = [rel for rel in sorted(live) if page_hash(pages[rel]) != st["imported"][rel]]
    removed = [rel for rel in sorted(st["imported"]) if rel not in pages]
    return edited, removed


def lost_shape(pages: dict[str, str], st: dict) -> list[str]:
    """Registered pages that exist but are no longer a wrapper (treated as ordinary pages)."""
    live = effective(pages, st)
    return [rel for rel in sorted(st["imported"]) if rel in pages and rel not in live]


def invalid_mode_notice(root: Path) -> list[str]:
    mode = state._read_raw(root).get("imported_mode")
    if mode is None or mode in state.IMPORTED_MODES:
        return []
    return [f"NOTICE: {state.STATE_REL} imported_mode must be editable or frozen; using editable"]


def register(root: Path, hashes: dict[str, str]) -> None:
    """Add ``hashes`` to the state file's ``imported`` map; nothing else changes."""
    st = state.load(root)
    state.save(root, st["covered"], imported={**st["imported"], **hashes})


def migrate(root: Path, apply_changes: bool) -> tuple[int, list[str]]:
    """Register wrapper-shaped pages that are not registered yet; writes only the state file."""
    try:
        state.check_wiki_path(root)
        st = state.load(root)
        found = {
            rel: page_hash(text)
            for rel, text in sorted(drift.read_pages(root, at_head=False).items())
            if rel not in st["imported"] and is_imported_shape(text)
        }
        if not found:
            return 0, ["nothing to register"]
        verb = "registered" if apply_changes else "would register"
        lines = [_safe(f"{verb}: {rel}") for rel in found]
        if apply_changes:
            register(root, found)
        else:
            lines.append("dry run: rerun with --apply to write docs/wiki/.wikify.json")
        return 0, lines
    except state.UnsafeWikiPath as exc:
        return 1, [f"refused: {exc}"]
    except OSError as exc:
        return 1, [f"migrate-imported failed: {type(exc).__name__}"]


def cmd_migrate(cwd: str | Path | None = None, apply_changes: bool = False) -> int:
    root = gitview.repo_root(cwd or os.getcwd())
    if root is None:
        print("not a git repository")
        return 1
    rc, lines = migrate(root, apply_changes)
    print("\n".join(lines))
    return rc
