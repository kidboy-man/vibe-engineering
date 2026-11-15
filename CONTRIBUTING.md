# Contributing

Thanks for helping improve vibe-kits. Bug reports and feature ideas go in
[GitHub issues](https://github.com/kidboy-man/vibe-engineering/issues).

## Pull requests

- Use Conventional Commit subjects with a scope, for example
  `fix(cli): improve pipx detection` or `feat(second-brain): wire proactive context`.
- Explain the user-visible change, list the tests you ran, and call out installer
  safety implications (file writes, merge behavior, network commands).
- Installer changes must preserve existing user files unless a manifest proves
  ownership, and dry-run paths must stay side-effect free.

## Adding a new kit

A copy-only kit (managed files, no config merging) is a `core.CopyKit(...)`
declaration in `agents/installer_core.py` plus four one-line wrappers; see
`agents/kits/codex/installer.py`. Extra install flags are declared in
`INSTALL_OPTIONS` in `agents/kit_registry.py` (flag -> installer kwarg).

The simplest kits (Claude Code / OpenCode shape) export four functions. The
`second-brain` kit is the canonical example for kits that need a fake
`home` parameter for testing, environment-variable overrides, multiple
agent config adapters, and a safe-scaffold pattern that never deletes user
data. Read its `installer.py` before designing a new kit of similar scope.

1. **Create the installer module** at `agents/kits/<kit_name>/installer.py` exporting four functions (the canonical signature, shared by every kit):
   - `install(home=None, dry_run=False, yes=False, **kwargs) -> int`
   - `diff_kit(home=None) -> int`
   - `doctor(home=None) -> int`
   - `uninstall(home=None, dry_run=False, yes=False, **kwargs) -> int`

   For kits that merge agent config snippets, gate the merge behind a
   boolean (the CLI exposes it as `--no-settings`). For kits that scaffold
   user data, treat that data as immutable: `mkdir -p` and
   create-if-absent seeds only; never `rm` or overwrite user files.
2. **Add a `KitSpec`** in `agents/kit_registry.py` pointing to those functions. The spec's `help` text is what shows up in `vibe kits <name> --help`.
3. **Place templates and a manifest** under `agents/kits/<kit_name>/templates/<kit_name>/`:
   - `manifest.json` with `kit`, `version`, `managed_files`, `settings_fragment`, and `secret_policy`
   - All files listed in `managed_files`
4. **Add manifest contract tests** in `tests/test_manifest_contracts.py` asserting every managed file exists and the manifest surface is valid. `tests/test_kit_contract.py` and `MANIFEST.in` check that the kit is packaged and honors the shared signature.
5. **If the kit merges JSON / JSONC / TOML / ENV**, add or reuse a strategy in `agents/merge_strategies.py`. The second-brain kit added `toml_block_merge_strategy` and `strip_toml_block`; reuse them rather than re-implementing.
6. **If the kit needs shared key/secret policy** (the `local-only` and `secret-substring` sets used by both the OpenCode and second-brain JSONC adapters), import from `agents/secret_policies.py` instead of redefining locally.

No CLI dispatch code needs to change: `build_parser(kit_specs=KITS)` reads the registry dynamically.

## Development

```bash
python3 -m unittest discover -s tests -v
```

Inside an activated virtualenv where `python` points to Python 3, `python -m unittest discover -s tests -v` is also acceptable.

You don't need to unset colour variables: the CLI help snapshot tests
neutralise `FORCE_COLOR` / `NO_COLOR` themselves. The publish workflow runs the
test suite before it builds or uploads a release.

The full suite covers kit registry, CLI contract, extension contract, manifest contracts, installer behavior (install / diff / doctor / uninstall) for every kit, and the shared merge strategies. All tests must pass before shipping.
