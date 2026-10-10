"""FR-090 action discovery for bash-valid compound commands."""

import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.test_fr223_v2_hook import (
    DENIALS,
    HookHarnessMixin,
    denial,
    load_guard_module,
)

PUSH_COMMANDS = (
    "git push origin main",
    "case a in a) git push origin main;; esac",
    "case a in a) git push origin main; esac",
    "case a in a) git push origin main\nesac",
    "echo $(case a in (a) git push origin main;; esac)",
    "{ if case a in a) git push origin main;; esac; then :; fi; }",
    "if true; then git push origin main; fi",
    "while false; do git push origin main; done",
    "echo $(case a in a) git push origin main; esac; case b in (b) :;; esac)",
    "if true; then>/dev/null git push origin main; fi",
)
BASELINE_COMMAND_POSITION_TAIL = re.compile(
    r"\s*(?:(?:if|then|elif|else|while|until|do)\s+)*(?:(?:[({]|!|time|-p)\s*)*"
)


class CompoundActionTests(HookHarnessMixin, unittest.TestCase):
    def test_controls_and_inert_spellings(self) -> None:
        module = load_guard_module(self, "forge_guard_compound_controls")
        for command in PUSH_COMMANDS[:2]:
            with self.subTest(control=command):
                self.assertEqual(
                    [(a.executable, a.subcommand) for a in module.find_actions(command)],
                    [("git", "push")],
                )
        for command in (
            "echo if then git push",
            "case x in git) echo;; esac",
            "'then' git push origin main",
            r"\then git push origin main",
            "then\rgit push origin main",
        ):
            with self.subTest(inert=command):
                self.assertEqual(module.find_actions(command), [])

    def test_terminal_case_arms_require_case_end_scanner(self) -> None:
        module = load_guard_module(self, "forge_guard_terminal_case_arms")
        for command in PUSH_COMMANDS[2:4]:
            with self.subTest(command=command):
                self.assertEqual(
                    [(a.executable, a.subcommand) for a in module.find_actions(command)],
                    [("git", "push")],
                )
                # The baseline scanner returned None for these terminal arms.
                with mock.patch.object(module, "_matching_case_end", return_value=None):
                    self.assertEqual(module.find_actions(command), [])

    def test_parenthesized_case_pattern_requires_substitution_scanner(self) -> None:
        module = load_guard_module(self, "forge_guard_parenthesized_case_pattern")
        command = PUSH_COMMANDS[4]
        self.assertEqual(
            [(action.executable, action.subcommand) for action in module.find_actions(command)],
            [("git", "push")],
        )
        # The baseline scanner returned None after counting the pattern's '('.
        with mock.patch.object(
            module, "_matching_executable_parenthesis_body", return_value=None
        ):
            self.assertEqual(module.find_actions(command), [])

    def test_terminal_case_before_parenthesized_case_in_substitution(self) -> None:
        module = load_guard_module(self, "forge_guard_nested_terminal_case")
        command = PUSH_COMMANDS[8]
        self.assertEqual(
            [(action.executable, action.subcommand) for action in module.find_actions(command)],
            [("git", "push")],
        )
        # The baseline substitution scanner returned None for this combined shape.
        with mock.patch.object(
            module, "_matching_executable_parenthesis_body", return_value=None
        ):
            self.assertEqual(module.find_actions(command), [])

    def test_terminal_esac_releases_substitution_case_depth(self) -> None:
        module = load_guard_module(self, "forge_guard_terminal_esac_depth")
        command = "echo $(" + "; ".join("case a in a) :; esac" for _ in range(3)) + ")"
        original_start = module._reserved_word_start
        with mock.patch.object(module, "MAX_NESTING_DEPTH", 2):
            self.assertEqual(
                module._matching_executable_parenthesis_body(command, command.index("$(")),
                len(command) - 1,
            )
            # The baseline scanner ignored esac after a terminal arm.
            with mock.patch.object(
                module,
                "_reserved_word_start",
                side_effect=lambda value, index: not value.startswith("esac", index)
                and original_start(value, index),
            ):
                with self.assertRaises(module.GuardInputBoundExceeded):
                    module._matching_executable_parenthesis_body(
                        command, command.index("$(")
                    )

    def test_keyword_after_group_opener_requires_command_position(self) -> None:
        module = load_guard_module(self, "forge_guard_case_after_group_opener")
        command = PUSH_COMMANDS[5]
        self.assertEqual(
            [(action.executable, action.subcommand) for action in module.find_actions(command)],
            [("git", "push")],
        )
        with mock.patch.object(
            module, "COMMAND_POSITION_TAIL", BASELINE_COMMAND_POSITION_TAIL
        ):
            self.assertEqual(module.find_actions(command), [])

    def test_control_flow_bodies_require_reserved_word_strip(self) -> None:
        module = load_guard_module(self, "forge_guard_control_flow_bodies")
        for command in (*PUSH_COMMANDS[6:8], PUSH_COMMANDS[9]):
            with self.subTest(command=command):
                self.assertEqual(
                    [(a.executable, a.subcommand) for a in module.find_actions(command)],
                    [("git", "push")],
                )
                with mock.patch.object(module, "LEADING_CONTROL_FLOW_WORDS", re.compile(r"(?!)")):
                    self.assertEqual(module.find_actions(command), [])

    def test_reserved_word_boundaries_match_bash(self) -> None:
        module = load_guard_module(self, "forge_guard_reserved_word_boundaries")
        positives = (
            "if true; then>/dev/null git push origin main; fi",
            "while false; do>/dev/null git push origin main; done",
        )
        negatives = (
            "'then' git push origin main",
            r"\then git push origin main",
            "then\rgit push origin main",
        )
        for command in (*positives, *negatives):
            with self.subTest(command=command), tempfile.TemporaryDirectory() as scratch:
                marker = Path(scratch) / "git-actions"
                # Enter the unchanged while body once to prove its do-redirection syntax.
                bootstrap = (
                    "counter=0; false() { ((counter++ == 0)); }; "
                    if command.startswith("while false;") else ""
                )
                script = (
                    "git() { printf '%s\\n' \"$*\" >> \"$MARKER\"; }; "
                    + bootstrap + command
                )
                probe = subprocess.run(
                    ["bash", "-c", script],
                    env={"MARKER": str(marker)},
                    capture_output=True,
                    text=True,
                    check=False,
                )
                expected_push = command in positives
                self.assertEqual(probe.returncode, 0 if expected_push else 127, probe.stderr)
                self.assertEqual(
                    marker.read_text() if marker.exists() else "",
                    "push origin main\n" if expected_push else "",
                )
                expected_actions = [("git", "push")] if expected_push else []
                self.assertEqual(
                    [(a.executable, a.subcommand) for a in module.find_actions(command)],
                    expected_actions,
                )
                with mock.patch.object(module, "LEADING_CONTROL_FLOW_WORDS", re.compile(r"(?!)")):
                    self.assertEqual(module.find_actions(command), [])

    def test_compound_git_push_reaches_raw_push_denial(self) -> None:
        repo = self.repository("forge-verbs-v1", None)
        for command in PUSH_COMMANDS:
            with self.subTest(command=command):
                result = self.invoke(repo, command)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout), denial(DENIALS["deny-raw-push"]))
