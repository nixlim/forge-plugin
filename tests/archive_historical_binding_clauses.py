"""Focused disable proofs for historical-binding normative sub-clauses."""

from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any, NoReturn
from unittest import mock

from tests._cli_loader import load_script

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = load_script(
    "_forge_archive_historical_binding_clauses",
    ROOT / "scripts" / "forge" / "archive-run.py",
)
HISTORY = ARCHIVE.binding_history
CONTROLS = frozenset(HISTORY._CONTROL_BY_REASON.values())


class ClauseRefusal(RuntimeError):
    """A structured mismatch raised through a synthetic resolution context."""


def _refuse(code: str) -> NoReturn:
    if code != "structured_chain_mismatch":
        raise AssertionError(f"unexpected discrepancy code: {code}")
    raise ClauseRefusal(code)


def _record(
    line: int,
    *,
    chain: str = "chain-a",
    outcome: str | None = None,
    result: str = "passed",
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "_line": line,
        "type": "verification",
        "task": "task-01",
        "criterion": "gate-1: focused historical clause",
        "result": result,
        "binding": {
            "binding_id": f"binding-{line}",
            "source_record": {"chain_id": chain},
        },
    }
    if outcome is not None:
        record.update(type="decision", outcome=outcome)
    return record


def _context(
    states: dict[str, dict[str, object]],
    records: list[dict[str, Any]] | None = None,
) -> Any:
    return HISTORY.ResolutionContext(
        Path("."),
        "run-20261003-focused-clauses",
        -1,
        {chain_id: SimpleNamespace(state=state) for chain_id, state in states.items()},
        records or [],
        CONTROLS,
        None,
        lambda *_args: None,
        _refuse,
    )


