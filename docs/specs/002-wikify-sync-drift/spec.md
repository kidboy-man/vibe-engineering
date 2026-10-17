# Feature Specification: Wikify Sync and Drift Checks

**Feature Branch**: `feat/wikify-adopt` (spec authored here; spec directory `002-wikify-sync-drift`; no dedicated branch created)

**Created**: 2026-10-17

**Status**: Draft

**Input**: User description: "Keep the wiki always in sync (`vibe wikify sync` + drift checks): page-level
drift detection, mechanical re-anchoring of moved citations, editable imported pages, reference
checks for imported prose, enforcement beyond the agent hook (CLI, `pre-push`, CI), a sync
workflow and skill, and map-size hygiene. Observed on a Go modular monolith (615 files, 29 imported
docs, 12 hand-written cited pages)."

## Clarifications

### Session 2026-10-17

- Q: When existing citations have no stored range hash yet (upgrade), should `check` fail, warn, or ignore? → A: Warn: report "no range hash yet" per citation, non-failing; keep checking `moved` and `missing`.
- Q: How do existing adopt-wrapped docs become imported pages? → A: A separate migrate command, dry run by default, writes only with an explicit apply flag; the baseline step never changes page content.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See exactly which pages a code change affected (Priority: P1)

A maintainer (or an agent) changes code and wants to know whether the wiki is still true. They run
a read-only drift check and get, per page, which citations are **moved**, **changed**, **missing**,
or **uncovered**, plus the commits that touched those citations, instead of a generic "wiki is
stale" refusal.

**Why this priority**: Everything else (healing, gating, sync) depends on precise, page-level drift
detection. It alone turns "re-plan the repo" into "update 2 pages".

**Independent Test**: In a fixture repo with one shifted range, one changed cited body, one deleted
symbol and one new uncovered file, run the check and confirm each is reported against the right
page with the right category and commits; confirm the working tree is byte-identical afterwards.

**Acceptance Scenarios**:

1. **Given** a cited symbol whose line range shifted but whose body is unchanged, **When** the check
   runs, **Then** the citation is reported as `moved` against its page as auto-healable and does
   not by itself cause a failing exit.
2. **Given** a cited range whose content changed since the last baseline, **When** the check runs,
   **Then** it is reported as `changed` with the commits that touched it.
3. **Given** a cited symbol or file that no longer exists, **When** the check runs, **Then** it is
   reported as `missing`.
4. **Given** new or changed code in a bounded area that no page covers, **When** the check runs,
   **Then** it is reported as `uncovered` as a warning that does not fail the run (FR-001a).
5. **Given** a wiki with no drift (or only `moved` citations), **When** the check runs, **Then** it
   exits zero; **Given** any `changed` or `missing` finding, **Then** it exits non-zero.
6. **Given** any repo state, **When** the check runs twice, **Then** the tree is unchanged and both
   outputs are identical.

---

### User Story 2 - Auto-heal pure line-number drift (Priority: P1)

When the only thing wrong is that a cited symbol moved, the maintainer runs a re-anchor command that
previews, then applies, the corrected line numbers without touching prose.

**Why this priority**: Line shifts are the most frequent, least meaningful failure; removing them
keeps genuine drift visible.

**Independent Test**: Shift a cited range by inserting lines above it; run re-anchor (dry run shows
the planned change, tree untouched), then with apply and confirm only the line numbers changed and
the check now passes.

**Acceptance Scenarios**:

1. **Given** a `moved` citation whose symbol occurs exactly once in the new file with an unchanged
   body, **When** re-anchor runs without apply, **Then** it lists the rewrite and changes nothing.
2. **Given** the same state, **When** re-anchor runs with apply, **Then** only the line numbers in
   that citation are rewritten.
3. **Given** a symbol that now occurs twice, or whose body changed, **When** re-anchor runs,
   **Then** it refuses that citation and reports why.
4. **Given** human blocks, generated pages, or imported prose, **When** re-anchor applies,
   **Then** they are never modified.
