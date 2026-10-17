# Walkthrough: syncing the wiki after a code change

This is the loop the `wikify-sync` skill follows. `tests/test_wikify_skill_walkthrough.py` parses
every `vibe wikify` command below against the real CLI and replays the loop on a scratch repo.

Setup: a wiki page cites `app/svc.py:10-20 \`handle\``, and the wiki was last marked and committed.

## 1. Two things changed in the code

Someone added helper lines above `handle` (the citation now points at the wrong lines) and edited
the body of `handle`'s caller in another file that a second page cites.

```
vibe wikify sync
```

`sync` is read-only. It prints the work list, ordered `moved`, `changed`, `missing`, `uncovered`:

```
work list (2):
  1. moved     svc.md:1  run: vibe wikify reanchor --apply (10-20 -> 13-23)
  2. changed   billing.md:4  read app/billing.py:5-12 and update the claim (cited body changed)
```

## 2. Heal the mechanical drift

```
vibe wikify reanchor
vibe wikify reanchor --apply
```

The first command previews; the second rewrites only the line numbers of `moved` citations. It
refuses a citation whose body changed or that matches twice, and then exits 1: that is your cue
for step 3, not a failure of the healing.

## 3. Update what the code really changed

Open `app/billing.py:5-12`, compare it with the paragraph in `billing.md`, and update the paragraph
and its citation. Do not state anything you did not read in the code. If a doc contradicts the
code, report it to the user instead of smoothing it over.

## 4. Verify and mark

```
vibe wikify verify
vibe wikify mark
```

`verify` must pass (notices such as `IMPORTED PAGE EDITED` are for the user to review). `mark`
records the covered commit and the range hashes. `vibe wikify mark --reanchor` does step 2 first.

## 5. Show the diff, then commit docs-only

```
git status --short -- docs/wiki
git add -N -- docs/wiki && git diff -- docs/wiki
```

After the user confirms: `git add -- docs/wiki` and `git commit -m "docs(wiki): sync with billing change"`.

## 6. Confirm

```
vibe wikify check
```

It exits 0: nothing is `changed` or `missing`. In CI use `vibe wikify check --ci`; to gate pushes
locally use `vibe wikify install-hook`.
