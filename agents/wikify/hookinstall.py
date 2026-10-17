"""``vibe wikify install-hook``: write a pre-push git hook, never overwriting one.

Ceiling: a convenience gate, not a security control.
"""

from __future__ import annotations

import os
from pathlib import Path

from agents.wikify import gitview

SCRIPT = """#!/bin/sh
# Installed by `vibe wikify install-hook`; delete this file to remove the gate.
if ! command -v vibe >/dev/null 2>&1; then
    echo "wikify: 'vibe' was not found on PATH; cannot check the wiki before pushing" >&2
    exit 1
fi
exec vibe wikify check --ci
"""


def plan(root: Path) -> tuple[Path | None, str]:
    """(hook path, "") when it can be written, else (None, reason)."""
    configured = gitview.run_git(root, "config", "--get", "core.hooksPath")
    if configured.returncode == 0:
        return None, (
            f"core.hooksPath is set ({configured.stdout.strip()}): git would not run a hook in "
            "the default directory. Add `vibe wikify check --ci` to your hook manager instead."
        )
    where = gitview.run_git(root, "rev-parse", "--git-path", "hooks")
    out = where.stdout.strip()
    if where.returncode != 0 or not out:
        return None, "cannot locate the git hooks directory"
    hooks = Path(out) if os.path.isabs(out) else Path(root) / out
    target = hooks / "pre-push"
    if target.exists() or target.is_symlink():
        return None, f"{target} already exists; it is never overwritten (add `vibe wikify check --ci` to it yourself)"
    return target, ""


def cmd_install_hook(cwd: str | Path | None = None, apply: bool = False) -> int:
    root = gitview.repo_root(cwd or os.getcwd())
    if root is None:
        print("not a git repository")
        return 1
    target, reason = plan(root)
    if target is None:
        print(f"refused: {reason}")
        return 1
    if not apply:
        print(f"would write {target} (mode 0755); rerun with --apply to install it:\n")
        print(SCRIPT, end="")
        return 0
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o755)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(SCRIPT)
        os.chmod(target, 0o755)
    except FileExistsError:
        print(f"refused: {target} already exists; it is never overwritten")
        return 1
    except OSError as exc:
        print(f"cannot write the hook: {type(exc).__name__}")
        return 1
    print(f"installed {target}")
    return 0