5. **Given** the user asks the baseline-recording step to re-anchor first, **When** it runs,
   **Then** healing happens before the baseline is recorded.

---

### User Story 3 - Edit imported docs without tripping tamper alarms (Priority: P1)

A maintainer edits an imported doc (a TRD or guide) because the feature changed. The wiki treats
the edit as a normal, noticed change rather than tampering, and the protocol text tells agents they
may edit imported pages and what to run afterwards.

**Why this priority**: Today's rule contradicts how repos work; every legitimate edit looks like
tampering, which erodes trust in the real tamper signal.

**Independent Test**: Edit an imported page; verification reports a notice (not an error) naming the
page; after recording a new baseline the notice is gone. Edit a genuine human block and confirm the
existing changed/removed error still fires.

**Acceptance Scenarios**:

1. **Given** an imported page edited after its recorded content hash, **When** verification runs,
   **Then** it prints `IMPORTED PAGE EDITED: <page>` as a notice and does not fail.
2. **Given** that notice, **When** the baseline is recorded, **Then** the new hash is stored and the
   notice disappears.
3. **Given** a genuine human block altered or removed, **When** verification runs, **Then** the
   existing `HUMAN BLOCK CHANGED/REMOVED` notice behaviour (non-failing, shown to the user for
   review) is unchanged.
4. **Given** a repo that opts into `imported_mode: frozen`, **When** an imported page is edited,
   **Then** the edit is reported as an error (a deliberate strengthening: today it is only a
   notice).
5. **Given** an existing wiki state created before this feature, **When** it is verified, **Then**
   it keeps working with no required migration step.
6. **Given** a page previously adopted and wrapped in human blocks, **When** the user runs the
   migrate command with its apply flag, **Then** it is recognised as an imported page (dry run first, no page
   rewritten without consent); until then, editing it behaves as today.

---

### User Story 4 - Block drift in git and CI, not only in the agent hook (Priority: P2)

A team wants a push from a plain terminal, an IDE, or CI to fail when the wiki has drifted, using
the same verdict the agent hook uses.

**Why this priority**: Closes the "convenience gate only" gap; depends on Story 1.

**Independent Test**: Install the git hook with explicit consent in a fixture repo and push a drifting
commit (blocked) and a clean one (allowed); run the CI mode and confirm concise, machine-readable
output and a failing exit on drift.

**Acceptance Scenarios**:

1. **Given** drift, **When** the CI mode runs, **Then** it prints a concise summary, can emit a
   machine-readable summary, and exits non-zero.
2. **Given** the user asks to install the git hook, **When** a pre-push hook already exists,
   **Then** nothing is overwritten and the user is told why; with no existing hook it is written
   only after explicit consent, and a dry run writes nothing.
3. **Given** one repo state, **When** both the agent hook and the check run, **Then** they return
   the same verdict, except the FR-019 case (a cited file changed but its citation has no stored
   hash), where the hook may block while the check passes.
4. **Given** an internal error, **When** the CI mode or git hook runs, **Then** it fails closed;
   **When** the agent-session hook hits an internal error, **Then** it fails open (per
   constitution Principle III).
5. **Given** a squash merge that mixes code with the baseline file, **When** every citation resolves
   with no `changed` or `missing` entries, **Then** the check passes even though the
   commit-order rule is violated, and recording a new baseline re-baselines without a docs-only
   commit being required to pass the check.

---

### User Story 5 - A guided sync loop for agents (Priority: P2)

An agent (or person) runs one command that checks, previews healing, and prints a prioritized work
list; a shipped skill drives the loop to a verified, user-confirmed docs-only commit.

**Why this priority**: Turns detection into a repeatable workflow; valuable but built on Stories
1–3.

**Independent Test**: Run sync on the multi-drift fixture and confirm the work list is ordered
(moved, changed, missing, uncovered) per page; install the kit and confirm the skill is present;
follow the documented walkthrough end to end until the check passes.

**Acceptance Scenarios**:

