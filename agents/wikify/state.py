"""Wiki freshness state stored in ``docs/wiki/.wikify.json``.

Freshness is derived from git, not from a stored SHA: the base is the commit
that last touched the state file, so rebasing, amending or cherry-picking
docs-only commits does not invalidate it.

Limitation: a squash merge folds code and the state file into one mixed
commit, which reads as stale (a mixed base must not hide uncovered code).
After a squash merge, run ``vibe wikify mark`` and commit docs-only once.
"""

from __future__ import annotations

import json
from pathlib import Path

from agents.wikify import gitview

WIKI_DIR = "docs/wiki/"
STATE_REL = "docs/wiki/.wikify.json"


CONTROL_RELS = tuple(
    WIKI_DIR + name
    for name in (".wikify.json", "WIKIFY.md", ".wikifyignore", ".wikify-allow", ".wikifydocs", ".wikifymap", "index.md")
)


def ignored_control_files(root: Path) -> list[str]:
    """One error per control file git would ignore (it would never be committed,
    so the state base would never advance and the hook would block forever)."""
    hits = gitview.ignored_or_none(root, CONTROL_RELS)
    if hits is None:
        return ["docs/wiki control files: could not determine whether git ignores them (git check-ignore failed)"]
    return [
        f"{rel}: ignored by git, so it would never be committed; un-ignore it "
        "(e.g. add `!docs/wiki/` then `!docs/wiki/**` at the end of .gitignore; "
        "if a parent directory such as `docs/` is ignored, narrow that rule instead)"
        for rel in hits
    ]


IMPORTED_MODES = ("editable", "frozen")


def _default() -> dict:
    return {
        "version": 1, "covered": None, "citations": {}, "imported": {}, "imported_mode": "editable",
    }


def _parse(text: str | None) -> dict:
    try:
        data = json.loads(text or "")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _readable(root: Path) -> bool:
    """True when the state file parses to a JSON object, so a rewrite cannot drop settings."""
    try:
        return isinstance(json.loads((Path(root) / STATE_REL).read_text(encoding="utf-8")), dict)
    except (OSError, ValueError):
        return False


def _read_raw(root: Path) -> dict:
    try:
        return _parse((Path(root) / STATE_REL).read_text(encoding="utf-8"))
    except OSError:
        return {}


def _str_map(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {k: v for k, v in value.items() if isinstance(k, str) and isinstance(v, str)}


def load(root: Path) -> dict:
    """Read state; anything missing, invalid, or mistyped yields defaults."""
    return _normalise(_read_raw(root))


def load_head(root: Path) -> dict:
    """Like ``load`` but from the committed state file, so a dirty tree never counts."""
    return _normalise(_parse(gitview.show_head(Path(root), STATE_REL)))


def _normalise(data: dict) -> dict:
    covered = data.get("covered")
    mode = data.get("imported_mode")
    return {
        "version": 1,
        "covered": covered if isinstance(covered, str) else None,
        "citations": _str_map(data.get("citations")),
        "imported": _str_map(data.get("imported")),
        "imported_mode": mode if mode in IMPORTED_MODES else "editable",
    }


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


def save(
    root: Path,
    head: str | None,
    citations: dict[str, str] | None = None,
    imported: dict[str, str] | None = None,
) -> None:
    """Rewrite the state file; ``covered`` always reflects ``head``.

    Keys this version does not own (and the citation/imported maps when the
    argument is ``None``) are kept as found, so a newer state file survives an
    older code path rewriting it.
    """
    check_wiki_path(root)
    path = Path(root) / STATE_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not _readable(root):
        raise UnsafeWikiPath(f"{STATE_REL} is not valid JSON (merge conflict?); fix it first")
    payload = _read_raw(root)
    payload.update(version=1, covered=head)
    if citations is not None:
        payload["citations"] = citations
    if imported is not None:
        payload["imported"] = imported
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def base(root: Path) -> str | None:
    return gitview.last_commit_touching(root, STATE_REL)


def _docs_only(paths: list[str] | None) -> bool:
    return paths is not None and all(p.startswith(WIKI_DIR) for p in paths)


def mixed_base(root: Path, commit: str) -> bool:
    """True when ``commit`` touched anything outside docs/wiki/ (or is unreadable)."""
    return not _docs_only(gitview.files_in_commit(root, commit))


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
