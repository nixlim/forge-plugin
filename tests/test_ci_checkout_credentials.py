from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKOUT_USE = re.compile(r"^(?P<indent> *)(?:-\s+)?uses:\s+actions/checkout@")
LIST_ITEM = re.compile(r"^(?P<indent> *)-(?:\s+|$)")
PERSIST_FALSE = "persist-credentials: false"


def _checkout_step_lines(text: str) -> list[int]:
    return [
        line_number
        for line_number, line in enumerate(text.splitlines(), start=1)
        if CHECKOUT_USE.match(line)
    ]


def _step_bounds(lines: list[str], use_index: int, use_indent: int) -> tuple[int, int, int]:
    inline_item = LIST_ITEM.match(lines[use_index])
    if inline_item is not None:
        start = use_index
        step_indent = len(inline_item.group("indent"))
    else:
        start = use_index
        step_indent = use_indent
        for candidate_index in range(use_index - 1, -1, -1):
            item = LIST_ITEM.match(lines[candidate_index])
            if item is not None and len(item.group("indent")) < use_indent:
                start = candidate_index
                step_indent = len(item.group("indent"))
                break
    end = len(lines)
    for candidate_index in range(start + 1, len(lines)):
        item = LIST_ITEM.match(lines[candidate_index])
        if item is not None and len(item.group("indent")) <= step_indent:
            end = candidate_index
            break
    return start, end, step_indent


def checkout_steps_without_persist_false(text: str) -> list[int]:
    lines = text.splitlines()
    missing = []
    for index, line in enumerate(lines):
        checkout = CHECKOUT_USE.match(line)
        if checkout is None:
            continue
        start, end, step_indent = _step_bounds(
            lines,
            index,
            len(checkout.group("indent")),
        )
        protected = False
        for candidate in lines[start:end]:
            candidate_indent = len(candidate) - len(candidate.lstrip(" "))
            if candidate_indent > step_indent and candidate.strip() == PERSIST_FALSE:
                protected = True
        if not protected:
            missing.append(index + 1)
    return missing


class CheckoutCredentialTests(unittest.TestCase):
    def test_every_checkout_disables_persisted_credentials(self) -> None:
        workflows = sorted((ROOT / ".github/workflows").glob("*.yml"))
        self.assertGreaterEqual(len(workflows), 2)
        for workflow in workflows:
            with self.subTest(workflow=workflow.name):
                text = workflow.read_text(encoding="utf-8")
                checkout_lines = _checkout_step_lines(text)
                self.assertGreaterEqual(len(checkout_lines), 1)
                self.assertEqual(checkout_steps_without_persist_false(text), [])

                mutant_lines = [
                    line
                    for line in text.splitlines(keepends=True)
                    if line.strip() != PERSIST_FALSE
                ]
                mutant = "".join(mutant_lines)
                self.assertNotEqual(mutant, text)
                self.assertEqual(
                    checkout_steps_without_persist_false(mutant),
                    _checkout_step_lines(mutant),
                )

    def test_named_checkout_step_is_detected(self) -> None:
        text = (
            "steps:\n"
            "  - name: Checkout\n"
            "    uses: actions/checkout@example\n"
            "    with:\n"
            "      persist-credentials: false\n"
        )
        self.assertEqual(checkout_steps_without_persist_false(text), [])
        mutant = text.replace("      persist-credentials: false\n", "", 1)
        self.assertEqual(checkout_steps_without_persist_false(mutant), [3])

    def test_bare_step_boundary_does_not_borrow_later_protection(self) -> None:
        text = (
            "steps:\n"
            "  -\n"
            "    uses: actions/checkout@example\n"
            "  -\n"
            "    env:\n"
            "      persist-credentials: false\n"
        )
        self.assertEqual(checkout_steps_without_persist_false(text), [3])


if __name__ == "__main__":
    unittest.main()
