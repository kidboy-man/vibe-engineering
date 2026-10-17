# Research: Wikify Sync and Drift Checks

Read-first pass over `agents/wikify/{citations,state,commands,plan,gitview,adopt_plan,adopt_refs,
init_cmd,agentmap}.py`, `agents/kits/wikify/{installer.py,templates/wikify/*}` and the hook
`wikify_guard.py`. Line references are to the tree at `a26e381`.

## 1. Which stated gaps are real

| Gap in the request | Verdict | Evidence |
|--------------------|---------|----------|
| Push hook only knows "something outside docs/wiki changed", names no page | Real | `wikify_guard.py:_is_stale` returns a bool; `MESSAGE` is a fixed string |
| Terminal / IDE / CI pushes not covered; hook fails open | Real, by design | `wikify_guard.py` module docstring; `main()` fails open on any exception |
| Shifted lines fail `verify` though the claim is unchanged | Real | `citations._check` requires the symbol inside `start..end`; no relocation exists |
| Imported docs are human blocks and protocol says "never edit" | Real | `adopt_plan.wrap`; `WIKIFY.md` "Adopting existing docs" |
| Edits to imported docs look like tampering | Partly real. `HUMAN BLOCK CHANGED/REMOVED` are **notices, not errors** (`commands._verify` appends them to `notices`), so nothing fails. They are still indistinguishable from real human-block tampering and noisy | `commands._notices` |
| Imported prose never checked against the code | Real | No code reads imported bodies; `citations.parse` strips human blocks |
| Squash merge breaks freshness | Real, and documented as a limitation | `state.py` docstring, `state.is_fresh`/`mixed_base`, `WIKIFY.md` |
| `vibe upgrade` cannot deliver new protocol text | Real | `init_cmd.cmd_init` opens `WIKIFY.md` with `"xb"` (never overwrites); the kit installer manages only the hook and skill in the home directory, not the in-repo `WIKIFY.md` |
| `stale_deleted` exists | Confirmed | `plan.build_plan` computes it from deleted files since the base |

Additional findings that shape the design:

- `state.load` returns only `{"version", "covered"}` and `state.save` rewrites only those two keys,
  so **any new field would be dropped by an old `mark`** and, worse, by the current code on the next
  `mark`. State read/write must preserve unknown and new keys.
- `state.base()` is derived from git (`last commit touching .wikify.json`), not from `covered`, so
  the "since when" for commit attribution is already available.
- The hook is a vendored, stdlib-only script that cannot import `agents`; it duplicates
  `is_fresh`. "Same verdict" therefore has to be achieved by calling the CLI, not by sharing code.
- Citation grammar `(src: path:S-E `Symbol`)` is parsed by `citations.CITE`; changing it would break
  older installs. Hashes therefore go in the state file, not in page text.
- `verify` rejects a moved citation (symbol no longer in range). Constitution III keeps `verify`
  fail-closed, so it is not weakened. `check` classifies instead; `mark --reanchor` heals before
  `verify` runs.

## 2. Decisions

### D1. Range hash baseline lives in `.wikify.json`
- **Decision**: add optional `citations` map keyed `"<page>|<path>:<start>-<end>|<symbol>"` ->
  first 12 hex of sha256 over the cited lines (via `citations.split_lines`, `\n`-joined). Written by
  `mark`. `state.load/save` preserve unknown keys. Version stays `1`.
- **Rationale**: no page-text grammar change; old installs ignore the extra keys; deterministic.
  Keys embed `start-end`, so `reanchor --apply` re-keys moved entries with the same hash in the same
  atomic step (otherwise `changed` detection would go blind between reanchor and `mark`). The state
  file is written with sorted keys, one per line, for readable diffs and merges. No new size cap
  is added (`state.load` has none); roughly 100 bytes per citation.
- **Alternatives**: hash inside the citation text (breaks old parsers); separate baseline file
  (new control file, new ignore/commit surface).
- **Per Q1 clarification**: citations without a stored hash are reported "no range hash yet"
  (non-failing) and still checked for `moved`/`missing` by symbol presence only.

### D2. Classification and relocation algorithm (`drift.py`)
Per citation, against HEAD content of the cited file:
1. File not tracked / not regular at HEAD -> `missing`.
2. Stored hash present: hash the range as cited.
   - equal -> clean;
   - different (including a small shift where the symbol is still inside the old range) -> **always
     run the window search first**: slide a window of the original length over the file and compare the
     sha256 of each window (only windows containing the cited symbol are tried, and a work budget of
     4M line visits makes the search give up with `changed` instead of running away):
     - exactly one match -> `moved` (new start/end), even if the symbol is still in the old range;
     - zero matches -> symbol absent from the file -> `missing`; symbol present -> `changed`;
     - more than one match -> `changed` (ambiguous, never healed).
