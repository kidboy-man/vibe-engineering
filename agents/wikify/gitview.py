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


def ignored(root: Path, rels: list[str] | tuple[str, ...]) -> list[str]:
    """Which untracked ``rels`` git would ignore; [] on error or timeout."""
    result = run_git(root, "check-ignore", "--", *rels)
    return _lines(result) if result.returncode == 0 else []


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


def show_head(root: Path, rel: str) -> str | None:
    """Content of ``rel`` at HEAD, so uncommitted edits never count."""
    result = run_git(root, "show", f"HEAD:{rel}")
    return result.stdout if result.returncode == 0 else None


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
