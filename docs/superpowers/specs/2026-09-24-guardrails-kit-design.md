# Guardrails kit for vibe-kits — design

## Context
vibe-kits installs personas/rules/agents/skills into AI coding tools, but ships no enforcement: the only hook is second-brain's SessionStart injector. Rules like "never expose secrets" and "ask before destructive actions" are advice the agent can ignore. Goal: add a `guardrails` kit that turns the most important rules into hooks for Claude Code, Codex and Cursor. This is sub-project 1 of the wider roadmap (see Backlog).

Decisions made with the user: theme = guardrail hooks; default = block only catastrophic, verification hooks opt-in; targets = Claude Code + Codex + Cursor; shape = new standalone `guardrails` kit.

## Design

### Kit shape
- `agents/kits/guardrails/installer.py` + `templates/guardrails/{manifest.json,hooks/guard.py,hooks/verify.py}`
- Registered in `agents/kit_registry.py`; CLI verbs come free: `vibe kits guardrails install|diff|doctor|uninstall`, `--home`, `--dry-run`, `--yes`, plus `--with-verify` (opt-in PostToolUse/Stop hooks).
- Uninstall removes only manifest-owned scripts and hook entries whose command matches ours.

### guard.py (target-neutral)
- Reads tool-call JSON on stdin, emits the target's block/allow response. One pure `decide(tool, input) -> Decision` function; a thin per-target adapter maps event names and response JSON.
- Hard-block: `rm -rf` on `/`, `~`, `$HOME` or paths outside cwd; `git push --force` (allow `--force-with-lease`); `git reset --hard`, `git clean -fdx`; `DROP`/`TRUNCATE` via psql/mysql in shell; reads or writes of `.env*`, `*.pem`, `id_rsa*`, `~/.aws/credentials`.
- Never raises; parse error or unknown shape => allow (same posture as `hooks/second-brain-context.py`). Blocks print a short reason the agent can act on.
- `verify.py` (opt-in): PostToolUse runs `gofmt -l`/`go vet` on edited `.go` files, warn-only; Stop reminds when edits happened with no test run.

### Merge machinery (main refactor)
`agents/merge_strategies.py` has `hook_command_merge_strategy`, `codex_hook_block_merge_strategy`, `cursor_hook_merge_strategy`, hardcoded to matcher-less SessionStart. Generalize them to take (event, matcher, command) so PreToolUse entries with matchers merge idempotently, preserving user hooks and secret/local-only keys. Reuse the second-brain helpers in `agents/kits/second_brain/installer.py` (~L636-850: `_json_hook_already_installed`, `_install_hook_script_file`, byte-stable command strings) by moving shared bits into `agents/installer_core.py` rather than duplicating. Second-brain behavior must stay byte-identical (its tests pin it).

### Per-target wiring
| Target | Config | Events |
|---|---|---|
| Claude Code | `~/.claude/settings.json` | PreToolUse (Bash, Read, Edit, Write), PostToolUse, Stop |
| Codex | `~/.codex/config.toml` `[[hooks.*]]` | equivalent events |
| Cursor | `~/.cursor/hooks.json` | equivalent events |

**Verify before implementing (not yet confirmed):** exact event names, block-response JSON, and matcher support for Codex and Cursor. Check current official docs (context7/WebFetch) first; if a target lacks a pre-tool blocking event, ship it warn-only there and say so in `doctor` output.

## Testing (TDD, per repo convention)
- Table-driven `tests/test_guard_decisions.py` over `decide()`: allowed and denied commands/paths, `--force-with-lease`, safe `rm -rf ./build`, malformed JSON => allow.
- `tests/test_guardrails_installer.py`: install/idempotent re-install/diff/doctor/uninstall per target on fake homes; user hooks and secret keys preserved; `--dry-run` writes nothing; invalid config skipped, not clobbered.
- Regression: existing `test_second_brain_*` and `test_manifest_contracts.py` (add guardrails to package-data/managed-file contract); CLI help snapshots in `tests/fixtures/cli_help/` updated.
- Verify end to end: `python -m pytest`, then a fake-home install and piping sample tool-call JSON through `guard.py`.

## Risks
- False positives block legit work: keep the block list narrow, add a test per rule, allow override via an env var (`VIBE_GUARDRAILS=off`).
- Shell-command parsing is heuristic (quoting, chained commands); document the ceiling, do not claim it is a sandbox.
- Refactoring shared merge code touches second-brain; guard with existing tests.

## Backlog (later sub-projects, in recommended order)
1. Agent-operable CLI: `--json`, `status`, `update --all`, `restore`, `vibe init` (per-project scaffolding).
2. Cross-agent parity: port agents/commands/skills to Codex, Gemini, Cursor; new targets.
3. Content: stack packs beyond Go, context7/GitHub MCP, more skills.
4. Quality: frontmatter linter, skill trigger evals, manifest versioning/changelog; fix README `unittest` vs CI `pytest`.

## Implementation notes (as built)
- Blocking uses exit code 2 + stderr on all three targets (verified against current Cursor and Codex docs). Cursor also treats empty stdout from a permission hook as invalid and blocks, so the Cursor command runs `guard.py --format=cursor`, which always prints `{"permission": ...}` (including on every fail-open path). Codex needs a one-time `/hooks` trust review for new hooks; `doctor` says so.
- Cursor registers `beforeShellExecution`, `beforeReadFile` (documented payloads) and `preToolUse` matcher `Write`. The Cursor `preToolUse` Write payload shape is unverified; the guard fails open if the path key differs.
- `--with-verify` is Claude Code only and covers `gofmt -l` on edited `.go` files. Dropped from the original plan: `go vet` (needs package context) and the Stop-time "no tests run" reminder (needs transcript state). Cursor `afterFileEdit` output and Codex file-path payloads are not usable for this.
- Agents are installed only if `~/.claude`, `~/.codex` or `~/.cursor` already exists.
- Manifest lives at `~/.vibe-guardrails/.vibe-engineering-manifest.json` because each agent dir's manifest slot is already taken by its persona kit.
