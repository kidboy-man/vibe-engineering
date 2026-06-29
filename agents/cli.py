"""Command-line interface for Vibe Engineering kits."""

from __future__ import annotations

import argparse
import subprocess
import sys
from typing import Mapping

from agents.kit_registry import KITS, KitSpec

GIT_SOURCE_URL = "git+https://github.com/kidboy-man/vibe-engineering.git"
PYPI_PACKAGE = "vibe-engineering"


def _is_pipx() -> bool:
    return ".local/pipx/venvs" in sys.executable or "/pipx/venvs/" in sys.executable


def _run(cmd: list[str]) -> int:
    print(f"Upgrading: {' '.join(cmd)}")
    return subprocess.run(cmd, check=False).returncode


def cmd_upgrade(_args: argparse.Namespace) -> int:
    if _is_pipx():
        return _run(["pipx", "install", "--force", GIT_SOURCE_URL])
    return _run([sys.executable, "-m", "pip", "install", "--upgrade", PYPI_PACKAGE])


def build_parser(kit_specs: Mapping[str, KitSpec] = KITS) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vibe",
        description="Install and manage portable engineering kits.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("upgrade", help="Self-upgrade the vibe CLI to the latest version")

    kits = sub.add_parser("kits", help="List and manage kits")
    kits_sub = kits.add_subparsers(dest="kits_command", required=True)

    kits_sub.add_parser("list", help="List available kits")

    for kit in kit_specs.values():
        kit_parser = kits_sub.add_parser(kit.name, help=kit.help)
        kit_sub = kit_parser.add_subparsers(dest=f"{kit.name}_command", required=True)

        install_parser = kit_sub.add_parser("install", help=f"Install or update the {kit.name} kit")
        install_parser.add_argument("--home", default=None, help="Target config base directory (default: $XDG_CONFIG_HOME or current user's home)")
        install_parser.add_argument("--dry-run", action="store_true", help="Show changes without writing files")
        install_parser.add_argument("--yes", "-y", action="store_true", help="Apply without interactive confirmation")
        install_parser.add_argument("--no-settings", action="store_true", help="Do not merge the safe settings fragment")
        install_parser.add_argument("--no-setup-deps", action="store_true", help="Do not auto-install qmd or other dependencies")

        diff_parser = kit_sub.add_parser("diff", help="Show file-level differences for managed files")
        diff_parser.add_argument("--home", default=None, help="Target config base directory (default: $XDG_CONFIG_HOME or current user's home)")

        doctor_parser = kit_sub.add_parser("doctor", help=f"Check {kit.name} kit installation status")
        doctor_parser.add_argument("--home", default=None, help="Target config base directory (default: $XDG_CONFIG_HOME or current user's home)")

        uninstall_parser = kit_sub.add_parser("uninstall", help="Remove files managed by this kit")
        uninstall_parser.add_argument("--home", default=None, help="Target config base directory (default: $XDG_CONFIG_HOME or current user's home)")
        uninstall_parser.add_argument("--dry-run", action="store_true", help="Show changes without writing files")
        uninstall_parser.add_argument("--yes", "-y", action="store_true", help="Apply without interactive confirmation")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "upgrade":
        return cmd_upgrade(args)

    if args.command == "kits" and args.kits_command == "list":
        for name in KITS:
            print(name)
        return 0

    if args.command == "kits":
        kit = KITS.get(args.kits_command)
        if kit is None:
            parser.error("unsupported kit")
            return 2
        sub_command_attr = f"{kit.name}_command"
        sub_command = getattr(args, sub_command_attr, None)
        if sub_command == "install":
            return kit.install(home=args.home, dry_run=args.dry_run, yes=args.yes, merge_settings=not args.no_settings, setup_deps=not args.no_setup_deps)
        if sub_command == "diff":
            return kit.diff(home=args.home)
        if sub_command == "doctor":
            return kit.doctor(home=args.home)
        if sub_command == "uninstall":
            return kit.uninstall(home=args.home, dry_run=args.dry_run, yes=args.yes)

    parser.error("unsupported command")
    return 2


if __name__ == "__main__":
    sys.exit(main())
