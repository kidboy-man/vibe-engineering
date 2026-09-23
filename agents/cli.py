"""Command-line interface for Vibe Engineering kits."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from importlib import metadata
from typing import Mapping

from agents.kit_registry import KITS, KitSpec

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
        if "settings" in kit.install_options:
            install_parser.add_argument("--no-settings", action="store_true", help="Do not merge the safe settings fragment")
        if "setup_deps" in kit.install_options:
            install_parser.add_argument("--no-setup-deps", action="store_true", help="Do not auto-install qmd or other dependencies")
        if "hooks" in kit.install_options:
            install_parser.add_argument("--no-hooks", action="store_true", help="Skip the proactive SessionStart hook / CLAUDE.md prompt")

        if "with_verify" in kit.install_options:
            install_parser.add_argument("--with-verify", action="store_true", help="Also register the opt-in gofmt check after Claude Code edits")

        diff_parser = kit_sub.add_parser("diff", help="Show file-level differences for managed files")
        diff_parser.add_argument("--home", default=None, help="Target config base directory (default: $XDG_CONFIG_HOME or current user's home)")

        doctor_parser = kit_sub.add_parser("doctor", help=f"Check {kit.name} kit installation status")
        doctor_parser.add_argument("--home", default=None, help="Target config base directory (default: $XDG_CONFIG_HOME or current user's home)")

        uninstall_parser = kit_sub.add_parser("uninstall", help="Remove files managed by this kit")
        uninstall_parser.add_argument("--home", default=None, help="Target config base directory (default: $XDG_CONFIG_HOME or current user's home)")
        uninstall_parser.add_argument("--dry-run", action="store_true", help="Show changes without writing files")
        uninstall_parser.add_argument("--yes", "-y", action="store_true", help="Apply without interactive confirmation")

        if kit.enable_hook is not None:
            enable_hook_parser = kit_sub.add_parser("enable-hook", help="Enable proactive context wiring (SessionStart hook + persona section) for Claude Code, Codex CLI, Cursor, and OpenCode")
            enable_hook_parser.add_argument("--home", default=None, help="Target config base directory (default: $XDG_CONFIG_HOME or current user's home)")
            enable_hook_parser.add_argument("--dry-run", action="store_true", help="Show changes without writing files")
            enable_hook_parser.add_argument("--yes", "-y", action="store_true", help="Apply without interactive confirmation")

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
            kwargs = {"home": args.home, "dry_run": args.dry_run, "yes": args.yes}
            if "settings" in kit.install_options:
                kwargs["merge_settings"] = not args.no_settings
            if "setup_deps" in kit.install_options:
                kwargs["setup_deps"] = not args.no_setup_deps
            if "hooks" in kit.install_options:
                kwargs["enable_hooks"] = not args.no_hooks
            if "with_verify" in kit.install_options:
                kwargs["with_verify"] = args.with_verify
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
