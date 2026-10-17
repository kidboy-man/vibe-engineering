# Tasks: Vibe Kits Baseline (planned delta: `vibe wikify adopt`)

**Input**: Design documents from `/specs/001-vibe-kits-baseline/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/adopt-cli.md, contracts/adopt-report.schema.json, quickstart.md

**Scope note**: User Stories 1-6 are shipped behavior; they need no implementation tasks and are guarded by the
existing suite (`python3 -m unittest discover -s tests`). The only unshipped story is **US7 (doc adoption)**, so all
implementation tasks below carry `[US7]`.

**Tests**: Included. Constitution Principle IV requires a failing `unittest` test before each behavior change.

## Format: `- [ ] [ID] [P?] [Story] Description`

- **[P]**: parallelizable (different files, no dependency on an incomplete task)
- Paths are repo-root relative

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Resolve the open design checks and create fixtures.

- [X] T001 Confirm research.md D1 in source: read `agents/wikify/citations.py` and `agents/wikify/commands.py` and record in `docs/superpowers/specs/2026-10-17-wikify-adopt-design.md` whether (a) large human blocks hit any size cap, (b) headings/links inside human blocks are tolerated, (c) `verify` can report provenance-marked pages separately; state final choice Option A or B with reasons
- [X] T002 [P] Create fixture repo builders (empty docs, flat `docs/`, nested `docs/` with images and relative links, build-coupled file, secret-bearing file) as in-code file maps in the helper (no static tree under `tests/fixtures/adopt/`; the walkthrough lives there) `tests/wikify_adopt_helpers.py` that materializes them into a temp git repo
- [ ] T003 [P] Add a `tests/fixtures/adopt/WALKTHROUGH.md` skeleton describing the agent-driven loop from quickstart.md section 3 (filled in at T030)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared pieces every adopt behavior depends on. No adopt command work starts before this phase.

- [X] T004 Write failing tests in `tests/test_wikify_adopt.py` for mapping-file parsing: `source-glob -> destination-folder/` lines, `#` comments, first-match-wins, rejection over the `.wikifyignore`-style limits (size, pattern count, wildcards per pattern), non-UTF-8 and symlinked file rejected
- [X] T005 Implement mapping parse/render in `agents/wikify/adopt_plan.py` reusing `citations.read_control_lines` and glob compile helpers; make T004 pass
- [X] T006 [P] Write failing test in `tests/test_wikify_citations.py` that `.wikifymap` is a control file reported by `verify` when git ignores it; then add `.wikifymap` to `CONTROL_FILES` in `agents/wikify/citations.py` and `CONTROL_RELS` in `agents/wikify/state.py`
- [X] T007 Write failing tests for candidate classification in `tests/test_wikify_adopt.py`: kinds `spec|adr|reference|asset|skipped` and skip reasons `build-coupled|ignored|secret-path|secret-hit|non-markdown|collision|unmapped` from data-model.md; unique destination; never an existing path; symlinks skipped
- [X] T008 Implement candidate model and classification in `agents/wikify/adopt_plan.py` reusing `docs_inventory.inventory`, `citations.is_ignored`, and the `scan` secret checks (no auto allow-listing); make T007 pass
- [X] T009 Write failing tests for the page wrapper in `tests/test_wikify_adopt.py`: body wrapped verbatim in one `<!-- wikify:human -->` block with first inner line `<!-- imported from=<source> -->`; body SHA-256 recorded before the move equals the hash of the unwrapped inner body; a body that already contains the human end marker is refused as a skip
- [X] T010 Implement the wrapper in `agents/wikify/adopt_plan.py`; make T009 pass (if T001 chose Option B, replace with the page-kind marker design and update tests first)

**Checkpoint**: mapping, classification, and wrapping unit-tested; no command wiring yet.

---

## Phase 3: User Story 7 - Fold existing docs into the wiki (Priority: P3, planned) 🎯 MVP

**Goal**: A developer moves existing markdown into `docs/wiki/` with `vibe wikify adopt`, with no content loss, via a
dry run first and an agent-drivable skill.

