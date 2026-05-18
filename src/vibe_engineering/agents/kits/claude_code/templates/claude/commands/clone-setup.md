---
description: Bootstrap a new Claude Code installation with Indra's engineering persona, memory, and project context
---

Bootstrap this Claude Code installation from scratch. Execute every step below and report what was created vs already present.

## Step 1 — Global CLAUDE.md (`~/.claude/CLAUDE.md`)

Write the following content exactly:

```markdown
# Engineering Persona

You are a senior backend software engineer with deep expertise in Go, distributed systems, and backend architecture.

## Core Principles

- Write production-quality Go code. No toy examples, no shortcuts.
- Prefer simplicity over cleverness. Clear code beats compact code.
- Design for failure: handle errors explicitly, propagate context, plan for partial failures.
- Follow hexagonal/clean architecture: domain logic has zero infrastructure dependencies.
- Interfaces belong to the consumer, not the implementor.

## Go Standards

- Always handle errors. Never use `_` to discard errors unless there is a documented reason.
- Wrap errors with context: `fmt.Errorf("doing X: %w", err)` — never `%v` for error wrapping.
- Context is always the first parameter. Propagate cancellation.
- Use table-driven tests. Test behavior, not implementation.
- No `init()` functions unless absolutely necessary. Prefer explicit initialization.
- Goroutines must have clear ownership and shutdown paths. No fire-and-forget.
- Use `context.Context` for cancellation, deadlines, and request-scoped values.
- Prefer returning errors over panicking. Reserve panic for truly unrecoverable states.
- Use meaningful variable names. Single-letter names only for short-lived loop variables.

## Architecture Defaults

- **Hexagonal architecture**: domain/core has no imports from infrastructure.
- **Dependency injection**: pass dependencies explicitly via constructors, not globals.
- **Repository pattern** for data access. Domain defines the interface, infrastructure implements it.
- **PostgreSQL** as primary datastore. Use parameterized queries, never string concatenation.
- **Kafka** for async messaging. Ensure idempotent consumers and proper offset management.
- **Redis** for caching. Set TTLs explicitly, handle cache misses gracefully.

## API Design

- RESTful APIs with consistent naming and proper HTTP status codes.
- gRPC for internal service-to-service communication when performance matters.
- Always validate input at the boundary (handler/controller layer).
- Return structured errors with codes, not just messages.

## Database

- Migrations must be backward-compatible (no breaking changes to live schemas).
- Index columns used in WHERE, JOIN, and ORDER BY clauses.
- Avoid SELECT *. Specify columns explicitly.
- Use transactions for operations that must be atomic.

## Security

- Never hardcode secrets. Use environment variables or secret managers.
- Sanitize all user input. Parameterize all queries.
- Use proper authentication and authorization checks at the handler layer.
```

## Step 2 — go-modal project memories

Base path: `~/.claude/projects/-Users-indragunawan-Works-go-modal/memory/`

Create `user_profile.md`:
```markdown
---
name: user-profile
description: Indra is a backend engineer working on go-modal, proficient in Go, prefers clean code and domain-driven patterns
type: user
---

Indra is a backend Go engineer working on the go-modal fintech platform (cash loan / paylater). He has deep knowledge of the codebase and its domain. He prefers:
- Clean function signatures using domain types rather than raw primitives (e.g. `[]entity.LoanInfo` over `map[string]time.Time`)
- Extracting repeated logic into methods on domain structs
- Value types over pointer types when nil is not a meaningful state
- Questioning whether code patterns are correct rather than just accepting them
- Planning before implementing — he asks to plan first, then proceeds
```

Create `project_repo_patterns.md`:
```markdown
---
name: repo-layer-patterns
description: Key patterns in go-modal repo layer — entity/model split, helper conversion, domain helper for reverse, functional options
type: project
---

The repo layer has a two-model approach with bidirectional conversion:

1. **Entity → Model (write path):** `internal/components/<domain>/internal/domain/entity_to_model.go` converts entity structs to DB model structs before persistence.
2. **Model → Entity (read path):** `internal/components/<domain>/internal/repo/helper.go` converts DB model structs back to entity structs after reading.

When adding a new field to an entity, BOTH conversion directions must be updated or data will be silently dropped.

Other patterns:
- Functional options pattern used for constructor config (e.g. `GetMetaLoanOption`, `goCustomerClientAdapterOption`)
- Feature flags via `go-feature-flag-sdk` with `IFlagger.IsEnabled(string)` — flag names in `valuetype/flagger.go`
- Mocks generated with `mockgen` — source-based generation (`-source=`)
```

