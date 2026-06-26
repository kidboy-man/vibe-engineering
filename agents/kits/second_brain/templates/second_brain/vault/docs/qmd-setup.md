# qmd Setup — Local Hybrid Search

[qmd](https://github.com/tobi/qmd) combines BM25 full-text search, vector semantic search, and LLM reranking. All running locally. No cloud, no API keys, no indexing service.

## Prerequisites

- **Node.js >= 22** — required runtime
- **npm 9+** or **bun** — package manager

## Install

```bash
# npm
npm install -g @tobilu/qmd

# or bun
bun install -g @tobilu/qmd

# Verify
qmd --version
```

## Configure the Vault

```bash
# Index the wiki folder (run once)
qmd collection add wiki <vault>/wiki --name second-brain

# Build the initial index
qmd update

# Smoke test
qmd search "test"
```

## Search Modes

### BM25 (keyword) — default, no models needed

Works immediately after `qmd update`. Fast, accurate for known terms.

```bash
qmd search "authentication middleware"
```

### Semantic (vector) — optional, ~333 MB model

Run after you have ~15-20 pages. Downloads a GGUF embedding model and reindexes all docs.

```bash
qmd embed        # downloads model, builds vectors (~30s for 20 pages)
qmd search "how do I handle session expiry" --semantic
```

### Hybrid (BM25 + semantic + rerank) — optional, ~2 GB total

Combines keyword and vector results with LLM reranking for best precision.

```bash
qmd search "session management patterns" --hybrid
```

## Maintenance

```bash
# Reindex after new pages
qmd update

# List collections
qmd ls

# Remove a collection
qmd collection remove second-brain
```

## Scoping Note

Always index `<vault>/wiki`, not the vault root. Indexing the root includes schema files (AGENTS.md, CLAUDE.md) in search results, which pollutes answers.
