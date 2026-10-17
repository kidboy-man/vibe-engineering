# Design: `vibe wikify adopt`

Status: decided (task T001). Source of truth for the feature spec in
`docs/specs/001-vibe-kits-baseline/`. Where this document and `research.md`/`data-model.md`
differ, this document wins; those files were updated to match.

## Findings from the verifier source (what the plan assumed vs. what the code does)

| Plan assumption | Code fact | Decision |
|---|---|---|
| Human blocks have no size cap | `citations.human_spans`/`_strip_human` have none; only control files (64 KiB), citations per page (2000) are capped | Option A holds |
| Headings and links inside a human block are tolerated | `_strip_human` blanks the block before the uncited-paragraph check; `agentmap._mask` hides it from reachability | Option A holds, but links inside blocks do not make pages reachable and are never checked |
| `verify` can report adopted pages separately | It cannot; it already reports `HUMAN BLOCK CHANGED` notices for every new block | The provenance comment line plus those notices are the "documented, not code-verified" signal. `adopt --report` lists adopted pages. No verifier change |
| Assets move with docs | `walk_wiki` errors on any non-`.md` file under `docs/wiki/` | Assets never move. Links to them from moved docs are listed in `unresolved_refs` (the verifier cannot catch them: blocks are masked) |
| `.markdown` docs are adoptable | Inventory accepts them, `walk_wiki` accepts only `.md` | Skipped, reason `non-markdown` |
| Root `.md` files are ordinary candidates | Inventory marks any root `.md` default-eligible (README.md, referenced by `pyproject.toml`) | Root files move only if a mapping rule names the exact path; otherwise skipped, reason `root-file` |
| Outline-page removal is optional (`--prune-sources`) | After the move commit the doc sits under `docs/wiki/`, is no longer eligible, and its `sources/` page fails verify with "generated page has no eligible source"; `sources/index.md` goes stale | Apply always removes the outline pages of the docs it moves and rewrites or removes `sources/index.md`. `--prune-sources` stays for unrelated stale generated pages |
| A single docs-only commit works | Freshness allows only docs-only commits after the one touching `.wikify.json`; a rename touches both `docs/` and `docs/wiki/` | Two commits, see below |

## Representation of migrated prose (FR-020): Option A

The body is wrapped verbatim in one human block. The first line inside the block is
`<!-- imported from=<source> -->` (source must satisfy `docs_inventory._citable`).

    <!-- wikify:human -->
    <!-- imported from=docs/trd/x.md -->
    ...original bytes...
    <!-- /wikify:human -->

A body that already contains `<!-- /wikify:human -->` or `<!-- wikify:human -->` is skipped
(reason `unsafe-body`), because wrapping would corrupt the block structure.

## Mapping file `docs/wiki/.wikifymap`

    # comment
    docs/trd/**  ->  specs/trd/        kind=spec
    docs/adr/**  ->  decisions/        kind=adr
    docs/security/** -> technical/security/

- Grammar: `<glob> -> <folder>/ [kind=spec|adr|reference]`; first matching rule wins.
- Destination = folder + the part of the source path after the glob's literal directory prefix
  (`docs/trd/a/b.md` under `docs/trd/**` becomes `specs/trd/a/b.md`).
- `kind` is taken from the rule (default `reference`). No rule means reason `unmapped`; the CLI never
  guesses. `unclassified` in the report is the list of unmapped docs (the agent's work queue).
- Folder is relative to `docs/wiki/`; it must not be absolute, contain `..`, `:` or `\`, start with
  `sources/`, or equal a control file.
- Same limits as `.wikifyignore` (`citations.read_control_lines`, patterns/length/wildcards).
- `.wikifymap` is added to `citations.CONTROL_FILES` and `state.CONTROL_RELS`.

## Skip reasons

`unmapped`, `ignored`, `secret-path`, `secret-hit` (pre-scan with `scan.scan_text`, no allow-listing),
`root-file`, `non-markdown`, `build-coupled` (referenced by a tracked non-markdown config/build file such
as `pyproject.toml`, `Makefile`, `*.toml|json|yaml|yml|cfg|ini|mk`), `collision` (destination exists,
duplicates another move, or differs only by case), `unsafe-body`, `unsafe-path`.
References from source-code comments or markdown are reported in `unresolved_refs`, they do not block a move.

## Sequence and commits

`apply` is validated as a whole first. Then, per move in sorted order: `git mv` (stages a pure rename),
then write the wrapped body (unstaged). Then the map entries, outline-page removal, `sources/index.md`
rewrite, and `verify`.

1. `git commit` the staged renames only. This is commit 1: a pure rename keeps `git log --follow` and
   rename detection intact. With `--rewrite-refs`, edits outside `docs/wiki/` are listed to be added to
   commit 1 as well.
2. `vibe wikify mark`
3. `git add -- docs/wiki` and commit: wrapped bodies, map, outline removal, `.wikify.json`. This is commit 2,
   docs-only. The CLI prints this plan and never commits.

`verify` inside `apply` reads docs at HEAD, so it is a smoke check, not evidence. The acceptance tests
commit, then run `verify`, `mark` and `plan`.

## Dirty tree, resume, idempotence

- Dirty tree or detached HEAD: refuse (exit 1) without `--force`. A clean, already-adopted repo is a no-op
  (exit 0): sources no longer exist at HEAD, so nothing matches.
- Resume after an interrupted run needs `--force`: for each move, if the source is gone and the destination
  exists it counts as moved, and the wrapper is applied if missing. A destination that exists while the
  source also exists is a `collision`.

## `--rewrite-refs`

Default runs leave bodies byte-identical (SC-009 hashes equal). With the flag, relative markdown link
targets are rewritten in moved files and in other tracked docs-only markdown files; the check becomes
"equal after reversing only the link-target substitutions", and `rewritten` link counts are in the report.
Everything that cannot be rewritten is listed, never edited.

## Map

One `<!-- wikify:map -->` entry per page: title from the first heading (falling back to the file stem),
hint `imported from <source>`, both passed through `agentmap._markup_error` rules and the 60/80 char caps.
If entries would exceed 60 or 6144 bytes, entries are grouped under per-folder `index.md` pages containing
link-only lines, and the folder indexes are mapped. A hand-written `<folder>/index.md` blocks grouping.

## Reused checks for untrusted text

`docs_inventory._citable` (provenance path), `scan.scan_text` (secret pre-scan), `agentmap._markup_error`
(titles and hints), `docs_cmd`-style lstat and temp-file writes.
