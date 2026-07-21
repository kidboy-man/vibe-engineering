---
name: second-brain
description: Use the personal second-brain vault for relevant nontrivial work, durable decisions, source ingest, and inbox review. Search it before repeating prior research; capture durable outcomes as inbox drafts; curate only when asked.
compatibility: Requires the qmd MCP server for indexed wiki retrieval and write access to the configured vault for capture or curation.
---

# Second-Brain Workflow

The vault is at `$VIBE_SECOND_BRAIN_PATH` or `~/second-brain`.

## Retrieve before re-deriving

For a nontrivial task, before researching externally or recreating a past
decision, search the vault when prior work may help. Use `qmd` MCP `query` with
an explicit intent and lexical terms. Hybrid retrieval is allowed by default;
its first use may download local QMD models and temporarily use available GPU
resources. Retrieve the full relevant pages with `get` or `multi_get` before
relying on a result. Cite vault paths when they inform the answer.

Skip retrieval for trivial, local, or time-sensitive work. If qmd is unavailable
or has no useful result, continue normally and do not block the task.

## Capture durable outcomes automatically

After a verified nontrivial fix, durable decision, or reusable project
convention, write one concise, secret-free draft to
`inbox/YYYY-MM-DD-HHMM-<slug>.md`. Do not capture incomplete investigations,
temporary details, trivial edits, credentials, tokens, or private user data.

Use this shape:

```markdown
---
type: capture
status: inbox
created: YYYY-MM-DD
---

# Clear outcome title

## Outcome

What was decided or resolved.

## Why it matters

The reusable context, constraints, and evidence.

## Promotion

Suggested wiki destination and links to relevant project/source pages.
```

Inbox drafts are intentionally unindexed and uncurated. Do not update
`wiki/index.md`, `wiki/log.md`, `wiki/hot.md`, or run `qmd update` for a draft.

## Curate only on request

When asked to review or promote an inbox draft, handle one draft at a time:

1. Read the draft and related wiki pages.
2. Create or update the smallest appropriate wiki page with explicit
   `[[wikilinks]]`.
3. Update `wiki/index.md`, append `wiki/log.md`, and refresh `wiki/hot.md`.
4. Run `qmd update` after the approved wiki change. Report any failure.

Do not run `qmd pull` or `qmd embed` unless the user explicitly asks for
semantic indexing. Those are bulk operations; normal MCP `query` retrieval is
allowed.