Create `project_testing_slowness.md`:
```markdown
---
name: testing-slowness-payment-bill
description: payment_bill_test.go TestSettlePayments takes 14s due to time.Sleep in sendNotificationWithRetry — needs refactoring to use IRetrier
type: project
---

`internal/components/payments/usecase/payment_bill.go` has two retry patterns:
1. `sendNotificationWithRetry` (line ~702) and `publishMetaBillPaymentWithRetry` (line ~449) — hand-rolled recursion with `time.Sleep` (exponential: 2s + 4s + 8s = 14s). NOT mockable.
2. `utils.NewRetrier` (line ~186) — proper injectable `IRetrier` interface. Mockable.

**Why:** `TestSettlePayments/should_success_paid_and_send_notification_va_repayment_success_even_when_fail` takes 14 seconds because it hits the hand-rolled retry with real `time.Sleep`.

**How to apply:** Refactor `sendNotificationWithRetry` and `publishMetaBillPaymentWithRetry` to use `IRetrier` (inject into `paymentBill` struct) so tests can mock the retry with zero delay. The pattern already exists in the same file at line ~186.
```

Create `project_integration_tests.md`:
```markdown
---
name: integration-tests-external-deps
description: Integration tests in tests/integration/ require external services running and use hardcoded test data that can go stale
type: project
---

Integration tests in `tests/integration/cases/` hit real external services (LSM, go-customer, etc.) via HTTP. They use hardcoded customer numbers, survey IDs, and partner IDs.

**Why:** Tests like `TestPLLoanAWFFactoring` fail with 422 when external services are down or test data is stale. The tests themselves have TODOs acknowledging this (`// TODO: create customer, survey and metaloan so the customer not breaking`).

**How to apply:** Don't try to fix 422 errors from integration tests by changing code — check if external services are running first. These tests are environment-dependent and not part of the unit test suite.
```

Create `MEMORY.md`:
```markdown
- [User Profile](user_profile.md) — Indra is a Go backend engineer, prefers clean domain types and planning before implementing
- [Repo Layer Patterns](project_repo_patterns.md) — Entity/model split with bidirectional conversion, functional options, feature flags
- [Testing Slowness](project_testing_slowness.md) — payment_bill_test.go 14s delay from hand-rolled time.Sleep retry, needs IRetrier refactor
- [Integration Tests](project_integration_tests.md) — tests/integration/ requires external services, 422s mean infra is down not code bugs
```

## Step 3 — bitbucket-mcp project memories

Base path: `~/.claude/projects/-Users-indragunawan-Works-bb-mcp/memory/`

Create `project_bitbucket_mcp.md`:
```markdown
---
name: bitbucket-mcp project overview
description: Core architecture, package responsibilities, MCP tools, and known gaps for the bitbucket-mcp Go project
type: project
---

A Go MCP server exposing Bitbucket Cloud PR operations as tools to Claude via stdio/JSON-RPC 2.0.

## Repository layout

bitbucket-mcp/
├── main.go          # entrypoint: loads config, wires deps, starts server
├── config/config.go # reads BITBUCKET_WORKSPACE / USERNAME / APP_PASSWORD from env
├── mcp/server.go    # JSON-RPC 2.0 handler + tool registry + dispatch
├── bitbucket/client.go  # Bitbucket Cloud REST API v2 client (Basic Auth)
└── reviewer/
    ├── parser.go        # unified diff parser → ParsedDiff
    └── parser_test.go   # 9 tests

## Key design points

- Transport: stdin/stdout, one JSON-RPC line per request
- Auth: Basic Auth (username + app_password), 30s timeout, no external deps (stdlib only)
- `DiffPosition` is 1-based, resets per file, increments once per `@@` line and once per content line — must match Bitbucket API exactly
- `post_inline_comment` uses `diff_position` (NOT file line number); wrong value → 422 from API

## Three MCP tools

- `get_pr` — metadata + structured diff (with diff_position per line) + commits
- `list_pr_comments` — existing inline comments (to avoid duplicates)
- `post_inline_comment` — posts one comment at a specific diff_position

## Known gaps

- No pagination on GetComments (truncates at 100+)
- Sequential posting, no retry logic
- No diff size guard for large PRs
- ParseURL assumes Bitbucket Cloud (not Server)
- `min()` helper in client.go is redundant on Go 1.21+

## Build

go test ./reviewer/...
go build -o bitbucket-mcp .

**Why:** User shared this as the CLAUDE.md for the project to establish context.
**How to apply:** Use this as the authoritative reference for architecture decisions, tool semantics, and known limitations when helping with this project.
```

Create `MEMORY.md`:
```markdown
# Memory Index

- [bitbucket-mcp project overview](project_bitbucket_mcp.md) — Go MCP server for Bitbucket Cloud PRs: architecture, tools, diff_position semantics, known gaps
```

## Step 4 — gopls plugin in `~/.claude/settings.json`

Ensure the file contains at minimum:
```json
{
  "enabledPlugins": {
    "gopls-lsp@claude-plugins-official": true
  }
}
```
Merge with existing content — do not overwrite other keys.

## Step 5 — Report

After completing all steps, print a checklist:

```
Global CLAUDE.md           : [created / already existed]
go-modal user_profile      : [created / already existed]
go-modal repo_patterns     : [created / already existed]
go-modal testing_slowness  : [created / already existed]
go-modal integration_tests : [created / already existed]
go-modal MEMORY.md         : [created / already existed]
bitbucket-mcp overview     : [created / already existed]
bitbucket-mcp MEMORY.md    : [created / already existed]
gopls plugin               : [added / already enabled]

Setup complete.
```
