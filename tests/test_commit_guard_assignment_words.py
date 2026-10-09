"""FR-090 regressions for git verbs after substitution-bearing assignments."""

import json
import os
import subprocess
import time
import unittest
from pathlib import Path
from types import ModuleType
from unittest import mock

from tests import test_fr223_v2_hook as v2_hook
from tests.test_fr223_v2_hook import (
    DENIALS,
    LEGACY_OPERATOR_DENIALS,
    HookHarnessMixin,
    denial,
    load_guard_module,
)


class AssignmentWordActionTests(HookHarnessMixin, unittest.TestCase):
    BRACE_SEPARATOR_DEFAULTS = ("a;b", "a|b", "a&&b", "a||b", "a&b", "a\nb")
    NON_EXPANSION_WRAPPERS = (
        ("comment-brace", "true # ${\n{inner}; echo }"),
        ("comment-bracket", "true # $[\n{inner}; echo ]"),
        ("pid-brace", "true $${; {inner}; echo }"),
        ("pid-bracket", "true $$[; {inner}; echo ]"),
        ("heredoc-brace", "cat <<EOF\n${\nEOF\n{inner}; echo }"),
    )
    MERGE_APPROVE = (
        "python3 scripts/forge/cli.py merge approve "
        "--candidate abc --chain-id c-2026-09-01T000000Z-0000"
    )
    COMMIT_APPROVE = (
        "python3 scripts/forge/cli.py commit approve "
        "--candidate abc --chain-id c-2026-09-01T000000Z-0000"
    )
    BRACE_DENIED_ROW_COMMAND = "A=${X:-a;b} git push --force origin main"
    DENIED_ROW_COMMANDS = (
        "A=$(x y) git push --force origin main",
        "A=`x y` git push --force origin main",
        "A=${X:-a b} git push --force origin main",
        BRACE_DENIED_ROW_COMMAND,
        "env A=$(x y) git push --force origin main",
    )
    CONTROLS = (
        ("A=1 git commit -m x", ("git", "commit")),
        ('A="$(cat pid)" git commit -m x', ("git", "commit")),
        ("A='$(cat pid)' git commit -m x", ("git", "commit")),
        ("A='`cat pid`' git commit -m x", ("git", "commit")),
        ('A="`cat pid`" git commit -m x', ("git", "commit")),
    )
    SUBSTITUTIONS = (
        ("A=$(cat pid) git commit -m x", ("git", "commit")),
        ("A=`cat pid` git commit -m x", ("git", "commit")),
        ("A=${X:-a b} git commit -m x", ("git", "commit")),
        ("A=$((1 + 2)) git commit -m x", ("git", "commit")),
        ("A=$[1 + 2] git commit -m x", ("git", "commit")),
        ("A=$[arr[0] + 1] git commit -m x", ("git", "commit")),
        ("A=$[matrix[0][1] + 1] git commit -m x", ("git", "commit")),
        ("A=<(cat pid) git commit -m x", ("git", "commit")),
        ("A=$(cat pid) git push origin main", ("git", "push")),
        ("A=$(cat pid) B=$(id -u) git push origin main", ("git", "push")),
        ("env A=$(cat pid) git commit -m x", ("git", "commit")),
        ("env -i A=$(printf 123) git commit -m x", ("git", "commit")),
        ("env --ignore-environment A=$(cat pid) git push origin main", ("git", "push")),
        ("/usr/bin/env -u OLD A=${X:-a b} /usr/bin/git commit -m x", ("/usr/bin/git", "commit")),
        ("A=${X:-a b } git commit -m x", ("git", "commit")),
        ('A=${X:-"}" b} git commit -m x', ("git", "commit")),
        (r"A=${X:-\} b} git commit -m x", ("git", "commit")),
        ("A=${X:-${Y} b} git commit -m x", ("git", "commit")),
    )
    MASKING_INDEPENDENT = (
        ("A=${X:-$(y)} git commit -m x", ("git", "commit")),
        ('A=${X:-"}"} git commit -m x', ("git", "commit")),
        (r"A=${X:-\}} git commit -m x", ("git", "commit")),
        ("A=${X:-${Y}} git commit -m x", ("git", "commit")),
        ("git commit -m $(date)", ("git", "commit")),
        ("A=$(git commit -m x) true", ("git", "commit")),
        ('A="${X:-a b}" git commit -m x', ("git", "commit")),
    )

    @staticmethod
    def action_pairs(module: ModuleType, command: str) -> list[tuple[str, str]]:
        return [
            (action.executable, action.subcommand)
            for action in module.find_actions(command)
        ]

    def test_assignment_substitutions_preserve_git_actions(self) -> None:
        module = load_guard_module(self, "forge_guard_assignment_word_actions")
        for command, expected in self.CONTROLS:
            with self.subTest(control=command):
                self.assertEqual(module._mask_unquoted_substitutions(command), command)
                self.assertEqual(self.action_pairs(module, command), [expected])
                with mock.patch.object(
                    module, "_mask_unquoted_substitutions", side_effect=lambda value: value
                ):
                    self.assertEqual(self.action_pairs(module, command), [expected])

        for command, expected in self.SUBSTITUTIONS:
            with self.subTest(command=command):
                self.assertEqual(self.action_pairs(module, command), [expected])
                with mock.patch.object(
                    module,
                    "_mask_unquoted_substitutions",
                    side_effect=lambda value: value,
                ):
                    self.assertEqual(module.find_actions(command), [])

        for command, expected in self.MASKING_INDEPENDENT:
            with self.subTest(command=command):
                self.assertEqual(self.action_pairs(module, command), [expected])
                with mock.patch.object(
                    module, "_mask_unquoted_substitutions", side_effect=lambda value: value
                ):
                    self.assertEqual(self.action_pairs(module, command), [expected])

    def test_assignment_substitutions_do_not_invent_outer_actions(self) -> None:
        module = load_guard_module(self, "forge_guard_assignment_word_negatives")
        for command in (
            "echo A=$(cat pid) git commit -m x",
            "A=$(cat pid)",
            "echo $(date) git commit",
        ):
            with self.subTest(command=command):
                self.assertEqual(module.find_actions(command), [])

    def test_assignment_value_survives_action_tokenization(self) -> None:
        module = load_guard_module(self, "forge_guard_assignment_word_value")
        actions = module.find_actions("A=$(cat pid) git commit -m x")
        self.assertEqual(actions[0].assignments, (("A", "$(cat pid)"),))
        quoted = 'A="${X:-a b}" git commit -m x'
        self.assertEqual(module._mask_unquoted_substitutions(quoted), quoted)
        self.assertEqual(
            module.find_actions(quoted)[0].assignments, (("A", "${X:-a b}"),)
        )

    def test_nested_git_action_survives_assignment_masking(self) -> None:
        module = load_guard_module(self, "forge_guard_assignment_word_nested")
        self.assertEqual(
            self.action_pairs(module, "A=$(git commit -m x) true"),
            [("git", "commit")],
        )

    def test_brace_separator_defaults_run_and_need_span_helper(self) -> None:
        """The span helper keeps Bash's assignment defaults in one segment."""
        module = load_guard_module(self, "forge_guard_brace_separator_actions")
        fake_bin = self.scratch / "bin"
        fake_bin.mkdir()
        fake_git = fake_bin / "git"
        fake_git.write_text(
            '#!/bin/sh\nprintf "%s|%s\\n" "$*" "${A-}"\n',
            encoding="utf-8",
        )
        fake_git.chmod(0o755)
        environment = os.environ.copy()
        environment["PATH"] = f"{fake_bin}{os.pathsep}{environment.get('PATH', '')}"
        for default in self.BRACE_SEPARATOR_DEFAULTS:
            command = "A=${X:-" + default + "} git commit -m x"
            with self.subTest(command=command):
                result = subprocess.run(
                    ["bash", "-c", "X=; " + command],
                    env=environment,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, f"commit -m x|{default}\n")
                self.assertEqual(self.action_pairs(module, command), [("git", "commit")])
                with mock.patch.object(
                    module, "_substitution_span_ends", side_effect=lambda view: {}
                ):
                    self.assertEqual(self.action_pairs(module, command), [])

    def test_brace_separator_controls_keep_their_actions(self) -> None:
        module = load_guard_module(self, "forge_guard_brace_separator_controls")
        for command in (
            "A=${X}; git commit -m x",
            "echo ${X; git commit -m x",
            "A=$[1;2] git commit -m x",
        ):
            with self.subTest(command=command):
                self.assertEqual(self.action_pairs(module, command), [("git", "commit")])
        for command in (
            "echo ${X; git commit -m x",
            "A=$[1;2] git commit -m x",
        ):
            with self.subTest(bash_rejects=command):
                result = subprocess.run(
                    ["bash", "-c", command], check=False, capture_output=True, text=True
                )
                self.assertNotEqual(result.returncode, 0)

    def test_parameter_wrapper_structured_pass_needs_span_helper(self) -> None:
        """The span skip supersedes the parameter raw-union dependency."""
        module = load_guard_module(self, "forge_guard_parameter_span_skip")
        push = v2_hook.GuardRawSegmentUnionTests.wrap(
            "parameter", v2_hook.GuardRawSegmentUnionTests.PUSH
        )
        approve = v2_hook.GuardRawSegmentUnionTests.wrap(
            "parameter", v2_hook.GuardRawSegmentUnionTests.APPROVE
        )
        with mock.patch.object(module, "RAW_SEGMENT_PASS_ENABLED", False):
            self.assertEqual(
                [action.subcommand for action in module.find_actions(push)], ["push"]
            )
            self.assertEqual(
                module.classify_forge_cli_invocation(approve), "deny-merge-approve"
            )
            with mock.patch.object(
                module, "_substitution_span_ends", side_effect=lambda view: {}
            ):
                self.assertEqual(module.find_actions(push), [])
                self.assertEqual(module.classify_forge_cli_invocation(approve), "no-match")

    def test_many_substitution_words_fit_parse_budget(self) -> None:
        module = load_guard_module(self, "forge_guard_assignment_word_budget")
        command = " ".join(f"A{index}=${{X:-a b}}" for index in range(1800))
        command += " git commit -m x"
        started = time.perf_counter()
        actions, _operator = module._classify_command_bounded(command)
        elapsed = time.perf_counter() - started
        self.assertEqual(
            [(action.executable, action.subcommand) for action in actions],
            [("git", "commit")],
        )
        # Quadratic rescans took 10 s at 9000 chars; linear took 0.01 s, so 5 s only guards hangs.
        self.assertLess(elapsed, 5.0)
        with mock.patch.object(
            module, "_mask_unquoted_substitutions", side_effect=lambda value: value
        ):
            actions, _operator = module._classify_command_bounded(command)
            self.assertEqual(actions, [])

    def test_unterminated_braces_fit_parse_budget(self) -> None:
        module = load_guard_module(self, "forge_guard_unterminated_braces")
        segment = "A=" + "${" * 4500 + " git commit -m x"
        started = time.perf_counter()
        masked = module._mask_unquoted_substitutions(segment)
        elapsed = time.perf_counter() - started
        self.assertEqual(masked, segment)
        # Quadratic rescans took 10 s at 9000 chars; linear took 0.01 s, so 5 s only guards hangs.
        self.assertLess(elapsed, 5.0)

    def test_old_style_arithmetic_substitution_runs_in_bash(self) -> None:
        result = subprocess.run(
            [
                "bash",
                "-c",
                'git() { printf "%s|%s\\n" "$A" "$*"; }; A=$[1 + 2] git commit -m x',
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "3|commit -m x\n")

    def test_denied_row_spellings_run_git_in_bash(self) -> None:
        fake_bin = self.scratch / "bin"
        fake_bin.mkdir()
        fake_git = fake_bin / "git"
        fake_git.write_text(
            '#!/bin/sh\nprintf "%s|%s\\n" "$*" "${A-}"\n',
            encoding="utf-8",
        )
        fake_git.chmod(0o755)
        environment = os.environ.copy()
        environment["PATH"] = f"{fake_bin}{os.pathsep}{environment.get('PATH', '')}"
        for command in self.DENIED_ROW_COMMANDS:
            with self.subTest(command=command):
                result = subprocess.run(
                    ["bash", "-c", "x() { printf expanded; }; X=; " + command],
                    env=environment,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                assignment = "expanded"
                if "${X:-a b}" in command:
                    assignment = "a b"
                elif "${X:-a;b}" in command:
                    assignment = "a;b"
                self.assertEqual(
                    result.stdout,
                    f"push --force origin main|{assignment}\n",
                )

    def test_assignment_substitutions_preserve_operator_verbs(self) -> None:
        module = load_guard_module(self, "forge_guard_assignment_word_operators")
        spellings = (
            ("VAR=$(cat pid) python3 scripts/forge/cli.py commit approve x", "deny-approve"),
            ("VAR=`cat pid` python3 scripts/forge/cli.py commit approve x", "deny-approve"),
            (
                "VAR=$[arr[0] + 1] python3 scripts/forge/cli.py commit approve x",
                "deny-approve",
            ),
            (
                "VAR=${X:-a b} python3 scripts/forge/cli.py "
                "merge approve --candidate c --chain-id d",
                "deny-merge-approve",
            ),
        )
        for command, expected in spellings:
            with self.subTest(command=command):
                plain = command.split(" python3 ", 1)[1]
                self.assertEqual(
                    module._classify_forge_cli_segment("python3 " + plain), expected
                )
                self.assertEqual(module._classify_forge_cli_segment(command), expected)
                with mock.patch.object(
                    module, "_mask_unquoted_substitutions", side_effect=lambda value: value
                ):
                    self.assertEqual(module._classify_forge_cli_segment(command), "no-match")

    def test_brace_separator_operator_verb_needs_span_helper(self) -> None:
        module = load_guard_module(self, "forge_guard_brace_separator_operator")
        command = "VAR=${X:-a;b} python3 scripts/forge/cli.py commit approve x"
        self.assertEqual(module._classify_forge_cli_segment(command), "deny-approve")
        self.assertEqual(module._classify_forge_cli_invocation_bounded(command), "deny-approve")
        with mock.patch.object(
            module, "_substitution_span_ends", side_effect=lambda view: {}
        ):
            self.assertEqual(module._classify_forge_cli_invocation_bounded(command), "no-match")

    def test_assignment_substitutions_preserve_direct_invocations(self) -> None:
        module = load_guard_module(self, "forge_guard_assignment_word_direct_invocations")
        expected = ("git", "push", "--force", "origin", "main")
        for command in self.DENIED_ROW_COMMANDS:
            with self.subTest(command=command):
                self.assertIn(
                    expected,
                    module._find_direct_invocations_recursive(command, Path.cwd()),
                )
                with mock.patch.object(
                    module, "_mask_unquoted_substitutions", side_effect=lambda value: value
                ):
                    invocations = module._find_direct_invocations_recursive(
                        command, Path.cwd()
                    )
                    if command == self.BRACE_DENIED_ROW_COMMAND:
                        self.assertIn(expected, invocations)
                    else:
                        self.assertNotIn(expected, invocations)

    def test_brace_separator_direct_invocation_needs_span_helper(self) -> None:
        module = load_guard_module(self, "forge_guard_brace_separator_direct")
        command = self.BRACE_DENIED_ROW_COMMAND
        expected = ("git", "push", "--force", "origin", "main")
        self.assertIn(
            expected, module._find_direct_invocations_recursive(command, Path.cwd())
        )
        with mock.patch.object(
            module, "_substitution_span_ends", side_effect=lambda view: {}
        ):
            self.assertNotIn(
                expected, module._find_direct_invocations_recursive(command, Path.cwd())
            )

    def test_assignment_substitutions_match_committed_denied_row(self) -> None:
        repo = self.repository("forge-verbs-v1", None)
        reason = "force pushes require an operator-reviewed release path"
        (repo / "forge-project.md").write_text(
            "<!-- FORGE:REGION guard-denied-commands BEGIN -->\n"
            "| pattern | reason |\n"
            "|---|---|\n"
            f"| git push --force | {reason} |\n"
            "<!-- FORGE:REGION guard-denied-commands END -->\n",
            encoding="utf-8",
        )
        self.git(repo, "add", "forge-project.md")
        self.git(repo, "commit", "--quiet", "-m", "install command policy")
        for command in self.DENIED_ROW_COMMANDS:
            with self.subTest(command=command):
                result = self.invoke(repo, command)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(
                    json.loads(result.stdout),
                    denial(f"forge: operator-denied command — {reason}"),
                )

    def test_assignment_substitution_operator_verb_is_denied_by_hook(self) -> None:
        repo = self.repository("forge-verbs-v1", None)
        command = "VAR=$(cat pid) python3 scripts/forge/cli.py commit approve x"
        result = self.invoke(repo, command)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            denial(LEGACY_OPERATOR_DENIALS["deny-approve"]),
        )

    def test_assignment_substitutions_reach_raw_git_denials(self) -> None:
        repo = self.repository("forge-verbs-v1", None)
        for command, (_, subcommand) in (
            *self.CONTROLS,
            *self.SUBSTITUTIONS,
            *self.MASKING_INDEPENDENT,
        ):
            with self.subTest(command=command):
                result = self.invoke(repo, command)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(
                    json.loads(result.stdout),
                    denial(DENIALS[f"deny-raw-{subcommand}"]),
                )


class DollarRunOpenerTests(HookHarnessMixin, unittest.TestCase):
    @staticmethod
    def action_pairs(module: ModuleType, command: str) -> list[tuple[str, str]]:
        return AssignmentWordActionTests.action_pairs(module, command)

    def fake_verbs_environment(self) -> dict[str, str]:
        fake_bin = self.scratch / "bin"
        fake_bin.mkdir()
        for name in ("git", "python3"):
            executable = fake_bin / name
            executable.write_text(
                '#!/bin/sh\nprintf "%s|%s\\n" "$*" "${A-${VAR-}}"\n',
                encoding="utf-8",
            )
            executable.chmod(0o755)
        environment = os.environ.copy()
        environment["PATH"] = f"{fake_bin}{os.pathsep}{environment.get('PATH', '')}"
        return environment

    def test_pid_prefix_words_expose_bash_verbs(self) -> None:
        module = load_guard_module(self, "forge_guard_odd_dollar_verbs")
        environment = self.fake_verbs_environment()
        rows = (
            (
                "A=$${X git push origin main}",
                ("git", "push"),
                ("git", "push", "origin", "main}"),
                "{X",
            ),
            ("A=$$[X git commit -m x]", ("git", "commit"), ("git", "commit", "-m", "x]"), "[X"),
            (
                "env A=$${X git push --force origin main}",
                ("git", "push"),
                ("git", "push", "--force", "origin", "main}"),
                "{X",
            ),
            (
                "VAR=$${X python3 scripts/forge/cli.py commit approve x}",
                None,
                ("python3", "scripts/forge/cli.py", "commit", "approve", "x}"),
                "{X",
            ),
        )
        def old_rule(text: str, offset: int) -> bool:
            return text.startswith(("${", "$["), offset)

        for command, action, invocation, suffix in rows:
            with self.subTest(command=command):
                result = subprocess.run(
                    ["bash", "-c", "X=; " + command],
                    env=environment,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                arguments, assignment = result.stdout.split("|", 1)
                self.assertEqual(arguments, " ".join(invocation[1:]))
                self.assertTrue(assignment.endswith(suffix + "\n"), assignment)
                self.assertTrue(assignment[: -len(suffix) - 1].isdigit(), assignment)
                self.assertEqual(self.action_pairs(module, command), [action] if action else [])
                classification = "deny-approve" if action is None else "no-match"
                self.assertEqual(module.classify_forge_cli_invocation(command), classification)
                self.assertIn(invocation, module.find_direct_invocations(command))
                with mock.patch.object(module, "_expansion_opener_at", side_effect=old_rule):
                    self.assertEqual(self.action_pairs(module, command), [])
                    self.assertEqual(module.classify_forge_cli_invocation(command), "no-match")
                    self.assertNotIn(invocation, module.find_direct_invocations(command))

    def test_pid_prefix_force_push_matches_committed_denied_row(self) -> None:
        repo = self.repository("forge-verbs-v1", None)
        reason = "force pushes require an operator-reviewed release path"
        (repo / "forge-project.md").write_text(
            "<!-- FORGE:REGION guard-denied-commands BEGIN -->\n"
            "| pattern | reason |\n"
            "|---|---|\n"
            f"| git push --force | {reason} |\n"
            "<!-- FORGE:REGION guard-denied-commands END -->\n",
            encoding="utf-8",
        )
        self.git(repo, "add", "forge-project.md")
        self.git(repo, "commit", "--quiet", "-m", "install command policy")
        result = self.invoke(repo, "env A=$${X git push --force origin main}")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            denial(f"forge: operator-denied command — {reason}"),
        )

    def test_even_dollar_runs_keep_bash_assignment_words_whole(self) -> None:
        module = load_guard_module(self, "forge_guard_even_dollar_verbs")
        environment = self.fake_verbs_environment()
        commands = (
            ("A=$$${X:-a b} git commit -m x", None),
            (r"A=\$${X:-a b} git commit -m x", "$a b\n"),
        )
        invocation = ("git", "commit", "-m", "x")
        for command, expected_assignment in commands:
            with self.subTest(command=command):
                result = subprocess.run(
                    ["bash", "-c", "X=; " + command],
                    env=environment,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                arguments, assignment = result.stdout.split("|", 1)
                self.assertEqual(arguments, "commit -m x")
                if expected_assignment is None:
                    self.assertRegex(assignment, r"^[0-9]+a b\n$")
                else:
                    self.assertEqual(assignment, expected_assignment)
                self.assertEqual(self.action_pairs(module, command), [("git", "commit")])
                self.assertEqual(module.classify_forge_cli_invocation(command), "no-match")
                self.assertIn(invocation, module.find_direct_invocations(command))
                with mock.patch.object(
                    module, "_expansion_opener_at", side_effect=lambda text, offset: False
                ):
                    self.assertEqual(self.action_pairs(module, command), [])
                    self.assertEqual(module.classify_forge_cli_invocation(command), "no-match")
                    self.assertNotIn(invocation, module.find_direct_invocations(command))

    def test_dollar_run_parity_controls_mask_and_segments(self) -> None:
        module = load_guard_module(self, "forge_guard_dollar_run_parity")
        spellings = (
            ("${X}", True),
            ("$${X}", False),
            ("$$${X}", True),
            ("$$$${X}", False),
            ("$$$$${X}", True),
            (r"\$${X}", True),
            (r"\$$${X}", False),
            ("$[X]", True),
            ("$$[X]", False),
        )
        for spelling, expected in spellings:
            with self.subTest(spelling=spelling):
                offset = max(spelling.find("${"), spelling.find("$["))
                self.assertEqual(module._expansion_opener_at(spelling, offset), expected)
                view = module._shell_syntax_view(spelling)
                self.assertEqual(module._expansion_opener_at(view, offset), expected)

        literal = "A=$${X a b}"
        self.assertEqual(module._mask_unquoted_substitutions(literal), literal)
        command = "true $${; git push origin main; echo }"
        expected_segments = [
            ("true $${", ";"),
            (" git push origin main", ";"),
            (" echo }", None),
        ]
        self.assertEqual(module.split_segments(command), expected_segments)
        default = "A=${X:-a;b} git commit -m x"
        self.assertEqual(module.split_segments(default), [(default, None)])
        def old_rule(text: str, offset: int) -> bool:
            return text.startswith(("${", "$["), offset)

        with mock.patch.object(module, "_expansion_opener_at", side_effect=old_rule):
            self.assertNotEqual(module._mask_unquoted_substitutions(literal), literal)
            self.assertEqual(module.split_segments(command), [(command, None)])


class NonExpansionSpanTests(HookHarnessMixin, unittest.TestCase):
    NON_EXPANSION_WRAPPERS = AssignmentWordActionTests.NON_EXPANSION_WRAPPERS
    MERGE_APPROVE = AssignmentWordActionTests.MERGE_APPROVE
    COMMIT_APPROVE = AssignmentWordActionTests.COMMIT_APPROVE
    BRACE_SEPARATOR_DEFAULTS = AssignmentWordActionTests.BRACE_SEPARATOR_DEFAULTS
    action_pairs = staticmethod(AssignmentWordActionTests.action_pairs)

    def test_non_expansion_openers_need_raw_union(self) -> None:
        """PID parity finds actions alone; raw union catches old-rule PID, comment, heredoc."""
        module = load_guard_module(self, "forge_guard_non_expansion_union")
        fake_bin = self.scratch / "bin"
        fake_bin.mkdir()
        fake_git = fake_bin / "git"
        fake_git.write_text(
            '#!/bin/sh\nprintf "git:%s\\n" "$*"\n', encoding="utf-8"
        )
        fake_git.chmod(0o755)
        environment = os.environ.copy()
        environment["PATH"] = f"{fake_bin}{os.pathsep}{environment.get('PATH', '')}"
        expected_force = ("git", "push", "--force", "origin", "main")
        def old_rule(text: str, offset: int) -> bool:
            return text.startswith(("${", "$["), offset)

        for name, wrapper in self.NON_EXPANSION_WRAPPERS:
            push = wrapper.replace("{inner}", "git push origin main")
            merge_approve = wrapper.replace("{inner}", self.MERGE_APPROVE)
            commit_approve = wrapper.replace("{inner}", self.COMMIT_APPROVE)
            force = wrapper.replace("{inner}", "git push --force origin main")
            with self.subTest(wrapper=name):
                result = subprocess.run(
                    ["bash", "-c", push],
                    env=environment,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.splitlines().count("git:push origin main"), 1)
                self.assertEqual(self.action_pairs(module, push), [("git", "push")])
                self.assertEqual(
                    module.classify_forge_cli_invocation(merge_approve),
                    "deny-merge-approve",
                )
                self.assertEqual(
                    module.classify_forge_cli_invocation(commit_approve), "deny-approve"
                )
                self.assertIn(expected_force, module.find_direct_invocations(force))
                with mock.patch.object(module, "RAW_SEGMENT_PASS_ENABLED", False):
                    pid_row = name.startswith("pid-")
                    if pid_row:
                        self.assertEqual(self.action_pairs(module, push), [("git", "push")])
                    else:
                        self.assertEqual(module.find_actions(push), [])
                    self.assertEqual(
                        module.classify_forge_cli_invocation(merge_approve),
                        "deny-merge-approve" if pid_row else "no-match",
                    )
                    self.assertEqual(
                        module.classify_forge_cli_invocation(commit_approve),
                        "deny-approve" if pid_row else "no-match",
                    )
                if pid_row:
                    with (
                        mock.patch.object(module, "RAW_SEGMENT_PASS_ENABLED", False),
                        mock.patch.object(module, "_expansion_opener_at", side_effect=old_rule),
                    ):
                        self.assertEqual(module.find_actions(push), [])
                        self.assertEqual(
                            module.classify_forge_cli_invocation(merge_approve),
                            "no-match",
                        )
                        self.assertEqual(
                            module.classify_forge_cli_invocation(commit_approve),
                            "no-match",
                        )
                    with (
                        mock.patch.object(module, "RAW_SEGMENT_PASS_ENABLED", True),
                        mock.patch.object(module, "_expansion_opener_at", side_effect=old_rule),
                    ):
                        self.assertEqual(self.action_pairs(module, push), [("git", "push")])

    def test_span_skip_is_structured_only_and_defaults_stay_whole(self) -> None:
        module = load_guard_module(self, "forge_guard_span_skip_flag")
        command = "true $${; git push origin main; echo }"
        expected = [
            ("true $${", ";"),
            (" git push origin main", ";"),
            (" echo }", None),
        ]
        self.assertEqual(module.split_segments(command), expected)
        self.assertEqual(
            module._raw_segment_pass(lambda: module.split_segments(command)),
            expected,
        )
        self.assertEqual(module.split_segments(command), expected)
        for default in self.BRACE_SEPARATOR_DEFAULTS:
            command = "A=${X:-" + default + "} git commit -m x"
            with self.subTest(default=default):
                self.assertEqual(module.split_segments(command), [(command, None)])
                self.assertEqual(self.action_pairs(module, command), [("git", "commit")])
        default = "A=${X:-a;b} git commit -m x"
        self.assertEqual(
            module._raw_segment_pass(lambda: module.split_segments(default)),
            [("A=${X:-a", ";"), ("b} git commit -m x", None)],
        )

    def test_non_expansion_force_rows_match_committed_denied_row(self) -> None:
        repo = self.repository("forge-verbs-v1", None)
        reason = "force pushes require an operator-reviewed release path"
        (repo / "forge-project.md").write_text(
            "<!-- FORGE:REGION guard-denied-commands BEGIN -->\n"
            "| pattern | reason |\n"
            "|---|---|\n"
            f"| git push --force | {reason} |\n"
            "<!-- FORGE:REGION guard-denied-commands END -->\n",
            encoding="utf-8",
        )
        self.git(repo, "add", "forge-project.md")
        self.git(repo, "commit", "--quiet", "-m", "install command policy")
        for name, wrapper in self.NON_EXPANSION_WRAPPERS[:4]:
            command = wrapper.replace("{inner}", "git push --force origin main")
            with self.subTest(wrapper=name):
                result = self.invoke(repo, command)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(
                    json.loads(result.stdout),
                    denial(f"forge: operator-denied command — {reason}"),
                )
