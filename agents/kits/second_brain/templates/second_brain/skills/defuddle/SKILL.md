---
name: defuddle
description: Clean a web page before ingesting it into the local second-brain. Triggers on defuddle, clean this page, strip this URL, or remove web clutter.
---

# Clean Web Content

Derived from `claude-obsidian` v1.9.2 (MIT); adapted for vibe-engineering.

Prefer an already-available reader or extraction tool. If `defuddle` is present, use it only for a user-requested URL and save the result under `raw/` before passing it to `wiki-ingest`.

Never install `defuddle-cli`, bypass login walls, or fetch URLs without the user's request.
