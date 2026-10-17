# Quickstart: validating the baseline and `wikify adopt`

## Prerequisites

- Python 3.10+, git, a clone of this repo on Linux, macOS, or WSL.
- `python3 -m pip install -e .` (provides the `vibe` command).

## 1. Baseline still holds (User Stories 1-6)

```bash
python3 -m unittest discover -s tests
vibe kits list
vibe kits claude-code install --dry-run --yes     # expect: plan printed, no files written
```

Expected: all tests pass, every registered kit is listed, the dry run leaves `~/.claude` unchanged.

## 2. Adopt on a fixture repo (User Story 7, after implementation)

Use a scratch copy of a fixture from `tests/fixtures/adopt/` (never your real repo first).

```bash
cd "$(mktemp -d)" && cp -r <repo>/tests/fixtures/adopt/nested-docs/. . && git init -q && git add -A && git commit -qm init
vibe wikify init
vibe wikify adopt                      # dry run: table of moves, skips, inbound refs
vibe wikify adopt --report > report.json
# edit docs/wiki/.wikifymap, review the dry run again
vibe wikify adopt --apply              # git mv (staged), human-block wrap, map update
git commit -m 'docs(wiki): move docs'  # commit 1: staged renames only
vibe wikify verify && vibe wikify mark
git add -- docs/wiki && git commit -m 'docs(wiki): adopt'   # commit 2: docs-only
vibe wikify adopt --apply              # second run: no-op
vibe wikify plan                       # expect: nothing uncovered
```

Expected outcomes (map to Success Criteria):

| Check | Spec reference |
|-------|----------------|
| Dry run writes nothing (`git status` clean) | FR-017, SC-003 |
| Moved bodies hash-equal to originals | FR-019, SC-009 |
| Build-coupled, ignored, secret files remain, listed with reasons | User Story 7 scenario 3 |
| Second apply changes nothing | FR-021, SC-009 |
| Dirty tree refuses without `--force` | FR-021 |
| Printed commit plan lists outside-wiki and docs-only commits | FR-021 |

## 3. Skill walkthrough

Follow `tests/fixtures/adopt/WALKTHROUGH.md` with an agent that has the `wikify-adopt` skill installed
(`vibe kits wikify install --yes`). Expected: the agent edits only `.wikifymap` and wiki pages, never
migrated prose, and stops for your confirmation before each commit.
