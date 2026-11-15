# Codex CLI Kit

[← Back to README](../../README.md)

Portable Codex CLI setup for senior backend engineering. Installs a single
`AGENTS.md` file with the same persona and embedded rules.

## Commands

```bash
vibe kits codex doctor
vibe kits codex install --dry-run
vibe kits codex install --yes
vibe kits codex diff
vibe kits codex uninstall --yes
```

## What it installs

`~/.codex/AGENTS.md` — a single self-contained file with the same structure as
`GEMINI.md` in the [Gemini CLI kit](gemini.md), adapted to Codex CLI conventions. Project-level `AGENTS.md`
files take priority over the global file.
