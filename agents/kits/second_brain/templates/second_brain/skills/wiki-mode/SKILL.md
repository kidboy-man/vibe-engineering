---
name: wiki-mode
description: Set or inspect the organizational mode of the local second-brain wiki. Triggers on set vault mode, switch to PARA, use Zettelkasten, or wiki methodology mode.
---

# Wiki Mode

Derived from `claude-obsidian` v1.9.2 (MIT); adapted for vibe-engineering.

The default mode is the existing category structure: `wiki/sources/`, `wiki/entities/`, `wiki/concepts/`, and `wiki/synthesis/`. Do not reorganize existing notes automatically.

If the user asks for PARA, LYT, or Zettelkasten, first explain the directory and migration impact. Apply the selected mode only to new notes after explicit approval, and record the decision in `wiki/synthesis/`.
