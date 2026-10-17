"""Read-only git helpers for wikify.

Every call uses a fixed argv list (never a shell) with a timeout. Failures
degrade to empty/None so callers can fail safe, including on repos with no
commits.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

TIMEOUT_SECONDS = 10


def run_git(root: Path, *args: str) -> subprocess.CompletedProcess:
    """Run ``git <args>`` in ``root``; a timeout yields returncode 124."""
    argv = ["git", "-c", "core.quotePath=false", *args]
    try:
        return subprocess.run(
            argv,
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return subprocess.CompletedProcess(argv, 124, "", str(exc))


def _lines(result: subprocess.CompletedProcess) -> list[str]:
    return [line for line in result.stdout.splitlines() if line]


def repo_root(cwd: str | Path) -> Path | None:
    result = run_git(Path(cwd), "rev-parse", "--show-toplevel")
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return Path(result.stdout.strip())


def head(root: Path) -> str | None:
    result = run_git(root, "rev-parse", "--verify", "-q", "HEAD")
    return result.stdout.strip() or None if result.returncode == 0 else None


def tracked_files_or_none(root: Path) -> list[str] | None:
    """Paths in the index (``git ls-files``); None on error."""
    result = run_git(root, "ls-files")
    return _lines(result) if result.returncode == 0 else None


def tracked_files(root: Path) -> list[str]:
    """Paths in the index (``git ls-files``); empty on error."""
    return tracked_files_or_none(root) or []


def regular_tracked(root: Path) -> set[str] | None:
    """Paths that are regular files in the HEAD tree (100644/100755); None on error.

    Modes come from HEAD, the same commit ``show_head`` reads, so a path staged
    as a regular file but a symlink at HEAD is not trusted. Symlinks (120000)
    and gitlinks (160000) are dropped: ``git show`` returns the link target or
    commit text for them. No commits -> empty set.
    """
    if head(root) is None:
        return set()
    result = run_git(root, "ls-tree", "-r", "-z", "HEAD")
    if result.returncode != 0:
        return None
    out: set[str] = set()
    for entry in result.stdout.split("\0"):
        meta, _, path = entry.partition("\t")
        if path and meta.split(" ", 1)[0] in ("100644", "100755"):
            out.add(path)
    return out


def ls_tree_files(root: Path, rel: str) -> list[str] | None:
    """Regular files (100644/100755) under ``rel`` in the HEAD tree; None on error.

    Symlinks and gitlinks are dropped for the same reason as ``regular_tracked``.
    """
    if head(root) is None:
        return []
    result = run_git(root, "ls-tree", "-r", "-z", "HEAD", "--", rel)
    if result.returncode != 0:
        return None
    out: list[str] = []
    for entry in result.stdout.split("\0"):
        meta, _, path = entry.partition("\t")
        if path and meta.split(" ", 1)[0] in ("100644", "100755"):
            out.append(path)
    return sorted(out)


MAX_LOG_COMMITS = 2000


def log_names_since(root: Path, base: str) -> list[tuple[str, list[str]]] | None:
    """``(short hash, paths)`` per commit in ``base..HEAD``, newest first; None on error.

    One git call, capped at ``MAX_LOG_COMMITS`` commits.
    """
    result = run_git(
        root, "log", "--no-renames", "--name-only", f"-n{MAX_LOG_COMMITS + 1}",
        "--format=%x01%h", f"{base}..HEAD",
    )
    if result.returncode != 0:
        return None
    commits: list[tuple[str, list[str]]] = []
    for line in result.stdout.splitlines():
        if line.startswith("\x01"):
            commits.append((line[1:], []))
        elif line and commits:
            commits[-1][1].append(line)
    if len(commits) > MAX_LOG_COMMITS:
        return None  # truncated history would undercount touched files; callers say so
    return commits


def ignored(root: Path, rels: list[str] | tuple[str, ...]) -> list[str]:
    """Which untracked ``rels`` git would ignore; [] on error or timeout."""
    result = run_git(root, "check-ignore", "--", *rels)
    return _lines(result) if result.returncode == 0 else []


def ignored_or_none(root: Path, rels: list[str] | tuple[str, ...]) -> list[str] | None:
    """Which ``rels`` git would ignore; None on error or timeout (fail closed)."""
    result = run_git(root, "check-ignore", "--", *rels)
    return _lines(result) if result.returncode in (0, 1) else None


def status_paths(root: Path, rel: str) -> list[str] | None:
    """``"XY path"`` per changed or untracked file under ``rel``; None on error.

    ``-z`` keeps odd paths unquoted; each untracked file is listed (never just
    its directory) so the user sees the exact paths to be committed.
    """
    result = run_git(root, "status", "--porcelain", "-z", "--untracked-files=all", "--", rel)
    if result.returncode != 0:
        return None
    out: list[str] = []
    entries = iter(result.stdout.split("\0"))
    for entry in entries:
        if not entry:
            continue
        out.append(entry)
        if "R" in entry[:2] or "C" in entry[:2]:
            next(entries, None)  # rename/copy source path follows
    return out


def dirty_paths(root: Path) -> list[str] | None:
    """Paths ``git status`` lists (staged, unstaged, untracked); None on error."""
    result = run_git(root, "status", "--porcelain", "-z", "--untracked-files=all")
    if result.returncode != 0:
        return None
    out: list[str] = []
    entries = iter(result.stdout.split("\0"))
    for entry in entries:
        if not entry:
            continue
        out.append(entry[3:])
        if "R" in entry[:2] or "C" in entry[:2]:
            out.append(next(entries, ""))  # rename/copy source path follows
    return out


def is_clean(root: Path, ignore: tuple[str, ...] = ()) -> bool:
    """True when nothing but ``ignore`` paths shows in ``git status``."""
    paths = dirty_paths(root)
    return paths is not None and all(p in ignore for p in paths)


def on_branch(root: Path) -> bool:
    """False on a detached HEAD (or any error)."""
    return run_git(root, "symbolic-ref", "-q", "HEAD").returncode == 0


def show_head(root: Path, rel: str) -> str | None:
    """Content of ``rel`` at HEAD, so uncommitted edits never count."""
    result = run_git(root, "show", f"HEAD:{rel}")
    return result.stdout if result.returncode == 0 else None


def show_head_strict(root: Path, rel: str) -> str | None:
    """UTF-8 text of ``rel`` at HEAD with universal newlines, like ``Path.read_text``;
    None when the blob is missing or not valid UTF-8 (so HEAD and work-tree reads agree)."""
    try:
        result = subprocess.run(
            ["git", "-c", "core.quotePath=false", "show", f"HEAD:{rel}"],
            cwd=root, capture_output=True, check=False, timeout=TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    try:
        text = result.stdout.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return text.replace("\r\n", "\n").replace("\r", "\n")


_COMMIT_ID = __import__("re").compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
_HUNK = __import__("re").compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", __import__("re").M)


def diff_hunks(root: Path, base: str, rel: str) -> list[tuple[int, int, int, int]] | None:
    """``(old_start, old_count, new_start, new_count)`` per hunk of ``rel`` in ``base..HEAD``
    (zero context, no rename detection); None when git cannot produce the diff.

    ``base`` may come from a repo-controlled file (``covered`` in .wikify.json), so only a full
    commit id is accepted: anything else, such as ``--output=...``, would be read as an option."""
    if not _COMMIT_ID.fullmatch(base):
        return None
    result = run_git(root, "diff", "--no-renames", "--no-color", "-U0", f"{base}..HEAD", "--", rel)
    if result.returncode != 0:
        return None
    return [
        (int(a), int(b) if b else 1, int(c), int(d) if d else 1)
        for a, b, c, d in _HUNK.findall(result.stdout)
    ]


def last_commit_touching(root: Path, rel: str) -> str | None:
    result = run_git(root, "log", "-1", "--format=%H", "--", rel)
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def changed_since(root: Path, base: str) -> list[str] | None:
    """Paths changed in ``base..HEAD``; None on error."""
    result = run_git(root, "diff", "--name-only", "--no-renames", f"{base}..HEAD")
    return _lines(result) if result.returncode == 0 else None


def deleted_since(root: Path, base: str) -> list[str]:
    result = run_git(
        root, "diff", "--name-only", "--no-renames", "--diff-filter=D", f"{base}..HEAD"
    )
    return _lines(result) if result.returncode == 0 else []


def files_in_commit(root: Path, commit: str) -> list[str] | None:
    """Paths touched by ``commit`` itself (works for root commits)."""
    result = run_git(
        root, "show", "--name-only", "--no-renames", "--format=", commit
    )
    return _lines(result) if result.returncode == 0 else None


def git_dir(root: Path) -> Path | None:
    """Absolute path of the repo's git dir; None on error."""
    result = run_git(root, "rev-parse", "--absolute-git-dir")
    out = result.stdout.strip()
    return Path(out) if result.returncode == 0 and out else None
