# OpenCode Kit

[← Back to README](../../README.md)

Portable OpenCode setup for senior backend engineering. Mirrors the Claude Code kit's persona, rules, agents, and commands, adapted to OpenCode's directory layout and config format (`AGENTS.md` for persona, `~/.config/opencode/opencode.jsonc` for config, `~/.config/opencode/{agents,commands,skills,rules}/` for the rest).

## Commands

```bash
vibe kits opencode doctor
vibe kits opencode install --dry-run
vibe kits opencode install --yes
vibe kits opencode diff
vibe kits opencode uninstall --yes
```

## What it installs

Managed files are copied into `$XDG_CONFIG_HOME/opencode` (default: `~/.config/opencode`):

- `AGENTS.md` global senior/staff backend engineering persona
- `rules/*.md` modular operating, Go backend, security/data, database/ops, and testing rules
- `agents/*.md` custom global subagents for tech lead review, Go implementation, security/data review, DB/ops review, and TDD
- `commands/*.md` reusable slash commands (`/trd`, `/review-go`, `/clone-setup`)
- selected portable skills, currently `skills/vibe-engineering/SKILL.md`
- safe non-secret defaults merged into `opencode.jsonc` (`$schema`, `lsp: true`)
- a manifest at `~/.config/opencode/.vibe-engineering-manifest.json`

The installer respects `$XDG_CONFIG_HOME` and ships a JSONC parser that strips `//` and `/* */` comments and trailing commas so it can read your existing `opencode.jsonc` without losing it.

## AGENTS.md merge behavior

Unlike most managed files, `AGENTS.md` is **merged** with any existing file, never overwritten. The installer injects the persona between `<!-- vibe-engineering-kit:begin -->` and `<!-- vibe-engineering-kit:end -->` markers, leaving your own rules above and below untouched. Re-installs replace only the content between the markers, so the persona body can be upgraded without disturbing your local content. `vibe kits opencode uninstall` strips the marked section; if no other content remains, the file is deleted.

```
<!-- vibe-engineering-kit:begin -->
# Global Engineering Persona
...kit content...
<!-- vibe-engineering-kit:end -->
# My Project Rules
...your content (preserved)...
```
