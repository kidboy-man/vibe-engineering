"""Command-line interface for Vibe Engineering kits."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from importlib import metadata
from typing import Mapping

from agents.kit_registry import KITS, KitSpec
from agents.wikify import commands as wikify_commands

PYPI_PACKAGE = "vibe-kits"


def _is_pipx() -> bool:
    return "pipx/venvs" in sys.executable


def _has_pip() -> bool:
    return subprocess.run(
        [sys.executable, "-m", "pip", "--version"],
        capture_output=True,
    ).returncode == 0


def _run(cmd: list[str]) -> int:
    print(f"Upgrading: {' '.join(cmd)}")
    return subprocess.run(cmd, check=False).returncode


def _installed_version() -> str | None:
    try:
        return metadata.version(PYPI_PACKAGE)
    except metadata.PackageNotFoundError:
        return None


def cmd_upgrade(_args: argparse.Namespace) -> int:
    # pipx+uv venvs have no pip — fall back to pipx which manages the venv itself
    use_pipx = _is_pipx() and not _has_pip()

    if use_pipx:
        if shutil.which("pipx") is None:
            print(
                "pipx not found on PATH — cannot self-upgrade this way. "
                f"Reinstall manually with: pipx install --force {PYPI_PACKAGE}"
            )
            return 1
        cmd = ["pipx", "upgrade", PYPI_PACKAGE]
    else:
        cmd = [sys.executable, "-m", "pip", "install", "--upgrade", PYPI_PACKAGE]

    before = _installed_version()
    rc = _run(cmd)
    if rc != 0:
        recovery = (
            f"pipx install --force {PYPI_PACKAGE}"
            if use_pipx
            else f"pip install --force-reinstall {PYPI_PACKAGE}"
        )
        print(f"Upgrade failed (exit {rc}). To recover, try: {recovery}")
        return rc

    after = _installed_version()
    if before is not None and before == after:
        print(f"Already on the latest installed version ({after}).")
    elif after is not None:
        print(f"Upgraded to {after}.")
    return rc


HOME_HELP = "Target config base directory (default: $XDG_CONFIG_HOME or current user's home)"


def _add_home(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--home", default=None, help=HOME_HELP)


def _add_apply_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing files")
    parser.add_argument("--yes", "-y", action="store_true", help="Apply without interactive confirmation")


def build_parser(kit_specs: Mapping[str, KitSpec] = KITS) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vibe",
        description="Install and manage portable engineering kits.",
    )
    parser.add_argument(
        "--version",
        "-V",
        action="version",
        version=f"vibe {_installed_version() or 'unknown'}",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("upgrade", help="Self-upgrade the vibe CLI to the latest version")

    wik = sub.add_parser("wikify", help="Maintain a verified repo wiki in docs/wiki")
    wik_sub = wik.add_subparsers(dest="wikify_command", required=True)
    wik_sub.add_parser("init", help="Scaffold docs/wiki (never overwrites files)")
    plan_parser = wik_sub.add_parser("plan", help="Show which wiki pages need updating")
    plan_parser.add_argument("--full", action="store_true", help="Plan a full rebuild")
    plan_parser.add_argument("--json", action="store_true", help="Print the plan as JSON")
    wik_sub.add_parser("verify", help="Check citations and scan the wiki for secrets")
    wik_sub.add_parser("mark", help="Verify, then record the covered commit")

    kits = sub.add_parser("kits", help="List and manage kits")
    kits_sub = kits.add_subparsers(dest="kits_command", required=True)

    kits_sub.add_parser("list", help="List available kits")

    for kit in kit_specs.values():
        kit_parser = kits_sub.add_parser(kit.name, help=kit.help)
        kit_sub = kit_parser.add_subparsers(dest=f"{kit.name}_command", required=True)

        install_parser = kit_sub.add_parser("install", help=f"Install or update the {kit.name} kit")
        _add_home(install_parser)
        _add_apply_flags(install_parser)
        for option in kit.options():
            install_parser.add_argument(option.flag, action="store_true", help=option.help)

        diff_parser = kit_sub.add_parser("diff", help="Show file-level differences for managed files")
        _add_home(diff_parser)

        doctor_parser = kit_sub.add_parser("doctor", help=f"Check {kit.name} kit installation status")
        _add_home(doctor_parser)

        uninstall_parser = kit_sub.add_parser("uninstall", help="Remove files managed by this kit")
        _add_home(uninstall_parser)
        _add_apply_flags(uninstall_parser)

        if kit.enable_hook is not None:
            enable_hook_parser = kit_sub.add_parser("enable-hook", help="Enable proactive context wiring (SessionStart hook + persona section) for Claude Code, Codex CLI, Cursor, and OpenCode")
            _add_home(enable_hook_parser)
            _add_apply_flags(enable_hook_parser)

    return parser


def main(argv: list[str] | None = None, kit_specs: Mapping[str, KitSpec] | None = None) -> int:
    kit_specs = KITS if kit_specs is None else kit_specs
    parser = build_parser(kit_specs)
    args = parser.parse_args(argv)

    if args.command == "upgrade":
        return cmd_upgrade(args)

    if args.command == "wikify":
        return wikify_commands.cmd_wikify(args)

    if args.command == "kits" and args.kits_command == "list":
        for name in kit_specs:
            print(name)
        return 0

    if args.command == "kits":
        kit = kit_specs.get(args.kits_command)
        if kit is None:
            parser.error("unsupported kit")
            return 2
        sub_command = getattr(args, f"{kit.name}_command", None)
        if sub_command == "install":
            kwargs = {"home": args.home, "dry_run": args.dry_run, "yes": args.yes}
            kwargs.update({option.kwarg: option.value_from(args) for option in kit.options()})
            return kit.install(**kwargs)
        if sub_command == "diff":
            return kit.diff(home=args.home)
        if sub_command == "doctor":
            return kit.doctor(home=args.home)
        if sub_command == "uninstall":
            return kit.uninstall(home=args.home, dry_run=args.dry_run, yes=args.yes)
        if sub_command == "enable-hook" and kit.enable_hook is not None:
            return kit.enable_hook(home=args.home, dry_run=args.dry_run, yes=args.yes)

    parser.error("unsupported command")
    return 2


if __name__ == "__main__":
    sys.exit(main())
