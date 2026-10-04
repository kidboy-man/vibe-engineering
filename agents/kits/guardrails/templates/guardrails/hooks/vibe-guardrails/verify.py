#!/usr/bin/env python3
"""Opt-in PostToolUse check for Claude Code: warn when an edited Go file is not gofmt-clean.

Exit 2 feeds the message back to the agent (the edit already happened, so this
is a nudge, not a block). Fails open on every error, and when gofmt is absent.
Set VIBE_GUARDRAILS=off to disable.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys


def main() -> int:
    if os.environ.get("VIBE_GUARDRAILS", "").lower() == "off":
        return 0
    try:
        payload = json.loads(sys.stdin.read() or "null")
        tool_input = payload.get("tool_input") if isinstance(payload, dict) else None
        path = tool_input.get("file_path") if isinstance(tool_input, dict) else None
        if not isinstance(path, str) or not path.endswith(".go") or not os.path.isfile(path):
            return 0
        gofmt = shutil.which("gofmt")
        if not gofmt:
            return 0
        result = subprocess.run(
            [gofmt, "-l", path], capture_output=True, text=True, timeout=10, check=False
        )
    except Exception:  # noqa: BLE001 - fail open by design
        return 0
    if result.returncode == 0 and result.stdout.strip():
        print(f"gofmt: {path} is not formatted; run `gofmt -w {path}`.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
