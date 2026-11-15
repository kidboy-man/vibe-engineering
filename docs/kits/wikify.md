# Wikify Kit

[← Back to README](../../README.md)

Keeps a repo's `docs/wiki` in sync with the code. The kit installs a push-gate
hook (`hooks/vibe-wikify/wikify_guard.py`) for each agent whose config directory
already exists (`~/.claude`, `~/.codex`, `~/.cursor`); missing agents are skipped.
The hook blocks an agent's `git push` in repos that opted in with
`docs/wiki/.wikify.json` until the wiki is fresh.

```bash
vibe kits wikify doctor
vibe kits wikify install --dry-run
vibe kits wikify install --yes
vibe kits wikify diff
vibe kits wikify uninstall --yes

vibe wikify init | plan | verify | mark     # per-repo commands
vibe wikify link [--dry-run]                # agent pointer block (see below)
vibe wikify docs [--dry-run]                # outline pages for existing docs (see below)
vibe wikify check [--ci] [--json]           # which pages drifted from the code (read-only)
vibe wikify reanchor [--apply]              # fix line numbers of moved citations
vibe wikify sync                            # check + reanchor preview + ordered work list
vibe wikify migrate-imported [--apply]      # register adopted docs as editable imported pages
vibe wikify fix-links [--apply]             # repoint dead paths in imported pages via .wikifymap
vibe wikify install-hook [--apply]          # pre-push git hook running check --ci
vibe wikify init --update-protocol [--apply]  # refresh WIKIFY.md if it is an unmodified older version
```

## Drift checks and sync

`vibe wikify check` compares every citation with the code at `HEAD` and names the pages
that need work: `moved` (same lines, new numbers; heal with `reanchor`), `changed` (the cited
lines were edited), `missing` (file or symbol gone). It also warns about `uncovered` code areas, edited
imported pages, dead references in imported prose (`DEAD PATH`, `DEAD SYMBOL`, `STALE LINK`; name-only
matching, a floor not proof) and a map near its caps. It exits 1 only for `changed` or `missing`, and
fails closed on any error. `mark` stores a hash of each cited range in `docs/wiki/.wikify.json`, which
is what lets `check` tell `changed` from `moved`; citations without a hash yet are reported as
"no range hash yet" until the next `mark`.

`--ci` judges the committed wiki, so it also works as a CI step and as a git `pre-push` hook (see
[docs/wikify-ci.md](../wikify-ci.md)). The agent hook asks the same check when `vibe` is on `PATH`.
Squash merges no longer need a manual fix: the check judges the tree, not the commit order. The loop an
agent follows is in [docs/wikify-sync-walkthrough.md](../wikify-sync-walkthrough.md); upgrading is
described in [docs/wikify-migration.md](../wikify-migration.md).

Push flow (commit-order fallback; with a recent `vibe` the hook asks `vibe wikify check --ci` first): the hook blocks the push, the agent updates `docs/wiki`, runs
`vibe wikify verify` and `vibe wikify mark`, you confirm, a docs-only commit
records the mark, and the push goes through. `plan` lists what to cover; it does a
full plan, not an incremental one, when the commit that last touched
`.wikify.json` also carries code. A page that is not valid UTF-8 is reported by
`verify` as `<page>: not valid UTF-8`. Freshness rule: the commit that last
touched `.wikify.json` and every commit since it may touch only `docs/wiki/`.
`vibe kits wikify uninstall` unregisters the hooks before it removes the scripts;
if a hook config cannot be edited (invalid JSON, a hand-edited Codex block) it
keeps the scripts and manifest, says why, and exits non-zero rather than leave a
hook pointing at a missing script.

## Control files

All live in `docs/wiki/` and must be committed (a gitignored control file is a
`verify` error, and if git cannot say, `verify` reports "could not determine").

- `.wikify.json`: state written by `mark` (covered files). The commit that last touched it is the freshness base.
- `.wikifyignore`: paths wikify never reads, cites or outlines. A pattern with no
  `/` matches that name at any depth; a `/` inside it or a leading `/` anchors at
  the repo root (`*` never crosses `/`, `**` spans directories); a trailing `/`
  means a directory. `!` negation is not supported. The file is rejected, and
  `verify`, `plan` and `docs` fail closed (`plan` returns an error and no path
  data), when it has `!` lines, more than 200 patterns, a pattern over 200
  characters or with more than 8 wildcards, is not a regular UTF-8 file, or is
  over 64 KiB.
