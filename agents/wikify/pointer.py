"""The agent pointer block: a static, marked section in AGENTS.md & co.

Security-sensitive: this writes into user-owned files every teammate's agent
loads. It only ever writes the static TEMPLATE between the markers, never
follows a symlink out of the repo, and applies all changes or none.
"""

from __future__ import annotations

import difflib
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from agents.merge_strategies import marked_section_strategy
from agents.wikify import gitview

BEGIN = "<!-- wikify:pointer -->\n"
END = "<!-- /wikify:pointer -->\n"
TEMPLATE = (
    "## Repo docs (wikify)\n"
    "Repo knowledge lives in `docs/wiki/`. Start at [docs/wiki/index.md](docs/wiki/index.md): it is a map.\n"
    "Load only the pages whose \"when\" hint matches your task; do not read the whole wiki.\n"
)
TARGETS = ("AGENTS.md", "CLAUDE.md", "GEMINI.md")
INDEX_REL = "docs/wiki/index.md"
REFUSED = "refused: "


@dataclass(frozen=True)
class Change:
    rel: str
    action: str  # create | merge | unchanged
    old: str | None
    new: str


_BOM = "\ufeff"
_CONTROL = re.compile("[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def _safe(line: str) -> str:
    """Escape control characters so a diff can never drive the terminal."""
    return _CONTROL.sub(lambda m: f"\\x{ord(m.group()):02x}", line)


def _fenced_begin(text: str) -> bool:
    """True when a BEGIN marker line sits inside a ``` / ~~~ code fence."""
    fence = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("```", "~~~")):
            if fence is None:
                fence = stripped[:3]
            elif stripped[:3] == fence:
                fence = None
        elif fence and stripped == BEGIN.strip():
            return True
    return False


def _merge(existing: str) -> tuple[str, str] | None:
    """Merge keeping a leading BOM first; None when the markers are ambiguous."""
    if existing.startswith(_BOM):
        merged = _merge_body(existing[1:])
        return None if merged is None else (_BOM + merged[0], merged[1])
    return _merge_body(existing)


def _merge_body(existing: str) -> tuple[str, str] | None:
    eol = "\r\n" if BEGIN[:-1] + "\r\n" in existing else "\n"
    begin, end, template = (s.replace("\n", eol) for s in (BEGIN, END, TEMPLATE))
    nb, ne = existing.count(begin), existing.count(end)
    if (nb, ne) != (0, 0):
        if nb != 1 or ne != 1 or existing.index(begin) > existing.index(end):
            return None
        return marked_section_strategy(template, existing, begin, end)
    return marked_section_strategy(TEMPLATE, existing, BEGIN, END)


def plan_link(root: Path) -> tuple[list[Change], list[str]]:
    """Compute every change; refusals in the notes start with ``refused: ``."""
    root = Path(root)
    real_root = root.resolve()
    changes: list[Change] = []
    notes: list[str] = []
    if not (root / INDEX_REL).is_file():
        return [], [f"{REFUSED}{INDEX_REL} is missing; run `vibe wikify init` first"]
    for rel in TARGETS:
        path = root / rel
        if path.is_symlink():
            try:
                resolved = path.resolve(strict=True)
            except (OSError, RuntimeError):
                notes.append(f"{REFUSED}{rel} is a broken or looping symlink")
                continue
            target = resolved.relative_to(real_root).as_posix() if resolved.is_relative_to(real_root) else None
            if target in TARGETS and target != rel and resolved.is_file():
                notes.append(f"{rel} -> {target}: covered by its target")
            else:
                notes.append(f"{REFUSED}{rel} is a symlink that does not resolve to another target in the repo")
            continue
        exists = path.exists()
        if not exists and rel != TARGETS[0]:
            continue
        if exists and not path.is_file():
            notes.append(f"{REFUSED}{rel} is not a regular file")
            continue
        if gitview.ignored(root, [rel]):
            notes.append(f"{REFUSED}{rel} is gitignored; the pointer block would not be shared")
            continue
        if not exists:
            changes.append(Change(rel, "create", None, BEGIN + TEMPLATE + END))
            continue
        try:
            hard = path.stat().st_nlink > 1
            old = path.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError):
            notes.append(f"{REFUSED}{rel} is unreadable or not valid UTF-8")
            continue
        if hard:
            notes.append(f"{REFUSED}{rel} has multiple hard links; writing could change a file outside the repo")
            continue
        if _fenced_begin(old):
            notes.append(f"{REFUSED}{rel} has a wikify:pointer marker inside a code fence; move or remove the example")
            continue
        merged = _merge(old)
        if merged is None:
            notes.append(f"{REFUSED}{rel} has unbalanced or repeated wikify:pointer markers; fix by hand")
            continue
        changes.append(Change(rel, merged[1], old, merged[0]))
    return changes, notes


