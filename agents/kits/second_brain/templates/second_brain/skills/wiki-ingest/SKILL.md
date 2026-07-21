---
name: wiki-ingest
description: Ingest one source into the local second-brain wiki. Triggers on ingest this, process this source, add this to the wiki, or read and file this.
---

# Wiki Ingestion

Derived from `claude-obsidian` v1.9.2 (MIT); adapted for vibe-engineering.

Read one supplied source or one file in `raw/`. Preserve the source. Create one summary in `wiki/sources/`, then create only the 3-8 useful concept or entity pages, cross-link them, update `wiki/index.md`, append `wiki/log.md`, and refresh `wiki/hot.md`.

Ask before batch ingestion. After an approved write, run `qmd update` when available. Never run `qmd pull` or `qmd embed` without explicit user approval.
