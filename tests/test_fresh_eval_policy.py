from __future__ import annotations

import dataclasses
import unittest
from unittest import mock

from tests._fresh_eval_support import (
    FRESH,
    POLICY,
    ROOT,
    TRIGGER_ROWS,
    TRIGGER_TABLE,
    FreshEvalRepo,
    policy_with_trigger_region,
    sha256,
    trigger_table,
)


STACK_FENCE_ERROR = (
    "forge: stack-validations region present but contains no fenced shell cell — "
    "write one fenced ```bash or ```sh cell per stack category (see /forge:init)"
)


def policy_with_stack_region(raw: bytes, body: bytes) -> bytes:
    begin = b"<!-- FORGE:REGION stack-validations BEGIN -->\n"
    end = b"<!-- FORGE:REGION stack-validations END -->"
    before, remainder = raw.split(begin, 1)
    _old_body, after = remainder.split(end, 1)
    return before + begin + body + end + after


class ReviewerEvalTriggerGrammarTests(unittest.TestCase):
    def test_exact_closed_table_parses_in_normative_order(self) -> None:
        self.assertEqual(
            POLICY._parse_reviewer_eval_triggers(TRIGGER_TABLE), TRIGGER_ROWS
        )

    def test_well_formed_narrowing_is_rejected_by_the_canonical_byte_pin(self) -> None:
        narrowed = TRIGGER_TABLE.replace("| constitution | rules/** |", "| constitution | rules/never/** |")

        def assert_narrowing_is_rejected() -> None:
            with self.assertRaises(POLICY.PolicyError) as caught:
                POLICY._parse_reviewer_eval_triggers(narrowed)
            self.assertEqual(
                str(caught.exception),
                "reviewer-facing-eval-triggers is malformed",
            )

        assert_narrowing_is_rejected()
        with mock.patch.object(
            POLICY, "REVIEWER_EVAL_TRIGGER_TABLE", narrowed
        ), self.assertRaises(AssertionError):
            assert_narrowing_is_rejected()

    def test_malformed_tables_are_rejected_without_partial_defaults(self) -> None:
        malformed = {
            "missing-row": trigger_table(TRIGGER_ROWS[:-1]),
            "reordered-row": trigger_table(
                (TRIGGER_ROWS[1], TRIGGER_ROWS[0], *TRIGGER_ROWS[2:])
            ),
            "unknown-control": TRIGGER_TABLE.replace(
                "| constitution |", "| unknown |", 1
            ),
            "duplicate-pattern": TRIGGER_TABLE.replace(
                "| constitution | rules/** |",
                "| constitution | rules/**, rules/** |",
            ),
            "empty-cell": TRIGGER_TABLE.replace(
                "| constitution | rules/** |", "| constitution | |"
            ),
            "empty-pattern": TRIGGER_TABLE.replace(
                "| constitution | rules/** |", "| constitution | rules/**, |"
            ),
            "negative-bang": TRIGGER_TABLE.replace("rules/**", "!rules/**", 1),
            "negative-caret": TRIGGER_TABLE.replace("rules/**", "^rules/**", 1),
            "pathspec-magic": TRIGGER_TABLE.replace(
                "rules/**", ":(glob)rules/**", 1
            ),
            "absolute": TRIGGER_TABLE.replace("rules/**", "/rules/**", 1),
            "parent": TRIGGER_TABLE.replace("rules/**", "rules/../**", 1),
            "empty-component": TRIGGER_TABLE.replace("rules/**", "rules//**", 1),
            "crlf": TRIGGER_TABLE.replace("\n", "\r\n"),
            "extra-prose": TRIGGER_TABLE + "defaults are allowed\n",
            "multiple-table": TRIGGER_TABLE + TRIGGER_TABLE,
        }
        for label, body in malformed.items():
            with self.subTest(label=label):
                with self.assertRaises(POLICY.PolicyError) as caught:
                    POLICY._parse_reviewer_eval_triggers(body)
                self.assertEqual(
                    str(caught.exception),
                    "reviewer-facing-eval-triggers is malformed",
                )

    def test_policy_retains_authenticated_region_digest_and_fail_closed_error(self) -> None:
        base = (ROOT / "forge-project.md").read_bytes()
        good_raw = policy_with_trigger_region(base)
        good = POLICY.parse_policy("a" * 40, good_raw)
        self.assertEqual(good.reviewer_eval_triggers, TRIGGER_ROWS)
        self.assertEqual(
            good.reviewer_eval_region_digest, sha256(TRIGGER_TABLE.encode("utf-8"))
        )
        self.assertIsNone(good.reviewer_eval_trigger_error)

        bad_raw = policy_with_trigger_region(
            base, TRIGGER_TABLE.replace("| constitution |", "| surprise |", 1)
        )
        bad = POLICY.parse_policy("a" * 40, bad_raw)
        self.assertEqual(bad.reviewer_eval_triggers, ())
        self.assertEqual(
            bad.reviewer_eval_trigger_error,
            "reviewer-facing-eval-triggers is malformed",
        )

        begin = b"<!-- FORGE:REGION reviewer-facing-eval-triggers BEGIN -->\n"
        end = b"<!-- FORGE:REGION reviewer-facing-eval-triggers END -->\n"
        before, remainder = good_raw.split(begin, 1)
        _body, after = remainder.split(end, 1)
        legacy = POLICY.parse_policy("a" * 40, before + after)
        self.assertEqual(legacy.reviewer_eval_triggers, ())
        self.assertIsNone(legacy.reviewer_eval_region_digest)
        self.assertEqual(
            legacy.reviewer_eval_trigger_error,
            "authenticated reviewer-facing-eval-triggers region is missing",
        )

    def test_trigger_region_structural_defects_are_carried_fail_closed(self) -> None:
        good_raw = policy_with_trigger_region((ROOT / "forge-project.md").read_bytes())
        good = POLICY.parse_policy("a" * 40, good_raw)
        begin = b"<!-- FORGE:REGION reviewer-facing-eval-triggers BEGIN -->\n"
        end = b"<!-- FORGE:REGION reviewer-facing-eval-triggers END -->\n"
        before, remainder = good_raw.split(begin, 1)
        body, after = remainder.split(end, 1)
        region = begin + body + end
        without_region = before + after
        trigger_paths_begin = b"<!-- FORGE:REGION trigger-paths BEGIN -->\n"
        malformed = {
            "duplicate": good_raw + b"\n" + region,
            "nested": good_raw.replace(begin, begin + begin, 1),
            "mismatched": good_raw.replace(
                end,
                b"<!-- FORGE:REGION reviewer-facing-eval-trigger END -->\n",
                1,
            ),
            "misordered": without_region.replace(
                trigger_paths_begin, region + trigger_paths_begin, 1
            ),
        }

        for label, raw in malformed.items():
            with self.subTest(label=label):
                parsed = POLICY.parse_policy("a" * 40, raw)
                self.assertEqual(parsed.raw, raw)
                self.assertEqual(parsed.digest, sha256(raw))
                self.assertEqual(parsed.gate1, good.gate1)
                self.assertEqual(parsed.stack_commands, good.stack_commands)
                self.assertEqual(parsed.invariants, good.invariants)
                self.assertEqual(parsed.changelog, good.changelog)
                self.assertEqual(parsed.reviewer_eval_triggers, ())
                self.assertIsNone(parsed.reviewer_eval_region_digest)
                self.assertEqual(
                    parsed.reviewer_eval_trigger_error,
                    "reviewer-facing-eval-triggers is malformed",
                )

    def test_trigger_recovery_never_hides_an_unrelated_region_defect(self) -> None:
        good_raw = policy_with_trigger_region((ROOT / "forge-project.md").read_bytes())
        begin = b"<!-- FORGE:REGION reviewer-facing-eval-triggers BEGIN -->\n"
        duplicate_legacy = (
            b"<!-- FORGE:REGION project-overview BEGIN -->\n"
            b"duplicate\n"
            b"<!-- FORGE:REGION project-overview END -->\n"
        )
        cases = {
            "legacy-only": (
                good_raw + duplicate_legacy,
                "duplicate Forge region: project-overview",
            ),
            "combined": (
                good_raw.replace(begin, begin + begin, 1) + duplicate_legacy,
                "nested Forge region marker",
            ),
            "foreign-region-inside-trigger": (
                good_raw.replace(begin, begin + duplicate_legacy, 1),
                "nested Forge region marker",
            ),
        }
        for label, (raw, expected_error) in cases.items():
            with self.subTest(label=label):
                with self.assertRaises(POLICY.PolicyError) as caught:
                    POLICY.parse_policy("a" * 40, raw)
                self.assertEqual(
                    str(caught.exception),
                    expected_error,
                )

    def test_disabling_trigger_structure_recovery_restores_policy_unreadable(self) -> None:
        good_raw = policy_with_trigger_region((ROOT / "forge-project.md").read_bytes())
        begin = b"<!-- FORGE:REGION reviewer-facing-eval-triggers BEGIN -->\n"
        malformed = good_raw.replace(begin, begin + begin, 1)

        def strict_only(raw: bytes):
            return POLICY._parse_regions(raw), None

        with mock.patch.object(
            POLICY, "_parse_regions_with_trigger_defect", strict_only
        ), self.assertRaises(POLICY.PolicyError):
            POLICY.parse_policy("a" * 40, malformed)

    def test_authenticated_stack_fence_reparse_preserves_fresh_error_reason(self) -> None:
        with FreshEvalRepo() as repository:
            malformed_raw = policy_with_stack_region(
                repository.policy.raw,
                b"1. Python tests: `python3 -m unittest`\n",
            )
            repository.write("forge-project.md", malformed_raw)
            repository.git("add", "--", "forge-project.md")
            repository.git("commit", "-qm", "malformed stack validation policy")
            repository.stage_append("rules/review-constitution.md")
            snapshot = repository.snapshot()
            malformed_policy = dataclasses.replace(
                repository.policy,
                sha=str(snapshot.base_commit_oid),
                raw=malformed_raw,
                digest=sha256(malformed_raw),
            )

            with self.assertRaises(FRESH.FreshEvalError) as caught:
                FRESH.derive_trigger(
                    repository.context,
                    malformed_policy,
                    snapshot.state_record(),
                    snapshot.paths,
                )

        self.assertEqual(caught.exception.reason, STACK_FENCE_ERROR)
        self.assertEqual(
            str(caught.exception),
            "forge: fresh reviewer eval evidence invalid: " + STACK_FENCE_ERROR,
        )


