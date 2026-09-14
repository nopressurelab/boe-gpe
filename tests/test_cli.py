import unittest

from collector.__main__ import _opt, build_parser


class CliTest(unittest.TestCase):
    """The CLI is driven by CI, so argument placement is part of the contract."""

    def parse(self, argv):
        return build_parser().parse_args(argv)

    def test_workflow_invocation(self):
        # Exactly what .github/workflows/daily.yml runs.
        args = self.parse(["collect", "--days", "4", "--verbose"])
        self.assertEqual(args.days, 4)
        self.assertTrue(_opt(args, "verbose", False))

    def test_global_flag_after_subcommand(self):
        self.assertTrue(_opt(self.parse(["collect", "-v"]), "verbose", False))

    def test_global_flag_before_subcommand(self):
        self.assertTrue(_opt(self.parse(["-v", "collect"]), "verbose", False))

    def test_global_flag_absent(self):
        self.assertFalse(_opt(self.parse(["check"]), "verbose", False))

    def test_root_works_on_either_side(self):
        for argv in (["--root", "/tmp/x", "build"], ["build", "--root", "/tmp/x"]):
            with self.subTest(argv=argv):
                self.assertEqual(_opt(self.parse(argv), "root", "."), "/tmp/x")

    def test_defaults_survive_when_flag_is_omitted(self):
        args = self.parse(["check"])
        self.assertEqual(_opt(args, "root", "."), ".")
        self.assertEqual(_opt(args, "templates", "templates"), "templates")
        self.assertIsNone(_opt(args, "config_dir", None))

    def test_every_subcommand_has_a_handler(self):
        for name in ("collect", "build", "run", "check"):
            with self.subTest(command=name):
                self.assertTrue(callable(self.parse([name]).func))

    def test_collect_options(self):
        args = self.parse(["collect", "--date", "2026-09-14",
                           "--source", "boe", "--source", "dog", "--dry-run"])
        self.assertEqual(args.date, "2026-09-14")
        self.assertEqual(args.source, ["boe", "dog"])
        self.assertTrue(args.dry_run)

    def test_run_accepts_the_same_collect_options(self):
        args = self.parse(["run", "--days", "2", "--dry-run", "-v"])
        self.assertEqual(args.days, 2)
        self.assertTrue(args.dry_run)
        self.assertTrue(_opt(args, "verbose", False))


if __name__ == "__main__":
    unittest.main()
