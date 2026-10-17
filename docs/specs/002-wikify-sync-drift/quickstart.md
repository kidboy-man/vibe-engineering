# Quickstart: validating wikify sync and drift checks

Prerequisites: `python3 -m pip install -e .`, git, a scratch repo (tests build fixtures with
`tests/wikify_*_helpers.py`-style helpers; no network). Contracts: [contracts/cli.md](contracts/cli.md);
entities: [data-model.md](data-model.md).

## 1. Automated
```
python3 -m unittest discover -s tests
python3 -m unittest tests.test_wikify_drift tests.test_wikify_reanchor tests.test_wikify_imported \
  tests.test_wikify_check_cmd tests.test_wikify_hookinstall tests.test_wikify_hook \
  tests.test_wikify_installer tests.test_wikify_parity tests.test_wikify_control_files \
  tests.test_wikify_skill_walkthrough
```
Expect: all green; CLI help fixtures updated intentionally.

## 2. Manual scenario (mirrors the acceptance fixtures)
In a scratch repo with a wiki that cites `app/svc.py:10-20 \`handle\``:
1. `vibe wikify mark` -> state now has `citations` hashes.
2. Insert 3 lines above line 10, commit. `vibe wikify check` -> exit 0, one `moved`.
   `vibe wikify reanchor` (dry run) shows `10-20 -> 13-23`; `--apply` rewrites digits only; `verify` ok.
3. Edit the body of `handle`, commit. `check` -> exit 1 with `changed` and the commit hash.
4. Delete the file. `check` -> exit 1 with `missing`.
5. Add `app/new/x.py` uncited. `check` -> `uncovered` warning, exit unchanged.
6. Edit a registered imported page. `verify` prints `IMPORTED PAGE EDITED: <page>`, exit 0;
   `mark` clears it. Remove a file an imported doc cites -> `check` lists `DEAD PATH`.
7. Squash two commits (code + `.wikify.json`) -> `check --ci` exits 0; `mark` re-baselines.
8. `vibe wikify install-hook` (dry run) then `--apply`; `git push` of a drifting commit fails.
9. Tree hash (`git status --porcelain` plus `git diff`) is identical before and after any `check`/`sync`.

## 3. `wikify-sync` skill walkthrough
`docs/wiki`-level checked walkthrough lives in the repo docs (T051 writes it; T047 checks it): sync -> edit -> verify
-> mark -> diff -> user confirms -> docs-only commit -> `check` exits 0. A test asserts the listed
commands exist in `--help` output.