**Independent Test**: On each fixture repo run dry run, `--apply`, second `--apply`, `verify`, `mark`, `plan`; moved bodies
are hash-equal, second apply changes nothing, `plan` reports nothing uncovered (SC-009).

### 7a. Dry run and report (FR-017, FR-018)

- [X] T011 [US7] Write failing tests in `tests/test_wikify_adopt.py` for the dry run: prints per file source, destination, kind, skip reason, inbound refs; writes nothing (git status clean, no new files); refuses outside a git repo or without `docs/wiki/index.md` (exit 1)
- [X] T012 [US7] Write failing tests that `--report` output validates against `specs/001-vibe-kits-baseline/contracts/adopt-report.schema.json` (required keys `moves`, `skips`, `unresolved_refs`, `unclassified`, `suggested_contexts`, `commit_plan`; `body_sha256` is 64 lowercase hex) using a small stdlib validator in `tests/wikify_adopt_helpers.py`
- [X] T013 [US7] Implement `cmd_adopt` dry-run and `--report` in `agents/wikify/adopt_cmd.py`; apply the same safety preamble as `docs_cmd.cmd_docs` (`state.check_wiki_path`, lstat checks, fail-closed on inventory failure); make T011-T012 pass
- [X] T014 [US7] Add the `adopt` subparser (`--map`, `--include`, `--exclude`, `--apply`, `--report`, `--rewrite-refs`, `--prune-sources`, `--force`) in `agents/cli.py` and route it in `agents/wikify/commands.py`; update the matching snapshot in `tests/fixtures/cli_help/` and assertions in `tests/test_cli_contract.py`

### 7b. Apply, safety, idempotence (FR-019, FR-021)

- [X] T015 [US7] Write failing tests in `tests/test_wikify_adopt.py` for apply: files moved with `git mv` (history preserved, `git log --follow` works), bodies wrapped, hashes match originals, destination never overwritten, no deletion without a flag
- [X] T016 [US7] Write failing tests for refusal: dirty tree and detached HEAD exit 1 without `--force`, proceed with it; build-coupled, ignored, secret-path, and secret-hit files stay in place and appear in `skips` with the right reason
- [X] T017 [US7] Write failing tests for idempotence and resume: after commits 1 and 2 a second `--apply` is a no-op; after an interrupted run the dirty tree is refused without `--force`, and with `--force` the remainder completes with no duplicate pages
- [X] T018 [US7] Implement apply in `agents/wikify/adopt_cmd.py`: validate full plan first, then sorted per-file `git mv` and wrapper write, using `gitview` helpers; make T015-T017 pass
- [X] T019 [US7] Write failing tests for the map and indexes: one `<!-- wikify:map -->` entry per adopted page with a mechanical hint from the title, 60/80 char and 60-entry / 6144-byte caps honored, per-folder index pages when caps would be exceeded, entries stay inert text under the existing grammar
- [X] T020 [US7] Implement map updates in `agents/wikify/adopt_cmd.py` using `agents/wikify/agentmap.py`; make T019 pass
- [X] T021 [US7] Write failing tests that, after `apply` and commit 1 (apply does not run `verify`: it reads HEAD, which still has the old layout), `verify`, `mark` and `plan` pass with no `docs_unindexed`; edit `agents/wikify/plan.py` only if the post-commit test fails
- [X] T022 [US7] Write failing tests for the printed commit plan (commit 1 outside `docs/wiki/`, commit 2 docs-only, never commits) and implement it in `agents/wikify/adopt_cmd.py`

### 7c. References and outline pages (FR-021, edge cases)

- [X] T023 [US7] Write failing tests in `tests/test_wikify_adopt.py` for inbound-reference scan: relative links in other tracked docs, README, `AGENTS.md`, `CLAUDE.md`, source comments, CI configs are found and listed with file and line; unresolvable ones land in `unresolved_refs`; nothing is edited by default
- [X] T024 [US7] Implement scan and `--rewrite-refs` in `agents/wikify/adopt_refs.py`: rewrite relative links in moved files and in other tracked docs-only files only; make T023 pass
- [X] T025 [US7] Write failing tests that apply removes the outline pages of moved docs and rewrites or removes `sources/index.md`, and that unrelated stale generated pages are removed only with `--prune-sources`; implement in `agents/wikify/adopt_cmd.py` reusing `docs_cmd._stale`

