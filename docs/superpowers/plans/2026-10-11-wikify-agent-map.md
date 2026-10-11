# Wikify Agent Map Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use `- [ ]`.
> **Execution method chosen by user: subagent-driven** (fresh implementer + fresh reviewer per task, scoped re-review per fix round, whole-branch review at the end; ledger rulings as in the wikify v1 run).
> **Step 0 of execution:** copy this file to `docs/superpowers/plans/2026-10-11-wikify-agent-map.md` and commit it on `feat/wikify` (plan mode forbids writing there now).

**Goal:** make `docs/wiki/index.md` a verified agent map and add `vibe wikify link`, which writes a small marked pointer block into `AGENTS.md` (and existing `CLAUDE.md`/`GEMINI.md`), so agents load wiki pages on demand instead of a bloated instruction file.

**Architecture:** a pure grammar/validation module (`agentmap.py`) feeds `verify` and `plan`; a separate `pointer.py` owns the pointer template, target discovery, merge (via `merge_strategies.marked_section_strategy`) and the `link` command. No change to freshness (`state.is_fresh`), the hook, or the parity test.

**Tech Stack:** Python 3.10+ stdlib, `unittest`, git CLI.

**Spec:** `docs/superpowers/specs/2026-10-11-wikify-agent-map-design.md` (committed, 758f2b2). Builds on `feat/wikify` (26+ commits, unpushed: SSH auth failed).

## Global Constraints
- Python 3.10+, stdlib only, no new dependencies; match surrounding style (`agents/wikify/*.py`).
- Map entry grammar, verbatim: `- [<title>](<path>.md) — <when-hint>`; separator is space, U+2014, space; title 1-60 chars; hint 1-80 chars, required; neither contains `[`, `]`, `(`, `)` or newline; path relative to `docs/wiki/`, forward slashes, ends `.md` (any case), no `..`, no scheme/colon, no `@`, no backslash, not `index.md`/`WIKIFY.md` at top level.
- Map block delimiters: `<!-- wikify:map -->` / `<!-- /wikify:map -->`; caps: at most 60 entries and 6144 bytes inside the block; at most one block per `index.md`; a block inside a `<!-- wikify:human -->` block is ignored.
- Pointer block delimiters: `<!-- wikify:pointer -->` / `<!-- /wikify:pointer -->`; template is static (no repo-derived content), plain relative links, no `@`, 5 lines.
- Pointer checks in `verify` are notices only (rc unchanged). `link` writes only `AGENTS.md`, plus `CLAUDE.md`/`GEMINI.md` only if they already exist; never creates the latter two.
- `AGENTS.md`/`CLAUDE.md`/`GEMINI.md` text outside the marked block is preserved byte for byte.
- Test commands prefix: `FORCE_COLOR= NO_COLOR=1 PYTHON_COLORS=0` (env has FORCE_COLOR=3). Full suite: `python3 -m unittest discover -s tests` (baseline 806 OK).
- Commits: Conventional Commits, scope `wikify`; trailer `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`; commit explicit paths, never `.superpowers/`.

## Rulings made while planning (confirm at review)
- R1 Backup: `installer_core.backup(path, base)` writes `backups/` **inside the repo**, which would pollute a committed tree. `link` instead copies an existing target to `<git-dir>/wikify-backups/<UTC ts>/<name>` (untracked by construction), via a new `gitview.git_dir(root)`.
- R2 Symlinks: `CLAUDE.md -> AGENTS.md` is a common pattern. A target that is a symlink resolving to another target file inside the repo is skipped with a note (covered by its target); any other symlink, or one resolving outside the repo, makes `link` refuse (rc 1, nothing written).
- R3 `init` writes an empty map block into the new `index.md` so agents see where entries go; existing wikis (no block) get a notice, not an error (opt-in rule).
- R4 Pointer notices are emitted by `verify` only; `plan` stays about pages.

## Review Focus
1. Map path `@x`, `../x`, `/abs`, `http://..`, `a:b.md`, backslash: rejected (eager `@` imports would defeat the goal) — Task 1.
2. Map block in a human block ignored; prose OUTSIDE the block is still an uncited paragraph — Task 2.
3. Existing `AGENTS.md` with CRLF, no trailing newline, or a stale pointer block: bytes outside the block preserved, block updated in place — Task 4.
4. `CLAUDE.md` symlinked to `AGENTS.md`, symlink to elsewhere, gitignored target, missing index — Task 4.
5. `link` followed by mark in the same commit makes the base commit mixed (stale): `link` output must say commit pointer files separately first — Task 4.
6. Orphan page after the agent adds a page but no entry; duplicate entry; entry pointing at a deleted page — Task 2.

