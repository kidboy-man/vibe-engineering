import inspect
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents import cli
from agents.kit_registry import INSTALL_OPTIONS, KITS, KitSpec

ROOT = Path(__file__).resolve().parent.parent


def _accepts(fn, name: str) -> bool:
    params = inspect.signature(fn).parameters
    return name in params or any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())


class RegisteredKitContractTests(unittest.TestCase):
    def test_every_kit_callable_accepts_the_shared_arguments(self):
        for name, spec in KITS.items():
            with self.subTest(kit=name):
                for arg in ("home", "dry_run", "yes"):
                    self.assertTrue(_accepts(spec.install, arg), f"install missing {arg}")
                    self.assertTrue(_accepts(spec.uninstall, arg), f"uninstall missing {arg}")
                self.assertTrue(_accepts(spec.diff, "home"))
                self.assertTrue(_accepts(spec.doctor, "home"))
                if spec.enable_hook is not None:
                    for arg in ("home", "dry_run", "yes"):
                        self.assertTrue(_accepts(spec.enable_hook, arg))

    def test_every_declared_install_option_is_known_and_accepted(self):
        for name, spec in KITS.items():
            for key in spec.install_options:
                with self.subTest(kit=name, option=key):
                    self.assertIn(key, INSTALL_OPTIONS)
                    self.assertTrue(_accepts(spec.install, INSTALL_OPTIONS[key].kwarg))

    def test_registry_key_matches_spec_name(self):
        for key, spec in KITS.items():
            self.assertEqual(key, spec.name)


class OptionWiringTests(unittest.TestCase):
    def _spec(self, options):
        install = MagicMock(return_value=0)
        noop = MagicMock(return_value=0)
        spec = KitSpec(
            name="fake",
            help="fake",
            install=install,
            diff=noop,
            doctor=noop,
            uninstall=noop,
            install_options=frozenset(options),
        )
        return spec, install

    def _run(self, spec, argv):
        return cli.main(["kits", "fake", *argv], kit_specs={"fake": spec})

    def test_negated_options_map_to_positive_kwargs(self):
        spec, install = self._spec(INSTALL_OPTIONS)
        self.assertEqual(self._run(spec, ["install", "--yes"]), 0)
        kwargs = install.call_args.kwargs
        self.assertEqual(kwargs["home"], None)
        self.assertTrue(kwargs["yes"])
        self.assertFalse(kwargs["dry_run"])
        self.assertIs(kwargs["merge_settings"], True)
        self.assertIs(kwargs["setup_deps"], True)
        self.assertIs(kwargs["enable_hooks"], True)
        self.assertIs(kwargs["with_verify"], False)

    def test_flags_flip_kwargs(self):
        spec, install = self._spec(INSTALL_OPTIONS)
        self._run(spec, ["install", "--no-settings", "--no-setup-deps", "--no-hooks", "--with-verify"])
        kwargs = install.call_args.kwargs
        self.assertIs(kwargs["merge_settings"], False)
        self.assertIs(kwargs["setup_deps"], False)
        self.assertIs(kwargs["enable_hooks"], False)
        self.assertIs(kwargs["with_verify"], True)

    def test_undeclared_options_are_not_passed(self):
        spec, install = self._spec(set())
        self._run(spec, ["install"])
        self.assertEqual(set(install.call_args.kwargs), {"home", "dry_run", "yes"})


class PackagingTests(unittest.TestCase):
    def test_manifest_in_includes_templates_of_every_kit(self):
        lines = [
            line.split()
            for line in (ROOT / "MANIFEST.in").read_text(encoding="utf-8").splitlines()
            if line.startswith("recursive-include ")
        ]
        for kit in sorted(p.name for p in (ROOT / "agents" / "kits").iterdir() if p.is_dir() and p.name != "__pycache__"):
            probe = f"agents/kits/{kit}/templates/x.md"
            covered = any(len(parts) == 3 and parts[2] == "*" and probe.startswith(parts[1] + "/") for parts in lines)
            self.assertTrue(covered, f"MANIFEST.in does not include templates of kit {kit!r}")


if __name__ == "__main__":
    unittest.main()
