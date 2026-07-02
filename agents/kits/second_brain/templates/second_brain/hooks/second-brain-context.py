#!/usr/bin/env python3
"""vibe-engineering second-brain kit — SessionStart context injector.

Reads wiki/hot.md and wiki/index.md from the second-brain vault (if present)
and prints them so the host agent folds them into session context. Supports
multiple agents' hook output contracts via --format:
  - plain (default): raw text on stdout — Claude Code, Codex CLI.
  - cursor: JSON envelope {"additional_context": "<text>"} — Cursor.
Contract: NEVER raise, NEVER block session start, NEVER write anything,
exit 0 always — even on any error, missing vault, or missing qmd.
"""
import argparse
import json
import os
import sys

MAX_HOT_CHARS = 4000     # hot.md is ~500 words by design; generous cap, cheap insurance
MAX_INDEX_CHARS = 6000   # index.md is an unbounded catalog; this is the real bloat guard


def _vault_dir() -> str:
    env = os.environ.get("VIBE_SECOND_BRAIN_PATH")
    if env:
        return env
    home = os.environ.get("HOME") or os.path.expanduser("~")
    return os.path.join(home, "second-brain")


def _read_capped(path: str, cap: int) -> "str | None":
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            data = fh.read(cap + 1)
    except OSError:
        return None
    if len(data) > cap:
        data = data[:cap] + "\n\n...(truncated; read the full file for more)"
    return data


def _build_context_text() -> "str | None":
    """Return the auto-loaded context text, or None if the vault has nothing yet."""
    vault = _vault_dir()
    hot = _read_capped(os.path.join(vault, "wiki", "hot.md"), MAX_HOT_CHARS)
    index = _read_capped(os.path.join(vault, "wiki", "index.md"), MAX_INDEX_CHARS)
    if hot is None and index is None:
        return None  # no vault / no seed pages yet — silent, not an error

    lines = [
        "## second-brain vault (auto-loaded context)",
        f"Vault: {vault}",
        "Use the qmd MCP tools (query/get/multi_get/status) to search further,",
        "and file new learnings back into this vault. See your agent's instructions file.",
        "",
    ]
    if hot is not None:
        lines += ["### wiki/hot.md", hot, ""]
    if index is not None:
        lines += ["### wiki/index.md", index]
    return "\n".join(lines)


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--format", choices=["plain", "cursor"], default="plain")
    args = parser.parse_args(argv)

    text = _build_context_text()
    if text is None:
        return 0

    if args.format == "cursor":
        print(json.dumps({"additional_context": text}))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)  # never fail session start
