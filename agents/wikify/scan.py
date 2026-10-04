"""Pre-commit secret and PII scan of the rendered wiki.

Ceiling: the built-in rules are a floor, not a complete scanner. They catch
well-known token shapes, home paths, emails and quoted credential assignments.
``external_scanner`` only reports whether gitleaks/trufflehog is installed
(for ``doctor``); it is never invoked here.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from agents.wikify.state import WIKI_DIR

ALLOW_REL = WIKI_DIR + ".wikify-allow"

# Quantifiers are bounded so long non-matching runs cannot backtrack badly.
RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private-key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |)PRIVATE KEY-----")),
    ("aws-access-key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("github-token", re.compile(r"ghp_[A-Za-z0-9]{36}")),
    ("slack-token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}")),
    ("bearer-token", re.compile(r"Bearer[ \t]+[A-Za-z0-9._-]{20,}")),
    ("jwt", re.compile(r"eyJ[\w-]+\.[\w-]+\.[\w-]+")),
    ("home-path", re.compile(r"/(?:home|Users)/[A-Za-z0-9._-]+/")),
    ("email", re.compile(r"[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9-]{1,63}(?:\.[A-Za-z0-9-]{1,63})+")),
    (
        "secret-assignment",
        re.compile(
            r"""(?:api[_-]?key|secret|token|password)[ \t]*[:=][ \t]*['"][^'"\s]{8,}['"]""",
            re.I,
        ),
    ),
)


def _scan(text: str) -> list[tuple[int, str, str]]:
    hits = []
    for rule, pattern in RULES:
        for m in pattern.finditer(text):
            hits.append((text.count("\n", 0, m.start()) + 1, rule, m.group(0)))
    return sorted(hits, key=lambda h: (h[0], h[1]))


def scan_text(text: str) -> list[tuple[int, str]]:
    """Return (1-based line, rule name) for every built-in rule match."""
    return [(line, rule) for line, rule, _ in _scan(text)]


def load_allow(root: Path) -> set[tuple[str, str]]:
    """Parse ``<page-rel>|<exact matched text>`` lines; ``#`` and blanks ignored."""
    try:
        raw = (Path(root) / ALLOW_REL).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return set()
    entries = set()
    for line in raw.splitlines():
        if not line.strip() or line.lstrip().startswith("#") or "|" not in line:
            continue
        page, text = line.split("|", 1)
        entries.add((page.strip(), text))
    return entries


def _all_hits(root: Path) -> list[tuple[str, int, str, str]]:
    wiki = Path(root) / WIKI_DIR
    if not wiki.is_dir():
        return []
    skip = Path(root) / ALLOW_REL
    out = []
    for path in sorted(wiki.rglob("*")):
        if path == skip or path.is_symlink() or not path.is_file():
            continue
        text = path.read_bytes().decode("utf-8", errors="replace")
        rel = path.relative_to(wiki).as_posix()
        out.extend((rel, line, rule, hit) for line, rule, hit in _scan(text))
    return out


def scan_wiki(root: Path) -> list[str]:
    """Non-allow-listed hits as ``<rel>:<line>: <rule>`` (rel is under docs/wiki/)."""
    allow = load_allow(root)
    return [
        f"{rel}:{line}: {rule}"
        for rel, line, rule, text in _all_hits(root)
        if (rel, text) not in allow
    ]


def allowed_hits(root: Path) -> list[str]:
    """Hits suppressed by the allow-list, for display at the confirmation gate."""
    allow = load_allow(root)
    return [
        f"{rel}:{line}: {rule} (allow-listed)"
        for rel, line, rule, text in _all_hits(root)
        if (rel, text) in allow
    ]


def external_scanner() -> str | None:
    """Name of the first installed external scanner (informational only)."""
    for name in ("gitleaks", "trufflehog"):
        if shutil.which(name):
            return name
    return None
