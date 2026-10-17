"""Heal moved citations by rewriting only their line numbers.

Ceiling: a citation is healed only when its recorded range hash matches exactly one window.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from agents.wikify import citations, drift, gitview, imported, state
from agents.wikify.atomic import write_atomic as _write_atomic


@dataclass
class Plan:
    heals: list[drift.Finding]
    refusals: list[drift.Finding]


def plan(root: Path) -> Plan:
    """Heals for ``moved`` citations, refusals for ``changed`` ones (ambiguous or edited body).

    Pages are read from the work tree, cited code from HEAD. Registered imported
    pages are skipped: re-anchoring never edits prose it does not own.
    """
    root = Path(root)
    tracked = gitview.regular_tracked(root)
    if tracked is None:
        raise RuntimeError("git ls-tree failed")
    st = state.load(root)
    everything = drift.read_pages(root, at_head=False)
    skip = imported.effective(everything, st)
    pages = {rel: text for rel, text in everything.items() if rel not in skip}
    done = drift.classify(root, pages, st, tracked, citations.load_ignore(root))
    return Plan(
        [f for f in done.findings if f.category == "moved"],
        [f for f in done.findings if f.category == "changed"],
    )


def _rewrite(text: str, heals: list[drift.Finding]) -> tuple[str, int]:
    """Replace the line numbers of the matching citations; nothing else changes."""
    human = citations.human_spans(text)
    wanted = {(f.path, f.start, f.end, f.symbol): f for f in heals}
    out: list[str] = []
    last = count = 0
    for m in citations.CITE.finditer(text):
        if any(a <= m.start() < b for a, b in human):
            continue
        key = (m.group(1), int(m.group(2)), int(m.group(3) or m.group(2)), m.group(4))
        heal = wanted.get(key)
        if heal is None:
            continue
        out.append(text[last : m.start(2)])
        out.append(str(heal.new_start) if m.group(3) is None else f"{heal.new_start}-{heal.new_end}")
        last = m.end(3 if m.group(3) else 2)
        count += 1
    out.append(text[last:])
    return "".join(out), count


def apply(root: Path, heals: list[drift.Finding]) -> int:
    """Write the heals page by page and re-key their baseline hashes; returns citations healed."""
    root = Path(root)
    state.check_wiki_path(root)
    st = state.load(root)
    original = st["citations"]
    renamed: dict[str, str] = {}  # new key -> hash, built from the original map only
    total = 0
    by_page: dict[str, list[drift.Finding]] = {}
    for f in heals:
        by_page.setdefault(f.page, []).append(f)
    for rel, group in sorted(by_page.items()):
        path = root / state.WIKI_DIR / rel
        with open(path, newline="", encoding="utf-8") as handle:
            text = handle.read()
        new, count = _rewrite(text, group)
        if count:
            _write_atomic(path, new)
            total += count
        for f in group:
            old_key = drift.finding_key(f)
            if old_key in original:
                renamed[drift.finding_key(f, moved=True)] = original[old_key]
    old_keys = {drift.finding_key(f) for f in heals}
    keys = {k: v for k, v in original.items() if k not in old_keys}
    keys.update(renamed)
    if keys != original:
        state.save(root, st["covered"], citations=keys)
    return total


def _line(f: drift.Finding) -> str:
    from agents.wikify.pointer import _safe

    sym = f" `{f.symbol}`" if f.symbol else ""
    return _safe(f"{f.page}:{f.line}: {f.path} {f.start}-{f.end}") + (
        _safe(f" -> {f.new_start}-{f.new_end}{sym}") if f.new_start else _safe(sym)
    )


def run(root: Path, apply_changes: bool) -> tuple[int, list[str]]:
    """(exit code, output lines). Exit 1 when any citation is refused or the wiki path is unsafe."""
    try:
        state.check_wiki_path(root)
        todo = plan(root)
        lines = [_line(f) for f in todo.heals]
        lines += [f"refused: {_line(f)} ({f.reason})" for f in todo.refusals]
        if not todo.heals and not todo.refusals:
            lines.append("nothing to re-anchor")
        elif apply_changes and todo.heals:
            lines.append(f"re-anchored {apply(root, todo.heals)} citation(s)")
        elif todo.heals:
            lines.append("dry run: rerun with --apply to rewrite these line numbers")
        return (1 if todo.refusals else 0), lines
    except state.UnsafeWikiPath as exc:
        return 1, [f"refused: {exc}"]
    except (OSError, RuntimeError) as exc:
        return 1, [f"reanchor failed: {type(exc).__name__}"]


def cmd_reanchor(cwd: str | Path | None = None, apply_changes: bool = False) -> int:
    root = gitview.repo_root(cwd or os.getcwd())
    if root is None:
        print("not a git repository")
        return 1
    rc, lines = run(root, apply_changes)
    print("\n".join(lines))
    return rc
