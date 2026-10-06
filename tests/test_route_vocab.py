"""Contract tests for the shared route-vocabulary readers."""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "forge"))

import route_config  # noqa: E402
import route_evidence  # noqa: E402
import route_vocab  # noqa: E402

MODEL_ID_PROBES = ("fable", "claude-fable-5-1[1m]", "m" * 128, "m" * 129, "model name", "-model")


def model_id_grammar_forks() -> list[tuple[str, str]]:
    """Name each route surface whose model-id verdict differs from route_vocab.MODEL_ID_RE."""

    pinned = re.compile(route_vocab.MODEL_ID_RE)
    forks: list[tuple[str, str]] = []
    if (route_config.MODEL_RE.pattern, route_config.MODEL_RE.flags) != (
        pinned.pattern,
        pinned.flags,
    ):
        forks.append(("route_config.MODEL_RE", pinned.pattern))
    for raw in MODEL_ID_PROBES:
        valid = pinned.fullmatch(raw) is not None
        entry = {"provider": "codex", "model": raw, "effort": "high", "route_source": "local"}
        entry["route_sha256"] = route_evidence.route_digest("implementer", entry)
        route_entry_valid = route_evidence._valid_route_entry("implementer", entry) is None
        verdicts = (
            ("transcript model", route_evidence._valid_transcript_model(raw)),
            ("run_started.route model", route_entry_valid),
            ("orchestrator_model", route_evidence._valid_orchestrator_model({"observed": raw})),
        )
        forks.extend((surface, raw) for surface, verdict in verdicts if verdict is not valid)
    return forks


class RouteVocabularyConstantTests(unittest.TestCase):
    def test_canonical_id_inventories_are_exact(self) -> None:
        self.assertEqual(
            (
                "implementer",
                "review-cheap",
                "review-final",
                "plan",
                "monitoring",
            ),
            route_vocab.ROLE_IDS,
        )
        self.assertEqual(
            ("review-cheap", "review-final"), route_vocab.REVIEW_ROLE_IDS
        )
        self.assertEqual(("codex", "claude"), route_vocab.PROVIDER_IDS)
        self.assertEqual(("exec", "claude"), route_vocab.EVENT_SOURCE_IDS)
        self.assertEqual(
            ("headless", "detached", "subagent", "teammate"),
            route_vocab.MODE_IDS,
        )
        self.assertEqual(
            ("workspace-write", "read-only", "instruction-bounded"),
            route_vocab.SANDBOX_IDS,
        )


