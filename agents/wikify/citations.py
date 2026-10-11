"""Citation parser and verifier for wikify pages.

Ceiling: verification is structural (the cited path exists at HEAD, the range
is in bounds, the symbol occurs in the range), not semantic. Verification
reads committed content only, so uncommitted edits never satisfy a citation.
"""

from __future__ import annotations

import fnmatch
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
LINK = re.compile(r"\[\[[^\]]*\]\]|\[[^\]]*\]\([^)]*\)")
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
    return [
        Citation(
            m.group(1),
            int(m.group(2)),
            int(m.group(3) or m.group(2)),
            m.group(4),
            clean.count("\n", 0, m.start()) + 1,
        )
        for m in CITE.finditer(clean)
    ]


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


def ignore_status(root: Path) -> str:
    return read_control_lines(Path(root) / IGNORE_REL)[1]


def load_ignore(root: Path) -> list[str]:
    return _globs(read_control_lines(Path(root) / IGNORE_REL)[0])



def _ignored(path: str, glob: str) -> bool:
    prefix = glob.rstrip("/")
    return (
        fnmatch.fnmatchcase(path, glob)
        or path == prefix
        or path.startswith(prefix + "/")
    )


def is_ignored(path: str, globs: list[str]) -> bool:
    return any(_ignored(path, g) for g in globs)


def _check(root: Path, cite: Citation, tracked: set[str], ignore: list[str]) -> str | None:
    bad = _shape_error(cite.path)
    if bad:
        return bad
    if cite.path.startswith(WIKI_DIR):  # would launder unverified wiki text
        return f"cites the wiki itself ({cite.path})"
    if is_secret_path(cite.path):
        return f"secret path {cite.path}"
    if is_ignored(cite.path, ignore):
        return f"ignored path {cite.path}"
    content = gitview.show_head(root, cite.path) if cite.path in tracked else None
    if content is None:
        return f"{cite.path} not tracked at HEAD"
    lines = [ln.rstrip("\r") for ln in content.split("\n")]
    if lines[-1] == "":
        lines.pop()
    if not 1 <= cite.start <= cite.end <= len(lines):
        return f"range {cite.start}-{cite.end} out of range for {cite.path} ({len(lines)} lines)"
    if cite.symbol and cite.symbol not in "\n".join(lines[cite.start - 1 : cite.end]):
        return f"symbol `{cite.symbol}` not found in {cite.path}:{cite.start}-{cite.end}"
    return None


def verify_page(root: Path, page_rel: str, text: str, ignore: list[str]) -> list[str]:
    """Error strings ``"<page_rel>:<line>: <reason>"``; empty when the page verifies."""
    root = Path(root)
    cites, uncited = parse(text)
    tracked = set(gitview.tracked_files(root))
    errors: list[tuple[int, str]] = []
    for cite in cites:
        reason = _check(root, cite, tracked, ignore)
        if reason:
            errors.append((cite.line, reason))
    errors.extend((n, "uncited paragraph") for n in uncited)
    return [f"{page_rel}:{n}: {reason}" for n, reason in sorted(errors, key=lambda e: e[0])]


CONTROL_FILES = {".wikify.json", ".wikifyignore", ".wikify-allow", "WIKIFY.md"}


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
