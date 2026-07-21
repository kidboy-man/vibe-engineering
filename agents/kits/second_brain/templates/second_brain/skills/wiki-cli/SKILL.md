---
name: wiki-cli
description: Use safe filesystem and qmd commands with the local second-brain vault. Triggers on wiki cli, vault transport, qmd commands, obsidian read, or obsidian write.
---

# Wiki Transport

Derived from `claude-obsidian` v1.9.2 (MIT); adapted for vibe-engineering.

Use normal filesystem tools for vault reads and writes. Use qmd MCP for search. The supported maintenance command is `qmd update` after approved wiki changes.

Obsidian CLI, REST plugins, and custom transport scripts are optional external tooling, not kit requirements. Do not install or configure them unless the user explicitly requests it.
