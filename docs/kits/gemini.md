# Gemini CLI Kit

[← Back to README](../../README.md)

Portable Gemini CLI setup for senior backend engineering. Installs a single
`GEMINI.md` file with the full persona, all six engineering rules, and specialist
role descriptions embedded inline. Gemini CLI reads a single global
instructions file, so no separate rule files are needed.

## Commands

```bash
vibe kits gemini doctor
vibe kits gemini install --dry-run
vibe kits gemini install --yes
vibe kits gemini diff
vibe kits gemini uninstall --yes
```

## What it installs

`~/.gemini/GEMINI.md` — a single self-contained file containing:

- senior/staff backend engineering persona and operating identity
- task risk policy and autonomy boundaries
- all six modular engineering rules (operating model, Go backend, testing, security/data, database/ops, uncertainty/sources) embedded as sections
- specialist role descriptions for all five subagent modes (backend-tech-lead, go-backend-implementer, security-data-reviewer, db-operations-reviewer, tdd-test-engineer)
- communication style and definition of done

Rules are embedded rather than referenced because Gemini CLI loads a single
instructions file rather than a rules directory.