---
### Task 0: Plan committed
- [ ] Copy this plan to `docs/superpowers/plans/2026-10-11-wikify-agent-map.md`; `git add` that path; commit `docs(wikify): add agent-map implementation plan`.

### Task 1: Map grammar module (pure)
**Files:** Create `agents/wikify/agentmap.py`; Test `tests/test_wikify_agentmap.py`.
**Produces:**
```python
MAP_BEGIN = "<!-- wikify:map -->"; MAP_END = "<!-- /wikify:map -->"
MAX_ENTRIES = 60; MAX_BYTES = 6144; MAX_TITLE = 60; MAX_HINT = 80
@dataclass(frozen=True)
class Entry: path: str; title: str; hint: str; line: int
@dataclass(frozen=True)
class MapBlock: entries: list[Entry]; errors: list[str]; blocks: int  # errors are "index.md:<line>: <reason>"
def parse_map(text: str) -> MapBlock          # ignores blocks inside wikify:human blocks; line numbers are original
def strip_map(text: str) -> str               # replaces the (first valid-delimited) block with the same number of newlines
def validate_map(block: MapBlock, pages: set[str]) -> list[str]   # pages = rels from citations.walk_wiki
```
Grammar regex (use verbatim): `ENTRY = re.compile(r"^- \[([^\[\]()\n]{1,60})\]\(([^\s()\[\]]+)\) — ([^\[\]()\n]{1,80})$")`; then `_path_error(path)` rejects: leading `/`, `..` segment, `\\`, `@`, `:` anywhere, not ending `.md` (case-insensitive), equal to `index.md`/`WIKIFY.md`.
`parse_map` rules: find blocks after removing human blocks (`citations.HUMAN`; import it, no copy); more than one block -> error `more than one map block`; unterminated begin marker -> error; lines inside: blank allowed, other lines must match ENTRY else error `invalid map entry`; byte cap and entry cap errors (`map exceeds 60 entries`, `map exceeds 6144 bytes`).
`validate_map`: each path must be in `pages` (`link target missing: <path>`), no duplicates (`duplicate entry: <path>`), and when the block exists every page except top-level `index.md` must appear (`page not reachable from the map: <rel>`). A text with no block returns `[]` (opt-in).
- [ ] Write failing table tests (`subTest` per row): valid single entry; 60 entries ok / 61 error; 6144 bytes ok / 6145 error; missing hint; hint 81 chars; title 61 chars; each bad path (`@a.md`, `../a.md`, `/a.md`, `http://x/a.md`, `a:b.md`, `a\\b.md`, `a.txt`, `index.md`, `WIKIFY.md`); parens/brackets in title or hint; wrong dash (`-`, en dash); stray prose line inside block; two blocks; unterminated begin; block inside a human block ignored (entries empty, no error); line numbers correct with a human block above; validate: missing target, duplicate, orphan page, no-block returns []; `strip_map` keeps line count.
- [ ] Run -> FAIL (ImportError); implement; run -> PASS; commit `feat(wikify): agent map grammar and validation`.

### Task 2: verify integration, init, WIKIFY.md map section
**Files:** Modify `agents/wikify/commands.py` (`_verify` ~L43-64), `agents/wikify/init_cmd.py` (`INDEX` L16), `agents/kits/wikify/templates/wikify/WIKIFY.md`; Test `tests/test_wikify_cli.py` (+ `tests/test_wikify_init.py` if INDEX is pinned).
**Consumes:** `agentmap.parse_map/strip_map/validate_map`, `citations.walk_wiki`, `citations.verify_page`.
**Behaviour:**
- In `_verify`, for the top-level page `index.md` only: `block = agentmap.parse_map(text)`; call `citations.verify_page(root, rel, agentmap.strip_map(text), ignore)` (map lines are navigation, exempt from the citation rule; prose outside the block is still checked); extend errors with `block.errors` and `agentmap.validate_map(block, {rel for rel, _ in pages})`.
- When `index.md` has no map block and the wiki has more than the index page: add the notice `NOTICE: docs/wiki/index.md has no wikify:map block; N page(s) are not reachable from a map` (rc unchanged).
- `init_cmd.INDEX = "# Wiki index\n\n<!-- wikify:map -->\n<!-- /wikify:map -->\n"`; init still verifies clean (a fresh wiki scans and verifies rc 0). `cmd_init` also prints one final hint line: `Next: run vibe wikify link to add the agent pointer block to AGENTS.md` (test: printed on first init and on re-init, never writes outside docs/wiki).
- WIKIFY.md: new "Agent map" section (<= 20 lines): the grammar with one example, "add an entry for every page you create", hint = when to load, never use `@`, entries are navigation not claims, caps; keep file scanning clean and total under ~140 lines; update the template test that pins phrases.
- [ ] Failing tests: after `init`, `verify` rc 0; page `a.md` added without entry -> error `page not reachable from the map: a.md`; with `- [A](a.md) — when changing foo` -> rc 0 and no citation error on that line; duplicate -> error; entry to missing page -> error; prose paragraph outside the block in index.md -> `uncited paragraph`; map inside human block -> ignored, no reachability errors for pages (block count 0, notice shown); existing wiki without block + pages -> notice only, rc 0; 61 entries -> error; WIKIFY.md contains the map section text.
- [ ] Run -> FAIL; implement; run focused (`tests.test_wikify_cli tests.test_wikify_init tests.test_wikify_agentmap`) then full suite; fix any exact-output assertions that now see the new notice lines (only update expectations that include the new notice, nothing else); commit `feat(wikify): verify the agent map and scaffold it in init`.

