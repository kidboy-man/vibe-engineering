"""Diff-driven refresh plan: which wiki pages the agent should update.

Ceiling: page mapping is by cited path only (see citations.index), and
``contexts`` is a heuristic, not a module graph.
"""

from __future__ import annotations

import ast
from pathlib import Path

from agents.secret_policies import is_secret_path
from agents.wikify import citations, gitview, state

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


def build_plan(root: Path, full: bool = False) -> dict:
    root = Path(root)
    head = gitview.head(root)
    plan: dict = {
        "mode": "full",
        "base": None,
        "head": head,
        "changed": [],
        "refresh_pages": [],
        "uncovered": [],
        "stale_deleted": [],
        "contexts": [],
        "symbols": {},
        "error": None,
    }
    if head is None:
        return plan
    ignore = citations.load_ignore(root)
    listing = gitview.tracked_files_or_none(root)
    if listing is None:
        plan["error"] = "git ls-files failed or timed out; plan is incomplete"
        return plan
    tracked = [p for p in listing if _keep(p, ignore)]
    plan["contexts"] = _contexts(tracked)
    base = None if full else state.base(root)
    changed = gitview.changed_since(root, base) if base else None
    pages = citations.index(root)
    if base and changed is None:
        plan["error"] = "git diff failed or timed out; fell back to full plan"
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
    for key in ("changed", "refresh_pages", "uncovered", "contexts"):
        lines.append(f"{key} ({len(plan[key])}):")
        lines.extend(f"  {item}" for item in plan[key])
    lines.append(f"stale_deleted ({len(plan['stale_deleted'])}):")
    lines.extend(
        f"  {item['page']}: {', '.join(item['missing'])}" for item in plan["stale_deleted"]
    )
    lines.append(f"symbols ({len(plan['symbols'])}):")
    lines.extend(f"  {path}: {', '.join(names)}" for path, names in plan["symbols"].items())
    return "\n".join(lines) + "\n"