class RouteVocabularyCanonicalizationTests(unittest.TestCase):
    def test_new_write_validation_accepts_canonical_vocabulary(self) -> None:
        for role in route_vocab.ROLE_IDS:
            for provider in route_vocab.PROVIDER_IDS:
                with self.subTest(role=role, provider=provider):
                    self.assertIsNone(
                        route_vocab.validate_new_write(
                            role=role,
                            provider=provider,
                            mode="headless",
                            event_source="exec",
                        )
                    )

    def test_new_write_validation_gives_canonical_legacy_target(self) -> None:
        cases = (
            (
                "implementation",
                "codex",
                "headless",
                "exec",
                "role",
                "implementation",
                "implementer",
            ),
            (
                "review",
                "claude",
                "headless",
                "exec",
                "role",
                "review",
                "review-final",
            ),
            (
                "implementer",
                "codex-cli",
                "headless",
                "exec",
                "provider",
                "codex-cli",
                "codex",
            ),
            (
                "implementer",
                "codex",
                "headless",
                "agent-tool",
                "event_source",
                "agent-tool",
                "claude",
            ),
        )
        for role, provider, mode, source, field, raw, target in cases:
            with self.subTest(field=field, target=target):
                expected = (
                    f"execution {field} {raw!r} is not canonical; use {target}"
                )
                with self.assertRaisesRegex(
                    route_vocab.NewWriteRefusal, rf"^{re.escape(expected)}$"
                ):
                    route_vocab.validate_new_write(
                        role=role,
                        provider=provider,
                        mode=mode,
                        event_source=source,
                    )

    def test_new_write_validation_lists_ids_without_a_legacy_target(self) -> None:
        with self.assertRaisesRegex(
            route_vocab.NewWriteRefusal,
            "^execution mode 'orchestrator-inline' "
            "is not canonical; use one of headless, detached, subagent, teammate$",
        ):
            route_vocab.validate_new_write(
                role="implementer",
                provider="claude",
                mode="orchestrator-inline",
                event_source="claude",
            )

    def test_implementation_aliases_and_canonical_roles(self) -> None:
        for raw_role in ("implementation", "implementer", "implement"):
            for provider in ("codex", "claude", "codex-cli", "unknown"):
                with self.subTest(raw_role=raw_role, provider=provider):
                    self.assertEqual(
                        "implementer",
                        route_vocab.canonical_role(raw_role, provider),
                    )

        for raw_role in route_vocab.ROLE_IDS:
            for provider in ("codex", "claude", "codex-cli", "unknown"):
                with self.subTest(raw_role=raw_role, provider=provider):
                    self.assertEqual(
                        raw_role,
                        route_vocab.canonical_role(raw_role, provider),
                    )

    def test_legacy_review_role_depends_on_canonical_provider(self) -> None:
        cases = (
            ("review", "codex", "review-cheap"),
            ("reviewer", "codex", "review-cheap"),
            ("review", "codex-cli", "review-cheap"),
            ("reviewer", "codex-cli", "review-cheap"),
            ("review", "claude", "review-final"),
            ("reviewer", "claude", "review-final"),
        )
        for raw_role, provider, expected in cases:
            with self.subTest(raw_role=raw_role, provider=provider):
                self.assertEqual(
                    expected,
                    route_vocab.canonical_role(raw_role, provider),
                )

    def test_unknown_or_malformed_roles_fail_closed(self) -> None:
        for raw_role in ("", "Review", "review-finally", "worker", None, 1, [], {}):
            with self.subTest(raw_role=raw_role):
                self.assertIsNone(route_vocab.canonical_role(raw_role, "codex"))

        for provider in ("", "Codex", "unknown", None, 1, [], {}):
            with self.subTest(provider=provider):
                self.assertIsNone(route_vocab.canonical_role("review", provider))

        for provider in (None, 1, [], {}):
            with self.subTest(provider=provider):
                self.assertIsNone(
                    route_vocab.canonical_role("implementer", provider)
                )

    def test_provider_mappings_and_malformed_values(self) -> None:
        cases = (
            ("codex", "codex"),
            ("claude", "claude"),
            ("codex-cli", "codex"),
        )
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(expected, route_vocab.canonical_provider(raw))

        for raw in ("", "Codex", "agent-tool", "exec", None, 1, [], {}):
            with self.subTest(raw=raw):
                self.assertIsNone(route_vocab.canonical_provider(raw))

    def test_event_source_mappings_include_literal_paths(self) -> None:
        cases = (
            ("exec", "exec"),
            ("claude", "claude"),
            ("codex", "exec"),
            ("agent-tool", "claude"),
            ("captured/events.jsonl", "exec"),
            ("/absolute/events.jsonl", "exec"),
        )
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(expected, route_vocab.canonical_event_source(raw))

        for raw in (
            "",
            "events.jsonl",
            "captured/events",
            "/absolute/events.log",
            "captured/events.jsonl/extra",
            "agent_tool",
            "Exec",
            None,
            1,
            [],
            {},
        ):
            with self.subTest(raw=raw):
                self.assertIsNone(route_vocab.canonical_event_source(raw))

    def test_modes_and_legacy_sandboxes_are_kept_distinct(self) -> None:
        for raw in route_vocab.MODE_IDS:
            with self.subTest(raw=raw):
                self.assertEqual((raw, None), route_vocab.canonical_mode(raw))

        for raw in ("read-only", "workspace-write"):
            with self.subTest(raw=raw):
                self.assertEqual((None, raw), route_vocab.canonical_mode(raw))

        for raw in (
            "orchestrator-inline",
            "instruction-bounded",
            "",
            "Headless",
            None,
            1,
            [],
            {},
        ):
            with self.subTest(raw=raw):
                self.assertEqual((None, None), route_vocab.canonical_mode(raw))

    def test_non_mutating_classification_uses_exact_raw_spellings(self) -> None:
        non_mutating = {
            "review",
            "reviewer",
            "review-cheap",
            "review-final",
            "plan",
            "monitoring",
        }
        mutating_or_unknown = {
            "implementation",
            "implementer",
            "implement",
            "Review",
            "review-cheap ",
            "",
            "worker",
        }
        for raw_role in non_mutating:
            with self.subTest(raw_role=raw_role):
                self.assertTrue(route_vocab.is_non_mutating(raw_role))
        for raw_role in mutating_or_unknown:
            with self.subTest(raw_role=raw_role):
                self.assertFalse(route_vocab.is_non_mutating(raw_role))
        for raw_role in (None, 1, [], {}):
            with self.subTest(raw_role=raw_role):
                self.assertFalse(route_vocab.is_non_mutating(raw_role))


