---
description: Bootstrap a new OpenCode installation with the senior backend engineering persona, modular rules, and global subagents.
---

Bootstrap this OpenCode installation from scratch using the `vibe-engineering` kit. Execute every step below and report what was created vs already present.

## Step 1 — Install the kit

Run the portable installer. It manages only safe, non-secret files:

```bash
vibe kits opencode install --yes
```

If `vibe` is not on PATH, install the kit first:

```bash
pipx install git+https://github.com/kidboy-man/vibe-engineering.git
vibe kits opencode install --yes
```

Verify the install:

```bash
vibe kits opencode doctor
```

## Step 2 — Verify the persona is loaded

Confirm these files now exist at the OpenCode global config dir (default: `~/.config/opencode/`):

```
AGENTS.md                                # global engineering persona
rules/operating-model.md                 # risk classification + scope discipline
rules/go-backend-engineering.md          # Go standards + architecture
rules/security-and-data-safety.md        # authz, tenant isolation, secrets
rules/database-and-operations.md         # schema/queries/migrations/observability
rules/testing-and-verification.md        # TDD policy + verification strategy
agents/backend-tech-lead.md              # architecture / TRD review
agents/go-backend-implementer.md         # Go implementation with TDD
agents/security-data-reviewer.md         # security + data isolation review
agents/db-operations-reviewer.md         # migration + query review
agents/tdd-test-engineer.md              # test design + bug reproduction
commands/trd.md                          # /trd slash command
commands/review-go.md                    # /review-go slash command
skills/vibe-engineering/SKILL.md         # TRD-to-GitHub-issues pipeline
```

The install should have written a manifest at `~/.config/opencode/.vibe-engineering-manifest.json`.

## Step 3 — OpenCode config (`~/.config/opencode/opencode.jsonc`)

The installer merges safe non-secret defaults (`$schema`, `lsp: true`) into `opencode.jsonc`. It NEVER touches `model`, `provider`, `plugin`, `mcp`, `tools`, or `env` — those are local-only and preserved as-is.

If `opencode.jsonc` is missing entirely, create a minimal one:

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "lsp": true
}
```

Then layer on your own model, provider, plugin, and MCP config — these are not the kit's concern.

## Step 4 — Report

After completing all steps, print a checklist:

```
vibe CLI installed                       : [ok / missing]
AGENTS.md                                : [created / already existed]
rules/operating-model.md                 : [created / already existed]
rules/go-backend-engineering.md          : [created / already existed]
rules/security-and-data-safety.md        : [created / already existed]
rules/database-and-operations.md         : [created / already existed]
rules/testing-and-verification.md        : [created / already existed]
agents/backend-tech-lead.md              : [created / already existed]
agents/go-backend-implementer.md         : [created / already existed]
agents/security-data-reviewer.md         : [created / already existed]
agents/db-operations-reviewer.md         : [created / already existed]
agents/tdd-test-engineer.md              : [created / already existed]
commands/trd.md                          : [created / already existed]
commands/review-go.md                    : [created / already existed]
skills/vibe-engineering/SKILL.md         : [created / already existed]
vibe-engineering-manifest.json           : [wrote / already existed]
opencode.jsonc                           : [merged / untouched / created]

Setup complete.
```
