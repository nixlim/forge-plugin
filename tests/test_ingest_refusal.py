"""Legibility coverage for Revision-18 retrospective ingest refusals."""

from __future__ import annotations

import contextlib
import copy
import hashlib
import inspect
import io
import json
import sys
import textwrap
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tests import test_revision9_ingest_negatives as NEGATIVE
from tests import test_revision9_matrix as MATRIX
from tests._cli_loader import package_module, patch_chain_core

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from codex_orchestrator import ingest_refusal  # noqa: E402

STATUS = package_module("engine._verbs_status")
_BareRefusal = type("CoordinationRefusal", (Exception,), {})
_FrozenCause = type("FrozenError", (Exception,), {})


def _caused_refusal(base: str, cause: BaseException | None) -> BaseException:
    refusal = _BareRefusal(base)
    if cause is not None:
        refusal.__cause__ = cause
    return refusal


def _without_verbose_gate():
    function = STATUS._legible_ingest_refusal
    source = textwrap.dedent(inspect.getsource(function))
    anchor = "        ctx.options.verbose\n        and "
    if source.count(anchor) != 1:
        raise AssertionError("verbose-gate mutation anchor count differs")
    namespace = dict(function.__globals__)
    exec(
        compile(source.replace(anchor, "        "), function.__code__.co_filename, "exec"),
        namespace,
    )
    return namespace[function.__name__]


