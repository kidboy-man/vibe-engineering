---
name: vibe-flow
description: >
  End-to-end flow from a business requirement to a PRD, a TRD, dependency-ordered
  tickets, and TDD implementation. Use when the user has a business requirement, feature
  request, or product idea and wants it turned into a PRD/TRD/tickets, asks "what is the
  next step" in that chain, mentions requirement IDs (R-001) or ticket IDs (T-01), or runs
  /flow, /prd, /implement-ticket or /push-tickets.
---

# vibe-flow

One trail of files carries a requirement from business language to shipped code. Each
stage reads the previous stage's file and writes its own, so any stage can be run alone
or the whole chain can be run with `/flow`.

| Stage | Command | Reads | Writes |
|---|---|---|---|
| 1. PRD | `/prd` | business requirement (text or file) | `docs/prd/<slug>.md` |
| 2. TRD | `/trd` | the PRD | `docs/trd/<slug>.md` |
| 3. Tickets | `vibe-engineering` skill | the TRD (and PRD) | `.vibe/issues/<slug>/issue-NN.md`, `_metadata.json` |
| 4. Push (optional) | `/push-tickets` | tickets | GitHub issues, after approval |
| 5. Implement | `/implement-ticket` | one ticket | tests + code, no commit |

`<slug>` is the kebab-case feature name and stays identical across all stages.

## Artifact conventions

### PRD (`docs/prd/<slug>.md`)
Sections in order: Problem & Background, Users & Stakeholders, Goals & Non-goals,
Requirements, Success Metrics, Assumptions, Open Questions & Risks.

Each requirement is its own heading with a stable ID:

```markdown
### R-001: <short title>
Priority: Must
<one-sentence statement of what the business needs>
- Given <context>, when <action>, then <observable outcome>.
```

- `Priority` is `Must`, `Should` or `Could`.
- IDs are stable. Never renumber. New requirements take the next free number.
- Every Must requirement has at least one Given/When/Then criterion a test can check.

### TRD (`docs/trd/<slug>.md`)
The standard `/trd` sections, plus:
- Frontmatter `prd: docs/prd/<slug>.md` when a PRD exists.
- A `## Traceability` table: `| Requirement | Design section | Test cases |`, one row per
  requirement, so every R-ID points at the design that satisfies it and the tests that prove it.

### Tickets (`.vibe/issues/<slug>/issue-NN.md`)
Existing ticket format, with these frontmatter fields added:

```yaml
id: T-01
implements: [R-001, R-003]
blocked_by: [T-00]
size: S
status: todo
```

`status` is `todo`, `in-progress` or `done`. `_metadata.json` also records `prd`, `trd`, and
each ticket's `id`, `implements`, `blocked_by` and (after a push) `github_issue`.

All of these are optional. Older files without IDs keep working; they just have no
traceability.

## Validating the trail

Run this at every checkpoint after tickets exist. It is deterministic; do not judge IDs and
dependencies by eye.

```bash
python3 ~/.claude/skills/vibe-flow/scripts/check_trace.py \
  --tickets .vibe/issues/<slug> --prd docs/prd/<slug>.md --trd docs/trd/<slug>.md
```

It fails on duplicate ids, unknown `blocked_by`/`implements` ids, dependency cycles, and
Must requirements no ticket implements, and prints a safe implementation order. Add `--next`
to print the next ready ticket id, or `--json` for machine-readable output.

## Rules

- Stop at every checkpoint and wait for an explicit approval. Never advance on silence.
- Never commit, push, or create issues unless the user asked for that step.
- Do not invent requirements. Anything unstated becomes `> **Assumption:** ...` or an open
  question, visible for review.
- Match the user's language per message. Artifact files default to English.