1. **Given** drift, **When** sync runs, **Then** it runs the check, previews re-anchoring, and prints
   a per-page prioritized work list, writing nothing.
2. **Given** the kit is installed, **Then** a `wikify-sync` skill is installed the same way the
   `wikify-adopt` skill is.
3. **Given** the skill, **Then** it instructs: sync, edit pages, verify, record baseline, show the
   diff, wait for user confirmation, then a docs-only commit; never invent facts; read the code
   behind any claim before changing it; report doc-versus-code contradictions as findings.
4. **Given** sync + edits + baseline, **Then** the check passes.

---

### User Story 6 - Catch dead references in imported prose (Priority: P3)

A maintainer learns that an imported TRD mentions a file, symbol, or link that no longer exists.

**Why this priority**: Useful, report-only; no gating risk.

**Independent Test**: Delete a file referenced in an imported doc; the check reports `DEAD PATH` for
it without failing the run.

**Acceptance Scenarios**:

1. **Given** a backticked path not tracked in the repo, **Then** `DEAD PATH` is reported.
2. **Given** a backticked identifier found nowhere in the repo, **Then** `DEAD SYMBOL` is reported.
3. **Given** a link to a page that does not exist, **Then** `STALE LINK` is reported.
4. **Given** reference findings only, **Then** the run does not fail because of them.
5. **Given** the user asks to fix links, **Then** only paths that map through the repo's
   move-mapping file are rewritten; everything else is left alone.
6. **Given** any reference output, **Then** it states that name-only matching is a floor, not proof.

---

### User Story 7 - Warn before the map outgrows its caps (Priority: P3)

The check warns when the wiki map passes 80% of its size or entry-count caps, and sync suggests
grouping pages under per-folder index pages.

**Why this priority**: Preventive hygiene.

**Independent Test**: Build a fixture map above 80% of either cap; check prints a warning (no
failure); sync prints a grouping suggestion.

**Acceptance Scenarios**:

1. **Given** the map exceeds 80% of 6144 bytes or 60 entries, **Then** the check warns and does not
   fail.
2. **Given** the same state, **Then** sync suggests per-folder index grouping and does not create it.

---

### Edge Cases

- Repo with no baseline yet (never recorded): check reports "no baseline" distinctly, not as drift
  on every page.
- Shallow clone or missing history in CI: attribution to commits degrades with a clear message;
  structural verdicts still work; the gate fails closed only on verdict-affecting errors.
- A citation range that is partly deleted, or a file renamed: classified `missing` (or `moved` only
  if unambiguous), never silently healed.
- Symbol appears in multiple files or twice in one file: re-anchor refuses.
- Imported page that also contains a genuine human block: the human-block rule applies to that block
  only; adopt-wrapped legacy blocks are handled by FR-027.
- Citations recorded before this feature have no range hash: reported as "no range hash yet",
  non-failing, until the baseline is re-recorded.
- Repo sets a custom git hooks directory (for example via husky): the hook installer detects it and
  refuses or reports instead of writing a hook that never runs.
- Symbol now occurs twice or its body changed: classified `changed` (not `moved`), so it is never
  silently healed.
- Secret-scan rules: matched rules are never printed in any new output.
- Windows line endings / non-UTF-8 files: range hashing is deterministic and does not crash.
- Page excluded by `.wikifyignore` or `.wikify-allow` contents: respected and never edited.
- Detached HEAD or unborn branch: check explains it instead of crashing.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide a read-only check that, for every wiki page, classifies each
  cited file/symbol against HEAD as `moved`, `changed`, `missing` or `uncovered`, and exits non-zero
  when any `changed` or `missing` finding exists. `moved` is reported and auto-healable but does not
  fail the run on its own.
- **FR-001a**: `uncovered` findings MUST be reported by the check and sync but MUST NOT cause a
  failing exit, including in CI and git-hook modes. The "bounded area" for `uncovered` is a code
  directory or package that no page cites, and the work list names it.
