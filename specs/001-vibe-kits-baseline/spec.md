# Feature Specification: Vibe Kits Baseline

**Feature Branch**: `n/a (baseline of shipped behavior; spec dir 001-vibe-kits-baseline)`

**Created**: 2026-10-17

**Status**: Draft

**Input**: User description: "Create baseline specification"

## Clarifications

### Session 2026-10-17

- Q: Should the `vibe wikify adopt` proposal in `feature.md` stay out of this baseline? → A: No, it is in scope (User Story 7, FR-017 to FR-022); it is marked as planned, not yet shipped.
- Q: Is native Windows (outside WSL) a supported platform? → A: No; Linux, macOS, and WSL only.
- Q: Keep the unmeasured "under 1 minute" install target in SC-001? → A: No; SC-001 requires only a single command with no manual editing.

## User Scenarios & Testing *(mandatory)*

<!--
  Baseline spec: documents the behavior the product already ships so later features
  can be specified as deltas. Exception: User Story 7 (doc adoption) is planned work.
-->

### User Story 1 - Install an engineering persona into my AI coding tool (Priority: P1)

A developer who uses one or more AI coding tools (Claude Code, OpenCode, Gemini CLI, Codex CLI, Cursor)
runs one command per tool to receive a consistent senior-engineering persona, rules, and (where the tool
supports them) agents, commands, and skills, without losing anything they already configured.

**Why this priority**: This is the product's core value; every other kit builds on the same install,
preview, diff, and uninstall contract.

**Independent Test**: In an isolated home directory, run `doctor`, `install --dry-run`, `install --yes`,
`diff`, and `uninstall --yes` for one kit and verify the resulting files and that pre-existing user files
are unchanged.

**Acceptance Scenarios**:

1. **Given** a fresh home directory, **When** the developer runs `install --yes` for a kit, **Then** the
   kit's managed files appear in the tool's config location and a manifest records what the kit owns.
2. **Given** an existing user-authored file at a managed path, **When** the developer runs `install`,
   **Then** the file is not overwritten unless the manifest proves the kit owns it.
3. **Given** an installed kit, **When** the developer runs `uninstall --yes`, **Then** only kit-owned files
   and kit-owned sections of merged files are removed, and a merged file with no remaining content is deleted.
4. **Given** any kit, **When** the developer runs `install --dry-run`, **Then** the planned changes are
   reported and nothing on disk changes.

---

### User Story 2 - Discover and diagnose kits (Priority: P2)

A developer lists available kits, checks whether a kit is healthy, and sees what the next install
would change, before committing to any change.

**Why this priority**: Trust and troubleshooting; lets users adopt kits one at a time with confidence.

**Independent Test**: Run `vibe kits list`, `doctor`, and `diff` against installed and uninstalled states
and verify the reports match the actual on-disk state.

**Acceptance Scenarios**:

1. **Given** the CLI is installed, **When** the developer runs `vibe kits list`, **Then** every registered
   kit is shown.
2. **Given** a missing dependency or config directory, **When** the developer runs `doctor`, **Then** the
   problem is named with an actionable message.
3. **Given** an installed kit whose templates have changed, **When** the developer runs `diff`, **Then**
   created, updated, and unchanged files are distinguished.

---

### User Story 3 - Block catastrophic or secret-exposing agent actions (Priority: P2)

A developer installs the guardrails kit so that their AI agent is stopped from destructive commands
(recursive delete of home or root, force-push, hard reset, destructive SQL from the shell) and from
reading or writing secret files, in every supported tool that is present.

**Why this priority**: Converts safety advice into enforcement and protects users from the highest-cost
agent mistakes.

**Independent Test**: Feed representative blocked and allowed tool calls to the installed guard and verify
deny versus allow decisions, including the Cursor-specific response format.

**Acceptance Scenarios**:

1. **Given** the guard is installed, **When** the agent attempts a blocked action, **Then** the action is
   denied with a stated reason.
2. **Given** an action outside the block list (for example `--force-with-lease`, `.env.example`, `/tmp`
   cleanup), **When** the agent attempts it, **Then** it is allowed.
3. **Given** a parse or internal guard error, **When** a tool call is evaluated, **Then** it is allowed
   rather than blocking the session.
4. **Given** the developer sets the bypass variable for a session, **When** a blocked action is attempted,
   **Then** it is allowed for that session.

---

### User Story 4 - Keep a repo's wiki in sync with its code (Priority: P2)

