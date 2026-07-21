---
name: wiki-retrieve
description: Retrieve relevant local second-brain passages with qmd. Triggers on retrieve, hybrid retrieval, BM25, semantic search, rerank, or find matching notes.
---

# Wiki Retrieval

Derived from `claude-obsidian` v1.9.2 (MIT); adapted for vibe-engineering.

Use qmd MCP `query` as the default hybrid retrieval path. Use `search` for keyword-only lookup when model downloads or GPU work are unwanted. Read the returned pages before relying on them.

`qmd pull` and `qmd embed` are explicit, bulk operations. Do not run either unless the user asks. qmd is the only retrieval engine this kit manages.
