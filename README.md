# Vibe Engineering

Portable engineering kits for AI coding tools. The `vibe kits` CLI installs
context, rules, agents, and skills into Claude Code, OpenCode, Gemini CLI,
Codex CLI, and Cursor, and scaffolds a local-first Obsidian/qmd second-brain
vault with safe AI-agent config snippets — all without copying secrets or
overwriting your existing config files. The `second-brain` kit optionally runs
`npm install -g @tobilu/qmd` with your consent; all other kits run no network commands.

## Available Kits

| Kit key | Surface | What it does |
|---------|---------|--------------|
| `claude-code` | `vibe kits claude-code …` | Persona, rules, agents, commands, skills into `~/.claude` |
| `opencode` | `vibe kits opencode …` | Same content, adapted to `~/.config/opencode` layout + JSONC merge |
| `gemini` | `vibe kits gemini …` | Self-contained persona + rules into `~/.gemini/GEMINI.md` |
| `codex` | `vibe kits codex …` | Self-contained persona + rules into `~/.codex/AGENTS.md` |
| `cursor` | `vibe kits cursor …` | Seven `.mdc` rule files into `~/.cursor/rules/` |
| `second-brain` | `vibe kits second-brain …` | Local Obsidian/qmd vault scaffold + non-secret AI-agent snippets |
| `workflow` | `vibe kits workflow …` | Business requirement → PRD → TRD → tickets → TDD: `/prd`, `/flow`, `/implement-ticket`, `/push-tickets`, `vibe-flow` skill (Claude Code, OpenCode) |
| `guardrails` | `vibe kits guardrails …` | Pre-tool-use hooks that block destructive commands and secret-file access (Claude Code, Codex CLI, Cursor) |
| `wikify` | `vibe kits wikify …` | Push-gate hook that blocks an agent's `git push` while `docs/wiki` is stale (Claude Code, Codex CLI, Cursor) |

## Install

```bash
pipx install vibe-kits

# Self-upgrade to the latest released version
vibe upgrade
```

```bash
vibe kits list

# Claude Code
vibe kits claude-code doctor
vibe kits claude-code install --yes

# OpenCode
vibe kits opencode doctor
vibe kits opencode install --yes

# Gemini CLI
vibe kits gemini doctor
vibe kits gemini install --yes

# Codex CLI
vibe kits codex doctor
vibe kits codex install --yes

# Cursor IDE
vibe kits cursor doctor
vibe kits cursor install --yes

# Second Brain
vibe kits second-brain install --dry-run --yes
VIBE_SECOND_BRAIN_PATH="$HOME/notes" vibe kits second-brain install --yes
vibe kits second-brain doctor
```

## Claude Code Kit

Portable Claude Code setup for senior backend engineering. The kit installs global Claude Code context files, modular rules, custom agents, and slash commands without copying secrets or machine-specific auth/proxy configuration.

### Commands

```bash
vibe kits claude-code doctor
vibe kits claude-code install --dry-run
vibe kits claude-code install --yes
vibe kits claude-code diff
vibe kits claude-code uninstall --yes
```

### What it installs

Managed files are copied into `~/.claude`:

- `CLAUDE.md` global senior/staff backend engineering persona
- `rules/*.md` modular operating, Go backend, security/data, database/ops, testing, and uncertainty/source rules
- `agents/*.md` custom global agents for implementation, tech lead review, security/data review, DB/ops review, and TDD
- `commands/*.md` reusable slash commands
- selected portable skills, currently `skills/vibe-engineering/SKILL.md`
- a manifest at `~/.claude/.vibe-engineering-manifest.json`

## OpenCode Kit

Portable OpenCode setup for senior backend engineering. Mirrors the Claude Code kit's persona, rules, agents, and commands, adapted to OpenCode's directory layout and config format (`AGENTS.md` for persona, `~/.config/opencode/opencode.jsonc` for config, `~/.config/opencode/{agents,commands,skills,rules}/` for the rest).

### Commands

```bash
vibe kits opencode doctor
vibe kits opencode install --dry-run
vibe kits opencode install --yes
vibe kits opencode diff
vibe kits opencode uninstall --yes
```

