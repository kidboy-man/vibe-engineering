"""Drift classification of wiki citations against HEAD.

Ceiling: structural only (a content hash of the cited lines), never semantic.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from pathlib import Path

from agents.secret_policies import is_secret_path

from agents.wikify import agentmap, citations, docs_inventory, gitview, state
from agents.wikify.citations import CONTROL_FILES, Citation, walk_wiki
from agents.wikify.state import WIKI_DIR

HASH_HEX = 12
MAX_WINDOW_WORK = 4_000_000  # line visits per search; bounds relocation on huge cited ranges


def range_hash(lines: list[str], start: int, end: int) -> str:
    """First 12 hex of sha256 over lines ``start..end`` (1-based, inclusive)."""
    body = "\n".join(lines[start - 1 : end])
    return hashlib.sha256(body.encode("utf-8", "surrogateescape")).hexdigest()[:HASH_HEX]


def citation_key(page: str, cite: Citation) -> str:
    """State key of a citation; it embeds the range, so ``reanchor`` must re-key."""
    return f"{page}|{cite.path}:{cite.start}-{cite.end}|{cite.symbol or ''}"


def find_windows(
    lines: list[str], length: int, digest: str, anchor: str | None = None
) -> list[int] | None:
    """1-based starts of every ``length``-line window whose hash is ``digest``.

    With ``anchor`` only windows containing a line with that text are tried
    (the cited symbol must still be inside the range). ``None`` when the work
    would exceed ``MAX_WINDOW_WORK`` line visits: the caller cannot relocate.
    """
    last = len(lines) - length  # last 0-based start
    if length < 1 or last < 0:
        return []
    if anchor is None:
        starts = range(last + 1)
    else:
        found: set[int] = set()
        for i, line in enumerate(lines):
            if anchor in line:
                found.update(range(max(0, i - length + 1), min(i, last) + 1))
        starts = sorted(found)
    if len(starts) * length > MAX_WINDOW_WORK:
        return None
    return [s + 1 for s in starts if range_hash(lines, s + 1, s + length) == digest]


def read_pages(root: Path, at_head: bool) -> dict[str, str]:
    """Page (relative to docs/wiki) -> text, from the work tree or from HEAD.

    HEAD mode reads committed blobs only, so a dirty tree cannot change the
    verdict for what is being pushed. Control files, non-markdown files,
    symlinks and non-UTF-8 pages are skipped; ``verify`` reports those.
    """
    root = Path(root)
    pages: dict[str, str] = {}
    if at_head:
        for path in gitview.ls_tree_files(root, WIKI_DIR) or []:
            rel = path[len(WIKI_DIR):]
            if rel.lower().endswith(".md") and rel not in CONTROL_FILES:
                text = gitview.show_head(root, path)
                if text is not None:
                    pages[rel] = text
        return pages
    for rel, path in walk_wiki(root)[1]:
        try:
            pages[rel] = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
    return pages


def read_state(root: Path, at_head: bool) -> dict:
    return state.load_head(root) if at_head else state.load(root)


def page_citations(rel: str, text: str) -> list[Citation]:
    """Citations that make claims, as ``verify`` sees them (human blocks, map lines and
    generated pages excluded)."""
    if rel == "index.md":
        text = agentmap.strip_map(text)
    elif docs_inventory.is_generated(text):
        return []
    return citations.parse(text)[0]


def head_lines(root: Path, path: str, cache: dict[str, list[str] | None]) -> list[str] | None:
    """Lines of ``path`` at HEAD as citations count them; cached per run."""
    if path not in cache:
        content = (
            gitview.show_head(root, path) if citations._shape_error(path) is None else None
        )
        cache[path] = None if content is None else citations.split_lines(content)
    return cache[path]


def moved_hashes(root: Path, pages: dict[str, str], st: dict) -> dict[str, str]:
    """Stored hashes of citations that only moved. ``mark`` keeps these so a plain re-mark
    cannot bless the old line numbers as the new baseline."""
    tracked = gitview.regular_tracked(Path(root))
    if tracked is None:
        return {}
    done = classify(root, pages, st, tracked, load_ignore(root, at_head=False))
    keys = (
        f"{f.page}|{f.path}:{f.start}-{f.end}|{f.symbol or ''}"
        for f in done.findings if f.category == "moved"
    )
    return {key: st["citations"][key] for key in keys if key in st["citations"]}


def baseline(
    root: Path, pages: dict[str, str], keep: dict[str, str] | None = None
) -> dict[str, str]:
    """State ``citations`` map for ``pages``: key -> range hash, for every citation whose
    range is in bounds at HEAD. Out-of-range citations are left out (``verify`` rejects them).
    Hashes in ``keep`` win over freshly computed ones."""
    root = Path(root)
    cache: dict[str, list[str] | None] = {}
    out: dict[str, str] = {}
    for rel, text in sorted(pages.items()):
        for cite in page_citations(rel, text):
            lines = head_lines(root, cite.path, cache)
            if lines is not None and 1 <= cite.start <= cite.end <= len(lines):
                key = citation_key(rel, cite)
                out[key] = (keep or {}).get(key) or range_hash(lines, cite.start, cite.end)
    return out


@dataclass(frozen=True)
class Finding:
    page: str
    line: int
    category: str  # moved | changed | missing
    path: str
    start: int
    end: int
    symbol: str | None
    reason: str = ""
    new_start: int | None = None
    new_end: int | None = None
    commits: tuple[str, ...] = ()


@dataclass
class Classification:
    findings: list[Finding]
    unhashed: list[tuple[str, Citation]]  # citations with no stored range hash


def _blocked(cite: Citation, ignore: list[str]) -> str | None:
    """Why ``cite`` may not be checked at all, mirroring ``citations._check``."""
    if len(cite.path) > citations.MAX_CITE_PATH:
        return "path too long"
    bad = citations._shape_error(cite.path)
    if bad:
        return bad
    if cite.path.startswith(WIKI_DIR):
        return f"cites the wiki itself ({cite.path})"
    if is_secret_path(cite.path):
        return f"secret path {cite.path}"
    if citations.is_ignored(cite.path, ignore):
        return f"ignored path {cite.path}"
    return None


def _classify_one(
    cite: Citation, lines: list[str], digest: str | None
) -> tuple[str, str, int | None] | None:
    """(category, reason, new start) or None when the citation is clean."""
    length = cite.end - cite.start + 1
    in_bounds = 1 <= cite.start <= cite.end <= len(lines)
    symbol_in_file = cite.symbol is None or any(cite.symbol in ln for ln in lines)
    if digest is None:
        if not symbol_in_file:
            return "missing", f"symbol `{cite.symbol}` not found in {cite.path}", None
        if in_bounds and (
            cite.symbol is None or cite.symbol in "\n".join(lines[cite.start - 1 : cite.end])
        ):
            return None
        return "changed", "no range hash yet; cannot prove the cited body moved unchanged", None
    if in_bounds and range_hash(lines, cite.start, cite.end) == digest:
        return None
    windows = find_windows(lines, length, digest, anchor=cite.symbol)
    if windows is None:
        return "changed", "cited range too large to relocate", None
    if len(windows) == 1:
        return "moved", "", windows[0]
    if len(windows) > 1:
        return "changed", f"ambiguous: {len(windows)} matches", None
    if not symbol_in_file:
        return "missing", f"symbol `{cite.symbol}` not found in {cite.path}", None
    return "changed", "cited body changed", None


def classify(
    root: Path,
    pages: dict[str, str],
    st: dict,
    tracked: set[str],
    ignore: list[str],
) -> Classification:
    """Classify every citation of ``pages`` against the HEAD content of the cited files."""
    root = Path(root)
    cache: dict[str, list[str] | None] = {}
    hashes = st.get("citations", {})
    result = Classification([], [])
    for rel, text in sorted(pages.items()):
        cites = page_citations(rel, text)
        if len(cites) > citations.MAX_CITATIONS:
            result.findings.append(
                Finding(rel, 1, "changed", "", 0, 0, None, f"too many citations (limit {citations.MAX_CITATIONS})")
            )
            continue
        for cite in cites:
            def found(category, reason, new_start=None):
                length = cite.end - cite.start
                result.findings.append(Finding(
                    rel, cite.line, category, cite.path, cite.start, cite.end, cite.symbol, reason,
                    new_start, None if new_start is None else new_start + length,
                ))
            blocked = _blocked(cite, ignore)
            if blocked:
                found("missing", blocked)
                continue
            lines = head_lines(root, cite.path, cache) if cite.path in tracked else None
            if lines is None:
                found("missing", f"{cite.path} not tracked at HEAD")
                continue
            digest = hashes.get(citation_key(rel, cite))
            if digest is None:
                result.unhashed.append((rel, cite))
            verdict = _classify_one(cite, lines, digest)
            if verdict:
                found(*verdict)
    return result


MAX_COMMITS_SHOWN = 5


def load_ignore(root: Path, at_head: bool) -> list[str]:
    """``.wikifyignore`` globs from the work tree or, in HEAD mode, from the commit."""
    if at_head:
        return citations.globs_from_text(gitview.show_head(Path(root), citations.IGNORE_REL))
    return citations.load_ignore(root)


def touched_since(root: Path, base: str) -> dict[str, list[str]] | None:
    """Path -> short hashes (newest first) of commits in ``base..HEAD`` that touched it."""
    commits = gitview.log_names_since(Path(root), base)
    if commits is None:
        return None
    touched: dict[str, list[str]] = {}
    for short, names in commits:
        for name in names:
            touched.setdefault(name, []).append(short)
    return touched


def attribute(findings: list[Finding], touched: dict[str, list[str]]) -> list[Finding]:
    """Findings with the commits that touched their cited path attached."""
    return [
        replace(f, commits=tuple(touched.get(f.path, ())[:MAX_COMMITS_SHOWN])) for f in findings
    ]


def uncovered_areas(
    changed: list[str], pages: dict[str, str], tracked: set[str], ignore: list[str]
) -> list[dict]:
    """Contexts with changed code that no page cites anything inside (warn-only)."""
    from agents.wikify import plan  # local import: plan pulls in the docs inventory

    cited = {c.path for rel, text in pages.items() for c in page_citations(rel, text)}
    alive = sorted(p for p in changed if p in tracked and plan._keep(p, ignore))
    areas: list[dict] = []
    for area in plan._contexts(alive):
        if any(path.startswith(area + "/") for path in cited):
            continue
        files = [p for p in alive if p.startswith(area + "/")]
        areas.append({"area": area, "files": files[:MAX_COMMITS_SHOWN * 2]})
    return areas
