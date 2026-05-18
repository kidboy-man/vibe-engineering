# Claude Code Kit

Portable Claude Code setup for senior backend engineering.

Canonical install path through the Python CLI:

```bash
vibe kits claude-code doctor
vibe kits claude-code install --dry-run
vibe kits claude-code install --yes
```

The packaged templates live under `src/vibe_engineering/kits/claude_code/templates/claude` so GitHub/pipx installs include them reliably. This directory keeps the human-facing kit metadata and safety notes.

## Managed content

See `manifest.json` for the file list.

## Secret policy

Do not add credentials, local proxy auth, tokens, project transcripts, or cache files to this kit. Keep it portable and safe to publish.
