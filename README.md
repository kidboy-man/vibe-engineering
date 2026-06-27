# Vibe Engineering

Portable engineering kits for AI coding tools. The `vibe kits` CLI installs
context, rules, agents, and skills into Claude Code, OpenCode, Gemini CLI,
Codex CLI, and Cursor, and scaffolds a local-first Obsidian/qmd second-brain
vault with safe AI-agent config snippets — all without copying secrets or
overwriting your existing config files. The `second-brain` kit optionally runs
`npm install -g @tobilu/qmd` with your consent; all other kits run no network commands.

## Available Kits

| Kit key | Surface | What it does |
|---------|---------|--------------|
| `claude-code` | `vibe kits claude-code …` | Persona, rules, agents, commands, skills into `~/.claude` |
| `opencode` | `vibe kits opencode …` | Same content, adapted to `~/.config/opencode` layout + JSONC merge |
| `gemini` | `vibe kits gemini …` | Self-contained persona + rules into `~/.gemini/GEMINI.md` |
| `codex` | `vibe kits codex …` | Self-contained persona + rules into `~/.codex/instructions.md` |
| `cursor` | `vibe kits cursor …` | Seven `.mdc` rule files into `~/.cursor/rules/` |
| `second-brain` | `vibe kits second-brain …` | Local Obsidian/qmd vault scaffold + non-secret AI-agent snippets |

## Install from GitHub