- `.wikify-allow`: reviewed secret-scan false positives, one `<page>|sha256:<16 hex>`
  per line. `verify` prints the exact line for each unallowed hit (`ALLOW-LIST KEY`)
  and never echoes the matched text. Legacy plaintext entries still work and are
  reported as `ALLOW-LIST LEGACY`. Scan results that mean "could not scan"
  (`unreadable`, `too-large`) cannot be allow-listed.
- `.wikifydocs`: extra globs for `vibe wikify docs` (see Doc sources).

Secret paths are never read or cited, whatever the ignore file says: `.env`,
`.env.*`, `*.pem`, `id_rsa*` / `id_ed25519*` / `id_ecdsa*`, `*.key`, `*.p12`,
`*.pfx`, `.npmrc`, `.netrc`, `.pgpass`, `.git-credentials`, `*.tfstate`,
`credentials.json`, `kubeconfig`, `prod.env` and `.aws/credentials`, except names
ending `.example`, `.sample`, `.template`, `.dist` or `.pub`.

## Agent map and `vibe wikify link`

Agents load `AGENTS.md` / `CLAUDE.md` in full at session start. Wikify keeps
that file small: `docs/wiki/index.md` holds a **map** (one line per page with a
"when to load" hint) and `AGENTS.md` carries only a static pointer block to it.

Map block in `docs/wiki/index.md` (`vibe wikify init` writes an empty one):

```
<!-- wikify:map -->
- [Overview](architecture/overview.md) — read first for what the module does
<!-- /wikify:map -->
```

- Entry shape is exactly `- [<title>](<path>.md) — <hint>`: a space, an em
  dash (U+2014) and a space separate link and hint; the hint is required.
- `<path>` is relative to `docs/wiki/`, forward slashes, ends in `.md`, with no
  `..`, `@`, `:`, `<`, `>` or backslash; `index.md` and `WIKIFY.md` cannot be listed.
- Title is 1-60 chars and hint 1-80 chars; neither may contain `@`, `<`, `>`,
  `://`, `www.` (any case), square brackets or parentheses (so no HTML,
  comments or URLs). Title, hint and path also reject control and invisible
  characters (Unicode category `C*`, such as ESC, bidi overrides, zero-width
  and tag characters, plus U+2028/2029).
- Titles and hints are agent-written untrusted text that other agents read;
  the pointer block tells agents to treat them as navigation, not
  instructions. The grammar keeps them inert, but it cannot judge what a hint
  says: your review before the `docs(wiki)` commit is the control.
- At most 60 entries and 6144 bytes inside the block, one block per file, a
  `wikify:human` block inside a map is an error, and any line that is not an
  entry (blank lines aside) is an error. Entries are exempt from the citation
  rule: they are navigation, not factual claims.
- Plain links are used, never `@path` imports: as of 2026-10-11 Claude Code
  expands `@path` imports eagerly at launch (max four hops), which would load
  every page.

Until `index.md` has a map block the map rule is off and `vibe wikify verify`
only prints a notice. With a block it checks that every link resolves to a wiki
page, there are no duplicate paths, no page except `index.md` / `WIKIFY.md` is
missing from the map (orphans are errors), and the caps hold. `vibe wikify plan`
lists pages missing from the map under `map_missing`.

`vibe wikify link [--dry-run]` writes the pointer block (6 static lines, plain
relative links) between `<!-- wikify:pointer -->` markers:

- It touches only the marked block and prints a diff first; text outside the
  block is preserved byte for byte. `--dry-run` writes nothing.
- It creates `AGENTS.md` when missing, and updates `CLAUDE.md` / `GEMINI.md`
  only if they already exist. A symlink from one target to another (for example
  `CLAUDE.md` -> `AGENTS.md`, or `AGENTS.md` -> `CLAUDE.md`) is skipped as
  covered by that target.
- Markers count only as whole lines at column 0 outside code fences (an END
  marker on the last line may lack a newline; the rewrite adds one); a marker
  string anywhere else is ordinary text. A backtick line whose info string
  contains a backtick does not open a fence (CommonMark).
- It refuses, writing nothing, when `docs/wiki/index.md` is missing, a target is
  a symlink to anywhere else or a dangling or looping symlink, has multiple
  hard links, is not valid UTF-8 or not a regular file, has a pointer marker
  inside a code fence, has unbalanced or repeated markers (the refusal names
  the cause), when `AGENTS.md` is gitignored or the git ignore check itself
  fails, or when the backup cannot be made. A gitignored `CLAUDE.md` /
  `GEMINI.md` is local-only, so it is skipped with a note instead. A leading
  BOM and CRLF line endings are preserved; a CRLF file gets a CRLF block.
