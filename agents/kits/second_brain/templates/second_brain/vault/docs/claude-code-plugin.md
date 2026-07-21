# Optional Claude Code Plugin — claude-obsidian

The second-brain kit already installs portable `second-brain` and named wiki
skills for proactive retrieval, capture, ingestion, querying, and maintenance.
This plugin is optional only for Claude-specific slash commands.

Repository: [https://github.com/AgriciDaniel/claude-obsidian](https://github.com/AgriciDaniel/claude-obsidian)

## Install

```bash
# Step 1: Add the marketplace
claude plugin marketplace add AgriciDaniel/claude-obsidian

# Step 2: Install the plugin
claude plugin install claude-obsidian@agricidaniel-claude-obsidian

# Verify
claude plugin list
```

## What You Get

### Slash Commands (4)

Invoked with `/` prefix in Claude Code:

| Command | Purpose |
|---------|---------|
| `/wiki` | Open wiki session, browse vault |
| `/save` | Save current conversation as a wiki page |
| `/canvas` | Add content to an Obsidian canvas file |
| `/autoresearch` | Run autonomous research loop |

### Portable Agent Skills

The kit installs the named workflows below for compatible agents. Trigger them
with natural language (or `$wiki` in Codex), not a slash command.

| Skill | Trigger Phrases |
|-------|----------------|
| `wiki` | "set up wiki", "scaffold vault", "create knowledge base" |
| `wiki-ingest` | "ingest this", "process this source", "add this to the wiki" |
| `wiki-query` | "what do I know about", "explain", "summarize", "find in wiki" |
| `wiki-lint` | "lint", "health check", "clean up wiki", "find orphans" |
| `wiki-fold` | "fold the log", "run a fold", "log rollup" |
| `wiki-retrieve` | "retrieve", "hybrid retrieval", "BM25", "chunk search" |
| `wiki-mode` | "set vault mode", "switch to PARA", "change mode" |
| `wiki-cli` | "wiki-cli", "obsidian read", "obsidian write", "vault transport" |
| `save` | "save this", "save that answer", "file this", "keep this" |
| `autoresearch` | "autoresearch", "research [topic]", "deep dive" |
| `canvas` | "canvas new", "add to canvas", "create canvas" |
| `defuddle` | "defuddle", "clean this page", "strip this url" |
| `obsidian-markdown` | "write obsidian note", "wikilink", "callout" |
| `obsidian-bases` | "create a base", "obsidian bases", "database view" |

## Slash Commands vs Agent Skills

This is a common point of confusion:

- **Slash commands** require the `/` prefix. Only work in Claude Code.
- **Agent skills** are triggered by natural language phrases declared in their `description:` field. Work in Claude Code, Codex CLI, and OpenCode.

You **cannot** type `/wiki-lint`. That returns "Unknown command." Instead, say "lint the wiki" or "health check my vault."

## Built-in vs Plugin Skills

The kit's `second-brain` and wiki skills are installed globally for compatible
agents. The plugin manages separate Claude slash commands; do not copy plugin
files into this vault or any project.
