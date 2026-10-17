---

description: "Task list for Wikify Sync and Drift Checks"
---

# Tasks: Wikify Sync and Drift Checks

**Input**: Design documents from `/docs/specs/002-wikify-sync-drift/`

**Prerequisites**: plan.md, spec.md, research.md (D1-D10), data-model.md, contracts/cli.md, quickstart.md

**Tests**: INCLUDED. Constitution Principle IV requires a failing `unittest` first (red, green, refactor). Each
story lists its tests before its implementation; run each test and watch it fail before implementing.

**Organization**: Tasks are grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1..US7, matching spec.md
- Paths are repo-relative. Run tests with `python3 -m unittest tests.<module>`; full suite
  `python3 -m unittest discover -s tests`.

## Path Conventions

Single Python package: source in `agents/wikify/`, kit in `agents/kits/wikify/`, tests in `tests/`
(helpers: `tests/test_wikify_hook.py:RepoCase`, `tests/wikify_adopt_helpers.py`).

---

## Phase 1: Setup

**Purpose**: Shared fixtures and module skeletons

- [X] T001 Create shared test helper `tests/wikify_drift_helpers.py` with a `DriftCase(RepoCase)` that builds a temp git repo with `docs/wiki/{index.md,.wikify.json}`, one cited code file (e.g. `app/svc.py` with a function `handle` at lines 10-20), a page citing it as `(src: app/svc.py:10-20 \`handle\`)`, and helpers `commit()`, `insert_lines_above()`, `tree_hash()` (sha256 of `git status --porcelain` + `git diff` + file bytes under the work tree) for the read-only assertion
- [X] T002 [P] Create empty-module skeletons with docstrings stating the module ceiling: `agents/wikify/drift.py`, `agents/wikify/reanchor.py`, `agents/wikify/imported.py`, `agents/wikify/imported_refs.py`, `agents/wikify/check_cmd.py`, `agents/wikify/hookinstall.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: State round-tripping, hashing, HEAD page reading, and CLI plumbing every story needs

**CRITICAL**: no user story work before this phase is complete

- [X] T003 Write failing tests in `tests/test_wikify_state.py`: `state.load` returns `citations`, `imported`, `imported_mode` when present and defaults when absent or mistyped (`imported_mode` not in {`editable`,`frozen`} -> `editable`); `state.save(root, head, citations=None, imported=None)` preserves existing `citations`/`imported`/`imported_mode` and unknown keys when the new args are `None`; written JSON uses sorted keys, one key per line, `version` stays `1`
- [X] T004 Implement key-preserving `load`/`save` in `agents/wikify/state.py` per data-model.md (version stays `1`; default `{"version":1,"covered":None,"citations":{},"imported":{},"imported_mode":"editable"}`); keep `check_wiki_path` semantics; make T003 pass; confirm `tests/test_wikify_state.py` and `tests/test_wikify_cli.py` still pass
- [X] T005 [P] Write failing tests in `tests/test_wikify_drift.py` for `drift.range_hash(lines, start, end)` (12 hex of sha256 over the `\n`-joined `citations.split_lines` lines; `\r` stripped so CRLF and LF hash equal), `drift.citation_key(page, cite)` (`"<page>|<path>:<start>-<end>|<symbol-or-empty>"`), and `drift.find_windows(lines, length, hash)` returning all start lines of windows whose hash equals (exactly-one, zero, and several-match cases)
- [X] T006 Implement `range_hash`, `citation_key`, `find_windows` in `agents/wikify/drift.py` using a per-line hash list and a window scan that is O(file length); cap file size at 1 MiB (reuse `adopt_refs.MAX_FILE_BYTES` value) and return "too large" as a distinct result; make T005 pass
- [X] T007 [P] Write failing tests in `tests/test_wikify_drift.py` for `drift.read_pages(root, at_head)` returning `{page_rel: text}`: working-tree mode reuses `citations.walk_wiki`; HEAD mode reads via `git ls-tree -r HEAD docs/wiki` + `gitview.show_head`, skips control files and non-`.md`, so a dirty working tree never changes the HEAD result
- [X] T008 Implement `drift.read_pages` and a `drift.read_state(root, at_head)` (HEAD mode parses `git show HEAD:docs/wiki/.wikify.json`) in `agents/wikify/drift.py`; add `gitview.ls_tree_names(root, rel)` and `gitview.log_names_since(root, base)` (one `git log --format=%h --name-only base..HEAD` call, capped, `None` on error) in `agents/wikify/gitview.py` with tests in `tests/test_wikify_state.py`-style temp repos; make T007 pass
- [X] T009 Add `Citation` listing helper `drift.page_citations(text)` wrapping `citations.parse(text)[0]` in `agents/wikify/drift.py` (human blocks excluded as today) and a `drift.MAX_FILE_BYTES` constant; no behaviour change to `citations.py`

**Checkpoint**: state round-trips new keys; hashing/relocation primitives and HEAD/work-tree readers exist

---

## Phase 3: User Story 1 - Page-level drift detection (Priority: P1) MVP

**Goal**: read-only `vibe wikify check [--ci] [--json]` classifying moved/changed/missing/uncovered with commits and notices

**Independent Test**: fixture with a shifted range, a changed body, a deleted symbol and a new uncovered file; each is reported against the right page and category; tree hash unchanged; two runs give identical output

### Tests for User Story 1 (write first, confirm failing)

- [X] T010 [P] [US1] In `tests/test_wikify_drift.py` add `classify` tests: unchanged hash -> clean; **small shift where the symbol is still inside the old range** -> `moved` (new start/end), not `changed`; large shift -> `moved`; edited body -> `changed`; deleted symbol in existing file -> `missing`; deleted file -> `missing`; duplicated body (two window matches) -> `changed` with reason `ambiguous: 2 matches`; no stored hash + symbol in range -> clean + `no range hash yet` notice; no stored hash + symbol outside range -> `changed`; a non-UTF-8 cited file and a CRLF file are handled deterministically without crashing
- [X] T011 [P] [US1] In `tests/test_wikify_check_cmd.py` add CLI tests via `commands.cmd_wikify`/`check_cmd.run_check`: exit 0 when clean or only `moved`/`uncovered`/notices; exit 1 on any `changed` or `missing`; exit 1 and `error` set when an internal exception is injected (fail closed); commits attributed (short hashes of commits touching the cited path since the base); `uncovered_areas` lists a `plan._contexts` context no page cites and never fails the run; `counts.unbaselined_changed` counts hashless citations whose path changed since the base; a repo never marked reports "no baseline" distinctly and exits 0; detached HEAD and an unborn branch give a clear message, exit 0, no crash
- [X] T012 [P] [US1] In `tests/test_wikify_check_cmd.py` add: `check` leaves `tree_hash()` unchanged and two runs print identical output; `--ci` reads pages and state at HEAD (a dirty uncommitted page edit does not change the verdict); `--json` output validates against the schema in contracts/cli.md (use the `validate` helper from `tests/wikify_adopt_helpers.py`); page and token text is sanitised like `pointer._safe`; no secret-scan rule text is ever printed (reuse the `tests/test_wikify_scan.py` secret fixture)

### Implementation for User Story 1

- [X] T013 [US1] Implement `drift.classify(root, pages, state, tracked, ignore)` in `agents/wikify/drift.py` per research D2 (hash present: equal -> clean, else window search first; no hash: symbol-in-range rule; always apply `citations._check`'s path-shape/secret/ignored/wiki-self rules and report those as `missing` with the reason text); returns `DriftFinding` dataclasses (fields per data-model.md) and the list of `no range hash yet` citations; make T010 pass; for a deleted file the pages reported `missing` equal `plan.build_plan(...)['stale_deleted']` (add the regression test in `tests/test_wikify_plan.py`)
- [X] T014 [US1] Implement commit attribution and `unbaselined_changed` in `agents/wikify/drift.py` using `gitview.log_names_since` and `state.base` (base `None` -> full mode, no commits listed, message `no base commit`); degrade with a notice on shallow clones or git failure
- [X] T015 [US1] Implement `drift.uncovered_areas(root, changed, pages)` in `agents/wikify/drift.py` per research D2 step 4 (reuse `plan._contexts` and `plan._keep`; named `uncovered_areas`; warn-only)
- [X] T016 [US1] Implement `agents/wikify/check_cmd.py`: `run_check(root, ci=False) -> CheckResult` assembling drift, uncovered areas, notices; text renderer (sections per contracts/cli.md) and `--ci` one-line renderer; `render_json`; whole body wrapped so any exception returns `ok: false` with `error` set (exit 1)
- [X] T017 [US1] Wire `check` in `agents/cli.py` (`--ci`, `--json`) and `commands.cmd_wikify`; add `cmd_check` returning the exit code; make T011/T012 pass
- [X] T018 [US1] Record hashes on `mark`: in `commands.cmd_mark` after a successful verify, compute the `citations` map for all non-generated pages with `drift.range_hash` and call `state.save(root, head, citations=...)`; test in `tests/test_wikify_cli.py` that a second `mark` rebuilds the map and drops stale keys
- [X] T019 [US1] Add `tests/fixtures/cli_help/wikify_check_help.txt` and update `tests/fixtures/cli_help/wikify_help.txt` to match the new parser output (intentional fixture updates per Principle IV); run `tests/test_cli_contract.py`

**Checkpoint**: `vibe wikify check` is usable alone and is the MVP

---

## Phase 4: User Story 2 - Auto-heal moved citations (Priority: P1)

**Goal**: `vibe wikify reanchor [--apply]` and `mark --reanchor`

**Independent Test**: shift a range by fewer lines than its length; dry run shows the rewrite and changes nothing; `--apply` changes only the digits and re-keys the state entry; `check` and `verify` pass afterwards

### Tests for User Story 2

- [X] T020 [P] [US2] In `tests/test_wikify_reanchor.py`: dry run prints `page:line: path S-E -> S'-E' \`Symbol\`` and leaves `tree_hash()` unchanged; `--apply` rewrites only the digits inside `(src: ...)` (all other bytes of the page identical), is atomic, and re-keys the `citations` entry with the same hash; ambiguous (two window matches) and changed-body citations are refused with a reason and exit 1; a shift smaller than the range length (symbol still inside the old range) is healed
- [X] T021 [P] [US2] In `tests/test_wikify_reanchor.py`: citations inside human blocks and generated pages (first line `<!-- wikify:generated -->`) are never modified; a symlinked `docs/wiki` is refused via `state.check_wiki_path`; a page with CRLF endings keeps its endings
- [X] T022 [P] [US2] In `tests/test_wikify_cli.py`: `mark --reanchor` heals first, then verify passes and the new hashes are recorded; without `--reanchor` a moved citation still makes `verify`/`mark` fail (unchanged fail-closed behaviour)

