"""Report-only reference checks for imported prose.

Ceiling: name-only matching is a floor, not proof the sentence is true.
"""

from __future__ import annotations

import os
import posixpath
import re
from pathlib import Path

from agents.secret_policies import is_secret_path
from agents.wikify import adopt_plan, citations, drift, gitview, imported, scan, state
from agents.wikify import adopt_refs
from agents.wikify.atomic import write_atomic
from agents.wikify.pointer import _safe
from agents.wikify.state import WIKI_DIR

MAX_REFERENCES = 500
MAX_TOKEN = 200
FLOOR_NOTICE = "NOTICE: reference checks match names and paths only; a hit is a floor, not proof"
_TICKS = re.compile(r"`([^`\n]+)`")
_LINK = adopt_refs._LINK
_LOCATION = re.compile(r":\d+(?:-\d+)?$")
_PATH = re.compile(r"^[\w.@+-]+(?:/[\w.@+-]+)+$")
_EXT = re.compile(r"\.[a-z0-9]{1,8}$")  # lowercase: `server.Build` is a qualified name, not a file
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:(?:\.|::)[A-Za-z_][A-Za-z0-9_]*)*(?:\(\))?$")
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_PROSE = (".md", ".markdown", ".rst", ".txt")


def _read_text(root: Path, rel: str) -> str | None:
    return adopt_refs._read(root, rel)


def _words(root: Path, tracked: set[str], ignore: list[str]) -> set[str]:
    """Every identifier-like word in tracked code and config; the wiki, prose files, secret
    and ignored paths do not count (a doc mentioning a name is not the code defining it)."""
    found: set[str] = set()
    for rel in sorted(tracked):
        if (
            rel.startswith(WIKI_DIR) or rel.lower().endswith(_PROSE)
            or is_secret_path(rel) or citations.is_ignored(rel, ignore)
        ):
            continue
        text = _read_text(root, rel)
        if text is not None:
            found.update(_WORD.findall(text))
    return found


def _tails(paths: set[str]) -> set[str]:
    """Every trailing sub-path of every path ('a/b/c.go' -> 'b/c.go', 'c.go' excluded)."""
    out: set[str] = set()
    for path in paths:
        parts = path.split("/")
        out.update("/".join(parts[i:]) for i in range(1, len(parts) - 1))
    return out


def _body(text: str) -> tuple[str, int] | None:
    """(imported body, page lines before it) of a wrapper-shaped page."""
    wrapped = adopt_plan.unwrap(text)
    if wrapped is None:
        return None
    header = adopt_plan._WRAPPED.match(text)
    return wrapped[1], text[: header.end()].count("\n")


def _tokens(body: str, offset: int):
    """(page line, kind, token) for backticked paths/identifiers and markdown link targets."""
    fenced = False
    for n, line in enumerate(body.split("\n"), 1 + offset):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        for m in _TICKS.finditer(line):
            token = m.group(1).strip()
            path = _LOCATION.sub("", token)
            if _PATH.match(path) and _EXT.search(path) and "://" not in path:
                yield n, "path", path
            elif len(token) >= 3 and _IDENT.match(token):
                yield n, "symbol", token
        for m in _LINK.finditer(line):
            target = m.group(1)
            if "://" not in target and not target.startswith(("/", "mailto:")) and not target.endswith("/"):
                yield n, "link", target


def find(
    root: Path, pages: dict[str, str], tracked: set[str], ignore: list[str]
) -> list[dict]:
    """Report-only findings for every wrapper-shaped page: DEAD PATH, DEAD SYMBOL, STALE LINK.

    Ceiling: names and paths only. A hit is a floor, never proof a sentence is true."""
    root = Path(root)
    words: set[str] | None = None  # built lazily: one pass over the tracked files
    tails: set[str] | None = None
    out: list[dict] = []
    wiki_pages = {WIKI_DIR + rel for rel in pages}
    for rel in sorted(pages):
        parsed = _body(pages[rel])
        if parsed is None:
            continue
        for line, kind, token in _tokens(*parsed):
            if len(token) > MAX_TOKEN or scan.scan_text(token):
                continue  # never echo something that may be a secret
            if kind == "path":
                clean = token[2:] if token.startswith("./") else token
                if clean not in tracked and WIKI_DIR + clean not in wiki_pages:
                    if tails is None:
                        tails = _tails(tracked | wiki_pages)
                    if clean in tails:
                        continue  # a partial path, as docs often write them (`port/service.go`)
                    out.append({"page": rel, "line": line, "kind": "DEAD PATH", "token": clean})
            elif kind == "symbol":
                if words is None:
                    words = _words(root, tracked, ignore)
                name = re.split(r"\.|::", token.removesuffix("()"))[-1]
                if name not in words:
                    out.append({"page": rel, "line": line, "kind": "DEAD SYMBOL", "token": token})
            else:
                target = posixpath.normpath(posixpath.join(posixpath.dirname(WIKI_DIR + rel), token))
                if target not in tracked and target not in wiki_pages:
                    out.append({"page": rel, "line": line, "kind": "STALE LINK", "token": token})
            if len(out) >= MAX_REFERENCES:
                return out
    return out