3. No stored hash: range in bounds and symbol inside -> clean + "no range hash yet" notice; symbol
   not inside the range -> `changed` (cannot prove the body unchanged, so never healed; satisfies
   FR-007). Also counted as `unbaselined_changed` when the cited path changed since the base (see
   D6).
4. `uncovered`: **area-level**, named `uncovered_areas` in JSON to avoid confusion with
   `plan --json`'s file-level `uncovered`. Take tracked, non-ignored, non-secret paths changed in
   `base..HEAD` (all files when there is no base), map each to its context with `plan._contexts`
   (depth 1, or 2 under `src/app/agents/cmd/internal/pkg/lib`), and report a context only if **no
   page cites any path inside it**. Warn-only (spec FR-001a).

Commits attribution: one `git log --format=%h --name-only base..HEAD` call, mapped to cited paths,
capped (e.g. 5 shortest hashes per page); degrades with a message on shallow clones.

- **Alternatives**: symbol-only relocation (cannot prove body unchanged); AST-based symbols (Python
  only; repo in the request is Go). Rolling-window content matching is language-agnostic.

### D3. Exit codes and verdict
`check` exits 1 iff any `changed` or `missing` exists, or an internal error occurs (fail closed in
`--ci`). `moved`, `uncovered`, reference findings, "no range hash yet", map-cap warnings and
imported-page-edited notices never fail. Squash handling falls out: the verdict is structural, not
commit-order based, so a mixed squash commit no longer matters.

Pages are read from the **working tree** in interactive `check`/`sync`, and from **HEAD**
(`git show`/`ls-tree`) in `--ci` mode, the hook and `pre-push`, so a dirty tree cannot change the
verdict for what is being pushed. State hashes follow the same source.

Known tension (documented, accepted): `check` passes with `moved` findings while `verify` still
rejects them. CI should therefore run `check --ci` for the drift gate; `mark` (which runs `verify`)
is where `--reanchor` is applied.