### What it installs

Managed files are copied into `$XDG_CONFIG_HOME/opencode` (default: `~/.config/opencode`):

- `AGENTS.md` global senior/staff backend engineering persona
- `rules/*.md` modular operating, Go backend, security/data, database/ops, and testing rules
- `agents/*.md` custom global subagents for tech lead review, Go implementation, security/data review, DB/ops review, and TDD
- `commands/*.md` reusable slash commands (`/trd`, `/review-go`, `/clone-setup`)
- selected portable skills, currently `skills/vibe-engineering/SKILL.md`
- safe non-secret defaults merged into `opencode.jsonc` (`$schema`, `lsp: true`)
- a manifest at `~/.config/opencode/.vibe-engineering-manifest.json`

The installer respects `$XDG_CONFIG_HOME` and ships a JSONC parser that strips `//` and `/* */` comments and trailing commas so it can read your existing `opencode.jsonc` without losing it.

### AGENTS.md merge behavior

Unlike most managed files, `AGENTS.md` is **merged** with any existing file, never overwritten. The installer injects the persona between `<!-- vibe-engineering-kit:begin -->` and `<!-- vibe-engineering-kit:end -->` markers, leaving your own rules above and below untouched. Re-installs replace only the content between the markers, so the persona body can be upgraded without disturbing your local content. `vibe kits opencode uninstall` strips the marked section; if no other content remains, the file is deleted.

```
<!-- vibe-engineering-kit:begin -->
# Global Engineering Persona
...kit content...
<!-- vibe-engineering-kit:end -->
# My Project Rules
...your content (preserved)...
```

## Gemini CLI Kit

Portable Gemini CLI setup for senior backend engineering. Installs a single
`GEMINI.md` file with the full persona, all six engineering rules, and specialist
role descriptions embedded inline — no separate rule files needed since Gemini CLI
reads a single global instructions file.

### Commands

```bash
vibe kits gemini doctor
vibe kits gemini install --dry-run
vibe kits gemini install --yes
vibe kits gemini diff
vibe kits gemini uninstall --yes
```

### What it installs

`~/.gemini/GEMINI.md` — a single self-contained file containing:

- senior/staff backend engineering persona and operating identity
- task risk policy and autonomy boundaries
- all six modular engineering rules (operating model, Go backend, testing, security/data, database/ops, uncertainty/sources) embedded as sections
- specialist role descriptions for all five subagent modes (backend-tech-lead, go-backend-implementer, security-data-reviewer, db-operations-reviewer, tdd-test-engineer)
- communication style and definition of done

Rules are embedded rather than referenced because Gemini CLI loads a single
instructions file rather than a rules directory.

## Codex CLI Kit

Portable Codex CLI setup for senior backend engineering. Installs a single
`AGENTS.md` file with the same comprehensive persona and embedded rules.

### Commands

```bash
vibe kits codex doctor
vibe kits codex install --dry-run
vibe kits codex install --yes
vibe kits codex diff
vibe kits codex uninstall --yes
```

### What it installs

`~/.codex/AGENTS.md` — a single self-contained file with the same structure as
`GEMINI.md` above, adapted to Codex CLI conventions. Project-level `AGENTS.md`
files take priority over the global file.

## Cursor IDE Kit

Portable Cursor IDE setup for senior backend engineering. Installs rule files
into `~/.cursor/rules/` as `.mdc` files. Each file has YAML frontmatter
(`description`, `globs`, `alwaysApply`) so Cursor can selectively load rules
based on file type.

### Commands

```bash
vibe kits cursor doctor
vibe kits cursor install --dry-run
vibe kits cursor install --yes
vibe kits cursor diff
vibe kits cursor uninstall --yes
```

### What it installs

Seven `.mdc` files into `~/.cursor/rules/`:

| File | `alwaysApply` | Scope |
|------|---------------|-------|
| `00-persona.mdc` | `true` | global persona, risk policy, autonomy, definition of done |
| `operating-model.mdc` | `true` | workflow, risk classification, scope discipline |
| `security-and-data-safety.mdc` | `true` | authz, secrets, injection, tenant isolation |
| `uncertainty-and-sources.mdc` | `true` | epistemic honesty, citation standards |
| `go-backend-engineering.mdc` | `false` | Go-specific rules; globs `**/*.go` |
| `testing-and-verification.mdc` | `false` | TDD, test quality; globs test file patterns |
| `database-and-operations.mdc` | `false` | migrations, queries, transactions; globs DB file patterns |

