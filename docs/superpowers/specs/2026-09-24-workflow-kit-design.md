# Workflow kit: business requirement -> PRD -> TRD -> tickets -> TDD — design

## Context
vibe-kits already ships `/trd` (create/update/improve) and the `vibe-engineering` skill (TRD -> ticket files, two checkpoints), both Go-hexagonal-flavoured and only in the claude-code/opencode kits. Missing: a PRD stage, an orchestrator that chains the stages, a TDD implement-a-ticket stage, and traceability (no requirement IDs, no ticket dependencies; TRDs in `docs/trd/` and tickets in `.vibe/issues/` are not linked). Goal: an end-to-end flow from a business requirement to tickets to TDD implementation, usable by an AI agent stage by stage or in one guided run.

Decisions made with the user: composable stages + orchestrator; new standalone `workflow` kit that adds the missing stages while `/trd` and `vibe-engineering` are upgraded in place; implementation is one ticket per run with a human gate before any commit; stack-neutral but Go-aware; tickets are files plus an opt-in, approval-gated `gh issue create` push.

## Artifact trail (the contract between stages)
| Stage | Artifact | Key content |
|---|---|---|
| PRD | `docs/prd/<slug>.md` | Problem, users, goals/non-goals, requirements as `### R-001: Title` with `Priority: Must\|Should\|Could` and Given/When/Then criteria, success metrics, assumptions, open questions |
| TRD | `docs/trd/<slug>.md` | existing 9 sections + frontmatter `prd:` link, a Traceability table (R-ID -> design section), and a test-case list per R-ID (feeds TDD) |
| Tickets | `.vibe/issues/<slug>/issue-NN.md` + `_metadata.json` | frontmatter adds `id: T-NN`, `implements: [R-001]`, `blocked_by: [T-01]`, `size`, `status: todo\|in-progress\|done`; metadata adds `prd`, `trd`, and `github_issue` after push |

All new fields are optional for old files: absent IDs mean no traceability, not an error.

## Design

### Workflow kit (new): `agents/kits/workflow/`
- `installer.py` modeled on `agents/kits/guardrails/installer.py`: targets `~/.claude` and OpenCode's XDG config dir, each only if it already exists; install/diff/doctor/uninstall via `agents/installer_core.py` (`install_copy_style_file`, `diff_copy_style`, `uninstall_unchanged_file`, `backup`). Manifest at `~/.vibe-workflow/.vibe-engineering-manifest.json` (agent-dir manifest slot is taken by the persona kits). Registered in `agents/kit_registry.py`, `MANIFEST.in`.
- Templates `templates/workflow/{claude,opencode}/`, same relative paths per target, target-specific wording (Claude uses AskUserQuestion/Explore agents; OpenCode does not):
  - `skills/vibe-flow/SKILL.md`: artifact conventions + stage detection; auto-triggers on "business requirement -> tickets" style requests.
  - `skills/vibe-flow/scripts/check_trace.py`: stdlib-only validator (below).
  - `commands/prd.md`: business requirement (pasted text or file) -> interview -> `docs/prd/<slug>.md`; unknowns become `> **Assumption:**` blocks; Must-requirements need testable criteria.
  - `commands/flow.md`: detects the furthest existing artifact and continues: no PRD -> `/prd`; PRD, no TRD -> `/trd`; TRD, no tickets -> `vibe-engineering`; tickets -> `/implement-ticket`. Checkpoints: PRD approved, TRD approved, ticket plan approved, push approved.
  - `commands/implement-ticket.md`: TDD stage (below).
  - `commands/push-tickets.md`: runs `check_trace.py`, shows the `gh issue create` plan in dependency order, and only after explicit approval creates issues, writing `github_issue` back to `_metadata.json`. Never pushes unprompted.
- `doctor` warns if `/trd` or the `vibe-engineering` skill is missing in a present target ("install the claude-code/opencode kit").

### `check_trace.py` (deterministic, tested)
Agents get IDs and dependency graphs wrong, so this is code, not prose. Reads PRD/TRD/tickets, no YAML dependency (minimal `key: value` / `[a, b]` parsing). Reports: dangling `implements`/`blocked_by` IDs, duplicate IDs, dependency cycles, Must-requirements no ticket implements, tickets implementing nothing (warn). Prints a topological ticket order; exit 1 on errors. Used at the ticket-plan and push checkpoints and by `/implement-ticket` to pick the next unblocked ticket.