class IngestRefusalTests(NEGATIVE.CLI_FIXTURE_SUPPORT.ForgeCLIFixture):
    """Reuse the established real-chain fixture without inheriting unrelated tests."""

    revision9_environment = (
        NEGATIVE.Revision9IngestPredicateNegativeTests.revision9_environment
    )
    cli_process_context = (
        NEGATIVE.Revision9IngestPredicateNegativeTests.cli_process_context
    )
    invoke_cli = NEGATIVE.Revision9IngestPredicateNegativeTests.invoke_cli
    open_run_and_task = (
        NEGATIVE.Revision9IngestPredicateNegativeTests.open_run_and_task
    )
    selected_commit_ingest_event_digests = staticmethod(
        NEGATIVE.Revision9IngestPredicateNegativeTests.selected_commit_ingest_event_digests
    )
    prepare_terminal_ingest = (
        NEGATIVE.Revision9IngestPredicateNegativeTests.prepare_terminal_ingest
    )
    event_name = staticmethod(
        NEGATIVE.Revision9IngestPredicateNegativeTests.event_name
    )
    canonical_event_bytes = staticmethod(
        NEGATIVE.Revision9IngestPredicateNegativeTests.canonical_event_bytes
    )
    rewrite_event_chain = staticmethod(
        NEGATIVE.Revision9IngestPredicateNegativeTests.rewrite_event_chain
    )
    write_package = NEGATIVE.Revision9IngestPredicateNegativeTests.write_package
    reset_package = NEGATIVE.Revision9IngestPredicateNegativeTests.reset_package
    carry_state_change = (
        NEGATIVE.Revision9IngestPredicateNegativeTests.carry_state_change
    )
    run_snapshot = NEGATIVE.Revision9IngestPredicateNegativeTests.run_snapshot
    assert_snapshot_unchanged = (
        NEGATIVE.Revision9IngestPredicateNegativeTests.assert_snapshot_unchanged
    )
    local_ingest_globals = (
        NEGATIVE.Revision9IngestPredicateNegativeTests.local_ingest_globals
    )
    assert_ingest_refusal = (
        NEGATIVE.Revision9IngestPredicateNegativeTests.assert_ingest_refusal
    )

    def _malformed_state_argv(
        self, prepared, marker: str
    ) -> tuple[str, ...]:
        relative = f"external/{marker}.json"
        (self.repo / relative).write_text(
            "{ malformed bytes " + marker, encoding="utf-8"
        )
        argv = list(prepared.ingest_argv)
        argv[argv.index("--state-file") + 1] = relative
        return tuple(argv)

    def _assert_named_proof_zero(
        self, prepared, argv: tuple[str, ...], *, verbose: bool = True
    ) -> dict[str, object]:
        _batch, builders, _journal = NEGATIVE.CLI._coordination_modules()
        invocation = ("--verbose", *argv) if verbose else argv
        exit_code, envelope = self.invoke_cli(*invocation)
        expected = (
            builders.INGEST_PROOF_INVALID
            + ": proof 0 inputs: malformed chain bytes"
        )
        self.assertEqual(exit_code, 1, envelope)
        self.assertEqual(envelope["message"], expected)
        self.assertEqual(envelope["reason_code"], "ingest-proof-invalid")
        self.assertEqual(
            envelope["remediation"],
            "repair the authoritative chain proof and retry",
        )
        return envelope

    def test_proof_zero_verbose_output_is_safe_and_control_is_discriminating(
        self,
    ) -> None:
        marker = "caller-path-fragment-c82a91"
        prepared = self.prepare_terminal_ingest("run-20260930-ingest-proof-zero")
        argv = self._malformed_state_argv(prepared, marker)
        snapshot = self.run_snapshot(prepared)

        envelope = self._assert_named_proof_zero(prepared, argv)
        observed = str(envelope["observed"])
        self.assertNotIn(marker, str(envelope["message"]))
        self.assertNotIn(marker, observed)
        self.assertNotIn("Expecting property name", observed)
        self.assertRegex(
            observed,
            r"; raise site scripts/forge/forge_cli/chain_core/"
            r"(?:_commit_chain|_ingest_merge)\.py:\d+; "
            r"causes CoordinationRefusal <- JSONDecodeError$",
        )

        disabled = ingest_refusal.INGEST_LEGIBILITY_CONTROLS - {"proof-named"}
        with mock.patch.object(
            ingest_refusal, "INGEST_LEGIBILITY_CONTROLS", disabled
        ):
            with self.assertRaises(AssertionError):
                self._assert_named_proof_zero(prepared, argv)
            exit_code, prior = self.invoke_cli("--verbose", *argv)
        self.assertEqual(exit_code, 1, prior)
        self.assertEqual(
            prior["message"],
            NEGATIVE.CLI._coordination_modules()[1].INGEST_PROOF_INVALID,
        )
        self.assertEqual(prior["reason_code"], "ingest-proof-invalid")
        self.assertEqual(prior["observed"], prior["message"])
        self.assertEqual(
            prior["remediation"],
            "repair the authoritative chain proof and retry",
        )
        self.assert_snapshot_unchanged(prepared, snapshot)

    def test_nonverbose_proof_refusal_has_no_exception_detail(self) -> None:
        prepared = self.prepare_terminal_ingest(
            "run-20260930-ingest-proof-zero-nonverbose"
        )
        argv = self._malformed_state_argv(prepared, "nonverbose-marker")

        def assert_bare_observation() -> None:
            envelope = self._assert_named_proof_zero(prepared, argv, verbose=False)
            observed = str(envelope["observed"])
            self.assertEqual(observed, envelope["message"])
            self.assertNotIn("raise site", observed)
            self.assertNotIn("CoordinationRefusal", observed)
            self.assertNotIn("JSONDecodeError", observed)

        assert_bare_observation()
        with mock.patch.object(
            STATUS, "_legible_ingest_refusal", _without_verbose_gate()
        ), self.assertRaises(AssertionError):
            assert_bare_observation()


    def test_verbose_unclassified_nonproof_refusal_has_no_augmentation(self) -> None:
        prepared = self.prepare_terminal_ingest(
            "run-20260930-ingest-unclassified-refusal"
        )
        _batch, _builders, journal = NEGATIVE.CLI._coordination_modules()
        message = "forge: unrelated coordination fault"
        snapshot = self.run_snapshot(prepared)

        with patch_chain_core(
            "_verify_and_build_ingest_records",
            side_effect=journal.CoordinationRefusal(message),
        ):
            exit_code, envelope = self.invoke_cli(
                "--verbose", *prepared.ingest_argv
            )

        self.assertEqual(exit_code, 1, envelope)
        self.assertEqual(envelope["message"], message)
        self.assertEqual(envelope["observed"], message)
        self.assertNotIn("raise site", str(envelope["observed"]))
        self.assertNotIn("causes", str(envelope["observed"]))
        self.assertEqual(envelope["reason_code"], "ingest-proof-invalid")
        self.assertEqual(
            envelope["remediation"],
            "inspect the Revision-9 coordination proof and retry",
        )
        self.assert_snapshot_unchanged(prepared, snapshot)

    def _assert_bare_postproof_refusal(self, prepared) -> dict[str, object]:
        _batch, builders, _journal = NEGATIVE.CLI._coordination_modules()
        with mock.patch.object(
            builders,
            "ingest_chain_records",
            wraps=builders.ingest_chain_records,
        ) as builder:
            exit_code, envelope = self.invoke_cli(
                "--verbose", *prepared.ingest_argv
            )
        builder.assert_not_called()
        self.assertEqual(exit_code, 1, envelope)
        self.assertEqual(envelope["message"], builders.INGEST_PROOF_INVALID)
        self.assertEqual(envelope["observed"], builders.INGEST_PROOF_INVALID)
        self.assertEqual(envelope["reason_code"], "ingest-proof-invalid")
        self.assertEqual(
            envelope["remediation"],
            "repair the authoritative chain proof and retry",
        )
        return envelope

    def test_outcome_map_digest_mismatch_is_bare_after_proof_sixteen(self) -> None:
        prepared = self.prepare_terminal_ingest(
            "run-20260930-ingest-outcome-map-mismatch"
        )
        outcome = copy.deepcopy(prepared.outcome_map)
        outcome["event_digests"] = list(outcome["event_digests"][:-1])
        self.write_package(prepared, outcome=outcome)
        snapshot = self.run_snapshot(prepared)

        self._assert_bare_postproof_refusal(prepared)
        with mock.patch.object(
            ingest_refusal, "close_progress", return_value=None
        ):
            with self.assertRaises(AssertionError):
                self._assert_bare_postproof_refusal(prepared)
            exit_code, disabled = self.invoke_cli(*prepared.ingest_argv)

        self.assertEqual(exit_code, 1, disabled)
        self.assertIn(
            ": proof 16 scope-membership: predicate not satisfied",
            disabled["message"],
        )
        self.assert_snapshot_unchanged(prepared, snapshot)

    def test_incomplete_verifier_names_first_missing_proof(self) -> None:
        prepared = self.prepare_terminal_ingest(
            "run-20260930-ingest-incomplete-verifier"
        )
        _batch, builders, _journal = NEGATIVE.CLI._coordination_modules()
        completed = NEGATIVE.CLI.INGEST_PROOF_ORDER[:5]
        missing = NEGATIVE.CLI.INGEST_PROOF_ORDER[len(completed)]
        snapshot = self.run_snapshot(prepared)

        with patch_chain_core(
            "_verify_and_build_ingest_records",
            return_value=((), completed),
        ):
            exit_code, envelope = self.invoke_cli(*prepared.ingest_argv)

        self.assertEqual(exit_code, 1, envelope)
        self.assertEqual(
            envelope["message"],
            f"{builders.INGEST_PROOF_INVALID}: proof 6 {missing}: "
            "predicate not satisfied",
        )
        self.assertEqual(envelope["reason_code"], "ingest-proof-invalid")
        self.assertEqual(
            envelope["remediation"],
            "repair the authoritative chain proof and retry",
        )
        self.assert_snapshot_unchanged(prepared, snapshot)

    def test_new_verifier_pass_clears_stale_progress_before_proof_one(self) -> None:
        _batch, builders, journal = NEGATIVE.CLI._coordination_modules()
        order = NEGATIVE.CLI.INGEST_PROOF_ORDER
        ingest_refusal.record_progress(order)
        controls = NEGATIVE.CLI.INGEST_PROOF_CONTROLS - {order[0]}

        with patch_chain_core("INGEST_PROOF_CONTROLS", controls), self.assertRaises(
            journal.CoordinationRefusal
        ) as raised:
            NEGATIVE.CLI._require_ingest_proof(order[0], [])

        self.assertEqual(
            ingest_refusal.legible_message(
                builders.INGEST_PROOF_INVALID,
                order,
                raised.exception,
            ),
            builders.INGEST_PROOF_INVALID
            + ": proof 0 inputs: predicate not satisfied",
        )

    def test_postproof_reverification_mismatch_keeps_bare_literal(self) -> None:
        prepared = self.prepare_terminal_ingest(
            "run-20260930-ingest-postproof-mismatch"
        )
        _batch, builders, _journal = NEGATIVE.CLI._coordination_modules()
        original_ingest = builders.ingest_chain_records
        original_verifier = builders._INGEST_PROOF_VERIFIER
        self.assertIsNotNone(original_verifier)
        calls: list[int] = []

        def inconsistent_verifier(*args, **kwargs):
            records, completed = original_verifier(*args, **kwargs)
            calls.append(len(records))
            if len(calls) == 1:
                return records, completed
            changed = list(copy.deepcopy(tuple(records)))
            changed[-1] = dict(changed[-1], status="failed")
            return tuple(changed), completed

        inconsistent_verifier._forge_cli_revision9_seam = True

        def ingest_with_mismatch(*args, **kwargs):
            with mock.patch.object(
                builders, "_INGEST_PROOF_VERIFIER", inconsistent_verifier
            ):
                return original_ingest(*args, **kwargs)

        snapshot = self.run_snapshot(prepared)
        with mock.patch.object(
            builders,
            "ingest_chain_records",
            side_effect=ingest_with_mismatch,
        ):
            exit_code, envelope = self.invoke_cli(*prepared.ingest_argv)

        self.assertEqual(exit_code, 1, envelope)
        self.assertGreaterEqual(len(calls), 2)
        self.assertEqual(envelope["message"], builders.INGEST_PROOF_INVALID)
        self.assertEqual(envelope["reason_code"], "ingest-proof-invalid")
        self.assertEqual(
            envelope["remediation"],
            "repair the authoritative chain proof and retry",
        )
        self.assert_snapshot_unchanged(prepared, snapshot)

    def test_later_builder_verifier_failure_starts_at_proof_zero(self) -> None:
        prepared = self.prepare_terminal_ingest(
            "run-20260930-ingest-later-verifier"
        )
        _batch, builders, journal = NEGATIVE.CLI._coordination_modules()
        original_ingest = builders.ingest_chain_records
        original_verifier = builders._INGEST_PROOF_VERIFIER
        self.assertIsNotNone(original_verifier)
        calls = 0

        def fail_before_proof(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                return original_verifier(*args, **kwargs)
            try:
                raise ValueError("planted verifier failure")
            except ValueError as cause:
                raise journal.CoordinationRefusal(
                    builders.INGEST_PROOF_INVALID
                ) from cause

        fail_before_proof._forge_cli_revision9_seam = True

        def ingest_with_failure(*args, **kwargs):
            with mock.patch.object(
                builders, "_INGEST_PROOF_VERIFIER", fail_before_proof
            ):
                return original_ingest(*args, **kwargs)

        snapshot = self.run_snapshot(prepared)
        with mock.patch.object(
            builders,
            "ingest_chain_records",
            side_effect=ingest_with_failure,
        ):
            exit_code, envelope = self.invoke_cli(*prepared.ingest_argv)

        self.assertEqual(exit_code, 1, envelope)
        self.assertEqual(calls, 2)
        self.assertEqual(
            envelope["message"],
            builders.INGEST_PROOF_INVALID
            + ": proof 0 inputs: malformed chain bytes",
        )
        self.assertEqual(envelope["reason_code"], "ingest-proof-invalid")
        self.assertEqual(
            envelope["remediation"],
            "repair the authoritative chain proof and retry",
        )
        self.assert_snapshot_unchanged(prepared, snapshot)

    def test_legible_message_covers_closed_observed_vocabulary(self) -> None:
        _batch, builders, _journal = NEGATIVE.CLI._coordination_modules()
        base = builders.INGEST_PROOF_INVALID
        order = ("alpha-proof",)
        cases = (
            (_FrozenCause("planted"), "chain state invalid"),
            (ValueError("planted"), "malformed chain bytes"),
            (OSError("planted"), "filesystem read failed"),
            (KeyError("planted"), "internal proof error"),
            (None, "predicate not satisfied"),
        )

        for cause, observed in cases:
            with self.subTest(observed=observed):
                ingest_refusal.reset_progress()
                ingest_refusal.record_progress(order)
                message = ingest_refusal.legible_message(
                    base, order, _caused_refusal(base, cause)
                )
                self.assertEqual(
                    message, f"{base}: proof 1 alpha-proof: {observed}"
                )


class MergeCountRefusalTests(MATRIX.CLI_FIXTURE_SUPPORT.ForgeCLIFixture):
    """Exercise a merge count refusal through the real CLI ingest surface."""

    run_id = "run-20260930-merge-count-refusal"
    task_id = "task-merge-count"
    chain_id = "c-2026-09-30T120000Z-abcd"

    cli_context = (
        MATRIX.Revision9MergeIngestArchiveMatrixTests.cli_context
    )
    append_merge_event = (
        MATRIX.Revision9MergeIngestArchiveMatrixTests.append_merge_event
    )
    build_real_merge_package = (
        MATRIX.Revision9MergeIngestArchiveMatrixTests.build_real_merge_package
    )

    def _invoke_cli_unchecked(
        self, *argv: str
    ) -> tuple[int, dict[str, object], str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with self.cli_context(), contextlib.redirect_stdout(
            stdout
        ), contextlib.redirect_stderr(stderr):
            exit_code = MATRIX.CLI.main(
                ["--json", "--repo", str(self.repo), *argv]
            )
        self.assertEqual(stdout.getvalue().count("\n"), 1)
        return exit_code, json.loads(stdout.getvalue()), stderr.getvalue()

    def _prepare_merge_ingest(self) -> SimpleNamespace:
        MATRIX.CLI.register_coordination_seams()
        MATRIX.ARCHIVE._CLI_INGEST_AUTHORITY = MATRIX.CLI
        (
            state_raw,
            events_raw,
            outcome_raw,
            candidate_head,
            _base,
            _eligible,
        ) = self.build_real_merge_package()

        chains = self.repo / ".forge" / "chains"
        chains.mkdir(parents=True)
        (chains / f"{self.chain_id}.json").write_bytes(state_raw)
        (chains / f"{self.chain_id}.events.jsonl").write_bytes(events_raw)

        with self.cli_context():
            _batch, _builders, journal = MATRIX.CLI._coordination_modules()
            journal.open_run(
                self.repo,
                self.run_id,
                ["docs/**"],
                {
                    "type": "run_started",
                    "recorded_at": "2026-09-30T12:00:00Z",
                    "run_id": self.run_id,
                    "goal": "Exercise a post-proof merge count refusal",
                    "repo": str(self.repo.resolve()),
                    "repo_head": self.git("rev-parse", "HEAD"),
                    "repo_status": self.git("status", "--short").splitlines(),
                    "plugin_ref": "forge-revision18-ingest-refusal-tests",
                },
            )
            journal.append_run_record(
                self.repo,
                self.run_id,
                {
                    "type": "task",
                    "recorded_at": "2026-09-30T12:01:00Z",
                    "run_id": self.run_id,
                    "id": self.task_id,
                    "status": "active",
                    "goal": "Reject a duplicate synthesized landing count",
                    "acceptance": ["Post-proof merge count refusal stays bare"],
                    "files": ["docs/guide.md"],
                },
            )

        run_dir = self.repo / ".codex-orchestrator" / "runs" / self.run_id
        legacy_lock = run_dir / journal.BATCH_LOCK_NAME
        self.assertTrue(legacy_lock.is_file())
        legacy_lock.unlink()
        source_dir = self.repo / "external-merge"
        source_dir.mkdir()
        sources = {
            "state-file": ("external-merge/state.json", state_raw),
            "events-file": ("external-merge/events.jsonl", events_raw),
            "outcome-map": ("external-merge/outcome-map.json", outcome_raw),
        }
        for relative, raw in sources.values():
            (self.repo / relative).write_bytes(raw)
        argv = (
            "--run-id",
            self.run_id,
            "journal",
            "ingest-chain",
            "--task",
            self.task_id,
            "--state-file",
            sources["state-file"][0],
            "--events-file",
            sources["events-file"][0],
            "--outcome-map",
            sources["outcome-map"][0],
            "--closing-head",
            candidate_head,
            "--task-status",
            "complete",
            "--idempotency-key",
            hashlib.sha256(b"merge-count-refusal").hexdigest(),
        )
        return SimpleNamespace(argv=argv, run_dir=run_dir, journal=journal)

    def _assert_bare_merge_count_refusal(
        self, prepared: SimpleNamespace
    ) -> dict[str, object]:
        _batch, builders, _journal = MATRIX.CLI._coordination_modules()
        with self._duplicate_landing_count() as duplicated, mock.patch.object(
            builders,
            "ingest_chain_records",
            wraps=builders.ingest_chain_records,
        ) as builder:
            exit_code, envelope, _stderr = self._invoke_cli_unchecked(
                "--verbose", *prepared.argv
            )
        duplicated.assert_called()
        builder.assert_not_called()
        self.assertEqual(exit_code, 1, envelope)
        self.assertEqual(envelope["message"], builders.INGEST_PROOF_INVALID)
        self.assertEqual(envelope["observed"], builders.INGEST_PROOF_INVALID)
        self.assertEqual(envelope["reason_code"], "ingest-proof-invalid")
        self.assertEqual(
            envelope["remediation"],
            "repair the authoritative chain proof and retry",
        )
        return envelope

    @contextlib.contextmanager
    def _duplicate_landing_count(self):
        original = MATRIX.CORE._merge_ingest_record_templates

        def duplicate_landing(*args, **kwargs):
            templates = original(*args, **kwargs)
            landing = next(
                (
                    item
                    for item in templates
                    if item[0].get("outcome") == "chain-landing"
                ),
                None,
            )
            return templates if landing is None else (*templates, landing)

        with patch_chain_core(
            "_merge_ingest_record_templates", side_effect=duplicate_landing
        ) as duplicated:
            yield duplicated

    def test_merge_landing_count_mismatch_is_bare_after_proof_sixteen(
        self,
    ) -> None:
        prepared = self._prepare_merge_ingest()
        journal_before = (prepared.run_dir / "journal.jsonl").read_bytes()

        self._assert_bare_merge_count_refusal(prepared)
        with mock.patch.object(
            ingest_refusal, "close_progress", return_value=None
        ):
            with self.assertRaises(AssertionError):
                self._assert_bare_merge_count_refusal(prepared)
            with self._duplicate_landing_count():
                exit_code, disabled, _stderr = self._invoke_cli_unchecked(
                    *prepared.argv
                )

        self.assertEqual(exit_code, 1, disabled)
        self.assertIn(
            ": proof 16 scope-membership: predicate not satisfied",
            disabled["message"],
        )
        self.assertEqual(
            (prepared.run_dir / "journal.jsonl").read_bytes(), journal_before
        )
        self.assertFalse(
            (prepared.run_dir / prepared.journal.BATCH_INTENT_NAME).exists()
        )
