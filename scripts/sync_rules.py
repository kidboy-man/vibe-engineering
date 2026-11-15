#!/usr/bin/env python3
"""Regenerate the opencode and cursor rule copies from the claude-code rules.

The claude-code rules are canonical. Run `python3 scripts/sync_rules.py` after editing one,
or add --check to fail when a copy is stale. Dev tool only: it lives outside `agents/`, so
it is not packaged into the wheel.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

CLAUDE_RULES = Path("agents/kits/claude_code/templates/claude/rules")
OPENCODE_RULES = Path("agents/kits/opencode/templates/opencode/rules")
CURSOR_RULES = Path("agents/kits/cursor/templates/cursor/rules")

RULES = (
    "database-and-operations",
    "go-backend-engineering",
    "operating-model",
    "security-and-data-safety",
    "testing-and-verification",
    "uncertainty-and-sources",
)

# name -> (description, globs, alwaysApply): frontmatter Cursor uses to decide when to load a rule.
CURSOR_FRONTMATTER: dict[str, tuple[str, tuple[str, ...], bool]] = {
    "database-and-operations": (
        "Database and operations standards — migrations, queries, transactions, observability",
        ("**/*.sql", "**/migrations/**", "**/db/**", "**/database/**", "**/repository/**"),
        False,
    ),
    "go-backend-engineering": (
        "Go backend engineering standards — architecture, error handling, concurrency, API design",
        ("**/*.go", "**/go.mod", "**/go.sum"),
        False,
    ),
    "operating-model": (
        "Engineering operating model — workflow, risk classification, scope discipline",
        ("**/*",),
        True,
    ),
    "security-and-data-safety": (
        "Security and data safety standards — authz, secrets, injection, tenant isolation",
        ("**/*",),
        True,
    ),
    "testing-and-verification": (
        "Testing and verification standards — TDD, test quality, verification strategy",
        ("**/*_test.go", "**/test_*.py", "**/*.test.ts", "**/*.spec.ts"),
        False,
    ),
    "uncertainty-and-sources": (
        "Uncertainty and sources — epistemic honesty, citation standards, fact-checking",
        ("**/*",),
        True,
    ),
}


def _read(path: Path) -> str:
    with path.open("r", encoding="utf-8", newline="\n") as fh:
        return fh.read()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def _render_mdc(name: str, body: str) -> str:
    description, globs, always_apply = CURSOR_FRONTMATTER[name]
    globs_text = "[" + ", ".join(f'"{glob}"' for glob in globs) + "]"
    return (
        f"---\ndescription: {description}\nglobs: {globs_text}\n"
        f"alwaysApply: {str(always_apply).lower()}\n---\n\n{body}"
    )


def expected_outputs(root: Path) -> dict[Path, str]:
    """Map every generated destination to the exact content it must have."""
    outputs: dict[Path, str] = {}
    for name in RULES:
        body = _read(root / CLAUDE_RULES / f"{name}.md")
        outputs[root / OPENCODE_RULES / f"{name}.md"] = body
        outputs[root / CURSOR_RULES / f"{name}.mdc"] = _render_mdc(name, body)
    return outputs


def sync(root: Path, write: bool) -> list[Path]:
    """Return destinations that differ from the canonical text; rewrite them when *write*."""
    outputs = expected_outputs(root)
    stale = [path for path, text in outputs.items() if not path.is_file() or _read(path) != text]
    if write:
        for path in stale:
            _write(path, outputs[path])
    return stale


def main(argv: list[str] | None = None, root: Path = REPO_ROOT) -> int:
    parser = argparse.ArgumentParser(description="Sync opencode and cursor rule copies from claude-code.")
    parser.add_argument("--check", action="store_true", help="Exit 1 if any copy is stale; write nothing")
    args = parser.parse_args(argv)

    try:
        stale = sync(root, write=not args.check)
    except FileNotFoundError as exc:
        print(f"error: canonical rule file not found: {exc.filename}", file=sys.stderr)
        return 2

    if args.check:
        if stale:
            for path in stale:
                print(f"stale: {path}")
            print("Run: python3 scripts/sync_rules.py")
            return 1
        print("rule copies are in sync")
        return 0

    for path in stale:
        print(f"updated: {path}")
    if not stale:
        print("rule copies already in sync")
    return 0


if __name__ == "__main__":
    sys.exit(main())
