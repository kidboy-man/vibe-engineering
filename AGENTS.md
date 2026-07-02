# Repository Guidelines

## Project Structure & Module Organization

This repository packages the `vibe` CLI as the `vibe-kits` Python project.
Core code lives in `agents/`: `cli.py` contains command dispatch,
`installer_core.py` shared install behavior, `kit_registry.py` kit discovery,
and `merge_strategies.py` config merging helpers. Individual kits live under
`agents/kits/<kit_name>/` with an `installer.py` plus bundled files in
`templates/`. Tests are in `tests/`, with CLI help snapshots in
`tests/fixtures/cli_help/`. User-facing setup notes are in `docs/`.

## Build, Test, and Development Commands

- `python3 -m pip install -e .` installs the package locally with the `vibe`
  console script.
- `python3 -m pytest` runs the test suite.
- `python3 -m pytest tests/test_second_brain_installer.py` runs one focused
  test module while iterating.
- `vibe kits list` verifies the installed CLI can load registered kits.
- `vibe kits <kit> install --dry-run --yes` checks installer behavior without
  writing managed files.

## Coding Style & Naming Conventions

Use standard Python 3.10+ style with 4-space indentation, small functions, and
clear module-level helpers. Keep kit directories and command keys aligned:
Python packages use snake_case, while CLI kit names may use hyphenated names
such as `claude-code` and `second-brain`. Template files should remain portable
and must not include local secrets, absolute machine-specific paths, or auth
tokens.

## Testing Guidelines

Tests use `pytest` and follow the `tests/test_*.py` naming pattern. Add focused
tests beside related coverage: installer behavior in `test_*_installer.py`,
shared merge logic in `test_merge_strategies.py`, registry behavior in
`test_kit_registry.py`, and CLI contracts in `test_cli_contract.py`. When a CLI
command's help text changes intentionally, update the matching fixture in
`tests/fixtures/cli_help/`. Prefer exact assertions for subprocess arguments
when command ordering matters.

## Commit & Pull Request Guidelines

Recent history uses Conventional Commit-style subjects, for example
`fix(cli): improve pipx detection` and `feat(second-brain): wire proactive context`.
Keep commits scoped and describe the affected surface in the optional scope.
Pull requests should explain the user-visible change, list tests run, link any
issue, and call out installer safety implications such as file writes, merge
behavior, or network commands.

## Security & Configuration Tips

Installer changes must preserve existing user files unless a manifest proves
ownership. Keep dry-run paths side-effect free. Any dependency setup or network
operation should require clear user consent, matching the current
`second-brain` kit behavior.