class HistoricalBindingClauseTests(unittest.TestCase):
    """Pin each terminal, agreement, replay, and plain-rendering clause."""

    def test_terminal_anchor_subclauses_are_independently_required(self) -> None:
        landing = _record(1, outcome="chain-landing")
        abort = _record(1, outcome="chain-abort")
        refused = (
            ({"state": "verifying"}, [landing], {1: "current"}),
            (
                {"state": "aborted", "journal_outbox": {"records": []}},
                [abort],
                {1: "current"},
            ),
            ({"state": "closed"}, [abort], {1: "current"}),
            (
                {"state": "aborted", "journal_outbox": None},
                [abort, _record(2, outcome="chain-abort")],
                {1: "current", 2: "current"},
            ),
        )
        for state, records, currency in refused:
            with self.subTest(state=state, lines=sorted(currency)):
                with self.assertRaises(ClauseRefusal):
                    HISTORY._terminal_anchors(_context({"chain-a": state}), records, currency)

        self.assertEqual(
            HISTORY._terminal_anchors(
                _context({"chain-a": {"state": "closed"}}),
                [landing],
                {1: "rerun"},
            ),
            {},
        )

    def test_abort_class_requires_bidirectional_agreement_and_currency(self) -> None:
        record = _record(1)
        context = _context({"chain-a": {"state": "closed"}}, [record])
        common = (
            mock.patch.object(HISTORY.journal, "_superseded_binding_ids", return_value=set()),
            mock.patch.object(
                HISTORY.landed_evidence,
                "retirement_predicate",
                return_value=lambda _record: True,
            ),
        )
        with (
            mock.patch.object(
                HISTORY, "_terminal_anchors", return_value={"chain-a": "chain-landing"}
            ),
            common[0],
            common[1],
            self.assertRaises(ClauseRefusal),
        ):
            HISTORY._classify(context, [record], {1: "current"})

        with (
            mock.patch.object(
                HISTORY, "_terminal_anchors", return_value={"chain-a": "chain-abort"}
            ),
            common[0],
            common[1],
            self.assertRaises(ClauseRefusal),
        ):
            HISTORY._classify(context, [record], {1: "superseded"})

    def test_superseded_and_rerun_require_bidirectional_agreement(self) -> None:
        record = _record(1)
        context = _context({"chain-a": {"state": "closed"}}, [record])
        common = (
            mock.patch.object(
                HISTORY, "_terminal_anchors", return_value={"chain-a": "chain-landing"}
            ),
            mock.patch.object(
                HISTORY.landed_evidence,
                "retirement_predicate",
                return_value=lambda _record: False,
            ),
        )
        with (
            common[0],
            common[1],
            mock.patch.object(
                HISTORY.journal,
                "_superseded_binding_ids",
                return_value={"binding-1"},
            ),
            self.assertRaises(ClauseRefusal),
        ):
            HISTORY._classify(context, [record], {1: "rerun"})

        with (
            common[0],
            common[1],
            mock.patch.object(HISTORY.journal, "_superseded_binding_ids", return_value=set()),
            mock.patch.object(HISTORY, "_reason_for", return_value=HISTORY.RERUN),
            self.assertRaises(ClauseRefusal),
        ):
            HISTORY._classify(context, [record], {1: "superseded"})

    def test_recheck_and_rerun_never_classify_current_records(self) -> None:
        record = _record(1)
        context = _context({"chain-a": {"state": "closed"}}, [record])
        for reason in (HISTORY.RECHECKED, HISTORY.RERUN):
            with (
                self.subTest(reason=reason),
                mock.patch.object(
                    HISTORY,
                    "_terminal_anchors",
                    return_value={"chain-a": "chain-landing"},
                ),
                mock.patch.object(HISTORY.journal, "_superseded_binding_ids", return_value=set()),
                mock.patch.object(
                    HISTORY.landed_evidence,
                    "retirement_predicate",
                    return_value=lambda _record: False,
                ),
                mock.patch.object(HISTORY, "_reason_for", return_value=reason),
                self.assertRaises(ClauseRefusal),
            ):
                HISTORY._classify(context, [record], {1: "current"})

    def test_reason_precedence_is_fixed(self) -> None:
        record = _record(1)
        newer = _record(2)
        key = ("gate-1: focused historical clause", "chain-a", b"candidate")
        cases = (
            ({"binding-1"}, True, True, HISTORY.SUPERSEDED),
            (set(), True, True, HISTORY.ABORTED),
            (set(), False, True, HISTORY.RECHECKED),
            (set(), False, False, HISTORY.RERUN),
        )
        with mock.patch.object(HISTORY, "_step_key", return_value=key):
            for superseded, aborted, cleared, expected in cases:
                with self.subTest(expected=expected):
                    self.assertEqual(
                        HISTORY._reason_for(
                            record,
                            superseded=superseded,
                            aborted=aborted,
                            cleared=cleared,
                            newest_steps={key: newer},
                            current_lines={2},
                        ),
                        expected,
                    )

    def test_recheck_requires_source_rule_and_same_pair(self) -> None:
        failed = _record(1, result="failed")
        passed = _record(2)
        records = [failed, passed]
        with mock.patch.object(HISTORY, "_same_pair", return_value=True):
            self.assertFalse(
                HISTORY._cleared_by_current_recheck(
                    failed, records, lambda _records, _index: False, {2}
                )
            )

        pairs = {
            id(failed): ("chain-a", b"candidate-a", "binding-1"),
            id(passed): ("chain-b", b"candidate-b", "binding-2"),
        }
        with mock.patch.object(
            HISTORY.journal,
            "_binding_chain_and_candidate",
            side_effect=lambda record: pairs[id(record)],
        ):
            self.assertFalse(
                HISTORY._cleared_by_current_recheck(
                    failed, records, lambda _records, _index: True, {2}
                )
            )

    def test_current_and_deferred_replay_require_exact_wrapped_results(self) -> None:
        record = _record(1)
        binding = record["binding"]
        context = _context({"chain-a": {"state": "closed"}}, [record])
        deferred_results = (
            {"binding": binding, "currency": "current"},
            {"binding": {"binding_id": "different"}, "currency": "rerun"},
        )
        for replayed in deferred_results:
            with (
                self.subTest(replayed=replayed),
                mock.patch.object(HISTORY, "_replay", return_value=replayed),
                self.assertRaises(ClauseRefusal),
            ):
                HISTORY._resolve_deferred(context, [record], {}, {})

        with (
            mock.patch.object(
                HISTORY,
                "_replay",
                return_value={"binding_id": "different"},
            ),
            self.assertRaises(ClauseRefusal),
        ):
            HISTORY._resolve_current(context, [record])

    def test_each_unclassified_noncurrent_guard_refuses(self) -> None:
        record = _record(1, result="failed")
        context = _context({"chain-a": {"state": "closed"}}, [record])
        with (
            mock.patch.object(
                HISTORY, "_terminal_anchors", return_value={"chain-a": "chain-landing"}
            ),
            mock.patch.object(HISTORY.journal, "_superseded_binding_ids", return_value=set()),
            mock.patch.object(
                HISTORY.landed_evidence,
                "retirement_predicate",
                return_value=lambda _record: False,
            ),
            self.assertRaises(ClauseRefusal),
        ):
            HISTORY._classify(context, [record], {1: "rerun"})

        with (
            mock.patch.object(
                HISTORY,
                "_resolve_current",
                return_value=({1: record["binding"]}, {1: "rerun"}, []),
            ),
            mock.patch.object(HISTORY, "_resolve_deferred"),
            mock.patch.object(HISTORY, "_classify", return_value={}),
            self.assertRaises(ClauseRefusal),
        ):
            HISTORY.resolve_live_bindings(context, {"chain-a": [record]}, {"chain-a"})

    def test_resolved_bindings_require_complete_known_classifications(self) -> None:
        with self.assertRaisesRegex(ValueError, "incomplete binding classifications"):
            HISTORY.ResolvedBindings({1: {}}, {})
        with self.assertRaisesRegex(ValueError, "incomplete binding classifications"):
            HISTORY.ResolvedBindings({1: {}}, {1: "unknown"})

    def test_current_rendering_stays_plain(self) -> None:
        binding_id = "current-binding"
        bindings = HISTORY.ResolvedBindings({7: {"binding_id": binding_id}}, {7: HISTORY.CURRENT})
        self.assertEqual(
            HISTORY.status_for(bindings, 7, binding_id, _refuse),
            "BOUND (current-binding)",
        )
        self.assertEqual(
            HISTORY.journal_mapping(bindings, 7, binding_id, _refuse),
            "- line 7: current-binding",
        )