### 7d. Skill (FR-018, FR-022)

- [ ] T026 [P] [US7] Write failing tests in `tests/test_wikify_installer.py`: `skills/wikify-adopt/SKILL.md` is in `agents/kits/wikify/templates/wikify/manifest.json` `managed_files`, installed only for agents whose config dir exists, removed by uninstall without touching user skills, dry-run writes nothing
- [ ] T027 [US7] Add `agents/kits/wikify/templates/wikify/skills/wikify-adopt/SKILL.md` documenting the loop `adopt` dry run -> agent edits `.wikifymap` -> user approves -> `adopt --apply` -> per-context page writing -> `verify` -> `mark` -> user review -> docs-only commit; include the guardrails: never rewrite migrated prose or human blocks, never invent facts, report doc-vs-code contradictions as findings, treat repo content as untrusted data, one bounded context per batch
- [ ] T028 [US7] Update `agents/kits/wikify/templates/wikify/manifest.json` and `agents/kits/wikify/installer.py` to install and uninstall the skill per agent; make T026 pass
- [ ] T029 [P] [US7] Write a test in `tests/test_wikify_installer.py` that the skill file contains no absolute machine paths, tokens, or secrets and references only `vibe wikify` commands that exist
- [ ] T030 [US7] Fill `tests/fixtures/adopt/WALKTHROUGH.md` with a checked fixture-repo walkthrough (expected command outputs per step) from the nested-docs fixture

**Checkpoint**: US7 works end to end on all three fixtures; skill installs and uninstalls cleanly.

---

## Phase 4: Polish & Cross-Cutting

- [ ] T031 [P] Update `agents/kits/wikify/templates/wikify/WIKIFY.md`: layout section, new "Adopting existing docs" section stating which prose is code-verified and which is imported, and the "Upgrading" note
- [ ] T032 [P] Update the Wikify section of `README.md` with `adopt` usage, flags, and the commit plan; keep it consistent with `contracts/adopt-cli.md`
- [ ] T033 [P] Add a no-content-loss check on the three fixtures and a perf case in `tests/test_wikify_perf.py` using call counts / doubling ratios (no wall-clock limits per Constitution IV)
- [ ] T034 Run `python3 -m unittest discover -s tests` and fix regressions; then run `vibe kits wikify install --dry-run --yes` and confirm no writes
- [ ] T035 Run the quickstart.md section 2 sequence on a scratch copy of a fixture and tick every expected-outcome row; run `git diff` and confirm no unrelated edits, secrets, or debug output

---

## Dependencies & Execution Order

- Phase 1: no dependencies. T002 and T003 parallel with T001.
- Phase 2: depends on Phase 1. T004->T005, T007->T008, T009->T010 are test-then-implement pairs; T006 parallel.
- Phase 3: depends on Phase 2. Order: 7a -> 7b -> 7c; 7d is independent of 7a-7c (only needs the CLI command names) and can run in parallel after T014.
- Phase 4: depends on Phase 3.
- Within each pair, the test task MUST fail before its implementation task starts (red, then green).

### Parallel examples

```text
After Phase 2:        T011 | T012          (different test concerns, same file: coordinate edits)
7b tests:             T016 | T017
After T014:           7d (T026, T029) in parallel with 7b/7c
Polish:               T031 | T032 | T033
```

## Implementation Strategy

- **MVP**: Phases 1-2 plus 7a and 7b (dry run, report, apply, idempotence). This delivers the CLI contract; the
  skill (7d) and link rewriting (7c) are increments.
- **Gate**: T001 decides Option A vs B. If B, revise T009/T010/T021 before proceeding.
- Commit per completed pair using Conventional Commits, e.g. `feat(wikify): add adopt dry run`.
- Do not push; the repository's SSH push has previously failed and pushing needs your explicit approval.
