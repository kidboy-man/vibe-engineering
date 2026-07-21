## Second-Brain Vault

You have a personal knowledge vault at `$VIBE_SECOND_BRAIN_PATH` (or `~/second-brain`
if unset), searchable via the `qmd` MCP server (tools: `query`, `get`, `multi_get`, `status`).
A summary of `wiki/hot.md` and `wiki/index.md` is auto-loaded into context at the
start of every session (see the SessionStart hook) — you do not need to ask the
user before reading it.

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

### Automatic durable capture

After resolving a nontrivial bug, adopting a project convention, or reaching a
durable decision, use the installed `second-brain` skill. It writes one
secret-free draft to `inbox/` automatically. Only promote a draft into the
searchable wiki when the user asks; then update the index and meta pages.