### D4. "Imported" page kind: keep the existing wrapper, add tracking
- **Decision**: keep `adopt`'s representation (`<!-- wikify:human -->` + `<!-- imported from=SRC
  [no-eol] -->` ... `<!-- /wikify:human -->`, recognised by `adopt_plan.unwrap`). A page that is
  exactly one such wrapper is an **imported page** once it is registered in the state file under
  `imported: {"<page>": "<sha256-16 of the page text>"}`. No page rewrite, no marker change, so old
  installs still verify the repo identically.
- **Behaviour**: for a registered imported page, a content mismatch emits
  `IMPORTED PAGE EDITED: <page>` and **suppresses** the wrapper block's
  `HUMAN BLOCK CHANGED/REMOVED` notice (both are notices today, never errors). `mark` re-records
  hashes. Genuine human blocks (any block that is not a registered imported wrapper) keep today's
  notice behaviour and are never touched by any writer. Registered imported wrappers are the only
  human-block-shaped text that `fix-links` may rewrite.
- **adopt**: `adopt --apply` registers the hashes of the pages it creates, so new adoptions never
  need `migrate-imported`.
- **Migration (Q2 answer)**: `vibe wikify migrate-imported` (dry run; `--apply` writes) registers
  hashes for existing wrapped pages. It writes only `.wikify.json`; `mark` never registers pages.
  Until run, wrapped pages behave exactly as today (spec Story 3 scenario 6).
- **Rationale**: smallest change; no rewrite of 29 pages; fully backward compatible.
- **Alternatives**: new `wikify:imported` markers (needs a page rewrite and breaks old verifiers
  with uncited-paragraph errors); a hash-less "kind" inferred only from the provenance line (an
  attacker-controlled line could launder a human block into an editable one).
- **Opt-out**: `.wikify.json` key `"imported_mode": "editable" | "frozen"` (default `editable`).
  In `frozen`, an edit to an imported page is an **error** `IMPORTED PAGE CHANGED (frozen)`. This is
  a deliberate strengthening: today's behaviour is only a notice.

### D5. Reference checking of imported prose (`imported_refs.py`)
Parse the body (inside the wrapper) of every wrapper-shaped page (`adopt_plan.is_wrapped`), registered
or not; checking is read-only. Only `fix-links` is limited to registered pages. Extract backticked
tokens and markdown links. Classify:
- path-shaped token (contains `/`, has an extension, no spaces) not in `git ls-files` -> `DEAD PATH`;
- identifier-shaped token (`[A-Za-z_][\w.]*` with a code-ish shape) not found as a whole word in any
  tracked text file -> `DEAD SYMBOL` (one pass building a word set, files capped by size, secret and
  ignored paths skipped);
- relative link to a missing page/file -> `STALE LINK`.
Report only. Output states name-only matching is a floor (same style as `scan.FLOOR_NOTICE`).
Link fixing is a separate writer command, `fix-links` (not a `check` flag, because `check` is
read-only): rewrite only a `DEAD PATH` whose old path is a **source** in `.wikifymap`
(`adopt_map`/`adopt_refs.rewrite_links` reuse), only inside registered imported pages, dry-run
first.

### D6. Hook and CI enforcement
- `check --ci [--json]`: concise lines, `--json` machine summary, exit per D3, **fail closed** on any
  exception (constitution III v1.1.0).
- Agent hook (`wikify_guard.py`): on a gated push, whenever `vibe` is on `PATH`, run
  `vibe wikify check --ci --json` (HEAD-based, existing time budget) and use **its** verdict, with
  no commit-order pre-filter (a pre-filter would let a docs-only commit with a bad citation pass the
  hook but fail CI).
  - `ok: false` -> block, message = the per-page output.
  - `ok: true` and `counts.unbaselined_changed == 0` -> allow (covers squash merges).
  - `ok: true` and `counts.unbaselined_changed > 0` -> **FR-019 exception**: some cited file changed
    but its citation has no recorded hash, so `check` cannot see body changes. Fall back to today's
    commit-order rule; if it says stale, block with "run `vibe wikify mark` to record range hashes".
    This keeps the existing protection on the first push after an upgrade.
  - error/timeout/missing `vibe` -> today's behaviour (block with the generic message on positive
    commit-order staleness).
  The hook still fails open on its own parse/internal errors (Principle III). `check --ci` itself
  stays non-failing for `unbaselined_changed` (Q1 answer), so CI/`pre-push` are weaker than the hook
  until `mark` records hashes; documented in the migration note.
- `vibe wikify install-hook`: dry run unless `--apply`; resolves the hooks directory via
  `git rev-parse --git-path hooks` and `core.hooksPath` (refuse and report a custom path); refuses
  when `pre-push` already exists (never overwrite); writes a small POSIX `sh` script that runs
  `vibe wikify check --ci` and **fails closed** (a missing `vibe` fails with a clear message).
  `--apply` is the explicit consent; no network.
- Docs: GitHub Actions snippet (`vibe wikify check --ci`) and a design for posting
  `check --json` as a PR comment via an Actions step (no network inside the CLI).

### D7. Protocol delivery to installed repos
`WIKIFY.md` is repo-owned and `init` never overwrites it. Add `vibe wikify init --update-protocol`
(dry run unless `--apply`; see contracts): replace `docs/wiki/WIKIFY.md` only when
its sha256 equals a known earlier shipped version. The frozen hash list in code MUST contain every
version ever shipped, built from `git log --follow -- agents/kits/wikify/templates/wikify/WIKIFY.md`
(a task and a test enumerate the history). Ownership proof (Principle I): this frozen list is the proof that the kit owns the file; any other content is user-owned. Because only a pristine shipped version is ever replaced, nothing user-owned is lost, so no backup file is written (a `.bak` file inside `docs/wiki` would also fail `verify`'s layout check); otherwise report "locally edited, not overwritten" with a diff hint. `check`/`sync` print a
notice when `WIKIFY.md` differs from the shipped template. The kit-installed `wikify-sync` skill
reaches users through the existing `core.install_copy_style_file` path (managed, backed up).

### D8. Map hygiene
`agentmap` already exports `MAX_ENTRIES`/`MAX_BYTES`. `check` adds a non-failing notice at >=80%
of either cap; `sync` suggests per-folder grouping by listing folders with >=5 direct entries
(deterministic, read-only, never creates pages).

### D9. `sync` and the skill
`sync` = `check` + `reanchor` dry run + ordered work list (moved -> changed -> missing ->
uncovered -> reference findings), per page, writing nothing. The `wikify-sync` skill mirrors
`wikify-adopt`'s install path (`SKILL_REL` becomes a tuple of two skills). Skill text enforces: no
invented facts, read the code behind each claim, report doc-versus-code contradictions, never touch
human blocks or generated pages, confirm before the docs-only commit.

### D10. Module layout and size discipline (Principle V)
New small modules under `agents/wikify/`: `drift.py` (classify), `reanchor.py` (plan + apply),
`imported.py` (kind, hashes, migration), `imported_refs.py` (reference findings), `check_cmd.py`
(check/sync rendering), `hookinstall.py`. `state.py` gains key-preserving load/save; `commands.py`
gains dispatch only. No new dependencies.

## 3. Open risks
- Cost on large repos: windowed hashing is O(file length) per drifted citation; mitigate with the
  existing 1 MiB read cap pattern and a per-run citation cap (`MAX_CITATIONS`).
- Hook latency: one extra subprocess only when the cheap test says stale.
- Go specifics: no language parsing is used, so Go repos behave identically.
- `git log --name-only` output size on huge ranges: cap lines and degrade with a notice.
