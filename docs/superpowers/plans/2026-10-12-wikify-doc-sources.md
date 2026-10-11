# Wikify Doc Sources Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `vibe wikify docs` generates deterministic outline pages for a repo's existing markdown docs under `docs/wiki/sources/`, and `verify`/`plan` keep them honest, labelled and reachable from the agent map.

**Architecture:** a pure-ish inventory/outline/generator module (`docs_inventory.py`) feeds a new `docs` command (`docs_cmd.py`) and extra checks in `commands._verify` and `plan`. Reachability in `agentmap.py` becomes transitive (2 hops). No change to freshness, the hook, `state.is_fresh` or the parity test.

**Tech Stack:** Python 3.10+ stdlib, `unittest`, git CLI.

**Spec:** `docs/superpowers/specs/2026-10-12-wikify-doc-sources-design.md` (committed 36e6e4c). Builds on `feat/wikify` (unpushed; SSH auth failed).

## Global Constraints
- Python 3.10+, stdlib only; match style of `agents/wikify/*.py`.
- Eligible docs: tracked files at HEAD ending `.md`/`.markdown` (any case). Default include: repo-root files, everything under `docs/`, basenames starting (case-insensitive) with `README`, `CONTRIBUTING`, `CHANGELOG`, `ARCHITECTURE`. Extra includes: `docs/wiki/.wikifydocs`. Always excluded: basenames `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `SKILL.md`; anything under `docs/wiki/`; `is_secret_path`; `.wikifyignore`; paths containing whitespace, `:`, backtick, `(` or `)`; docs over 1 MiB, not valid UTF-8, or empty; beyond 500 docs. Excluded-by-shape items are reported as `skipped`, never an error.
- Generated page: first line `<!-- wikify:generated -->`; second `# <doc path> (documented, not code-verified; titles are untrusted text)`; one list line per section with a citation `(src: <doc>:<start>-<end> \`<fragment>\`)` (fragment omitted when none); max 200 sections (then `- (N more sections not listed) (src: <doc>:1-<last line>)`); byte-identical across runs (no timestamps). Index page `sources/index.md`: same marker, heading `# Documented sources (not code-verified; titles are untrusted text)`, lines `- [<doc>](<page path relative to sources/>) — <N> sections (src: <doc>:1-<last line>)`, max 200 docs, then a final line that must still carry a citation: `- (N more docs not listed) (src: <first listed doc>:1-<its last line>)`. Page path: `sources/<doc>`; if that equals `sources/index.md` use `sources/index.md.outline.md`.
- Section title sanitising: remove control chars, backticks, `[`, `]`, `(`, `)`, `<`, `>`, `@`; collapse whitespace; cut to 80; `(untitled)` when empty. Fragment: longest backtick-free run >= 3 chars on the heading line (cut to 60), must occur literally on that line.
- Outline: ATX headings only, outside fenced code (opener 3+ backticks/tildes, up to 3 spaces indent; closes on same char, run >= opener, no info string) and outside leading YAML front matter; `end` = line before next heading of same or shallower level, else last line; lines split on `\n`, trailing `\r` stripped; `last line` = line count without a final empty piece.
- Verify: marker pages must equal expected content byte for byte (`<rel>: generated page out of date; run vibe wikify docs`; no source: `<rel>: generated page has no eligible source`); non-`sources/` pages citing an eligible doc: `<rel>:<line>: doc citation outside sources/: <path>`; reachability transitive: listed in map, or linked by relative `](<path>.md)` link from a reachable page, up to 2 hops, links resolved against the page directory and kept inside `docs/wiki/`.
- Command `vibe wikify docs [--dry-run]`: writes only under `docs/wiki/sources/`; refuses (rc 1, nothing written) on symlinked `docs`/`docs/wiki`/`sources`, unsafe wiki path, or a destination that is a symlink, not a regular file, or an existing page WITHOUT the marker; stale generated pages listed, never deleted; originals never opened for writing.
- Control file `docs/wiki/.wikifydocs` (comment-only scaffold) is added to `citations.CONTROL_FILES`, `state.CONTROL_RELS` and `init`.
- Test commands: prefix `FORCE_COLOR= NO_COLOR=1 PYTHON_COLORS=0`; full suite `python3 -m unittest discover -s tests` (baseline 941 OK).
- Commits: Conventional Commits scope `wikify`; trailer `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`; commit explicit paths, never `.superpowers/`.

