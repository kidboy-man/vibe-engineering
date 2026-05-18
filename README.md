# Vibe Engineering

Portable engineering kits for AI coding tools.

The first kit is `claude-code`: a safe, reusable Claude Code setup for senior backend engineering workflows. It installs global Claude Code context files, modular rules, custom agents, and slash commands without copying secrets or machine-specific auth/proxy configuration.

## Install from GitHub

```bash
pipx install git+https://github.com/<owner>/grill-me.git
vibe kits list
vibe kits claude-code doctor
vibe kits claude-code install --dry-run
vibe kits claude-code install --yes
```

The package also exposes the longer command name:

```bash
vibe-engineering kits claude-code doctor
```

## Claude Code kit commands

```bash
vibe kits list
vibe kits claude-code doctor
vibe kits claude-code diff
vibe kits claude-code install --dry-run
vibe kits claude-code install --yes
vibe kits claude-code install --yes --no-settings
vibe kits claude-code uninstall --dry-run
vibe kits claude-code uninstall --yes
```

Use `--home /path/to/home` to test against a temporary home directory.

## What the Claude Code kit installs

Managed files are copied into `~/.claude`:

- `CLAUDE.md` global senior/staff backend engineering persona
- `rules/*.md` modular operating, Go backend, security/data, database/ops, and testing rules
- `agents/*.md` custom global agents for implementation, tech lead review, security/data review, DB/ops review, and TDD
- `commands/*.md` reusable slash commands
- selected portable skills, currently `skills/vibe-engineering/SKILL.md`
- a manifest at `~/.claude/.vibe-engineering-manifest.json`

The installer can also merge a tiny safe `settings.json` fragment containing non-secret defaults such as model/effort. It only fills missing keys and preserves existing local `env`, provider, token, router, model, and autonomy settings.

## Safety model

This repository intentionally does **not** include or install:

- `~/.claude/.credentials.json`
- auth tokens or API keys
- `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_API_KEY`, or local router/proxy URLs
- `~/.claude/projects`, histories, tasks, caches, paste cache, IDE locks, backups, or transcripts
- local machine-specific MCP auth state

Before overwriting any existing managed file, the installer writes a timestamped backup under:

```text
~/.claude/backups/vibe-engineering/<timestamp>/...
```

Uninstall removes only files that still match the kit templates. Modified files are left in place.

## Development

This CLI is standard-library only for v1.

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e .
python -m vibe_engineering.cli kits list
python -m vibe_engineering.cli kits claude-code doctor --home /tmp/vibe-home
python -m vibe_engineering.cli kits claude-code install --home /tmp/vibe-home --yes
python -m vibe_engineering.cli kits claude-code diff --home /tmp/vibe-home
python -m unittest discover -s tests
```
