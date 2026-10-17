"""``vibe wikify adopt``: fold existing markdown docs into docs/wiki/.

The command is deterministic and never calls a model. Which doc goes where is
decided by the reviewable mapping file; anything without a rule is reported as
unmapped. Dry run is the default: only ``--apply`` writes.
"""

from __future__ import annotations

import json
import os
import posixpath
import stat
from pathlib import Path

from agents.wikify import adopt_plan as ap
from agents.wikify import adopt_map, adopt_refs, docs_cmd, gitview, state
from agents.wikify import docs_inventory as di
from agents.wikify.pointer import _safe
from agents.wikify.state import WIKI_DIR

INDEX_REL = WIKI_DIR + "index.md"
MAX_REFS_SHOWN = 5


def _root(cwd: str | Path | None) -> Path | None:
    root = gitview.repo_root(cwd or os.getcwd())
    if root is None:
        print("not a git repository")
    return root


def _contexts(unmapped: list[str]) -> list[str]:
    return sorted({"/".join(p.split("/")[:2]) for p in unmapped if "/" in p})


def _rewritable(ref: adopt_refs.Ref, moved: set[str]) -> bool:
    """Incoming link refs that ``--rewrite-refs`` fixes: links in markdown files under docs/."""
    return (
        ref.kind == "link" and ref.file.startswith("docs/") and not ref.file.startswith(WIKI_DIR)
        and ref.file.lower().endswith(".md") and ref.file not in moved
    )


def build_report(
    plan: ap.Plan, outgoing: list[tuple[str, int, str]], rewrite: bool = False
) -> dict:
    moves = [c for c in plan.candidates if not c.reason]
    skips = [c for c in plan.candidates if c.reason]
    unresolved: set[tuple[str, str, int]] = set()
    sources = {c.source for c in moves}
    edited = sorted({r.file for c in moves for r in c.refs if rewrite and _rewritable(r, sources)})
    for c in moves:
        for r in c.refs:
            if not (rewrite and _rewritable(r, sources)):
                unresolved.add((c.source, r.file, r.line))
    for doc, line, target in outgoing:
        if not rewrite:
            unresolved.add((target, doc, line))
    unmapped = sorted(c.source for c in skips if c.reason == "unmapped")
    return {
        "moves": [
            {"source": c.source, "destination": WIKI_DIR + c.destination, "kind": c.kind,
             "body_sha256": c.sha256}
            for c in moves
        ],
        "skips": [{"source": c.source, "reason": c.reason} for c in skips],
        "unresolved_refs": [
            {"target": t, "file": f, "line": n} for t, f, n in sorted(unresolved)
        ],
        "unclassified": unmapped,
        "suggested_contexts": _contexts(unmapped),
        "commit_plan": {
            "outside_wiki": sorted([c.source for c in moves] + edited),
            "wiki_only": sorted([WIKI_DIR + c.destination for c in moves] + ([INDEX_REL] if moves else [])),
        },
    }


def _print_plan(plan: ap.Plan) -> None:
    for c in plan.candidates:
        if c.reason:
            print(f"skip {_safe(c.source)}: {c.reason}")
        else:
            print(f"move {_safe(c.source)} -> {WIKI_DIR}{_safe(c.destination)} [{c.kind}]")
        for r in c.refs[:MAX_REFS_SHOWN]:
            print(f"  ref {_safe(r.file)}:{r.line} ({r.kind})")
        if len(c.refs) > MAX_REFS_SHOWN:
            print(f"  ... and {len(c.refs) - MAX_REFS_SHOWN} more refs")


def cmd_adopt(
    cwd: str | Path | None = None,
    *,
    map_file: str | None = None,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
    apply: bool = False,
    report: bool = False,
    rewrite_refs: bool = False,
    prune_sources: bool = False,
    force: bool = False,
) -> int:
    root = _root(cwd)
    if root is None:
        return 1
    try:
        index_mode = os.lstat(root / INDEX_REL).st_mode
    except FileNotFoundError:
        print(f"{INDEX_REL} is missing; run vibe wikify init first")
        return 1
    except OSError as exc:
        print(f"refused: cannot inspect {INDEX_REL}: {type(exc).__name__}\nnothing written")
        return 1
    if not stat.S_ISREG(index_mode):
        print(f"refused: {INDEX_REL} is a symlink or not a regular file\nnothing written")
        return 1
    try:
        state.check_wiki_path(root)
    except state.UnsafeWikiPath as exc:
        print(f"refused: {exc}\nnothing written")
        return 1
    rules, errors = ap.load_rules(root, Path(map_file) if map_file else None)
    if errors:
        print("\n".join(f"refused: {_safe(e)}" for e in errors) + "\nnothing written")
        return 1
    if apply and not force:
        why = _unsafe_tree(root)
        if why:
            print(f"refused: {why}; commit or stash first, or pass --force\nnothing written")
            return 1
    plan = ap.plan_candidates(root, rules, include, exclude)
    if plan.error:
        print(f"refused: {_safe(plan.error)}\nnothing written")
        return 1
    moves = [c.source for c in plan.candidates if not c.reason]
    outgoing = adopt_refs.outgoing(root, moves)
    if report:
        print(json.dumps(build_report(plan, outgoing, rewrite_refs), indent=2, sort_keys=True))
        return 0
    _print_plan(plan)
    n_skip = sum(1 for c in plan.candidates if c.reason)
    print(f"{len(moves)} move(s), {n_skip} skipped")
    if apply:
        return _apply(root, plan, prune_sources, rewrite_refs)
    print("dry run: no files written; pass --apply to move the docs")
    return 0


