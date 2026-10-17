# Data Model: Wikify Sync and Drift Checks

## `.wikify.json` (state file, `docs/wiki/.wikify.json`)

Version stays `1`. All new keys are optional; readers MUST preserve keys they do not understand and
writers MUST NOT drop them (`state.load`/`state.save` change; older `mark` simply drops the new keys,
which degrades to "no range hash yet" and unregistered imported pages).

```json
{
  "version": 1,
  "covered": "<head sha or null>",
  "imported_mode": "editable",
  "citations": { "<page>|<path>:<start>-<end>|<symbol-or-empty>": "<12 hex>" },
  "imported": { "<page>": "<16 hex>" }
}
```

| Key | Type | Written by | Rule |
|-----|------|-----------|------|
| `covered` | string or null | `mark` | unchanged |
| `imported_mode` | `editable` or `frozen` | user (edit by hand) | default `editable`; invalid value -> `editable` plus a notice |
| `citations` | map string -> 12-hex | `mark` | rebuilt from the current pages on every successful `mark`; entries for citations that no longer exist are dropped |
| `imported` | map page -> 16-hex | `migrate-imported --apply` (legacy docs) and `adopt --apply` (pages it creates); `mark` re-records hashes for already-registered pages | page text hash; only pages that satisfy the imported-wrapper shape are accepted |

Size: about 100 bytes per citation; `citations` is bounded by the existing `MAX_CITATIONS` per
page. `state.load` has no size cap, so no new cap is introduced. Written with sorted keys, one per
line. `reanchor --apply` re-keys moved entries (same hash, new `start-end`) in the same operation.

## Entities

### Citation (existing `citations.Citation`)
`path, start, end, symbol, line` + derived `key` (above) + `baseline_hash` (optional).

### DriftFinding
| Field | Notes |
|-------|-------|
| `page` | page path relative to `docs/wiki` |
| `line` | page line of the citation |
| `category` | `moved` / `changed` / `missing` |
| `path`, `start`, `end`, `symbol` | cited location |
| `new_start`, `new_end` | only for `moved` |
| `reason` | short human text (`ambiguous: 2 matches`, `file not tracked`, `no range hash yet` is a separate notice, not a category) |
| `commits` | up to 5 short hashes touching `path` since the base |

### UncoveredFinding
`area` (a `plan._contexts` context that no page cites), `files` (changed paths, capped),
non-failing. JSON key `uncovered_areas`.

### ReferenceFinding
`page`, `line`, `kind` (`DEAD PATH` / `DEAD SYMBOL` / `STALE LINK`), `token`. Non-failing.

### CheckResult
`ok` (bool), `counts` (incl. `unbaselined_changed`), `drift` (list), `uncovered_areas`, `references`, `notices`, `warnings`, `error` (string or
null). Rendered as text, or JSON with `--json` (schema in `contracts/cli.md`).

### ImportedPage
A page whose entire text is exactly one `adopt_plan` wrapper (`is_wrapped`), registered in
`imported`. States: `unregistered` (behaves as a human-block page) -> `registered` (hash
tracked) -> `edited` (hash differs, notice) -> `registered` again after `mark`.

### WorkItem (sync)
`priority` (1 moved, 2 changed, 3 missing, 4 uncovered, 5 reference), `page`, `action` text,
`detail`. Ordered by (priority, page, line).

## State transitions (page citation)

```
clean --(code edit above)--> moved --(reanchor --apply / mark --reanchor)--> clean
clean --(code edit inside range)--> changed --(agent updates page, mark)--> clean
clean --(file/symbol deleted)--> missing --(agent edits/removes with user OK, mark)--> clean
moved --(also edited / ambiguous)--> changed
```
