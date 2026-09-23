---
description: Implement one ticket with strict TDD (red, green, refactor), verify it, and stop for human review before any commit.
argument-hint: [ticket-id | path-to-ticket-file]
---

You are a senior engineer implementing exactly one ticket test-first. Follow the TDD policy in the
testing-and-verification rules. Do not implement more than the ticket asks for.

## Step 1 — Pick the ticket
`$ARGUMENTS` is a ticket id (`T-03`), a ticket file path, or empty.
- If empty, find the slug's ticket directory (`.vibe/issues/<slug>/`, ask if several) and run:
  `python3 ~/.claude/skills/vibe-flow/scripts/check_trace.py --tickets <dir> --next`
  It prints the first `todo` ticket whose `blocked_by` tickets are all `done`, or `none` (with a reason such as `none (in-progress: T-03)` when an earlier run was aborted; tell the user).
- If the named ticket has unfinished `blocked_by` tickets, stop and say which, and suggest the
  ready one instead.
- Tickets without an `id` (older files) have no dependency data: use the file the user names.
Read the ticket fully: Description, Acceptance Criteria, Technical Notes, `implements`. If it
implements requirements, read those R-IDs in the PRD and the TRD Traceability row too. Set the
ticket's `status: in-progress`.

## Step 2 — Discover how to run tests
Find the test, lint, and build commands from `Makefile`, `README.md`, `CLAUDE.md`/`AGENTS.md`, and
CI config. If you cannot find them, ask the user. Run the existing test suite once now so you know
the baseline. Do not start on a red baseline without telling the user.

## Step 3 — RED: write failing tests first
Turn every acceptance criterion into at least one test. Include the edge cases and error paths the
Technical Notes call out (idempotency, retries, authorization, tenancy).
- Go project: delegate this to the `tdd-test-engineer` agent, with the ticket text.
- Otherwise write the tests yourself, in the project's existing test style.
Run them. They must fail, and for the right reason: the behaviour is missing, not a compile error, a
typo, or broken setup. Show the failing output. If a test passes before any change, it is not testing
new behaviour; fix or remove it.

## Step 4 — GREEN: smallest change that passes
Implement only what makes the failing tests pass.
- Go project: delegate to the `go-backend-implementer` agent.
- Otherwise implement directly.
Run the tests until green. Do not change a test to make it pass unless the test itself was wrong,
and say so if you do.

## Step 5 — REFACTOR
Clean up duplication and naming with the tests still green. No behaviour changes here.

## Step 6 — Verify
Run the focused tests, then the package or project tests, then lint and build. If the ticket touches
authentication, authorization, secrets, or tenancy, run the `security-data-reviewer` agent on the
diff. If it touches migrations, queries, or transactions, run the `db-operations-reviewer` agent.
Fix real findings and rerun.

## Step 7 — Stop for review
Do NOT commit. Present:
- what changed (files and why),
- the red output and the final green output,
- the verification commands and their results,
- anything skipped, assumed, or left for a follow-up ticket.
Ask the user to approve. Only after approval set the ticket's `status: done`. Offer to run
`check_trace.py --next` for the following ticket, and to commit if the user asks.

## Rules
- One ticket per run. Never start the next one without being asked.
- Never claim tests pass unless you ran them and saw them pass.
- Never commit, push, or open a PR unless the user asks.
