---
description: Create GitHub issues from an approved ticket set, in dependency order, only after explicit approval.
---

You are publishing already-reviewed tickets to GitHub. Creating issues is visible to other people
and hard to undo, so nothing is created until the user approves the exact plan.

## Step 1 — Validate first
Find `.vibe/issues/<slug>/` (ask if there are several). Run:
`python3 ${XDG_CONFIG_HOME:-$HOME/.config}/opencode/skills/vibe-flow/scripts/check_trace.py --tickets .vibe/issues/<slug> [--prd <prd>] [--trd <trd>]`
If it reports any error, stop and show it. Do not push a broken trail. The order it prints is the
creation order: every blocker is created before the tickets it blocks.

## Step 2 — Check the target
Run `gh auth status` and `gh repo view --json nameWithOwner`. Tell the user exactly which repository
issues will be created in. If `gh` is missing or not logged in, stop and say so.
Run `gh label list` and `gh api repos/{owner}/{repo}/milestones`. Report labels or milestones a
ticket names that do not exist, and ask whether to drop them or create them. Do not create labels
or milestones silently.

## Step 3 — Show the plan and ask
Print a table in creation order: ticket id, title, labels, milestone, blocked_by. Say how many issues
will be created and where. Then ask for explicit approval. This is Checkpoint 4: do not create
anything on a vague answer.

## Step 4 — Create, in order
For each ticket in order, skipping any that already has a `github_issue` in `_metadata.json`
(so a re-run resumes instead of duplicating):
1. Build the body from the ticket file without its frontmatter. Append `Implements: R-001, R-003`
   and, when there are blockers, `Blocked by: #<number>` using the numbers already created.
2. `gh issue create --title "<title>" --body-file <file> --label <labels> [--milestone <name>]`
3. Record the returned issue number under that ticket's `github_issue` in `_metadata.json`
   immediately, before moving to the next ticket.
If a creation fails, stop, report which tickets were created, and do not retry blindly.

## Step 5 — Report
List each ticket id with its issue URL. Never delete or edit issues you did not just create.
