# Cursor Setup — Second Brain Integration

Cursor can access the second-brain vault through project-local rule files. This guide covers the recommended approach.

## Recommended: Project-Local `.mdc` Files

Since Cursor 0.45, the preferred method is project-local rules in `.cursor/rules/*.mdc`. Each project that needs vault access gets its own rule file.

### Setup

1. Copy the snippet from `agent-snippets/cursor/second-brain.mdc` into your project:

```bash
cp <vault>/agent-snippets/cursor/second-brain.mdc <your-project>/.cursor/rules/second-brain.mdc
```

2. Edit the copied file to set the correct vault path for your machine.

3. Cursor reads `.cursor/rules/*.mdc` automatically when the project is open.

## Deprecated: `.cursorrules`

The root-level `.cursorrules` file was deprecated in Cursor 0.45. Existing files still work but will not receive updates. Migrate to `.cursor/rules/*.mdc`.

## Cross-Tool Alternative: `AGENTS.md`

If you use multiple AI coding tools (Claude Code, OpenCode, Codex, Cursor), place second-brain instructions in the project's `AGENTS.md` file instead. All agents read `AGENTS.md` automatically. This avoids maintaining separate rule files per tool.

## Do Not Use: Global Rules

**Never use `~/.cursor/rules`** for vault configuration. Global rules are unstable across Cursor versions and can cause unexpected behavior in unrelated projects. Always scope vault rules to specific projects via `.cursor/rules/`.

## What the Rule File Does

The `second-brain.mdc` rule file tells Cursor:

- Where the vault is located (vault path)
- How to use qmd for search (MCP configuration)
- How to read and write wiki pages (wikilink syntax, frontmatter)
- Which anti-patterns to avoid (no batch ingest, no auto-tags)

Each project that needs vault access should have its own copy of this file.
