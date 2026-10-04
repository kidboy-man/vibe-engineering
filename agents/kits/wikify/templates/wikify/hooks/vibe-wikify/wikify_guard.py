#!/usr/bin/env python3
"""Pre-tool-use hook that blocks an agent's `git push` while docs/wiki is stale.

Shared by Claude Code, Codex CLI and Cursor; same contract as the guardrails
hook: one tool-call JSON object on stdin, exit 2 + stderr blocks, exit 0 allows.
With --format=cursor every path (allow, deny, fail-open) prints a
{"permission": ...} JSON object, because Cursor treats empty stdout as a block.

This is a convenience gate, not a security control. It fails open on any
parse error, git error or timeout. Set VIBE_WIKIFY=off to disable it.

Freshness mirrors agents/wikify/state.py:is_fresh (vendored: hook scripts run
with a bare python3 and cannot import `agents`): no commits -> fresh; the state
file never committed -> stale; the commit that last touched the state file and
everything since must touch only docs/wiki/.

Known v1 limitations: it checks HEAD, not the ref being pushed
(`git push origin other:main`), and it does not cover pushes typed in a
terminal. On git errors or timeouts the hook intentionally allows (fail open)
whereas state.is_fresh reports stale; parity holds for normal repo states.
Known false-allow limits (heuristic parsing): `env -i git push`,
`sudo -u bob git push`, `git --git-dir x push`, `(cd x && git push)`,
`if ...; then git push; fi`, `$(git push)`, `bash -c "git push"`, combined
short flags such as `-nf` are treated as a normal push, and refspec deletions
(`git push origin :old`) are gated like a normal push. Heredoc bodies are
dropped on a best-effort basis. The hook never creates any file and only runs in repos whose working
tree has docs/wiki/.wikify.json.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import time

SHELL_TOOLS = {"", "bash", "shell", "local_shell"}
SEPARATORS = {";", "&&", "||", "|", "&", "|&"}
COMMAND_PREFIXES = {"sudo", "command", "env", "nohup", "time", "exec"}
NO_CHECK_FLAGS = {"--delete", "-d", "--dry-run", "-n"}
WIKI_DIR = "docs/wiki/"
STATE_REL = "docs/wiki/.wikify.json"
TIMEOUT_SECONDS = 10
BUDGET_SECONDS = 20  # total git time per hook invocation
_deadline = 0.0
MESSAGE = (
    "wikify: docs/wiki is out of date for this push. Follow docs/wiki/WIKIFY.md: run "
    "'vibe wikify plan', update the wiki, run 'vibe wikify verify' and 'vibe wikify mark', "
    "show the user the wiki diff and scan result, and only after the user confirms commit "
    "with 'git add -- docs/wiki'. Set VIBE_WIKIFY=off to bypass."
)


def _tokenize(line: str) -> list[str]:
    try:
        lexer = shlex.shlex(line, posix=True, punctuation_chars=True)
        lexer.commenters = ""  # `fix#12` is not a comment; never drop the tail
        lexer.whitespace_split = True
        return list(lexer)
    except ValueError:  # unbalanced quotes: degrade to a crude split
        return line.split()


HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1")


def _drop_heredocs(command: str) -> str:
    """Remove heredoc bodies (best effort) so their text is never parsed as commands."""
    kept: list[str] = []
    terminator: str | None = None
    for line in command.split("\n"):
        if terminator is not None:
            if line.strip() == terminator:
                terminator = None
            continue
        kept.append(line)
        match = HEREDOC.search(line)
        if match:
            terminator = match.group(2)
    return "\n".join(kept)


def _newlines_to_separators(command: str) -> str:
    """Replace unquoted newlines with `;`; newlines inside quotes stay in the token."""
    out: list[str] = []
    quote = ""
    i = 0
    while i < len(command):
        ch = command[i]
        if ch == "\\" and quote != "'" and i + 1 < len(command):
            out.append(command[i : i + 2])
            i += 2
            continue
        if quote:
            if ch == quote:
                quote = ""
        elif ch in "'\"":
            quote = ch
        elif ch == "\n":
            ch = ";"
        out.append(ch)
        i += 1
    return "".join(out)


def _segments(command: str) -> list[list[str]]:
    segments: list[list[str]] = []
    current: list[str] = []
    for token in _tokenize(_newlines_to_separators(_drop_heredocs(command))):
        if token in SEPARATORS:
            if current:
                segments.append(current)
            current = []
        else:
            current.append(token)
    if current:
        segments.append(current)
    return segments


def _strip_prefixes(tokens: list[str]) -> list[str]:
    i = 0
    while i < len(tokens) and (tokens[i] in COMMAND_PREFIXES or re.fullmatch(r"\w+=.*", tokens[i])):
        i += 1
    return tokens[i:]


def _resolve(cwd: str, target: str) -> str | None:
    path = os.path.normpath(os.path.join(cwd, os.path.expanduser(target)))
    return path if os.path.isdir(path) else None


def _git(cwd: str, *args: str) -> str | None:
    """stdout of ``git <args>`` in cwd; None on any failure (callers fail open)."""
    remaining = _deadline - time.monotonic()
    if remaining <= 0:
        return None  # budget exhausted: fail open
    try:
        result = subprocess.run(
            ["git", "-c", "core.quotePath=false", *args],
            cwd=cwd, capture_output=True, text=True, errors="replace",
            check=False, timeout=min(TIMEOUT_SECONDS, remaining),
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    return result.stdout if result.returncode == 0 else None


def _docs_only(output: str | None) -> bool:
    return output is not None and all(p.startswith(WIKI_DIR) for p in output.splitlines() if p)


def _is_stale(cwd: str) -> bool:
    """True only when git positively says the wiki is stale; any doubt -> False."""
    top = _git(cwd, "rev-parse", "--show-toplevel")
    if not top or not top.strip():
        return False
    root = top.strip()
    if not os.path.isfile(os.path.join(root, STATE_REL)):
        return False  # repo is not wikified
    if _git(root, "rev-parse", "--verify", "-q", "HEAD") is None:
        return False  # no commits (or git failed): nothing to cover
    base = _git(root, "log", "-1", "--format=%H", "--", STATE_REL)
    if base is None:
        return False
    base = base.strip()
    if not base:
        return True  # state file never committed
    in_base = _git(root, "show", "--name-only", "--no-renames", "--format=", base)
    since = _git(root, "diff", "--name-only", "--no-renames", f"{base}..HEAD")
    if in_base is None or since is None:
        return False
    return not (_docs_only(in_base) and _docs_only(since))


def _git_push_cwd(args: list[str], cwd: str) -> tuple[bool, str | None]:
    """For `git <args>`: (is a gated push, effective cwd or None if unresolvable)."""
    i = 0
    while i < len(args):
        if args[i] == "-C" and i + 1 < len(args):
            cwd = _resolve(cwd, args[i + 1])
            if cwd is None:
                return False, None
            i += 2
        elif args[i] == "-c":
            i += 2
        elif args[i].startswith("-"):
            i += 1
        else:
            rest = args[i + 1 :]
            return args[i] == "push" and not NO_CHECK_FLAGS & set(rest), cwd
    return False, cwd


def _shell_stale(command: str, cwd: str) -> bool:
    for tokens in _segments(command):
        tokens = _strip_prefixes(tokens)
        if not tokens:
            continue
        name, args = tokens[0].rsplit("/", 1)[-1], tokens[1:]
        if name == "cd":
            if args:
                resolved = _resolve(cwd, args[0])
                if resolved is None:
                    return False  # unresolvable: allow
                cwd = resolved
        elif name == "git":
            is_push, where = _git_push_cwd(args, cwd)
            if is_push and where is not None and _is_stale(where):
                return True
    return False


def decide(payload: object) -> str | None:
    """Return a block reason, or None to allow."""
    global _deadline
    _deadline = time.monotonic() + BUDGET_SECONDS
    if not isinstance(payload, dict):
        return None
    if str(payload.get("tool_name") or "").lower() not in SHELL_TOOLS:
        return None
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}
    command = tool_input.get("command", payload.get("command"))
    if not isinstance(command, str) or not command:
        return None
    cwd = str(payload.get("cwd") or os.getcwd())
    return MESSAGE if _shell_stale(command, cwd) else None


def _emit(cursor_format: bool, permission: str, reason: str | None = None) -> None:
    if cursor_format:
        payload = {"permission": permission}
        if reason:
            payload.update(user_message=reason, agent_message=reason)
        print(json.dumps(payload))


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    cursor_format = "--format=cursor" in argv or argv[-2:] == ["--format", "cursor"]
    if os.environ.get("VIBE_WIKIFY", "").lower() == "off":
        _emit(cursor_format, "allow")
        return 0
    try:
        reason = decide(json.loads(sys.stdin.read() or "null"))
    except Exception:  # noqa: BLE001 - fail open by design
        _emit(cursor_format, "allow")
        return 0
    if reason:
        _emit(cursor_format, "deny", reason)
        print(reason, file=sys.stderr)
        return 2
    _emit(cursor_format, "allow")
    return 0


if __name__ == "__main__":
    sys.exit(main())