class ReviewerEvalTriggerDerivationTests(unittest.TestCase):
    def test_every_normative_pattern_matches_only_exact_tree_pair_paths(self) -> None:
        paths = (
            ".claude/agents/fresh.md",
            ".codex/agents/fresh.toml",
            ".codex/config.toml",
            ".codex/rules/fresh.rules",
            "agents/fresh.md",
            "docs/specs/forge-plugin-spec.md",
            "rules/fresh.md",
            "scripts/forge/forge_cli/engine.py",
            "skills/commit/SKILL.md",
            "skills/orchestrate/SKILL.md",
            "system/codex/agents/fresh.toml",
            "system/codex/config.toml",
            "system/codex/prompts/fresh.md",
            "system/codex/rules/fresh.rules",
        )
        with FreshEvalRepo() as repository:
            repository.stage_many(paths)
            snapshot = repository.snapshot()

            trigger = FRESH.derive_trigger(
                repository.context,
                repository.policy,
                snapshot.state_record(),
                snapshot.paths,
            )

        self.assertEqual(snapshot.paths, tuple(sorted(paths, key=str.encode)))
        expected = [
            ("constitution", "rules/**", "rules/fresh.md"),
            ("agent-prompt-template", ".claude/agents/**", ".claude/agents/fresh.md"),
            ("agent-prompt-template", "agents/**", "agents/fresh.md"),
            (
                "agent-prompt-template",
                "system/codex/prompts/**",
                "system/codex/prompts/fresh.md",
            ),
            ("reviewer-routing", ".codex/agents/**", ".codex/agents/fresh.toml"),
            ("reviewer-routing", ".codex/config.toml", ".codex/config.toml"),
            (
                "reviewer-routing",
                "scripts/forge/forge_cli/engine.py",
                "scripts/forge/forge_cli/engine.py",
            ),
            (
                "reviewer-routing",
                "skills/orchestrate/SKILL.md",
                "skills/orchestrate/SKILL.md",
            ),
            (
                "reviewer-routing",
                "system/codex/agents/**",
                "system/codex/agents/fresh.toml",
            ),
            (
                "reviewer-routing",
                "system/codex/config.toml",
                "system/codex/config.toml",
            ),
            ("execpolicy", ".codex/rules/**", ".codex/rules/fresh.rules"),
            (
                "execpolicy",
                "system/codex/rules/**",
                "system/codex/rules/fresh.rules",
            ),
            ("model-provider-version", ".codex/agents/**", ".codex/agents/fresh.toml"),
            ("model-provider-version", "agents/**", "agents/fresh.md"),
            (
                "model-provider-version",
                "docs/specs/forge-plugin-spec.md",
                "docs/specs/forge-plugin-spec.md",
            ),
            (
                "model-provider-version",
                "scripts/forge/forge_cli/engine.py",
                "scripts/forge/forge_cli/engine.py",
            ),
            (
                "model-provider-version",
                "skills/orchestrate/SKILL.md",
                "skills/orchestrate/SKILL.md",
            ),
            (
                "model-provider-version",
                "system/codex/agents/**",
                "system/codex/agents/fresh.toml",
            ),
            (
                "commit-review-prompt",
                "skills/commit/SKILL.md",
                "skills/commit/SKILL.md",
            ),
        ]
        expected_records = [
            {"control": control, "pattern": pattern, "path": path}
            for control, pattern, path in sorted(
                expected,
                key=lambda item: tuple(part.encode("utf-8") for part in item),
            )
        ]
        self.assertEqual(trigger["matches"], expected_records)
        self.assertEqual(trigger["paths"], list(snapshot.paths))

    def test_base_policy_is_pinned_and_candidate_policy_cannot_remove_trigger(self) -> None:
        with FreshEvalRepo() as repository:
            repository.write("forge-project.md", b"candidate attempts to remove policy\n")
            repository.git("add", "forge-project.md")
            repository.stage_append("rules/review-constitution.md")
            snapshot = repository.snapshot()

            trigger = FRESH.derive_trigger(
                repository.context,
                repository.policy,
                snapshot.state_record(),
                snapshot.paths,
            )

        self.assertEqual(trigger["policy_sha"], snapshot.base_commit_oid)
        self.assertIn(
            {
                "control": "constitution",
                "pattern": "rules/**",
                "path": "rules/review-constitution.md",
            },
            trigger["matches"],
        )

    def test_spoofed_path_list_stale_policy_and_malformed_policy_fail_closed(self) -> None:
        with FreshEvalRepo() as repository:
            repository.stage_append("rules/review-constitution.md")
            snapshot = repository.snapshot()
            cases = (
                (
                    repository.policy,
                    ("README.md",),
                    "candidate staged path list differs from the tree pair",
                ),
                (
                    dataclasses.replace(repository.policy, sha="f" * 40),
                    snapshot.paths,
                    "authenticated trigger policy does not bind the candidate base",
                ),
                (
                    dataclasses.replace(
                        repository.policy,
                        reviewer_eval_trigger_error="authenticated trigger table malformed",
                    ),
                    snapshot.paths,
                    "authenticated trigger table malformed",
                ),
            )
            for policy, paths, diagnostic in cases:
                with self.subTest(diagnostic=diagnostic):
                    with self.assertRaises(FRESH.FreshEvalError) as caught:
                        FRESH.derive_trigger(
                            repository.context,
                            policy,
                            snapshot.state_record(),
                            paths,
                        )
                    self.assertEqual(caught.exception.reason, diagnostic)

    def test_delete_side_of_rename_still_triggers(self) -> None:
        with FreshEvalRepo() as repository:
            repository.git(
                "mv", "rules/rename-source.md", "rename-destination.md"
            )
            snapshot = repository.snapshot()
            trigger = FRESH.derive_trigger(
                repository.context,
                repository.policy,
                snapshot.state_record(),
                snapshot.paths,
            )

        self.assertEqual(
            snapshot.paths, ("rename-destination.md", "rules/rename-source.md")
        )
        self.assertEqual(
            trigger["matches"],
            [
                {
                    "control": "constitution",
                    "pattern": "rules/**",
                    "path": "rules/rename-source.md",
                }
            ],
        )

    def test_nonmatching_exact_candidate_is_not_triggered(self) -> None:
        with FreshEvalRepo() as repository:
            repository.stage_append("README.md")
            snapshot = repository.snapshot()
            trigger = FRESH.derive_trigger(
                repository.context,
                repository.policy,
                snapshot.state_record(),
                snapshot.paths,
            )
        self.assertEqual(trigger["matches"], [])
        self.assertFalse(FRESH.trigger_required(trigger))

    def test_first_policy_bootstrap_fails_closed_without_fixed_coordinator(self) -> None:
        with FreshEvalRepo() as repository:
            repository.stage_append("README.md")
            snapshot = repository.snapshot()
            unavailable = dataclasses.replace(
                repository.policy,
                sha="f" * 40,
                reviewer_eval_triggers=(),
                reviewer_eval_region_digest=None,
                reviewer_eval_trigger_error="base trigger source unavailable",
            )
            with self.assertRaises(FRESH.FreshEvalError) as caught:
                FRESH.derive_trigger(
                    repository.context,
                    unavailable,
                    snapshot.state_record(),
                    snapshot.paths,
                    bootstrap=True,
                )
        self.assertEqual(
            caught.exception.reason,
            "fixed first-policy fresh-evaluation coordinator is unavailable",
        )


if __name__ == "__main__":
    unittest.main()
