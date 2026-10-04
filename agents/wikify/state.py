"""Wiki freshness state stored in ``docs/wiki/.wikify.json``.

Freshness is derived from git, not from a stored SHA: the base is the commit
that last touched the state file, so rebases and squashes do not invalidate it.
"""

from __future__ import annotations

import json
from pathlib import Path

from agents.wikify import gitview

WIKI_DIR = "docs/wiki/"
STATE_REL = "docs/wiki/.wikify.json"


def _default() -> dict:
    return {"version": 1, "covered": None}


def load(root: Path) -> dict:
    """Read state; anything missing, invalid, or mistyped yields defaults."""
    try:
        data = json.loads((Path(root) / STATE_REL).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _default()
    if not isinstance(data, dict):
        return _default()
    covered = data.get("covered")
    if covered is not None and not isinstance(covered, str):
        covered = None
    return {"version": 1, "covered": covered}


class UnsafeWikiPath(Exception):
    """The wiki location is a symlink or escapes the repo; nothing is written."""


def check_wiki_path(root: Path) -> None:
    """Raise UnsafeWikiPath if docs, docs/wiki or the state file is a symlink
    or the wiki dir resolves outside the repo root."""
    root = Path(root)
    for rel in ("docs", "docs/wiki", STATE_REL):
        if (root / rel).is_symlink():
            raise UnsafeWikiPath(f"{rel} is a symlink")
    wiki = (root / WIKI_DIR).resolve()
    if not wiki.is_relative_to(root.resolve()):
        raise UnsafeWikiPath("docs/wiki resolves outside the repository")


def save(root: Path, head: str | None) -> None:
    """Rewrite the state file; ``covered`` always reflects ``head``."""
    check_wiki_path(root)
    path = Path(root) / STATE_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "covered": head}
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def base(root: Path) -> str | None:
    return gitview.last_commit_touching(root, STATE_REL)


def _docs_only(paths: list[str] | None) -> bool:
    return paths is not None and all(p.startswith(WIKI_DIR) for p in paths)


def is_fresh(root: Path) -> bool:
    """True when nothing outside docs/wiki/ changed since the state commit.

    The base commit itself must also be docs-only, otherwise a commit mixing
    code with the state file would hide uncovered code.
    """
    if gitview.head(root) is None:
        return True  # no commits: nothing to push or cover
    commit = base(root)
    if commit is None:
        return False  # state never committed
    return _docs_only(gitview.files_in_commit(root, commit)) and _docs_only(
        gitview.changed_since(root, commit)
    )
