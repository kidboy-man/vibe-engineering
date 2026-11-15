# Guardrails Kit

[← Back to README](../../README.md)

Turns the key safety rules into hooks that
check each tool call before it runs. Installs a guard script and registers it as a pre-tool-use hook
for each agent whose config directory already exists (`~/.claude`, `~/.codex`,
`~/.cursor`); missing agents are skipped, never created.

## Commands

```bash
vibe kits guardrails doctor
vibe kits guardrails install --dry-run
vibe kits guardrails install --yes
vibe kits guardrails install --yes --with-verify   # also gofmt-check Go edits (Claude Code only)
vibe kits guardrails diff
vibe kits guardrails uninstall --yes
```

## What it blocks

Only catastrophic or secret-exposing actions; everything else is allowed.

- `rm -rf` on `/`, `~`, `$HOME`, `.`, `..`, or paths outside the project (`/tmp` is allowed)
- `git push --force` / `-f` (`--force-with-lease` is allowed), `git reset --hard`, `git clean -fdx`
- `DROP` / `TRUNCATE` passed to `psql` / `mysql` from the shell
- Reading, copying, or writing `.env*` (not `.env.example`), `*.pem`, `id_rsa*`, `id_ed25519*`, `~/.aws/credentials`

The guard exits `2` with a reason on stderr, which Claude Code, Codex CLI and
Cursor all treat as "deny". Cursor additionally requires JSON on stdout (empty
output from a permission hook blocks), so its command runs the guard with
`--format=cursor`, which always prints `{"permission": "allow"|"deny", ...}`.
Codex skips new or changed hooks until you trust them once via `/hooks` in the
CLI. The guard fails open on any parse or internal error, and
`VIBE_GUARDRAILS=off` bypasses it for a session. It is a heuristic speed bump,
not a sandbox: shell parsing can be bypassed by obfuscation.

## What it installs

| Agent | Script | Registered in |
|-------|--------|---------------|
| Claude Code | `~/.claude/hooks/vibe-guardrails/guard.py` | `settings.json` `PreToolUse` (Bash, Read, Edit, Write, MultiEdit, NotebookEdit) |
| Codex CLI | `~/.codex/hooks/vibe-guardrails/guard.py` | `config.toml` `[[hooks.PreToolUse]]` (Bash, apply_patch) |
| Cursor | `~/.cursor/hooks/vibe-guardrails/guard.py` | `hooks.json` `beforeShellExecution`, `beforeReadFile`, `preToolUse` (Write) |

`--with-verify` additionally installs `verify.py` and a Claude Code `PostToolUse`
hook that tells the agent when an edited `.go` file is not `gofmt`-clean. Codex and
Cursor are not covered by it. Existing hooks and settings are preserved, changed
files are backed up, and uninstall removes only what this kit registered.