**Note:** Cursor 0.45+ also supports project-local rules at `.cursor/rules/`. For
per-project behavior, copy the relevant `.mdc` files from `~/.cursor/rules/` into
your project's `.cursor/rules/` directory and adjust as needed.

## Workflow Kit

An end-to-end flow from a business requirement to implemented tickets, built from stages you can
run alone or chain with `/flow`. Stages hand off through files with stable IDs, so every ticket traces
back to a requirement.

| Stage | Command | Reads | Writes |
|-------|---------|-------|--------|
| 1. PRD | `/prd` | business requirement (text or file) | `docs/prd/<slug>.md` |
| 2. TRD | `/trd` | the PRD | `docs/trd/<slug>.md` |
| 3. Tickets | `vibe-engineering` skill | the TRD (and PRD) | `.vibe/issues/<slug>/issue-NN.md`, `_metadata.json` |
| 4. Push (optional) | `/push-tickets` | tickets | GitHub issues, only after explicit approval |
| 5. Implement | `/implement-ticket` | one ticket | failing tests, then code; no commit |

`/flow` detects which artifact already exists and continues from there, stopping at a checkpoint
after each stage. `/implement-ticket` does one ticket per run: red (tests from the acceptance
criteria, shown failing for the right reason), green, refactor, verify, then stops for your review.
It uses the `tdd-test-engineer` and `go-backend-implementer` agents when it detects Go, and works
directly otherwise; it finds the test/lint/build commands from your repo.

### Commands

```bash
vibe kits workflow doctor
vibe kits workflow install --dry-run
vibe kits workflow install --yes
vibe kits workflow diff
vibe kits workflow uninstall --yes
```

Installs only into agent config directories that already exist (`~/.claude`, and OpenCode's
`opencode` config dir). `/trd` and the `vibe-engineering` skill come from the `claude-code` /
`opencode` kits; install those too. `doctor` warns when they are missing. Upgrade both kits together:
this release adds requirement IDs and ticket dependencies to `/trd` and `vibe-engineering`.

### The trail and its validator

- PRD requirements are `### R-001: Title` headings with a `Priority: Must|Should|Could` line.
- The TRD gets a `prd:` link and a `## Traceability` table (requirement, design section, test cases).
- Tickets gain `id`, `implements`, `blocked_by`, `size`, `status` frontmatter. All are optional;
  older ticket files keep working without traceability.

`check_trace.py` (installed with the `vibe-flow` skill) is deterministic and standard-library only. It
fails on duplicate IDs, unknown `blocked_by`/`implements` IDs, dependency cycles, and Must
requirements no ticket implements, and prints a safe implementation order (`--next` prints the next
ready ticket, `--json` is machine-readable):

```bash
python3 ~/.claude/skills/vibe-flow/scripts/check_trace.py \
  --tickets .vibe/issues/<slug> --prd docs/prd/<slug>.md --trd docs/trd/<slug>.md
```

Nothing here commits, pushes, or creates issues without you asking. `/push-tickets` uses your own
`gh` login and shows the exact plan first. The stage prompts themselves are not unit-tested; only the
validator, installer and template contracts are.

## Guardrails Kit

Turns the most important safety rules into enforced hooks instead of advice the
agent can ignore. Installs a guard script and registers it as a pre-tool-use hook
for each agent whose config directory already exists (`~/.claude`, `~/.codex`,
`~/.cursor`); missing agents are skipped, never created.

### Commands

```bash
vibe kits guardrails doctor
vibe kits guardrails install --dry-run
vibe kits guardrails install --yes
vibe kits guardrails install --yes --with-verify   # also gofmt-check Go edits (Claude Code only)
vibe kits guardrails diff
vibe kits guardrails uninstall --yes
```

### What it blocks

Only catastrophic or secret-exposing actions; everything else is allowed.

