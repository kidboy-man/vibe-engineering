# Implementation Plan: Wikify Sync and Drift Checks

**Branch**: `feat/wikify-adopt` (spec dir `002-wikify-sync-drift`) | **Date**: 2026-10-17 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/docs/specs/002-wikify-sync-drift/spec.md`

## Summary

Add page-level drift detection (`check`), mechanical line-number healing (`reanchor`), hash-tracked
editable imported pages (`migrate-imported`), report-only reference checks for imported prose,
enforcement outside the agent hook (`check --ci`, `install-hook`, hook delegates to the CLI), a `sync`
work list with a shipped `wikify-sync` skill, and map-cap warnings. Approach (see
[research.md](research.md)): store a 12-hex hash per citation range in `.wikify.json`; classify each
citation against HEAD by content-addressed relocation (never symbol-only); keep `adopt`'s wrapper
as the imported representation and register pages by hash; keep `verify` fail-closed and unchanged
for citations; make the verdict structural so squash merges stop mattering.

## Technical Context

**Language/Version**: Python 3.10+ (stdlib only)

**Primary Dependencies**: none new (reuse `gitview`, `citations`, `state`, `adopt_plan`, `adopt_refs`, `agentmap`, `plan._contexts`)

**Storage**: `docs/wiki/.wikify.json` (extended, backward compatible); no new control files

**Testing**: `unittest` (`tests/test_wikify_*.py`), temp git repos via existing helpers

**Target Platform**: Linux/macOS/WSL (native Windows unsupported, per baseline spec)

**Project Type**: CLI (`vibe-kits`) plus a vendored stdlib-only hook script

**Performance Goals**: `check` on a 615-file repo with ~12 pages completes in a few seconds; verified by call-count / doubling-ratio tests, not wall clock (Principle IV)

**Constraints**: deterministic, no model, no network; read-only `check`/`sync`; dry-run-first writers; hook fails open in agent sessions, git/CI fail closed

**Scale/Scope**: up to `MAX_CITATIONS` (2,000) per page, files read capped at 1 MiB, state file about 100 bytes per citation (no new size cap)

## Constitution Check

*Gate evaluated against constitution v1.1.0.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I Installer safety | Pass | New writers never overwrite (`init --update-protocol` replaces only a file whose hash is in the shipped list, i.e. pristine kit-owned text): `install-hook` refuses existing hook; `init --update-protocol` only replaces known shipped versions; skill uses `install_copy_style_file` (backup); `migrate-imported` writes only the state file |
| II Dry runs and consent | Pass | `reanchor`, `migrate-imported`, `install-hook`, `--fix-links`, `--update-protocol` dry-run by default, `--apply` is the explicit opt-in; no network anywhere |
| III No secrets; fail open/closed | Pass | Hook (agent session) fails open on its own errors; `check --ci`, `pre-push`, CI fail closed; `check` joins fail-closed commands; no secret rule text printed |
| IV Test-first, frozen contracts | Pass with action | Help fixtures updated intentionally; second-brain contract untouched; perf tests use counts/ratios |
| V Simplicity, shared core | Pass | Small modules, stdlib, existing helpers reused; only new surface is justified in research D1-D10 |

Post-design re-check: still pass. No Complexity Tracking entries.

## Project Structure

### Documentation (this feature)

```text
docs/specs/002-wikify-sync-drift/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/cli.md
├── checklists/requirements.md
└── tasks.md            # /speckit-tasks
```

### Source Code (repository root)

```text
agents/wikify/
├── state.py            # key-preserving load/save; helpers for citations/imported maps
├── drift.py            # NEW: range hashing, classification, relocation, commit attribution
├── reanchor.py         # NEW: plan + atomic apply (digits only)
├── imported.py         # NEW: wrapper recognition, registration, hash compare, mode
├── imported_refs.py    # NEW: DEAD PATH / DEAD SYMBOL / STALE LINK, fix-links
├── check_cmd.py        # NEW: check/sync rendering, JSON, work list, map-cap notices
├── hookinstall.py      # NEW: pre-push installer (hooksPath detection)
├── commands.py         # dispatch; verify uses imported.py; mark --reanchor and hash recording
├── init_cmd.py         # --update-protocol
└── agentmap.py         # cap-ratio helper (80%)
agents/cli.py           # new subparsers and flags
agents/kits/wikify/
├── installer.py        # SKILL_RELS tuple (adopt + sync); uninstall/doctor/diff loops
└── templates/wikify/
    ├── WIKIFY.md       # protocol text updated (editable imported pages, sync/check flow)
    ├── manifest.json   # managed_files += skills/wikify-sync/SKILL.md; version bump
    ├── skills/wikify-sync/SKILL.md   # NEW
    └── hooks/vibe-wikify/wikify_guard.py   # delegate to `vibe wikify check --ci` when stale

tests/
├── test_wikify_drift.py, test_wikify_reanchor.py, test_wikify_imported.py,
│   test_wikify_check_cmd.py, test_wikify_hookinstall.py,
│   test_wikify_parity.py, test_wikify_control_files.py,
│   test_wikify_skill_walkthrough.py                          # NEW
├── test_wikify_hook.py, test_wikify_installer.py, test_wikify_state.py,
│   test_wikify_cli.py                                         # extended
└── fixtures/cli_help/                                          # new + updated snapshots
docs/ + README.md + WIKIFY.md  # user docs, CI snippet, PR-comment design, migration note, skill walkthrough
```

**Structure Decision**: single Python package, new logic in small sibling modules under
`agents/wikify/` following the `adopt_*` precedent; commands wired through the existing
`commands.cmd_wikify` dispatcher; the kit gains one skill file via the existing copy-style path.

## Key design decisions (summary of research.md)

- D1 hashes in `.wikify.json`; D2 content-addressed relocation (`moved` only if exactly one window
  matches the recorded hash); D3 exit only on `changed`/`missing`; D4 imported = existing wrapper +
  registered hash, migrated by an explicit command; D5 report-only reference findings; D6 hook
  delegates to the CLI with fallback to today's behaviour; D7 protocol delivery via
  `init --update-protocol`; D8 map-cap notices; D9 `sync` + skill; D10 module layout.

## Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Old `mark` drops new state keys | degrade to "no range hash yet"; documented migration note |
| `check` passes while `verify` rejects a moved citation | documented; `mark --reanchor`; CI snippet runs `check --ci`, and `verify` stays the publish gate |
| Hook/CLI disagreement when `vibe` not on PATH | fall back to current commit-order rule (documented) |
| First push after upgrade has no hashes, so `check` is blind to body edits | FR-019 exception: hook falls back to the commit-order rule while `unbaselined_changed > 0`; CI/pre-push stay non-failing per Q1 and the gap is documented |
| Perf on large files | 1 MiB cap, rolling line-hash windows, per-page citation cap, call-count tests |
| Imported-kind spoofing | only pages registered by hash via `migrate-imported --apply` are imported; unregistered wrappers stay human blocks |

## Complexity Tracking

No constitution violations to justify.
