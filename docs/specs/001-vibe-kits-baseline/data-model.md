# Data Model: `vibe wikify adopt`

Only the planned delta is modeled; baseline entities (Kit, Manifest, Hook registration, Wiki) already exist.

## Doc candidate

One markdown file considered for adoption.

| Field | Meaning |
|-------|---------|
| `source` | repo-relative path of the file |
| `destination` | repo-relative path under `docs/wiki/`, empty when skipped |
| `kind` | `spec`, `adr`, `reference` (from the mapping rule, default `reference`), or `skipped` |
| `skip_reason` | set only when `kind = skipped`: `build-coupled`, `ignored`, `secret-path`, `secret-hit`, `non-markdown`, `root-file`, `collision`, `unsafe-body`, `unsafe-path`, `unmapped` |
| `inbound_refs` | list of `{file, line, rewritable}` references to this file from elsewhere |
| `body_sha256` | hash of the body before the move, for the no-content-loss check |

Rules:
- `destination` is unique across candidates and MUST NOT exist already (never overwrite).
- `source` MUST be a tracked, regular, UTF-8 markdown file inside the repo; symlinks are skipped.
- Non-markdown assets and `.markdown` files never move (`walk_wiki` allows only `.md` under `docs/wiki/`); links to them from moved docs are reported in `unresolved_refs`.
- Root-level files move only when a mapping rule names the exact path.

## Mapping rule (in `.wikifymap`)

`source-glob -> destination-folder/ [kind=spec|adr|reference]`, first match wins, `#` comments, bounded size and wildcard count.
Absent rule for a candidate means `skip_reason = unmapped`, reported, never guessed by the CLI.

## Adopted page

A wiki page produced by a move.

- Body: original markdown wrapped verbatim in one human block.
- First line inside the block: `<!-- imported from=<source> -->`.
- Map entry: one `<!-- wikify:map -->` entry, hint derived mechanically from the title; grouped under
  per-folder index pages when the map caps would be exceeded.

## Adoption report (JSON)

Machine-readable output of `--report`; schema in `contracts/adopt-report.schema.json`.
Top-level: `moves`, `skips`, `unresolved_refs`, `unclassified`, `suggested_contexts`, `commit_plan`.

## State transitions

```text
unmapped -> mapped (mapping file edited, approved by a human)
mapped -> moved (apply: git mv + wrap in human block)
moved -> moved (re-apply: no-op)
skipped -> skipped (reason stays until the cause is fixed by the user)
```
