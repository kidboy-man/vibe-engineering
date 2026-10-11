# Wikify Agent Map Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `docs/wiki/index.md` a verified agent map and add `vibe wikify link`, which writes a small marked pointer block into `AGENTS.md` (and existing `CLAUDE.md` / `GEMINI.md`), so agents load wiki pages on demand instead of bloating context.

**Architecture:** A new pure module `agents/wikify/agentmap.py` owns the map grammar, validation and pointer-block template. `verify` and `plan` consume it; `link` is a new command that writes only a marked block via `marked_section_strategy`. No change to freshness (`state.is_fresh`), the hook, or the parity test.

**Tech Stack:** Python 3.10+ stdlib, `unittest`, git CLI.

**Spec:** `docs/superpowers/specs/2026-10-11-wikify-agent-map-design.md` (extends `docs/superpowers/specs/2026-10-04-wikify-design.md`).

## Global Constraints
- Python 3.10+, stdlib only, 4-space indent, no new dependencies; match surrounding style in `agents/wikify/`.
- Test commands in this environment MUST be prefixed `FORCE_COLOR= NO_COLOR=1 PYTHON_COLORS=0` (the shell has `FORCE_COLOR=3`, which colours argparse help on Python 3.14 and breaks help snapshots). Full suite: `python3 -m unittest discover -s tests`; baseline **806 tests OK**.
- Map block markers exactly `<!-- wikify:map -->` / `<!-- /wikify:map -->` in top-level `docs/wiki/index.md`; entry grammar `- [<title>](<path>.md) — <when-hint>` with an em dash (U+2014) between spaces; title 1-60 chars, hint 1-80 chars, neither containing ``[ ] ( ) ` < > @`` or newline; caps 60 entries and 6 KiB.
- Pointer block markers exactly `<!-- wikify:pointer -->` / `<!-- /wikify:pointer -->`; static template, plain relative links, never `@` imports.
- `link` writes only inside the marked block, never creates `CLAUDE.md`/`GEMINI.md`, refuses symlinks / gitignored / outside-root targets, and never touches `.wikify.json`.
- Notices about pointer blocks never change `verify`'s exit code.
- Commits: Conventional Commits, scope `wikify`; end every message with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. Stage explicit paths only; never `.superpowers/`.
- Repo conventions (AGENTS.md): installer safety, dry-run side-effect free, help fixtures updated by hand/regeneration when a help string changes.

## Review Focus
1. Entry with a non-em-dash separator (`-`, en dash, double hyphen) must give a clear error, not silently parse (Task 1).
2. Title/hint carrying markup that could act as an import or injection: `@path`, `[x](y)`, backticks, HTML, `(src: ...)` — grammar rejects (Task 1).
3. Unicode control/format characters (bidi overrides U+202E, zero-width) in title/hint or path are rejected (Task 1).
4. CRLF line endings in `index.md` and in `AGENTS.md` (Tasks 1, 3).
5. Map block inside a human block is ignored and does not satisfy reachability (Task 2).
6. `AGENTS.md` with exactly one of the two markers (hand-edited): `link` must refuse, not prepend a second block (Task 3).
7. `AGENTS.md` that is not UTF-8 or is huge: refuse, never corrupt (Task 3).
8. `link` backup must not create a `backups/` directory in the user's repo (Task 3).
9. Orphan pages when no map block exists: opt-in rule, notice only (Task 2).

## File Structure
- Create `agents/wikify/agentmap.py` — map grammar, validation, `strip_map`, pointer template/markers, pointer inspection helpers. Pure (no git, no writes). One responsibility: the format.
- Create `agents/wikify/link_cmd.py` — `cmd_link`: target discovery, refusals, diff, backup, write. Depends on `agentmap`, `gitview`, `state`.
- Modify `agents/wikify/citations.py` — add public `strip_human(text)`; no behaviour change.
- Modify `agents/wikify/commands.py` — `_verify` map rule + pointer notices; `cmd_wikify` dispatches `link`.
- Modify `agents/wikify/plan.py` — `map_missing` key + render.
- Modify `agents/wikify/init_cmd.py` — print one-line hint to run `link`.
- Modify `agents/cli.py` — `link` subparser (`--dry-run`); fixtures `tests/fixtures/cli_help/wikify_help.txt` (+ new `wikify_link_help.txt` and its test).
- Modify `agents/kits/wikify/templates/wikify/WIKIFY.md` (map protocol, keep scanning clean, <= ~140 lines) and `README.md`.
- Tests: create `tests/test_wikify_agentmap.py`, `tests/test_wikify_link.py`; extend `tests/test_wikify_cli.py`, `tests/test_wikify_plan.py`, `tests/test_wikify_init.py`, `tests/test_cli_contract.py`.

---
### Task 1: Map grammar and validator (`agentmap.py`, pure)

**Files:**
- Create: `agents/wikify/agentmap.py`
- Test: `tests/test_wikify_agentmap.py`

**Interfaces:**
- Produces:
  - `MAP_BEGIN: str`, `MAP_END: str`, `MAX_ENTRIES = 60`, `MAX_BYTES = 6 * 1024`
  - `class MapEntry(NamedTuple): title: str; path: str; hint: str; line: int`
  - `strip_map(text: str) -> str` — replaces every map block (markers included) with the same number of newlines; text without a block is returned unchanged.
  - `check_map(clean: str, pages: set[str]) -> MapReport` where `clean` is the index text with human blocks already removed (line numbers preserved) and `pages` are page paths relative to `docs/wiki` (may include `index.md`).
  - `class MapReport(NamedTuple): has_block: bool; entries: list[MapEntry]; errors: list[str]; mapped: set[str]; missing: list[str]` — `errors` are `"index.md:<line>: <reason>"`; `missing` = sorted pages not in the map and not `index.md`/`WIKIFY.md` (empty when `has_block` is False).

- [ ] **Step 1: Write the failing tests** (`tests/test_wikify_agentmap.py`)

```python
import unittest