## Rulings made while planning
- R1 The generated marker line is not a citeable paragraph and the spec's header prose would be an uncited paragraph. Fix: put the provenance note inside the heading (headings are exempt) and have `commands._verify` blank the marker line before `verify_page` for pages whose first line is the marker. No change to `citations._uncited`.
- R2 Generated headings contain the doc path; paths are citable by construction (whitespace, `:`, backtick, parentheses excluded).
- R3 A heading that carries an email or key-like text is scanned like any page text: the secret scan can fail a generated page; users resolve via `.wikify-allow` or `.wikifyignore`. Not special-cased.
- R4 `agentmap.validate_map` gains an optional keyword `reachable: set[str] | None = None` (None keeps the old "listed only" behaviour, so existing tests stay valid).

## Review Focus
1. Hostile heading text (ESC, `@`, `<`, `](x)`, backticks, 500 chars, a heading that contains `(src: other.md:1-2)`) cannot inject a citation, markup or control characters into a generated page — Task 2.
2. A hand-written page already at a generated destination is never overwritten — Task 3.
3. Doc edited after generation: `verify` errors and `plan` lists `docs_stale`; regeneration then passes; the push gate is unchanged — Tasks 4-5.
4. Doc deleted, renamed or made ineligible: generated page reported, never deleted by `docs`, `verify` errors — Tasks 3-5.
5. Transitive reachability: cycles, self-links, `../` escapes, human-block links, depth 3 rejected — Task 4.
6. 500 docs / 1 MB doc timing; verify with many eligible docs stays fast — Tasks 2, 5.

---
### Task 0: Plan committed
- [ ] `git add docs/superpowers/plans/2026-10-12-wikify-doc-sources.md && git commit -m "docs(wikify): add doc-sources implementation plan"` (with the trailer).

### Task 1: Eligible-doc inventory
**Files:** Create `agents/wikify/docs_inventory.py`; Test `tests/test_wikify_docs.py`.
**Consumes:** `gitview.tracked_files(root) -> list[str]`, `gitview.show_head(root, rel) -> str | None` (invalid UTF-8 comes back with U+FFFD replacement characters), `citations.load_ignore(root) -> list[str]`, `citations.is_ignored(path, globs) -> bool` (fnmatch + directory-prefix matcher; reuse it for `.wikifydocs` includes), `secret_policies.is_secret_path`.
**Produces:**
```python
INCLUDES_REL = "docs/wiki/.wikifydocs"
MAX_DOCS = 500; MAX_DOC_BYTES = 1 << 20
@dataclass(frozen=True)
class Skip: path: str; reason: str
@dataclass(frozen=True)
class Inventory: docs: list[str]; skipped: list[Skip]      # both sorted by path
def load_includes(root: Path) -> list[str]                  # working tree file; missing -> []; '#' comments, blanks skipped
def inventory(root: Path) -> Inventory
```
Order inside `inventory`: suffix filter -> default-or-include -> hard exclusions (instruction names, `docs/wiki/`, secret, ignored; these are silently excluded, not `skipped`) -> citable-path check (`skipped`, reason `path not citable`) -> read via `show_head` (None -> `unreadable`; empty or no lines -> `empty`; >1 MiB -> `larger than 1 MiB`; contains U+FFFD -> `not valid UTF-8`) -> cap at 500 (`over 500 docs`).
- [ ] Failing table tests on a temp git repo mirroring this repo: root `README.md`, `docs/a.md`, `docs/sub/b.markdown`, `pkg/README.md`, `pkg/CHANGELOG.md`, `agents/kits/x/templates/CLAUDE.md`, `agents/kits/x/skills/s/SKILL.md`, `agents/kits/x/rules/r.md`, `AGENTS.md`, `docs/wiki/index.md`, `docs/my notes.md` (skipped: not citable), `docs/empty.md` (skipped: empty), a 1 MiB+1 doc, a latin-1 doc; `.wikifydocs` include `agents/kits/x/rules/` adds `r.md`; `.wikifyignore` of `docs/a.md` removes it even if included; `.env.md` secret path excluded; UPPER-case `README.MD` accepted; 501 docs -> 500 + `over 500 docs`; deterministic sort.
- [ ] Run -> FAIL; implement; run -> PASS; commit `feat(wikify): inventory of eligible docs`.

