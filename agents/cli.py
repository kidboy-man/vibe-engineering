"""Command-line interface for Vibe Engineering kits."""

from __future__ import annotations

import argparse
import sys

from agents.kits.claude_code.installer import (
    diff_kit,
    doctor,
    install,
    uninstall,
)


KIT_NAMES = ["claude-code"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vibe",
        description="Install and manage portable engineering kits.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    kits = sub.add_parser("kits", help="List and manage kits")
    kits_sub = kits.add_subparsers(dest="kits_command", required=True)

    kits_sub.add_parser("list", help="List available kits")

    claude = kits_sub.add_parser("claude-code", help="Manage the Claude Code kit")
    claude_sub = claude.add_subparsers(dest="claude_command", required=True)

    install_parser = claude_sub.add_parser("install", help="Install or update the Claude Code kit")
    install_parser.add_argument("--home", default=None, help="Target home directory (default: current user's home)")
    install_parser.add_argument("--dry-run", action="store_true", help="Show changes without writing files")
    install_parser.add_argument("--yes", "-y", action="store_true", help="Apply without interactive confirmation")
    install_parser.add_argument("--no-settings", action="store_true", help="Do not merge the safe settings fragment")

    diff_parser = claude_sub.add_parser("diff", help="Show file-level differences for managed files")
    diff_parser.add_argument("--home", default=None, help="Target home directory (default: current user's home)")

    doctor_parser = claude_sub.add_parser("doctor", help="Check Claude Code and kit installation status")
    doctor_parser.add_argument("--home", default=None, help="Target home directory (default: current user's home)")

    uninstall_parser = claude_sub.add_parser("uninstall", help="Remove files managed by this kit")
    uninstall_parser.add_argument("--home", default=None, help="Target home directory (default: current user's home)")
    uninstall_parser.add_argument("--dry-run", action="store_true", help="Show changes without writing files")
    uninstall_parser.add_argument("--yes", "-y", action="store_true", help="Apply without interactive confirmation")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "kits" and args.kits_command == "list":
        for name in KIT_NAMES:
            print(name)
        return 0

    if args.command == "kits" and args.kits_command == "claude-code":
        if args.claude_command == "install":
            return install(home=args.home, dry_run=args.dry_run, yes=args.yes, merge_settings=not args.no_settings)
        if args.claude_command == "diff":
            return diff_kit(home=args.home)
        if args.claude_command == "doctor":
            return doctor(home=args.home)
        if args.claude_command == "uninstall":
            return uninstall(home=args.home, dry_run=args.dry_run, yes=args.yes)

    parser.error("unsupported command")
    return 2


if __name__ == "__main__":
    sys.exit(main())