def _diff(change: Change) -> list[str]:
    old = (change.old or "").splitlines()
    return [
        _safe(line)
        for line in difflib.unified_diff(
            old, change.new.splitlines(),
            fromfile=f"a/{change.rel}", tofile=f"b/{change.rel}", lineterm="",
        )
    ]


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")


def _open(path: Path, create: bool) -> int:
    """Open for writing without following a symlink where the OS supports it."""
    flags = os.O_WRONLY | (os.O_CREAT | os.O_EXCL if create else os.O_TRUNC)
    return os.open(path, flags | getattr(os, "O_NOFOLLOW", 0), 0o666)


def _put(path: Path, text: str, create: bool) -> None:
    with os.fdopen(_open(path, create), "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def _restore(root: Path, change: Change) -> None:
    if change.old is None:
        (root / change.rel).unlink(missing_ok=True)
    else:
        _put(root / change.rel, change.old, create=False)


def _write(root: Path, changes: list[Change]) -> tuple[str | None, Path | None]:
    """Back up then write; on any failure roll back. Returns (error, backup dir)."""
    merges = [c for c in changes if c.action == "merge"]
    backup: Path | None = None
    if merges:
        gd = gitview.git_dir(root)
        if gd is None:
            return "git dir unavailable, cannot back up existing files", None
        try:
            (gd / "wikify-backups").mkdir(parents=True, exist_ok=True)
            backup = gd / "wikify-backups" / _stamp()
            backup.mkdir(exist_ok=False)
            for c in merges:
                dest = backup / c.rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(root / c.rel, dest)
        except FileExistsError:
            return "backup directory already exists; rerun", None
        except OSError as exc:
            return f"backup failed: {type(exc).__name__}", None
    touched: list[Change] = []
    try:
        for c in changes:
            fd = _open(root / c.rel, create=c.old is None)  # raises before touching
            touched.append(c)
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
                fh.write(c.new)
    except OSError as exc:
        failed = []
        for c in touched:  # restore: nothing is left half-applied
            try:
                _restore(root, c)
            except OSError:
                failed.append(c.rel)
        if failed:
            where = f"; backup at {backup}" if backup else ""
            return (
                "\n".join(f"rollback failed for {rel}{where}" for rel in failed),
                backup,
            )
        return f"write failed: {type(exc).__name__}; rolled back", backup
    return None, backup


def cmd_link(cwd: str | Path | None = None, dry_run: bool = False) -> int:
    root = gitview.repo_root(cwd or os.getcwd())
    if root is None:
        print("not a git repository")
        return 1
    changes, notes = plan_link(root)
    refusals = [n for n in notes if n.startswith(REFUSED)]
    if refusals:
        print("\n".join(refusals))
        print("nothing written")
        return 1
    for change in changes:
        label = {"create": "create", "merge": "update"}.get(change.action, "unchanged")
        print(f"{label} {change.rel}")
        if change.action != "unchanged":
            print("\n".join(_diff(change)))
    for note in notes:
        print(note)
    todo = [c for c in changes if c.action != "unchanged"]
    if dry_run:
        print("dry run: no files written")
        return 0
    if not todo:
        return 0
    error, backup = _write(root, todo)
    if error:
        print(error if error.startswith("rollback") else f"refused: {error}")
        return 1
    if backup is not None:
        print(f"backup: {backup}")
    print(
        f"Next: commit {' '.join(c.rel for c in todo)} in their own commit "
        "(not together with docs/wiki), then run vibe wikify mark."
    )
    return 0


def pointer_notices(root: Path) -> list[str]:
    """Verify notices about the pointer block; never raises, never fails verify."""
    root = Path(root)
    notices: list[str] = []
    blocks: list[str] = []
    seen = False
    for rel in TARGETS:
        path = root / rel
        try:
            if path.is_symlink() or not path.is_file():
                continue
            text = path.read_bytes().decode("utf-8").replace("\r\n", "\n")
        except (OSError, UnicodeDecodeError):
            notices.append(f"NOTICE: could not read {rel}")
            continue
        if BEGIN in text and END in text and text.index(BEGIN) < text.index(END):
            seen = True
            inner = text.partition(BEGIN)[2].partition(END)[0]
            blocks.append(rel)
            if inner != TEMPLATE:
                notices.append(f"POINTER STALE: {rel}; run vibe wikify link")
    if not seen and not notices:
        notices.append(
            "NOTICE: no wikify pointer block in AGENTS.md/CLAUDE.md/GEMINI.md; "
            "run vibe wikify link"
        )
    try:
        index_ok = (root / INDEX_REL).is_file()
    except OSError:
        index_ok = True
    if not index_ok:
        notices += [
            f"POINTER BROKEN: {rel} points at a missing {INDEX_REL}" for rel in blocks
        ]
    return notices
