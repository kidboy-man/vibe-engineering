#!/usr/bin/env python3
"""Pre-tool-use guard shared by Claude Code, Codex CLI and Cursor.

Reads one tool-call JSON object on stdin. Exit 2 with a reason on stderr
blocks the call (all three tools honour that contract); exit 0 allows it.

Cursor is the exception: it treats empty stdout from a permission hook as
invalid output and blocks, so with --format=cursor every path (allow, deny and
every fail-open case) prints a {"permission": ...} JSON object.

Deliberately narrow: it only blocks catastrophic or secret-exposing actions.
It is a speed bump for a well-meaning agent, not a sandbox — shell parsing is
heuristic and can be bypassed by obfuscation. Any parse or internal error
fails open, so a bug here can never brick the agent. Set VIBE_GUARDRAILS=off
to disable it for a session.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import shlex
import sys

SHELL_TOOLS = {"", "bash", "shell", "local_shell"}
SEPARATORS = {";", "&&", "||", "|", "&", "|&"}
COMMAND_PREFIXES = {"sudo", "command", "env", "nohup", "time", "exec"}
# Commands that read, copy, or write file contents; a secret path argument is only
# an exposure when handed to one of these (or redirected into).
FILE_READERS_WRITERS = {
    "cat", "less", "more", "head", "tail", "bat", "grep", "rg", "sed", "awk", "cut",
    "cp", "mv", "tee", "xxd", "strings", "base64", "source", ".", "scp", "rsync",
    "nano", "vi", "vim", "code", "diff", "sort", "openssl",
}
DANGEROUS_RM_TARGETS = {"/", "/*", "~", "~/", "~/*", "*", ".", "..", "./*"}
SECRET_BASENAMES = (".env", ".env.*", "*.pem", "id_rsa*", "id_ed25519*", "id_ecdsa*")
SECRET_SAFE_SUFFIXES = (".example", ".sample", ".template", ".dist", ".pub")
SQL_DESTRUCTIVE = re.compile(r"\b(drop|truncate)\b", re.IGNORECASE)
PATCH_FILE_LINE = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$", re.MULTILINE)


def is_secret_path(path: str) -> bool:
    if not isinstance(path, str) or not path:
        return False
    path = path.strip().rstrip("/")
    if path.endswith(SECRET_SAFE_SUFFIXES):
        return False
    if path.endswith(".aws/credentials"):
        return True
    base = path.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatchcase(base, pattern) for pattern in SECRET_BASENAMES)


def _tokenize(line: str) -> list[str]:
    try:
        lexer = shlex.shlex(line, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        return list(lexer)
    except ValueError:  # unbalanced quotes: degrade to a crude split
        return line.split()


def _segments(command: str) -> list[list[str]]:
    segments: list[list[str]] = []
    for line in command.splitlines():
        current: list[str] = []
        for token in _tokenize(line):
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


def _inside(path: str, root: str) -> bool:
    """True when *path* is strictly below *root* (the root itself does not count)."""
    return path.rstrip("/").startswith(root.rstrip("/") + "/")


def _rm_reason(args: list[str], cwd: str) -> str | None:
    flags = [a for a in args if a.startswith("-")]
    recursive = any(
        a == "--recursive" or (not a.startswith("--") and ("r" in a[1:] or "R" in a[1:])) for a in flags
    )
    if not recursive:
        return None
    # A cwd of "/" or $HOME would make nearly every absolute path "inside the project".
    project_root = cwd.rstrip("/") not in {"", os.path.expanduser("~").rstrip("/")}
    for target in (a for a in args if not a.startswith("-")):
        risky = (
            target in DANGEROUS_RM_TARGETS
            or target.startswith(("~", "$HOME", "${HOME}"))
            or ".." in target.split("/")
            or (target.startswith("/") and not (project_root and _inside(target, cwd)) and not _inside(target, "/tmp"))
        )
        if risky:
            return f"blocked: recursive rm on '{target}' (outside the project or too broad)"
    return None


def _git_subcommand(args: list[str]) -> tuple[str, list[str]]:
    i = 0
    while i < len(args):
        if args[i] in {"-C", "-c"}:
            i += 2
        elif args[i].startswith("-"):
            i += 1
        else:
            return args[i], args[i + 1 :]
    return "", []


def _git_reason(args: list[str]) -> str | None:
    sub, rest = _git_subcommand(args)
    flags = [a for a in rest if a.startswith("-")]
    if sub == "push" and any(a == "--force" or a == "-f" for a in flags):
        return "blocked: git push --force (use --force-with-lease)"
    if sub == "reset" and "--hard" in flags:
        return "blocked: git reset --hard discards uncommitted work"
    if sub == "clean":
        letters = "".join(a[1:] for a in flags if not a.startswith("--"))
        if "f" in letters and "x" in letters:
            return "blocked: git clean -fdx deletes untracked and ignored files"
    return None


def _segment_reason(tokens: list[str], cwd: str) -> str | None:
    tokens = _strip_prefixes(tokens)
    if not tokens:
        return None
    name, args = tokens[0].rsplit("/", 1)[-1], tokens[1:]

    if name == "rm":
        reason = _rm_reason(args, cwd)
    elif name == "git":
        reason = _git_reason(args)
    elif name in {"psql", "mysql", "mariadb"} and SQL_DESTRUCTIVE.search(" ".join(args)):
        reason = "blocked: destructive SQL (DROP/TRUNCATE) from the shell"
    else:
        reason = None
    if reason:
        return reason

    for i, token in enumerate(tokens):
        if token in {">", ">>"} and i + 1 < len(tokens) and is_secret_path(tokens[i + 1]):
            return f"blocked: writing to secret file '{tokens[i + 1]}'"
    if name in FILE_READERS_WRITERS:
        for arg in args:
            if is_secret_path(arg):
                return f"blocked: '{name}' on secret file '{arg}'"
    return None


def _shell_reason(command: str, cwd: str) -> str | None:
    for tokens in _segments(command):
        reason = _segment_reason(tokens, cwd)
        if reason:
            return reason
    return None


def _patch_paths(patch_text: str) -> list[str]:
    return PATCH_FILE_LINE.findall(patch_text)


def decide(payload: object) -> str | None:
    """Return a block reason, or None to allow."""
    if not isinstance(payload, dict):
        return None
    tool = str(payload.get("tool_name") or "").lower()
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}
    cwd = str(payload.get("cwd") or os.getcwd())

    command = tool_input.get("command", payload.get("command"))
    if isinstance(command, str) and command:
        if tool in SHELL_TOOLS:
            reason = _shell_reason(command, cwd)
            if reason:
                return reason
        elif tool == "apply_patch":
            for path in _patch_paths(command):
                if is_secret_path(path):
                    return f"blocked: patch touches secret file '{path}'"

    for key in ("file_path", "path", "notebook_path"):
        path = tool_input.get(key, payload.get(key))
        if is_secret_path(path):
            return f"blocked: access to secret file '{path}'"
    return None


def _emit(cursor_format: bool, permission: str, reason: str | None = None) -> None:
    if cursor_format:
        payload = {"permission": permission}
        if reason:
            payload.update(user_message=reason, agent_message=reason)
        print(json.dumps(payload))


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    cursor_format = "--format=cursor" in argv or argv[-2:] == ["--format", "cursor"]
    if os.environ.get("VIBE_GUARDRAILS", "").lower() == "off":
        _emit(cursor_format, "allow")
        return 0
    try:
        reason = decide(json.loads(sys.stdin.read() or "null"))
    except Exception:  # noqa: BLE001 - fail open by design
        _emit(cursor_format, "allow")
        return 0
    if reason:
        message = f"{reason}. Set VIBE_GUARDRAILS=off to bypass if this is intentional."
        _emit(cursor_format, "deny", message)
        print(message, file=sys.stderr)
        return 2
    _emit(cursor_format, "allow")
    return 0


if __name__ == "__main__":
    sys.exit(main())
