"""Inventory of existing markdown docs eligible for generated outline pages.

Eligible docs are tracked files read at HEAD only. Hard exclusions (instruction
files, the wiki itself, secret and ignored paths) are silent; shape or size
problems are reported as ``skipped`` so the user can see why a doc is absent.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from agents.secret_policies import is_secret_path
from agents.wikify import citations, gitview, pointer
from agents.wikify.state import WIKI_DIR

INCLUDES_REL = WIKI_DIR + ".wikifydocs"
MAX_DOCS = 500
MAX_DOC_BYTES = 1 << 20
SUFFIXES = (".md", ".markdown")
EXCLUDED_NAMES = {"agents.md", "claude.md", "gemini.md", "skill.md"}  # casefolded
DEFAULT_PREFIXES = ("readme", "contributing", "changelog", "architecture")
_PATH_BAD = frozenset(":`()[]<>@\\")


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
    lines, _ = citations.read_control_lines(Path(root) / INCLUDES_REL)
    return citations._globs(lines)


def includes_status(root: Path) -> str:
    return citations.read_control_lines(Path(root) / INCLUDES_REL)[1]


def _citable(path: str) -> bool:
    """Doc paths are untrusted text that lands in headings and links: allow no
    whitespace, markup or citation-syntax characters, and no control, format,
    surrogate, private-use or unassigned characters (bidi, zero-width, NEL, ...)."""
    return not any(
        ch.isspace() or ch in _PATH_BAD or unicodedata.category(ch)[0] == "C"
        for ch in path
    )


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
    if citations.ignore_status(root) == "rejected":  # fail closed: privacy control
        return Inventory([], [Skip(".wikifyignore", "ignore file rejected; ignore rules not applied")])
    includes = load_includes(root)
    ignore = citations.load_ignore(root)
    candidates: list[str] = []
    skipped: list[Skip] = []
    if includes_status(root) == "rejected":  # fewer docs, never more
        skipped.append(Skip(INCLUDES_REL, "includes file rejected"))
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
        if not _citable(path):
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


MARKER = "<!-- wikify:generated -->"
MAX_SECTIONS = 200
MAX_INDEX_DOCS = 200
MAX_TITLE = 80
MAX_FRAGMENT = 60
NOTE = "documented, not code-verified; titles are untrusted text"
INDEX_PAGE = "sources/index.md"
_HEADING = re.compile(r" {0,3}(#{1,6})(?:[ \t]+(.*))?")
_FRONT_MATTER = re.compile(r"[A-Za-z0-9_-]+\s*:|#|-(?:[ \t]|$)")
_STRIPPED = frozenset("`[]()<>@")  # never shown in a title or fragment
_SPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class Section:
    level: int
    title: str
    start: int
    end: int
    fragment: str


def _drop(ch: str) -> bool:
    return ch in _STRIPPED or unicodedata.category(ch)[0] == "C" or ch in "\u2028\u2029"


def _unclose(raw: str) -> str:
    """Strip the optional ATX closing ``#`` run (linear; only after space/tab or alone)."""
    s = raw.rstrip(" \t")
    t = s.rstrip("#")
    if t != s and (not t or t[-1] in " \t"):
        s = t.rstrip(" \t")
    return s


def _title(raw: str) -> str:
    kept = "".join(" " if ch.isspace() else ch for ch in raw if not _drop(ch) or ch.isspace())
    return _SPACE.sub(" ", kept).strip()[:MAX_TITLE].strip() or "(untitled)"


def _fragment(line: str) -> str:
    """Longest run >= 3 chars with no backtick, control or markup char (cut to 60).

    A substring of the heading line, so it occurs literally on the cited range.
    """
    runs: list[str] = []
    cur: list[str] = []
    for ch in line:
        if _drop(ch):
            runs.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    runs.append("".join(cur))
    best = ""
    for run in runs:
        run = run.strip()
        if len(run) >= 3 and len(run) > len(best):
            best = run
    return best[:MAX_FRAGMENT].rstrip()


def _lines(text: str) -> list[str]:
    """Lines as the citation verifier counts them: split on ``\\n``, ``\\r`` stripped."""
    lines = [ln.rstrip("\r") for ln in text.split("\n")]
    if lines[-1] == "":
        lines.pop()
    return lines


def outline(text: str) -> list[Section]:
    lines = _lines(text)
    if lines and lines[0].startswith("\ufeff"):
        lines[0] = lines[0][1:]
    first = 0
    if lines and lines[0].rstrip() == "---":
        close = next((i for i, ln in enumerate(lines[1:], 1) if ln.rstrip() in ("---", "...")), None)
        body = next((ln for ln in lines[1:close] if ln.strip()), "") if close else ""
        if close is not None and _FRONT_MATTER.match(body):
            first = close + 1
    found: list[tuple[int, int, str]] = []  # (line number, level, heading line)
    for i, line, fenced in pointer._scan(lines[first:]):
        m = None if fenced else _HEADING.fullmatch(line)
        if m:
            found.append((first + i + 1, len(m.group(1)), line))
    sections: list[Section] = []
    later: list[tuple[int, int]] = []  # (level, start) stack for "next heading at same or shallower level"
    for start, level, line in reversed(found):
        while later and later[-1][0] > level:
            later.pop()
        end = later[-1][1] - 1 if later else len(lines)
        later.append((level, start))
        m = _HEADING.fullmatch(line)
        sections.append(Section(level, _title(_unclose(m.group(2) or "")), start, end, _fragment(line)))
    sections.reverse()
    return sections


