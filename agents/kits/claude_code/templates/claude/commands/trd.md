---
description: Create, update, or improve a Technical Requirements Document (TRD) as a senior software engineer. Use /trd to start from scratch (interview-driven), /trd update <feature> to reverse-engineer from the codebase with gap analysis, or /trd improve <path> to improve an existing TRD.
argument-hint: [create|update|improve] [feature-name-or-path]
---

You are a senior software engineer writing a Technical Requirements Document (TRD). Your audience is engineers — write with deep technical precision, no hand-holding.

Parse `$ARGUMENTS` to determine mode:
- Starts with `update` → **Update Mode**
- Starts with `improve` → **Improve Mode**
- Otherwise (including empty) → **Create Mode**

---

## TRD Standard Sections

Every TRD you produce must contain these sections in order:

1. **Overview** — one-paragraph summary of the feature and why it exists
2. **Problem / Background** — current pain point, business or technical motivation
3. **Scope & Non-goals** — explicit in/out of scope list; prevents scope creep
4. **Architecture / Design** — component or sequence diagram in Mermaid, data flow narrative
5. **API Contracts** — per endpoint: method, path, request schema, response schema, error codes
6. **Database / Data Model** — new/changed tables, columns, types, indexes, migration notes
7. **Security & Auth** — AuthN/AuthZ requirements, sensitive data handling, threat notes
8. **Testing Strategy** — unit, integration, e2e test plan; acceptance criteria per requirement
9. **Open Questions & Risks** — unresolved decisions, external dependencies, technical risks

---

## Create Mode

**Trigger:** args are empty, or start with `create`.

**Step 1 — Identify the feature.**
If a feature name was provided in args, use it. Otherwise ask: "What is the feature or epic name?"

**Step 2 — Interview.**
Ask the following questions. You may ask them all at once using `AskUserQuestion` (multi-question form) or in one clear numbered list. Do not proceed to writing until you have answers.

1. What problem does this feature solve? (1–3 sentences)
2. Who is the consumer — end user, mobile client, internal service, third-party integration?
3. What are the key domain entities or concepts involved?
4. What is the rough API surface — endpoint names, gRPC methods, or event topics?
5. What database changes are expected — new tables, new columns, schema changes?
6. Any hard constraints — SLAs, data residency, backward compatibility, rate limits?
7. Any known risks, open questions, or things you're uncertain about?

**Step 3 — Write the TRD.**
Using the answers, write a complete TRD covering all 9 standard sections. Use Mermaid for diagrams. Be specific: name actual tables, columns, endpoints, and error codes where known. Where the user was vague, make a reasonable engineering assumption and mark it `> **Assumption:** ...` so it's visible for review.

**Step 4 — Save.**
Write the TRD to `docs/trd/<kebab-feature-name>.md`. Create the directory if it doesn't exist. Print the file path when done.

---

## Update Mode

**Trigger:** args start with `update`. Feature name follows (e.g. `update cms-admin`). If no name given, ask for it.

**Step 1 — Explore the codebase.**
Use an Explore agent to read all relevant code for the feature:
- HTTP handlers (`internal/adapter/http/handler/`)
- Services (`internal/core/service/`)
- Domain structs (`internal/core/domain/`)
- Port interfaces (`internal/core/port/`)
- Repository models (`internal/adapter/repository/model/`)
- Migrations (`migrations/`)
- Tests (`*_test.go` files for the feature)

**Step 2 — Write the TRD (current state).**
Document what the code *actually does* across all 9 standard sections. Be precise — name real functions, types, endpoints, tables, and columns from the code.

**Step 3 — Append Gap Analysis section.**
After the 9 standard sections, add a `## Gap Analysis` section covering:

- **Missing documentation** — undocumented behavior, missing Swagger annotations, unclear error semantics
- **Missing test coverage** — untested paths, missing edge cases, no integration tests
- **Security concerns** — unvalidated inputs, missing auth checks, sensitive data exposure
- **Architecture violations** — domain importing infrastructure, missing interface abstractions, globals
- **Improvement opportunities** — refactoring suggestions, performance notes, consistency issues

Each gap item: one bullet, concrete, actionable. Reference file and line number where possible.

**Step 4 — Save.**
Write to `docs/trd/<feature-name>.md`. Create directory if needed. Print the file path when done.

---

## Improve Mode

**Trigger:** args start with `improve`. A file path follows (e.g. `improve docs/trd/cms-admin.md`). If no path given, ask for it.

**Step 1 — Read the existing TRD.**
Read the file at the given path.

**Step 2 — Audit each section.**
For each of the 9 standard sections, identify:
- Vague or non-committal language ("might", "could", "TBD" without context)
- Missing required content (e.g. API section with no error codes)
- Outdated references (check against current codebase if relevant)
- Sections that are missing entirely

**Step 3 — Rewrite.**
Produce an improved version of the full TRD. Where you make a meaningful improvement, add an HTML comment immediately after: `<!-- improved: <reason> -->`. Do not add comments for minor wording changes.

**Step 4 — Save.**
Overwrite the original file with the improved version. Print the file path and a brief summary of what was improved.

---

## General Rules

- Never commit the file. Leave that to the user.
- Use Mermaid for all diagrams (```mermaid blocks).
- Use code blocks for all schemas and SQL.
- Use `> **Assumption:** ...` for any engineering assumption you make.
- Target engineers as readers — skip motivation fluff, be precise about types, constraints, and behavior.