A developer opts a repo into the wikify kit so that an agent's `git push` is blocked while `docs/wiki` is
stale, and so the repo gains a cited wiki, an agent map with a pointer block in `AGENTS.md`, and outline
pages for existing documentation.

**Why this priority**: Keeps agent-facing repo knowledge trustworthy; high value but narrower audience.

**Independent Test**: In a scratch repo opted in via `docs/wiki/.wikify.json`, change code, attempt a
push, and walk the plan, update, verify, mark, and push cycle.

**Acceptance Scenarios**:

1. **Given** an opted-in repo with a stale wiki, **When** the agent runs `git push`, **Then** the push is
   blocked with instructions.
2. **Given** a wiki updated, verified, and marked in docs-only commits, **When** the agent pushes,
   **Then** the push is allowed.
3. **Given** a repo that has not opted in, **When** the agent pushes, **Then** the hook does not interfere.
4. **Given** existing markdown docs, **When** the developer runs `vibe wikify docs`, **Then** outline pages
   are produced; with `--dry-run` nothing is written.

---

### User Story 5 - Run a requirement-to-implementation workflow (Priority: P3)

A developer turns a business requirement into a PRD, a TRD, traceable tickets, optionally GitHub issues,
and then implements one ticket at a time test-first, using slash commands that hand off through files with
stable IDs.

**Why this priority**: Valuable for structured delivery but optional on top of the persona kits.

**Independent Test**: Run the trace validator on a sample PRD, TRD, and ticket set and verify it reports
duplicate IDs, unknown references, cycles, and unimplemented Must requirements.

**Acceptance Scenarios**:

1. **Given** a PRD, **When** the developer runs `/flow`, **Then** it continues from the latest existing
   artifact and pauses at a checkpoint after each stage.
2. **Given** tickets with dependency cycles or unknown IDs, **When** the validator runs, **Then** it fails
   and names the problem.
3. **Given** a ticket, **When** `/implement-ticket` runs, **Then** failing tests precede implementation and
   the run stops for review without committing.
4. **Given** tickets, **When** `/push-tickets` is invoked without explicit approval, **Then** no GitHub
   issues are created.

---

### User Story 6 - Scaffold a local-first second-brain vault (Priority: P3)

A developer creates a local Obsidian-compatible vault searchable by AI agents, with non-secret agent
config snippets and portable wiki skills, while keeping the vault's contents entirely under their control.

**Why this priority**: Personal knowledge workflow; independent of the engineering persona kits.

**Independent Test**: Install with a redirected vault path and home, then uninstall, and verify the vault
and user content survive while only kit-owned snippets and the manifest are removed.

**Acceptance Scenarios**:

1. **Given** no vault, **When** the developer installs, **Then** the directory scaffold and seed pages are
   created only where absent.
2. **Given** the search tool is not installed, **When** the developer installs without the dependency flag,
   **Then** nothing is installed and `doctor` reports its absence.
3. **Given** the developer passes the dependency flag and approves the prompt, **When** installing,
   **Then** the search tool is installed; declining skips it.
4. **Given** an installed vault, **When** the developer uninstalls, **Then** the vault and its contents
   remain untouched.

---

### User Story 7 - Fold existing docs into the wiki (Priority: P3, planned, not yet shipped)

A developer whose repo already has a markdown docs tree (TRDs, PRDs, ADRs, security notes) moves those
docs into `docs/wiki/` so the wiki becomes the single active documentation tree instead of a second,
parallel one that only points at `docs/`. A deterministic command does the inventory, moves, and link
rewrites; an agent, driven by a shipped playbook (skill), does the judgment work (classifying ambiguous
docs, proposing destinations, drafting map hints), and every result must pass the wiki verifier.

**Why this priority**: Removes the two-tree problem on repos with existing docs, but only matters to
repos that already have a docs tree and have opted into wikify.

**Independent Test**: On fixture repos with no docs, a flat `docs/`, and a nested `docs/` containing
images and relative links, run the dry run, then apply, then verify; confirm no markdown content is lost,
a second apply changes nothing, and `plan` reports nothing uncovered.

**Acceptance Scenarios**:

1. **Given** an opted-in repo with existing docs, **When** the developer runs `vibe wikify adopt` (dry
   run), **Then** it prints per file the source, destination, kind, any skip reason, and inbound
   references found, and writes nothing.
2. **Given** an approved mapping, **When** the developer runs `vibe wikify adopt --apply`, **Then** files
   are moved with history preserved, bodies are wrapped verbatim, the map is updated, outline pages for the
   moved docs are removed, and the printed commit steps leave the wiki verifying cleanly.