### Implementation for User Story 2

- [X] T023 [US2] Implement `agents/wikify/reanchor.py`: `plan(root) -> list[Heal|Refusal]` built from `drift.classify` (`moved` -> Heal, ambiguous/changed-with-hash -> Refusal), `apply(root, plan)` rewriting only `S-E` digits via a regex anchored on the exact `(src: path:S-E ...)` text from `citations.CITE` match spans, skipping human/generated/imported regions (use `citations.human_spans`), atomic write via the temp-file+rename pattern in `adopt_cmd._write_atomic`, then `state.save(..., citations=rekeyed)`; make T020/T021 pass
- [X] T024 [US2] Wire `reanchor` (`--apply`) in `agents/cli.py` and `agents/wikify/commands.py`; wire `mark --reanchor` in `cmd_mark`; make T022 pass
- [X] T025 [US2] Add `tests/fixtures/cli_help/wikify_reanchor_help.txt` and update `wikify_help.txt`/mark help fixtures as needed

**Checkpoint**: shifted lines no longer require hand edits

---

## Phase 5: User Story 3 - Editable imported pages (Priority: P1)

**Goal**: hash-tracked imported pages, `IMPORTED PAGE EDITED` notice, `migrate-imported`, `imported_mode`, protocol text, `init --update-protocol`

