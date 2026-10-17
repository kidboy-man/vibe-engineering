"""``vibe wikify check`` and ``sync``: read-only drift reports.

Ceiling: deterministic and structural; no model, no network. ``check`` never
writes, and fails closed: any internal error is a failing verdict.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from agents.wikify import agentmap, drift, gitview, imported, imported_refs, state
from agents.wikify.pointer import _safe

FAILING = ("changed", "missing")


@dataclass
class CheckResult:
    ok: bool = True
    drift: list[drift.Finding] = field(default_factory=list)  # changed + missing
    moved: list[drift.Finding] = field(default_factory=list)
    uncovered_areas: list[dict] = field(default_factory=list)
    references: list[dict] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)
    unbaselined_changed: int = 0
    suggestions: list[str] = field(default_factory=list)
    error: str | None = None

    def counts(self) -> dict:
        return {
            "moved": len(self.moved),
            "changed": sum(f.category == "changed" for f in self.drift),
            "missing": sum(f.category == "missing" for f in self.drift),
            "uncovered_areas": len(self.uncovered_areas),
            "references": len(self.references),
            "unbaselined_changed": self.unbaselined_changed,
        }


def run_check(root: Path, ci: bool = False) -> CheckResult:
    """Classify every citation. ``ci`` judges pages and state at HEAD, not the work tree."""
    try:
        return _check(Path(root), ci)
    except Exception as exc:  # fail closed: this verdict gates pushes
        return CheckResult(ok=False, error=type(exc).__name__)


def _check(root: Path, ci: bool) -> CheckResult:
    result = CheckResult()
    if gitview.head(root) is None:
        result.notices.append("NOTICE: repository has no commits; nothing to check")
        return result
    pages = drift.read_pages(root, at_head=ci)
    st = drift.read_state(root, at_head=ci)
    tracked = gitview.regular_tracked(root)
    if tracked is None:
        raise RuntimeError("git ls-tree failed")
    base = state.base(root)
    touched = drift.touched_since(root, base) if base else None
    if base is None:
        result.notices.append(
            f"NOTICE: no baseline: {state.STATE_REL} was never committed; "
            "run vibe wikify mark and commit it"
        )
    elif touched is None:
        result.notices.append(
            "NOTICE: could not read git history; commits are not attributed (shallow clone?)"
        )
    ignore = drift.load_ignore(root, at_head=ci)
    done = drift.classify(root, pages, st, tracked, ignore, st["covered"])
    found = drift.attribute(done.findings, touched or {})
    result.drift = [f for f in found if f.category in FAILING]
    result.moved = [f for f in found if f.category == "moved"]
    if done.unhashed:
        result.notices.append(
            f"NOTICE: {len(done.unhashed)} citation(s) have no range hash yet; "
            "run vibe wikify mark to record them"
        )
        result.unbaselined_changed = (
            len(done.unhashed)
            if base is None or touched is None
            else sum(cite.path in touched for _, cite in done.unhashed)
        )
    result.references = imported_refs.find(root, pages, tracked, ignore)
    _map_hygiene(result, pages.get("index.md", ""))
    edited, _ = imported.edited_pages(pages, st)
    result.notices.extend(f"IMPORTED PAGE EDITED: {rel}" for rel in edited)
    changed = sorted(tracked) if base is None or touched is None else sorted(touched)
    result.uncovered_areas = drift.uncovered_areas(changed, pages, tracked, ignore)
    result.ok = not result.drift
    return result


def _map_hygiene(result: CheckResult, index_text: str) -> None:
    entries, size = agentmap.cap_usage(index_text)
    if max(entries, size) < agentmap.CAP_WARN_RATIO:
        return
    result.notices.append(
        f"NOTICE: the index.md map is at {entries:.0%} of its {agentmap.MAX_ENTRIES}-entry cap and "
        f"{size:.0%} of its {agentmap.MAX_BYTES}-byte cap; group pages under per-folder index.md pages"
    )
    result.suggestions = [
        f"group docs/wiki/{folder}/ ({n} entries) under {folder}/index.md"
        for folder, n in agentmap.group_suggestions(agentmap.parse_map(index_text))
    ]


def _where(f: drift.Finding) -> str:
    sym = f" `{f.symbol}`" if f.symbol else ""
    return _safe(f"{f.page}:{f.line}: {f.category}  {f.path}:{f.start}-{f.end}{sym}")


def _detail(f: drift.Finding) -> str:
    bits = [f.reason] if f.reason else []
    if f.commits:
        bits.append("commits " + ", ".join(f.commits))
    return f" ({'; '.join(bits)})" if bits else ""


def render_text(result: CheckResult) -> str:
    if result.error:
        return f"check failed: {result.error}\n"
    lines: list[str] = []
    if result.drift:
        lines.append(f"drift: {len({f.page for f in result.drift})} page(s)")
        lines += [f"  {_where(f)}{_safe(_detail(f))}" for f in result.drift]
    if result.moved:
        lines.append(f"moved (auto-healable: vibe wikify reanchor): {len(result.moved)}")
        lines += [
            _safe(f"  {f.page}:{f.line}: {f.path}:{f.start}-{f.end} -> {f.new_start}-{f.new_end}")
            for f in result.moved
        ]
    if result.uncovered_areas:
        lines.append("uncovered (warning):")
        lines += [
            _safe(f"  {a['area']}/ ({len(a['files'])} file(s))") for a in result.uncovered_areas
        ]
    if result.references:
        lines.append(f"references (name-only matching is a floor, not proof): {len(result.references)}")
        lines += imported_refs.render(result.references)
    lines += [_safe(n) for n in result.notices]
    lines.append("ok: no drift" if result.ok else f"drift found: {len(result.drift)} citation(s)")
    return "\n".join(lines) + "\n"


def render_ci(result: CheckResult) -> str:
    if result.error:
        return f"check failed: {result.error}\n"
    lines = [_safe(f"{f.category} {f.page}:{f.line} {f.path}:{f.start}-{f.end}{_detail(f)}")
             for f in result.drift + result.moved]
    lines += [_safe(f"uncovered {a['area']}/") for a in result.uncovered_areas]
    lines += [_safe(f"reference {r['kind']} {r['page']}:{r['line']} {r['token']}") for r in result.references]
    lines += [_safe(n) for n in result.notices]
    lines.append("ok" if result.ok else f"drift: {len(result.drift)}")
    return "\n".join(lines) + "\n"


def render_json(result: CheckResult) -> str:
    def item(f: drift.Finding) -> dict:
        data = asdict(f)
        data["commits"] = list(f.commits)
        return data

    payload = {
        "ok": result.ok,
        "counts": result.counts(),
        "drift": [item(f) for f in result.drift],
        "moved": [item(f) for f in result.moved],
        "uncovered_areas": result.uncovered_areas,
        "references": result.references,
        "suggestions": result.suggestions,
        "notices": result.notices,
        "error": result.error,
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def cmd_check(cwd: str | Path | None = None, ci: bool = False, as_json: bool = False) -> int:
    root = gitview.repo_root(cwd or os.getcwd())
    if root is None:
        print("not a git repository")
        return 1
    result = run_check(root, ci)
    render = render_json if as_json else render_ci if ci else render_text
    print(render(result), end="")
    return 0 if result.ok else 1


ACTIONS = {
    "moved": "run: vibe wikify reanchor --apply ({old} -> {new})",
    "changed": "read {path}:{old} and update the claim ({reason})",
    "missing": "cited code is gone ({reason}); ask the user before editing or removing the page",
}


def work_items(result: CheckResult) -> list[tuple[int, str, str, str]]:
    """(priority, label, where, action) per thing to do, ordered moved -> changed -> missing ->
    uncovered -> reference, then by page and line. Writes nothing."""
    items: list[tuple[int, int, str, str, str, str]] = []
    for f in result.moved + result.drift:
        old = f"{f.start}-{f.end}"
        action = ACTIONS[f.category].format(
            old=old, new=f"{f.new_start}-{f.new_end}", path=f.path, reason=f.reason or f.category
        )
        items.append((FAILING_RANK[f.category], f.line, f.category, f"{f.page}:{f.line}", action, f.page))
    for area in result.uncovered_areas:
        items.append((4, 0, "uncovered", f"{area['area']}/",
                      "changed code that no page cites; add a page only if it needs one", area["area"]))
    for ref in result.references:
        items.append((5, ref.get("line", 0), "reference", f"{ref['page']}:{ref.get('line', 0)}",
                      f"{ref['kind']} {ref['token']}: fix or report it in the imported doc", ref["page"]))
    items.sort(key=lambda i: (i[0], i[5], i[1]))
    return [(i[0], i[2], i[3], i[4]) for i in items]


FAILING_RANK = {"moved": 1, "changed": 2, "missing": 3}


def render_sync(result: CheckResult) -> str:
    if result.error:
        return f"sync failed: {result.error}\n"
    items = work_items(result)
    lines = [f"work list ({len(items)}):"]
    for n, (_, label, where, action) in enumerate(items, 1):
        lines.append(_safe(f"  {n}. {label:<9} {where}  {action}"))
    lines += [_safe(n) for n in result.notices]
    if result.suggestions:
        lines.append("suggestions:")
        lines += [_safe(f"  {text}") for text in result.suggestions]
    return "\n".join(lines) + "\n"


def cmd_sync(cwd: str | Path | None = None) -> int:
    root = gitview.repo_root(cwd or os.getcwd())
    if root is None:
        print("not a git repository")
        return 1
    result = run_check(root)
    print(render_sync(result), end="")
    return 0 if result.ok else 1
