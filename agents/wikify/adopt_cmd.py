"""``vibe wikify adopt``: fold existing markdown docs into docs/wiki/.

The command is deterministic and never calls a model. Which doc goes where is
decided by the reviewable mapping file; anything without a rule is reported as
unmapped. Dry run is the default: only ``--apply`` writes.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from agents.wikify import adopt_plan as ap
from agents.wikify import adopt_refs, citations, gitview, state
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


def build_report(plan: ap.Plan, outgoing: list[tuple[str, int, str]]) -> dict:
    moves = [c for c in plan.candidates if not c.reason]
    skips = [c for c in plan.candidates if c.reason]
    unresolved: set[tuple[str, str, int]] = set()
    for c in moves:
        for r in c.refs:
            unresolved.add((c.source, r.file, r.line))
    for doc, line, target in outgoing:
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
            "outside_wiki": sorted(c.source for c in moves),
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
    if not (root / INDEX_REL).is_file():
        print(f"{INDEX_REL} is missing; run vibe wikify init first")
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
    plan = ap.plan_candidates(root, rules, include, exclude)
    if plan.error:
        print(f"refused: {_safe(plan.error)}\nnothing written")
        return 1
    moves = [c.source for c in plan.candidates if not c.reason]
    outgoing = adopt_refs.outgoing(root, moves)
    if report:
        print(json.dumps(build_report(plan, outgoing), indent=2, sort_keys=True))
        return 0
    _print_plan(plan)
    n_skip = sum(1 for c in plan.candidates if c.reason)
    print(f"{len(moves)} move(s), {n_skip} skipped")
    print("dry run: no files written; pass --apply to move the docs")
    return 0
