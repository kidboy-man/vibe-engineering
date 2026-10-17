# Research: `vibe wikify adopt`

All items from the plan's Technical Context are resolved; no unknowns remain open.
Items marked **verify in design spec** need confirmation in source before implementation starts, as
`feature.md` also requires.

## D1. Representation of migrated prose (FR-020)

- **Decision**: Option A. The migrated body is wrapped verbatim in one `<!-- wikify:human -->` ...
  `<!-- /wikify:human -->` block. Provenance goes on a comment line inside the block:
  `<!-- imported from=<old path> -->`.
- **Rationale**: `citations.parse` already strips human blocks before the uncited-paragraph check, so the
  verifier stays strict for every ordinary page and needs no new page kind. `commands._notices` already
  reports added, changed, and removed human blocks, which gives free change detection for imported text.
- **Alternatives considered**: Option B, a new page kind exempt from citation checks. It needs verifier,
  planner, and notice changes and creates a second exemption path to keep safe. Rejected unless the
  verification below fails.
- **Verified (T001)**: no cap on human blocks; headings and links inside blocks are masked from both the
  uncited check and reachability; `verify` cannot report adopted pages separately, so the provenance comment
  and existing `HUMAN BLOCK CHANGED` notices serve as the label. Option A stands. See
  `docs/superpowers/specs/2026-10-17-wikify-adopt-design.md`.

## D2. Mapping file

- **Decision**: `docs/wiki/.wikifymap`, plain text, one `source-glob -> destination-folder/` rule per line,
  `#` comments, same limits as `.wikifyignore` (size, pattern count, wildcards). Added to `CONTROL_FILES`
  so `verify` flags it if git ignores it.
- **Rationale**: matches the existing control-file family, is reviewable in a diff, and makes re-runs
  idempotent because applied moves are recomputed from the tree plus the file.
- **Alternatives considered**: JSON (harder to review, no comments); storing moves in `.wikify.json`
  (mixes freshness state with user intent).

## D3. Atomicity

- **Decision**: validate the whole plan first (collisions, secret-scan hits, path safety, dirty tree), then
  perform `git mv` per file in sorted order. Resume after an interruption needs `--force` (dirty tree);
  after commits 1 and 2 a re-run is a no-op. No partial rollback.
- **Rationale**: git history is the undo; `git mv` is cheap and each step is independently valid.
- **Alternatives considered**: staging area in a temp tree then swap (more code, same safety).

## D4. Link rewriting

- **Decision**: rewrite relative markdown links inside moved files and in other tracked docs-only files only
  when `--rewrite-refs` is given; always list unresolvable inbound references (README, `AGENTS.md`,
  `CLAUDE.md`, source comments, CI configs) without editing them.
- **Rationale**: matches Principle I; rewriting outside `docs/` could change build or authz behavior.

## D5. Freshness and commit plan

- **Decision**: commit 1 is the staged pure `git mv` renames (plus rewritten refs outside the wiki); then
  `mark`; then a docs-only commit 2. The wrapper write is unstaged so renames stay 100% similar. It never commits.
- **Rationale**: the freshness rule allows only docs-only commits after the commit that touches
  `.wikify.json`.

## D6. Outline pages from `wikify docs`

- **Decision**: apply always removes the `sources/` outline pages of the docs it moves and rewrites or removes
  `sources/index.md`; `--prune-sources` removes only unrelated stale generated pages.
- **Rationale**: after the move commit the doc is under `docs/wiki/`, no longer eligible, so its outline page would
  fail verify ("generated page has no eligible source").

## D7. Skill delivery

- **Decision**: ship `skills/wikify-adopt/SKILL.md` in the wikify kit templates and install it per agent
  whose config directory exists (Claude Code, Codex CLI, Cursor), registered in the kit manifest so
  uninstall removes only it.
- **Rationale**: the CLI is the contract; the skill is a playbook, so any agent that can run commands works.
- **Alternatives considered**: a separate kit (extra registry entry for one file); document in WIKIFY.md
  only (not discoverable as a skill).

## D8. Skill testing

- **Decision**: a checked-in fixture-repo walkthrough in `tests/fixtures/adopt/` plus a unit test that the
  skill file exists, is listed in the manifest, and contains no absolute paths or secrets. Model behavior
  is not unit-tested.
