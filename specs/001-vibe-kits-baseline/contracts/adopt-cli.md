# Contract: `vibe wikify adopt`

```text
vibe wikify adopt [--map FILE] [--include GLOB] [--exclude GLOB]
                  [--apply] [--report] [--rewrite-refs] [--prune-sources] [--force]
```

| Flag | Behavior |
|------|----------|
| (none) | Dry run. Prints per file: source, destination, kind, skip reason, inbound refs. Writes nothing. |
| `--map FILE` | Mapping file to use; default `docs/wiki/.wikifymap`. |
| `--include` / `--exclude` | Narrow the candidate set by glob; same grammar limits as `.wikifyignore`. |
| `--apply` | Perform `git mv`, wrap bodies in human blocks, update the map, then run verify. |
| `--report` | Print the JSON in `adopt-report.schema.json` to stdout; implies no writes unless `--apply` is also given. |
| `--rewrite-refs` | Also rewrite relative links in moved files and in other tracked docs-only files. |
| `--prune-sources` | Also remove unrelated stale generated `sources/` pages. Outline pages of the docs this run moves are always removed. |
| `--force` | Allow a dirty tree or detached HEAD. |

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Dry run or apply completed; for apply, verify passed |
| 1 | Refused (not a git repo, wiki not initialised, dirty tree or detached HEAD without `--force`, unsafe path, inventory failed) or verify failed after apply |

## Guarantees

- Dry run is the default and has no side effects (Constitution II).
- Never overwrites an existing file; never deletes without `--prune-sources`.
- A second `--apply` is a no-op.
- Stdout contains no repo prose beyond paths and counts; repo content is treated as untrusted data.
- The CLI never calls a model and never touches the network.

## Printed commit plan

```text
1. git commit            # staged pure renames (+ `git add` of rewritten refs outside docs/wiki/)
2. vibe wikify mark
3. git add -- docs/wiki && git commit   # wrapped bodies, map, outline removal, .wikify.json (docs-only)
```

The renames are one commit so `git log --follow` works; the command prints this plan and never commits.
Re-running before commit 1 requires `--force` (resume); after both commits it is a no-op.
