# Testing and Verification

## TDD Policy

Use TDD by default for non-trivial backend behavior.

Preferred loop:

1. Write or update a failing test that captures the desired behavior or bug.
2. Implement the smallest correct change.
3. Refactor while keeping tests green.

TDD is strongly preferred for:

- domain logic
- authorization and access-control rules
- tenancy/isolation rules
- billing/state-machine behavior
- data consistency
- concurrency
- bug fixes with clear reproduction steps
- parsers, validators, and edge-case-heavy code

TDD may be skipped for:

- mechanical renames
- formatting
- comments/docs
- generated code
- trivial wiring with no behavior change

Even when not doing strict TDD, do not finish without relevant verification.

## Test Quality

- Use table-driven tests for Go behavior with multiple cases.
- Test behavior and externally visible outcomes, not implementation details.
- Include edge cases, error paths, and boundary conditions.
- Prefer deterministic tests. Avoid sleeps and timing-sensitive assertions when possible.
- Use fakes/stubs at boundaries; avoid real external services unless the test is explicitly integration-level.
- Make tests readable enough to document expected behavior.

## Verification Strategy

Run checks in this order when practical:

1. Focused tests for changed behavior.
2. Package/module tests for touched areas.
3. Integration tests when the change crosses boundaries.
4. Lint/format/typecheck/build as appropriate for the project.

Use the project's existing commands and conventions. If uncertain, inspect README, Makefile, package scripts, CI config, or existing docs before inventing commands.

## Definition of Done

Before final response:

- run relevant verification or explain why it could not be run
- inspect the diff for accidental edits
- confirm no debug prints, secrets, or unrelated changes were introduced
- report exact commands and results
- state unverified risks clearly

Do not claim tests passed unless they actually ran and passed.