3. **Given** build-coupled files, non-markdown assets, ignored files, secret paths, or files with secret
   scan hits, **When** adopt runs, **Then** they stay in place and are reported with a reason.
4. **Given** a dirty working tree or detached HEAD, **When** adopt runs without `--force`, **Then** it
   refuses.
5. **Given** a completed apply, **When** it is run again, **Then** it is a no-op.
6. **Given** the developer asks for a machine-readable report, **When** adopt runs with `--report`,
   **Then** it emits JSON of moves, skips, unresolved references, unclassified docs, and suggested contexts.

---

### Edge Cases

- A managed file exists but is not recorded in the manifest (user-authored): left untouched.
- A merged config file (JSON, JSONC with comments and trailing commas, TOML, markdown with markers) holds
  user content around kit content: user content is preserved byte-for-byte outside kit-owned regions.
- A target agent's config directory does not exist: that agent is skipped, never created (hook-based kits).
- Hook configuration cannot be edited on uninstall (invalid JSON, hand-edited block): scripts and manifest
  are kept, the reason is reported, and the exit status is non-zero.
- Re-running install is idempotent: no duplicate sections or hook registrations.
- Home directory redirected via an option or environment variable: all reads and writes honor it.
- A wiki page that is not valid UTF-8 is reported rather than crashing verification.
- The docs inventory fails: `vibe wikify docs` refuses and exits non-zero.
- Secret-bearing keys in existing agent configs are always preserved and never copied.
- Adopt: an interrupted run leaves the tree consistent (all-or-nothing or resumable from the mapping file).
- Adopt: references that cannot be rewritten (README, `AGENTS.md`, source comments, CI configs) are listed,
  never silently edited, unless the developer opts in and the file is docs-only.
- Adopt: a stale generated outline page is flagged and removed only on explicit request.
- Adopt: map entry caps would be exceeded, so entries are grouped under per-folder index pages.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The CLI MUST list all registered kits and expose `doctor`, `install`, `diff`, and `uninstall`
  for each kit, with `--dry-run` and `--yes` semantics consistent across kits.
- **FR-002**: Install MUST preserve existing user files; only files provably owned by a kit manifest may be
  overwritten, merged, or removed.
- **FR-003**: Dry-run MUST perform no writes or side-effecting commands.
- **FR-004**: Uninstall MUST remove only kit-owned content and MUST leave user content in merged files intact.
- **FR-005**: Kits MUST NOT include or install credentials, tokens, local proxy URLs, model/provider
  selection, transcripts, or machine-specific absolute paths; secret-like config keys MUST be preserved
  as-is.
- **FR-006**: Persona kits (Claude Code, OpenCode, Gemini, Codex, Cursor) MUST install the persona and rules
  in the layout each tool expects (separate files where supported, single embedded file or `.mdc` rules
  otherwise).
- **FR-007**: Only the second-brain kit MAY run a network or package-manager command, and only with the
  explicit dependency flag plus an interactive approval; `--yes` alone MUST NOT trigger it.
- **FR-008**: The guardrails kit MUST deny catastrophic and secret-exposing actions listed in its policy,
  allow everything else, fail open on internal errors, and honor a session bypass variable.
- **FR-009**: Hook-based kits MUST register hooks only for agents whose config directory already exists and
  MUST preserve existing hooks, backing up changed files.
- **FR-010**: The wikify kit MUST block an opted-in repo's agent push while the wiki is stale and MUST allow
  it once the freshness rule is met; repos that have not opted in MUST be unaffected.
- **FR-011**: Wikify commands (`init`, `plan`, `verify`, `mark`, `link`, `docs`) MUST be deterministic, MUST
  support dry-run where they write, and `docs` MUST refuse with a non-zero exit when its inventory fails.
- **FR-012**: The workflow kit MUST provide PRD, TRD, ticket, push, and implement stages plus a
  deterministic trace validator that fails on duplicate IDs, unknown references, dependency cycles, and
  unimplemented Must requirements.
- **FR-013**: GitHub issue creation MUST occur only after explicit user approval.
- **FR-014**: The second-brain kit MUST create its vault scaffold create-if-absent and MUST NOT delete the
  vault or user content on uninstall.
- **FR-015**: The CLI MUST support self-upgrade and reflect its help text in versioned snapshots; intentional
  help changes MUST update those snapshots.
