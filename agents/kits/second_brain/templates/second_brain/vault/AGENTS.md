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
qmd search "your query" --semantic
```

## Supported AI Agents

### Claude Code
- Install the `claude-obsidian` plugin via marketplace (see `docs/claude-code-plugin.md` for exact commands: `claude plugin marketplace add`, `claude plugin install`, `claude plugin list`).
- Provides slash commands (`/wiki`, `/save`, `/canvas`, `/autoresearch`) and agent skills (natural language triggers like "lint the wiki", "ingest this").
- Slash commands require `/` prefix. Skills trigger by natural language — you cannot type `/wiki-lint`; say "lint the wiki" instead.
- Start sessions in the vault root so `CLAUDE.md` is read automatically.

### OpenCode
- Symlink skills from `.claude/skills/` into `~/.config/opencode/skills/`.
- Register qmd MCP in `opencode.jsonc`.

### Codex CLI
- Symlink skills from `.claude/skills/` into `~/.codex/skills/`.
- Register qmd MCP in `~/.codex/config.toml`.

### Hermes
- Uses filesystem-first access via native file tools. Set `OBSIDIAN_VAULT_PATH` in `.env` or `.bashrc`.
- No CLI package needed. The built-in `obsidian` skill reads `OBSIDIAN_VAULT_PATH`.

### Cursor
- Copy `agent-snippets/cursor/second-brain.mdc` into each project's `.cursor/rules/second-brain.mdc`.
- `AGENTS.md` in the project root also works as a cross-tool alternative.
- `.cursorrules` is deprecated since Cursor 0.45 — migrate to `.cursor/rules/*.mdc`.
- Do not use global `~/.cursor/rules` — unstable across versions.

## Anti-Patterns

- **No batch ingest** — one source at a time.
- **No auto-tags** — tags are deliberate, not inferred.
- **No premature RAG** — BM25 covers the use case until ~30+ pages.
- **No external API calls** without asking first.
- **No overwriting seed pages** — `index.md`, `log.md`, `hot.md` are append/update only.