- `rm -rf` on `/`, `~`, `$HOME`, `.`, `..`, or paths outside the project (`/tmp` is allowed)
- `git push --force` / `-f` (`--force-with-lease` is allowed), `git reset --hard`, `git clean -fdx`
- `DROP` / `TRUNCATE` passed to `psql` / `mysql` from the shell
- Reading, copying, or writing `.env*` (not `.env.example`), `*.pem`, `id_rsa*`, `id_ed25519*`, `~/.aws/credentials`

The guard exits `2` with a reason on stderr, which Claude Code, Codex CLI and
Cursor all treat as "deny". Cursor additionally requires JSON on stdout (empty
output from a permission hook blocks), so its command runs the guard with
`--format=cursor`, which always prints `{"permission": "allow"|"deny", ...}`.
Codex skips new or changed hooks until you trust them once via `/hooks` in the
CLI. The guard fails open on any parse or internal error, and
`VIBE_GUARDRAILS=off` bypasses it for a session. It is a heuristic speed bump,
not a sandbox: shell parsing can be bypassed by obfuscation.

### What it installs

| Agent | Script | Registered in |
|-------|--------|---------------|
| Claude Code | `~/.claude/hooks/vibe-guardrails/guard.py` | `settings.json` `PreToolUse` (Bash, Read, Edit, Write, MultiEdit, NotebookEdit) |
| Codex CLI | `~/.codex/hooks/vibe-guardrails/guard.py` | `config.toml` `[[hooks.PreToolUse]]` (Bash, apply_patch) |
| Cursor | `~/.cursor/hooks/vibe-guardrails/guard.py` | `hooks.json` `beforeShellExecution`, `beforeReadFile`, `preToolUse` (Write) |

`--with-verify` additionally installs `verify.py` and a Claude Code `PostToolUse`
hook that tells the agent when an edited `.go` file is not `gofmt`-clean. Codex and
Cursor are not covered by it. Existing hooks and settings are preserved, changed
files are backed up, and uninstall removes only what this kit registered.

## Wikify Kit

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
```

Push flow: the hook blocks the push, the agent updates `docs/wiki`, runs
`vibe wikify verify` and `vibe wikify mark`, you confirm, a docs-only commit
records the mark, and the push goes through. Freshness rule: the commit that last
touched `.wikify.json` and every commit since it may touch only `docs/wiki/`.

### Agent map and `vibe wikify link`

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
  comments or URLs).
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

Limitations:

- Pushes typed in a plain terminal are not covered.
- The hook checks `HEAD`, not the ref being pushed.
- It is a convenience gate, not a security control, and fails open on errors.
- The verifier is structural, not semantic: one citation covers its whole
  paragraph, fenced code and headings are not checked for citations, and link
  text is not verified. You must still review the wiki.
- The hook gates freshness only; it does not re-run `verify`, so a docs-only
  commit made without `mark`/`verify` passes the gate.
- After a squash merge the wiki reads as stale (the squashed commit mixes code
  with `.wikify.json`): run `vibe wikify mark` and make one docs-only commit.
- The built-in secret scan is a floor, not a complete scanner.
- Codex needs a one-time `/hooks` trust review.
- Cursor's push-time payload shape is unverified; the hook fails open if it differs.

### Doc sources and `vibe wikify docs`

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
  and `.wikifyignore` matches; those always win over `.wikifydocs`.
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
  `expected_pages` raises), `plan` sets `error` and exits 1, and `verify` fails
  with `docs: doc inventory failed: <cause>` instead of blaming every page.
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

## Second-Brain Kit

Local-first Obsidian + qmd vault with safe AI-agent config snippets. The
kit creates a vault scaffold, seeds three wiki pages, and merges a
non-secret `qmd` MCP entry into Claude Code, OpenCode, Codex CLI, and Cursor
configs. When qmd is on PATH, `install` verifies the wiki collection and runs
`qmd update`. Installing qmd itself is opt-in: pass `--setup-deps` and, when qmd
is not found, `install` prompts then runs `npm install -g @tobilu/qmd` (with a
timeout). `--yes` alone never installs anything. `--no-setup-deps` is still
accepted as a deprecated no-op; all other network commands (`qmd`, `pip`,
`git clone`, etc.) are never run.

The install also adds the portable `second-brain` umbrella skill plus named
wiki skills (`wiki`, `wiki-ingest`, `wiki-query`, `wiki-lint`, and related
workflows) to `$HOME/.agents/skills` and `~/.claude/skills`.

### Vault location

- Default: `~/second-brain`
- Override: `VIBE_SECOND_BRAIN_PATH=/path/to/vault`

The vault is your data. The installer creates it; `uninstall` never
touches it. See the safety contract in the [Safety Model](#safety-model)
section.

### Commands

```bash
vibe kits second-brain install --dry-run --yes          # show plan, write nothing
VIBE_SECOND_BRAIN_PATH="$HOME/notes" \
    vibe kits second-brain install --yes                 # scaffold vault + agent snippets
