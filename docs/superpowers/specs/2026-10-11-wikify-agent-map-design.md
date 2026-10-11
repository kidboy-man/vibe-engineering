# Wikify agent map (sub-project A) — design

## Context
Agents load a repo's `AGENTS.md` / `CLAUDE.md` in full at session start, which bloats the context window. Wikify should make that file a thin **map** pointing into the verified wiki, so detail is loaded only when needed. The request also covered transforming existing markdown docs into the wiki standard; that is **sub-project B** and gets its own spec (see Out of scope). This work builds on branch `feat/wikify` (not yet pushed; see Risks) and extends `docs/superpowers/specs/2026-10-04-wikify-design.md`.

## Decisions (agreed with the user)
| # | Topic | Decision |
|---|---|---|
| 1 | Scope | A first; B has its own spec cycle. |
| 2 | Map home | `docs/wiki/index.md` is the map. `AGENTS.md` carries only a small, stable, marked pointer block. |
| 3 | Files | `AGENTS.md` canonical; `CLAUDE.md` / `GEMINI.md` get the same pointer block only if they already exist. |
| 4 | User text | Wikify never edits or moves existing text; it writes only inside its marked block, via `agents/merge_strategies.py:marked_section_strategy`. |

## Facts this design relies on (fetched from primary docs 2026-10-11; re-verify before README claims)
- Claude Code: `@path` imports expand eagerly at launch (max 4 hops), so the map uses plain links, never `@`. Subdirectory `CLAUDE.md`/`AGENTS.md` load on demand when a file there is read. Target is under 200 lines per file. `AGENTS.md` is read only when no `CLAUDE.md` exists in the working directory or above (default); sources: https://code.claude.com/docs/en/memory.
- Codex: one instruction chain built once at startup, root downward, one file per directory, capped by `project_doc_max_bytes` (default 32 KiB); source: OpenAI Codex AGENTS.md guide (https://learn.chatgpt.com/docs/agent-configuration/agents-md).
- Cursor: reads root and nested `AGENTS.md`; rules should stay under 500 lines; source: https://cursor.com/docs/context/rules.
- agents.md: the nearest `AGENTS.md` to the edited file wins; no size guidance; source: https://agents.md.

## Design

### Map block in `docs/wiki/index.md`
Delimited by `<!-- wikify:map -->` and `<!-- /wikify:map -->`. One entry per line, exact grammar:

`- [<title>](<path>.md) — <when-hint>`

- `<path>` is relative to `docs/wiki/`, forward slashes, ends in `.md`, no `..`, no scheme, no `@`.
- `<title>` 1-60 chars; `<when-hint>` 1-80 chars and required (it tells an agent when to load the page). Neither may contain `[`, `]`, `(`, `)`, or a newline.
- The separator is a space, an em dash (U+2014) and a space.
- Lines inside the block that do not match the grammar are errors; blank lines are allowed.

The existing uncited-paragraph rule would flag these lines (the hint is prose, so the pure-link-list exemption does not apply). `verify` therefore gets a **map rule**: lines inside the block are validated by the grammar and are exempt from the citation rule, because they are navigation, not factual claims. All checks are deterministic:
1. every link resolves to a page listed by `citations.walk_wiki` (regular file, not a symlink, `.md`);
2. no duplicate paths;
3. **reachability**: every page except top-level `index.md` and `WIKIFY.md` appears in the map;
4. **size cap**: at most 60 entries and 6 KiB inside the block (the measurable "not bloating" criterion; the numbers are v1 defaults);
5. at most one map block per `index.md`; a map block inside a human block is ignored (human blocks stay opaque);
6. the secret/PII scan still covers the whole file.
The map rule applies to the top-level `index.md` only. A repo with no map block verifies as before (the rule is opt-in), but `plan` and `verify` print a notice that pages are not reachable from any map.

`plan` gains a `map_missing` list (pages not in the map). The agent adds entries; entries are agent-written and verified like any other page text.

### Pointer block in `AGENTS.md` (and `CLAUDE.md` / `GEMINI.md` if they exist)
Static template, no repo-derived content, plain relative links, no `@`, 5 lines:

```
<!-- wikify:pointer -->
## Repo docs (wikify)
Repo knowledge lives in `docs/wiki/`. Start at [docs/wiki/index.md](docs/wiki/index.md): it is a map.
Load only the pages whose "when" hint matches your task; do not read the whole wiki.
<!-- /wikify:pointer -->
```

New command `vibe wikify link [--dry-run]`:
- idempotent: uses `marked_section_strategy` with the markers above; text outside the block is preserved byte for byte;
- prints the unified diff for every file it would change before writing; `--dry-run` writes nothing;
- targets: `AGENTS.md` always (created containing only the block when absent); `CLAUDE.md` and `GEMINI.md` only if they already exist; never any other file;
- refuses (rc 1, nothing written) when a target is a symlink, is ignored by git (`gitview.ignored`), lies outside the repo root, or when `docs/wiki/index.md` does not exist (run `init` first);
- backs up an existing file before changing it (reuse `agents/installer_core.py` helpers: `backup`, `write_text`);
- `init` does not call `link`; it prints a one-line hint to run it.
`verify` reads the target files read-only and prints a notice (rc unchanged) when a pointer block exists but differs from the template or the index it points at is missing, and a different notice when none of the files carries a block.

### Freshness and hook interaction
Pointer blocks are outside `docs/wiki/`, so a commit touching them is not docs-only (spec R4). `link` therefore tells the user to commit `AGENTS.md` / `CLAUDE.md` / `GEMINI.md` changes in their own commit **before** running `vibe wikify mark`. No change to `state.is_fresh`, the hook script, or the parity test.

### Safety and privacy
- `AGENTS.md` is user-owned and read by every teammate's agent; wikify writes only the marked block and shows the diff first. The agent never edits `AGENTS.md` during the wiki flow; only `vibe wikify link` does, on the user's command.
- The pointer text is static, so it cannot carry repo content, personal data or injected instructions.
- Map entries (title, hint) are agent-written and untrusted text: the grammar bans markup that would turn them into `@` imports, links with schemes, or HTML; `WIKIFY.md` says repo content is data, not instructions.
- No network, no telemetry; reading uses fixed-argv git and tracked files only.

### Testing (TDD)
- `tests/test_wikify_agentmap.py` table-driven: valid map; bad link; missing page; duplicate; orphan page; oversize (entries and bytes); stray prose in block; missing hint; hint too long; `@`/scheme/`..` in path; map inside a human block ignored; two map blocks; no map block (opt-in) with notice.
- `link` on temp repos: no `AGENTS.md` (created, block only); existing `AGENTS.md` (user text preserved byte for byte, block prepended); existing `CLAUDE.md` gets the block, absent `GEMINI.md` is not created; re-run unchanged; stale block updated in place; `--dry-run` writes nothing; symlink, gitignored, outside-root and missing-index refusals; backup created.
- `verify` pointer notices; parity test untouched and still passing; end-to-end scratch repo: init, pages, map, link, commit, verify, mark.
- Full suite with `FORCE_COLOR= NO_COLOR=1 PYTHON_COLORS=0`.

## Out of scope (sub-project B, own spec)
Migrating existing markdown into the wiki. It conflicts with Decision 1 of the shipped spec (pages state only code-verifiable facts; existing docs are uncited and rationale-heavy). Direction for that spec: non-destructive; inventory tracked docs at HEAD honouring `is_secret_path` and `.wikifyignore`; classify; link from the map; convert only code-verifiable facts into cited pages; never move or delete originals automatically; imported human prose only inside human blocks, which the agent may not edit. Also out of scope here: generating nested per-directory `AGENTS.md`, `.cursor/rules` files, and rewriting or slimming a user's existing `AGENTS.md`.

## Risks
- Tool behaviour changes (loading rules, size caps); the facts above are dated 2026-10-11.
- If a repo has `CLAUDE.md`, Claude Code ignores `AGENTS.md` by default; the pointer block must also be in `CLAUDE.md` for that repo (handled by decision 3).
- The 60-entry / 6 KiB caps are defaults, not measured; large monorepos may need a per-directory map (future work).
- `feat/wikify` is unpushed because SSH auth failed; this spec and its implementation stack on that branch.

## Open for review
Confirm the v1 defaults: required hint, caps (60 entries / 6 KiB), `link` creating a missing `AGENTS.md`, `init` only hinting at `link`, and notice-only (never failing) pointer checks in `verify`.