- **FR-002**: The check MUST name the affected pages and the commits that touched their citations.
- **FR-003**: Recording a baseline MUST store a content hash of at least 12 hex characters of each cited range so `changed`
  can be detected; the baseline file MUST remain readable by installs that predate this feature.
  Citations without a stored hash MUST be reported as "no range hash yet" (non-failing) while still
  being checked for `moved` and `missing`; `changed` detection for each begins once the baseline is
  re-recorded.
- **FR-004**: The check MUST be deterministic, perform no network access and use no model, MUST NOT
  modify the working tree, and MUST be idempotent.
- **FR-005**: The existing deleted-citation detection MUST be extended to feed the `missing`
  category rather than duplicated.
- **FR-006**: The system MUST provide a re-anchor command that is a dry run by default and writes
  only with an explicit apply flag.
- **FR-007**: Re-anchor MUST rewrite only line numbers of `moved` citations whose symbol occurs
  exactly once in the new file and whose body hash is unchanged; otherwise it MUST refuse and report
  the reason.
- **FR-008**: Re-anchor MUST NOT touch prose, human blocks, generated pages, or imported prose.
- **FR-009**: The baseline-recording command MUST accept an option to re-anchor first.
- **FR-010**: "Imported" MUST become an explicit page kind with a documented representation; edits
  to imported pages MUST NOT be treated as tampering.
- **FR-011**: Verification MUST track each imported page by a stored content hash, MUST report an
  edit as the notice `IMPORTED PAGE EDITED: <page>` (non-failing), and recording a baseline MUST
  re-record the hash.
- **FR-012**: Genuine human blocks MUST keep their existing changed/removed notice behaviour
  (non-failing); only registered imported pages get the new editable treatment.
- **FR-013**: The protocol text (`WIKIFY.md` and the text shipped into repos) MUST state that
  imported pages are editable, what to run after editing, and MUST drop the "never edit imported
  prose" rule. The new text MUST reach already-installed repos through an explicit, dry-run-first
  protocol-update command that replaces `docs/wiki/WIKIFY.md` only when its content matches a
  previously shipped version (the ownership proof under constitution Principle I), after a backup;
  a locally edited copy MUST be reported, not overwritten.
- **FR-014**: A repo MUST be able to opt out with the setting `imported_mode: frozen`; the default is `editable`.
- **FR-015**: The system MUST report, without failing, for every wrapper-shaped imported page
  (registered or not): `DEAD PATH`, `DEAD SYMBOL` and `STALE LINK` for backticked identifiers, file
  paths and links; the output MUST state that name-only matching is a floor.
- **FR-016**: A link-fix command (`fix-links`) MUST rewrite only paths that map through the existing move-mapping
  file, with dry-run-first behaviour.
- **FR-017**: The check MUST offer a CI mode with concise output and a machine-readable summary, and
  MUST fail closed in that mode; documentation MUST include a CI workflow snippet and a design for
  posting the summary on pull requests (no network inside the CLI).
- **FR-018**: The system MUST provide an install-hook command that writes a `pre-push` git hook only
  with explicit consent, never overwrites an existing hook, has a side-effect-free dry run, and
  detects a custom hooks directory setting, refusing or reporting rather than writing a hook that
  would never run. The explicit apply flag is the user's consent.
- **FR-019**: The agent push hook MUST use the same verdict as the check, with one exception: while
  a cited file has changed but its citation has no stored hash (so body edits are invisible to the
  check), the hook MUST keep the existing commit-order staleness rule so the first push after an
  upgrade is not less protected than today; the agent-session hook
  fails open on internal errors, while git-hook and CI paths fail closed (constitution Principle III).
- **FR-020**: The check MUST pass when all citations resolve and no failing finding (`changed`,
  `missing`; `uncovered` never fails per FR-001a) exists, even if the commit-order freshness rule
  is violated (squash merges), and
  recording a baseline MUST re-baseline in that case.
- **FR-021**: The system MUST provide a sync command that runs the check, previews re-anchoring and
  prints a prioritized per-page work list without writing anything.
