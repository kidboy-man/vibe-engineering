# Walkthrough: adopting the nested-docs fixture

The fixture repo is built by `python3 -m tests.wikify_adopt_helpers <dir>` (docs/trd, docs/adr, an
image, a Makefile that reads `docs/build.md`, a secret-looking note, and a root README read by
`pyproject.toml`). `tests/test_wikify_adopt.py::WalkthroughTests` runs these steps and checks that every
`expect:` line below appears in the combined command output, so this file cannot drift from the CLI.

The loop an agent follows with the `wikify-adopt` skill:

1. Dry run, read the moves and skips.

       vibe wikify adopt
       expect: move docs/adr/0001.md -> docs/wiki/decisions/0001.md [adr]
       expect: move docs/trd/auth/tokens.md -> docs/wiki/specs/trd/auth/tokens.md [spec]
       expect: skip docs/build.md: build-coupled
       expect: skip docs/secret-notes.md: secret-hit
       expect: skip README.md: unmapped
       expect: dry run: no files written

2. Machine-readable plan for the agent (`unclassified` is the list the agent maps next).

       vibe wikify adopt --report

3. The agent proposes `docs/wiki/.wikifymap`, the user approves, then apply. Moves are staged renames;
   bodies are wrapped verbatim; nothing is committed.

       vibe wikify adopt --apply --rewrite-refs
       expect: moved 3 doc(s). Next, in order:
       expect: 1. git commit
       expect: 2. vibe wikify verify
       expect: 3. git add -- docs/wiki

4. Commit 1 (staged renames only), verify, mark, show the user the diff, then commit 2 (docs-only).

       git commit -m "docs(wiki): move docs into the wiki"
       vibe wikify verify
       expect: ok: wiki verified
       vibe wikify mark
       expect: marked at
       git add -- docs/wiki && git commit -m "docs(wiki): adopt moved docs"

5. A second run changes nothing.

       vibe wikify adopt --apply
       expect: nothing to move
