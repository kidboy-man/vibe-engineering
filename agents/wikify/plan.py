"""Diff-driven refresh plan: which wiki pages the agent should update.

Ceiling: page mapping is by cited path only (see citations.index), and
``contexts`` is a heuristic, not a module graph.
"""

from __future__ import annotations

import ast
from pathlib import Path

from agents.secret_policies import is_secret_path
from agents.wikify import agentmap, citations, docs_inventory, gitview, state
from agents.wikify.pointer import _safe

MAX_SKIPPED_SHOWN = 50
# ponytail: repos using these roots get the sub-directory as the context.
CONTEXT_ROOTS = ("src", "app", "agents", "cmd", "internal", "pkg", "lib")


def _keep(path: str, ignore: list[str]) -> bool:
    return (
        not path.startswith(state.WIKI_DIR)
        and not is_secret_path(path)
        and not citations.is_ignored(path, ignore)
    )


def _contexts(paths: list[str]) -> list[str]:
    out: set[str] = set()
    for path in paths:
        parts = path.split("/")
        if len(parts) < 2:
            continue
        depth = 2 if parts[0] in CONTEXT_ROOTS and len(parts) > 2 else 1
        out.add("/".join(parts[:depth]))
    return sorted(out)


def _names(source: str) -> list[str]:
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        return []
    out: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append(node.name)
        elif isinstance(node, ast.ClassDef):
            out.append(node.name)
            for stmt in node.body:
                if isinstance(stmt, ast.Assign):
                    targets = stmt.targets
                elif isinstance(stmt, ast.AnnAssign):
                    targets = [stmt.target]
                else:
                    targets = []
                out.extend(
                    f"{node.name}.{t.id}" for t in targets if isinstance(t, ast.Name)
                )
    return out


def _symbols(root: Path, paths: list[str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for path in paths:
        if not path.endswith(".py"):
            continue
        source = gitview.show_head(root, path)
        names = _names(source) if source is not None else []
        if names:
            out[path] = names
    return out


def _page_texts(root: Path) -> tuple[list[str], list[str], dict[str, str]]:
    layout_errors, walked = citations.walk_wiki(root)
    texts: dict[str, str] = {}
    for rel, path in walked:
        try:
            texts[rel] = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            pass
    return layout_errors, [rel for rel, _ in walked], texts


def _map_missing(rels: list[str], texts: dict[str, str]) -> list[str]:
    """Pages (excluding top-level index.md) not reachable from the index.md agent map."""
    listed = {e.path for e in agentmap.parse_map(texts.get("index.md", "")).entries}
    reachable = agentmap.reachable_pages(listed, texts)
    return sorted(rel for rel in rels if rel != "index.md" and rel not in reachable)


def _docs_status(
    root: Path, head: str | None, layout_errors: list[str], texts: dict[str, str]
) -> tuple[dict, str | None]:
    """(status, error). No inventory when the wiki layout is already broken."""
    empty = {"unindexed": [], "stale": [], "skipped": []}
    if head is None or not (root / state.WIKI_DIR).is_dir():
        return empty, None
    if any(e.startswith(("docs:", "docs/wiki:")) for e in layout_errors):
        return empty, None
    try:
        return docs_inventory.status(root, texts), None
    except Exception as exc:  # plan is advisory, but never reports "all fresh" falsely
        return empty, f"doc inventory failed ({type(exc).__name__}); docs_* keys are incomplete"


def _join(prev: str | None, msg: str) -> str:
    return f"{prev}; {msg}" if prev else msg


def build_plan(root: Path, full: bool = False) -> dict:
    root = Path(root)
    head = gitview.head(root)
    layout_errors, rels, texts = _page_texts(root)
    docs, docs_error = _docs_status(root, head, layout_errors, texts)
    plan: dict = {
        "mode": "full",
        "base": None,
        "head": head,
        "changed": [],
        "refresh_pages": [],
        "uncovered": [],
        "map_missing": _map_missing(rels, texts),
        "docs_unindexed": docs["unindexed"],
        "docs_stale": docs["stale"],
        "docs_skipped": docs["skipped"],
        "stale_deleted": [],
        "contexts": [],
        "symbols": {},
        "error": None,
    }
    if citations.ignore_status(root) == "rejected":
        plan["error"] = f"{citations.IGNORE_REL} rejected; ignore rules were NOT applied"
    if docs_error:
        plan["error"] = _join(plan["error"], docs_error)
    if head is None:
        return plan
    ignore = citations.load_ignore(root)
    listing = gitview.tracked_files_or_none(root)
    if listing is None:
        plan["error"] = _join(plan["error"], "git ls-files failed or timed out; plan is incomplete")
        return plan
    tracked = [p for p in listing if _keep(p, ignore)]
    plan["contexts"] = _contexts(tracked)
    base = None if full else state.base(root)
    changed = gitview.changed_since(root, base) if base else None
    pages = citations.index(root)
    if base and changed is None:
        plan["error"] = _join(plan["error"], "git diff failed or timed out; fell back to full plan")
    if changed is None:  # full requested, no state, or unusable base
        plan["changed"] = sorted(tracked)
        plan["refresh_pages"] = sorted(pages)
    else:
        deleted = [p for p in gitview.deleted_since(root, base) if _keep(p, ignore)]
        alive = set(tracked)
        plan["mode"] = "incremental"
        plan["base"] = base
        plan["changed"] = sorted(p for p in changed if p in alive)
        touched = set(plan["changed"]) | set(deleted)
        plan["refresh_pages"] = sorted(pg for pg, cited in pages.items() if cited & touched)
        plan["stale_deleted"] = [
            {"page": pg, "missing": sorted(cited & set(deleted))}
            for pg, cited in sorted(pages.items())
            if cited & set(deleted)
        ]
    cited_all = set().union(*pages.values()) if pages else set()
    plan["uncovered"] = [p for p in plan["changed"] if p not in cited_all]
    plan["symbols"] = _symbols(root, plan["changed"])
    return plan


def render(plan: dict) -> str:
    lines = [f"ERROR: {plan['error']}"] if plan.get("error") else []
    lines += [
        f"mode: {plan['mode']}",
        f"base: {plan['base'] or '-'}",
        f"head: {plan['head'] or '-'}",
    ]
    keys = ("changed", "refresh_pages", "uncovered", "map_missing", "docs_unindexed", "docs_stale")
    for key in keys + ("docs_skipped", "contexts"):
        lines.append(f"{key} ({len(plan[key])}):")
        if key == "docs_skipped":  # paths are untrusted text; JSON carries them all
            shown = plan[key][:MAX_SKIPPED_SHOWN]
            lines.extend(f"  {_safe(i['path'])}: {_safe(i['reason'])}" for i in shown)
            if len(plan[key]) > len(shown):
                lines.append(f"  ... and {len(plan[key]) - len(shown)} more")
        else:
            lines.extend(f"  {_safe(item)}" for item in plan[key])
    lines.append(f"stale_deleted ({len(plan['stale_deleted'])}):")
    lines.extend(
        f"  {item['page']}: {', '.join(item['missing'])}" for item in plan["stale_deleted"]
    )
    lines.append(f"symbols ({len(plan['symbols'])}):")
    lines.extend(f"  {path}: {', '.join(names)}" for path, names in plan["symbols"].items())
    return "\n".join(lines) + "\n"
