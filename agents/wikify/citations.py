"""Citation parser and verifier for wikify pages.

Ceiling: verification is structural (the cited path exists at HEAD, the range
is in bounds, the symbol occurs in the range), not semantic. Verification
reads committed content only, so uncommitted edits never satisfy a citation.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from pathlib import Path

from agents.secret_policies import is_secret_path
from agents.wikify import gitview
from agents.wikify.state import WIKI_DIR

CITE = re.compile(r"\(src: ([^\s:`()]+):(\d+)(?:-(\d+))?(?: `([^`]+)`)?\)")
HUMAN = re.compile(r"<!-- wikify:human -->.*?<!-- /wikify:human -->", re.S)
LINK = re.compile(r"\[\[[^\]]*\]\]|\[[^\]]*\]\([^)]*\)")
IGNORE_REL = WIKI_DIR + ".wikifyignore"


@dataclass(frozen=True)
class Citation:
    path: str
    start: int
    end: int
    symbol: str | None
    line: int


def _strip_human(text: str) -> str:
    return HUMAN.sub(lambda m: "\n" * m.group(0).count("\n"), text)


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


def _is_exempt(block: list[str]) -> bool:
    if block[0].lstrip().startswith("#"):
        return True
    rest = re.sub(r"[\W_]+", "", LINK.sub("", "\n".join(block)))
    return not rest  # empty or a pure link list


def _uncited(clean: str) -> list[int]:
    out: list[int] = []
    block: list[str] = []
    first = 0
    in_fence = False

    def flush() -> None:
        if block and not _is_exempt(block) and not CITE.search("\n".join(block)):
            out.append(first)
        block.clear()

    for n, line in enumerate(clean.split("\n"), 1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            flush()
            continue
        if in_fence:
            continue
        if not line.strip():
            flush()
            continue
        if not block:
            first = n
        block.append(line)
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


def load_ignore(root: Path) -> list[str]:
    try:
        lines = (Path(root) / IGNORE_REL).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return []
    globs = (line.strip() for line in lines)
    return [g for g in globs if g and not g.startswith("#")]


def _check(root: Path, cite: Citation, tracked: set[str], ignore: list[str]) -> str | None:
    bad = _shape_error(cite.path)
    if bad:
        return bad
    if is_secret_path(cite.path):
        return f"secret path {cite.path}"
    if any(fnmatch.fnmatchcase(cite.path, g) for g in ignore):
        return f"ignored path {cite.path}"
    content = gitview.show_head(root, cite.path) if cite.path in tracked else None
    if content is None:
        return f"{cite.path} not tracked at HEAD"
    lines = content.splitlines()
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
    if page_rel != "index.md":
        errors.extend((n, "uncited paragraph") for n in uncited)
    return [f"{page_rel}:{n}: {reason}" for n, reason in sorted(errors, key=lambda e: e[0])]


def index(root: Path) -> dict[str, set[str]]:
    """Page (relative to docs/wiki) -> repo paths it cites, from the working tree."""
    wiki = Path(root) / WIKI_DIR
    out: dict[str, set[str]] = {}
    for page in sorted(wiki.rglob("*.md")):
        rel = page.relative_to(wiki).as_posix()
        if rel == "WIKIFY.md":
            continue
        try:
            text = page.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        cites, _ = parse(text)
        out[rel] = {c.path for c in cites if _shape_error(c.path) is None}
    return out