class ModelVocabularyTests(unittest.TestCase):
    def test_model_id_pattern_is_exact(self) -> None:
        self.assertEqual(
            r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,127}(\[1m\])?$",
            route_vocab.MODEL_ID_RE,
        )

    def test_model_id_pattern_accepts_boundaries_punctuation_and_suffix(self) -> None:
        valid = (
            "A",
            "0",
            "model._:/@+-9",
            "m" * 128,
            "claude-fable-5-1[1m]",
            ("m" * 128) + "[1m]",
        )
        for raw in valid:
            with self.subTest(raw=raw):
                self.assertIsNotNone(re.fullmatch(route_vocab.MODEL_ID_RE, raw))

    def test_model_id_pattern_rejects_out_of_grammar_values(self) -> None:
        invalid = (
            "",
            "-model",
            "_model",
            ".model",
            ":model",
            "/model",
            "@model",
            "+model",
            "model name",
            "model=name",
            "modèle",
            "m" * 129,
            "model[1m][1m]",
            "model[1m]tail",
            "model\n",
        )
        for raw in invalid:
            with self.subTest(raw=raw):
                self.assertIsNone(re.fullmatch(route_vocab.MODEL_ID_RE, raw))

    def test_normalize_model_id_strips_exactly_one_trailing_suffix(self) -> None:
        cases = (
            ("claude-fable-5-1[1m]", "claude-fable-5-1"),
            ("claude-fable-5-1[1m][1m]", "claude-fable-5-1[1m]"),
            ("claude-fable-5-1[1m]tail", "claude-fable-5-1[1m]tail"),
            ("[1m]", ""),
            ("fable", "fable"),
            ("", ""),
        )
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(expected, route_vocab.normalize_model_id(raw))

    def test_model_family_recognizes_aliases_and_full_claude_ids(self) -> None:
        for family in ("fable", "opus", "sonnet", "haiku"):
            for raw in (family, f"{family}[1m]"):
                with self.subTest(raw=raw):
                    self.assertEqual(family, route_vocab.model_family(raw))

        cases = (
            ("claude-fable-5", "fable"),
            ("claude-fable-5-1", "fable"),
            ("claude-fable-5-1[1m]", "fable"),
            ("claude-opus-4-1", "opus"),
            ("claude-sonnet-4-5-20250929", "sonnet"),
            ("claude-haiku-4-5-20251001", "haiku"),
            ("claude-3-opus-20240229", "opus"),
            ("claude-3-5-sonnet-20241022", "sonnet"),
            ("claude-3-5-haiku-20241022", "haiku"),
            ("us.anthropic.claude-3-7-sonnet-20250219-v1:0", "sonnet"),
            ("claude-sonnet-4@20250514", "sonnet"),
        )
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(expected, route_vocab.model_family(raw))

    def test_model_family_rejects_false_positives_and_ambiguity(self) -> None:
        invalid = (
            "",
            "FABLE",
            "fable-5",
            "vendor-fable-5",
            "notclaude-fable-5",
            "claude-fable",
            "claude-5-fable",
            "claude-fables-5",
            "claude-sonnet-opus-4",
            "claude-sonnet-4-opus-5",
            "claude-sonnet-sonnet-4",
            "sonnet/claude-opus-4",
            "claude-opus-4/sonnet",
            "claude-sonnet-4!",
            "claude-sonnet-4\n",
        )
        for raw in invalid:
            with self.subTest(raw=raw):
                self.assertIsNone(route_vocab.model_family(raw))

        for raw in (None, 1, [], {}):
            with self.subTest(raw=raw):
                self.assertIsNone(route_vocab.model_family(raw))


class ModelIdGrammarPinTests(unittest.TestCase):
    def test_route_modules_share_the_route_vocab_model_id_grammar(self) -> None:
        self.assertEqual([], model_id_grammar_forks())

    def test_grammar_pin_detects_a_forked_route_config_literal(self) -> None:
        forked = re.compile(route_vocab.MODEL_ID_RE.replace("{0,127}", "{0,255}"))
        with mock.patch.object(route_config, "MODEL_RE", forked):
            self.assertEqual(
                [("route_config.MODEL_RE", route_vocab.MODEL_ID_RE)], model_id_grammar_forks()
            )

    def test_route_evidence_reads_the_route_vocab_grammar_at_every_site(self) -> None:
        with mock.patch.object(route_vocab, "MODEL_ID_RE", r"^.+$"):
            self.assertEqual([("route_config.MODEL_RE", r"^.+$")], model_id_grammar_forks())
        stand_in = SimpleNamespace(MODEL_ID_RE=r"^.+$")
        with mock.patch.object(route_evidence, "route_vocab", stand_in):
            forks = model_id_grammar_forks()
        self.assertEqual(
            {"transcript model", "run_started.route model", "orchestrator_model"},
            {surface for surface, _raw in forks},
        )
        self.assertEqual(
            {"m" * 129, "model name", "-model"}, {raw for _surface, raw in forks}
        )


if __name__ == "__main__":
    unittest.main()
