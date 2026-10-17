"""Pure planning for ``vibe wikify adopt``: mapping rules, destinations, wrapping.

Nothing here writes files or runs git. The mapping file is the only judgment
input; a doc with no rule is ``unmapped`` and is never guessed at.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from agents.wikify import adopt_refs, agentmap, citations, docs_inventory, gitview, scan
from agents.wikify.state import WIKI_DIR

MAP_REL = WIKI_DIR + ".wikifymap"
KINDS = ("spec", "adr", "reference")
DEFAULT_KIND = "reference"
HUMAN_BEGIN = citations.HUMAN_BEGIN
HUMAN_END = citations.HUMAN_END
_WILD = re.compile(r"[*?\[]")
_NO_EOL = " no-eol"


@dataclass(frozen=True)
class Rule:
    glob: str
    folder: str  # relative to docs/wiki, ends with "/"
    kind: str
    line: int


def _folder_error(folder: str) -> str | None:
    if not folder.endswith("/") or folder == "/":
        return "destination must be a folder ending in '/'"
    if folder.startswith("/") or "\\" in folder or ":" in folder or "@" in folder:
        return "unsafe destination"
    parts = folder.split("/")[:-1]
    if any(p in ("", ".", "..") for p in parts):
        return "unsafe destination"
    if parts[0].casefold() == "sources":
        return "destination may not be under sources/"
    if any(ch.isspace() or ord(ch) < 32 for ch in folder):
        return "unsafe destination"
    return None


def parse_rules(lines: list[str]) -> tuple[list[Rule], list[str]]:
    """Rules plus ``.wikifymap:<line>: <reason>`` errors; any error rejects the file."""
    rules: list[Rule] = []
    errors: list[str] = []
    for n, raw in enumerate(lines, 1):
        text = raw.strip()
        if not text or text.startswith("#"):
            continue
        glob, sep, rest = text.partition("->")
        glob, tokens = glob.strip(), rest.split()
        if not sep or not glob or not tokens:
            errors.append(f"{MAP_REL}:{n}: expected '<glob> -> <folder>/ [kind=...]'")
            continue
        kind = DEFAULT_KIND
        if len(tokens) == 2 and tokens[1].startswith("kind="):
            kind = tokens[1][5:]
        elif len(tokens) != 1:
            errors.append(f"{MAP_REL}:{n}: unexpected text after the destination")
            continue
        if kind not in KINDS:
            errors.append(f"{MAP_REL}:{n}: kind must be one of {', '.join(KINDS)}")
            continue
        bad = _folder_error(tokens[0])
        if bad:
            errors.append(f"{MAP_REL}:{n}: {bad}")
            continue
        if len(glob) > citations.MAX_IGNORE_PATTERN_LEN or len(_WILD.findall(glob)) > citations.MAX_IGNORE_WILDCARDS:
            errors.append(f"{MAP_REL}:{n}: pattern over the length or wildcard limit")
            continue
        rules.append(Rule(glob, tokens[0], kind, n))
    if len(rules) > citations.MAX_IGNORE_PATTERNS:
        errors.append(f"{MAP_REL}: over {citations.MAX_IGNORE_PATTERNS} rules")
    return rules, errors


def load_rules(root: Path, map_file: Path | None = None) -> tuple[list[Rule], list[str]]:
    """Rules from the mapping file; an absent file means no rules, a rejected one is an error."""
    path = map_file or Path(root) / MAP_REL
    lines, status = citations.read_control_lines(path)
    if status == "absent":
        return [], []
    if status == "rejected":
        return [], [f"{MAP_REL}: rejected (symlink, not a regular file, not UTF-8, or over 64 KiB)"]
    return parse_rules(lines)


def _prefix(glob: str) -> str:
    """Literal leading directories of a glob ('docs/trd/**' -> 'docs/trd/')."""
    out: list[str] = []
    for part in glob.strip("/").split("/")[:-1]:
        if _WILD.search(part):
            break
        out.append(part)
    return "/".join(out) + "/" if out else ""


def match(rules: list[Rule], source: str) -> Rule | None:
    for rule in rules:
        if citations.is_ignored(source, [rule.glob]):
            return rule
    return None


def destination(rule: Rule, source: str) -> str | None:
    """Wiki-relative destination page, or None when the result is not a safe page path."""
    prefix = _prefix(rule.glob)
    rest = source[len(prefix):] if source.startswith(prefix) else source.rsplit("/", 1)[-1]
    dest = rule.folder + rest
    if not dest.endswith(".md") or agentmap._path_error(dest):
        return None
    return dest


def names_exactly(rules: list[Rule], source: str) -> bool:
    return any(r.glob.strip("/") == source and not _WILD.search(r.glob) for r in rules)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def provenance_ok(source: str) -> bool:
    return docs_inventory._citable(source) and "-->" not in source


def body_error(body: str) -> str | None:
    if HUMAN_BEGIN in body or HUMAN_END in body:
        return "body contains a human-block marker"
    return None


def wrap(source: str, body: str) -> str:
    """The body, byte for byte, inside one human block with a provenance line."""
    tail = "" if body.endswith("\n") else _NO_EOL
    text = f"{HUMAN_BEGIN}\n<!-- imported from={source}{tail} -->\n{body}"
    return text + ("" if body.endswith("\n") else "\n") + f"{HUMAN_END}\n"


_WRAPPED = re.compile(
    re.escape(HUMAN_BEGIN) + r"\n<!-- imported from=([^\s>]+)( no-eol)? -->\n", re.S
)


def is_wrapped(text: str) -> bool:
    return _WRAPPED.match(text) is not None


def unwrap(text: str) -> tuple[str, str] | None:
    """(source, original body) of a wrapped page, or None when ``text`` is not one."""
    m = _WRAPPED.match(text)
    if not m or not text.endswith(HUMAN_END + "\n"):
        return None
    inner = text[m.end() : len(text) - len(HUMAN_END) - 1]
    if m.group(2):
        if not inner.endswith("\n"):
            return None
        inner = inner[:-1]
    return m.group(1), inner


@dataclass(frozen=True)
class Candidate:
    source: str
    destination: str  # wiki-relative; "" when skipped
    kind: str  # spec | adr | reference | skipped
    reason: str | None
    sha256: str
    refs: tuple[adopt_refs.Ref, ...] = ()
    moved: bool = False  # resume: already moved by an interrupted run


@dataclass(frozen=True)
class Plan:
    candidates: list[Candidate]
    error: str | None = None


def _read_body(root: Path, source: str) -> bytes | None:
    path = Path(root) / source
    try:
        if path.is_symlink() or not path.is_file():
            return None
        return path.read_bytes()
    except OSError:
        return None


def _skip(source: str, reason: str, digest: str = "", refs: tuple = ()) -> Candidate:
    return Candidate(source, "", "skipped", reason, digest, refs)


def plan_candidates(
    root: Path,
    rules: list[Rule],
    include: list[str] | None = None,
    exclude: list[str] | None = None,
) -> Plan:
    """Classify every eligible doc: a move to a wiki page, or a skip with a reason."""
    root = Path(root)
    inv = docs_inventory.inventory(root)
    failed = docs_inventory.failure(inv)
    if failed:
        return Plan([], f"doc inventory failed: {failed}")
    docs = sorted(
        d for d in inv.docs
        if (not include or citations.is_ignored(d, include))
        and not (exclude and citations.is_ignored(d, exclude))
    )
    refs = adopt_refs.scan(root, docs)
    wiki_pages = {p for p in (gitview.tracked_files(root)) if p.startswith(WIKI_DIR)}
    taken = {p[len(WIKI_DIR):].casefold() for p in wiki_pages}
    out: list[Candidate] = []
    for source in docs:
        mine = tuple(refs.get(source, ()))
        rule = match(rules, source)
        if not source.endswith(".md"):
            out.append(_skip(source, "non-markdown", refs=mine))
        elif rule is None:
            out.append(_skip(source, "unmapped", refs=mine))
        elif "/" not in source and not names_exactly(rules, source):
            out.append(_skip(source, "root-file", refs=mine))
        else:
            out.append(_classify(root, source, rule, mine, taken))
    return Plan(out)


def _classify(root: Path, source: str, rule: Rule, refs: tuple, taken: set[str]) -> Candidate:
    dest = destination(rule, source)
    if dest is None or not provenance_ok(source):
        return _skip(source, "unsafe-path", refs=refs)
    data = _read_body(root, source)
    if data is None:
        return _resume(root, source, dest, rule, refs) or _skip(source, "unsafe-path", refs=refs)
    digest = sha256(data)
    try:
        body = data.decode("utf-8")
    except UnicodeDecodeError:
        return _skip(source, "unsafe-body", digest, refs)
    if body_error(body):
        return _skip(source, "unsafe-body", digest, refs)
    if scan.scan_text(body):
        return _skip(source, "secret-hit", digest, refs)
    if any(adopt_refs.is_config(r.file) and r.kind == "path" for r in refs):
        return _skip(source, "build-coupled", digest, refs)
    if dest.casefold() in taken or (Path(root) / WIKI_DIR / dest).exists():
        return _skip(source, "collision", digest, refs)
    taken.add(dest.casefold())
    return Candidate(source, dest, rule.kind, None, digest, refs)


def _resume(root: Path, source: str, dest: str, rule: Rule, refs: tuple) -> Candidate | None:
    """A doc whose source is gone but whose destination exists was moved by an interrupted run."""
    if (Path(root) / source).exists():
        return None
    data = _read_body(root, WIKI_DIR + dest)
    if data is None:
        return None
    try:
        wrapped = unwrap(data.decode("utf-8"))
    except UnicodeDecodeError:
        return None
    if wrapped is not None:
        if wrapped[0] != source:
            return None
        data = wrapped[1].encode("utf-8")
    return Candidate(source, dest, rule.kind, None, sha256(data), refs, moved=True)
