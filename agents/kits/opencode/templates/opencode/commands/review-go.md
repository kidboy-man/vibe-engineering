---
description: Review staged and unstaged Go code changes before pushing. Checks security vulnerabilities, hexagonal architecture violations, Go code quality, and test coverage. Reports findings grouped by severity (HIGH/MEDIUM/LOW) and returns a PASS or BLOCK verdict.
---

You are a senior Go engineer performing a pre-push code review. Your job is to find real problems — not to nitpick style. Be precise: every finding must reference a file and line number.

---

## Step 1 — Get the diff

Run the following to collect all changes (staged + unstaged) since the last commit:

```bash
git diff HEAD $ARGUMENTS
git diff --cached $ARGUMENTS
```

If `$ARGUMENTS` is provided, it scopes the diff to that path. Deduplicate if both commands return overlapping output.

If the combined diff is empty, stop immediately and respond:

> Nothing to review — working tree is clean.

---

## Step 2 — Read context

- If `AGENTS.md` exists in the project root, read it. Use its architecture rules as ground truth.
- For any changed file where the diff alone is insufficient to judge correctness (e.g. a function that calls something you can't see), read the full file.

---

## Step 3 — Review across four categories

Work through the diff methodically. For each finding, note the file path and line number from the diff.

### A. Security

Flag any of the following:

- **Hardcoded secrets** — API keys, tokens, passwords, private keys anywhere in code (not just config files)
- **Unvalidated input** — user-supplied data reaching a DB query, shell command, file path, or storage call without sanitization or parameterization
- **Missing auth/permission check** — new HTTP handler registered on a protected route group but no middleware applied, or a service method that skips an authorization check that analogous methods enforce
- **Sensitive field serialization** — struct fields holding passwords, hashes, or tokens that lack `json:"-"` and are returned in handler responses
- **File upload gaps** — multipart file handling that trusts `Content-Type` header instead of checking magic bytes, or reads the file with no size cap
- **SQL injection** — any query built by string concatenation instead of parameterized placeholders
- **Stack trace leak** — `err.Error()` or `fmt.Sprintf("%+v", err)` written directly into an HTTP response body

### B. Architecture (hexagonal boundaries)

This project enforces strict hexagonal architecture. Flag any of the following:

- Any file under `internal/core/` importing from `internal/adapter/` or `internal/infrastructure/`
- Any service file importing `github.com/gin-gonic/gin` or referencing `*gin.Context`, HTTP request or response types
- A repository implementation placed inside `internal/core/` instead of `internal/adapter/repository/`
- An interface defined in the same package as its implementation (interfaces belong to the consumer)
- A wide interface dependency where only one or two methods are used — should be a narrow interface (consumer-defined)
- Domain structs in `internal/core/domain/` carrying GORM struct tags (`gorm:"..."`) or `gorm.DeletedAt`
- A new cross-domain service dependency (e.g. one domain's service taking a full service interface from another domain)

### C. Code quality (Go standards)

- `_ = err` or blank identifier discarding an error without an explanatory comment
- Errors wrapped with `fmt.Errorf("...: %v", err)` — must use `%w` for unwrapping
- A function that calls a database, cache, or external service but does not accept `context.Context` as its first parameter
- Use of `panic()` where returning an error is appropriate
- A goroutine launched without a documented owner or shutdown mechanism
- An `init()` function added without a documented reason
- Single-letter variable names used outside of short loop bodies (e.g. `i`, `j` in a for loop is fine; `c` for a complex struct is not)
- Dead code: unreachable `return` or `case` branches, exported symbols that are never referenced
- GORM queries that use `Select("*")` or omit `WHERE deleted_at IS NULL` on soft-delete tables

### D. Test coverage

- A new exported function or method with no test in any `_test.go` file in the same package
- A new HTTP handler with no corresponding handler-level or service-level test
- A new error path (new `return nil, err` or `return domain.ErrXxx`) in a service with no test asserting that error is returned under the right conditions
- A test that only covers the happy path when the new code introduces obvious edge cases (empty input, concurrent modification, nil pointer)

---

## Step 4 — Report findings

Use this exact format for each finding:

```
[SEVERITY] CATEGORY — file/path.go:LINE
Problem: one sentence describing what is wrong.
Fix: one sentence describing the concrete remediation.
```

Group all findings under three Markdown headers. Omit a section entirely if there are no findings at that level.

```
## HIGH
## MEDIUM
## LOW
```

**Severity definitions:**
- **HIGH** — security vulnerability, architectural boundary violation, data-correctness bug, or error silently discarded on a critical path. Must be fixed before pushing.
- **MEDIUM** — code quality issue with realistic runtime failure potential, or a missing test for a high-risk code path.
- **LOW** — minor style issue, missing test for low-risk path, improvement opportunity. Advisory only.

Do not invent findings. If you are uncertain whether something is actually a problem given the full context, note it as LOW with a clear "verify this" qualifier rather than escalating it.

---

## Step 5 — Verdict

After the findings (or immediately if there are none), print a horizontal rule and one of the following verdicts:

```
---
VERDICT: BLOCK — N HIGH finding(s) must be resolved before pushing.
```

```
---
VERDICT: PASS — no HIGH findings. Review MEDIUM/LOW items at your discretion.
```

Nothing else after the verdict line.
