"""``vibe wikify docs``: write generated outline pages for existing markdown docs.

Security-sensitive like ``pointer``: plan every page first, refuse the whole
command on anything unsafe, and only then write under ``docs/wiki/sources/``.
A hand-written page (no marker on its first line) is never overwritten, and
generated pages that are no longer expected are reported, never deleted.
Pages are written to a temp file and renamed, so a failure leaves no
half-written page.
"""

from __future__ import annotations

import difflib
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from agents.wikify import docs_inventory as di
from agents.wikify import gitview, state
from agents.wikify.pointer import _safe
from agents.wikify.state import WIKI_DIR

INDEX_REL = WIKI_DIR + "index.md"
SOURCES_REL = WIKI_DIR + "sources"
MAX_SKIPPED_SHOWN = 50
READ_CAP = 1 << 20
_MARKER = di.MARKER.encode()


@dataclass(frozen=True)
class Page:
    rel: str  # repo-relative
    action: str  # create | update | unchanged
    old: str
    new: str


def _is_generated(data: bytes) -> bool:
    return data.split(b"\n", 1)[0].rstrip(b"\r") == _MARKER


def _read(path: Path) -> bytes | None:
    """At most READ_CAP bytes (no symlink follow where supported); None when larger."""
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags), "rb") as fh:
        data = fh.read(READ_CAP + 1)
    return None if len(data) > READ_CAP else data


def _plan_page(root: Path, rel: str, new: str) -> Page | str:
    """The planned change, or the refusal reason."""
    path = root / rel
    here = root / SOURCES_REL
    for part in ("",) + Path(rel).relative_to(SOURCES_REL).parent.parts:
        here = here / part if part else here
        try:
            mode = os.lstat(here).st_mode
        except FileNotFoundError:
            break
        except OSError as exc:
            return f"{rel}: cannot inspect directory: {type(exc).__name__}"
        if not stat.S_ISDIR(mode):
            return f"{here.relative_to(root).as_posix()} is a symlink or not a directory"
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return Page(rel, "create", "", new)
    except OSError as exc:
        return f"{rel}: cannot inspect: {type(exc).__name__}"
    if stat.S_ISLNK(st.st_mode):
        return f"{rel} is a symlink"
    if not stat.S_ISREG(st.st_mode):
        return f"{rel} is not a regular file"
    if st.st_nlink > 1:
        return f"{rel} has multiple hard links; writing could change a file outside the repo"
    try:
        data = _read(path)
    except OSError as exc:
        return f"{rel}: unreadable: {type(exc).__name__}"
    if data is None or not _is_generated(data):
        return f"{rel} exists and is not a generated page (no {di.MARKER} first line); not overwriting"
    try:
        old = data.decode("utf-8")
    except UnicodeDecodeError:
        return f"{rel} is not valid UTF-8; not overwriting"
    return Page(rel, "unchanged" if old == new else "update", old, new)


def _stale(root: Path, expected: set[str]) -> list[str]:
    """Generated pages under sources/ that are no longer expected (read-only)."""
    out: list[str] = []
    top = root / SOURCES_REL
    for dirpath, _, names in os.walk(top, followlinks=False):
        for name in names:
            path = Path(dirpath) / name
            rel = path.relative_to(root).as_posix()
            if rel in expected or not name.lower().endswith(".md"):
                continue
            try:
                if not stat.S_ISREG(os.lstat(path).st_mode):
                    continue
                data = _read(path)
            except OSError:
                continue
            if data is not None and _is_generated(data):
                out.append(rel)
    return sorted(out)


def _diff(page: Page) -> list[str]:
    return [
        _safe(line)
        for line in difflib.unified_diff(
            page.old.splitlines(), page.new.splitlines(),
            fromfile=f"a/{page.rel}", tofile=f"b/{page.rel}", lineterm="",
        )
    ]


def _write(root: Path, page: Page) -> None:
    dest = root / page.rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f".{dest.name}.{os.getpid()}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    fd = os.open(tmp, flags | getattr(os, "O_NOFOLLOW", 0), 0o666)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(page.new.encode("utf-8"))
        os.replace(tmp, dest)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def cmd_docs(cwd: str | Path | None = None, dry_run: bool = False) -> int:
    root = gitview.repo_root(cwd or os.getcwd())
    if root is None:
        print("not a git repository")
        return 1
    if not (root / INDEX_REL).is_file():
        print(f"{INDEX_REL} is missing; run vibe wikify init first")
        return 1
    try:
        state.check_wiki_path(root)
    except state.UnsafeWikiPath as exc:
        print(f"refused: {exc}\nnothing written")
        return 1
    pages, inv = di.expected_pages(root)
    planned: list[Page] = []
    refusals: list[str] = []
    for rel in sorted(pages):
        result = _plan_page(root, f"{WIKI_DIR}{rel}", pages[rel])
        (refusals if isinstance(result, str) else planned).append(result)
    if refusals:
        print("\n".join(f"refused: {_safe(r)}" for r in refusals))
        print("nothing written")
        return 1
    for page in planned:
        print(f"{page.action} {page.rel}")
        if page.action != "unchanged":
            print("\n".join(_diff(page)))
    for rel in _stale(root, {p.rel for p in planned}):
        print(f"stale {_safe(rel)}")
    for skip in inv.skipped[:MAX_SKIPPED_SHOWN]:
        print(f"skipped {_safe(skip.path)}: {skip.reason}")
    if len(inv.skipped) > MAX_SKIPPED_SHOWN:
        print(f"... and {len(inv.skipped) - MAX_SKIPPED_SHOWN} more skipped")
    todo = [p for p in planned if p.action != "unchanged"]
    if dry_run:
        print("dry run: no files written")
        return 0
    try:
        for page in todo:
            _write(root, page)
    except OSError as exc:
        print(f"refused: write failed: {type(exc).__name__}")
        return 1
    if todo:
        print(
            "Next: review git status --short -- docs/wiki; add one entry for "
            "sources/index.md to the map in docs/wiki/index.md if it is missing, "
            "then run vibe wikify verify and mark."
        )
    return 0