def _unsafe_tree(root: Path) -> str | None:
    if not gitview.on_branch(root):
        return "detached HEAD"
    if not gitview.is_clean(root):
        return "uncommitted changes"
    return None


def _write_atomic(path: Path, text: str, exclusive: bool = False) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(tmp, flags, 0o666)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(text.encode("utf-8"))
        if exclusive and path.exists():
            raise FileExistsError(path.name)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _dirs_safe(root: Path, rel: str) -> bool:
    """Every existing directory on the way to ``docs/wiki/<rel>`` is a plain directory."""
    here = root
    for part in (WIKI_DIR + rel).split("/")[:-1]:
        here = here / part
        try:
            mode = os.lstat(here).st_mode
        except FileNotFoundError:
            return True
        except OSError:
            return False
        if not stat.S_ISDIR(mode):
            return False
    return True


def _read_wiki_text(root: Path, rel: str) -> str | None:
    """UTF-8 text of ``docs/wiki/<rel>``; None unless it is a regular file reached through plain directories."""
    if not _dirs_safe(root, rel):
        return None
    data = ap._read_body(root, WIKI_DIR + rel)
    try:
        return None if data is None else data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _remove_wiki_file(root: Path, rel: str) -> bool:
    """Unlink ``docs/wiki/<rel>`` only when no path component is a symlink and it is a regular file."""
    path = root / WIKI_DIR / rel
    if not _dirs_safe(root, rel):
        return False
    try:
        if not stat.S_ISREG(os.lstat(path).st_mode):
            return False
        path.unlink()
    except OSError:
        return False
    return True


def _sources_ok(root: Path) -> bool:
    try:
        mode = os.lstat(root / WIKI_DIR / "sources").st_mode
    except FileNotFoundError:
        return True
    except OSError:
        return False
    return stat.S_ISDIR(mode)


def _body(root: Path, c: ap.Candidate) -> str | None:
    data = ap._read_body(root, WIKI_DIR + c.destination if c.moved else c.source)
    if data is None:
        return None
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    wrapped = ap.unwrap(text)
    return wrapped[1] if wrapped else text


def _outline_cleanup(root: Path, moves: list[ap.Candidate], prune: bool) -> tuple[list[str], list[str]]:
    """(removed, stale) wiki-relative generated outline pages. Removes only what ``prune``/moves allow."""
    removed: list[str] = []
    gone = {di.page_rel(c.source) for c in moves}
    for rel in sorted(gone):
        if _is_generated_file(root, rel) and _remove_wiki_file(root, rel):
            removed.append(rel)
    index = di.INDEX_PAGE
    if removed and _is_generated_file(root, index):
        links = {"](" + rel[len("sources/"):] + ")" for rel in removed}
        text = _read_wiki_text(root, index) or ""
        keep = [ln for ln in text.split("\n") if not any(l in ln for l in links)]
        if any(ln.startswith("- [") for ln in keep):
            _write_atomic(root / WIKI_DIR / index, "\n".join(keep))
        elif _remove_wiki_file(root, index):
            removed.append(index)
    pages, _ = di.expected_pages(root)
    expected = {WIKI_DIR + rel for rel in pages if rel not in gone}
    if not any(rel != di.INDEX_PAGE for rel in pages if rel not in gone):
        expected.discard(WIKI_DIR + di.INDEX_PAGE)
    stale = [rel[len(WIKI_DIR):] for rel in docs_cmd._stale(root, expected)]
    if prune:
        removed += [rel for rel in stale if _remove_wiki_file(root, rel)]
    _prune_empty(root / WIKI_DIR / "sources")
    return removed, [] if prune else stale


def _is_generated_file(root: Path, rel: str) -> bool:
    text = _read_wiki_text(root, rel)
    return text is not None and text.split("\n", 1)[0].rstrip("\r") == di.MARKER


