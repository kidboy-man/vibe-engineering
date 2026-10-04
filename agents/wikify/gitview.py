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


def tracked_files(root: Path) -> list[str]:
    """Paths in the index (``git ls-files``); empty on error."""
    result = run_git(root, "ls-files")
    return _lines(result) if result.returncode == 0 else []


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
