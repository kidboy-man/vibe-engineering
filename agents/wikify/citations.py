"""Citation parser and verifier for wikify pages.

Ceiling: verification is structural (the cited path exists at HEAD, the range
is in bounds, the symbol occurs in the range), not semantic. Verification
reads committed content only, so uncommitted edits never satisfy a citation.
"""

from __future__ import annotations

import fnmatch
import functools
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

from agents.secret_policies import is_secret_path
from agents.wikify import gitview
from agents.wikify.state import WIKI_DIR

CITE = re.compile(r"\(src: ([^\s:`()]+):([0-9]{1,9})(?:-([0-9]{1,9}))?(?: `([^`]+)`)?\)")
HUMAN = re.compile(r"<!-- wikify:human -->.*?<!-- /wikify:human -->", re.S)
HEADING = re.compile(r"^#{1,6} ")
# No '[' or '(' inside the classes: an attempt never scans past the next
# bracket, so hostile text stays linear. Nested brackets / parens in a link
# are not a "pure link" and the paragraph falls to the citation rule.
LINK = re.compile(r"\[\[[^\[\]]*\]\]|\[[^\[\]]*\]\([^()]*\)")
IGNORE_REL = WIKI_DIR + ".wikifyignore"


@dataclass(frozen=True)
class Citation:
    path: str
    start: int
    end: int
    symbol: str | None
    line: int


HUMAN_BEGIN = "<!-- wikify:human -->"
HUMAN_END = "<!-- /wikify:human -->"


def human_spans(text: str) -> list[tuple[int, int]]:
    """(start, end) of each human block, left to right, end exclusive.

    Same semantics as ``HUMAN.finditer`` but linear: an unterminated begin
    marker ends the scan instead of being retried at every later marker.
    """
    spans: list[tuple[int, int]] = []
    pos = 0
    while True:
        begin = text.find(HUMAN_BEGIN, pos)
        if begin < 0:
            return spans
        end = text.find(HUMAN_END, begin + len(HUMAN_BEGIN))
        if end < 0:
            return spans
        pos = end + len(HUMAN_END)
        spans.append((begin, pos))


def _strip_human(text: str) -> str:
    out: list[str] = []
    last = 0
    for start, end in human_spans(text):
        out.append(text[last:start])
        out.append("\n" * text.count("\n", start, end))
        last = end
    out.append(text[last:])
    return "".join(out)


def _citations(clean: str) -> list[Citation]:
    out: list[Citation] = []
    pos, line = 0, 1  # finditer is ordered: count newlines only since the last match
    for m in CITE.finditer(clean):
        line += clean.count("\n", pos, m.start())
        pos = m.start()
        out.append(
            Citation(m.group(1), int(m.group(2)), int(m.group(3) or m.group(2)), m.group(4), line)
        )
    return out