### Task 3: plan reports pages missing from the map
**Files:** Modify `agents/wikify/plan.py` (`build_plan` ~L74-122, `render` ~L125); Test `tests/test_wikify_plan.py`.
**Produces:** plan dict key `map_missing: list[str]` = sorted pages (excluding top-level `index.md`) not listed in the map entries (all pages when there is no block); `render` prints `map_missing (N):` after `uncovered`.
**Consumes:** `agentmap.parse_map`; read `docs/wiki/index.md` from the working tree via `citations.walk_wiki` page list (no new file reads outside the shared walk).
- [ ] Failing tests: no block -> every page in `map_missing`; block listing some pages -> only the rest; no pages -> `[]`; unreadable/absent index -> `[]` and no exception; JSON output includes the key; render line present.
- [ ] Implement; run `tests.test_wikify_plan` + full suite; commit `feat(wikify): plan lists pages missing from the agent map`.

### Task 4: pointer block + `vibe wikify link`
**Files:** Create `agents/wikify/pointer.py`; Modify `agents/wikify/gitview.py` (add `git_dir`), `agents/wikify/commands.py` (`cmd_wikify` dispatch, `_verify` pointer notices), `agents/cli.py` (`link` subparser ~L104-109 with `--dry-run`), `tests/fixtures/cli_help/wikify_help.txt` (+ new `wikify_link_help.txt`), `tests/test_cli_contract.py`; Test `tests/test_wikify_pointer.py`.
**Produces:**
```python
BEGIN = "<!-- wikify:pointer -->\n"; END = "<!-- /wikify:pointer -->\n"
TEMPLATE = ("## Repo docs (wikify)\n"
            "Repo knowledge lives in `docs/wiki/`. Start at [docs/wiki/index.md](docs/wiki/index.md): it is a map.\n"
            "Load only the pages whose \"when\" hint matches your task; do not read the whole wiki.\n")
TARGETS = ("AGENTS.md", "CLAUDE.md", "GEMINI.md")
def plan_link(root: Path) -> tuple[list[Change], list[str]]   # Change(rel, action: create|merge|unchanged, old, new); second value = notes/refusals
def cmd_link(cwd=None, dry_run: bool = False) -> int
def pointer_notices(root: Path) -> list[str]                  # for verify: STALE / BROKEN / none
```
`gitview.git_dir(root) -> Path | None` runs `git rev-parse --absolute-git-dir` (timeout via `run_git`).
**Behaviour (spec + R1/R2):**
- Refuse (rc 1, nothing written, message names repo-relative path): `docs/wiki/index.md` missing; any target that is a symlink resolving outside the repo or to a non-target file; target gitignored (`gitview.ignored`) when it does not exist yet or is untracked-ignored; target resolving outside repo root. A symlink resolving to another target in the repo is skipped with note `CLAUDE.md -> AGENTS.md: covered by its target`.
- Targets: `AGENTS.md` always (created with the block only when absent); `CLAUDE.md`, `GEMINI.md` only if they exist as regular files.
- Merge: `marked_section_strategy(TEMPLATE, existing, BEGIN, END)` from `agents/merge_strategies.py:380`; text outside markers byte-preserved (read/write as bytes-safe: decode utf-8 with `newline=""`-equivalent handling so CRLF survives; if the file is not valid UTF-8, refuse that file).
- Output: for every changed file print `create|update <rel>` and a unified diff (`difflib`); `--dry-run` writes nothing and says so; otherwise before overwriting an existing file copy it to `<git_dir>/wikify-backups/<UTC ts>/<rel>`; write with plain `write_text` (no symlink following: target is verified a regular file or absent).
- Final lines: `Next: commit <changed files> in their own commit (not with docs/wiki), then run vibe wikify mark.` (so the base commit stays docs-only; freshness unchanged).
- `pointer_notices`: for each existing regular target: block present but differs from TEMPLATE -> `POINTER STALE: <rel>; run vibe wikify link`; none of the targets has a block -> `NOTICE: no wikify pointer block in AGENTS.md/CLAUDE.md/GEMINI.md; run vibe wikify link`; `docs/wiki/index.md` missing while a block exists -> `POINTER BROKEN: <rel> points at a missing docs/wiki/index.md`. Never changes rc; never raises (OSError -> skipped note).
- [ ] Failing tests (temp git repos via `tests.test_wikify_state.RepoCase`): no AGENTS.md -> created with block only, rc 0; existing AGENTS.md with user text -> user bytes preserved after the block (compare tail bytes), CRLF file keeps CRLF; re-run -> `unchanged`, no write, no backup; stale block updated in place; existing CLAUDE.md gets block, absent GEMINI.md not created; `CLAUDE.md` symlink to `AGENTS.md` -> skipped note, rc 0; symlink to `/etc/hostname` or `../x` -> rc 1 nothing written; gitignored AGENTS.md (`.gitignore` has `AGENTS.md`) -> rc 1; missing `docs/wiki/index.md` -> rc 1; `--dry-run` writes nothing and prints diff; backup file exists in git dir after a merge and no `backups/` dir appears in the work tree; output contains the commit-separately line; non-UTF-8 AGENTS.md -> refused; `pointer_notices` cases (stale, none, broken, clean -> []); `verify` prints the notices and rc unchanged; parity test file untouched.
- [ ] Run -> FAIL; implement; regenerate ONLY `wikify_help.txt` and new `wikify_link_help.txt` with the colour-off prefix (eyeball diff = only `link` added); run `tests.test_cli_contract` + full suite; commit `feat(wikify): link command writes the agent pointer block`.

