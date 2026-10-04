from __future__ import annotations

import unittest
from unittest import mock

from tests._fresh_eval_support import POLICY, ROOT, policy_with_trigger_region, sha256

Rows = tuple[tuple[str, tuple[str, ...]], ...]

RELEASED_DIGESTS = (
    "3d1be7b789a8ee5cc7b5f65ac7f77a5ce3622fe0214a09650c85424c91147d93",
    "9ad0623e2eb7c9d56df44a0c57cb4c7c79e30e4322d9bbc0ea2e50b8817c3ce2",
    "45e2e69e0067f06f99cb0e3d42f185d3fdc8ee45f6961100eb51f3298c9500c3",
)
RELEASED_LENGTHS = (606, 606, 681)
PREVIOUS_RELEASED_CANONICAL_DIGEST = RELEASED_DIGESTS[-1]
CURRENT_DIGEST = "e347704d6b910b38c617b712c2eb14f0c4a512903c1a4cf3a72ecc30db629790"
CANONICAL_SUCCESSION_PIN = (
    "e347704d6b910b38c617b712c2eb14f0c4a512903c1a4cf3a72ecc30db629790"
)
UNRELEASED_DIGEST = "895486c4ef0392b704860dbfc3fe52fdf51583544e354d1375544c2e487bdea1"
UNRELEASED_TABLE = (
    "| control | path patterns |\n"
    "|---|---|\n"
    "| constitution | rules/** |\n"
    "| agent-prompt-template | agents/**, system/codex/prompts/**, "
    "system/claude/prompts/**, .claude/agents/** |\n"
    "| reviewer-routing | system/codex/agents/**, system/codex/config.toml, "
    ".codex/agents/**, .codex/config.toml, skills/orchestrate/SKILL.md, "
    "scripts/forge/forge_cli/engine/**, scripts/forge/forge_cli/app/**, "
    "scripts/forge/route_config.py, scripts/forge/route_config_git.py, "
    "scripts/forge/route_config_probe.py, scripts/forge/route_vocab.py, "
    "system/local/** |\n"
    "| execpolicy | system/codex/rules/**, .codex/rules/** |\n"
    "| model-provider-version | docs/specs/forge-plugin-spec.md, agents/**, "
    "system/codex/agents/**, .codex/agents/**, skills/orchestrate/SKILL.md, "
    "scripts/forge/forge_cli/engine/**, scripts/forge/route_config.py, "
    "scripts/forge/route_config_git.py, scripts/forge/route_config_probe.py, "
    "scripts/forge/route_vocab.py |\n"
    "| commit-review-prompt | skills/commit/SKILL.md |\n"
)


def _table_rows(body: str) -> Rows:
    result: list[tuple[str, tuple[str, ...]]] = []
    for line in body.splitlines()[2:]:
        cells = tuple(cell.strip() for cell in line.strip("|").split("|"))
        if len(cells) != 2:
            raise AssertionError("pinned reviewer-trigger table row is malformed")
        result.append(
            (cells[0], tuple(pattern.strip() for pattern in cells[1].split(",")))
        )
    return tuple(result)


def _expected_effective_rows(body: str) -> Rows:
    current_rows = _table_rows(POLICY.REVIEWER_EVAL_TRIGGER_TABLE)
    base_rows = dict(_table_rows(body))
    return tuple(
        (
            control,
            tuple(dict.fromkeys((*current_patterns, *base_rows[control]))),
        )
        for control, current_patterns in current_rows
    )


def _parsed_policy(body: str):
    raw = policy_with_trigger_region((ROOT / "forge-project.md").read_bytes(), body)
    return POLICY.parse_policy("a" * 40, raw)