def _prune_empty(top: Path) -> None:
    if top.is_symlink() or not top.is_dir():
        return
    for dirpath, _, _ in os.walk(top, topdown=False):
        if Path(dirpath) != top:
            try:
                os.rmdir(dirpath)
            except OSError:
                pass


def _rewrite_incoming(root: Path, moves: list[ap.Candidate], new_paths: dict[str, str]) -> list[str]:
    """Fix relative links in docs-only markdown files that point at moved docs; stages each edit."""
    sources = set(new_paths)
    files = sorted({r.file for c in moves for r in c.refs if _rewritable(r, sources)})
    done: list[str] = []
    for rel in files:
        path = root / rel
        data = ap._read_body(root, rel)
        if data is None:
            continue
        base = posixpath.dirname(rel)
        text, n = adopt_refs.rewrite_links(data.decode("utf-8"), base, base, new_paths)
        if n:
            _write_atomic(path, text)
            gitview.run_git(root, "add", "--", rel)
            done.append(rel)
    return done


def _apply(root: Path, plan: ap.Plan, prune_sources: bool, rewrite: bool = False) -> int:
    moves = [c for c in plan.candidates if not c.reason]
    if not moves:
        print("nothing to move")
        return 0
    pages: list[adopt_map.Page] = []
    for c in moves:
        body = _body(root, c)
        if body is None or not _dirs_safe(root, c.destination):
            print(f"refused: cannot read or place {_safe(c.source)}\nnothing written")
            return 1
        pages.append(adopt_map.Page(c.destination, c.source, body))
    index_path = root / INDEX_REL
    index_before = _read_wiki_text(root, "index.md")
    if index_before is None or not _sources_ok(root):
        print("refused: index.md or sources/ is a symlink or not plain; nothing written")
        return 1
    planned = adopt_map.plan_map(index_before, pages)
    if isinstance(planned, str):
        print(f"refused: {_safe(planned)}\nnothing written")
        return 1
    index_text, extra = planned
    if any((root / WIKI_DIR / rel).exists() or not _dirs_safe(root, rel) for rel in extra):
        print("refused: a folder index page already exists; nothing written")
        return 1
    new_paths = {c.source: WIKI_DIR + c.destination for c in moves}
    for c in sorted(moves, key=lambda c: c.source):
        dest = root / WIKI_DIR / c.destination
        if not c.moved:
            dest.parent.mkdir(parents=True, exist_ok=True)
            result = gitview.run_git(root, "mv", "--", c.source, WIKI_DIR + c.destination)
            if result.returncode != 0:
                print(
                    f"git mv failed for {_safe(c.source)}; earlier moves are staged. Fix the cause "
                    "and re-run with --force to resume, or `git reset --hard` to start over"
                )
                return 1
        data = ap._read_body(root, WIKI_DIR + c.destination)
        text = data.decode("utf-8") if data is not None else ""
        if ap.is_wrapped(text):
            continue
        if data is None or ap.sha256(data) != c.sha256:
            print(f"refused: {_safe(c.destination)} does not match the planned content; stopping")
            return 1
        if rewrite:
            text, _ = adopt_refs.rewrite_links(
                text, posixpath.dirname(c.source), posixpath.dirname(WIKI_DIR + c.destination), new_paths
            )
        _write_atomic(dest, ap.wrap(c.source, text))
    for rel, text in sorted(extra.items()):
        (root / WIKI_DIR / rel).parent.mkdir(parents=True, exist_ok=True)
        _write_atomic(root / WIKI_DIR / rel, text, exclusive=True)
    if index_text != index_before:
        _write_atomic(index_path, index_text)
    edited = _rewrite_incoming(root, moves, new_paths) if rewrite else []
    for rel in edited:
        print(f"rewrote links in {_safe(rel)} (staged)")
    removed, stale = _outline_cleanup(root, moves, prune_sources)
    current = _read_wiki_text(root, "index.md")
    pruned = adopt_map.drop_entries(current, set(removed)) if current is not None else None
    if pruned is not None and pruned != current:
        _write_atomic(index_path, pruned)
    for rel in removed:
        print(f"removed {WIKI_DIR}{_safe(rel)}")
    for rel in stale:
        print(f"stale {WIKI_DIR}{_safe(rel)} (use --prune-sources to remove)")
    print(f"moved {len(moves)} doc(s). Next, in order:")
    print('  1. git commit -m "docs(wiki): move docs into the wiki"   # staged renames only')
    print("  2. vibe wikify verify && vibe wikify mark")
    print('  3. git add -- docs/wiki && git commit -m "docs(wiki): adopt moved docs"   # docs-only')
    return 0
