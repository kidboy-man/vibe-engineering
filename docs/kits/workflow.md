# Workflow Kit

[← Back to README](../../README.md)

An end-to-end flow from a business requirement to implemented tickets, built from stages you can
run alone or chain with `/flow`. Stages hand off through files with stable IDs, so every ticket traces
back to a requirement.

| Stage | Command | Reads | Writes |
|-------|---------|-------|--------|
| 1. PRD | `/prd` | business requirement (text or file) | `docs/prd/<slug>.md` |
| 2. TRD | `/trd` | the PRD | `docs/trd/<slug>.md` |
| 3. Tickets | `vibe-engineering` skill | the TRD (and PRD) | `.vibe/issues/<slug>/issue-NN.md`, `_metadata.json` |
| 4. Push (optional) | `/push-tickets` | tickets | GitHub issues, only after explicit approval |
| 5. Implement | `/implement-ticket` | one ticket | failing tests, then code; no commit |

`/flow` detects which artifact already exists and continues from there, stopping at a checkpoint
after each stage. `/implement-ticket` does one ticket per run: red (tests from the acceptance
criteria, shown failing for the right reason), green, refactor, verify, then stops for your review.
It uses the `tdd-test-engineer` and `go-backend-implementer` agents when it detects Go, and works
directly otherwise; it finds the test/lint/build commands from your repo.

## Commands

```bash
vibe kits workflow doctor
vibe kits workflow install --dry-run
vibe kits workflow install --yes
vibe kits workflow diff
vibe kits workflow uninstall --yes
```

Installs only into agent config directories that already exist (`~/.claude`, and OpenCode's
`opencode` config dir). `/trd` and the `vibe-engineering` skill come from the `claude-code` /
`opencode` kits; install those too. `doctor` warns when they are missing. Upgrade both kits together:
the workflow kit relies on the requirement IDs and ticket dependencies in current `/trd` and `vibe-engineering`.

## The trail and its validator

- PRD requirements are `### R-001: Title` headings with a `Priority: Must|Should|Could` line.
- The TRD gets a `prd:` link and a `## Traceability` table (requirement, design section, test cases).
- Tickets gain `id`, `implements`, `blocked_by`, `size`, `status` frontmatter. All are optional;
  older ticket files keep working without traceability.

`check_trace.py` (installed with the `vibe-flow` skill) is deterministic and standard-library only. It
fails on duplicate IDs, unknown `blocked_by`/`implements` IDs, dependency cycles, and Must
requirements no ticket implements, and prints a safe implementation order (`--next` prints the next
ready ticket, `--json` is machine-readable):

```bash
python3 ~/.claude/skills/vibe-flow/scripts/check_trace.py \
  --tickets .vibe/issues/<slug> --prd docs/prd/<slug>.md --trd docs/trd/<slug>.md
```

Nothing here commits, pushes, or creates issues without you asking. `/push-tickets` uses your own
`gh` login and shows the exact plan first. The stage prompts themselves are not unit-tested; only the
validator, installer and template contracts are.
