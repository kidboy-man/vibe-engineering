# Enforcing the wiki outside the agent hook

The agent hook only guards an agent's `git push`. `vibe wikify check --ci` gives the same verdict to
a plain terminal, an IDE or CI. It is read-only and deterministic: no model, no network.

What fails the check: a citation whose cited lines were `changed`, or whose file or symbol is
`missing`. What only warns: `moved` citations (heal them with `vibe wikify reanchor --apply`),
`uncovered` code areas, edited imported pages, a map near its caps. `--ci` judges the **committed**
wiki at HEAD, so a dirty working tree cannot change the result. Any internal error is a failure
(fail closed).

## Local pre-push hook

```
vibe wikify install-hook            # dry run: prints the target and the script
vibe wikify install-hook --apply    # writes .git/hooks/pre-push (mode 0755)
```

The hook runs `vibe wikify check --ci` and blocks the push when it fails or when `vibe` is not on
`PATH`. It never overwrites an existing `pre-push` hook, and it refuses when `core.hooksPath` is
set (husky and similar tools): add `vibe wikify check --ci` to that tool's pre-push step instead.
It judges the checked-out `HEAD`, not the refs being pushed (`git push origin other-branch` is
checked against the current checkout); pushes that only delete remote refs are skipped.
`VIBE_WIKIFY=off git push` skips it for one push, and a machine without `vibe` on `PATH` is blocked
rather than waved through (the gate fails closed; install `vibe` or use `--no-verify`). Delete the file to remove the gate. Like every client-side hook it can be skipped with
`git push --no-verify`; use CI for a gate that cannot be skipped.

## GitHub Actions

```yaml
name: wiki
on: [pull_request]
jobs:
  wiki:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # commit attribution needs history; the verdict does not
      - run: pipx install vibe-kits
      - run: vibe wikify check --ci
```

Run `vibe wikify verify` in the same job if you also want the full citation and secret-scan
gate; `check` is the drift gate. A shallow clone still gives a correct verdict but the output
then says commits are not attributed.

## Commenting the summary on a pull request (design)

The CLI never talks to the network. A CI step can do it with the JSON output:

```yaml
      - id: wiki
        run: |
          vibe wikify check --ci --json > wiki-check.json || true
          echo "ok=$(python3 -c 'import json;print(json.load(open("wiki-check.json"))["ok"])')" >> "$GITHUB_OUTPUT"
      - if: steps.wiki.outputs.ok == 'False'
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          python3 - <<'PY' > body.md
          import json
          d = json.load(open("wiki-check.json"))
          print("**Wiki drift** (`vibe wikify check`)")
          for f in d["drift"]:
              print(f"- {f['category']}: `{f['page']}:{f['line']}` cites `{f['path']}:{f['start']}-{f['end']}`")
          PY
          gh pr comment "${{ github.event.pull_request.number }}" --body-file body.md
      - run: python3 -c 'import json,sys;sys.exit(0 if json.load(open("wiki-check.json"))["ok"] else 1)'
```

Page names and paths in the JSON come from the repository: treat them as untrusted text and keep
them inside code spans, as above.

## After a squash merge

A squash merge folds code and `.wikify.json` into one commit. The commit-order rule used by the
agent hook reads that as stale, but `check` judges the tree: if every citation still resolves and
nothing `changed` or went `missing`, it passes. Run `vibe wikify mark` and make one docs-only
commit to re-baseline.
