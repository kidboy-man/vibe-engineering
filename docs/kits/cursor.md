# Cursor IDE Kit

[← Back to README](../../README.md)

Portable Cursor IDE setup for senior backend engineering. Installs rule files
into `~/.cursor/rules/` as `.mdc` files. Each file has YAML frontmatter
(`description`, `globs`, `alwaysApply`) so Cursor can selectively load rules
based on file type.

## Commands

```bash
vibe kits cursor doctor
vibe kits cursor install --dry-run
vibe kits cursor install --yes
vibe kits cursor diff
vibe kits cursor uninstall --yes
```

## What it installs

Seven `.mdc` files into `~/.cursor/rules/`:

| File | `alwaysApply` | Scope |
|------|---------------|-------|
| `00-persona.mdc` | `true` | global persona, risk policy, autonomy, definition of done |
| `operating-model.mdc` | `true` | workflow, risk classification, scope discipline |
| `security-and-data-safety.mdc` | `true` | authz, secrets, injection, tenant isolation |
| `uncertainty-and-sources.mdc` | `true` | epistemic honesty, citation standards |
| `go-backend-engineering.mdc` | `false` | Go-specific rules; globs `**/*.go` |
| `testing-and-verification.mdc` | `false` | TDD, test quality; globs test file patterns |
| `database-and-operations.mdc` | `false` | migrations, queries, transactions; globs DB file patterns |

**Note:** Cursor 0.45+ also supports project-local rules at `.cursor/rules/`. For
per-project behavior, copy the relevant `.mdc` files from `~/.cursor/rules/` into
your project's `.cursor/rules/` directory and adjust as needed.
