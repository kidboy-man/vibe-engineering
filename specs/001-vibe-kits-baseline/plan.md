# Implementation Plan: Vibe Kits Baseline (plus planned `wikify adopt`)

**Branch**: `001-vibe-kits-baseline` (working branch: `feat/wikify-adopt`) | **Date**: 2026-10-17 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-vibe-kits-baseline/spec.md`

## Summary

The baseline (User Stories 1-6, FR-001 to FR-016) is already shipped; this plan records its architecture
as the constraint set and plans only the unshipped delta: `vibe wikify adopt` (User Story 7, FR-017 to
FR-022). Approach: a deterministic CLI layer (inventory, mapping file, `git mv`, link rewrite, report)
built from existing `agents/wikify` modules, plus a shipped `wikify-adopt` skill that drives it. Migrated
prose is wrapped verbatim in the existing human-block syntax (Option A, see research.md), so the verifier
needs no relaxation for ordinary pages.

## Technical Context

**Language/Version**: Python 3.10+ (`requires-python = ">=3.10"`)

**Primary Dependencies**: standard library only; `tomli` on Python < 3.11 (existing). No new dependency.

**Storage**: files only (git working tree; `docs/wiki/.wikifymap` for the mapping, per-kit manifests)

**Testing**: `unittest` (`python3 -m unittest discover -s tests`); new `tests/test_wikify_adopt.py`

**Target Platform**: Linux, macOS, WSL (native Windows unsupported per spec clarification)

**Project Type**: single-package CLI (`vibe`, entry `agents.cli:main`)

**Performance Goals**: no wall-clock targets; scaling guarded by call-count and doubling-ratio tests, as in
`tests/test_wikify_perf.py`

**Constraints**: CLI layer never calls a model; dry-run by default; no overwrite; no delete without flag;
all-or-nothing or resumable apply; map caps (60 entries, 6144 bytes, 60/80 char hints) unchanged;
secret scan applies to moved content with no auto allow-listing

**Scale/Scope**: repos with tens to low hundreds of markdown docs (reference case: ~35 docs in a 615-file repo)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Gate | Status |
|-----------|------|--------|
| I. Installer Safety | Skill file is a manifest-owned managed file; `adopt` never overwrites and never deletes without a flag; moves via `git mv` | Pass |
| II. Dry runs and consent | `adopt` is dry-run by default, `--apply` writes; no network; no package-manager commands | Pass |
| III. No secrets, portable | Secret scan runs on moved content; skill template has no absolute paths or tokens | Pass |
| IV. Test-first, frozen contracts | CLI help fixture for `wikify` is updated intentionally; new tests precede implementation; no wall-clock assertions | Pass (obligation recorded in tasks) |
| V. Simplicity and shared core | Reuse `docs_inventory`, `citations`, `gitview`, `agentmap`, `state`; no new dependency; skill installed through existing wikify kit installer | Pass |

Post-design re-check (after Phase 1): still Pass. No complexity violations.

Note: the constitution says `--yes` is the only way to pre-grant consent; the README says `--yes` alone never
installs qmd. This plan does not depend on that line; the constitution amendment stays a separate item.

## Project Structure

### Documentation (this feature)

```text
specs/001-vibe-kits-baseline/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── adopt-cli.md
│   └── adopt-report.schema.json
└── tasks.md             # Phase 2 output (/speckit-tasks, not created here)
```

### Source Code (repository root)

```text
agents/
├── cli.py                       # add `adopt` subparser under `wikify`
├── wikify/
│   ├── adopt_cmd.py             # NEW: command, dry-run/apply/report, commit plan
│   ├── adopt_plan.py            # NEW: classification, mapping-file parse/render, destinations
│   ├── adopt_refs.py            # NEW: inbound-reference scan and relative-link rewrite
│   ├── commands.py              # route `adopt`; plan/verify aware of imported pages
│   ├── citations.py             # add `.wikifymap` to CONTROL_FILES
│   ├── docs_inventory.py        # reuse inventory and eligibility
│   └── plan.py                  # stop listing docs_unindexed for adopted docs
└── kits/wikify/
    ├── installer.py             # install skill next to the hook per agent
    └── templates/wikify/
        ├── WIKIFY.md            # new "Adopting existing docs" section, layout, upgrading note
        ├── manifest.json        # add skill to managed_files
        └── skills/wikify-adopt/SKILL.md   # NEW: the playbook

tests/
├── test_wikify_adopt.py         # NEW: classification, mapping, refs, skips, caps, commit plan, idempotence
├── test_wikify_installer.py     # skill installed and uninstalled
├── test_cli_contract.py         # help text
├── fixtures/cli_help/           # update wikify help snapshot intentionally
└── fixtures/adopt/              # NEW: empty-docs, flat-docs, nested-docs-with-assets repos
README.md                        # Wikify section: adopt usage
```

**Structure Decision**: single Python package; adopt is three small modules beside the existing wikify
modules, following the existing `*_cmd.py` / `*_inventory.py` split. No new top-level directories.

## Complexity Tracking

No constitution violations; table intentionally empty.
