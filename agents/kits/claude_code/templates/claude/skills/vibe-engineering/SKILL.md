---
name: vibe-engineering
description: >
  Full TRD-to-GitHub-issues pipeline for any repo. Use this skill whenever the user
  invokes /vibe-engineering, mentions "vibe engineering", wants to implement a TRD,
  wants to break down a technical spec into tickets, or says anything like "bikin
  issues dari TRD ini", "breakdown TRD", or "buat github issues dari spec ini".
  Works in both Claude Desktop and Claude Code CLI. Trigger even if the user only
  partially describes the workflow — if there's a TRD + intent to create issues,
  use this skill.
---

# vibe-engineering

Turn a TRD (Technical Requirements Document) into a structured, approved GitHub issue
set — ready to push to any repo.

---

## Phase 0 — Locate TRD

Accept TRD in either form:
- **File path**: read the file directly (absolute or relative to cwd)
- **Pasted content**: user pastes markdown/text inline

If neither is clear from the invocation, ask:
> "TRD-nya mau di-paste langsung atau kasih file path-nya?"

---

## Phase 1 — Gather Codebase Context

Run this discovery sequence **before** reading the TRD deeply:

### 1a. Always read first (if exists)
```
CLAUDE.md          # project conventions, architecture notes
README.md          # project overview
```

### 1b. Discover structure
```bash
# Get top-level layout
ls -la

# Find docs / TRD / ADR folders
find . -maxdepth 3 -type d \( -name "docs" -o -name "trd" -o -name "adr" -o -name "specs" \)

# Go-specific: find domain/usecase/handler/repo boundaries
find . -maxdepth 4 -type d \( -name "domain" -o -name "usecase" -o -name "handler" \
  -o -name "repository" -o -name "internal" -o -name "pkg" \)
```

### 1c. Read relevant code
Based on TRD topic, identify and read:
- Existing domain entities related to the feature
- Relevant interfaces (ports) in the usecase layer
- Related handler or consumer files
- Existing test files for the affected area

**Cap at ~10 files** to avoid context bloat. Prioritize interfaces over implementations.

### 1d. User hint override
After auto-discovery, say:
> "Gue udah baca [list files]. Ada file/folder lain yang relevan yang mau lo tambahin?"

Wait for response. If user adds hints, read those too.

---

## Phase 2 — Analyze TRD

Read the TRD thoroughly. Extract:

- **Objective**: what problem is being solved
- **Scope**: what's in/out
- **Key entities / data models**: new structs, DB tables, Kafka topics
- **APIs / endpoints / consumers**: contracts being added or changed
- **Dependencies**: external services, other internal services
- **Non-functional requirements**: SLAs, idempotency, retry, observability
- **Unknowns / open questions**: things that are ambiguous in the TRD

---

## Phase 3 — Build Implementation Plan

Generate a structured plan. For each work item, decide granularity:

### Splitting heuristic (use judgment, user can adjust at checkpoint)

| Complexity signal | Suggested split |
|---|---|
| Single entity + CRUD usecase | Vertical slice (1 ticket) |
| Multiple bounded contexts | Split per context |
| Infra setup (Kafka, DB migration) | Separate infra ticket(s) |
| Large usecase with 3+ external calls | Split by sub-flow |
| Anything requiring coordination between 2+ engineers | Hard split |

**Default preference**: vertical slice (domain + usecase + repo + handler/consumer in
one ticket) so each ticket is independently testable. Fall back to horizontal only if
the vertical would be too large (>2 days estimate).

### Plan output format

```
## Implementation Plan: <TRD Title>

### Context Summary
<2-3 sentences: what we're building and why>

### Open Questions
<List any ambiguities in the TRD that need clarification before/during impl>

### Tickets

| # | Title | Scope | Testable? | Est |
|---|-------|-------|-----------|-----|
| 1 | ...   | vertical: domain+usecase+repo+handler | unit + integration | S |
| 2 | ...   | infra: DB migration | migration runs clean | XS |
...

### Dependencies
<ticket ordering / blockers between tickets>
```

Size legend: `XS` <2h · `S` ~half day · `M` ~1 day · `L` ~2 days

---

## CHECKPOINT 1 — Plan Approval

**Stop here.** Present the plan. Ask:

> "Plan-nya gimana? Mau adjust splitting, scope, atau urutan sebelum gue generate issues-nya?"

Wait for explicit approval or adjustment requests. Iterate if needed.
Only proceed to Phase 4 after user says something like "oke", "lanjut", "approved", "gas".

---

## Phase 4 — Generate GitHub Issues

For each ticket in the approved plan, generate a separate markdown file.

### File naming
```
.vibe/issues/<trd-slug>/
  issue-01.md
  issue-02.md
  ...
  _metadata.json
```