- **FR-022**: The kit install MUST ship a `wikify-sync` skill installed like `wikify-adopt`, with the
  loop and guardrails described in Story 5.
- **FR-023**: The check MUST warn (non-failing) when the map exceeds 80% of its 6144-byte or 60-entry
  caps, and sync MUST suggest per-folder index grouping without creating it.
- **FR-024**: Existing baseline files MUST keep working; new fields are optional and a migration note
  MUST be documented.
- **FR-025**: Output MUST never print matched secret-scan rules; `.wikifyignore` and `.wikify-allow`
  MUST never be edited by any new command.
- **FR-026**: Test fixtures MUST cover: shifted range healed, changed body, missing symbol, uncovered
  file, edited imported page (notice, then clean), imported doc with a removed file (`DEAD PATH`),
  and squash-merge history; a read-only check proven by an unchanged tree hash; and a documented,
  checked walkthrough of the skill.
- **FR-027**: Existing adopt-wrapped docs (wrapped in human blocks) MUST be recognisable as imported
  pages through a separate migrate command that is dry-run by default and writes only with an
  explicit apply flag; the baseline-recording step MUST NOT convert or otherwise change page content.

### Key Entities

- **Page**: a wiki page, of kind hand-written/cited, imported, or generated; has citations.
- **Citation**: a reference from a page to a file, line range and symbol, with a stored range hash
  after a baseline.
- **Baseline**: the recorded state (commit, per-citation range hashes, per-imported-page content
  hashes) that drift is measured against.
- **Drift finding**: a (page, citation, category, touching commits) record; categories are moved,
  changed, missing, uncovered.
- **Reference finding**: a report-only record for imported prose: dead path, dead symbol, stale link.
- **Work list**: a prioritized, per-page set of findings produced by sync.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On a fixture with N known drifts across M pages, the check attributes 100% of them to
  the correct page and category with zero false positives for an undrifted fixture.
- **SC-002**: On a fixture where only 2 of its pages are affected, a single command lists exactly
  those 2 pages, so no other page needs to be touched.
- **SC-003**: Pure line-shift drift is resolved with zero manual edits in 100% of unambiguous
  fixtures; ambiguous cases are 100% refused.
- **SC-004**: Editing an imported page produces zero failing exits and exactly one notice until the
  baseline is re-recorded; a genuine human-block change still produces its review notice in 100% of cases.
- **SC-005**: A drifting push is blocked from the agent hook, a plain terminal and CI with the same
  verdict in 100% of tested cases, except the documented FR-019 unbaselined-citation case.
- **SC-006**: The check leaves the tree byte-identical and produces identical output across repeated
  runs in 100% of tested cases.
- **SC-007**: A squash-merge fixture passes the check and re-baselines without a hand-made docs-only
  commit.
- **SC-008**: Following the skill walkthrough on the multi-drift fixture ends with a passing check.
- **SC-009**: The existing test suite keeps passing; frozen second-brain contract strings are
  unchanged, and CLI help fixtures change only intentionally for the new commands.

## Assumptions

- `moved` does not fail the run (it is auto-healable); a citation whose symbol is ambiguous or whose
  body changed is `changed`, not `moved`.
- Command names follow the request: check, re-anchor, sync, install-hook under the existing wikify
  command group; exact CLI spellings are decided in planning.
- Representation of the "imported" page kind (marker vs hash-tracked metadata) is a planning
  decision; it must remain readable by older installs.
- `uncovered` is warn-only (FR-001a); its "bounded area" is a code directory or package no page cites.
- Reference checking is name/path matching only, not semantic proof; semantic truth, LLM use,
  auto-generating pages and deleting stale pages are out of scope.
- The `imported_mode` setting defaults to `editable`; `frozen` restores today's behaviour.
- Native Windows remains unsupported, consistent with the baseline spec.
- The read-first review of the verifier, planner, push hook and existing tests happens in
  `/speckit-plan`, which confirms which stated gaps are real before design.
- Constitution v1.1.0 Principle III governs fail-open vs fail-closed behaviour.
