"""``vibe wikify`` subcommands, all operating on the git repo containing cwd."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from agents.wikify import agentmap, citations, docs_cmd, docs_inventory, gitview, init_cmd, plan, pointer, scan, state


def _human_blocks(text: str) -> list[tuple[int, str]]:
    blocks: list[tuple[int, str]] = []
    line, last = 1, 0
    for start, end in citations.human_spans(text):  # spans are in order
        line += text.count("\n", last, start)
        last = start
        blocks.append((line, text[start:end]))
    return blocks


def _notices(root: Path, rel: str, text: str) -> list[str]:
    old = gitview.show_head(root, state.WIKI_DIR + rel)
    known = {b for _, b in _human_blocks(old)} if old is not None else set()
    now = {b for _, b in _human_blocks(text)}
    return [
        f"HUMAN BLOCK CHANGED: {rel}:{line}"
        for line, block in _human_blocks(text)
        if block not in known
    ] + [f"HUMAN BLOCK REMOVED: {rel}" for _ in sorted(known - now)]


def _allow_notices(root: Path) -> list[str]:
    try:
        now = scan.parse_allow(
            (root / scan.ALLOW_REL).read_text(encoding="utf-8", errors="replace")
        )
    except OSError:
        now = set()
    old = gitview.show_head(root, scan.ALLOW_REL)
    before = scan.parse_allow(old) if old is not None else set()
    return [f"ALLOW-LIST CHANGED: {p}|{t}" for p, t in sorted(now - before)]


def _verify(root: Path) -> tuple[int, list[str]]:
    ignore = citations.load_ignore(root)
    errors, pages = citations.walk_wiki(root)
    if citations.ignore_status(root) == "rejected":
        errors.append(
            f"{citations.IGNORE_REL}: rejected (symlink, not a regular file, not valid "
            "UTF-8, or over 64 KiB); ignore rules were NOT applied"
        )
    errors += state.ignored_control_files(root)
    notices: list[str] = []
    allowed: list[str] = []
    if not any(e.startswith(("docs:", "docs/wiki:")) for e in errors):
        block = agentmap.MapBlock([], [], 0)
        texts: dict[str, str] = {}
        tracked = set(gitview.tracked_files(root))  # once, not per page
        expected: dict[str, str] = {}
        eligible: set[str] = set()
        if (root / state.WIKI_DIR).is_dir():  # no wiki, no doc pages to compare
            expected, inv = docs_inventory.expected_pages(root)  # once per run
            eligible = set(inv.docs)
        for rel, path in pages:
            text = path.read_text(encoding="utf-8")
            texts[rel] = text
            checked = text
            if rel == "index.md":  # only the top-level index carries the map
                block = agentmap.parse_map(text)
                checked = agentmap.strip_map(text)  # map lines are navigation
            elif docs_inventory.is_generated(text):
                checked = docs_inventory.blank_marker(text)  # keep line numbers
                if text != expected.get(rel):
                    reason = (
                        "generated page out of date; run vibe wikify docs"
                        if rel in expected
                        else "generated page has no eligible source"
                    )
                    errors.append(f"{rel}: {reason}")
            errors.extend(citations.verify_page(root, rel, checked, ignore, tracked))
            if not rel.startswith("sources/") and eligible:
                errors.extend(
                    f"{rel}:{c.line}: doc citation outside sources/: {c.path}"
                    for c in citations.parse(checked)[0]
                    if c.path in eligible
                )
            notices.extend(_notices(root, rel, text))
        errors.extend(block.errors)
        reachable = agentmap.reachable_pages({e.path for e in block.entries}, texts)
        errors.extend(agentmap.validate_map(block, set(texts), reachable))
        others = sum(1 for rel, _ in pages if rel != "index.md")
        if block.blocks == 0 and others:
            notices.append(
                f"NOTICE: {state.WIKI_DIR}index.md has no wikify:map block; "
                f"{others} page(s) are not reachable from a map"
            )
        errors.extend(scan.scan_wiki(root))
        notices.extend(_allow_notices(root))
        allowed = scan.allowed_hits(root)
    notices.extend(pointer.pointer_notices(root))
    notices.extend(pointer.size_notices(root))
    lines = errors + notices
    if allowed:
        lines += ["ALLOW-LISTED:", *(f"  {a}" for a in allowed)]
    lines.append(scan.FLOOR_NOTICE)
    if not errors:
        lines.append("ok: wiki verified")
    return (1 if errors else 0), lines


def run_verify(root: Path) -> tuple[int, list[str]]:
    """Verify the wiki; any exception is a failure, never a clean result."""
    try:
        return _verify(Path(root))
    except Exception as exc:  # fail closed: this gate guards publishing
        return 1, [f"verify failed: {type(exc).__name__}"]


def _root(cwd: str | Path | None) -> Path | None:
    root = gitview.repo_root(cwd or os.getcwd())
    if root is None:
        print("not a git repository")
    return root


def cmd_verify(cwd: str | Path | None = None) -> int:
    root = _root(cwd)
    if root is None:
        return 1
    rc, lines = run_verify(root)
    print("\n".join(lines))
    return rc


def cmd_mark(cwd: str | Path | None = None) -> int:
    root = _root(cwd)
    if root is None:
        return 1
    rc, lines = run_verify(root)
    print("\n".join(lines))
    if rc:
        print("not marked: fix the errors above and rerun")
        return 1
    head = gitview.head(root)
    try:
        state.save(root, head)
    except (state.UnsafeWikiPath, OSError) as exc:
        print(f"not marked: {exc if isinstance(exc, state.UnsafeWikiPath) else type(exc).__name__}")
        return 1
    print(f"marked at {head[:7] if head else 'no commits'}")
    files = gitview.status_paths(root, "docs/wiki")
    print("Files to commit:")
    if files is None:
        print("  (git status failed; run `git status --short -- docs/wiki`)")
    elif not files:
        print("  (none)")
    for f in files or []:
        print(f"  {f}")
    print(
        "Next: show the user the verify output above, the file list "
        "(`git status --short -- docs/wiki`) and the content "
        "(`git add -N -- docs/wiki && git diff -- docs/wiki`; -N makes new pages "
        "appear in the diff). Only after the user confirms, run "
        "`git add -- docs/wiki` and commit with a `docs(wiki): ...` message."
    )
    return 0


def cmd_plan(
    cwd: str | Path | None = None, full: bool = False, as_json: bool = False
) -> int:
    root = _root(cwd)
    if root is None:
        return 1
    result = plan.build_plan(root, full)
    print(json.dumps(result, indent=2, sort_keys=True) if as_json else plan.render(result))
    return 1 if result.get("error") else 0


def cmd_wikify(args: argparse.Namespace, cwd: str | Path | None = None) -> int:
    sub = args.wikify_command
    if sub == "init":
        return init_cmd.cmd_init(cwd)
    if sub == "plan":
        return cmd_plan(cwd, args.full, args.json)
    if sub == "verify":
        return cmd_verify(cwd)
    if sub == "mark":
        return cmd_mark(cwd)
    if sub == "link":
        return pointer.cmd_link(cwd, args.dry_run)
    if sub == "docs":
        return docs_cmd.cmd_docs(cwd, args.dry_run)
    print(f"unknown wikify command: {sub}")
    return 2
