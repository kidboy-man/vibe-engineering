# Memory Compiler — Optional Add-On

[claude-memory-compiler](https://github.com/coleam00/claude-memory-compiler) automatically captures Claude Code sessions and compiles them into wiki pages. After 6 PM daily, the day's conversations become structured knowledge.

## What It Does

- Captures session transcripts at `SessionStart` and `SessionEnd`
- Compiles daily conversations into wiki pages
- Runs as Python hooks wired into Claude Code's hook system

## Install

```bash
cd <vault>
git clone https://github.com/coleam00/claude-memory-compiler.git /tmp/cmc
mkdir -p .claude/memory-compiler/{scripts,hooks,daily}
cp /tmp/cmc/scripts/*.py .claude/memory-compiler/scripts/
cp /tmp/cmc/hooks/*.py .claude/memory-compiler/hooks/
cp /tmp/cmc/AGENTS.md .claude/memory-compiler/AGENTS.md
cp /tmp/cmc/pyproject.toml .claude/memory-compiler/pyproject.toml
cp /tmp/cmc/uv.lock .claude/memory-compiler/uv.lock
cd .claude/memory-compiler && uv sync
```

## Prerequisites

- **uv** (Python package manager): `uv --version`
- **Python 3.12+**: `python3 --version`

## Wire Hooks

Add three hooks to `<vault>/.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [{
      "matcher": "",
      "hooks": [{
        "type": "command",
        "command": "cd <vault> && uv run --project .claude/memory-compiler python .claude/memory-compiler/hooks/session-start.py 2>/dev/null || true"
      }]
    }],
    "SessionEnd": [{
      "matcher": "",
      "hooks": [{
        "type": "command",
        "command": "cd <vault> && uv run --project .claude/memory-compiler python .claude/memory-compiler/hooks/session-end.py 2>/dev/null || true"
      }]
    }],
    "PreCompact": [{
      "matcher": "",
      "hooks": [{
        "type": "command",
        "command": "cd <vault> && uv run --project .claude/memory-compiler python .claude/memory-compiler/hooks/pre-compact.py 2>/dev/null || true"
      }]
    }]
  }
}
```

## Gitignore Required

Memory-compiler writes daily logs and state JSON files. Add these to `.gitignore` to avoid commit churn:

```gitignore
.claude/memory-compiler/daily/
.claude/memory-compiler/scripts/*.log
.claude/memory-compiler/scripts/*.json
.claude/memory-compiler/scripts/session-*.md
.claude/memory-compiler/.venv/
```

## Warnings

- **Token cost**: Hooks run on every session start/end. This adds latency and token usage to every Claude Code session.
- **Claude Code only**: This add-on only works with Claude Code. Other agents (OpenCode, Codex, Hermes, Cursor) do not support these hooks.
- **No auto-config**: This kit does not automatically install or configure memory-compiler. Follow the steps above manually if you want it.
