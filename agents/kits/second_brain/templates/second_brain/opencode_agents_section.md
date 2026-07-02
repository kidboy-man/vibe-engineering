## Second-Brain Vault

You have a personal knowledge vault at `$VIBE_SECOND_BRAIN_PATH` (or `~/second-brain`
if unset), searchable via the `qmd` MCP server (tools: `query`, `get`, `multi_get`, `status`).

OpenCode has no session-start context-injection hook, so `wiki/hot.md` and
`wiki/index.md` are not auto-loaded here the way they are for Claude Code,
Codex CLI, and Cursor. Read them yourself at the start of a session if you
need current vault state.

### When to actively query the vault

Proactively search the vault with `qmd` (no need to wait for "ingest this" /
"lint the wiki" style trigger phrases) when:
- you are about to research an unfamiliar library, service, or pattern the user
  may have already investigated before;
- the user references past work, a past decision, or asks "have I dealt with
  this before?" / "what did we decide about X?";
- you are starting a nontrivial new task and a quick check could save
  re-derivation of an existing decision or gotcha.

Skip querying for trivial, purely local, or time-sensitive tasks, and never
block on the vault or qmd being unavailable — treat it as best-effort context,
not a hard dependency.

### When to write learnings back

After resolving a nontrivial bug, adopting a project convention, or reaching a
durable decision worth remembering across sessions, offer to file it into the
vault (one source/concept page under the right `wiki/` subfolder, cross-linked,
with `wiki/index.md` and `wiki/log.md` updated) rather than letting it evaporate
at session end. Do not batch-ingest; do this incrementally, one item at a time,
and ask before writing when in doubt.
