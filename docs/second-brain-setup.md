# LLM Second-Brain — Setup Guide

> Based on a working implementation bootstrapped on 2026-06-26. This guide documents the exact steps, tool choices, and pitfalls discovered during the live build. Read it once, follow it once, and you'll have a local LLM-maintained second brain that compounds knowledge across every AI agent you use.

---

## About this guide

This is the **source guide** for the `second-brain` kit. The kit
(`vibe kits second-brain install`) now automates the safe-scaffold parts
of this guide — vault directories, seed pages, `.gitignore` merge, git
init, and the non-secret agent config snippets for Claude Code, OpenCode,
and Codex CLI. The kit's shipped templates under
`agents/kits/second_brain/templates/second_brain/vault/docs/` cover the
manual user-facing steps (qmd install, Claude plugin install, Obsidian
install, Cursor sample, memory-compiler add-on).

**Why keep this file?** It preserves the parts that are not duplicated
elsewhere:

- The **pitfalls** section (8 items) — the "why" behind the kit's design
  decisions, including the confirmed WSL2 EISDIR bug with the Obsidian
  forum thread reference.
- The **wishlist** — future work not yet in the kit.
- The **daily workflow** — the intended-use ritual for a second-brain
  vault.
- The **references** — provenance (Karpathy, Cole Medin, Tobi Lütke,
  Steph Ango) and the Agent Skills spec.
- The **first-ingest verification** — the "prove the loop works" step
  that closes the wiring into a working system.

If you are a **user** of the kit, you do not need to read this file —
the README and the kit's `wiki/docs/` templates are enough. If you are a
**maintainer** or **contributor** to the kit, this file is the
authoritative source for the rationale, design tradeoffs, and known
limitations.

---

## What You'll Build

A **local-first Obsidian vault** that acts as a persistent, interlinked knowledge base. Multiple AI agents (Claude Code, Codex CLI, Hermes, OpenCode, Cursor) read and write the same plain Markdown files. The AI agents **ingest sources** into the wiki, **query** it for answers, and **lint** it for consistency — all with natural language, not custom tooling.

```
raw/          →  (human-curated, immutable)  drop articles, papers, transcripts here
wiki/         →  (LLM-compiled, LLM-maintained)  structured, cross-referenced knowledge
AGENTS.md     →  (schema)  tells the LLM how to organize the vault
```

The key promise: **every session can become a source, every answer can become a page, and the wiki compounds with every interaction.**

---

## Prerequisites

| Tool | Why | Check |
|------|-----|-------|
| **Node.js 20+** | qmd search engine + Claude Code plugin installs | `node --version` |
| **npm 9+** | install qmd globally | `npm --version` |
| **git** | version-control the vault (plain text, trivial backup) | `git --version` |
| **uv** (Python package manager) | dependency management for memory-compiler hooks | `uv --version` |
| **Python 3.12+** | memory-compiler hooks use Claude Agent SDK | `python3 --version` |

Optional but strongly recommended:
| **Obsidian** | visual browser for the vault (graph view, wikilink navigation, search) | See OS-specific install below |

---

## Step-by-Step

### 1. Create the Vault Structure

```bash
VAULT=~/second-brain
mkdir -p $VAULT/{raw/assets,inbox,wiki/{sources,entities,concepts,synthesis},output,.claude}
cd $VAULT && git init -q
echo -e "node_modules/\n.qmd/\n.claude/settings.local.json" > .gitignore
```

Pre-create the domain folders you'll use:
```bash
mkdir -p $VAULT/wiki/sources/{learning,journal}
mkdir -p $VAULT/wiki/entities/projects
mkdir -p $VAULT/wiki/concepts/{backend,ai-engineering,pkm,personal}
```

### 2. Install qmd — Local Hybrid Search