from agents.wikify import agentmap

PAGES = {"index.md", "domain/pay.md", "technical/idem.md"}


def block(*lines: str) -> str:
    return "# Wiki index\n\n" + agentmap.MAP_BEGIN + "\n" + "\n".join(lines) + "\n" + agentmap.MAP_END + "\n"


def entry(path: str, title: str = "T", hint: str = "when touching x") -> str:
    return f"- [{title}]({path}) — {hint}"


class GrammarTests(unittest.TestCase):
    def test_valid_map_reaches_all_pages(self):
        rep = agentmap.check_map(block(entry("domain/pay.md"), entry("technical/idem.md")), PAGES)
        self.assertTrue(rep.has_block)
        self.assertEqual(rep.errors, [])
        self.assertEqual(rep.mapped, {"domain/pay.md", "technical/idem.md"})
        self.assertEqual(rep.missing, [])

    def test_no_block_is_opt_in(self):
        rep = agentmap.check_map("# Wiki index\n", PAGES)
        self.assertFalse(rep.has_block)
        self.assertEqual(rep.errors, [])
        self.assertEqual(rep.missing, [])

    def test_orphan_page_is_an_error(self):
        rep = agentmap.check_map(block(entry("domain/pay.md")), PAGES)
        self.assertEqual(rep.missing, ["technical/idem.md"])
        self.assertTrue(any("technical/idem.md" in e and "not reachable" in e for e in rep.errors))

    def test_bad_lines(self):
        cases = {
            "hyphen separator": "- [T](domain/pay.md) - when x",
            "en dash": "- [T](domain/pay.md) – when x",
            "missing hint": "- [T](domain/pay.md) — ",
            "prose line": "Some prose here",
            "import": "- [T](@domain/pay.md) — when x",
            "scheme": "- [T](https://x.y/pay.md) — when x",
            "dotdot": "- [T](../pay.md) — when x",
            "absolute": "- [T](/pay.md) — when x",
            "backslash": "- [T](domain\\pay.md) — when x",
            "not md": "- [T](domain/pay.txt) — when x",
            "paren in hint": "- [T](domain/pay.md) — see (src: a.py:1)",
            "bracket in title": "- [T [x]](domain/pay.md) — when x",
            "backtick link": "- [`T`](domain/pay.md) — when x ",
            "at in hint": "- [T](domain/pay.md) — load @docs/wiki/x.md",
            "html in hint": "- [T](domain/pay.md) — <b>when</b> x",
            "bidi": "- [T](domain/pay.md) — when ‮x",
            "zero width": "- [T](domain/pay.md) — wh​en x",
            "long hint": "- [T](domain/pay.md) — " + "x" * 81,
            "long title": "- [" + "t" * 61 + "](domain/pay.md) — when x",
        }
        for name, line in cases.items():
            with self.subTest(name):
                rep = agentmap.check_map(block(line), {"index.md", "domain/pay.md"})
                self.assertTrue(rep.errors, name)

    def test_unknown_page_and_duplicate(self):
        rep = agentmap.check_map(block(entry("domain/nope.md"), entry("domain/pay.md"), entry("domain/pay.md")), PAGES)
        text = "\n".join(rep.errors)
        self.assertIn("domain/nope.md", text)
        self.assertIn("duplicate", text)

    def test_caps(self):
        many = [entry(f"p{i}.md") for i in range(61)]
        rep = agentmap.check_map(block(*many), {"index.md"} | {f"p{i}.md" for i in range(61)})
        self.assertTrue(any("60 entries" in e for e in rep.errors))
        fat = [entry("domain/pay.md", hint="y" * 80)] * 1  # one entry, but pad the block with blanks
        rep = agentmap.check_map(block(*fat) .replace("\n-", "\n" + "\n" * 7000 + "-", 1), PAGES)
        self.assertTrue(any("6144 bytes" in e or "6 KiB" in e for e in rep.errors))

    def test_two_blocks(self):
        one = block(entry("domain/pay.md"))
        rep = agentmap.check_map(one + one, PAGES)
        self.assertTrue(any("more than one map block" in e for e in rep.errors))

    def test_unclosed_block(self):
        rep = agentmap.check_map("# I\n" + agentmap.MAP_BEGIN + "\n" + entry("domain/pay.md") + "\n", PAGES)
        self.assertTrue(any("unclosed" in e for e in rep.errors))

    def test_crlf(self):
        rep = agentmap.check_map(block(entry("domain/pay.md"), entry("technical/idem.md")).replace("\n", "\r\n"), PAGES)
        self.assertEqual(rep.errors, [])

    def test_line_numbers_are_original(self):
        text = "# I\n\n\n" + agentmap.MAP_BEGIN + "\nprose\n" + agentmap.MAP_END + "\n"
        rep = agentmap.check_map(text, PAGES)
        self.assertTrue(rep.errors[0].startswith("index.md:5:"))

    def test_strip_map_preserves_line_count(self):
        text = "a\n" + block(entry("domain/pay.md")) + "tail\n"
        out = agentmap.strip_map(text)
        self.assertEqual(out.count("\n"), text.count("\n"))
        self.assertNotIn("pay.md", out)
        self.assertIn("tail", out)
        self.assertEqual(agentmap.strip_map("no block\n"), "no block\n")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

