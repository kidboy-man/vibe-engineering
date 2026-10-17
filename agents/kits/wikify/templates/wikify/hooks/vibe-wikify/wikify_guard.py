#!/usr/bin/env python3
"""Pre-tool-use hook that blocks an agent's `git push` while docs/wiki is stale.

Shared by Claude Code, Codex CLI and Cursor; same contract as the guardrails
hook: one tool-call JSON object on stdin, exit 2 + stderr blocks, exit 0 allows.
With --format=cursor every path (allow, deny, fail-open) prints a
{"permission": ...} JSON object, because Cursor treats empty stdout as a block.

This is a convenience gate, not a security control. It fails open on any
parse error, git error or timeout. Set VIBE_WIKIFY=off to disable it.

The verdict comes from `vibe wikify check --ci --json` whenever `vibe` is on PATH,
so the hook, a git pre-push hook and CI cannot disagree: drift (`changed` or
`missing` citations) blocks and names the pages. One exception: while a cited file
changed but its citation has no recorded range hash (right after an upgrade, before
`vibe wikify mark`), `check` cannot see body edits, so the commit-order rule below
still decides. Without `vibe` (or on any error from it) the commit-order rule is the
fallback.

The commit-order rule mirrors agents/wikify/state.py:is_fresh (vendored: hook
scripts run with a bare python3 and cannot import `agents`): no commits -> fresh;
the state file never committed -> stale; the commit that last touched the state
file and everything since must touch only docs/wiki/.

Known v1 limitations: it checks HEAD, not the ref being pushed
(`git push origin other:main`), and it does not cover pushes typed in a
terminal. On git errors or timeouts the hook intentionally allows (fail open)
whereas state.is_fresh reports stale; parity holds for normal repo states.
Known false-allow limits (heuristic parsing): `env -i git push`,
`sudo -u bob git push`, `git --git-dir x push`, `(cd x && git push)`,
`if ...; then git push; fi`, `$(git push)`, `bash -c "git push"`, combined
short flags such as `-nf` are treated as a normal push, and refspec deletions
(`git push origin :old`) are gated like a normal push. Heredoc bodies are
dropped on a best-effort basis. Commands over 64 KiB are allowed unparsed (the
tokenizer is pure Python and slow on huge input), so a push hidden in such a
command is not gated. The hook never creates any file and only runs in repos whose working
tree has docs/wiki/.wikify.json.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time

SHELL_TOOLS = {"", "bash", "shell", "local_shell"}
SEPARATORS = {";", "&&", "||", "|", "&", "|&"}
COMMAND_PREFIXES = {
    "sudo", "command", "env", "nohup", "time", "exec",
    "timeout", "nice", "ionice", "stdbuf", "setsid",
}
# prefix -> options that take a separate value argument (`nice -n 5`, `timeout -s KILL`)
PREFIX_VALUE_FLAGS = {
    "timeout": {"-s", "-k", "--signal", "--kill-after"},
    "nice": {"-n", "--adjustment"},
    "ionice": {"-c", "-n", "-p", "-P", "-u", "--class", "--classdata", "--pid", "--pgid", "--uid"},
    "stdbuf": {"-i", "-o", "-e", "--input", "--output", "--error"},
    "time": {"-f", "-o", "--format", "--output"},
}
GROUP_TOKENS = {"{", "!"}  # leading shell grouping/negation; `(` runs are matched separately
NO_CHECK_FLAGS = {"--delete", "-d", "--dry-run", "-n"}
WIKI_DIR = "docs/wiki/"
STATE_REL = "docs/wiki/.wikify.json"
TIMEOUT_SECONDS = 10
MAX_COMMAND_CHARS = 64 * 1024  # longer commands are allowed unparsed (fail open)
BUDGET_SECONDS = 20  # total git time per hook invocation
_deadline = 0.0
MESSAGE = (
    "wikify: docs/wiki is out of date for this push. Follow docs/wiki/WIKIFY.md: run "
    "'vibe wikify plan', update the wiki, run 'vibe wikify verify' and 'vibe wikify mark', "
    "show the user the wiki diff and scan result, and only after the user confirms commit "
    "with 'git add -- docs/wiki'. Set VIBE_WIKIFY=off to bypass."
)
DRIFT_MESSAGE = (
    "wikify: docs/wiki has drifted from the code. Follow docs/wiki/WIKIFY.md: run "
    "'vibe wikify check' to see the pages, update only those, run 'vibe wikify verify' and "
    "'vibe wikify mark', show the user the wiki diff, and only after the user confirms commit "
    "with 'git add -- docs/wiki'. Set VIBE_WIKIFY=off to bypass."
)
UNBASELINED_MESSAGE = (
    "wikify: code changed under citations that have no recorded range hash, so drift cannot "
    "be checked precisely. Run 'vibe wikify verify' and 'vibe wikify mark', show the user the "
    "wiki diff, and only after the user confirms commit with 'git add -- docs/wiki'. "
    "Set VIBE_WIKIFY=off to bypass."
)
MAX_FINDINGS_SHOWN = 10
CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def _tokenize(line: str) -> list[str]:
    try:
        lexer = shlex.shlex(line, posix=True, punctuation_chars=True)
        lexer.commenters = ""  # `fix#12` is not a comment; never drop the tail
        lexer.whitespace_split = True
        return list(lexer)
    except ValueError:  # unbalanced quotes: degrade to a crude split
        return line.split()


HEREDOC = re.compile(r"(?<!<)<<(?!<)-?\s*(['\"]?)([A-Za-z_]\w*)\1")


def _heredoc_word(line: str) -> str | None:
    """Terminator of an unquoted `<<WORD` opener on this line, if any."""
    singles = doubles = pos = 0
    for match in HEREDOC.finditer(line):
        # an odd count of quote characters before the match means it is quoted;
        # count only the text since the previous match so the scan stays linear
        singles += line.count("'", pos, match.start())
        doubles += line.count('"', pos, match.start())
        pos = match.start()
        if singles % 2 == 0 and doubles % 2 == 0:
            return match.group(2)
    return None


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
        terminator = _heredoc_word(line)
    return "\n".join(kept)


def _newlines_to_separators(command: str) -> str:
    """Replace unquoted newlines with `;`; newlines inside quotes stay in the token."""
    out: list[str] = []
    quote = ""
    i = 0
    while i < len(command):
        ch = command[i]
        if ch == "\\" and quote != "'":
            cont = "\r\n" if command.startswith("\r\n", i + 1) else "\n" if command.startswith("\n", i + 1) else ""
            if cont:  # line continuation: shell removes it
                out.append("" if quote else " ")
                i += 1 + len(cont)
                continue
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


def _is_punct_separator(token: str) -> bool:
    """Punctuation runs like `));` or `);` merge into one token; they still end a segment."""
    return all(c in "();&|<>" for c in token) and bool(re.search(r"[;&|]", token))


def _segments(command: str) -> list[list[str]]:
    segments: list[list[str]] = []
    current: list[str] = []
    for token in _tokenize(_newlines_to_separators(_drop_heredocs(command))):
        if token in SEPARATORS or _is_punct_separator(token):
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
    while i < len(tokens):
        token = tokens[i]
        name = token.rsplit("/", 1)[-1]
        if token in GROUP_TOKENS or set(token) == {"("} or re.fullmatch(r"\w+=.*", token):
            i += 1
        elif name in COMMAND_PREFIXES:
            i += 1
            value_flags = PREFIX_VALUE_FLAGS.get(name, ())
            while i < len(tokens) and tokens[i].startswith("-"):
                i += 2 if tokens[i] in value_flags else 1
            if name == "timeout" and i < len(tokens):
                i += 1  # the DURATION operand
        else:
            break
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


def _wiki_root(cwd: str) -> str | None:
    """The repo root when it is wikified and has commits; None on any doubt."""
    top = _git(cwd, "rev-parse", "--show-toplevel")
    if not top or not top.strip():
        return None
    root = top.strip()
    if not os.path.isfile(os.path.join(root, STATE_REL)):
        return None  # repo is not wikified
    if _git(root, "rev-parse", "--verify", "-q", "HEAD") is None:
        return None  # no commits (or git failed): nothing to cover
    return root


def _commit_order_stale(root: str) -> bool:
    """True only when git positively says the wiki is stale; any doubt -> False."""
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


def _is_stale(cwd: str) -> bool:
    root = _wiki_root(cwd)
    return root is not None and _commit_order_stale(root)


def _find_vibe() -> str | None:
    return shutil.which("vibe")


def _vibe_check(root: str) -> dict | None:
    """Parsed `vibe wikify check --ci --json`, or None when it cannot give a verdict."""
    vibe = _find_vibe()
    remaining = _deadline - time.monotonic()
    if not vibe or remaining <= 0:
        return None
    try:
        result = subprocess.run(
            [vibe, "wikify", "check", "--ci", "--json"],
            cwd=root, capture_output=True, text=True, errors="replace",
            check=False, timeout=min(TIMEOUT_SECONDS, remaining),
        )
        data = json.loads(result.stdout)
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return None
    if result.returncode not in (0, 1) or not isinstance(data, dict):
        return None
    return data if isinstance(data.get("ok"), bool) else None


def _clean(text: object) -> str:
    return CONTROL.sub("?", str(text))[:200]


def _drift_message(data: dict) -> str:
    rows = [
        f"  {_clean(f.get('category'))} {_clean(f.get('page'))}:{_clean(f.get('line'))} "
        f"{_clean(f.get('path'))}:{_clean(f.get('start'))}-{_clean(f.get('end'))}"
        for f in (data.get("drift") or [])[:MAX_FINDINGS_SHOWN]
        if isinstance(f, dict)
    ]
    detail = _clean(data["error"]) if data.get("error") else ""
    head = DRIFT_MESSAGE if not detail else f"{DRIFT_MESSAGE} (check failed: {detail})"
    return "\n".join([head, *rows])


def _blocked(cwd: str) -> str | None:
    """A block reason for a push from ``cwd``, or None to allow."""
    root = _wiki_root(cwd)
    if root is None:
        return None
    data = _vibe_check(root)
    if data is None:
        return MESSAGE if _commit_order_stale(root) else None
    if not data["ok"]:
        return _drift_message(data)
    counts = data.get("counts")
    unbaselined = counts.get("unbaselined_changed", 0) if isinstance(counts, dict) else 0
    if unbaselined and _commit_order_stale(root):
        return UNBASELINED_MESSAGE
    return None


def _git_push_cwd(args: list[str], cwd: str) -> tuple[bool, str]:
    """For `git <args>`: (is a gated push, effective cwd).

    An unresolvable `-C` target (e.g. `"$R"`) keeps the current cwd.
    """
    i = 0
    while i < len(args):
        if args[i] == "-C" and i + 1 < len(args):
            cwd = _resolve(cwd, args[i + 1]) or cwd
            i += 2
        elif args[i] == "-c":
            i += 2
        elif args[i].startswith("-"):
            i += 1
        else:
            rest = args[i + 1 :]
            return args[i] == "push" and not NO_CHECK_FLAGS & set(rest), cwd
    return False, cwd


def _shell_block(command: str, cwd: str) -> str | None:
    for tokens in _segments(command):
        tokens = _strip_prefixes(tokens)
        if not tokens:
            continue
        name, args = tokens[0].rsplit("/", 1)[-1], tokens[1:]
        if name == "cd":
            if args:
                cwd = _resolve(cwd, args[0]) or cwd  # unresolvable: keep cwd, keep scanning
        elif name == "git":
            is_push, where = _git_push_cwd(args, cwd)
            if is_push:
                reason = _blocked(where)
                if reason:
                    return reason
    return None


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
    if not isinstance(command, str) or not command or len(command) > MAX_COMMAND_CHARS:
        return None
    cwd = str(payload.get("cwd") or os.getcwd())
    return _shell_block(command, cwd)


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