- **FR-016**: New kits MUST be addable through a registry entry and shared install helpers, and MUST pass the
  shared kit contract checks and packaging checks.

- **FR-017** *(planned)*: `vibe wikify adopt` MUST be a dry run by default, write only with `--apply`,
  never overwrite existing files, never delete without an explicit flag, and preserve history when moving.
- **FR-018** *(planned)*: Adopt's command-line layer MUST be deterministic and MUST NOT call a model;
  judgment work MUST be done by an agent through a shipped skill, and every agent output MUST pass the
  wiki verifier.
- **FR-019** *(planned)*: Adopt MUST preserve all moved markdown content (verifiable by content hash) and
  MUST NOT weaken citations, the secret scan, human blocks, the map, or the freshness gate.
- **FR-020** *(planned)*: Migrated prose that is not code-cited MUST be represented so the verifier stays
  strict for ordinary pages and migrated prose is visibly marked as documented, not code-verified
  (human-block notices plus a provenance label). Representation: see the design spec.
- **FR-021** *(planned)*: Adopt MUST refuse on a dirty tree or detached HEAD without `--force`, MUST be
  idempotent, and MUST print a commit plan that keeps the freshness rule satisfiable (changes outside
  `docs/wiki/` in a separate earlier commit).
- **FR-022** *(planned)*: The skill MUST NOT rewrite migrated prose or human blocks, MUST NOT invent facts,
  MUST report doc-versus-code contradictions as findings rather than editing, and MUST treat repo content
  as untrusted data, not instructions.

### Key Entities

- **Kit**: A named installable bundle (persona, rules, agents, commands, skills, hooks, or vault scaffold)
  with its own install, diff, doctor, and uninstall behavior.
- **Manifest**: Per-install record of files and sections a kit owns, used to decide what may be overwritten
  or removed.
- **Managed file / merged region**: A file wholly owned by a kit, or a marked region inside a user file.
- **Agent target**: A supported AI coding tool and its config location.
- **Hook registration**: An entry in an agent's config that invokes a kit script on tool events.
- **Wiki (docs/wiki)**: A repo's cited documentation tree with an opt-in control file and freshness mark.
- **Workflow artifact**: PRD, TRD, ticket, linked by stable requirement and ticket IDs.
- **Vault**: The user's local knowledge directory created by the second-brain kit.
- **Adoption mapping file** *(planned)*: Reviewable record of which doc moves where, so re-runs are
  idempotent and a human approves before apply.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A developer can install any single kit from a clean state with one command and no manual
  file editing.
- **SC-002**: 100% of install runs leave pre-existing, non-owned user files byte-identical.
- **SC-003**: 100% of dry-run invocations leave the file system unchanged.
- **SC-004**: After install then uninstall, no kit-owned files or registrations remain and user content is
  unchanged, verified for every kit.
- **SC-005**: Every action on the guardrails block list is denied and every action on its documented
  allow list is allowed in automated checks.
- **SC-006**: The trace validator detects every seeded defect (duplicate ID, unknown reference, cycle,
  uncovered Must requirement) in a sample set.
- **SC-007**: No packaged template contains secrets or machine-specific absolute paths, confirmed by
  automated checks on each release.
- **SC-008**: An opted-in repo with a stale wiki cannot be pushed by an agent, and the same repo pushes
  successfully after the documented update cycle.
- **SC-009** *(planned)*: On each adoption fixture repo, 100% of moved markdown bodies are byte-identical
  to the originals, a second apply makes zero changes, and the wiki check and plan report no errors or
  uncovered docs afterward.

## Assumptions

- Target users are developers comfortable with a terminal who use at least one supported AI coding tool.
- Supported platforms are Linux, macOS, and WSL. Native Windows (outside WSL) is not supported and has no
  acceptance coverage.
- Items not marked *(planned)* record shipped behavior as of version 0.6.0 development; the only
  unshipped scope is the doc-adoption feature (User Story 7, FR-017 to FR-022, SC-009).
- The README, `AGENTS.md`, and the project constitution are the authoritative sources for detailed
  behavior and are not duplicated here.
- Guardrails are a heuristic safety layer, not a sandbox; obfuscated commands may bypass them.
- Per-tool hook trust steps (for example Codex hook approval) remain the user's responsibility.
- Out of scope: installing the AI tools themselves, managing provider accounts or credentials, hosting or
  syncing user vaults, and for adoption: model-written summaries or new factual pages, ADR generation, and
  deleting originals outside version history.