### `/implement-ticket` (one ticket per run)
1. Pick the named ticket, or the first `todo` ticket whose `blocked_by` are all `done` (via `check_trace.py`).
2. Discover test/lint/build commands from Makefile, README, CLAUDE.md/AGENTS.md, CI config; ask if none found.
3. RED: each acceptance criterion -> at least one test (`tdd-test-engineer` when Go is detected, else the main agent); run and show failing for the expected reason, not a compile or setup error.
4. GREEN: smallest change (`go-backend-implementer` for Go); REFACTOR with tests green.
5. Verify: tests, lint, build; run `security-data-reviewer` / `db-operations-reviewer` when the ticket labels or files touch authz, secrets, or DB.
6. STOP: summary, test evidence, diff. No commit; `status` becomes `done` only after the user approves.

### Upgrades in place (claude-code + opencode kits, 4 files)
- `commands/trd.md`: optional `prd:` link and R-ID reuse, Traceability table, per-R-ID test cases in Testing Strategy; no behavior change when no PRD exists.
- `skills/vibe-engineering/SKILL.md`: emit `id`, `implements`, `blocked_by`, `size`, `status`; extend `_metadata.json`; read the TRD Traceability table; keep its two checkpoints and "do not push automatically".

## Testing
Prompts can't be unit-tested for behavior, so test what is deterministic:
- `tests/test_check_trace.py` (table-driven, TDD-first): valid graph, dangling ID, duplicate ID, cycle, uncovered Must, topological order, legacy tickets without IDs, malformed frontmatter.
- `tests/test_workflow_installer.py`: install/idempotent/dry-run/preserve-user-files/uninstall/diff/doctor per target on fake homes; only existing agent dirs touched; doctor warns when `/trd` missing.
- `tests/test_workflow_templates.py` content contract: every managed file exists in both targets; commands/skills have frontmatter `description`; claude and opencode variants list the same files; each artifact-convention field name appears in `SKILL.md`; the shipped `check_trace.py` runs against a fixture trail.
- Regression: full suite (`python3 -m unittest discover -s tests`, baseline 511), CLI help fixtures updated for the new kit, `test_manifest_contracts.py` covers the new kit.
- End to end: install into a fake home, run `check_trace.py` on a fixture PRD/TRD/tickets trail.

## Risks / not covered
- Stage behavior (interview quality, TDD discipline) is prompt-driven and unverified until run in a real agent; skill evals are backlog.
- Two kits own related files (`/trd` in claude-code/opencode, the rest in workflow); a version-skew note goes in the README and `doctor`.
- `gh` push uses the user's own `gh` login; not exercised in tests (dry-run plan output only).

## Verification
Run the full suite, then a fake-home install and `check_trace.py` on the fixture trail. Live agent run of `/flow` is a manual follow-up the PR must state as not done.

## Out of scope (backlog)
Jira/Atlassian push; PRD sourcing from URLs/Notion; autonomous multi-ticket loop; Codex/Gemini/Cursor ports; skill trigger evals.

## Implementation notes (as built)
- Templates split into `shared/` (the identical `check_trace.py`) and `claude/`/`opencode/` (prose variants). A file in `manifest.json` is taken from the target's directory when present, else `shared/`. The OpenCode variants are derived mechanically from the Claude ones (script path, no `AskUserQuestion`, no `argument-hint`, `AGENTS.md`).
- Path convention follows the opencode kit: with `--home X`, Claude uses `X/.claude` and OpenCode uses `X/opencode`; without it, OpenCode uses `$XDG_CONFIG_HOME/opencode`. OpenCode prompts call the validator as `${XDG_CONFIG_HOME:-$HOME/.config}/opencode/skills/vibe-flow/scripts/check_trace.py` so a non-default XDG dir still works; a `--home` install is a test/sandbox layout the prompts do not follow.
- Manifest entries are `<target>/<relative path>`; the manifest lives at `~/.vibe-workflow/`.
- `check_trace.py` also offers `--next` and `--json`; tickets without an `id` are warned about, not failed, and Must-coverage is skipped when no ticket has an id.
- Not covered: stage behavior in a real agent, `gh issue create` (prompt-only, never executed), Codex/Gemini/Cursor.
- `check_trace.py` frontmatter parser accepts block lists (`key:` + `- item`) and folded/literal scalars, since agents write both; an unparsable PRD (no `### R-NNN` headings) yields one error instead of blaming every ticket; `--next` says why it printed `none` when a ticket is stuck `in-progress`.
- The upgraded `vibe-engineering` next-step line only mentions `/push-tickets`/`/implement-ticket` conditionally (workflow kit may not be installed).
