# Upgrading a wiki to drift checks

Everything here is optional and backward compatible: an existing `docs/wiki/.wikify.json` keeps
working, and the new fields are only written by the new commands.

## What changed in `.wikify.json`

Version stays `1`. New optional keys:

- `citations`: a 12-hex hash of the cited lines per citation (written by `vibe wikify mark`).
- `imported`: a 16-hex hash per imported page (written by `adopt --apply` and `migrate-imported --apply`).
- `imported_mode`: `"editable"` (default) or `"frozen"`. You edit this by hand.

An older `vibe` that runs `mark` rewrites the file without the new keys. That is safe: citations
then read as "no range hash yet" and imported pages as unregistered, until a newer `mark` or
`migrate-imported` runs again.

## Steps

1. `pipx upgrade vibe-kits` (or `vibe upgrade`), then `vibe kits wikify install` to refresh the hook and the skills.
2. `vibe wikify init --update-protocol` (dry run), then `--apply`. It replaces `docs/wiki/WIKIFY.md`
   only if the file is an unmodified older shipped version. A locally edited copy is reported and left alone;
   diff it against the shipped text yourself.
3. `vibe wikify migrate-imported` (dry run), then `--apply`, to register docs that `adopt` moved earlier.
   It writes only `docs/wiki/.wikify.json`.
4. `vibe wikify mark` to record the range hashes, review the diff, make one docs-only commit.
5. Optional: `vibe wikify install-hook` and the CI step in [wikify-ci.md](wikify-ci.md).

## Until step 4 is done

- `vibe wikify check` still works. Citations without a hash are checked for `moved` and `missing`,
  but not for `changed`, and are listed as "no range hash yet".
- The agent push hook keeps its old commit-order rule for any code change under such a citation, so the
  first push after the upgrade is as protected as before.
- `check --ci` and a `pre-push` hook do **not** fail on those unhashed citations, so they are weaker than the
  agent hook until the hashes exist.

## Behaviour changes to know about

- A plain `vibe wikify mark` keeps the old range hash of a citation that only moved and prints a
  notice, so `check` keeps reporting it until you run `reanchor --apply` (or `mark --reanchor`).
- `mark` (and the other state writers) refuse to rewrite a `.wikify.json` that is not valid JSON, for
  example one with merge-conflict markers, instead of silently dropping its settings.
- Registering a page as imported is not enough: a page counts as imported only while it still is
  exactly one `adopt` wrapper. Otherwise it is checked as an ordinary page.
- Imported pages are editable. The line "never edit imported prose" is gone from `WIKIFY.md`.
  `verify` prints `IMPORTED PAGE EDITED: <page>` instead of `HUMAN BLOCK CHANGED`; set
  `"imported_mode": "frozen"` to make such an edit an error.
- After a squash merge `check` passes when nothing drifted; you no longer need a manual `mark` to unblock a push.
  The commit-order rule (`plan`, and the hook when `vibe` is unavailable) is unchanged.
