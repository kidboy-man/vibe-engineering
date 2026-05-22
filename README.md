# Vibe Engineering

Portable engineering kits for AI coding tools.

## Install from GitHub

```bash
pipx install git+https://github.com/kidboy-man/vibe-engineering.git
vibe kits list
vibe kits claude-code doctor
vibe kits claude-code install --dry-run
vibe kits claude-code install --yes
```

## Claude Code Kit

Portable Claude Code setup for senior backend engineering. The kit installs global Claude Code context files, modular rules, custom agents, and slash commands without copying secrets or machine-specific auth/proxy configuration.

### Commands

```bash
vibe kits claude-code doctor
vibe kits claude-code install --dry-run
vibe kits claude-code install --yes
vibe kits claude-code diff
vibe kits claude-code uninstall --yes
```

### What it installs

Managed files are copied into `~/.claude`:

- `CLAUDE.md` global senior/staff backend engineering persona
- `rules/*.md` modular operating, Go backend, security/data, database/ops, testing, and uncertainty/source rules
- `agents/*.md` custom global agents for implementation, tech lead review, security/data review, DB/ops review, and TDD
- `commands/*.md` reusable slash commands
- selected portable skills, currently `skills/vibe-engineering/SKILL.md`
- a manifest at `~/.claude/.vibe-engineering-manifest.json`

### Safety model

This repository intentionally does **not** include or install:

- auth tokens or API keys
- local router/proxy URLs
- project transcripts, histories, tasks, caches, or backups
- local machine-specific MCP auth state