def render(found: list[dict]) -> list[str]:
    if not found:
        return []
    return [_safe(f"  {f['page']}:{f['line']}: {f['kind']} {f['token']}") for f in found]


def fix_links(root: Path, apply_changes: bool) -> tuple[int, list[str]]:
    """Rewrite DEAD PATH tokens that a .wikifymap rule maps to an existing wiki page.

    Only registered imported pages are edited; everything else is left alone."""
    root = Path(root)
    try:
        state.check_wiki_path(root)
    except state.UnsafeWikiPath as exc:
        return 1, [f"refused: {exc}"]
    st = state.load(root)
    pages = drift.read_pages(root, at_head=False)
    unregistered = [rel for rel, text in pages.items() if rel not in st["imported"] and imported.is_imported_shape(text)]
    rules, errors = adopt_plan.load_rules(root)
    if errors:
        return 1, [f"refused: {_safe(e)}" for e in errors]
    tracked = set(gitview.tracked_files(root))
    wiki_pages = {WIKI_DIR + rel for rel in pages}
    lines: list[str] = []
    for rel in sorted(imported.effective(pages, st)):
        text = pages[rel]
        changes = _changes(text, rules, tracked, wiki_pages)
        lines += [_safe(f"{rel}:{n}: `{old}` -> `{new}`") for n, old, new in changes]
        if changes and apply_changes:
            with open(root / WIKI_DIR / rel, newline="", encoding="utf-8") as handle:
                raw = handle.read()
            new_raw = _apply_changes(raw, changes)
            write_atomic(root / WIKI_DIR / rel, new_raw)
            if imported.page_hash(raw) == st["imported"][rel]:
                # this tool's own mechanical edit is not a human edit: keep frozen mode and mark quiet
                imported.register(root, {rel: imported.page_hash(new_raw)})
            else:  # a human edit made earlier must stay visible until someone marks it
                lines.append(_safe(f"note: {rel} was edited since the last mark; run vibe wikify mark after reviewing it"))
    if unregistered and not lines:
        return 1, [f"refused: {len(unregistered)} wrapped page(s) are not registered; run vibe wikify migrate-imported first"]
    if not lines:
        return 0, ["nothing to fix"]
    if not apply_changes:
        lines.append("dry run: rerun with --apply to rewrite these paths")
    return 0, lines


def _changes(text, rules, tracked, wiki_pages):
    """[(page line, old token, new token)] for mapped dead paths in one page."""
    changes: list[tuple[int, str, str]] = []
    for line, kind, token in _tokens(*_body(text)):
        if kind != "path" or token in tracked:
            continue
        rule = adopt_plan.match(rules, token)
        dest = adopt_plan.destination(rule, token) if rule else None
        if dest and WIKI_DIR + dest in wiki_pages:
            changes.append((line, token, WIKI_DIR + dest))
    return changes


def _apply_changes(raw: str, changes: list[tuple[int, str, str]]) -> str:
    lines = raw.split("\n")
    for n, old, new in changes:
        lines[n - 1] = re.sub(
            "`" + re.escape(old) + r"(?![\w./-])", lambda _: f"`{new}", lines[n - 1]
        )
    return "\n".join(lines)


def cmd_fix_links(cwd: str | Path | None = None, apply_changes: bool = False) -> int:
    root = gitview.repo_root(cwd or os.getcwd())
    if root is None:
        print("not a git repository")
        return 1
    rc, lines = fix_links(root, apply_changes)
    print("\n".join(lines))
    return rc
