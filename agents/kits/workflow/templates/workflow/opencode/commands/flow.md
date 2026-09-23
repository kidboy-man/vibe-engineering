---
description: Run the end-to-end flow from a business requirement to a PRD, TRD, tickets, and TDD implementation, resuming from whichever artifact already exists.
---

You are orchestrating the `vibe-flow` pipeline. Read the `vibe-flow` skill for the artifact
conventions and the validation script, then drive the stages below. You do not write documents
yourself here: you detect where the feature stands, run the next stage, and stop at each checkpoint.

## Step 1 — Identify the feature
`$ARGUMENTS` is a feature slug, a path to a business requirement file, or empty. If empty, ask for
the feature name. Derive the kebab-case `<slug>` and use it for every stage.

## Step 2 — Detect the current stage
Check, in this order, and stop at the first gap:

| State on disk | Next stage |
|---|---|
| no `docs/prd/<slug>.md` | run `/prd` |
| PRD exists, no `docs/trd/<slug>.md` | run `/trd` (Create mode), passing the PRD path as context |
| TRD exists, no `.vibe/issues/<slug>/` | run the `vibe-engineering` skill on the TRD |
| tickets exist | run `check_trace.py` (see the skill); fix errors first, then go to implementation |

Tell the user which stage was detected and why before running it.

## Step 3 — Run one stage, then stop at its checkpoint
- PRD approved by the user, then TRD.
- TRD approved by the user, then tickets.
- Ticket plan approved (the `vibe-engineering` skill has its own checkpoints), then validate with
  `check_trace.py`. Show its errors and warnings. Do not proceed while there are errors.
Never advance past a checkpoint without an explicit approval. Each stage command already asks.

## Step 4 — After tickets are approved
Offer two optional next steps and let the user choose:
1. `/push-tickets` to create GitHub issues (never do this unprompted).
2. `/implement-ticket` to build the next ready ticket with TDD. It handles one ticket per run;
   after each ticket, ask whether to continue with the next.

## Rules
- One stage per turn of work. Do not chain a stage into the next without the checkpoint.
- If the user changes the PRD after a TRD or tickets exist, warn which downstream files are now
  stale and ask whether to regenerate them. Do not silently rewrite them.
- Never commit, push, or create issues on your own.
