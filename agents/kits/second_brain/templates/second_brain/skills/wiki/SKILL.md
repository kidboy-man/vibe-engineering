---
name: wiki
description: Set up, inspect, or maintain the local second-brain wiki. Triggers on wiki setup, scaffold vault, create knowledge base, or check wiki status.
---

# Wiki Coordinator

Derived from `claude-obsidian` v1.9.2 (MIT); adapted for vibe-engineering.

The vault is `$VIBE_SECOND_BRAIN_PATH` or `~/second-brain`. Keep human source material in `raw/`; keep generated knowledge in `wiki/`.

For setup/status, verify `wiki/index.md`, `wiki/log.md`, `wiki/hot.md`, and the qmd collection. Use `vibe kits second-brain doctor` for installation health.

Do not replace the vault schema, install plugins, or create a second retrieval stack. Route source work to `wiki-ingest`, questions to `wiki-query`, and maintenance to `wiki-lint`.
