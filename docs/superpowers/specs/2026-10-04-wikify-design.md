# Wikify kit for vibe-kits — design

## Context
Many repos have no docs; the code is the doc. `wikify` generates a **valid** wiki from code (no guessing) and keeps it current. When the agent is about to `git push`, vibe-engineering blocks the push, recaps the change, updates the wiki, confirms with the user, commits, and lets the push proceed. Builds on the guardrails kit (hook wiring, `git push` parsing).

## Decisions (agreed with the user)
| # | Topic | Decision |
|---|---|---|
| 1 | Validity | LLM prose where every claim cites `file:line` or symbol. A deterministic verifier rejects claims whose citation does not resolve or lacks the symbol. Failing claims are never published. |
| 2 | Location | In repo: `docs/wiki/`, committed and PR-reviewed. |
| 3 | Trigger | Agent PreToolUse hook on `git push`, reusing `git push` parsing in `agents/kits/guardrails/templates/guardrails/hooks/vibe-guardrails/guard.py`. Pushes typed in a plain terminal are not covered (stated limitation). |
| 4 | Push flow | First push is blocked with a reason. Agent recaps `git diff <last_covered>..HEAD` (see Bootstrap; not `@{u}`), updates wiki, shows the user, user confirms, separate `docs(wiki)` commit, push retried. No amend, no history rewrite. |
| 5 | Engine | Standalone stdlib extractor, diff-driven. Optional codegraph use if present, never required. Pages for deleted code are flagged, not auto-deleted. |
| 6 | Targets | Claude Code, Codex, Cursor. |

