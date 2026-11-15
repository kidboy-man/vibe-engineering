# Safety Model

[← Back to README](../../README.md)

All kits intentionally do **not** include or install:

- auth tokens, API keys, or passwords
- local router/proxy URLs
- provider / model selection (for OpenCode, also: `plugin`, `mcp`, `theme`, `env`, `permission`, `agent`)
- project transcripts, histories, tasks, caches, or backups
- local machine-specific MCP auth state

For the OpenCode kit, the top-level config keys `model`, `provider`, `plugin`, `mcp`, `tools`, `permission`, `env`, `agent`, `theme`, and any key containing `token`, `key`, `secret`, `password`, `auth`, or `credential` are always preserved as-is. The second-brain kit reuses the same policy via `agents/secret_policies.py`. The Gemini, Codex, and Cursor kits install only portable markdown/text files and never touch settings files or credentials.

The `second-brain` kit additionally guarantees:

- **Controlled package-manager execution**: `second-brain install` installs qmd only when you pass `--setup-deps` (never implied by `--yes`): if qmd is not found it prompts, then runs `npm install -g @tobilu/qmd`; decline the prompt to skip. When qmd is on PATH, install verifies the wiki collection and updates its index. All other kits never run any package-manager command.
- **No other network or install commands**: never runs `git pull`, `git clone`, `qmd embed`, `qmd init`, or starts the qmd MCP daemon
- **No symlinks**: never creates cross-directory symlinks
- **No plugin or Obsidian installs**: `obsidian` is checked by `doctor` but never installed
- **No memory-compiler hooks**: never mutates `.claude/settings.json` for memory-compiler hooks
- **Attributed portable wiki skills**: the kit adapts the MIT-licensed `claude-obsidian` v1.9.2 workflow names to its own qmd vault contract; it does not install the upstream plugin, scripts, or dependencies
- **Vault data is never deleted**: `uninstall` never deletes the vault directory, `.git`, seed pages, `.gitignore`, or any user content under `raw/`, `wiki/`, `output/`. It removes only kit-owned non-secret agent config snippets and the runtime manifest
