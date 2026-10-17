# CLI Contract: new and changed `vibe wikify` commands

All commands operate on the git repo containing the cwd, are deterministic, make no network calls,
and never print secret-scan rule text. Exit codes: `0` ok, `1` failing verdict or error, `2` usage.

## `vibe wikify check [--ci] [--json]`
Read-only; idempotent; tree byte-identical afterwards.

| Exit | When |
|------|------|
| 0 | no `changed` and no `missing` finding |
| 1 | any `changed` or `missing`, or any internal error (always fail closed here) |

Not failing: `moved`, `uncovered`, reference findings, "no range hash yet", imported-page-edited,
map >= 80% of caps, protocol outdated.

Text output (sections omitted when empty, page names untrusted -> sanitised like `pointer._safe`):

```
drift: 2 page(s)
  technical/auth.md:14: changed  internal/auth/token.go:40-58 `Validate` (a1b2c3d, e4f5a6b)
  domain/orders/rules.md:9: missing  internal/orders/legacy.go:1-20 `Legacy`
moved (auto-healable: vibe wikify reanchor): 1
  architecture/overview.md:5: cmd/api/main.go:12-30 -> 15-33 `main`
uncovered (warning): internal/billing/ (3 files)
references (name-only matching is a floor, not proof): 2
  specs/trd.md:21: DEAD PATH internal/old/handler.go
notices:
  IMPORTED PAGE EDITED: specs/trd.md
  NOTICE: 4 citation(s) have no range hash yet; run vibe wikify mark to record them
```

`--ci` judges pages and state at **HEAD** (not the working tree); interactive `check` reads the
working tree. `counts.unbaselined_changed` = citations without a stored hash whose cited path
changed since the base (used by the hook, see research D6). `--ci`: same data, one line per finding, no section prose, no colour. `--json` (valid with or
without `--ci`) prints one object:

```json
{
  "ok": false,
  "counts": {"moved": 1, "changed": 1, "missing": 1, "uncovered_areas": 1, "references": 2,
             "unbaselined_changed": 0},
  "drift": [{"page": "technical/auth.md", "line": 14, "category": "changed",
             "path": "internal/auth/token.go", "start": 40, "end": 58, "symbol": "Validate",
             "commits": ["a1b2c3d"]}],
  "uncovered_areas": [{"area": "internal/billing", "files": ["internal/billing/x.go"]}],
  "references": [{"page": "specs/trd.md", "line": 21, "kind": "DEAD PATH", "token": "internal/old/handler.go"}],
  "suggestions": ["group docs/wiki/specs/ (9 entries) under specs/index.md"],
  "notices": ["IMPORTED PAGE EDITED: specs/trd.md"],
  "error": null
}
```
Keys are stable; new keys may be added; `error` non-null implies `ok: false`.

## `vibe wikify reanchor [--apply]`
Dry run by default: prints `page:line: path S-E -> S'-E' \`Symbol\`` per healable citation and
`refused: <reason>` per refused one; writes nothing. With `--apply`: rewrites only the digits of
`S-E` inside the `(src: ...)` of healable citations and re-keys the matching `citations` entries
in `.wikify.json` (same hash), using atomic writes, only in pages that are
not generated, and never inside human blocks or imported wrappers. Exit 0 when nothing is refused
or nothing needed healing; 1 when any citation was refused (ambiguous / body changed) so scripts
notice. Refuses on symlinked wiki paths (`state.check_wiki_path`).

## `vibe wikify mark [--reanchor]`
Existing behaviour plus: with `--reanchor`, apply reanchor first, then verify, then record
`covered`, the `citations` hashes and the `imported` hashes of registered pages. Without the flag,
behaviour is unchanged except the extra hashes are recorded after a successful verify.

## `vibe wikify verify`
Unchanged exit semantics. New notice `IMPORTED PAGE EDITED: <page>` replaces the wrapper's
`HUMAN BLOCK CHANGED/REMOVED` notice for registered imported pages. `imported_mode: frozen` turns
an edit into an error line `IMPORTED PAGE CHANGED (frozen): <page>`.

## `vibe wikify migrate-imported [--apply]`
Dry run by default: lists wrapped pages that would be registered. `--apply` writes only
`docs/wiki/.wikify.json` (the `imported` map). Idempotent; never edits a page. (`adopt --apply`
registers the pages it creates itself.)

## `vibe wikify sync`
Runs check logic, a reanchor dry run and prints the ordered work list; writes nothing; exit equals
`check`'s verdict.

```
work list (3):
  1. moved    architecture/overview.md:5   run: vibe wikify reanchor --apply
  2. changed  technical/auth.md:14         read internal/auth/token.go:40-58, update the paragraph
  3. missing  domain/orders/rules.md:9     cited code is gone; ask the user before editing
suggestions: group docs/wiki/specs/ (9 entries) under specs/index.md
```

## `vibe wikify fix-links [--apply]`
Writer, dry run by default (`check` stays read-only). Rewrites only `DEAD PATH` tokens whose old
path is a source in `.wikifymap`, only inside registered imported pages; the next `mark`
re-records those page hashes.

## `vibe wikify install-hook [--apply]`
Dry run prints the target path and script. `--apply` writes `<hooks dir>/pre-push` mode `0755`
only if absent. Refuses (exit 1, explanation) when `core.hooksPath` is set to a path other than the
default, when a hook already exists, or when the repo is not a git repo. The script runs
`vibe wikify check --ci` and exits non-zero on failure or if `vibe` is missing.

## `vibe wikify init --update-protocol [--apply]`
Dry run by default. With `--apply`, replaces `docs/wiki/WIKIFY.md` only if its sha256 matches a
known earlier shipped version; otherwise prints `locally edited; not overwritten`.

## Kit: `vibe kits wikify install`
Also installs `skills/wikify-sync/SKILL.md` for Claude Code, managed like `wikify-adopt`. Manifest
`managed_files` gains the path. `uninstall` removes both unmodified skills. The vendored hook
script changes per D6; its stdin/exit contract is unchanged.

## Frozen / affected contracts
- CLI help snapshots in `tests/fixtures/cli_help/` (`wikify_help.txt` plus new
  `wikify_check_help.txt`, `wikify_reanchor_help.txt`, `wikify_sync_help.txt`,
  `wikify_install-hook_help.txt`, `wikify_migrate-imported_help.txt`, `wikify_fix-links_help.txt`) change intentionally.
- `tests/test_second_brain_contract.py` strings: untouched.