class ReviewerTriggerHistoryTests(unittest.TestCase):
    def test_released_tables_have_exact_pinned_bodies_and_digests(self) -> None:
        released = POLICY.SUPERSEDED_REVIEWER_EVAL_TRIGGER_TABLES
        self.assertEqual(tuple(digest for digest, _body in released), RELEASED_DIGESTS)
        self.assertEqual(
            tuple(len(body.encode("utf-8")) for _digest, body in released),
            RELEASED_LENGTHS,
        )
        for digest, body in released:
            with self.subTest(digest=digest):
                self.assertEqual(sha256(body.encode("utf-8")), digest)

    def test_released_tables_use_exact_current_first_effective_rows(self) -> None:
        current_rows = dict(_table_rows(POLICY.REVIEWER_EVAL_TRIGGER_TABLE))
        expected_base_only = {
            RELEASED_DIGESTS[0]: {
                "reviewer-routing": ("scripts/forge/forge_cli/engine.py",),
                "model-provider-version": (
                    "scripts/forge/forge_cli/engine.py",
                ),
            },
            RELEASED_DIGESTS[1]: {},
            RELEASED_DIGESTS[2]: {},
        }
        for digest, body in POLICY.SUPERSEDED_REVIEWER_EVAL_TRIGGER_TABLES:
            with self.subTest(digest=digest):
                parsed = _parsed_policy(body)
                self.assertIsNone(parsed.reviewer_eval_trigger_error)
                self.assertEqual(
                    parsed.reviewer_eval_region_digest,
                    digest,
                )
                self.assertEqual(
                    parsed.reviewer_eval_triggers,
                    _expected_effective_rows(body),
                )
                base_only = {
                    control: patterns[len(current_rows[control]) :]
                    for control, patterns in parsed.reviewer_eval_triggers
                    if len(patterns) > len(current_rows[control])
                }
                self.assertEqual(base_only, expected_base_only[digest])

    def test_current_table_behavior_is_unchanged(self) -> None:
        parsed = _parsed_policy(POLICY.REVIEWER_EVAL_TRIGGER_TABLE)
        expected = _table_rows(POLICY.REVIEWER_EVAL_TRIGGER_TABLE)
        self.assertEqual(
            sha256(POLICY.REVIEWER_EVAL_TRIGGER_TABLE.encode()), CURRENT_DIGEST
        )
        self.assertEqual(
            POLICY._parse_reviewer_eval_triggers(
                POLICY.REVIEWER_EVAL_TRIGGER_TABLE
            ),
            expected,
        )
        self.assertEqual(parsed.reviewer_eval_triggers, expected)
        self.assertEqual(parsed.reviewer_eval_region_digest, CURRENT_DIGEST)
        self.assertIsNone(parsed.reviewer_eval_trigger_error)

    def test_unreleased_table_and_one_byte_edits_are_rejected(self) -> None:
        self.assertEqual(sha256(UNRELEASED_TABLE.encode("utf-8")), UNRELEASED_DIGEST)
        cases = [("unreleased", UNRELEASED_TABLE)]
        for digest, body in POLICY.SUPERSEDED_REVIEWER_EVAL_TRIGGER_TABLES:
            edited = "!" + body[1:]
            self.assertEqual(len(edited.encode("utf-8")), len(body.encode("utf-8")))
            self.assertEqual(
                sum(
                    left != right
                    for left, right in zip(body, edited, strict=True)
                ),
                1,
            )
            cases.append((f"one-byte-{digest}", edited))

        for label, body in cases:
            with self.subTest(label=label):
                parsed = _parsed_policy(body)
                self.assertEqual(parsed.reviewer_eval_triggers, ())
                self.assertEqual(
                    parsed.reviewer_eval_trigger_error,
                    "reviewer-facing-eval-triggers is malformed",
                )

    def test_previous_released_canonical_digest_is_admitted(self) -> None:
        admitted = {
            digest for digest, _body in POLICY.SUPERSEDED_REVIEWER_EVAL_TRIGGER_TABLES
        }
        self.assertIn(PREVIOUS_RELEASED_CANONICAL_DIGEST, admitted)
        self.assertNotIn(UNRELEASED_DIGEST, admitted)

    def test_canonical_successor_must_append_superseded_current_body(self) -> None:
        def assert_succession_recorded() -> None:
            current_digest = sha256(
                POLICY.REVIEWER_EVAL_TRIGGER_TABLE.encode("utf-8")
            )
            superseded = {
                digest
                for digest, _body in POLICY.SUPERSEDED_REVIEWER_EVAL_TRIGGER_TABLES
            }
            if current_digest == CANONICAL_SUCCESSION_PIN:
                self.assertNotIn(CANONICAL_SUCCESSION_PIN, superseded)
            else:
                self.assertIn(CANONICAL_SUCCESSION_PIN, superseded)

        current_body = POLICY.REVIEWER_EVAL_TRIGGER_TABLE
        successor = current_body.replace(
            "| commit-review-prompt | skills/commit/SKILL.md |",
            "| commit-review-prompt | skills/commit/SKILL.md, future/** |",
        )
        superseded = POLICY.SUPERSEDED_REVIEWER_EVAL_TRIGGER_TABLES
        self.assertNotEqual(successor, current_body)
        assert_succession_recorded()
        with mock.patch.object(
            POLICY, "REVIEWER_EVAL_TRIGGER_TABLE", successor
        ):
            with self.assertRaises(AssertionError):
                assert_succession_recorded()
            with mock.patch.object(
                POLICY,
                "SUPERSEDED_REVIEWER_EVAL_TRIGGER_TABLES",
                (*superseded, (CANONICAL_SUCCESSION_PIN, current_body)),
            ):
                assert_succession_recorded()

    def test_disabling_superseded_admission_rejects_released_tables(self) -> None:
        released = POLICY.SUPERSEDED_REVIEWER_EVAL_TRIGGER_TABLES

        def assert_released_tables_are_admitted() -> None:
            for _digest, body in released:
                self.assertIsNone(_parsed_policy(body).reviewer_eval_trigger_error)

        assert_released_tables_are_admitted()
        with mock.patch.object(
            POLICY, "SUPERSEDED_REVIEWER_EVAL_TRIGGER_TABLES", ()
        ), self.assertRaises(AssertionError):
            assert_released_tables_are_admitted()

    def test_disabling_union_loses_current_trigger_coverage(self) -> None:
        released = POLICY.SUPERSEDED_REVIEWER_EVAL_TRIGGER_TABLES

        def assert_exact_effective_rows() -> None:
            for _digest, body in released:
                self.assertEqual(
                    POLICY._parse_reviewer_eval_triggers(body),
                    _expected_effective_rows(body),
                )

        assert_exact_effective_rows()
        with mock.patch.object(
            POLICY,
            "_effective_reviewer_eval_trigger_rows",
            side_effect=_table_rows,
        ), self.assertRaises(AssertionError):
            assert_exact_effective_rows()


if __name__ == "__main__":
    unittest.main()