- Existing files are backed up to `<git-dir>/wikify-backups/<timestamp>/`; the
  path is printed before any file is written. Writes are all-or-nothing: on a
  write failure earlier files are restored, and if that rollback fails the
  backup path is printed again.

Claude Code reads `AGENTS.md` only when no `CLAUDE.md`, `.claude/CLAUDE.md` or
`CLAUDE.local.md` exists in the working directory or above (by default, and
reading `AGENTS.md` at all needs Claude Code v2.1.277 or later; as of
2026-10-11). `link` updates only the root `CLAUDE.md`; it does not touch
`.claude/CLAUDE.md`, `CLAUDE.local.md` or a `CLAUDE.md` above the repo, so a
repo relying on one of those needs the pointer copied there by hand. Codex builds its
instruction chain once at startup from the root down, capped by
`project_doc_max_bytes` (default 32 KiB); Cursor reads root and nested
`AGENTS.md`. Sources: <https://code.claude.com/docs/en/memory>, the OpenAI
Codex AGENTS.md guide (<https://learn.chatgpt.com/docs/agent-configuration/agents-md>),
<https://cursor.com/docs/context/rules>.

Commit the pointer files (`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`) in their own
commit **before** `vibe wikify mark`: they live outside `docs/wiki/`, so a
commit that mixes them with wiki changes (or follows the mark) is not docs-only
and the push gate reads the wiki as stale. `verify` pointer checks (no block anywhere,
an existing target without a block once another has one (gitignored targets
excepted), a block that differs from the template (CRLF endings are fine; a
block written before the hints line was added reads as stale until `link` is
rerun), unusable markers, or a block pointing at a missing index) are notices
only and never change the exit code.

`verify` also prints a read-only size notice for each of `AGENTS.md`,
`CLAUDE.md` and `GEMINI.md` (regular files, not symlinks) over 200 lines
(Claude Code recommends under 200 lines per `CLAUDE.md`) or 32 KiB (the Codex
`project_doc_max_bytes` default for the combined chain), both as of
2026-10-11 from the sources above: it gives the line and KiB count and
lists the three largest `## ` sections by line count (column-0 headings outside
code fences and the pointer block) as candidates to move into wiki pages.
That list is a size ranking, not a judgement of the content, and wikify never
moves the text itself. `verify` reads at most 1 MiB of each file; a larger one
gets a "not analysed" notice.

Map and pointer limitations:

- Map entries are navigation, not verified claims; the verifier does not check
  that a hint matches the page.
- The 60 entry / 6144 byte caps are unmeasured defaults.
- The size notice checks each file on its own; the Codex cap applies to the
  combined chain, so files under 32 KiB each can still exceed it together.
- Tool loading behaviour is documented, not observed live, and may change.
- Case-insensitive filesystems and Windows write semantics are not covered.

Registered as `PreToolUse` (Bash) in Claude Code `settings.json`, `[[hooks.PreToolUse]]`
(`^Bash$`) in Codex `config.toml`, and `beforeShellExecution` in Cursor `hooks.json`.
`VIBE_WIKIFY=off` bypasses it. It coexists with the guardrails kit.

What the hook recognises as a push: `git push` (also `git -C <dir> push` and
`cd <dir> && git push`), after the prefixes `sudo`, `command`, `env`, `nohup`,
`time`, `exec`, `timeout`, `nice`, `ionice`, `stdbuf` and `setsid` (with their
flags and values), `VAR=value` assignments, and leading `(`, `{` or `!`. When a
`cd` or `-C` target cannot be resolved (for example `cd $REPO`), it keeps the
current directory and keeps scanning the rest of the command. `--dry-run`,
`-n`, `-d` and `--delete` pushes are not gated. Commands that wrap the push in a
string (`bash -c 'git push'`, `sh -c`), aliases and scripts are not parsed.

Limitations:

- Pushes typed in a plain terminal are not covered by the agent hook; use `vibe wikify install-hook` or CI.
- The hook checks `HEAD`, not the ref being pushed.
- It is a convenience gate, not a security control, and fails open on errors.
- The verifier is structural, not semantic: one citation covers its whole
  paragraph, fenced code and headings are not checked for citations, and link
  text is not verified. You must still review the wiki.
- The hook gates drift (via `check`) or, without `vibe` or hashes, freshness; it does not re-run
  `verify`, so a docs-only commit made without `mark`/`verify` can pass the gate.
- After a squash merge the commit-order rule reads the wiki as stale (the squashed commit mixes code
  with `.wikify.json`) and `plan` lists everything as uncovered (full plan); `check` still passes when
  nothing drifted. Run `vibe wikify mark` and make one docs-only commit to re-baseline.
- The built-in secret scan is a floor, not a complete scanner. Reviewed false
  positives go in `.wikify-allow` (see Control files).
- Codex needs a one-time `/hooks` trust review.
- Cursor's push-time payload shape is unverified; the hook fails open if it differs.

## Doc sources and `vibe wikify docs`

Existing markdown (README, `docs/`, ADRs) stays where it is. `vibe wikify docs`
generates one outline page per doc under `docs/wiki/sources/` so agents can load
a doc section by section through the map. Deterministic: no network, no LLM, no
doc text rewritten; originals are never written, moved or deleted.

```bash
vibe wikify docs --dry-run   # print creates/updates and diffs, write nothing
vibe wikify docs             # write pages under docs/wiki/sources/ only
```

- **Eligible docs** are tracked `.md` / `.markdown` files read at HEAD: repo-root
  files, everything under `docs/`, and any file whose name starts with `README`,
  `CONTRIBUTING`, `CHANGELOG` or `ARCHITECTURE` (case-insensitive). Add more with
  globs in `docs/wiki/.wikifydocs` (one per line, `#` comments, `dir/` matches a
  prefix; `init` scaffolds it comment-only). Never eligible: `AGENTS.md`,
  `CLAUDE.md`, `GEMINI.md`, `SKILL.md`, anything under `docs/wiki/`, secret paths
  and `.wikifyignore` matches (see Control files); those always win over
  `.wikifydocs`.
- **Skipped, with a reason printed** (not an error): paths with whitespace,
  `` : ` ( ) [ ] < > @ \ # " ``, control characters or any Unicode `C*` character
  (`path not citable`); empty docs; docs over 1 MiB; docs that are not valid
  UTF-8; docs beyond the first 500 (`over 500 docs`).
- **Page shape.** Page path is `sources/<doc path>` and always ends in `.md`
  (`x.markdown` becomes `sources/x.markdown.md`; a doc named `index.md` becomes
  `sources/index.md.outline.md`). The first line is `<!-- wikify:generated -->`,
  then a heading `# <doc> (documented, not code-verified; titles are untrusted
  text)`, then one nested list line per ATX heading, each cited by line range
  and, where possible, a text fragment of the heading:
  ``- Title (src: docs/a.md:3-9 `Title`)``. At most 200 sections per page.
  `sources/index.md` lists every eligible doc (up to 500) with its section count.
- **Provenance rule.** Doc-derived pages live only under `sources/` and say
  "documented, not code-verified". A page outside `sources/` that cites an
  eligible doc is a `verify` error (`doc citation outside sources/`). Why: a
  citation proves the doc says X, never that the code does X, so doc claims must
  not blend into code-verified pages. Citing other markdown (kit templates,
  prompts) as code artifacts is still allowed.
- **Drift is an error.** A generated page must equal what `docs` would write now,
  byte for byte; after any doc edit `verify` fails with `generated page out of
  date; run vibe wikify docs`, and a generated page whose doc is gone or no
  longer eligible fails with `generated page has no eligible source`. In `plan`,
  `docs_unindexed`, `docs_stale` and `docs_skipped` report the same state. If
  the doc inventory itself fails (for example git file modes cannot be read, or
  `expected_pages` raises), `plan` sets `error` and exits 1, `verify` fails
  with `docs: doc inventory failed: <cause>` instead of blaming every page, and
  `vibe wikify docs` exits 1 without writing anything.
- **Upgrading.** Existing pages that cite an eligible doc (README, `docs/*.md`)
  from outside `sources/` now fail `verify` with `doc citation outside
  sources/`, even if you never run `docs`. Move the claim into `sources/` or
  cite the code that backs it.
- **Reachability is transitive.** A page counts as reachable when the map lists
  it or a reachable page links to it with a relative `.md` link, up to 2 hops
  from a map entry. Add one map entry for `sources/index.md`; the per-doc pages
  are reached through its links.
- **Flagged, not deleted.** Generated pages whose source is gone are printed as
  `stale` and left in place; a file in `sources/` without the marker is never
  overwritten (the command refuses). Remove stale pages yourself, after review.
- **Limits.** ATX headings only (setext headings and `.rst` / `.txt` / `.adoc`
  docs are not covered); at most 500 docs, 200 sections per page, 1 MiB per doc
  (unmeasured defaults); the outline restates heading text and does not
  summarise; citing a doc does not verify the code; heading text is untrusted
  data, sanitised and length-capped but still the author's words. Sanitising
  replaces markup characters (including `@`) with a space, so an email address
  in a heading is split rather than reproduced.
- **Known limits.** The provenance check covers only docs that were outlined:
  docs skipped as over the cap, over 1 MiB, not valid UTF-8 or colliding page
  paths can still be cited from code pages. On case-insensitive filesystems,
  directories that differ only in case (`docs/Guide/` vs `docs/guide/`) are not
  detected as colliding. A hand-written page under `sources/` may cite eligible
  docs without the "documented, not code-verified" label.
- **Freshness is unchanged.** Editing a doc is a code-side change after the base
  commit, so the push gate stays stale until you run `docs`, `verify` and `mark`
  and make the docs-only commit.

## Adopting existing docs with `vibe wikify adopt`

`vibe wikify docs` leaves the real docs in `docs/` and the wiki only points at
them. `adopt` moves them into `docs/wiki/` so the wiki is the one tree. The CLI is
deterministic (no model, no network); the judgment is a reviewable mapping file,
`docs/wiki/.wikifymap`, that you or an agent write:

```text
# <glob> -> <folder>/ [kind=spec|adr|reference]   (first match wins)
docs/trd/**  -> specs/trd/  kind=spec
docs/adr/**  -> decisions/  kind=adr
```

```bash
vibe wikify adopt                       # dry run: moves, skips with reasons, inbound refs
vibe wikify adopt --report              # same plan as JSON
vibe wikify adopt --apply               # git mv (staged), wrap bodies, update map, drop outline pages
vibe wikify adopt --apply --rewrite-refs  # also re-point relative links
```

After `--apply` it prints the order to finish in: (1) commit the staged renames
(a pure rename, so `git log --follow` works), (2) `vibe wikify verify` then `mark`,
(3) a docs-only commit. It never commits or pushes.

- **Content is preserved.** Each body is wrapped byte for byte in a
  `<!-- wikify:human -->` block whose first line is `<!-- imported from=<path> -->`. It is
  documented prose, not code-verified. `adopt --apply` records each moved page's content hash in
  `.wikify.json`, so the page is an **imported page**: editing it later is allowed and shows as an
  `IMPORTED PAGE EDITED: <page>` notice (not an error) until `mark` re-records the hash. Docs adopted
  by an earlier version are registered with `vibe wikify migrate-imported --apply`; a repo can set
  `"imported_mode": "frozen"` in `.wikify.json` to make such an edit an error. With `--rewrite-refs`
  the only change adopt itself makes is relative link targets.
- **Dry run by default; never overwrites.** A destination that exists is a `collision` skip.
  A dirty tree or detached HEAD is refused without `--force`. A second run after both commits
  is a no-op; resuming an interrupted run needs `--force`.
- **What stays put** (listed with a reason): files without a rule (`unmapped`), root files
  without an exact rule, `.markdown` files and images (only `.md` pages can live in the wiki;
  links to them are reported as unresolved unless `--rewrite-refs` re-points them), docs read
  by a build or config file, secret-scan hits, and files whose body contains a human-block marker.
- **Outline pages.** Apply removes the `sources/` outline pages of the docs it moves and
  rewrites `sources/index.md`; `--prune-sources` also removes unrelated stale generated pages.
- **Map.** One map entry per page; past 60 entries or 6144 bytes, pages are grouped under
  per-folder `index.md` pages.
- **Skills.** `vibe kits wikify install` also installs the `wikify-adopt` and `wikify-sync` skills into
  `~/.claude/skills` (Claude Code only); a short version of the loops is in `docs/wiki/WIKIFY.md` for
  other agents. The adopt skill never rewrites migrated prose during adopt; the sync skill edits only
  the pages `vibe wikify sync` names. Both report doc-versus-code contradictions as findings.
- **Limits.** Inbound references from code comments, CI files and the root `README.md` are listed,
  never edited. Reference detection matches written-out paths and relative markdown links only.