Run: `FORCE_COLOR= NO_COLOR=1 PYTHON_COLORS=0 python3 -m unittest tests.test_wikify_agentmap`
Expected: ImportError / ERROR (module `agents.wikify.agentmap` missing).

- [ ] **Step 3: Implement `agents/wikify/agentmap.py`**

```python
"""Agent map: the navigation block in docs/wiki/index.md and the pointer block
written into AGENTS.md. Pure: no git, no file writes.

The map is navigation, not a factual claim, so its lines are validated by a strict
grammar instead of the citation rule. Entry text is agent-written and untrusted:
the grammar bans markup that could act as an import, link or HTML.
"""

from __future__ import annotations

import re
import unicodedata
from typing import NamedTuple

MAP_BEGIN = "<!-- wikify:map -->"
MAP_END = "<!-- /wikify:map -->"
MAX_ENTRIES = 60
MAX_BYTES = 6 * 1024
EXEMPT_FROM_REACHABILITY = {"index.md", "WIKIFY.md"}

POINTER_BEGIN = "<!-- wikify:pointer -->"
POINTER_END = "<!-- /wikify:pointer -->"
POINTER_BODY = (
    "\n## Repo docs (wikify)\n"
    "Repo knowledge lives in `docs/wiki/`. Start at [docs/wiki/index.md](docs/wiki/index.md): it is a map.\n"
    "Load only the pages whose \"when\" hint matches your task; do not read the whole wiki.\n"
)

_BLOCK = re.compile(re.escape(MAP_BEGIN) + r"(.*?)" + re.escape(MAP_END), re.S)
_ENTRY = re.compile(r"^- \[([^\[\]()`<>@]{1,60})\]\(([^()\s]+)\) — ([^\[\]()`<>@]{1,80})$")


class MapEntry(NamedTuple):
    title: str
    path: str
    hint: str
    line: int


class MapReport(NamedTuple):
    has_block: bool
    entries: list
    errors: list
    mapped: set
    missing: list


def strip_map(text: str) -> str:
    """Blank every map block (markers included), keeping the line count."""
    return _BLOCK.sub(lambda m: "\n" * m.group(0).count("\n"), text)


def _bad_chars(s: str) -> bool:
    return any(unicodedata.category(c) in {"Cc", "Cf"} for c in s)


def _path_error(path: str) -> str | None:
    if path.startswith("/") or "\\" in path or ":" in path or "@" in path:
        return "path must be relative to docs/wiki, with no scheme, backslash or @"
    if any(seg in {"", ".", ".."} for seg in path.split("/")):
        return "path must not contain empty, . or .. segments"
    if not path.lower().endswith(".md"):
        return "path must end in .md"
    if _bad_chars(path):
        return "path contains control or format characters"
    return None


def check_map(clean: str, pages: set[str]) -> MapReport:
    """Validate the map in ``clean`` (index.md text, human blocks already removed)."""
    errors: list[str] = []
    entries: list[MapEntry] = []
    mapped: set[str] = set()
    opens = clean.count(MAP_BEGIN)
    blocks = list(_BLOCK.finditer(clean))
    if opens == 0 and MAP_END not in clean:
        return MapReport(False, [], [], set(), [])
    if opens > 1 or len(blocks) > 1:
        errors.append("index.md:1: more than one map block")
    if opens != len(blocks) or (opens == 0 and MAP_END in clean):
        errors.append(f"index.md:{clean.count(chr(10), 0, clean.find(MAP_BEGIN)) + 1 if MAP_BEGIN in clean else 1}: unclosed or stray map marker")
    if not blocks:
        return MapReport(opens > 0, [], errors, set(), [])
    block = blocks[0]
    body = block.group(1)
    if len(body.encode("utf-8")) > MAX_BYTES:
        errors.append(f"index.md:{clean.count(chr(10), 0, block.start()) + 1}: map block exceeds {MAX_BYTES} bytes (6 KiB cap)")
    first = clean.count("\n", 0, block.start(1))  # 0-based line of the text after BEGIN
    for offset, raw in enumerate(body.split("\n")):
        line = first + offset + 1
        text = raw.rstrip("\r")
        if offset == 0 or not text.strip():
            if text.strip():
                errors.append(f"index.md:{line}: text on the marker line")
            continue
        m = _ENTRY.match(text)
        if not m or _bad_chars(text):
            errors.append(
                f"index.md:{line}: not a map entry; expected "
                "`- [title](path.md) — when-hint` with an em dash, no brackets or parentheses in title/hint"
            )
            continue
        title, path, hint = m.group(1), m.group(2), m.group(3)
        problem = _path_error(path)
        if problem:
            errors.append(f"index.md:{line}: {problem}")
            continue
        if path in mapped:
            errors.append(f"index.md:{line}: duplicate entry for {path}")
            continue
        if path not in pages:
            errors.append(f"index.md:{line}: {path} is not a page under docs/wiki")
            continue
        mapped.add(path)
        entries.append(MapEntry(title, path, hint, line))
    if len(entries) > MAX_ENTRIES:
        errors.append(f"index.md:{first + 1}: map has {len(entries)} entries; the cap is {MAX_ENTRIES} entries")
    missing = sorted(p for p in pages if p not in mapped and p not in EXEMPT_FROM_REACHABILITY)
    errors.extend(f"index.md:{first + 1}: {p} is not reachable from the map" for p in missing)
    return MapReport(True, entries, errors, mapped, missing)
```

Note for the implementer: the oversize test in Step 1 pads the block with blank lines to exceed 6144 bytes; the message must contain `6 KiB cap` or `6144 bytes` — adjust the test's `assertTrue` to match the exact text above (`exceeds 6144 bytes (6 KiB cap)`).

- [ ] **Step 4: Run to verify pass**

Run: `FORCE_COLOR= NO_COLOR=1 PYTHON_COLORS=0 python3 -m unittest tests.test_wikify_agentmap -v`
Expected: all tests PASS. Fix grammar edge cases until the table passes; do not weaken the table.

- [ ] **Step 5: Commit**

```bash
git add agents/wikify/agentmap.py tests/test_wikify_agentmap.py
git commit -m "feat(wikify): agent map grammar and validator

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---
### Task 2: Wire the map rule into `verify` and `plan`

**Files:**
- Modify: `agents/wikify/citations.py` (add `strip_human`), `agents/wikify/commands.py` (`_verify`), `agents/wikify/plan.py` (`build_plan`, `render`)
- Test: `tests/test_wikify_cli.py`, `tests/test_wikify_plan.py`

**Interfaces:**
- Consumes: `agentmap.check_map`, `agentmap.strip_map`, `agentmap.MapReport` (Task 1); `citations.walk_wiki`, `citations.verify_page`.
- Produces: `citations.strip_human(text) -> str` (public alias of `_strip_human`); `plan["map_missing"]: list[str]` (always present; sorted pages not in the map, `[]` when there is no map block); `render` prints `map_missing (N):` after `uncovered`.

Behavior:
- In `_verify`, for the page whose rel is exactly `index.md`: run `citations.verify_page` on `agentmap.strip_map(citations.strip_human(text))` (so map lines are not "uncited paragraphs"); run `agentmap.check_map(citations.strip_human(text), {rel for rel, _ in pages})` and append its `errors`. Other pages unchanged. Human-block notices still use the original text. The scan still reads the whole file.
- No map block: no errors; if there is at least one page besides `index.md`, add the notice `MAP: no map block in docs/wiki/index.md; N page(s) are not reachable from an agent map` (notice only).
- `plan.map_missing`: use `agentmap.check_map` on the working-tree `index.md` (read via `walk_wiki` page list; absent -> `[]`).

- [ ] **Step 1: Write failing tests**

In `tests/test_wikify_cli.py` (reuse that file's repo helpers; names: use whatever `RepoCase`/`commit`/`init` helpers it already defines — read the file first) add a `MapRuleTests` class with these cases, each asserting on `run_verify(root)` output lines and rc:
1. After `init`, writing `index.md` with a valid map block listing one cited page → rc 0.
2. Map entry line does NOT produce `uncited paragraph` (assert no line containing `uncited`).
3. Page exists but is not in the map block → rc 1 and a line containing `is not reachable from the map`.
4. Entry pointing at a missing page → rc 1 (`is not a page under docs/wiki`).
5. No map block, one extra page → rc 0 and a `MAP:` notice line present.
6. Map block wrapped inside a human block → ignored: not counted as a map (so reachability not enforced) and the `MAP:` notice appears.
7. A secret-shaped string placed in a hint is still caught by the scan (build the fake token by string concatenation).
8. Prose paragraph outside the block in `index.md` without citation → still `uncited paragraph` error (exemption is only for the block).

In `tests/test_wikify_plan.py`: `map_missing` lists pages absent from the map; `[]` with no block; key always present; `render` contains `map_missing (`.

- [ ] **Step 2: Run to verify failure** — `... python3 -m unittest tests.test_wikify_cli tests.test_wikify_plan` → new tests FAIL (map rule absent).

- [ ] **Step 3: Implement**

`citations.py`: add below `_strip_human`:

```python
def strip_human(text: str) -> str:
    """Blank human blocks, keeping the line count (public wrapper)."""
    return _strip_human(text)
```

`commands.py` `_verify` loop becomes:

```python
        index_text = None
        for rel, path in pages:
            text = path.read_text(encoding="utf-8")
            body = text
            if rel == "index.md":
                index_text = text
                body = agentmap.strip_map(citations.strip_human(text))
            errors.extend(citations.verify_page(root, rel, body, ignore))
            notices.extend(_notices(root, rel, text))
        if index_text is not None:
            report = agentmap.check_map(
                citations.strip_human(index_text), {rel for rel, _ in pages}
            )
            errors.extend(report.errors)
            others = [rel for rel, _ in pages if rel not in agentmap.EXEMPT_FROM_REACHABILITY]
            if not report.has_block and others:
                notices.append(
                    f"MAP: no map block in docs/wiki/index.md; {len(others)} page(s) "
                    "are not reachable from an agent map"
                )
```

(import `agentmap` from `agents.wikify`). `plan.py`: add `"map_missing": []` to the dict, compute with `agentmap.check_map` from the `index.md` working-tree text when present (use `citations.walk_wiki(root)[1]` to find it; wrap read in try/except OSError -> `[]`), and extend `render`'s key loop to `("changed", "refresh_pages", "uncovered", "map_missing", "contexts")`.

- [ ] **Step 4: Run to verify pass** — focused modules, then the full suite (expect baseline + new tests, all OK). `test_wikify_plan.py` equality assertions on the plan dict may need the new key; update them minimally.

- [ ] **Step 5: Commit**

```bash
git add agents/wikify/citations.py agents/wikify/commands.py agents/wikify/plan.py tests/test_wikify_cli.py tests/test_wikify_plan.py
git commit -m "feat(wikify): verify the agent map and report unmapped pages

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---
### Task 3: `vibe wikify link` and pointer notices

**Files:**
- Create: `agents/wikify/link_cmd.py`
- Modify: `agents/wikify/agentmap.py` (pointer helpers), `agents/wikify/commands.py` (dispatch + `verify` notices), `agents/cli.py` (`link` subparser), `tests/fixtures/cli_help/wikify_help.txt` (+ new `wikify_link_help.txt`)
- Test: `tests/test_wikify_link.py`, `tests/test_cli_contract.py`, `tests/test_wikify_cli.py`

**Interfaces:**
- Consumes: `merge_strategies.marked_section_strategy(template, existing, begin_marker, end_marker) -> (merged, action)`; `gitview.repo_root`, `gitview.ignored`, `gitview.run_git`; `state.WIKI_DIR`.
- Produces in `agentmap.py`:
  - `pointer_block() -> str` — `POINTER_BEGIN + POINTER_BODY + POINTER_END`.
  - `pointer_state(text: str) -> str` — one of `"missing"` (no markers), `"current"` (block equals the template), `"stale"` (markers present, content differs), `"broken"` (exactly one marker or END before BEGIN).
- Produces in `link_cmd.py`: `cmd_link(cwd: str | Path | None = None, dry_run: bool = False) -> int`; `TARGETS = ("AGENTS.md", "CLAUDE.md", "GEMINI.md")`.
- Produces in `commands.py`: `_pointer_notices(root: Path) -> list[str]` used by `_verify`.

Behavior of `cmd_link` (in this order; any refusal prints one line, returns 1, writes nothing):
1. `root = gitview.repo_root(cwd)`; None -> `not a git repository`.
2. `docs/wiki/index.md` must be a regular file, and `docs`/`docs/wiki` not symlinks -> else `run vibe wikify init first`.
3. Targets: `AGENTS.md` always; `CLAUDE.md`, `GEMINI.md` only if `os.path.lexists`. For each target: refuse if symlink, not a regular file, resolved path outside `root`, listed by `gitview.ignored(root, [name])`, larger than 256 KiB, or not valid UTF-8; refuse if `pointer_state(existing) == "broken"` with `hand-edited wikify:pointer markers in <name>; fix or remove them`.
4. Compute `merged, action = marked_section_strategy(POINTER_BODY, existing, POINTER_BEGIN, POINTER_END)` — note the template argument is the body only; the markers are passed separately. Preserve the file's line ending style: if the existing text uses `\r\n` throughout, convert the block's `\n` to `\r\n` before merging.
5. Print a unified diff (`difflib.unified_diff`, `a/<name>` `b/<name>`) per changed file; print `unchanged <name>` for `action == "unchanged"`. `--dry-run`: print `dry run: no files written`, return 0.
6. Else backup then write each changed file: backup path `<git-dir>/wikify-backups/<UTC timestamp>/<name>` where `<git-dir>` comes from `git rev-parse --absolute-git-dir` (never inside the working tree; do NOT use `installer_core.backup`, which would create `backups/` inside the repo); write with an exclusive temp file + `os.replace` in the same directory (no partial writes; keep file mode via `shutil.copymode`).
7. Print `linked <name>` and, last: `Next: commit these files on their own, before running vibe wikify mark (they are outside docs/wiki, so they must not share the docs commit).`

`verify` pointer notices (read-only, never affect rc; any OSError -> skip silently): for each existing regular non-symlink target, `pointer_state`: `stale` -> `POINTER STALE: <name> (run vibe wikify link)`; `broken` -> `POINTER BROKEN: <name> has unmatched wikify:pointer markers`; if `AGENTS.md` exists or is absent and no target is `current` and `docs/wiki/index.md` exists -> `POINTER MISSING: run vibe wikify link so agents find the map`; if a target is `current` but `docs/wiki/index.md` is missing -> `POINTER DANGLING: <name> points at docs/wiki/index.md, which does not exist`.

- [ ] **Step 1: Write failing tests** (`tests/test_wikify_link.py`; build temp git repos with the helper pattern from `tests/test_wikify_state.py`; run `init` via `init_cmd.cmd_init(root)` so `index.md` exists; capture stdout with `contextlib.redirect_stdout`):
  1. No `AGENTS.md`: created, content equals `pointer_block()`; rc 0; `CLAUDE.md`/`GEMINI.md` NOT created.
  2. Existing `AGENTS.md` with user text: user text preserved byte-for-byte after the block; running again prints `unchanged AGENTS.md`, file bytes identical (idempotent).
  3. Existing `CLAUDE.md` gets the block; absent `GEMINI.md` not created; existing `GEMINI.md` gets it.
  4. Stale block (edit template text inside markers) updated in place, text outside untouched.
  5. `--dry-run` writes nothing and prints a diff.
  6. Refusals (rc 1, victim untouched): `AGENTS.md` is a symlink to a temp victim file; `.gitignore` containing `AGENTS.md`; target > 256 KiB; non-UTF-8 bytes; only one marker present; index.md missing (no init); outside a git repo.
  7. CRLF `AGENTS.md`: block written with `\r\n`, no mixed endings.
  8. Backup: after a real change, `<repo>/.git/wikify-backups/*/AGENTS.md` exists with the old bytes and the working tree has no `backups/` directory (`git status --porcelain` shows only the intended files).
  9. `link` never modifies `.wikify.json` or anything under `docs/wiki/`.
  10. `verify` notices: no pointer -> `POINTER MISSING`; after `link` -> no pointer notice; stale -> `POINTER STALE`; broken -> `POINTER BROKEN`; rc unchanged (0) in all cases on an otherwise clean wiki.
  11. `agentmap.pointer_state` table test for `missing/current/stale/broken` (including END-before-BEGIN and two blocks -> `broken`).
  Also `tests/test_cli_contract.py`: `wikify --help` fixture updated; new `wikify link --help` fixture + test method (follow the existing pattern).

- [ ] **Step 2: Run to verify failure** — `... python3 -m unittest tests.test_wikify_link` → ImportError / failures.

- [ ] **Step 3: Implement.** Add to `agentmap.py`:

```python
def pointer_block() -> str:
    return POINTER_BEGIN + POINTER_BODY + POINTER_END


def pointer_state(text: str) -> str:
    begins, ends = text.count(POINTER_BEGIN), text.count(POINTER_END)
    if begins == 0 and ends == 0:
        return "missing"
    if begins != 1 or ends != 1 or text.index(POINTER_END) < text.index(POINTER_BEGIN):
        return "broken"
    start = text.index(POINTER_BEGIN)
    block = text[start : text.index(POINTER_END) + len(POINTER_END)]
    return "current" if block.replace("\r\n", "\n") == pointer_block() else "stale"
```

`link_cmd.py` implements the numbered behavior above. `cli.py`: under the `wikify` subparsers add `link` with `--dry-run` (`store_true`, help "Show the diff without writing files"); `commands.cmd_wikify` dispatches `link` to `link_cmd.cmd_link(cwd, args.dry_run)`. Regenerate ONLY `tests/fixtures/cli_help/wikify_help.txt` and add `wikify_link_help.txt`, both with the colour-off prefix: `FORCE_COLOR= NO_COLOR=1 PYTHON_COLORS=0 python3 -m agents.cli wikify --help > tests/fixtures/cli_help/wikify_help.txt` (and `... wikify link --help > ...wikify_link_help.txt`); `git diff` on `wikify_help.txt` must only add the `link` entry.

- [ ] **Step 4: Run to verify pass** — `... python3 -m unittest tests.test_wikify_link tests.test_wikify_agentmap tests.test_wikify_cli tests.test_cli_contract`, then the full suite (all OK).

- [ ] **Step 5: Commit**

```bash
git add agents/wikify/link_cmd.py agents/wikify/agentmap.py agents/wikify/commands.py agents/cli.py tests/test_wikify_link.py tests/test_cli_contract.py tests/test_wikify_cli.py tests/fixtures/cli_help/wikify_help.txt tests/fixtures/cli_help/wikify_link_help.txt
git commit -m "feat(wikify): link command writes the agent-map pointer block

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---
### Task 4: Protocol, init hint and README

**Files:**
- Modify: `agents/kits/wikify/templates/wikify/WIKIFY.md`, `agents/wikify/init_cmd.py`, `README.md`
- Test: `tests/test_wikify_init.py`, `tests/test_wikify_cli.py` (template phrase pins)

**Interfaces:** consumes `vibe wikify link` (Task 3), the map grammar (Task 1).

- [ ] **Step 1: Write failing tests**
  - `init` output ends with a line containing `vibe wikify link`; a fresh init still verifies rc 0 and scans clean (R2): the new WIKIFY.md text must contain no email, home path or key-like assignment.
  - A test pins these phrases in WIKIFY.md: `<!-- wikify:map -->`, `em dash`, `60 entries`, `vibe wikify link`, `never edit AGENTS.md`, `plain links`.
- [ ] **Step 2: Run to verify failure.**
- [ ] **Step 3: Implement.**
  - WIKIFY.md: add a "Map" section (<= 25 lines) covering: the map block lives in `docs/wiki/index.md`; entry grammar with an em dash; one line per page, hint says WHEN to load the page; every page must appear; caps (60 entries / 6 KiB); plain links only, never `@` imports (Claude Code expands them at launch); the agent adds entries after creating pages and `plan` lists `map_missing`; the agent never edits `AGENTS.md`/`CLAUDE.md`/`GEMINI.md` — only the user runs `vibe wikify link`, and those files are committed separately before `mark`. Keep the whole file <= ~140 lines.
  - `init_cmd.cmd_init`: after the file loop print `next: run vibe wikify link to add the agent-map pointer to AGENTS.md`.
  - README: add to the wikify section: the map format, `vibe wikify link [--dry-run]`, the commit-separately rule, the verified tool facts with dates and sources (Claude Code `@` imports eager, 200-line target, AGENTS.md read only when no CLAUDE.md; Codex 32 KiB chain; Cursor nested AGENTS.md; agents.md nearest wins) marked "as of 2026-10-11", and limitations: the pointer is static, the cap numbers are v1 defaults, no per-directory maps, and `link` is explicit (init does not call it).
- [ ] **Step 4: Run to verify pass** — focused modules, then the full suite.
- [ ] **Step 5: Commit**

```bash
git add agents/kits/wikify/templates/wikify/WIKIFY.md agents/wikify/init_cmd.py README.md tests/test_wikify_init.py tests/test_wikify_cli.py
git commit -m "docs(wikify): agent-map protocol, init hint and README

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---
### Task 5: End-to-end smoke and spec note (no code unless a defect is found)

- [ ] **Step 1:** In a scratch git repo under `$CLAUDE_JOB_DIR/tmp`: `vibe wikify init` -> write one cited page `domain/pay.md` and an `index.md` with a map block listing it -> `vibe wikify verify` (rc 0) -> remove the entry (rc 1, `not reachable`) -> restore -> `vibe wikify link --dry-run` (diff printed, nothing written) -> `vibe wikify link` -> commit `AGENTS.md` alone -> `vibe wikify mark` -> docs-only commit -> hook script allows (rc 0); `AGENTS.md` change after mark does not break freshness of the wiki commit ordering (record observed behaviour). Never touch the real home or the real `~/.claude`.
- [ ] **Step 2:** Append a short "As built" note to `docs/superpowers/specs/2026-10-11-wikify-agent-map-design.md` (backups go to `.git/wikify-backups/`, `link` refusals list, `MAP:`/`POINTER ...` notice texts). Commit `docs(wikify): record agent-map as-built notes`.

## Verification summary
`FORCE_COLOR= NO_COLOR=1 PYTHON_COLORS=0 python3 -m unittest discover -s tests` (baseline 806 + new, all OK); scratch-repo smoke above; `git status` shows no `backups/` directory in the working tree after `link`.

## Self-review (spec coverage)
Map grammar, caps, reachability, opt-in, human-block rule: Tasks 1-2. `plan` map_missing: Task 2. Pointer block, link command, refusals, backup, byte-preservation, no CLAUDE/GEMINI creation: Task 3. `verify` pointer notices (notice-only): Task 3. Freshness/hook untouched: no task edits `state.py` or the hook; Task 3 prints the commit-separately instruction; Task 5 observes it. WIKIFY.md/README/init hint and dated facts: Task 4. Out of scope (B migration, nested AGENTS.md, rewriting user files): not implemented. Known deviation from the spec text: backups go to `.git/wikify-backups/` rather than `installer_core.backup` (which would create `backups/` inside the repo); recorded in Task 5.
