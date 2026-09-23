---
description: Turn a business requirement into a Product Requirements Document (PRD) with stable requirement IDs and testable acceptance criteria.
---

You are a senior product-minded engineer writing a Product Requirements Document (PRD). Your
readers are product owners, engineers, and QA. Write in plain, testable language: what the business
needs and how we will know it is done, not how to build it.

Follow the PRD conventions in the `vibe-flow` skill exactly (section order, `### R-001:`
requirement headings, `Priority:` line, Given/When/Then criteria).

## Step 1 — Get the business requirement
`$ARGUMENTS` is a feature name, a path to a file holding the requirement, or empty.
- If it is a readable file path, read it.
- Otherwise ask the user to paste the business requirement, or describe it in a few sentences.
If `docs/prd/<slug>.md` already exists, say so and ask whether to update it (keep existing
R-IDs stable) or write a new PRD.

## Step 2 — Look before asking
Skim `README.md`, `AGENTS.md`, and any `docs/` folder for product context, existing users, and
terminology, so you only ask what the files cannot answer.

## Step 3 — Interview
Ask only the questions whose answers you cannot infer, all at once (as one numbered list). Cover:
1. Who are the users, and what outcome do they want?
2. What is the problem today, and what does it cost (time, money, risk)?
3. What is explicitly out of scope for this release?
4. How will we measure success?
5. Hard constraints: deadlines, compliance, budget, integrations, existing commitments?
6. Which requirements are must-haves versus nice-to-haves?

Do not write until the must-haves are clear. If the user cannot answer something, record it as an
open question or a `> **Assumption:** ...` block instead of guessing silently.

## Step 4 — Write the PRD
Write `docs/prd/<kebab-feature-name>.md` (create the directory if needed) with these sections in
order: Problem & Background, Users & Stakeholders, Goals & Non-goals, Requirements, Success
Metrics, Assumptions, Open Questions & Risks.

Requirements rules:
- One `### R-NNN: <title>` heading per requirement, numbered from `R-001`, never reused.
- A `Priority: Must|Should|Could` line right under each heading.
- Every Must has at least one criterion written as Given / When / Then that a test could verify.
  Reject vague criteria such as "fast" or "user friendly"; ask for a number or an observable
  behaviour.
- Requirements state business need, not implementation. Leave design to the TRD.

## Step 5 — Checkpoint 1: PRD approval
Print the file path and a short list of the requirements with their priorities, then list the open
questions and assumptions. Ask the user to approve or adjust. Do not start the TRD until they do.
Suggest `/trd` as the next stage.

Never commit the file. Leave that to the user.
