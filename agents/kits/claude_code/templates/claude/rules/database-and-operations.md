# Database and Operations

## Database Discipline

Treat database changes as production-impacting changes.

For schema changes:

- prefer backward-compatible migrations
- consider expand/contract rollout when needed
- avoid long locks on hot tables
- add indexes intentionally and justify them
- use explicit column lists; never use `SELECT *` in production queries
- preserve existing data and constraints
- plan data backfills separately from schema changes when appropriate
- define rollback or mitigation strategy
- consider tenant isolation and RLS implications when applicable
- ask before risky or irreversible schema/data changes

## Query and Persistence Standards

- Use parameterized queries only.
- Keep persistence concerns out of domain logic.
- Make transaction boundaries explicit.
- Use consistent repository/data-access patterns already present in the project.
- Avoid N+1 queries and unbounded result sets.
- Add pagination, limits, and indexes for list/search paths.
- Consider isolation levels and locking behavior for concurrent writes.

## Migrations

- Migrations should be deterministic and reviewable.
- Avoid mixing large data backfills with schema changes unless justified.
- For destructive changes, prefer multi-step rollout: add new structure, dual-write/backfill, migrate reads, then remove old structure.
- Include down/rollback behavior when the project convention supports it.
- Never run migrations against shared/staging/production databases without explicit approval.

## Observability and Operations

For backend/service changes, consider operational behavior as part of correctness:

- structured logs with useful context, without leaking secrets or PII
- metrics for critical paths, failures, latency, queues, workers, and external calls when applicable
- tracing across request, transaction, and async boundaries when available
- timeouts and cancellation for external calls and long-running work
- retry/backoff policies with idempotency and bounded attempts
- health/readiness checks for services with dependencies
- graceful shutdown for servers, goroutines, workers, and consumers

Do not add noisy logs or metrics for trivial code paths.

## Dependency Discipline

Prefer the standard library and existing project dependencies.

Before adding a new production dependency:

- check whether the project already has an accepted library for the purpose
- evaluate maintenance, license, transitive dependency risk, and API stability
- ask before adding it unless the user explicitly requested it

Dev/test-only dependencies may be added more freely when they clearly improve verification, but still prefer existing project conventions.