**Independent Test**: register an adopted page, edit it, `verify` prints the notice and exits 0, `mark` clears it; a genuine human block change still gives its notice; `frozen` errors; legacy unregistered wrappers behave as today

### Tests for User Story 3

- [X] T026 [P] [US3] In `tests/test_wikify_imported.py`: `imported.is_imported_shape(text)` true only for a page that is exactly one `adopt_plan` wrapper (reuse `adopt_plan.is_wrapped`/`unwrap`); `imported.page_hash(text)` is 16 hex of sha256; an unregistered wrapper is never treated as imported (no spoofing through the provenance line)
- [X] T027 [P] [US3] In `tests/test_wikify_imported.py`: `verify` on a registered page edited after registration prints `IMPORTED PAGE EDITED: <page>` as a notice, exit 0, and does **not** print `HUMAN BLOCK CHANGED`/`REMOVED` for the wrapper; a second registered edit before `mark` still shows exactly one notice; after `mark` the notice is gone; an unregistered wrapper edit still prints `HUMAN BLOCK CHANGED` (today's behaviour); a genuine human block elsewhere still prints its notice
- [X] T028 [P] [US3] In `tests/test_wikify_imported.py`: `imported_mode: "frozen"` makes an edited registered page an error line `IMPORTED PAGE CHANGED (frozen): <page>` (exit 1); an invalid mode value falls back to `editable` with a notice
- [X] T029 [P] [US3] In `tests/test_wikify_imported.py`: `migrate-imported` dry run lists wrapped pages and writes nothing; `--apply` writes only `.wikify.json` (the `imported` map), is idempotent, never edits a page, skips non-wrapper pages; `mark` re-records hashes only for pages already registered and never registers new ones; `adopt --apply` registers the pages it creates (extend `tests/test_wikify_adopt.py`); `reanchor --apply` never modifies a registered imported wrapper (needs T023, so this assertion runs after US2)
- [X] T030 [P] [US3] In `tests/test_wikify_cli.py`: `init --update-protocol` dry run reports; `--apply` replaces `docs/wiki/WIKIFY.md` only when its sha256 is in `init_cmd.KNOWN_PROTOCOL_SHA256`; a locally edited file prints `locally edited; not overwritten`; a test enumerates `git log --follow -- agents/kits/wikify/templates/wikify/WIKIFY.md`, hashes every historical blob, and asserts each is in the known list (skips with a clear message when git history is unavailable); only a pristine shipped version is replaced (no backup file: nothing user-owned is lost, and a `.bak` inside `docs/wiki` would fail `verify`)

### Implementation for User Story 3

- [X] T031 [US3] Implement `agents/wikify/imported.py`: `is_imported_shape`, `page_hash`, `registered(state)`, `edited_pages(root, pages, state)`, `register(root, pages, state)`; make T026 pass
- [X] T032 [US3] In `agents/wikify/commands.py` change `_notices`/`_verify`: for pages registered in state, suppress the wrapper's `HUMAN BLOCK CHANGED/REMOVED` and emit `IMPORTED PAGE EDITED` (editable) or the frozen error; keep all other behaviour byte-identical; make T027/T028 pass
- [X] T033 [US3] In `cmd_mark` re-record `imported` hashes for registered pages after a successful verify (extends T018's save call)
- [X] T034 [US3] Implement `migrate-imported` (`--apply`) in `agents/wikify/imported.py` + wiring in `agents/cli.py`/`commands.py`; hook `adopt_cmd.cmd_adopt --apply` to register created pages; make T029 pass; add `tests/fixtures/cli_help/wikify_migrate-imported_help.txt`
- [X] T035 [US3] Implement `init --update-protocol [--apply]` in `agents/wikify/init_cmd.py` with `KNOWN_PROTOCOL_SHA256` built from the real history (run `git log --follow --format=%H -- agents/kits/wikify/templates/wikify/WIKIFY.md` and hash each blob; include the current file); make T030 pass; add the CLI wiring and help fixture
- [X] T036 [US3] Update `agents/kits/wikify/templates/wikify/WIKIFY.md`: imported pages are editable; after editing run `verify` then `mark`; remove "never edit" for imported prose (keep "never rewrite genuine human blocks"); describe `check`, `reanchor`, `sync`, `migrate-imported`, `imported_mode`; fix the squash-merge paragraph (`check` passes, `mark` re-baselines); add `.wikify.json` new-key reference; update the "never edit imported prose" wording in `README.md` and any test asserting protocol text (e.g. `tests/test_wikify_init.py`); leave the historical design docs under `docs/superpowers/specs/` unchanged

**Checkpoint**: imported docs are first-class; protocol text no longer contradicts practice

---

## Phase 6: User Story 4 - Enforcement beyond the agent hook (Priority: P2)

**Goal**: `check --ci` gate, `install-hook`, hook delegating to the CLI with the FR-019 exception, squash handling

**Independent Test**: install the pre-push hook in a fixture repo; a drifting push fails, a clean one passes; a squash-merge history passes `check --ci` and `mark` re-baselines

### Tests for User Story 4

- [X] T037 [P] [US4] In `tests/test_wikify_hookinstall.py`: dry run writes nothing and prints target path + script; `--apply` writes `pre-push` mode `0755` only if absent; refuses when a hook exists, when `core.hooksPath` points elsewhere, when not a git repo, and in a linked worktree resolves via `git rev-parse --git-path hooks`; generated script runs `vibe wikify check --ci` and fails closed when `vibe` is missing
- [X] T038 [P] [US4] In `tests/test_wikify_hook.py` (extend, loading the module as in the existing `load_module`): with a fake `vibe` on `PATH` returning `ok:false` -> block with its per-page text; `ok:true`, `unbaselined_changed:0` -> allow even when the commit-order rule says stale (squash); `ok:true`, `unbaselined_changed>0` and commit-order stale -> block with the "run `vibe wikify mark`" message (FR-019 exception); docs-only commit with a bad citation -> block (no commit-order pre-filter); `vibe` missing / timeout / invalid JSON -> today's behaviour (generic `MESSAGE` on positive staleness); internal hook error -> allow (fail open); all existing hook tests still pass
- [X] T039 [P] [US4] In `tests/test_wikify_check_cmd.py` add the squash-merge fixture (single commit mixing code and `.wikify.json`): `check --ci` exits 0 while `state.is_fresh` is False; `mark` re-baselines; and a second fixture where the squashed commit also changed a cited body -> exit 1
- [X] T040 [P] [US4] In `tests/test_wikify_parity.py` run four fixtures (clean, drifting, squash, unbaselined-changed) through the hook (`wikify_guard.decide`), `check --ci`, and the installed `pre-push` script and assert the same allow/block verdict, except the documented FR-019 case where the hook blocks and `check --ci` passes

### Implementation for User Story 4

- [X] T041 [US4] Implement `agents/wikify/hookinstall.py` (`plan`, `apply`, hooks-dir resolution via `gitview.run_git(root, "rev-parse", "--git-path", "hooks")` and `config core.hooksPath`) and wire `install-hook [--apply]`; make T037 pass; add help fixture `wikify_install-hook_help.txt`
- [X] T042 [US4] Update `agents/kits/wikify/templates/wikify/hooks/vibe-wikify/wikify_guard.py` per research D6: delegate to `vibe wikify check --ci --json` via `shutil.which("vibe")` within the existing `_git` time budget, apply the FR-019 exception, keep `_is_stale` as the fallback, keep fail-open on internal errors, update the module docstring (remove the claim that terminal pushes are out of scope only for the hook; document the CLI delegation); make T038 pass; keep the stdin/exit contract
- [X] T043 [US4] Make T039 pass (verify no commit-order logic leaks into `check`); document the first-push-after-upgrade gap in the migration note (T058)
- [X] T044 [US4] Add `docs/wikify-ci.md` with the GitHub Actions snippet (`vibe wikify check --ci --json`), the plain `pre-push` setup, and the PR-comment design (a CI step posts the `--json` summary; no network inside the CLI); link it from `README.md`

**Checkpoint**: drift is blocked in agent, terminal, and CI paths with one verdict

---

## Phase 7: User Story 5 - Sync workflow and skill (Priority: P2)

**Goal**: `vibe wikify sync` work list and the installed `wikify-sync` skill

**Independent Test**: sync on the multi-drift fixture prints an ordered per-page list and writes nothing; kit install places the skill; the walkthrough ends with a passing check

### Tests for User Story 5

- [X] T045 [P] [US5] In `tests/test_wikify_check_cmd.py`: `sync` prints the work list ordered (moved, changed, missing, uncovered, reference) by (priority, page, line) per contracts/cli.md, includes a reanchor dry-run preview, leaves `tree_hash()` unchanged, and exits with `check`'s verdict
- [X] T046 [P] [US5] In `tests/test_wikify_installer.py` (extend): install writes `skills/wikify-sync/SKILL.md` for Claude Code exactly like `wikify-adopt` (backup when changed, idempotent); `uninstall` removes both unmodified skills and keeps edited ones; `doctor`/`diff` cover the new managed file; manifest lists it; `--dry-run --yes` writes nothing
- [X] T047 [P] [US5] Add `tests/test_wikify_skill_walkthrough.py`: asserts every `vibe wikify ...` command and flag named in `docs/wikify-sync-walkthrough.md` and in `skills/wikify-sync/SKILL.md` exists in the parser, and runs the walkthrough end-to-end on a temp repo (sync -> edit -> verify -> mark -> `check` exits 0)

### Implementation for User Story 5

- [X] T048 [US5] Implement `sync` in `agents/wikify/check_cmd.py` (reuse `run_check` + `reanchor.plan`) with the `WorkItem` list; wire in `agents/cli.py`/`commands.py`; add `wikify_sync_help.txt`; make T045 pass
- [X] T049 [US5] Write `agents/kits/wikify/templates/wikify/skills/wikify-sync/SKILL.md` (frontmatter like `wikify-adopt`; loop: `sync` -> `reanchor --apply` for moved -> read the code behind each changed/missing claim -> edit pages -> `verify` -> `mark` -> show diff -> user confirms -> docs-only commit; never invent facts; report doc-versus-code contradictions as findings; never edit human blocks, generated pages, `.wikifyignore`, `.wikify-allow`; ask before deleting stale pages)
- [X] T050 [US5] Update `agents/kits/wikify/installer.py` (`SKILL_REL` -> `SKILL_RELS` tuple, loops at install/diff/doctor/uninstall incl. `prune_empty_dirs` for both skill dirs), `agents/kits/wikify/templates/wikify/manifest.json` (`managed_files`, version `0.2.0`, description) and `MANIFEST.in` if needed; make T046 pass; run `tests/test_kit_contract.py`
- [X] T051 [US5] Write `docs/wikify-sync-walkthrough.md` (checked by T047) and link it from `README.md`

**Checkpoint**: one command plus a skill drives the sync loop

---

## Phase 8: User Story 6 - Reference checks for imported prose (Priority: P3)

**Goal**: report-only `DEAD PATH` / `DEAD SYMBOL` / `STALE LINK` plus `fix-links`

**Independent Test**: delete a file an imported doc cites; `check` lists `DEAD PATH`, exit unchanged; `fix-links` rewrites only `.wikifymap`-mapped paths

### Tests for User Story 6

- [X] T052 [P] [US6] In `tests/test_wikify_imported.py`: references are extracted from every `adopt_plan.is_wrapped` page's wrapper body, registered or not (read-only); backticked path-shaped token not in `git ls-files` -> `DEAD PATH`; identifier-shaped token found in no tracked text file (whole-word, files over 1 MiB and secret/ignored paths skipped) -> `DEAD SYMBOL`; relative link to a missing page or file -> `STALE LINK`; findings never change the exit code; output carries the "name-only matching is a floor, not proof" line; fenced code ignored; deterministic ordering; call-count (not wall-clock) perf test that tracked files are read once regardless of token count
- [X] T053 [P] [US6] In `tests/test_wikify_imported.py`: `fix-links` dry run prints the rewrites and writes nothing; `--apply` rewrites only `DEAD PATH` tokens whose old path is a source in `.wikifymap`, only inside registered imported pages, using `adopt_refs.rewrite_links`-style safe replacement, never touches unregistered wrappers or genuine human blocks; next `mark` re-records the page hash; `fix-links --apply` on an unregistered wrapper refuses with a hint to run `migrate-imported`

### Implementation for User Story 6

- [X] T054 [US6] Implement `agents/wikify/imported_refs.py` (`find_refs(root, pages, state, tracked)`; one pass builds the word set from tracked text files) and integrate findings into `check_cmd.run_check`; make T052 pass
- [X] T055 [US6] Implement `fix-links [--apply]` (reuse `adopt_map` mapping parse) + wiring + `wikify_fix-links_help.txt`; make T053 pass

**Checkpoint**: stale prose references are visible

---

## Phase 9: User Story 7 - Map and layout hygiene (Priority: P3)

**Goal**: non-failing cap warnings and grouping suggestions

**Independent Test**: map above 80% of 6144 bytes or 60 entries -> `check` warns, exit unchanged; `sync` suggests grouping

### Tests and implementation

- [X] T056 [P] [US7] In `tests/test_wikify_agentmap.py`: new `agentmap.cap_usage(block)` returns (entries/60, bytes/6144) ratios; `check` prints `NOTICE: map at 80%+ of ...` only at >= 0.8 of either cap and never changes the exit code; `sync` suggests `group docs/wiki/<folder>/ (N entries) under <folder>/index.md` for folders with >= 5 direct entries and creates nothing
- [X] T057 [US7] Implement `agentmap.cap_usage` in `agents/wikify/agentmap.py` and the notice/suggestion rendering in `agents/wikify/check_cmd.py`; make T056 pass

---

## Phase 10: Polish and Cross-Cutting Concerns

- [X] T058 [P] Write the migration note in `docs/wikify-migration.md` and link it from `README.md`: new optional `.wikify.json` keys, older `mark` drops them (degrades to "no range hash yet"), run `vibe wikify mark` to record hashes, `migrate-imported --apply` to register the existing adopted docs, `init --update-protocol`, first-push-after-upgrade behaviour (FR-019 exception), CI/pre-push weaker until hashes exist, `imported_mode`
- [X] T059 [P] Add a perf test to `tests/test_wikify_perf.py` (call counts / doubling ratios, no wall clock): `check` makes O(1) `git show` calls per distinct cited file and a single `git log` call regardless of page count; window search scales linearly with file length
- [X] T060 [P] Security pass per Constitution "Development Workflow": confirm untrusted page/token text is sanitised in every new output, new writers refuse symlinks (`state.check_wiki_path`), hook script still never creates files, `install-hook` never overwrites, no secret rule text appears; record findings in the PR description
- [X] T061 [P] In `tests/test_wikify_control_files.py` snapshot the bytes of `docs/wiki/.wikifyignore`, `.wikify-allow`, `.wikifydocs`, generated pages and human blocks before and after `reanchor --apply`, `fix-links --apply`, `migrate-imported --apply`, `install-hook --apply`, `init --update-protocol --apply` and `mark`; assert they are byte-identical (`docs/wiki/.wikify.json` and `WIKIFY.md` excepted where the command owns them)
- [X] T062 Run the quickstart in `docs/specs/002-wikify-sync-drift/quickstart.md` manually on a scratch repo; run `python3 -m unittest discover -s tests`; run `vibe kits wikify install --dry-run --yes`; confirm `tests/test_second_brain_contract.py` is untouched
- [ ] T063 Conventional-commit slices and PR notes: one commit per phase (`feat(wikify): ...`), PR body lists user-visible changes, tests run, and installer safety implications (hook script and skill files written, no network)

---

## Dependencies and Execution Order

- Phase 1 -> Phase 2 -> user stories. Phase 2 blocks everything.
- US1 (check) first; **MVP = Phase 1 + 2 + US1**.
- US2 depends on US1 (`drift.classify`). US3 depends only on Phase 2 (T018/T033 share `cmd_mark`; do T018 first, T033 extends it); its reanchor-exclusion assertion in T029 needs US2's T023.
- US4 depends on US1 (and `state.is_fresh` untouched). US5 depends on US1, US2 (preview). US6 depends on US3 (registered pages) and US1 (output). US7 depends on US1.
- Within a story: tests (fail) -> implementation -> help fixtures.
- Shared-file ordering: `agents/cli.py` and `agents/wikify/commands.py` are touched by US1-US6; apply those wiring tasks sequentially (T017, T024, T034, T035, T041, T048, T055).

## Parallel Examples

- After Phase 2: T010, T011, T012 (US1 tests) in parallel; once US1 is done, US2 (T020-T022), US3 (T026-T030) and US4 (T037-T040) test-writing can proceed in parallel by different people.
- US5 tests T045-T047 and US6 tests T052-T053 are parallel with each other.
- Polish T058-T061 are parallel.

## Implementation Strategy

1. MVP: Phases 1-2 + US1; stop and validate with `check` on a real repo.
2. Add US2 and US3 (both P1) so drift is healable and imported docs editable; this alone resolves four of the six stated gaps.
3. Add US4 (gates) then US5 (sync + skill), then US6/US7 (P3).
4. Land each phase as its own conventional commit; run the full suite at each checkpoint.
