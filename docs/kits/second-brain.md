# Second-Brain Kit

[← Back to README](../../README.md)

Local-first Obsidian + qmd vault with safe AI-agent config snippets. The
kit creates a vault scaffold, seeds three wiki pages, and merges a
non-secret `qmd` MCP entry into Claude Code, OpenCode, Codex CLI, and Cursor
configs. When qmd is on PATH, `install` verifies the wiki collection and runs
`qmd update`. Installing qmd itself is opt-in: pass `--setup-deps` and, when qmd
is not found, `install` prompts then runs `npm install -g @tobilu/qmd` (with a
timeout). `--yes` alone never installs anything. `--no-setup-deps` is still
accepted as a deprecated no-op; no other network commands (`pip`, `git clone`,
`qmd pull`, `qmd embed`, etc.) are ever run.

The install also adds the portable `second-brain` umbrella skill plus named
wiki skills (`wiki`, `wiki-ingest`, `wiki-query`, `wiki-lint`, and related
workflows) to `$HOME/.agents/skills` and `~/.claude/skills`.

## Vault location

- Default: `~/second-brain`
- Override: `VIBE_SECOND_BRAIN_PATH=/path/to/vault`

The vault is your data. The installer creates it; `uninstall` never
touches it. See the safety contract in the [Safety Model](safety-model.md)
section.

## Commands

```bash
vibe kits second-brain install --dry-run --yes          # show plan, write nothing
VIBE_SECOND_BRAIN_PATH="$HOME/notes" \
    vibe kits second-brain install --yes                 # scaffold vault + agent snippets
vibe kits second-brain diff                              # what would change on next install
vibe kits second-brain doctor                            # health check (qmd, vault, agent configs)
vibe kits second-brain uninstall --yes                   # strip agent snippets + manifest only
```

All four commands accept `--home <path>` to redirect the agent config
root (default `$XDG_CONFIG_HOME` or current user's home), useful for
isolated dry runs in CI. `install` also accepts `--no-settings` to
skip the agent config adapters and only scaffold the vault.

## What it creates in the vault

Directory scaffold (under the vault root, all create-if-absent):

```
raw/assets/                # unprocessed inputs
inbox/                     # new content waiting to be processed
wiki/
├── sources/learning/      # knowledge extracted from articles and talks
├── sources/journal/       # personal reflections
├── entities/projects/     # named projects and codebases
├── concepts/
│   ├── backend/           # extracted backend concepts
│   ├── ai-engineering/    # extracted AI/LLM concepts
│   ├── pkm/               # personal-knowledge-management concepts
│   └── personal/          # personal notes
├── synthesis/             # cross-source notes
├── index.md               # seed: vault map (frontmatter + content)
├── log.md                 # seed: rolling activity log
└── hot.md                 # seed: current focus / "in progress"
output/                    # rendered reports and exports
.claude/                   # local Claude config (separate from ~/.claude)
```

Files written by the installer:

- `.gitignore` — kit entries (`node_modules/`, `.qmd/`, `.claude/settings.local.json`) merged with any existing lines, no duplicates
- `.git/` — `git init -q`, idempotent (skipped if `.git` already exists)
- `.vibe-engineering-manifest.json` — runtime manifest recording what was installed and the safety note that vault data is never uninstall-deleted

Seed pages are created only if absent and never overwritten on reinstall.

## Agent config snippets

The installer merges a `qmd` MCP entry (`command: qmd`, `args: ["mcp"]`)
into each agent's config using a format-specific safe adapter. It adds no
secrets and replaces no keys on purpose; unrelated keys and MCP servers are
preserved, while JSON/JSONC formatting and comments may be normalized.
Existing config files are backed up before a merge rewrites them.

| Agent | Format | Adapter | Scope |
|-------|--------|---------|-------|
| Claude Code | JSON | `json_defaults_strategy` | `~/.claude/settings.json`; skips `env` and secret keys |
| OpenCode | JSONC | `jsonc_defaults_strategy` | `~/.config/opencode/opencode.jsonc`; skips 14 local-only keys + 6 secret substrings |
| Codex CLI | TOML | `toml_block_merge_strategy` | `~/.codex/config.toml`; inserts/replaces `[mcp_servers.qmd]` block only |
| Cursor | JSON + MDC | `cursor_hook_merge_strategy` + kit-owned rule copy + `_merge_cursor_config` | `~/.cursor/hooks.json` sessionStart entry + `~/.cursor/rules/second-brain.mdc` + `~/.cursor/mcp.json` `mcpServers.qmd` entry |
| Hermes | — | docs/sample only | No config mutation anywhere; ship docs only |

## qmd policy

`qmd` is the core search/index dependency. When qmd is on PATH, `install`
checks the wiki collection and runs `qmd update`. Installing qmd is opt-in: with
`--setup-deps`, a missing qmd prompts to run `npm install -g @tobilu/qmd` first.
`--yes` alone never installs dependencies; without `--setup-deps` you'll see the
manual commands below (`--no-setup-deps` is a deprecated no-op). `doctor` returns `1` if `qmd` is missing or its
`collection list` does not point at `<vault>/wiki`.

To install manually (Node.js 22+):

```bash
npm install -g @tobilu/qmd
qmd collection add <vault>/wiki --name second-brain
qmd update                                  # build the initial index
qmd doctor                                  # runtime, model-cache, and GPU diagnostics
```

Hybrid agent retrieval may download local QMD models and temporarily use GPU
compute/VRAM. CPU mode still supports indexing and keyword search; `qmd embed`
and `qmd pull` are never run automatically by this kit.

## Obsidian and memory compiler

- **Obsidian** is an optional visual client. If missing, doctor returns
  `0` with a warning. The vault works with any Markdown editor.
- **Memory compiler** is a docs-only add-on. The installer ships
  installation and hook-configuration docs under `wiki/docs/` but never
  clones, configures, or mutates Claude settings for it.