[qmd](https://github.com/tobi/qmd) combines BM25 full-text search, vector semantic search, and LLM reranking — all running locally with GGUF models. No cloud, no API keys, no indexing service.

`vibe kits second-brain install` prompts to install qmd automatically when it
is not found. Accept the prompt (or pass `--yes`) and it runs
`npm install -g @tobilu/qmd`, registers the wiki collection, and builds the
initial index for you. Pass `--no-setup-deps` to skip and follow the manual
steps below instead.

To install manually:

```bash
npm i -g @tobilu/qmd
qmd --version                                            # should be >= 2.5.x
qmd collection add wiki ~/second-brain/wiki              # index the wiki folder
qmd update                                               # initial index
qmd search "test"                                        # smoke test
```

**When to use `qmd embed`**: after you cross ~15-20 pages and want semantic ("what was I reading about X") in addition to keyword search. The first run downloads a ~333 MB embedding model and reindexes all docs (~30s for 20 pages).

### 3. Seed the Wiki

Create three meta pages the LLM uses as its operational surface:

- `wiki/index.md` — master catalog (every page listed with a one-line summary)
- `wiki/log.md` — chronological operations log (append-only)
- `wiki/hot.md` — ~500-word rolling session context (prevents the "what was I working on?" recap loop)

Create stub pages for your active projects as `wiki/entities/projects/<name>.md` with YAML frontmatter and `[[wikilinks]]`. This primes the wiki so the first query has anchors to link to.

**Recommended frontmatter format** (consistent across the vault):
```yaml
---
type: concept          # or: source, entity
status: active
created: 2026-06-26
updated: 2026-06-26
tags: [domain, subdomain]
---
```

### 4. Install the Claude Code Plugin (`claude-obsidian`)

This is the engine that turns your CLI agent into a wiki maintainer. It provides **4 slash commands** and **12 agent skills** that trigger via natural language.

The repo: `https://github.com/AgriciDaniel/claude-obsidian`

```bash
# Step 1: add the marketplace
claude plugin marketplace add AgriciDaniel/claude-obsidian

# Step 2: install the plugin
claude plugin install claude-obsidian@agricidaniel-claude-obsidian

# Verify
claude plugin list
```

**What you get:**

| Type | Count | Names | How to invoke |
|------|-------|-------|---------------|
| Slash commands | 4 | `/wiki`, `/save`, `/canvas`, `/autoresearch` | Prefix with `/` |
| Agent skills | ~12 | wiki, wiki-ingest, wiki-query, wiki-lint, wiki-fold, wiki-retrieve, wiki-mode, wiki-cli, save, autoresearch, canvas, defuddle, obsidian-markdown, obsidian-bases, think | Natural language ("lint the wiki", "ingest this", "what do I know about X") |

**Slash commands vs agent skills — the key distinction:**

| | Slash command | Agent skill |
|---|---|---|
| Declared in | `commands/*.md` | `skills/<name>/SKILL.md` |
| Invoked by | `/name` prefix | Natural language trigger phrases in `description:` field |
| Supported on | Claude Code | Claude Code, Codex, OpenCode (Agent Skills spec) |
| Example | `/wiki` — no alternatives | "lint the wiki", "health check", "find orphans" — all trigger wiki-lint |

You **cannot** type `/wiki-lint`. That fails with "Unknown command." Instead, say "lint the wiki" or "health check my vault."

### 5. Wire Multi-Agent Access

All agents share the same plain Markdown files on disk. The wiring just tells each agent where to look.

**Claude Code** (already wired by step 4):
- Plugin is installed globally
- Start any session in `~/second-brain/` and it reads `CLAUDE.md` automatically

**Codex CLI** — symlink the skill directories:
```bash
mkdir -p ~/.codex/skills
for skill in ~/second-brain/.claude/skills/*/; do
  name=$(basename "$skill")
  ln -sf "$skill" "$HOME/.codex/skills/$name"
done
```

**OpenCode** — same symlink pattern:
```bash
for skill in ~/second-brain/.claude/skills/*/; do
  name=$(basename "$skill")
  ln -sf "$skill" "$HOME/.config/opencode/skills/$name"
done
```

**Hermes Agent** — activate its built-in `obsidian` skill (filesystem-first, uses native file tools):
```bash
# Set the vault path persistently
echo 'export OBSIDIAN_VAULT_PATH="$HOME/second-brain"' >> ~/.bashrc
echo 'OBSIDIAN_VAULT_PATH="$HOME/second-brain"' >> ~/.hermes/.env

# The obsidian skill is filesystem-first — it uses read_file / write_file / patch / search_files.
# No CLI package needed. Verify:
hermes skills list | grep obsidian
```

**The Hermes obsidian skill does NOT need the official Obsidian CLI.** The npm packages `@obsidianmd/cli` and `@obsidianmd/obsidian-cli` do not exist on the npm registry. The skill reads `OBSIDIAN_VAULT_PATH` and uses Hermes's native file tools. No app needs to be running.

### 6. Register qmd MCP Server in All Agents

MCP servers expose tools to agents at runtime. Register qmd once per agent:

**Claude Code** (global scope):
```bash
claude mcp add-json qmd '{"type":"stdio","command":"qmd","args":["mcp"]}' --scope user
claude mcp list
```

**Codex CLI** — edit `~/.codex/config.toml`:
```toml
[mcp_servers.qmd]
command = "qmd"
args = ["mcp"]
```

**Hermes Agent** — via the CLI:
```bash
yes | hermes mcp add qmd --command qmd --args mcp
hermes mcp list
```

**OpenCode** — edit `~/.config/opencode/opencode.jsonc`:
```jsonc
{
  // ...existing config...
  "mcp": {
    "qmd": {
      "type": "local",
      "command": "qmd",
      "args": ["mcp"],
      "enabled": true
    }
    // ...other MCP servers...
  }
}
```

Verify: In any agent, the tools `qmd__query`, `qmd__get`, `qmd__multi_get`, and `qmd__status` should be available.

### 7. Install Obsidian (Browser for the Vault)

**WSL2 (Windows 11) — the approach that actually works:**

The "obvious" path — use Windows Obsidian binary and point it at `\\wsl$\Ubuntu\home\<user>\second-brain` via UNC path — is **BROKEN**. It errors with:

```
Error: EISDIR: illegal operation on a directory, watch '\\wsl$\Ubuntu\home\<user>\second-brain'
```

This is a confirmed, unfixed Open issue (Obsidian forum thread 8580, ongoing since 2021). The Windows file-watcher cannot watch 9P-mounted network shares.

**Correct approach for WSL2:** Install Obsidian inside WSL2 using WSLg (Windows 11+ supports Linux GUI apps natively).

```bash
# Download and install the Linux .deb
deb_url=$(curl -s https://api.github.com/repos/obsidianmd/obsidian-releases/releases/latest \
  | grep -oE 'https://[^"]*obsidian_[0-9.]+_amd64\.deb' | head -1)
wget "$deb_url" -O /tmp/obsidian.deb
sudo apt install -y /tmp/obsidian.deb
rm /tmp/obsidian.deb

# Verify
which obsidian
# Launches from Windows Start Menu as "Obsidian (Ubuntu)" or via: obsidian
```

**Non-WSL (macOS / Linux):**
- macOS: `brew install --cask obsidian`
- Linux: `flatpak install flathub md.obsidian.Obsidian` or AppImage from obsidian.md/download

**Set as default vault:**
After opening Obsidian → Manage Vaults → Open folder as vault → `/home/<user>/second-brain`. Edit `~/.config/obsidian/obsidian.json` to add `"lastOpenVault": "<id>"` so Obsidian defaults to this vault on launch.

### 8. Write Your Personal Schema (`CLAUDE.md` / `AGENTS.md`)

The schema tells the LLM how to organize the vault for *your* specific knowledge domains. This is a small file (~70 lines) that you co-evolve with the LLM over time.

A good schema includes:
1. **Who I Am** — your role, current projects, CLI agents you use
2. **My Knowledge Domains** — a table mapping topics → subfolders
3. **Ingest Heuristics** — how the LLM should route a new source (one source → 8-15 wiki pages)
4. **Query Patterns** — the read order (hot cache → index → relevant pages → synthesize → file answer back)
5. **What I Don't Want** — anti-patterns (no batch ingest, no auto-tags, no premature RAG, no external API calls without asking)

Example routing table:
```markdown
| Domain | Folder |
|--------|--------|
| Backend engineering (Go, distributed systems) | `wiki/concepts/backend/` |
| AI engineering / agents / LLMs | `wiki/concepts/ai-engineering/` |
| Knowledge management / PKM | `wiki/concepts/pkm/` |
| Project-specific decisions | `wiki/entities/projects/<name>/` |
| Daily journal / fleeting thoughts | `wiki/sources/journal/` |
```

### 9. Install Memory-Compiler Hooks (Claude Code Only — Optional)

[claude-memory-compiler](https://github.com/coleam00/claude-memory-compiler) automatically captures Claude Code sessions and compiles them into wiki pages. After 6 PM daily, the day's conversations become structured knowledge.

```bash
cd ~/second-brain
git clone https://github.com/coleam00/claude-memory-compiler.git /tmp/cmc
mkdir -p .claude/memory-compiler/{scripts,hooks,daily}
cp /tmp/cmc/scripts/*.py .claude/memory-compiler/scripts/
cp /tmp/cmc/hooks/*.py .claude/memory-compiler/hooks/
cp /tmp/cmc/AGENTS.md .claude/memory-compiler/AGENTS.md
cp /tmp/cmc/pyproject.toml .claude/memory-compiler/pyproject.toml
cp /tmp/cmc/uv.lock .claude/memory-compiler/uv.lock
cd .claude/memory-compiler && uv sync
```

Wire three hooks into `~/second-brain/.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [{
      "matcher": "",
      "hooks": [{
        "type": "command",
        "command": "cd ~/second-brain && uv run --project .claude/memory-compiler python .claude/memory-compiler/hooks/session-start.py 2>/dev/null || true"
      }]
    }],
    "SessionEnd": [{
      "matcher": "",
      "hooks": [{
        "type": "command",
        "command": "cd ~/second-brain && uv run --project .claude/memory-compiler python .claude/memory-compiler/hooks/session-end.py 2>/dev/null || true"
      }]
    }],
    "PreCompact": [{
      "matcher": "",
      "hooks": [{
        "type": "command",
        "command": "cd ~/second-brain && uv run --project .claude/memory-compiler python .claude/memory-compiler/hooks/pre-compact.py 2>/dev/null || true"
      }]
    }]
  }
}
```

**Important:** Memory-compiler writes daily logs and state JSON files. Add these to `.gitignore` or you'll get commit churn on every session end:
```gitignore
.claude/memory-compiler/daily/
.claude/memory-compiler/scripts/*.log
.claude/memory-compiler/scripts/*.json
.claude/memory-compiler/scripts/session-*.md
.claude/memory-compiler/.venv/
```

### 10. Verify the Setup

```bash
# 1. Vault structure
ls ~/second-brain/wiki/index.md  && echo "OK: index.md"  || echo "MISSING: index.md"
ls ~/second-brain/wiki/log.md    && echo "OK: log.md"    || echo "MISSING: log.md"
ls ~/second-brain/wiki/hot.md    && echo "OK: hot.md"    || echo "MISSING: hot.md"

# 2. qmd
qmd ls | grep wiki               && echo "OK: qmd collection"  || echo "MISSING: qmd collection"

# 3. Claude Code plugin
claude plugin list | grep claude-obsidian  && echo "OK: plugin"  || echo "MISSING: plugin"

# 4. qmd MCP in Claude Code
claude mcp list | grep qmd               && echo "OK: qmd MCP"  || echo "MISSING: qmd MCP"

# 5. Obsidian (WSL2 specific)
obsidian --version 2>&1 | head -1        && echo "OK: Obsidian"  || echo "MISSING: Obsidian"
```

### 11. First Ingest — Prove the Loop Works

```bash
# 1. Drop any text into raw/ (an article, paper abstract, book chapter, session transcript)
echo "# My first source..." > ~/second-brain/raw/first-source.md

# 2. In Claude Code (from the vault root):
cd ~/second-brain
claude
# In the session, say:
#   "ingest raw/first-source.md"
# or equivalently:
#   /wiki-ingest raw/first-source.md

# 3. Watch the LLM:
#   - Read the source
#   - Create 1 source page in wiki/sources/
#   - Create 3-8 concept/entity pages with [[wikilinks]]
#   - Update wiki/index.md and wiki/log.md
#   - Cross-reference existing pages

# 4. Verify:
ls wiki/sources/   # new files should appear
qmd update         # reindex
qmd search "<term>"  # new content is now searchable
```

**Anti-pattern to avoid:** Do not batch-ingest multiple sources at once. Karpathy's explicit advice is to ingest one at a time and stay involved — you'll catch miscategorizations early while the wiki is still small.

---

## Daily Workflow

```
Morning:  open Obsidian → read hot.md (last session's context)
Browse:   graph view to see what you know, follow [[wikilinks]]
Capture:  Web Clipper in browser (save articles to raw/)
          or: /save in Claude Code (file the current conversation)
Ingest:   drop file in raw/ → "ingest this" in any agent
Query:    "what do I know about X?" → agent reads index, synthesizes answer
          with citations, asks if you want to file it as a new page
Weekly:   "lint the wiki" → agent finds orphans, dead links, contradictions
```

## Pitfalls Discovered During This Build

1. **Windows Obsidian over `\\wsl$\...` UNC paths fails with EISDIR.** The file-watcher can't watch 9P-mounted shares. Use Obsidian inside WSL2 (WSLg). This is an unfixed, confirmed bug since 2021.

2. **Copying a plugin's `skills/` directory as raw files misses the `commands/` directory.** Plugins have both. Copying only `skills/` gives the LLM knowledge but the user gets "Unknown command" when trying to use slash commands. Install via `claude plugin install`, not raw file copy.

3. **Agent skills and slash commands are NOT interchangeable.** Four skills have slash commands (`/wiki`, `/save`, `/canvas`, `/autoresearch`). The ~12 other skills are triggered by natural language phrases declared in their `description:` field. Trying `/wiki-lint` fails — say "lint the wiki" instead.

4. **Memory-compiler runtime state must be gitignored.** The hooks write `.claude/memory-compiler/daily/`, `*/.log`, `*/.json`, `session-*.md` on every session end. Committing them creates churn with no value.

5. **The npm package `@obsidianmd/cli` does NOT exist.** The Hermes obsidian skill is filesystem-first — it uses `read_file` / `write_file` / `patch` / `search_files`. No CLI install needed.

6. **qmd collection scoping matters.** `qmd collection add wiki ~/second-brain/wiki` indexes the `wiki/` subdirectory. If you accidentally add the whole vault root, schema files (CLAUDE.md, AGENTS.md, WIKI.md) pollute search results.

7. **Obsidian `lastOpenVault` in `obsidian.json` is not auto-set.** After opening the vault, edit `~/.config/obsidian/obsidian.json` and add `"lastOpenVault": "<vault-id>"` so subsequent Obsidian launches open the right vault.

8. **Git `--since="YYYY-MM-DD"` uses midnight as the cutoff.** If you want "all commits today" from a timezone east of UTC, use `--since="24 hours ago"` or `--since=yesterday` instead of a literal date string.

## Wishlist / Not Yet Implemented

- **Web Clipper from Windows browser to WSLg Obsidian** — the browser extension can't reach WSL2's localhost. Needs either `netsh portproxy` on port 27124 OR Web Clipper in "file-path mode" pointing at `\\wsl$\...\raw\`.
- **Image clipboard between Windows screenshots and WSLg Obsidian** — X11/Wayland clipboard sharing is glitchy. Plain text copy/paste works fine.
- **qmd vector embeddings** — run `qmd embed` once you have ~30+ pages. Before that, BM25 keyword search covers the use case.
- **The actual ingest inside a live agent session** — this guide proves the wiring. The "ingest a real source" step (step 11) needs you to actually run it. That first ingest closes the loop.

---

## References

- [Karpathy LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) — the original pattern
- [claude-obsidian](https://github.com/AgriciDaniel/claude-obsidian) — the Claude Code plugin (15 skills, v1.9.2)
- [claude-memory-compiler](https://github.com/coleam00/claude-memory-compiler) — auto-capture sessions into wiki (Cole Medin)
- [qmd](https://github.com/tobi/qmd) — local hybrid search (Tobi Lütke)
- [Obsidian Skills](https://github.com/kepano/obsidian-skills) — teaches LLMs Obsidian-native syntax (Steph Ango)
- [Obsidian forum thread 8580](https://forum.obsidian.md/t/support-for-vaults-in-windows-subsystem-for-linux-wsl/8580) — the EISDIR bug
- [Agent Skills spec](https://agentskills.io/specification) — cross-platform skill standard