```bash
pipx install git+https://github.com/kidboy-man/vibe-engineering.git
vibe kits list

# Claude Code
vibe kits claude-code doctor
vibe kits claude-code install --yes

# OpenCode
vibe kits opencode doctor
vibe kits opencode install --yes

# Gemini CLI
vibe kits gemini doctor
vibe kits gemini install --yes

# Codex CLI
vibe kits codex doctor
vibe kits codex install --yes

# Cursor IDE
vibe kits cursor doctor
vibe kits cursor install --yes

# Second Brain
vibe kits second-brain install --dry-run --yes
VIBE_SECOND_BRAIN_PATH="$HOME/notes" vibe kits second-brain install --yes
vibe kits second-brain doctor
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

## OpenCode Kit

Portable OpenCode setup for senior backend engineering. Mirrors the Claude Code kit's persona, rules, agents, and commands, adapted to OpenCode's directory layout and config format (`AGENTS.md` for persona, `~/.config/opencode/opencode.jsonc` for config, `~/.config/opencode/{agents,commands,skills,rules}/` for the rest).

### Commands

```bash
vibe kits opencode doctor
vibe kits opencode install --dry-run
vibe kits opencode install --yes
vibe kits opencode diff
vibe kits opencode uninstall --yes
```

### What it installs

Managed files are copied into `$XDG_CONFIG_HOME/opencode` (default: `~/.config/opencode`):

- `AGENTS.md` global senior/staff backend engineering persona
- `rules/*.md` modular operating, Go backend, security/data, database/ops, and testing rules
- `agents/*.md` custom global subagents for tech lead review, Go implementation, security/data review, DB/ops review, and TDD
- `commands/*.md` reusable slash commands (`/trd`, `/review-go`, `/clone-setup`)
- selected portable skills, currently `skills/vibe-engineering/SKILL.md`
- safe non-secret defaults merged into `opencode.jsonc` (`$schema`, `lsp: true`)
- a manifest at `~/.config/opencode/.vibe-engineering-manifest.json`

The installer respects `$XDG_CONFIG_HOME` and ships a JSONC parser that strips `//` and `/* */` comments and trailing commas so it can read your existing `opencode.jsonc` without losing it.

### AGENTS.md merge behavior

Unlike most managed files, `AGENTS.md` is **merged** with any existing file, never overwritten. The installer injects the persona between `<!-- vibe-engineering-kit:begin -->` and `<!-- vibe-engineering-kit:end -->` markers, leaving your own rules above and below untouched. Re-installs replace only the content between the markers, so the persona body can be upgraded without disturbing your local content. `vibe kits opencode uninstall` strips the marked section; if no other content remains, the file is deleted.

```
<!-- vibe-engineering-kit:begin -->
# Global Engineering Persona
...kit content...
<!-- vibe-engineering-kit:end -->
# My Project Rules
...your content (preserved)...
```

## Gemini CLI Kit

Portable Gemini CLI setup for senior backend engineering. Installs a single
`GEMINI.md` file with the full persona, all six engineering rules, and specialist
role descriptions embedded inline — no separate rule files needed since Gemini CLI
reads a single global instructions file.

### Commands

```bash
vibe kits gemini doctor
vibe kits gemini install --dry-run
vibe kits gemini install --yes
vibe kits gemini diff
vibe kits gemini uninstall --yes
```

### What it installs

`~/.gemini/GEMINI.md` — a single self-contained file containing:

- senior/staff backend engineering persona and operating identity
- task risk policy and autonomy boundaries
- all six modular engineering rules (operating model, Go backend, testing, security/data, database/ops, uncertainty/sources) embedded as sections
- specialist role descriptions for all five subagent modes (backend-tech-lead, go-backend-implementer, security-data-reviewer, db-operations-reviewer, tdd-test-engineer)
- communication style and definition of done

Rules are embedded rather than referenced because Gemini CLI loads a single
instructions file rather than a rules directory.

## Codex CLI Kit

Portable Codex CLI setup for senior backend engineering. Installs a single
`instructions.md` file with the same comprehensive persona and embedded rules.

### Commands

```bash
vibe kits codex doctor
vibe kits codex install --dry-run
vibe kits codex install --yes
vibe kits codex diff
vibe kits codex uninstall --yes
```

### What it installs

`~/.codex/instructions.md` — a single self-contained file with the same
structure as `GEMINI.md` above, adapted to Codex CLI conventions. If a
project-level `AGENTS.md` or `.codex/instructions.md` exists, it takes
priority over the global file.

## Cursor IDE Kit

Portable Cursor IDE setup for senior backend engineering. Installs rule files
into `~/.cursor/rules/` as `.mdc` files. Each file has YAML frontmatter
(`description`, `globs`, `alwaysApply`) so Cursor can selectively load rules
based on file type.

### Commands

```bash
vibe kits cursor doctor
vibe kits cursor install --dry-run
vibe kits cursor install --yes
vibe kits cursor diff
vibe kits cursor uninstall --yes
```

### What it installs

Seven `.mdc` files into `~/.cursor/rules/`:

| File | `alwaysApply` | Scope |
|------|---------------|-------|
| `00-persona.mdc` | `true` | global persona, risk policy, autonomy, definition of done |
| `operating-model.mdc` | `true` | workflow, risk classification, scope discipline |
| `security-and-data-safety.mdc` | `true` | authz, secrets, injection, tenant isolation |
| `uncertainty-and-sources.mdc` | `true` | epistemic honesty, citation standards |
| `go-backend-engineering.mdc` | `false` | Go-specific rules; globs `**/*.go` |
| `testing-and-verification.mdc` | `false` | TDD, test quality; globs test file patterns |
| `database-and-operations.mdc` | `false` | migrations, queries, transactions; globs DB file patterns |

**Note:** Cursor 0.45+ also supports project-local rules at `.cursor/rules/`. For
per-project behavior, copy the relevant `.mdc` files from `~/.cursor/rules/` into
your project's `.cursor/rules/` directory and adjust as needed.

## Second-Brain Kit

Local-first Obsidian + qmd vault with safe AI-agent config snippets. The
kit creates a vault scaffold, seeds three wiki pages, and merges a
non-secret `qmd` MCP entry into Claude Code, OpenCode, and Codex CLI
configs. When qmd is not found, `install` prompts then runs
`npm install -g @tobilu/qmd` and registers the wiki collection. Pass
`--no-setup-deps` to skip; all other network commands (`qmd`, `pip`,
`git clone`, etc.) are never run.

### Vault location

- Default: `~/second-brain`
- Override: `VIBE_SECOND_BRAIN_PATH=/path/to/vault`

The vault is your data. The installer creates it; `uninstall` never
touches it. See the safety contract in the [Safety Model](#safety-model)
section.

### Commands

```bash
vibe kits second-brain install --dry-run --yes          # show plan, write nothing
VIBE_SECOND_BRAIN_PATH="$HOME/notes" \
    vibe kits second-brain install --yes                 # scaffold vault + agent snippets
vibe kits second-brain diff                              # what would change on next install
vibe kits second-brain doctor                            # health check (qmd, vault, agent configs)
vibe kits second-brain uninstall --yes                   # strip agent snippets + manifest only
```

All four commands accept `--home <path>` to redirect the agent config
root (default `$XDG_CONFIG_HOME` or current user's home) — useful for
isolated dry runs in CI. `install` also accepts `--no-settings` to
skip the agent config adapters and only scaffold the vault.

### What it creates in the vault

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

### Agent config snippets

The installer merges a `qmd` MCP entry (`command: qmd`, `args: ["mcp"]`)
into each agent's config using a format-specific safe adapter. No
secrets, no full-file overwrites — unrelated keys, MCP servers, and
settings are preserved byte-for-byte.

| Agent | Format | Adapter | Scope |
|-------|--------|---------|-------|
| Claude Code | JSON | `json_defaults_strategy` | `~/.claude/settings.json`; skips `env` and secret keys |
| OpenCode | JSONC | `jsonc_defaults_strategy` | `~/.config/opencode/opencode.jsonc`; skips 14 local-only keys + 6 secret substrings |
| Codex CLI | TOML | `toml_block_merge_strategy` | `~/.codex/config.toml`; inserts/replaces `[mcp_servers.qmd]` block only |
| Cursor | — | vault sample only | `.mdc` snippet under `wiki/agent-snippets/cursor/`; never writes global `~/.cursor/rules` |
| Hermes | — | docs/sample only | No config mutation anywhere; ship docs only |

### qmd policy

`qmd` is the core search/index dependency. When qmd is not found,
`install` prompts to run `npm install -g @tobilu/qmd` and register the
wiki collection automatically. Pass `--yes` to skip the prompt; pass
`--no-setup-deps` to skip auto-install entirely (you'll see the manual
commands below). `doctor` returns `1` if `qmd` is missing or its
`collection list` does not point at `<vault>/wiki`.

To install manually:

```bash
npm install -g @tobilu/qmd                  # Node >= 20
qmd collection add <vault>/wiki --name second-brain
qmd update                                  # build the initial index
```

### Obsidian and memory compiler

- **Obsidian** is an optional visual client. If missing, doctor returns
  `0` with a warning. The vault works with any Markdown editor.
- **Memory compiler** is a docs-only add-on. The installer ships
  installation and hook-configuration docs under `wiki/docs/` but never
  clones, configures, or mutates Claude settings for it.

## Safety Model

All kits intentionally do **not** include or install:

- auth tokens, API keys, or passwords
- local router/proxy URLs
- provider / model selection (for OpenCode, also: `plugin`, `mcp`, `theme`, `env`, `permission`, `agent`)
- project transcripts, histories, tasks, caches, or backups
- local machine-specific MCP auth state

For the OpenCode kit, the top-level config keys `model`, `provider`, `plugin`, `mcp`, `tools`, `permission`, `env`, `agent`, `theme`, and any key containing `token`, `key`, `secret`, `password`, `auth`, or `credential` are always preserved as-is. The second-brain kit reuses the same policy via `agents/secret_policies.py`. The Gemini, Codex, and Cursor kits install only portable markdown/text files and never touch settings files or credentials.

The `second-brain` kit additionally guarantees:

- **Controlled package-manager execution**: `second-brain install` prompts then runs `npm install -g @tobilu/qmd` when qmd is not found, then registers the wiki collection. Pass `--no-setup-deps` or decline the prompt to skip. All other kits never run any package-manager command.
- **No other network or install commands**: never runs `git pull`, `git clone`, `qmd embed`, `qmd init`, or starts the qmd MCP daemon
- **No symlinks**: never creates cross-directory symlinks
- **No plugin or Obsidian installs**: `obsidian` is checked by `doctor` but never installed
- **No memory-compiler hooks**: never mutates `.claude/settings.json` for memory-compiler hooks
- **No third-party skill redistribution**: `claude-obsidian` is referenced as install commands only; its skill files are not copied into the repo
- **Vault data is sacred**: `uninstall` never deletes the vault directory, `.git`, seed pages, `.gitignore`, or any user content under `raw/`, `wiki/`, `output/`. It removes only kit-owned non-secret agent config snippets and the runtime manifest

## Adding a new kit

The simplest kits (Claude Code / OpenCode shape) export four functions. The
`second-brain` kit is the canonical example for kits that need a fake
`home` parameter for testing, environment-variable overrides, multiple
agent config adapters, and a safe-scaffold pattern that never deletes user
data. Read its `installer.py` before designing a new kit of similar scope.

1. **Create the installer module** at `agents/kits/<kit_name>/installer.py` exporting four functions (the canonical signature, shared by every kit):
   - `install(home=None, dry_run=False, yes=False, **kwargs) -> int`
   - `diff_kit(home=None) -> int`
   - `doctor(home=None) -> int`
   - `uninstall(home=None, dry_run=False, yes=False, **kwargs) -> int`

   For kits that merge agent config snippets, gate the merge behind a
   boolean (the CLI exposes it as `--no-settings`). For kits that scaffold
   user data, treat that data as immutable: `mkdir -p` and
   create-if-absent seeds only; never `rm` or overwrite user files.
2. **Add a `KitSpec`** in `agents/kit_registry.py` pointing to those functions. The spec's `help` text is what shows up in `vibe kits <name> --help`.
3. **Place templates and a manifest** under `agents/kits/<kit_name>/templates/<kit_name>/`:
   - `manifest.json` with `kit`, `version`, `managed_files`, `settings_fragment`, and `secret_policy`
   - All files listed in `managed_files`
4. **Add manifest contract tests** in `tests/test_manifest_contracts.py` asserting every managed file exists and the manifest surface is valid.
5. **If the kit merges JSON / JSONC / TOML / ENV**, add or reuse a strategy in `agents/merge_strategies.py`. The second-brain kit added `toml_block_merge_strategy` and `strip_toml_block`; reuse them rather than re-implementing.
6. **If the kit needs shared key/secret policy** (the `local-only` and `secret-substring` sets used by both the OpenCode and second-brain JSONC adapters), import from `agents/secret_policies.py` instead of redefining locally.

No CLI dispatch code needs to change: `build_parser(kit_specs=KITS)` reads the registry dynamically.

## Development

```bash
python3 -m unittest discover -s tests -v
```

Inside an activated virtualenv where `python` points to Python 3, `python -m unittest discover -s tests -v` is also acceptable.

The full suite covers kit registry, CLI contract, extension contract, manifest contracts, installer behavior (install / diff / doctor / uninstall) for every kit, and the shared merge strategies. All tests must pass before shipping.
