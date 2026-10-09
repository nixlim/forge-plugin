"""FR-090 dollar-quoted guard regressions for bead forge-plugin-752."""

import json
import subprocess
import unittest
from unittest import mock

from tests.test_commit_guard import GUARD_POLICY_MALFORMED
from tests.test_fr223_v2_hook import (
    DENIALS,
    HookHarnessMixin,
    denial,
    load_guard_module,
)


class DollarQuoteActionTests(HookHarnessMixin, unittest.TestCase):
    def test_dollar_quoted_git_actions_require_quote_normalization(self) -> None:
        module = load_guard_module(self, "forge_guard_dollar_quoted_actions")
        for command, expected in (
            ("git commit -m x", [("git", "commit")]),
            ("git push origin main", [("git", "push")]),
        ):
            with self.subTest(control=command):
                actions = module.find_actions(command)
                self.assertEqual(
                    [(action.executable, action.subcommand) for action in actions],
                    expected,
                )

        cases = (
            ("$'git' commit -m x", ("git", "commit")),
            ("git $'commit' -m x", ("git", "commit")),
            ('$"git" commit -m x', ("git", "commit")),
            ('git $"commit" -m x', ("git", "commit")),
            ("FOO=1 $'git' commit -m x", ("git", "commit")),
            ("env FOO=1 $'git' push origin main", ("git", "push")),
            ("cat <<'EOF'\nbody\nEOF\n$'git' commit -m x", ("git", "commit")),
            ("cat <<EOF\n$($'git' commit -m x)\nEOF", ("git", "commit")),
            ("$'git' push origin main", ("git", "push")),
        )
        for command, expected in cases:
            with self.subTest(command=command):
                actions = module.find_actions(command)
                self.assertEqual(
                    [(action.executable, action.subcommand) for action in actions],
                    [expected],
                )
                with mock.patch.object(
                    module, "_normalize_dollar_quotes", side_effect=lambda value: value
                ):
                    self.assertEqual(module.find_actions(command), [])

    def test_escaped_dollar_quotes_do_not_hide_later_git_actions(self) -> None:
        module = load_guard_module(self, "forge_guard_escaped_dollar_quoted_actions")
        cases = (
            ("echo $'\\'' ; git commit -m x", ("git", "commit")),
            ("echo $'\\'' && git commit -m x", ("git", "commit")),
            ("echo $'\\''\ngit commit -m x", ("git", "commit")),
            ("echo $'it\\'s' ; git push origin main", ("git", "push")),
            ("echo $'a\\'b'; git commit -m x", ("git", "commit")),
        )
        for command, expected in cases:
            with self.subTest(command=command):
                actions = module.find_actions(command)
                self.assertEqual(
                    [(action.executable, action.subcommand) for action in actions],
                    [expected],
                )
                with mock.patch.object(
                    module, "_normalize_dollar_quotes", side_effect=lambda value: value
                ):
                    self.assertEqual(module.find_actions(command), [])

    def test_nul_ansi_c_quotes_fail_closed_in_action_discovery(self) -> None:
        module = load_guard_module(self, "forge_guard_dollar_quoted_nul_actions")
        for command in (
            "$'git\\0evil' commit -m x",
            "git $'commit\\0evil' -m x",
        ):
            with self.subTest(command=command):
                with self.assertRaises(module.GuardDeniedCommandError):
                    module.find_actions(command)
                with mock.patch.object(
                    module, "_normalize_dollar_quotes", side_effect=lambda value: value
                ):
                    self.assertEqual(module.find_actions(command), [])

    def test_dollar_quoted_git_actions_reach_raw_commit_and_push_denials(self) -> None:
        repo = self.repository("forge-verbs-v1", None)
        for command in (
            "git commit -m x",
            "$'git' commit -m x",
            "git $'commit' -m x",
            "FOO=1 $'git' commit -m x",
            "cat <<'EOF'\nbody\nEOF\n$'git' commit -m x",
            "cat <<EOF\n$($'git' commit -m x)\nEOF",
        ):
            with self.subTest(raw_commit=command):
                result = self.invoke(repo, command)
                self.assertEqual(json.loads(result.stdout), denial(DENIALS["deny-raw-commit"]))
        for command in (
            "git push origin main",
            "env FOO=1 $'git' push origin main",
            "$'git' push origin main",
        ):
            with self.subTest(raw_push=command):
                result = self.invoke(repo, command)
                self.assertEqual(json.loads(result.stdout), denial(DENIALS["deny-raw-push"]))

    def test_escaped_dollar_quotes_reach_raw_commit_and_push_denials(self) -> None:
        repo = self.repository("forge-verbs-v1", None)
        cases = (
            ("echo $'\\'' ; git commit -m x", "deny-raw-commit"),
            ("echo $'it\\'s' ; git push origin main", "deny-raw-push"),
        )
        for command, denial_key in cases:
            with self.subTest(command=command):
                result = self.invoke(repo, command)
                self.assertEqual(json.loads(result.stdout), denial(DENIALS[denial_key]))

    def test_nul_ansi_c_quotes_reach_policy_malformed_hook_denial(self) -> None:
        commands = (
            "$'git\\0evil' commit -m x",
            "git $'commit\\0evil' -m x",
        )
        for mode in ("forge-verbs-v1", "legacy-v1", "non-forge", "upstream"):
            repo = self.repository(mode, None)
            for command in commands:
                with self.subTest(mode=mode, command=command):
                    result = self.invoke(repo, command)
                    self.assertEqual(result.returncode, 0)
                    self.assertEqual(
                        json.loads(result.stdout), denial(GUARD_POLICY_MALFORMED)
                    )

    def test_nul_ansi_c_quotes_deny_cross_repository_from_outside(self) -> None:
        repo = self.repository("forge-verbs-v1", None)
        outside = self.scratch / "outside"
        outside.mkdir()
        probe = subprocess.run(
            ["git", "-C", str(outside), "rev-parse", "--show-toplevel"],
            capture_output=True,
            check=False,
            text=True,
        )
        self.assertNotEqual(probe.returncode, 0)

        for command in (
            f"git -C {repo} $'commit\\0evil' -m x",
            f"git -C {repo} $'push\\0evil' origin main",
        ):
            with self.subTest(command=command):
                result = self.invoke(outside, command)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(
                    json.loads(result.stdout), denial(GUARD_POLICY_MALFORMED)
                )

        result = self.invoke(outside, f"git -C {repo} commit -m x")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout), denial(DENIALS["deny-raw-commit"]))