vibe kits second-brain diff                              # what would change on next install
vibe kits second-brain doctor                            # health check (qmd, vault, agent configs)
vibe kits second-brain uninstall --yes                   # strip agent snippets + manifest only
```

All four commands accept `--home <path>` to redirect the agent config
root (default `$XDG_CONFIG_HOME` or current user's home) — useful for
isolated dry runs in CI. `install` also accepts `--no-settings` to
skip the agent config adapters and only scaffold the vault.

### What it creates in the vault

Directory scaffold (under the vault root, all create-if-absent):

```
raw/assets/                # unprocessed inputs
inbox/                     # new content waiting to be processed
wiki/
├── sources/learning/      # knowledge extracted from articles and talks
├── sources/journal/       # personal reflections
├── entities/projects/     # named projects and codebases
├── concepts/
│   ├── backend/           # extracted backend concepts
│   ├── ai-engineering/    # extracted AI/LLM concepts
│   ├── pkm/               # personal-knowledge-management concepts
│   └── personal/          # personal notes
├── synthesis/             # cross-source notes
├── index.md               # seed: vault map (frontmatter + content)
├── log.md                 # seed: rolling activity log
└── hot.md                 # seed: current focus / "in progress"
output/                    # rendered reports and exports
.claude/                   # local Claude config (separate from ~/.claude)
```

Files written by the installer:

- `.gitignore` — kit entries (`node_modules/`, `.qmd/`, `.claude/settings.local.json`) merged with any existing lines, no duplicates
- `.git/` — `git init -q`, idempotent (skipped if `.git` already exists)
- `.vibe-engineering-manifest.json` — runtime manifest recording what was installed and the safety note that vault data is never uninstall-deleted

Seed pages are created only if absent and never overwritten on reinstall.

### Agent config snippets

The installer merges a `qmd` MCP entry (`command: qmd`, `args: ["mcp"]`)
into each agent's config using a format-specific safe adapter. No
secrets or deliberate key replacement — unrelated keys and MCP servers are
preserved, while JSON/JSONC formatting and comments may be normalized.
Existing config files are backed up before a merge rewrites them.

| Agent | Format | Adapter | Scope |
|-------|--------|---------|-------|
| Claude Code | JSON | `json_defaults_strategy` | `~/.claude/settings.json`; skips `env` and secret keys |
| OpenCode | JSONC | `jsonc_defaults_strategy` | `~/.config/opencode/opencode.jsonc`; skips 14 local-only keys + 6 secret substrings |
| Codex CLI | TOML | `toml_block_merge_strategy` | `~/.codex/config.toml`; inserts/replaces `[mcp_servers.qmd]` block only |
| Cursor | JSON + MDC | `cursor_hook_merge_strategy` + kit-owned rule copy + `_merge_cursor_config` | `~/.cursor/hooks.json` sessionStart entry + `~/.cursor/rules/second-brain.mdc` + `~/.cursor/mcp.json` `mcpServers.qmd` entry |
| Hermes | — | docs/sample only | No config mutation anywhere; ship docs only |

### qmd policy

`qmd` is the core search/index dependency. When qmd is on PATH, `install`
checks the wiki collection and runs `qmd update`. Installing qmd is opt-in: with
`--setup-deps`, a missing qmd prompts to run `npm install -g @tobilu/qmd` first.
`--yes` alone never installs dependencies; without `--setup-deps` you'll see the
manual commands below (`--no-setup-deps` is a deprecated no-op). `doctor` returns `1` if `qmd` is missing or its
`collection list` does not point at `<vault>/wiki`.

To install manually (Node.js 22+):

```bash
npm install -g @tobilu/qmd
qmd collection add <vault>/wiki --name second-brain
qmd update                                  # build the initial index
qmd doctor                                  # runtime, model-cache, and GPU diagnostics
```

Hybrid agent retrieval may download local QMD models and temporarily use GPU
compute/VRAM. CPU mode still supports indexing and keyword search; `qmd embed`
and `qmd pull` are never run automatically by this kit.

### Obsidian and memory compiler

- **Obsidian** is an optional visual client. If missing, doctor returns
  `0` with a warning. The vault works with any Markdown editor.
- **Memory compiler** is a docs-only add-on. The installer ships
  installation and hook-configuration docs under `wiki/docs/` but never
  clones, configures, or mutates Claude settings for it.

## Safety Model

All kits intentionally do **not** include or install:

- auth tokens, API keys, or passwords
- local router/proxy URLs
- provider / model selection (for OpenCode, also: `plugin`, `mcp`, `theme`, `env`, `permission`, `agent`)
- project transcripts, histories, tasks, caches, or backups
- local machine-specific MCP auth state

For the OpenCode kit, the top-level config keys `model`, `provider`, `plugin`, `mcp`, `tools`, `permission`, `env`, `agent`, `theme`, and any key containing `token`, `key`, `secret`, `password`, `auth`, or `credential` are always preserved as-is. The second-brain kit reuses the same policy via `agents/secret_policies.py`. The Gemini, Codex, and Cursor kits install only portable markdown/text files and never touch settings files or credentials.

The `second-brain` kit additionally guarantees:

- **Controlled package-manager execution**: `second-brain install` prompts then runs `npm install -g @tobilu/qmd` when qmd is not found, then verifies the wiki collection and updates its index. `second-brain install` only installs qmd when you pass `--setup-deps` (never implied by `--yes`); decline the prompt to skip. All other kits never run any package-manager command.
- **No other network or install commands**: never runs `git pull`, `git clone`, `qmd embed`, `qmd init`, or starts the qmd MCP daemon
- **No symlinks**: never creates cross-directory symlinks
- **No plugin or Obsidian installs**: `obsidian` is checked by `doctor` but never installed
- **No memory-compiler hooks**: never mutates `.claude/settings.json` for memory-compiler hooks
- **Attributed portable wiki skills**: the kit adapts the MIT-licensed `claude-obsidian` v1.9.2 workflow names to its own qmd vault contract; it does not install the upstream plugin, scripts, or dependencies
- **Vault data is sacred**: `uninstall` never deletes the vault directory, `.git`, seed pages, `.gitignore`, or any user content under `raw/`, `wiki/`, `output/`. It removes only kit-owned non-secret agent config snippets and the runtime manifest

## Adding a new kit

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
4. **Add manifest contract tests** in `tests/test_manifest_contracts.py` asserting every managed file exists and the manifest surface is valid.
5. **If the kit merges JSON / JSONC / TOML / ENV**, add or reuse a strategy in `agents/merge_strategies.py`. The second-brain kit added `toml_block_merge_strategy` and `strip_toml_block`; reuse them rather than re-implementing.
6. **If the kit needs shared key/secret policy** (the `local-only` and `secret-substring` sets used by both the OpenCode and second-brain JSONC adapters), import from `agents/secret_policies.py` instead of redefining locally.

No CLI dispatch code needs to change: `build_parser(kit_specs=KITS)` reads the registry dynamically.

## Development

```bash
python3 -m unittest discover -s tests -v
```

Inside an activated virtualenv where `python` points to Python 3, `python -m unittest discover -s tests -v` is also acceptable.

The full suite covers kit registry, CLI contract, extension contract, manifest contracts, installer behavior (install / diff / doctor / uninstall) for every kit, and the shared merge strategies. All tests must pass before shipping.
