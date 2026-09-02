"""Engine policy reader: indented fenced shell cells and global-option help (GH#12)."""

from __future__ import annotations

import importlib.util
import io
import sys
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
CLI_PATH = ROOT / "scripts/forge/cli.py"


def load_script(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


CLI = load_script("forge_cli_policy_fence_tests", CLI_PATH)

FLAT_CELL = 'python3 -m unittest discover -s tests\n# blast radius\npython3 -m unittest tests.test_repo_conformance "$@"'

POLICY_TEMPLATE = """\
<!-- FORGE:REGION project-overview BEGIN -->
Fence fixture.
<!-- FORGE:REGION project-overview END -->
<!-- FORGE:REGION file-categories BEGIN -->
| Category | File patterns |
|---|---|
| python | `*.py` |
<!-- FORGE:REGION file-categories END -->
<!-- FORGE:REGION stack-validations BEGIN -->
{stack}
<!-- FORGE:REGION stack-validations END -->
<!-- FORGE:REGION gate1-test-command BEGIN -->
{gate1}
<!-- FORGE:REGION gate1-test-command END -->
<!-- FORGE:REGION changelog-policy BEGIN -->
No changelog gate is configured for this repository.
<!-- FORGE:REGION changelog-policy END -->
<!-- FORGE:REGION review-prompt-project-focus BEGIN -->
Review the exact staged bytes.
<!-- FORGE:REGION review-prompt-project-focus END -->
<!-- FORGE:REGION project-triggers BEGIN -->
No extra triggers.
<!-- FORGE:REGION project-triggers END -->
<!-- FORGE:REGION completeness-project-items BEGIN -->
- [ ] Focused tests pass.
<!-- FORGE:REGION completeness-project-items END -->
<!-- FORGE:REGION agent-project-context BEGIN -->
Fixture only.
<!-- FORGE:REGION agent-project-context END -->
<!-- FORGE:REGION mutation-testing BEGIN -->
Assertion-quality fallback.
<!-- FORGE:REGION mutation-testing END -->
<!-- FORGE:REGION invariants BEGIN -->
| invariant | check command | enforcement point |
|---|---|---|
<!-- FORGE:REGION invariants END -->
<!-- FORGE:REGION risk-tiers BEGIN -->
Fixture risk rules.
<!-- FORGE:REGION risk-tiers END -->
<!-- FORGE:REGION drift-config BEGIN -->
cadence: 14d
<!-- FORGE:REGION drift-config END -->
<!-- FORGE:REGION trigger-paths BEGIN -->
| Path pattern |
|---|
<!-- FORGE:REGION trigger-paths END -->
"""

FLAT_GATE1 = "```bash\n" + FLAT_CELL + "\n```"
# The shape /forge:init 0.6.x produced for the GH#12 reporter: the fence
# nested under a Markdown list item, comment lines included.
NESTED_GATE1 = (
    "- Targeted tests plus the always-run blast-radius suite:\n\n"
    "  ```bash\n"
    "  python3 -m unittest discover -s tests\n"
    "  # blast radius\n"
    '  python3 -m unittest tests.test_repo_conformance "$@"\n'
    "  ```"
)
FLAT_STACK = "```bash\ntrue\n```"


def policy(gate1: str, stack: str = FLAT_STACK) -> bytes:
    return POLICY_TEMPLATE.format(gate1=gate1, stack=stack).encode("utf-8")


class FencedShellCellTests(unittest.TestCase):
    def test_flat_fence_is_unchanged(self) -> None:
        self.assertEqual(CLI._fenced_shell_cells(FLAT_GATE1), [FLAT_CELL])

    def test_uniformly_indented_fence_yields_flat_bytes(self) -> None:
        self.assertEqual(CLI._fenced_shell_cells(NESTED_GATE1), [FLAT_CELL])

    def test_tab_indented_fence_yields_flat_bytes(self) -> None:
        body = "\t```sh\n\techo one\n\n\techo two\n\t```\n"
        self.assertEqual(CLI._fenced_shell_cells(body), ["echo one\n\necho two"])

    def test_flat_crlf_fence_closes(self) -> None:
        body = "```bash\r\necho one\r\n```\r\n"
        self.assertEqual(CLI._fenced_shell_cells(body), ["echo one"])

    def test_indented_crlf_fence_preserves_line_endings(self) -> None:
        body = "  ```bash\r\n  echo one\r\n\r\n  echo two\r\n  ```\r\n"
        self.assertEqual(CLI._fenced_shell_cells(body), ["echo one\r\n\r\necho two"])

    def test_blank_line_inside_indented_cell_may_carry_indent(self) -> None:
        body = "  ```bash\n  echo one\n  \n  echo two\n  ```\n"
        self.assertEqual(CLI._fenced_shell_cells(body), ["echo one\n\necho two"])

    def test_misaligned_line_is_malformed(self) -> None:
        body = "  ```bash\n  echo one\n echo two\n  ```\n"
        with self.assertRaises(CLI.PolicyError) as caught:
            CLI._fenced_shell_cells(body)
        self.assertEqual(str(caught.exception), "forge: executable policy row malformed")

    def test_mixed_indent_character_is_malformed(self) -> None:
        body = "  ```bash\n\techo one\n  ```\n"
        with self.assertRaises(CLI.PolicyError) as caught:
            CLI._fenced_shell_cells(body)
        self.assertEqual(str(caught.exception), "forge: executable policy row malformed")

    def test_closing_fence_must_match_opening_indent(self) -> None:
        # A closing fence at a different column does not close the cell.
        body = "  ```bash\n  echo one\n```\n"
        self.assertEqual(CLI._fenced_shell_cells(body), [])

    def test_deeper_indented_cell_lines_keep_relative_indent(self) -> None:
        body = "  ```bash\n  if true; then\n    echo nested\n  fi\n  ```\n"
        self.assertEqual(
            CLI._fenced_shell_cells(body), ["if true; then\n  echo nested\nfi"]
        )

    def test_empty_indented_cell_is_malformed(self) -> None:
        with self.assertRaises(CLI.PolicyError):
            CLI._fenced_shell_cells("  ```bash\n  \n  ```\n")

    def test_nul_inside_indented_cell_is_malformed(self) -> None:
        with self.assertRaises(CLI.PolicyError):
            CLI._fenced_shell_cells("  ```bash\n  echo \x00\n  ```\n")

    def test_unclosed_opening_is_skipped_and_later_cell_parses(self) -> None:
        body = "  ```bash\n  echo a\n```bash\necho b\n```\n"
        self.assertEqual(CLI._fenced_shell_cells(body), ["echo b"])

    def test_first_matching_close_ends_the_cell(self) -> None:
        # A closing fence at another column, or a later opening fence, is cell
        # text until the first closing fence at the opening fence's column.
        body = "```bash\necho a\n  ```\n```sh\necho b\n```\n"
        self.assertEqual(
            CLI._fenced_shell_cells(body), ["echo a\n  ```\n```sh\necho b"]
        )

    def test_hostile_unclosed_openings_parse_in_bounded_time(self) -> None:
        # Regression for the quadratic worst case of the former lazy-DOTALL
        # regex: tens of thousands of indented openings that never close.
        hostile = "  ```bash\n  a\n" * 24000
        started = time.monotonic()
        self.assertEqual(CLI._fenced_shell_cells(hostile), [])
        self.assertEqual(CLI._fenced_shell_cells("```bash\n" * 20000), [])
        self.assertLess(time.monotonic() - started, 5.0)

    def test_closing_index_control_disabled_in_memory_closes_at_wrong_column(self) -> None:
        # Proof that the per-prefix closing index is the control: with every
        # closing fence filed under the opening prefix, a mismatched-column
        # closing fence wrongly closes the cell.
        real = CLI._fence_lines

        def lenient(lines: list[str]):
            openings, closings = real(lines)
            merged = sorted(index for indexes in closings.values() for index in indexes)
            return openings, {prefix: list(merged) for _index, prefix in openings}

        body = "  ```bash\n  echo one\n```\n"
        with mock.patch.object(CLI, "_fence_lines", lenient):
            self.assertEqual(CLI._fenced_shell_cells(body), ["echo one"])
        self.assertEqual(CLI._fenced_shell_cells(body), [])


class ParsePolicyTests(unittest.TestCase):
    def test_nested_gate1_parses_identically_to_flat(self) -> None:
        flat = CLI.parse_policy("a" * 40, policy(FLAT_GATE1))
        nested = CLI.parse_policy("b" * 40, policy(NESTED_GATE1))
        self.assertEqual(flat.gate1, FLAT_CELL)
        self.assertEqual(nested.gate1, flat.gate1)
        self.assertEqual(nested.stack_commands, flat.stack_commands)

    def test_nested_stack_validation_cells_parse(self) -> None:
        stack = "- python:\n\n  ```bash\n  python3 -m compileall -q .\n  ```\n- shell:\n\n  ```sh\n  true\n  ```"
        parsed = CLI.parse_policy("c" * 40, policy(FLAT_GATE1, stack))
        self.assertEqual(parsed.stack_commands, ["python3 -m compileall -q .", "true"])

    def test_misaligned_gate1_is_policy_error(self) -> None:
        gate1 = "  ```bash\n  echo one\n echo two\n  ```"
        with self.assertRaises(CLI.PolicyError) as caught:
            CLI.parse_policy("d" * 40, policy(gate1))
        self.assertEqual(str(caught.exception), "forge: executable policy row malformed")

    def test_two_gate1_cells_still_refused(self) -> None:
        gate1 = "  ```bash\n  true\n  ```\n\n```bash\ntrue\n```"
        with self.assertRaises(CLI.PolicyError) as caught:
            CLI.parse_policy("e" * 40, policy(gate1))
        self.assertEqual(
            str(caught.exception), "gate1-test-command must contain exactly one shell cell"
        )

    def test_dedent_control_disabled_in_memory_breaks_equivalence(self) -> None:
        # Proof that the dedent helper is the control: with it neutralised the
        # nested cell no longer equals the flat cell, so a regression that
        # short-circuits the helper cannot pass the equivalence test above.
        with mock.patch.object(CLI, "_dedent_fenced_cell", lambda cell, prefix: cell):
            nested = CLI.parse_policy("f" * 40, policy(NESTED_GATE1))
        self.assertNotEqual(nested.gate1, FLAT_CELL)
        self.assertTrue(nested.gate1.startswith("  "))


class HelpTextTests(unittest.TestCase):
    def _help(self, argv: list[str]) -> str:
        buffer = io.StringIO()
        with redirect_stdout(buffer), self.assertRaises(SystemExit) as exited:
            CLI.build_parser().parse_args(argv)
        self.assertEqual(exited.exception.code, 0)
        return buffer.getvalue()

    def test_top_level_help_names_global_options(self) -> None:
        text = self._help(["--help"])
        for option in ("--repo", "--run-id", "--chain-id", "--json", "--verbose"):
            self.assertIn(option, text)
        # --task is a verb option, never a pre-argparse global; the help must
        # say so rather than list it among the globals.
        self.assertIn("--task TASK_ID is not global", text)
        globals_block = text.partition("global options")[2].partition("--task")[0]
        self.assertNotIn("--task", globals_block)

    def test_task_before_the_verb_is_refused(self) -> None:
        _options, remaining = CLI._extract_global_options(
            ["--task", "task-01", "commit", "start", "--paths", "a"]
        )
        self.assertEqual(remaining[:2], ["--task", "task-01"])
        with self.assertRaises(CLI.Refusal):
            CLI.build_parser().parse_args(remaining)

    def test_commit_start_help_names_run_binding(self) -> None:
        text = self._help(["commit", "start", "--help"])
        self.assertIn("--run-id", text)
        self.assertIn("requires --task", text)

    def test_help_epilog_does_not_change_option_parsing(self) -> None:
        options, remaining = CLI._extract_global_options(
            ["--run-id", "run-1", "commit", "start", "--paths", "a", "--task", "task-01"]
        )
        self.assertEqual(options.run_id, "run-1")
        self.assertEqual(remaining, ["commit", "start", "--paths", "a", "--task", "task-01"])


if __name__ == "__main__":
    unittest.main()
