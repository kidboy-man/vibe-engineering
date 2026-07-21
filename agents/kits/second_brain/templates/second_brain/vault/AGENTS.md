# Vault AGENTS.md

This file tells AI agents how to organize and maintain this second-brain vault.

## Structure

```
raw/          →  human-curated, immutable sources (articles, papers, transcripts)
wiki/         →  LLM-compiled, cross-referenced knowledge pages
  sources/    →  distilled source summaries
  entities/   →  projects, people, organizations, tools
  concepts/   →  ideas, patterns, design decisions
  synthesis/  →  cross-cutting analysis and comparisons
output/       →  generated artifacts (reports, diagrams, exports)
AGENTS.md     →  this file — vault schema and behavior guide
```

## Ingest Behavior

When asked to ingest a source:

1. Read the source file from `raw/` or the provided text.
2. Create **one** source summary page in `wiki/sources/`.
3. Create **3-8** concept/entity pages in the appropriate `wiki/` subfolder.
4. Use `[[wikilinks]]` to connect new pages to existing ones.
5. Update `wiki/index.md` with new page entries.
6. Append an entry to `wiki/log.md`.
7. If `wiki/hot.md` exists, update it with current context.

**Do not batch-ingest multiple sources at once.** Ingest one at a time and stay involved to catch miscategorizations early.

## Query Behavior

When asked a knowledge question:

1. Read `wiki/hot.md` for recent context (if it exists).
2. Read `wiki/index.md` to find relevant pages.
3. Read the 3-5 most relevant pages.
4. Synthesize an answer with citations to wiki pages.
5. Ask if the answer should be filed as a new wiki page.

## qmd Commands

Users run these commands manually for search:

```bash
# Add the wiki collection (run once)
qmd collection add <vault>/wiki --name second-brain

# Update the index (after new pages)
qmd update

# Search (BM25 keyword — no models needed)
qmd search "your query"

# Semantic search (requires embeddings — run `qmd embed` first)
qmd vsearch "your query"
```

## Supported AI Agents

### Claude Code
- `second-brain install` installs the first-party `second-brain` skill under global Agent Skills and Claude-compatible paths.
- The optional `claude-obsidian` plugin adds Claude-specific slash commands; see `docs/claude-code-plugin.md`.
- Start sessions in the vault root so this vault-local `CLAUDE.md`/`AGENTS.md` is read automatically — this covers ingest/query behavior *when working inside the vault*.
- **Global proactive wiring (works in any project, not just the vault):** `second-brain install` offers (interactive prompt, or `vibe kits second-brain enable-hook` standalone) to register a `SessionStart` hook that auto-loads `wiki/hot.md` + `wiki/index.md` into every Claude Code session, plus a marked section in `~/.claude/CLAUDE.md` that tells the agent when to proactively query the vault via the `qmd` MCP tools and when to file learnings back — even outside the vault directory. Both are idempotent and reversible via `uninstall`.

### OpenCode
- Discovers the kit's global `.agents/skills/second-brain` skill automatically.
- Register qmd MCP in `opencode.jsonc`.
- **Global proactive wiring:** `second-brain install` / `enable-hook` merges a marked section into `~/.config/opencode/AGENTS.md` describing the vault and qmd tools. There is no session-start context-injection hook for OpenCode (no documented API for it), so `wiki/hot.md`/`wiki/index.md` are not auto-loaded — read them yourself at session start if needed.

### Codex CLI
- Discovers the kit's global `.agents/skills/second-brain` skill automatically.
- Register qmd MCP in `~/.codex/config.toml`.
- **Global proactive wiring:** `second-brain install` / `enable-hook` registers a `SessionStart` hook (`[[hooks.SessionStart]]` in `~/.codex/config.toml`) that auto-loads `wiki/hot.md` + `wiki/index.md` into every session, plus a marked section in `~/.codex/AGENTS.md`. Both idempotent and reversible via `uninstall`.

### Hermes
- Uses filesystem-first access via native file tools. Set `OBSIDIAN_VAULT_PATH` in `.env` or `.bashrc`.
- No CLI package needed. The built-in `obsidian` skill reads `OBSIDIAN_VAULT_PATH`.

### Cursor
- Copy `agent-snippets/cursor/second-brain.mdc` into each project's `.cursor/rules/second-brain.mdc` for per-project behavior, if you want it scoped to one project instead of globally.
- `AGENTS.md` in the project root also works as a cross-tool alternative.
- `.cursorrules` is deprecated since Cursor 0.45 — migrate to `.cursor/rules/*.mdc`.
- **Global proactive wiring:** `second-brain install` / `enable-hook` manages exactly one global file, `~/.cursor/rules/second-brain.mdc` (`alwaysApply: true`), plus one `sessionStart` entry in `~/.cursor/hooks.json` that auto-loads `wiki/hot.md` + `wiki/index.md` into every session. Both are idempotent and uninstall-reversible (the rule file is only removed if unchanged from the template — hand edits are kept). Avoid hand-adding your own ad hoc global rules beyond what the kit manages.

## Anti-Patterns

- **No batch ingest** — one source at a time.
- **No auto-tags** — tags are deliberate, not inferred.
- **No premature RAG** — BM25 covers the use case until ~30+ pages.
- **No external API calls** without asking first.
- **No overwriting seed pages** — `index.md`, `log.md`, `hot.md` are append/update only.