## Wiki structure (arc42-shaped)
```
docs/wiki/
  index.md
  domain/                 # business knowledge, per bounded context
    glossary.md           # terms cited to type/enum/const definitions
    <context>/            # derived from top-level packages
      lifecycle.md        # states/transitions cited to enum + transition funcs
      rules.md            # invariants cited to validation/guard code
  technical/              # cross-cutting concerns, linked FROM domain pages
    idempotency.md  concurrency.md  transactions.md  errors.md ...
  architecture/           # module map, entry points, dependencies
  .wikify.json            # page -> cited files index + last-covered commit
```
arc42 puts domain-structured content in building-block/runtime views and system-wide patterns in cross-cutting concepts (https://arc42.org/method/). Diátaxis is not used for folders; as a limit, code alone supports only reference and explanation, so **v1 generates no tutorials or how-to guides**.

### Rules that protect "no guessing"
1. **Business "why" is unverifiable from code.** Domain pages state only what code shows. Rationale goes in human-owned blocks `<!-- wikify:human -->...<!-- /wikify:human -->`, never rewritten by wikify, skipped by the verifier. No generated `decisions/` or ADRs.
2. **Classification:** a concern found in two or more bounded contexts, or living in shared/infrastructure code, goes in `technical/`; otherwise in that context's domain page. Domain pages link to technical pages, never re-explain.
3. **Evidence-only pages:** `technical/` has a seed list of concerns; a page exists only if cited code backs it. No placeholders.
4. **Citation index is the diff map:** `.wikify.json` maps page to cited files. Inverting it turns a changed file into pages to refresh.

## Components
- **Citation syntax:** inline `(src: path/to/file.py:12-30 `Symbol`)`. Symbol is optional for line-only citations; every factual sentence needs one.
- **Verifier** (`wikify verify`, pure Python, no network, no LLM): for each citation checks file exists at HEAD, range is in bounds, and the symbol string appears inside the range. Exit non-zero listing failing claims. **Ceiling:** it proves the cited code exists and mentions the symbol, not that the sentence interprets it correctly; documented in kit output.
- **Extractor** (`wikify plan [--full]`): reads only tracked files at HEAD (`git ls-files`, `git show HEAD:<path>`), honoring `.wikifyignore`. From `git diff <last_covered>..HEAD` plus the citation index, emits the pages to refresh, new files with no page, and pages whose cited files were deleted (flagged only). Python files get symbol/enum/def extraction via `ast`; other languages get file/line-range citations checked by text match.
- **Push hook** (`hooks/vibe-wikify/wikify_guard.py`): never raises; unknown payload shape allows. Blocks `git push` with exit 2 + stderr instructing the agent to run the flow above. Stderr text is static (no branch names, subjects or filenames). Allows when the wiki is fresh (see Bootstrap), when `docs/wiki/` does not exist (repo not wikified; the hook never creates it), or when `VIBE_WIKIFY=off`. Fail-open: this is a convenience gate, **not a security control**.
- **Kit installer:** `agents/kits/wikify/` registered in `kit_registry.py`, reusing the generalized hook merge helpers from guardrails; verbs `install|diff|doctor|uninstall`, `--home`, `--dry-run`, `--yes`. Agents installed only if `~/.claude`, `~/.codex` or `~/.cursor` exists. Manifest owns only its scripts and hook entries.
- **Repo CLI verbs:** `vibe wikify init|plan|verify` operate on the cwd repo (per-repo, unlike home-level kit install). `init` scaffolds `docs/wiki/` and `.wikify.json`. Overlap with the `vibe init` backlog item is accepted; wikify owns only the wiki scaffold.
- **Skill/instructions** shipped with the kit tell the agent how to write cited prose per page type and to stop and ask the user before committing.

## Bootstrap / base selection (fresh repo and first run)
- "From scratch" means `vibe wikify init` works on a new or empty repo and the wiki grows with the code. Wikify never drafts docs before code exists (nothing to cite).
- `init` on a repo with no commits writes `index.md` and `.wikify.json` with `last_covered: null`; `rev-parse HEAD` is not required.
- **Base is `last_covered`, not `@{u}`** (`@{u}` fails on a new branch's first `git push -u`). If null, or not an ancestor of HEAD (after rebase), fall back to a full build.
- **Freshness:** fresh iff `git diff --name-only <last_covered>..HEAD` touches nothing outside `docs/wiki/**`. `.wikify.json` stores the **code commit covered**, never the docs commit (a commit cannot contain its own SHA, so "last_covered == HEAD" could never hold).
- `wikify plan --full` serves fresh repos and an established repo's first run; large repos batch by bounded context with a confirmation per batch.
- A fresh repo's wiki is intentionally near-empty (index + architecture), because pages exist only with cited evidence (rule 3). This is correct, not a bug.

## Security and privacy
`docs/wiki/` is committed and pushed, so wikify is a **publishing channel** for anything sitting next to the code.
1. **Tracked files at HEAD only**; never the working tree. Skips untracked secrets, local config and build output; every citation exists on the remote.
2. **Secret paths are never read or cited.** Reuse `is_secret_path` / `SECRET_BASENAMES` (`guard.py`) and `agents/secret_policies.py`. `guard.py` is a standalone copied template: move the shared logic into `secret_policies.py` for the CLI, vendor a copy into the hook, and add a test that keeps them in sync. No third copy.
3. **Pre-commit scan of `docs/wiki/**`** (human blocks included) for token-shaped strings, private-key headers and high-entropy literals. Use `gitleaks` or `trufflehog` if on PATH (optional, like codegraph); otherwise a minimal built-in set that is documented as a floor, not complete. **A hit hard-blocks the commit** and shows the line. No silent redaction.
4. **Commit wiki paths only:** `git add -- docs/wiki`, never `-A` or `.`; stated in the skill text and hook message.
5. **No personal data:** no blame, author names, emails or commit messages. Citations are `path:line` only.
6. **Repo-relative paths only** in pages and `.wikify.json`; the verifier rejects absolute and `..` citation paths.
7. **Repo content is data, not instructions.** Docstrings, comments, existing pages and human blocks may carry injected instructions; the skill says so.
8. **Inert hook:** fixed-argv `git` calls, no `shell=True`, no network; `.wikify.json` is untrusted JSON; no command named in config is ever run.
9. **Opt-in per repo:** only `vibe wikify init` creates `docs/wiki/`. Contributing to someone else's repo never produces a codebase inventory in a PR.
10. **No network or telemetry in the kit.** The agent's model provider sees code during generation, as it already does.
11. **Confirmation gate shows** the wiki diff, the scan result, and the exact list of paths to be committed.

## Testing (TDD)
- Verifier: table-driven cases for resolving, out-of-range, missing file, renamed symbol, human block skipped.
- Extractor: temp git repos covering changed, added, deleted files and inverted-index lookups.
- Hook: pipe `git push` tool-call JSON per target; assert block, allow-when-fresh (docs-only diff since `last_covered`), allow-when-not-wikified, allow-on-malformed, `VIBE_WIKIFY=off`, static stderr.
- Bootstrap: `init` on an empty repo with no commits; null `last_covered` and non-ancestor `last_covered` trigger full build; first `git push -u` on a new branch.
- Security: untracked/secret-path files never read; scan hit blocks (built-in set and fake `gitleaks` on PATH); absolute and `..` citations rejected; only `docs/wiki` staged; secret-path logic in hook and `secret_policies.py` stays in sync.
- Installer: fake-home install/idempotent re-install/diff/doctor/uninstall per target, user hooks preserved, `--dry-run` writes nothing; update `test_manifest_contracts.py` and `tests/fixtures/cli_help/` snapshots.
- Run: `python3 -m unittest discover -s tests`.

## Risks
- Hook loops: the docs-only-diff freshness rule means the wiki commit itself never re-triggers the hook.
- Hook annoyance on every push: escape hatch env var and freshness skip.
- Codex requires a one-time `/hooks` trust review; Cursor payload shapes for push-time events must be verified against current docs before coding (guardrails kit recorded the same caveat). If a target lacks a blocking pre-shell event, ship warn-only there and say so in `doctor`.
- Verifier gives structural, not semantic, validity; wording must not claim more.

## Out of scope (v1)
Tutorials/how-to pages, generated ADRs, terminal-level git hook, auto-pruning stale pages, vault mirroring.