### Task 5: docs and end-to-end smoke
**Files:** Modify `README.md` (wikify section), `docs/superpowers/specs/2026-10-11-wikify-agent-map-design.md` (only if a ruling above changed behaviour: R1 backup location, R2 symlink handling, R3 init block); smoke in a scratch dir under `$CLAUDE_JOB_DIR/tmp`.
- [ ] README: document the map block grammar and caps, `vibe wikify link [--dry-run]`, the commit-separately rule, `CLAUDE.md` precedence (Claude Code reads `AGENTS.md` only when no `CLAUDE.md` exists), plain links not `@` (eager import), the notice-only pointer checks; no claims beyond the implementation. Re-verify the cited tool-behaviour facts against the primary docs the spec lists before writing them; date the claim.
- [ ] Spec: amend R1/R2/R3 where they differ from the written spec (backup under the git dir; symlink-to-target skip; init writes an empty block).
- [ ] Smoke: scratch repo `git init`, commit `src/a.py`; `vibe wikify init`; write `docs/wiki/architecture/overview.md` with one citation; add the map entry; `verify` rc 0; remove the entry -> orphan error; `link --dry-run` (no write) then `link`; existing-`AGENTS.md` variant keeps user text; `verify` shows no STALE/none notice; commit pointer files, then `mark`, docs commit; `plan` shows empty `map_missing`; paste output into the report. Full suite once more.
- [ ] Commit `docs(wikify): document the agent map and link command`.

## Verification summary
`FORCE_COLOR= NO_COLOR=1 PYTHON_COLORS=0 python3 -m unittest discover -s tests` (806 baseline + new, all OK); `tests.test_cli_contract` with regenerated `wikify_help.txt`/`wikify_link_help.txt`; Task 5 smoke transcript; confirm `git diff` touches no hook/state files (`agents/kits/wikify/templates/.../wikify_guard.py`, `agents/wikify/state.py`) so freshness parity is untouched. Open verification gaps to state at the end: tool-loading behaviour is documented, not observed live; 60/6144 caps are unmeasured defaults.

## Self-review (spec coverage)
Map grammar/caps/reachability/dup/size/human-block: T1+T2; `plan` map_missing: T3; pointer template, `link`, targets, refusals, marked-section merge, diff/dry-run/backup, commit-separately: T4; verify pointer notices: T4; init hint (spec: init only hints) -> R3 refines: init writes an empty map block and prints a one-line hint to run `link` (add that print to `cmd_init` in Task 2 with a test); no freshness/hook change: verified in verification summary; safety (static text, grammar bans `@`/scheme): T1+T4; B out of scope: not in plan.
