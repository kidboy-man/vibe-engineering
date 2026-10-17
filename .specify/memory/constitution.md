# Vibe Engineering Constitution

## Core Principles

### I. Installer Safety (NON-NEGOTIABLE)

Installers MUST preserve existing user files. A file MAY be overwritten, merged, or
removed only when a manifest proves the kit owns it. Config merges MUST be additive
and reversible by `uninstall`. Anything not provably owned is left untouched.

Rationale: kits write into users' home-directory tool configs (`~/.claude`, `~/.codex`,
etc.); a single clobbered file destroys trust and user data.

### II. Side-Effect-Free Dry Runs and Explicit Consent

`--dry-run` MUST NOT write, delete, or execute anything with side effects. Any
dependency setup or network operation (for example `npm install -g @tobilu/qmd`) MUST
require clear user consent; non-`second-brain` kits MUST NOT run network commands.
`--yes` skips ordinary install confirmations but MUST NOT, by itself, grant consent to a
network or package-manager command; that requires its own explicit opt-in flag (for
example `--setup-deps`) plus an interactive approval.

Rationale: users must be able to preview exactly what an install does, and nothing
reaches the network or their machine without agreement.

### III. No Secrets, Portable Templates

Bundled templates MUST NOT contain local secrets, auth tokens, or absolute
machine-specific paths. Installers MUST NOT copy secret material from the user's
environment into managed files. Guardrail hooks MUST deny operations that match their
destructive or secret-bearing policy. Hook scripts that run inside an agent session MUST
fail open on parse or internal errors so a broken hook never blocks a session; they are
heuristic speed bumps, not sandboxes, and documentation MUST say so. Commands that gate
correctness (for example `vibe wikify verify`, `plan`, `docs`, and `check`) MUST fail
closed, as MUST git hooks and CI gates that invoke them (for example `check --ci` and an
installed `pre-push` hook).

Rationale: templates ship to every user; a leaked path or token is a permanent leak.
Hooks run inside the user's agent session, where a crashing hook must not lock them out.
A git or CI gate that fails open silently defeats its purpose, so it fails closed.

### IV. Test-First with Frozen Contracts

Behavior changes MUST be driven by a failing `unittest` test first (red, green,
refactor), placed beside related coverage per `AGENTS.md`. Strings that older installs
are found and removed by (`tests/test_second_brain_contract.py`) and CLI help
snapshots (`tests/fixtures/cli_help/`) are contracts: they MUST change only with an
explicit migration or an intentional fixture update. Tests MUST be deterministic;
performance checks use call counts or doubling ratios, not wall-clock limits.

Rationale: installers act on user machines and cannot be hotfixed there; regressions
must be caught before release.

### V. Simplicity and Shared Core

Prefer small functions, small modules, and the standard library. New kits MUST reuse
`installer_core` helpers (`CopyKit`, `plan_copy_files`, `apply_copy_plan`,
`report_binary`, `confirm`) and register through `kit_registry.py`; logic MUST NOT be
duplicated per kit. New runtime dependencies require explicit justification. Facade
modules keep the names tests patch, and submodules call `shutil`/`subprocess`/`core`
through the module object.

Rationale: many kits share one safety model; a single audited core keeps Principles I
and II enforceable in one place.

## Technical Constraints

- Python 3.10+, standard 4-space style; packages snake_case, CLI kit names may be
  hyphenated (`claude-code`, `second-brain`), and the two MUST stay aligned.
- Each kit lives in `agents/kits/<kit_name>/` with an `installer.py` and bundled
  `templates/<name>/manifest.json`; `MANIFEST.in` MUST package it and
  `tests/test_kit_contract.py` MUST pass.
- Extra install flags are declared in `INSTALL_OPTIONS` (flag -> installer kwarg).
- Documentation for users lives in `docs/` and `README.md` and MUST be updated with
  user-visible behavior changes.

## Development Workflow

- Commits use Conventional Commit subjects with a scope, e.g.
  `fix(cli): improve pipx detection`.
- Before review, run `python3 -m unittest discover -s tests`; also run
  `vibe kits <kit> install --dry-run --yes` for any installer change.
- Pull requests MUST explain the user-visible change, list tests run, link any issue,
  and call out installer safety implications (file writes, merge behavior, network
  commands).
- Changes to security-sensitive surfaces (hooks, guard rules, file writes, merges)
  MUST receive a security-focused review before merge.

## Governance

This constitution supersedes other project practices. Amendments require a pull
request that edits this file, states the rationale, and, for any change that alters
installer behavior or a frozen contract, includes the migration plan. Versioning
follows semantic rules: MAJOR for removal or redefinition of a principle, MINOR for a
new principle or materially expanded guidance, PATCH for clarifications. Every pull
request review MUST verify compliance with these principles; deviations MUST be
justified in the PR description. Runtime development guidance lives in `AGENTS.md`.

**Version**: 1.1.0 | **Ratified**: 2026-10-17 | **Last Amended**: 2026-10-17
