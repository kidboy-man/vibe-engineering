"""Pre-commit secret and PII scan of the rendered wiki.

Ceiling: the built-in rules are a floor, not a complete scanner. They catch
well-known token shapes, home paths, emails and quoted credential assignments.
``external_scanner`` only reports whether gitleaks/trufflehog is installed
(for ``doctor``); it is never invoked here.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import stat
from pathlib import Path

from agents.wikify.state import WIKI_DIR

ALLOW_REL = WIKI_DIR + ".wikify-allow"
MAX_BYTES = 1 << 20  # larger files are not read; they hard-block as "too-large"

FLOOR_NOTICE = (
    "Built-in scan rules are a floor, not a complete scanner; "
    "review the wiki text yourself before pushing."
)

# Every quantifier is bounded (Python 3.10 has no possessive quantifiers), but
# a bound alone is not enough: a run like `_eyJ_eyJ...` makes every `eyJ` a
# match start, so the cost is starts x per-start scan. The JWT header segment
# is therefore capped at 192 chars (real headers are ~36-150), which keeps the
# per-start work small; the start only excludes a preceding letter or digit, so
# `x_eyJ...` and `x-eyJ...` still hit. [^\S\r\n] is single-line whitespace
# that still matches NBSP and other Unicode spaces.
_WS = r"[^\S\r\n]*"
_KEY = r"(?:api[_-]?key|secret|token|password|passwd)['\"]?"
RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY")),
    ("aws-access-key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("github-token", re.compile(r"ghp_[A-Za-z0-9]{36}")),
    ("slack-token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,4096}")),
    ("bearer-token", re.compile(r"Bearer[^\S\r\n]{1,64}[A-Za-z0-9._-]{20,4096}")),
    ("jwt", re.compile(r"(?<![A-Za-z0-9])eyJ[\w-]{1,192}\.[\w-]{1,4096}\.[\w-]{1,4096}")),
    ("home-path", re.compile(r"/(?:home|Users)/[A-Za-z0-9._-]{1,128}/")),
    ("email", re.compile(r"[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9-]{1,63}(?:\.[A-Za-z0-9-]{1,63})+")),
    (
        "secret-assignment",
        re.compile(_KEY + _WS + r"[:=]" + _WS + r"""['"][^'"\s]{8,4096}['"]""", re.I),
    ),
    (
        # Unquoted value: >=10 chars with at least one digit (skips "password: required").
        "secret-assignment",
        re.compile(
            _KEY + _WS + r"[:=]" + _WS
            + r"(?=[A-Za-z0-9+/=_.-]{0,255}\d)[A-Za-z0-9+/=_.-]{10,256}",
            re.I,
        ),
    ),
)


def _scan(text: str) -> list[tuple[int, str, str]]:
    hits = []
    for rule, pattern in RULES:
        pos, line = 0, 1  # finditer is ordered: count newlines only since the last hit
        for m in pattern.finditer(text):
            line += text.count("\n", pos, m.start())
            pos = m.start()
            hits.append((line, rule, m.group(0)))
    return sorted(hits, key=lambda h: (h[0], h[1]))


def scan_text(text: str) -> list[tuple[int, str]]:
    """Return (1-based line, rule name) for every built-in rule match."""
    return [(line, rule) for line, rule, _ in _scan(text)]


_KEY_FORM = re.compile(r"sha256:[0-9a-f]{16}\Z")


def allow_key(text: str) -> str:
    """Allow-list key of a matched text: first 16 hex of its sha256."""
    return "sha256:" + hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:16]


def parse_allow(text: str) -> set[tuple[str, str]]:
    """Parse ``<page-rel>|sha256:<16 hex>`` lines (legacy: ``|<exact matched text>``).

    ``#`` and blank lines are ignored. Entries are returned as written.
    """
    entries = set()
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#") or "|" not in line:
            continue
        page, hit = line.split("|", 1)
        entries.add((page.strip(), hit.strip() if _KEY_FORM.match(hit.strip()) else hit))
    return entries


def canonical_allow(entries: set[tuple[str, str]]) -> set[tuple[str, str]]:
    """Entries with legacy plaintext mapped to its hash key (never shows the text)."""
    return {(p, t if _KEY_FORM.match(t) else allow_key(t)) for p, t in entries}


def legacy_allow_notices(entries: set[tuple[str, str]]) -> list[str]:
    """One migration notice per plaintext entry; shows the hash form, never the text."""
    return [
        f"ALLOW-LIST LEGACY: {p} has a plaintext entry; replace it with {p}|{allow_key(t)}"
        for p, t in sorted(entries)
        if not _KEY_FORM.match(t)
    ]


def load_allow(root: Path) -> set[tuple[str, str]]:
    try:
        raw = (Path(root) / ALLOW_REL).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return set()
    return parse_allow(raw)


def _all_hits(root: Path) -> list[tuple[str, int, str, str]]:
    wiki = Path(root) / WIKI_DIR
    if not wiki.is_dir():
        return []
    skip = Path(root) / ALLOW_REL
    items: list[tuple[Path, list[tuple[str, int, str, str]]]] = []

    def unreadable_dir(exc: OSError) -> None:  # fail closed, never skip silently
        path = Path(exc.filename) if exc.filename else wiki
        rel = path.relative_to(wiki).as_posix() if path != wiki else "."
        items.append((path, [(rel, 0, "unreadable", "unreadable")]))

    for dirpath, _dirs, files in os.walk(wiki, followlinks=False, onerror=unreadable_dir):
        for name in files:
            path = Path(dirpath) / name
            if path == skip:
                continue
            rel = path.relative_to(wiki).as_posix()
            try:
                st = os.lstat(path)
            except OSError:  # e.g. listable but not searchable directory
                items.append((path, [(rel, 0, "unreadable", "unreadable")]))
                continue
            if stat.S_ISLNK(st.st_mode) or stat.S_ISDIR(st.st_mode):
                continue  # symlinks are layout errors; never followed
            if not stat.S_ISREG(st.st_mode):  # FIFO, socket, device: never opened
                items.append((path, [(rel, 0, "unreadable", "unreadable")]))
                continue
            try:
                if st.st_size > MAX_BYTES:
                    items.append((path, [(rel, 0, "too-large", "too-large")]))
                    continue
                text = path.read_bytes().decode("utf-8", errors="replace")
            except OSError:
                items.append((path, [(rel, 0, "unreadable", "unreadable")]))
                continue
            items.append((path, [(rel, line, rule, hit) for line, rule, hit in _scan(text)]))
    return [hit for _, hits in sorted(items, key=lambda i: i[0]) for hit in hits]


def report(root: Path) -> tuple[list[str], list[str], list[str]]:
    """(errors, allow-list keys for the errors, allow-listed hits); one scan."""
    entries = load_allow(root)
    allow = canonical_allow(entries)
    plain = {e for e in entries}
    errors: list[str] = []
    keys: list[str] = []
    allowed: list[str] = []
    for rel, line, rule, text in _all_hits(root):
        key = allow_key(text)
        if (rel, key) in allow or (rel, text) in plain:
            allowed.append(f"{rel}:{line}: {rule} (allow-listed)")
        else:
            errors.append(f"{rel}:{line}: {rule}")
            keys.append(f"ALLOW-LIST KEY: {rel}:{line}: {rule} -> {rel}|{key}")
    return errors, keys, allowed


def scan_wiki(root: Path) -> list[str]:
    """Non-allow-listed hits as ``<rel>:<line>: <rule>`` (rel is under docs/wiki/)."""
    return report(root)[0]


def allowed_hits(root: Path) -> list[str]:
    """Hits suppressed by the allow-list, for display at the confirmation gate."""
    return report(root)[2]


def external_scanner() -> str | None:
    """Name of the first installed external scanner (informational only)."""
    for name in ("gitleaks", "trufflehog"):
        if shutil.which(name):
            return name
    return None