### Task 2: Outline and deterministic page generation
**Files:** Modify `agents/wikify/docs_inventory.py`; Test `tests/test_wikify_docs.py`.
**Produces:**
```python
MARKER = "<!-- wikify:generated -->"
MAX_SECTIONS = 200; MAX_INDEX_DOCS = 200
@dataclass(frozen=True)
class Section: level: int; title: str; start: int; end: int; fragment: str
def outline(text: str) -> list[Section]
def page_rel(doc: str) -> str                                # "sources/<doc>" or "sources/index.md.outline.md"
def render_doc_page(doc: str, text: str) -> str              # exact content per Global Constraints
def render_index(rows: list[tuple[str, str, int, int]]) -> str   # (doc, page_rel, n_sections, last_line)
def expected_pages(root: Path) -> tuple[dict[str, str], Inventory]   # keys are page paths relative to docs/wiki, incl. "sources/index.md"
```
Rules are in Global Constraints. Doc page list line: `"  " * (level - min_level) + "- " + title + " (src: " + doc + ":" + start + "-" + end + (" `" + fragment + "`" if fragment else "") + ")"`. Heading `#` count is the level. Duplicate titles are fine (different line ranges).
- [ ] Failing table tests: simple doc (exact expected bytes); nested levels and `end` computation (same/shallower heading ends a section, deeper does not); fenced blocks (backtick, tilde, 4-backtick opener containing a ``` line) hide `##` lines; front matter hides `# comment` lines; `#hashtag` is not a heading; setext ignored; CRLF; BOM at start (strip for matching, line numbers unchanged); heading with only backticks -> line-range-only citation; fragment longest-run choice and 60 cut; hostile titles: ESC, `@a`, `<img>`, `[x](y)`, a 500-char title, a title containing `(src: other.md:1-2)` — output contains exactly one citation per line and no raw ESC; 201 sections -> 200 lines + the `(N more sections not listed)` line; `page_rel("index.md") == "sources/index.md.outline.md"` and `page_rel("docs/index.md") == "sources/docs/index.md"`; `expected_pages` twice -> identical dict; index lists docs in sorted order with section counts; every generated page, passed through `agents.wikify.citations.verify_page` with its marker line blanked, yields `[]` against a committed repo (round-trip test).
- [ ] Run -> FAIL; implement; run -> PASS; commit `feat(wikify): deterministic doc outline pages`.

### Task 3: `vibe wikify docs` command and `.wikifydocs` control file
**Files:** Create `agents/wikify/docs_cmd.py`; Modify `agents/wikify/commands.py` (`cmd_wikify` dispatch), `agents/cli.py` (`docs` subparser with `--dry-run`), `agents/wikify/citations.py` (`CONTROL_FILES`), `agents/wikify/state.py` (`CONTROL_RELS`), `agents/wikify/init_cmd.py` (scaffold `.wikifydocs`, comment-only), `tests/fixtures/cli_help/wikify_help.txt` (+ new `wikify_docs_help.txt`), `tests/test_cli_contract.py`; Test `tests/test_wikify_docs.py`, `tests/test_wikify_init.py`.
**Produces:** `docs_cmd.cmd_docs(cwd=None, dry_run=False) -> int`.
**Behaviour:** root via `gitview.repo_root`; `state.check_wiki_path(root)` and symlink checks for `docs/wiki/sources`; plan every page (create/update/unchanged by comparing with the working-tree file); refuse before writing when a destination is a symlink / not a regular file / an existing file whose first line is not the marker; print `create|update|unchanged <rel>` and a unified diff with control characters escaped (reuse the escaping approach of `pointer._safe`); write with `O_NOFOLLOW` where available, creating directories; list generated pages under `sources/` that are not in `expected_pages` as `stale <rel>` (never deleted); list `skipped <path>: <reason>`; final line: `Next: review git status --short -- docs/wiki; add one entry for sources/index.md to the map in docs/wiki/index.md if it is missing, then run vibe wikify verify and mark.` `--dry-run` writes nothing and says so. Missing `docs/wiki/index.md` -> rc 1 `run vibe wikify init first`.
- [ ] Failing tests: creates pages and index on a fixture repo, originals byte-identical (hash compare); rerun -> all `unchanged`, no writes; doc edited and committed -> `update`; ineligible-now doc -> `stale`, file kept; hand-written `sources/docs/a.md` without marker -> rc 1, nothing written; symlinked `sources` / destination -> rc 1; `--dry-run` writes nothing and creates no `sources/` dir; not a repo -> rc 1; init scaffolds `.wikifydocs` (6 files now: update the "five files" expectations and WIKIFY-template tests only where they assert that count); `.wikifydocs` is not reported as a stray file by `verify`; `.wikifydocs` gitignored -> `ignored_control_files` error; help fixtures: only `docs` added.
- [ ] Run -> FAIL; implement; regenerate ONLY `wikify_help.txt` and new `wikify_docs_help.txt` with the colour-off prefix; run `tests.test_cli_contract` + full suite; commit `feat(wikify): docs command writes doc outline pages`.

### Task 4: Transitive reachability
**Files:** Modify `agents/wikify/agentmap.py`, `agents/wikify/plan.py` (`_map_missing`), `agents/wikify/commands.py` (`_verify` passes `reachable`); Test `tests/test_wikify_agentmap.py`, `tests/test_wikify_plan.py`, `tests/test_wikify_cli.py`.
**Produces:**
```python
LINK = re.compile(r"\]\(([^)\s#]+\.md)(?:#[^)\s]*)?\)", re.I)
def page_links(page_rel: str, text: str) -> set[str]         # resolved against dirname(page_rel); masks human blocks; drops absolute, ':'-containing, and anything that escapes docs/wiki
def reachable_pages(listed: set[str], texts: dict[str, str], depth: int = 2) -> set[str]   # BFS from `listed`; result includes `listed`
def validate_map(block, pages, reachable: set[str] | None = None) -> list[str]   # orphan rule uses `reachable` when given
```
`listed` = entry paths of the map; traversal reads `texts[rel]` only for known pages; cycles terminate; `index.md` is never added as a target.
- [ ] Failing tests: hop 1 and hop 2 pages reachable, hop 3 not; cycle a<->b terminates; self-link; link with `../x.md` escaping wiki dropped; absolute and `http://x/a.md` dropped; `#anchor` suffix stripped; link inside a human block ignored; relative link from `sources/index.md` to `docs/a.md` resolves to `sources/docs/a.md`; case: link to a page not in `pages` ignored; `validate_map` without `reachable` keeps old behaviour (existing tests pass untouched); verify: map lists only `sources/index.md`, which links 60+ pages -> no orphan errors; plan `map_missing` honours the same rule.
- [ ] Run -> FAIL; implement; run focused + full suite; commit `feat(wikify): transitive reachability for the agent map`.

### Task 5: verify and plan integration for doc sources
**Files:** Modify `agents/wikify/commands.py` (`_verify`), `agents/wikify/plan.py` (`build_plan`, `render`), `agents/wikify/docs_inventory.py` (add `status`); Test `tests/test_wikify_cli.py`, `tests/test_wikify_plan.py`, `tests/test_wikify_docs.py`.
**Produces:** `docs_inventory.status(root, texts: dict[str, str]) -> dict` with `unindexed: list[str]` (eligible docs whose page is absent), `stale: list[str]` (marker pages that differ from expected or have no eligible source), `skipped: list[dict]` (`{"path", "reason"}`); plan keys `docs_unindexed`, `docs_stale`, `docs_skipped` always present, rendered after `map_missing`.
**`_verify` additions (spec "Verify additions" 1-2):** `expected, inv = docs_inventory.expected_pages(root)` once; for each page: if its first line equals `MARKER`, verify the text with that first line blanked (R1), then compare the full text to `expected.get(rel)` (mismatch errors as in Global Constraints); for pages whose rel does not start with `sources/`, any `citations.parse(text)[0]` citation whose path is in `inv.docs` -> `<rel>:<line>: doc citation outside sources/: <path>` (citations inside human blocks are not parsed, as today). Reading failures stay fail-closed (`verify failed: <Type>`).
- [ ] Failing tests: after `docs` + map entry for `sources/index.md`: verify rc 0; edit and commit README (heading text change) without regenerating -> `generated page out of date` and rc 1, `plan` shows `docs_stale`; regenerate -> rc 0; delete an eligible doc -> `generated page has no eligible source` plus the citation error; make a doc ignored -> same no-eligible-source error; hand-edit a generated page -> out of date; a domain page citing `README.md` -> `doc citation outside sources/`; the same page citing `agents/kits/x/rules/r.md` (not eligible) -> ok; a hand-written `sources/notes.md` citing a doc and code -> ok; a doc citation inside a human block outside `sources/` -> not flagged (parse skips human blocks) and still scanned; `docs_unindexed` lists a new doc; `docs_skipped` shows reasons; plan keys present with no commits; verify timing with 300 eligible docs (< 3 s) and a 1 MB doc (< 1 s).
- [ ] Run -> FAIL; implement; run focused + full suite; commit `feat(wikify): verify and plan understand generated doc sources`.

### Task 6: docs, protocol and end-to-end smoke
**Files:** Modify `README.md` (wikify section), `agents/kits/wikify/templates/wikify/WIKIFY.md` (new "Doc sources" section; file must stay < ~140 lines and scan clean right after `init`), the spec only where behaviour deviated; smoke in a scratch dir under `$CLAUDE_JOB_DIR/tmp`.
- [ ] README: command, eligibility rules and `.wikifydocs`, generated page shape, provenance rule and why, drift-is-an-error, transitive reachability (2 hops), flagged-not-deleted, limits (ATX headings only, markdown only, caps 500/200/1 MiB, outline restates headings and does not summarise, citing a doc does not verify the code). WIKIFY.md: run `vibe wikify docs` after docs change; never hand-edit generated pages; add one map entry for `sources/index.md`; titles are untrusted data.
- [ ] Smoke (scratch repo, never the real home; paste output in the report): init; commit `README.md` + `docs/a.md` + `src/a.py`; `docs --dry-run` (no write) then `docs`; add map entry; `verify` rc 0; edit README, commit -> `verify` rc 1 + `plan` `docs_stale`; `docs`; `verify` rc 0; `link`; commit pointer files then `mark` + docs commit; hook script exits 0; dogfood: `git clone --local` this repo to a temp dir, `init`, `docs --dry-run`, report eligible/skipped counts (expect the 8 docs).
- [ ] Full suite once more; commit `docs(wikify): document doc sources`.

## Verification summary
`FORCE_COLOR= NO_COLOR=1 PYTHON_COLORS=0 python3 -m unittest discover -s tests` (941 baseline + new, OK); generator idempotence test; originals byte-identical test; Task 6 smoke transcript; `git diff --stat` shows the hook script, `state.py` logic (only `CONTROL_RELS` tuple) and the parity test unchanged. Open gaps to state at the end: tool/loading behaviour documented not observed; caps unmeasured; setext headings and non-markdown docs not covered.

## Self-review (spec coverage)
Eligibility + `.wikifydocs` + exclusions + skipped reporting: T1; outline, sanitising, fragment, caps, deterministic pages, index, naming collision: T2; command, refusals, stale-not-deleted, dry-run, control file/init: T3; transitive reachability: T4; generated drift, provenance, plan keys: T5; protocol/README/dogfood/e2e: T6; freshness untouched: verification summary; safety (untrusted titles, no network/LLM, originals never written): T2/T3; out of scope items: not in plan. Spec's "header prose" is realised inside the heading (R1).
