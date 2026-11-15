# Security Policy

vibe-kits installs files into your AI tool's config directories, so we treat
installer safety as a security matter. Examples: an install that overwrites
user data, copies a secret, or touches the network without consent.

## Supported versions

Only the [latest release](https://github.com/kidboy-man/vibe-engineering/releases/latest)
receives security fixes. Upgrade with `vibe upgrade`.

## Reporting a vulnerability

Please **do not open a public issue** for a security problem.

Report it privately through GitHub:
[Report a vulnerability](https://github.com/kidboy-man/vibe-engineering/security/advisories/new).

Include what you can of:

- the `vibe --version` output and the kit involved,
- steps to reproduce, ideally with `--dry-run` output,
- what you expected and what happened.

This is a volunteer-maintained project, so response times are best effort. We
will acknowledge the report, tell you whether we consider it in scope, and
credit you in the fix unless you prefer otherwise.

## Scope notes

- The `guardrails` kit hooks are heuristics. Obfuscated commands can get past
  them, and that alone is not a vulnerability. A bypass of a documented, plain
  pattern is a bug worth reporting.
- Reports about the safety contract in
  [docs/kits/safety-model.md](docs/kits/safety-model.md) (secrets, overwrites,
  uninstall ownership, network use) are in scope.
