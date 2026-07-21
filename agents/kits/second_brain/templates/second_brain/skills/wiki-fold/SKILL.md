---
name: wiki-fold
description: Roll up a bounded range of second-brain log entries into a linked summary. Triggers on fold the log, run a fold, log rollup, or roll up log entries.
---

# Wiki Fold

Derived from `claude-obsidian` v1.9.2 (MIT); adapted for vibe-engineering.

Read the requested range from `wiki/log.md`, produce an extractive summary that links to its source entries, and show a dry-run in chat first. Only write after the user confirms.

Save confirmed folds in `wiki/synthesis/`, update `wiki/index.md` and `wiki/log.md`, and never rewrite or delete the original log entries.