def page_rel(doc: str) -> str:
    """Page path under docs/wiki; always ends in ``.md`` so ``walk_wiki`` accepts it."""
    rel = "sources/" + doc
    if rel.casefold() == INDEX_PAGE:
        return rel + ".outline.md"
    return rel if rel.casefold().endswith(".md") else rel + ".md"


def _cite(doc: str, start: int, end: int, fragment: str = "") -> str:
    return f"(src: {doc}:{start}-{end}" + (f" `{fragment}`" if fragment else "") + ")"


def render_doc_page(doc: str, text: str, sections: list[Section] | None = None) -> str:
    if sections is None:
        sections = outline(text)
    last = max(len(_lines(text)), 1)
    out = [MARKER, f"# {doc} ({NOTE})", ""]
    base = min((s.level for s in sections), default=1)
    for s in sections[:MAX_SECTIONS]:
        out.append("  " * (s.level - base) + f"- {s.title} " + _cite(doc, s.start, s.end, s.fragment))
    if len(sections) > MAX_SECTIONS:
        out.append(f"- ({len(sections) - MAX_SECTIONS} more sections not listed) " + _cite(doc, 1, last))
    elif not sections:
        out.append("- (no headings) " + _cite(doc, 1, last))
    return "\n".join(out) + "\n"


def render_index(rows: list[tuple[str, str, int, int]]) -> str:
    out = [MARKER, f"# Documented sources ({NOTE.replace('documented, ', '')})", ""]
    for doc, rel, count, last in rows[:MAX_INDEX_DOCS]:
        link = rel[len("sources/"):]
        out.append(f"- [{doc}]({link}) \u2014 {count} sections " + _cite(doc, 1, last))
    if len(rows) > MAX_INDEX_DOCS:
        doc, last = rows[0][0], rows[0][3]
        out.append(f"- ({len(rows) - MAX_INDEX_DOCS} more docs not listed) " + _cite(doc, 1, last))
    return "\n".join(out) + "\n"


def expected_pages(root: Path) -> tuple[dict[str, str], Inventory]:
    """Every generated page (path relative to docs/wiki) plus the inventory used.

    Docs that vanish between inventory and read, or whose page path collides
    with an earlier doc's, move to ``skipped`` instead of raising.
    """
    root = Path(root)
    inv = inventory(root)
    pages: dict[str, str] = {}
    rows: list[tuple[str, str, int, int]] = []
    docs: list[str] = []
    skipped = list(inv.skipped)
    taken: set[str] = set()
    for doc in sorted(inv.docs):
        rel = page_rel(doc)
        text = gitview.show_head(root, doc)
        if text is None:
            skipped.append(Skip(doc, "unreadable at HEAD (not committed?)"))
        elif citations._shape_error(doc):  # defensive: never emit a page that cannot verify
            skipped.append(Skip(doc, "path not citable"))
        elif rel.casefold() in taken:  # also case-insensitive: stable on any filesystem
            skipped.append(Skip(doc, "page path collision"))
        else:
            taken.add(rel.casefold())
            docs.append(doc)
            sections = outline(text)
            pages[rel] = render_doc_page(doc, text, sections)
            rows.append((doc, rel, len(sections), max(len(_lines(text)), 1)))
    if rows:
        pages[INDEX_PAGE] = render_index(rows)
    return pages, Inventory(docs, sorted(skipped, key=lambda s: s.path))


def is_generated(text: str) -> bool:
    return text.split("\n", 1)[0] == MARKER


def blank_marker(text: str) -> str:
    """Marker line emptied, newline kept, so citation line numbers still hold."""
    return "\n" + text.split("\n", 1)[1] if "\n" in text else ""


def status(
    root: Path,
    texts: dict[str, str],
    built: tuple[dict[str, str], Inventory] | None = None,
) -> dict:
    """Generated-doc state against the pages present (``texts``, keyed by wiki rel).

    ``built`` is an ``expected_pages`` result, so callers that already have one
    do not recompute it.
    """
    expected, inv = built if built is not None else expected_pages(root)
    return {
        "unindexed": [d for d in inv.docs if page_rel(d) not in texts],
        "stale": sorted(
            rel for rel, text in texts.items()
            if is_generated(text) and text != expected.get(rel)
        ),
        "skipped": [{"path": s.path, "reason": s.reason} for s in inv.skipped],
    }