Create `.vibe/issues/<trd-slug>/` directory relative to cwd.
`trd-slug` = kebab-case of TRD title (e.g., `payment-reconciliation`).

### Issue file format

```markdown
---
title: "<ticket title>"
labels: [<suggested labels>]
milestone: "<suggested milestone>"
---

## Description

<2-3 sentences: what this ticket delivers and why>

## Acceptance Criteria

- [ ] <specific, verifiable criterion>
- [ ] <specific, verifiable criterion>
- [ ] <unit tests cover X>
- [ ] <integration test or manual test scenario>

## Technical Notes

### Context
<WHY this ticket exists in the bigger picture. 1-2 sentences connecting this ticket
to the overall TRD objective. A junior engineer should understand why this work
matters before touching a single file.>

### Approach
<Concrete, step-by-step explanation of HOW to implement — not just what to build.
For each step, explain WHY that approach is chosen over alternatives if non-obvious.

Example quality bar:
  "Add a `PaymentStatus` field to the `Loan` domain entity in
  `internal/domain/loan.go`. We put this in the domain layer (not usecase) because
  it's a core business attribute, not a derived computation — consistent with how
  `DisbursementStatus` is modeled in the same file."

Always reference actual file paths and existing patterns from the scanned codebase.
Never say "create a handler" without specifying which file and which existing handler
to use as a reference pattern.>

### Files likely affected
- `<actual/path/from/codebase.go>` — <what changes and WHY it changes here>
- `<actual/path/from/codebase.go>` — <what changes and WHY it changes here>
- `<actual/path/from/codebase.go>` — <what changes and WHY it changes here>

If a file doesn't exist yet, mark it explicitly:
- `internal/domain/reconciliation.go` *(new file)* — <why a new file is needed>

### Gotchas / watch out
- <Edge case with explanation of WHY it's a gotcha, not just WHAT it is>
- <Idempotency: explain what happens if this operation runs twice and how to handle it>
- <Error handling: what errors to expect, which to retry, which to surface upstream>
- <Cross-service implications with reasoning>

### Out of scope
- <What this ticket explicitly does NOT cover, and WHY it's deferred>

---
*Generated by vibe-engineering from: `<trd-source>`*
```

### Label suggestions
Suggest from common patterns — adjust to repo's actual labels:
`feature`, `backend`, `infra`, `migration`, `kafka`, `api`, `chore`, `p1`, `p2`

### Milestone suggestions
Look at existing milestones from repo context if available. Otherwise suggest based on
TRD scope (e.g., sprint name, version tag). Always surface suggestion for user to confirm.

### _metadata.json
```json
{
  "trd": "<source>",
  "generated_at": "<ISO timestamp>",
  "tickets": [
    { "file": "issue-01.md", "title": "...", "labels": [...], "milestone": "..." }
  ]
}
```

---

## CHECKPOINT 2 — Review Before Push

After all files are generated, present summary:

```
Generated N issues in .vibe/issues/<slug>/

  issue-01.md  →  <title>  [labels]  milestone: X
  issue-02.md  →  <title>  [labels]  milestone: X
  ...

Labels & milestones are suggestions — konfirmasi atau mau adjust dulu?
Kalau udah oke, push pakai GitHub issue skill lo.
```

**Do not push automatically.** User explicitly hands off to their GitHub issue push skill.

---

## Notes

### Language
Match user's language per message (Bahasa, English, or mix). Issue files themselves
default to English unless user specifies otherwise.

### Junior/AI readability — non-negotiable standards
Every issue must be self-contained enough for a junior engineer or a cheaper AI model
to pick up and implement without needing to ask clarifying questions. This means:

- **Always WHY, not just WHAT**: every technical decision in the issue must explain
  the reasoning. "Add X to Y" is incomplete. "Add X to Y because Z" is the standard.
- **Always actual file paths**: never write "create a handler" or "add a usecase".
  Always write the exact file path based on Phase 1 codebase scan. If uncertain,
  say so explicitly: "likely `internal/usecase/payment_usecase.go` — confirm first".
- **Existing pattern references**: when applicable, point to an existing file that
  uses the same pattern. E.g. "follow the same error wrapping pattern used in
  `internal/usecase/collection_usecase.go` line ~45".
- **No assumed knowledge**: don't assume the reader knows what "hexagonal port" means.
  Say "the interface in `internal/usecase/port/payment_port.go`".

### No hallucination
If TRD references a service/entity that doesn't exist in codebase yet, mark it
explicitly as "*(new — needs to be created)*" in Files likely affected. Never reference
a file path that wasn't confirmed in Phase 1 scan without this marker.

### Idempotency & error handling
Always address in Technical Notes for any ticket involving:
- DB writes / updates
- Kafka producers or consumers
- External HTTP calls
- Scheduled jobs / cron

### Keep SKILL.md lean
If issue templates grow complex, move verbose examples to `references/issue-template.md`.
