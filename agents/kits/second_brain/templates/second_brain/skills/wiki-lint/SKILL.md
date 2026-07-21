---
name: wiki-lint
description: Check the local second-brain wiki for broken links, orphan pages, stale index entries, and frontmatter gaps. Triggers on lint the wiki, health check, find orphans, or wiki maintenance.
---

# Wiki Lint

Derived from `claude-obsidian` v1.9.2 (MIT); adapted for vibe-engineering.

Inspect `wiki/` for missing wikilink targets, pages absent from `wiki/index.md`, empty required sections, and inconsistent frontmatter. Report findings in chat with file paths and suggested fixes.

Do not edit pages during a lint unless the user asks to apply specific fixes. If a saved report is requested, create it under `wiki/synthesis/` and update the index and log.