def _uncited(clean: str) -> list[int]:
    out: list[int] = []
    block: list[tuple[int, str]] = []
    in_fence = False

    def flush() -> None:
        body = [(n, ln) for n, ln in block if not HEADING.match(ln)]
        block.clear()
        if not body:
            return
        text = "\n".join(ln for _, ln in body)
        pure_links = not re.sub(r"[\W_]+", "", LINK.sub("", text))
        if not pure_links and not CITE.search(text):
            out.append(body[0][0])

    for n, line in enumerate(clean.split("\n"), 1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            flush()
        elif in_fence:
            continue
        elif not line.strip():
            flush()
        else:
            block.append((n, line))
    flush()
    return out


def parse(text: str) -> tuple[list[Citation], list[int]]:
    """Citations and 1-based line numbers of uncited paragraphs (human blocks excluded)."""
    clean = _strip_human(text)
    return _citations(clean), _uncited(clean)


def _shape_error(path: str) -> str | None:
    if path.startswith("/") or re.match(r"^[A-Za-z]:", path):
        return "absolute path"
    if "\\" in path:
        return "backslash in path"
    if ".." in path.split("/"):
        return "'..' segment in path"
    return None


MAX_CONTROL_BYTES = 64 * 1024
MAX_CITE_PATH = 4096
MAX_CITATIONS = 2_000  # per page: bounds verify cost by count


def read_control_lines(path: Path) -> tuple[list[str], str]:
    """(lines, status) of a small control file; status ok | absent | rejected.

    Rejected = symlink, not a regular file, over the cap, not UTF-8, or a read
    error. lstat first and open non-blocking without following links, so a FIFO
    or a symlink planted in the working tree can neither hang nor redirect the
    read. Callers that guard a privacy control must not treat rejected as absent.
    """
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return [], "absent"
    except OSError:
        return [], "rejected"
    try:
        if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_CONTROL_BYTES:
            return [], "rejected"
        flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
        with os.fdopen(os.open(path, flags), "rb") as handle:
            data = handle.read(MAX_CONTROL_BYTES + 1)
        if len(data) > MAX_CONTROL_BYTES:
            return [], "rejected"
        return data.decode("utf-8").splitlines(), "ok"
    except (OSError, UnicodeDecodeError):
        return [], "rejected"


def _globs(lines: list[str]) -> list[str]:
    globs = (line.strip() for line in lines)
    return [g for g in globs if g and not g.startswith("#")]


def ignore_negations(root: Path) -> list[str]:
    """Line numbers of unsupported ``!`` negation lines in .wikifyignore."""
    lines = read_control_lines(Path(root) / IGNORE_REL)[0]
    return [str(n) for n, ln in enumerate(lines, 1) if ln.strip().startswith("!")]


def ignore_over_limits(root: Path) -> bool:
    """True when .wikifyignore exceeds the pattern-count/length/wildcard caps."""
    lines, status = read_control_lines(Path(root) / IGNORE_REL)
    globs = _globs(lines) if status == "ok" else []
    return len(globs) > MAX_IGNORE_PATTERNS or any(
        len(g) > MAX_IGNORE_PATTERN_LEN or len(_WILD.findall(g)) > MAX_IGNORE_WILDCARDS
        for g in globs
    )


def ignore_status(root: Path) -> str:
    status = read_control_lines(Path(root) / IGNORE_REL)[1]
    if status == "ok" and (ignore_negations(root) or ignore_over_limits(root)):
        return "rejected"  # fail closed: never silently apply a partial rule set
    return status


def load_ignore(root: Path) -> list[str]:
    if ignore_over_limits(root):
        return []  # rejected by ignore_status; never run an unbounded rule set
    return _globs(read_control_lines(Path(root) / IGNORE_REL)[0])



_WILD = re.compile(r"[*?\[]")
MAX_IGNORE_PATTERNS = 200
MAX_IGNORE_PATTERN_LEN = 200
MAX_IGNORE_WILDCARDS = 8  # per pattern: bounds fnmatch backtracking


@functools.lru_cache(maxsize=4096)
def _compile_glob(glob: str) -> tuple[str, tuple[tuple[str, object], ...]]:
    """(kind, segments): kind is any (slash-less, component match) or root."""
    pat = glob.lstrip("/").rstrip("/")
    anchored = "/" in pat or glob.startswith("/")
    segs: list[str] = []
    for seg in pat.split("/"):
        if seg == "**" and segs and segs[-1] == "**":
            continue  # collapse runs: keeps the matcher linear in the pattern
        segs.append(seg)
    wild = tuple(
        (seg, re.compile(fnmatch.translate(seg)).match if _WILD.search(seg) else None)
        for seg in segs
    ) if pat else ()
    return ("root" if anchored else "any"), wild


def _seg(part: str, seg: tuple[str, object]) -> bool:
    return seg[1](part) is not None if seg[1] else part == seg[0]


def _root_match(segs: tuple[tuple[str, object], ...], parts: list[str]) -> bool:
    """Match ``segs`` against a leading run of ``parts`` (set-of-states DP, no
    backtracking); ``**`` spans 0+ segments; a fully consumed pattern matches."""
    if segs[0][0] == "**" and len(segs) == 1:
        return True
    if segs[0][1] is None and parts[0] != segs[0][0]:
        return False  # literal first segment: cheap reject
    states = {0}
    for part in parts:
        nxt: set[int] = set()
        for i in states:
            if segs[i][0] == "**":
                if i + 1 >= len(segs):
                    return True  # trailing `**`: the whole subtree
                nxt.add(i)  # consume the segment, stay
                if _seg(part, segs[i + 1]):  # or skip `**` and match
                    nxt.add(i + 2)
            elif _seg(part, segs[i]):
                nxt.add(i + 1)
        if any(i >= len(segs) for i in nxt):
            return True
        # a leading `**` may also match zero segments, handled by the i + 2 branch
        states = nxt
    return False


def _ignored(path: str, glob: str) -> bool:
    """gitignore-like: no ``/`` -> any path component; otherwise (leading ``/`` or not)
    anchored at the repo root with ``*`` confined to one segment and ``**`` spanning
    segments. A match covers the subtree. ``!`` negation is rejected earlier."""
    kind, segs = _compile_glob(glob)
    if not segs:
        return False
    parts = path.split("/")
    if kind == "any":
        return any(_seg(part, segs[0]) for part in parts)
    return _root_match(segs, parts)


def is_ignored(path: str, globs: list[str]) -> bool:
    return any(_ignored(path, g) for g in globs)


def split_lines(content: str) -> list[str]:
    """Lines as citations count them: split on ``\\n``, ``\\r`` stripped, no empty tail."""
    lines = [ln.rstrip("\r") for ln in content.split("\n")]
    if lines[-1] == "":
        lines.pop()
    return lines


def _check(
    root: Path,
    cite: Citation,
    tracked: set[str],
    ignore: list[str],
    cache: dict[str, list[str] | None] | None = None,
) -> str | None:
    if len(cite.path) > MAX_CITE_PATH:  # before any glob matching
        return "path too long"
    bad = _shape_error(cite.path)
    if bad:
        return bad
    if cite.path.startswith(WIKI_DIR):  # would launder unverified wiki text
        return f"cites the wiki itself ({cite.path})"
    if is_secret_path(cite.path):
        return f"secret path {cite.path}"
    if is_ignored(cite.path, ignore):
        return f"ignored path {cite.path}"
    lines: list[str] | None = None
    if cite.path in tracked:
        if cache is not None and cite.path in cache:
            lines = cache[cite.path]
        else:
            content = gitview.show_head(root, cite.path)
            lines = split_lines(content) if content is not None else None
            if cache is not None:
                cache[cite.path] = lines
    if lines is None:
        return f"{cite.path} not tracked at HEAD"
    if not 1 <= cite.start <= cite.end <= len(lines):
        return f"range {cite.start}-{cite.end} out of range for {cite.path} ({len(lines)} lines)"
    if cite.symbol and cite.symbol not in "\n".join(lines[cite.start - 1 : cite.end]):
        return f"symbol `{cite.symbol}` not found in {cite.path}:{cite.start}-{cite.end}"
    return None


def verify_page(
    root: Path,
    page_rel: str,
    text: str,
    ignore: list[str],
    tracked: set[str] | None = None,
    cache: dict[str, list[str] | None] | None = None,
) -> list[str]:
    """Error strings ``"<page_rel>:<line>: <reason>"``; empty when the page verifies."""
    root = Path(root)
    cites, uncited = parse(text)
    if len(cites) > MAX_CITATIONS:
        return [f"{page_rel}:1: too many citations (limit {MAX_CITATIONS})"]
    if tracked is None:  # callers verifying many pages pass one set
        tracked = set(gitview.tracked_files(root))
    errors: list[tuple[int, str]] = []
    for cite in cites:
        reason = _check(root, cite, tracked, ignore, cache)
        if reason:
            errors.append((cite.line, reason))
    errors.extend((n, "uncited paragraph") for n in uncited)
    return [f"{page_rel}:{n}: {reason}" for n, reason in sorted(errors, key=lambda e: e[0])]


CONTROL_FILES = {".wikify.json", ".wikifyignore", ".wikify-allow", ".wikifydocs", "WIKIFY.md"}


def walk_wiki(root: Path) -> tuple[list[str], list[tuple[str, Path]]]:
    """Layout errors plus the pages (rel, path) under docs/wiki.

    Pages are regular non-symlink files ending in ``.md`` (any case); the
    top-level control files are skipped. Anything that cannot be stat'ed, is a
    symlink, or is neither a regular file nor a directory is an error.
    """
    root = Path(root)
    for rel in ("docs", "docs/wiki"):
        if (root / rel).is_symlink():
            return [f"{rel}: symlink not allowed"], []
    errors: list[str] = []
    pages: list[tuple[str, Path]] = []
    wiki = root / WIKI_DIR
    if wiki.exists() and not wiki.is_dir():
        return ["docs/wiki: not a directory"], pages
    if not wiki.is_dir():
        return errors, pages

    def unreadable(exc: OSError) -> None:
        rel = Path(exc.filename).relative_to(wiki).as_posix() if exc.filename else ""
        errors.append(f"{WIKI_DIR}{rel}: unreadable directory")

    for dirpath, dirnames, filenames in os.walk(wiki, followlinks=False, onerror=unreadable):
        here = Path(dirpath)
        for name in sorted(dirnames + filenames):
            path = here / name
            rel = path.relative_to(wiki).as_posix()
            try:
                mode = os.lstat(path).st_mode
            except OSError:
                errors.append(f"{WIKI_DIR}{rel}: unreadable")
                continue
            if stat.S_ISLNK(mode):
                errors.append(f"{WIKI_DIR}{rel}: symlink not allowed")
            elif stat.S_ISREG(mode):
                if here == wiki and name in CONTROL_FILES:
                    continue
                if name.lower().endswith(".md"):
                    pages.append((rel, path))
                else:
                    errors.append(f"{WIKI_DIR}{rel}: only markdown pages and control files are allowed")
            elif not stat.S_ISDIR(mode):
                errors.append(f"{WIKI_DIR}{rel}: not a regular file")
    return errors, sorted(pages)


def index(root: Path) -> dict[str, set[str]]:
    """Page (relative to docs/wiki) -> repo paths it cites, from the working tree."""
    out: dict[str, set[str]] = {}
    for rel, page in walk_wiki(root)[1]:
        try:
            text = page.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        cites, _ = parse(text)
        out[rel] = {c.path for c in cites if _shape_error(c.path) is None}
    return out
