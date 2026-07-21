---
name: obsidian-bases
description: Create Obsidian Bases views over local second-brain notes. Triggers on create a base, Obsidian Bases, database view, or dynamic note table.
---

# Obsidian Bases

Derived from `claude-obsidian` v1.9.2 (MIT); adapted for vibe-engineering.

Use a `.base` file only when the user requests an Obsidian database view. Derive it from existing frontmatter and store it under `output/bases/` so it does not alter the wiki schema.

Validate the requested filters and fields against actual notes; do not install Dataview or another plugin as a prerequisite.
