"""Revision-19 retrospective archive proof and caller-surface coverage."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tests import test_cli_chain as cli_fixture
from tests._cli_loader import load_script, package_module, patch_engine
from tests._git_env import init_quiet_repository

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FORGE_SCRIPTS = SCRIPTS / "forge"
for import_root in (SCRIPTS, FORGE_SCRIPTS):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

CLOSING = load_script("archive_closing", FORGE_SCRIPTS / "archive_closing.py")
ARCHIVE = load_script("archive_backfill_archiver", FORGE_SCRIPTS / "archive-run.py")
CLI_PARSER = package_module("engine._parser")
CLI_OPTIONS = package_module("engine._cli_options")
CLI_DISPATCH = package_module("app._dispatch")
CLI_LIFECYCLE = package_module("engine._verbs_lifecycle")

APPROVAL_REFUSAL = "forge: archive refused — backfill approval missing or mismatched"
BLOCKED_REFUSAL = (
    "forge: archive refused — blocked judgment requires an approved backfill archive"
)
MODE_CONFLICT = (
    "forge: archive refused — backfill closing mode cannot be combined with "
    "normal or legacy closing mode"
)
REPOSITORY_REFUSAL = (
    "forge: archive refused — run repository does not match current repository"
)
CONTROLS = (
    "approval-binding",
    "archive-head-binding",
    "strict-passed-history",
    "archive-head-ancestry",
    "starting-head-ancestry",
    "landed-commit-enumeration",
    "landed-commit-containment",
    "basis-stability",
    "closing-time-order",
    "closing-identification",
    "archive-time-order",
    "blocked-admission",
)
REFUSALS = (
    APPROVAL_REFUSAL,
    "forge: archive refused — repository HEAD is not the approved archive HEAD",
    "forge: archive refused — backfill closing HEAD equals archive HEAD for a passed run",
    "forge: archive refused — backfill closing HEAD is not an ancestor of archive HEAD",
    "forge: archive refused — backfill closing HEAD does not contain starting HEAD",
    "forge: archive refused — could not authenticate every landed run commit",
    "forge: archive refused — backfill closing HEAD does not contain landed commit "
    "<full-object-id>",
    "forge: archive refused — basis document changed after closing HEAD: <label>",
    "forge: archive refused — backfill closing HEAD postdates run_closed",
    "forge: archive refused — backfill closing HEAD is not the last commit before run_closed",
    "forge: archive refused — archive HEAD predates run_closed",
    BLOCKED_REFUSAL,
)
GATED_PAYLOAD = {
    "issues": [],
    "non_passing_verifications": [],
    "ok": True,
    "profile": "gates",
    "warnings": [],
}


class GitBackfillFixture(unittest.TestCase):
    """A linear graph with native commit times on both sides of run_closed."""

    maxDiff = None

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="forge-backfill-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.repo = self.base / "repo"
        initialized = init_quiet_repository(self.repo, "--quiet")
        self.assertEqual(initialized.returncode, 0, initialized.stderr)
        self.git_text("config", "user.name", "Backfill Fixture")
        self.git_text("config", "user.email", "backfill@example.invalid")
        self.git_text("config", "commit.gpgsign", "false")

        self.starting = self.commit("starting", "2026-01-01T00:00:00+00:00")
        self.commit_landing = self.commit(
            "commit-landing", "2026-01-01T00:01:00+00:00"
        )
        self.merge_landing = self.commit(
            "merge-landing", "2026-01-01T00:02:00+00:00"
        )
        self.closing = self.commit("closing", "2026-01-01T00:03:00+00:00")
        self.successor = self.commit("successor", "2026-01-01T00:05:00+00:00")
        self.archive_head = self.commit(
            "archive", "2026-01-01T00:06:00+00:00", change_unstable=True
        )
        self.side = self.commit_tree(None, "2026-01-01T00:03:00+00:00")
        self.early_archive = self.commit_tree(
            self.successor, "2026-01-01T00:03:30+00:00"
        )
        self.run_dir = self.repo / ".codex-orchestrator/runs/run-backfill-target"
        self.run_dir.mkdir(parents=True)

    def git_bytes(
        self, *arguments: str, environment: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            ["git", *arguments],
            cwd=self.repo,
            env=environment,
            check=False,
            stdin=subprocess.DEVNULL,
            capture_output=True,
        )

    def git_text(self, *arguments: str) -> str:
        result = subprocess.run(
            ["git", *arguments],
            cwd=self.repo,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def dated_environment(self, when: str) -> dict[str, str]:
        return {
            **os.environ,
            "GIT_AUTHOR_DATE": when,
            "GIT_COMMITTER_DATE": when,
        }

    def commit(self, label: str, when: str, *, change_unstable: bool = False) -> str:
        if label == "starting":
            (self.repo / "basis.md").write_text("stable basis\n", encoding="utf-8")
            (self.repo / "unstable.md").write_text("before\n", encoding="utf-8")
        (self.repo / f"{label}.txt").write_text(label + "\n", encoding="utf-8")
        if change_unstable:
            (self.repo / "unstable.md").write_text("after\n", encoding="utf-8")
        self.git_text("add", "--all")
        result = self.git_bytes(
            "commit",
            "--quiet",
            "-m",
            label,
            environment=self.dated_environment(when),
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        return self.git_text("rev-parse", "HEAD")

    def commit_tree(self, parent: str | None, when: str) -> str:
        arguments = ["commit-tree", self.git_text("rev-parse", "HEAD^{tree}")]
        if parent is not None:
            arguments.extend(["-p", parent])
        result = subprocess.run(
            ["git", *arguments],
            cwd=self.repo,
            env=self.dated_environment(when),
            check=False,
            input=b"synthetic\n",
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        return result.stdout.decode("ascii").strip()

    @staticmethod
    def run_git(repo: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            ["git", *arguments],
            cwd=repo,
            check=False,
            stdin=subprocess.DEVNULL,
            capture_output=True,
        )

    def records(
        self,
        *,
        judgment: str = "passed",
        recorded_at: str = "2026-01-01T00:04:00Z",
        starting: str | None = None,
        chains: tuple[str, ...] = ("chain-commit", "chain-merge"),
    ) -> list[dict[str, object]]:
        result: list[dict[str, object]] = [
            {
                "type": "run_started",
                "run_id": self.run_dir.name,
                "repo": str(self.repo),
                "repo_head": starting or self.starting,
            }
        ]
        result.extend(
            {
                "type": "decision",
                "id": f"landing-{chain_id}",
                "outcome": "chain-landing",
                "binding": {"source_record": {"chain_id": chain_id}},
            }
            for chain_id in chains
        )
        result.append(
            {
                "type": "run_closed",
                "judgment": judgment,
                "recorded_at": recorded_at,
                "validation": dict(GATED_PAYLOAD),
            }
        )
        return result

    def package(self, *, commit_oid: str | None = None, merge_oid: str | None = None):
        commit_chain = SimpleNamespace(
            chain_id="chain-commit",
            family="commit",
            state={"commit_result": {"commit_sha": commit_oid or self.commit_landing}},
        )
        merge_chain = SimpleNamespace(
            chain_id="chain-merge",
            family="merge",
            state={"integration": {"push": {"landed_head": merge_oid or self.merge_landing}}},
        )
        return SimpleNamespace(chains=(commit_chain, merge_chain), tombstones=())

    def evidence(
        self,
        *,
        records: list[dict[str, object]] | None = None,
        closing: str | None = None,
        archive_head: str | None = None,
        package: object | None = None,
        documents: tuple[object, ...] | None = None,
    ):
        approved_archive = archive_head or self.archive_head
        mode = CLOSING.ClosingMode(
            closing or self.closing,
            backfill_approval="approval-run:decision-01",
            archive_head=approved_archive,
            backfill_reason="operator approved historical recovery",
        )
        return CLOSING.BackfillEvidence(
            self.repo,
            records or self.records(),
            package or self.package(),
            documents
            if documents is not None
            else (SimpleNamespace(label="stable-plan", path=self.repo / "basis.md"),),
            mode,
            approved_archive,
            self.run_git,
        )

    def assert_refusal(self, expected: str, callback) -> None:
        with self.assertRaises(CLOSING.ArchiveRefusal) as raised:
            callback()
        self.assertEqual(raised.exception.message, expected)


class BackfillControlContractTests(GitBackfillFixture):
    def test_control_order_and_refusal_vocabulary_are_exact(self) -> None:
        self.assertEqual(CLOSING.BACKFILL_CONTROLS, CONTROLS)
        self.assertEqual(len(REFUSALS), len(CONTROLS))

    def test_valid_real_graph_proves_all_controls(self) -> None:
        CLOSING.prove_backfill_controls(self.evidence())

    def test_commit_and_merge_landing_oids_are_extracted(self) -> None:
        landed = CLOSING._enumerate_landed_commits(self.evidence())
        self.assertEqual(landed, (self.commit_landing, self.merge_landing))

    def test_tombstoned_landing_is_excluded(self) -> None:
        package = self.package()
        package = SimpleNamespace(
            chains=(package.chains[0],),
            tombstones=(SimpleNamespace(chain_id="chain-merge"),),
        )
        evidence = self.evidence(package=package)
        self.assertEqual(CLOSING._enumerate_landed_commits(evidence), (self.commit_landing,))

    def test_each_nonapproval_control_has_a_disable_in_memory_leg(self) -> None:
        evidence = self.evidence()
        for position, control in enumerate(CONTROLS[1:], start=1):
            disabled = tuple(item for item in CONTROLS if item != control)
            expected = REFUSALS[position]
            if control == "basis-stability":
                expected = expected.replace("<label>", "stable-plan")
            with self.subTest(control=control), mock.patch.object(
                CLOSING, "BACKFILL_CONTROLS", disabled
            ):
                self.assert_refusal(
                    expected, lambda: CLOSING.prove_backfill_controls(evidence)
                )

    def test_approval_control_has_a_disable_in_memory_leg(self) -> None:
        services = SimpleNamespace()
        with mock.patch.object(CLOSING, "BACKFILL_CONTROLS", CONTROLS[1:]):
            self.assert_refusal(
                APPROVAL_REFUSAL,
                lambda: CLOSING.backfill_closing_mode(
                    self.repo,
                    self.run_dir,
                    self.records(),
                    self.closing,
                    "approval-run:decision-01",
                    services,
                ),
            )

    def test_first_failed_control_supplies_the_only_refusal(self) -> None:
        bad_records = self.records(starting=self.side)
        evidence = replace(self.evidence(records=bad_records), archiving_head=self.side)
        self.assert_refusal(
            REFUSALS[1], lambda: CLOSING.prove_backfill_controls(evidence)
        )


class BackfillProofFailureTests(GitBackfillFixture):
    def test_archive_head_binding_refuses_mismatch(self) -> None:
        evidence = self.evidence()
        evidence = replace(evidence, archiving_head=self.starting)
        self.assert_refusal(REFUSALS[1], lambda: CLOSING.prove_backfill_controls(evidence))

    def test_passed_run_refuses_equal_heads(self) -> None:
        evidence = self.evidence(closing=self.archive_head)
        self.assert_refusal(REFUSALS[2], lambda: CLOSING.prove_backfill_controls(evidence))

    def test_archive_ancestry_refuses_unrelated_closing(self) -> None:
        evidence = self.evidence(closing=self.side)
        self.assert_refusal(REFUSALS[3], lambda: CLOSING.prove_backfill_controls(evidence))

    def test_starting_ancestry_refuses_unrelated_start(self) -> None:
        evidence = self.evidence(records=self.records(starting=self.side))
        self.assert_refusal(REFUSALS[4], lambda: CLOSING.prove_backfill_controls(evidence))

    def test_landing_enumeration_refuses_missing_chain(self) -> None:
        package = SimpleNamespace(chains=(), tombstones=())
        evidence = self.evidence(package=package)
        self.assert_refusal(REFUSALS[5], lambda: CLOSING.prove_backfill_controls(evidence))

    def test_landing_containment_names_the_uncontained_oid(self) -> None:
        evidence = self.evidence(package=self.package(commit_oid=self.archive_head))
        expected = REFUSALS[6].replace("<full-object-id>", self.archive_head)
        self.assert_refusal(expected, lambda: CLOSING.prove_backfill_controls(evidence))

    def test_basis_stability_names_the_changed_document(self) -> None:
        document = SimpleNamespace(label="unstable-plan", path=self.repo / "unstable.md")
        evidence = self.evidence(documents=(document,))
        expected = REFUSALS[7].replace("<label>", "unstable-plan")
        self.assert_refusal(expected, lambda: CLOSING.prove_backfill_controls(evidence))

    def test_closing_time_refuses_commit_after_close(self) -> None:
        records = self.records(recorded_at="2026-01-01T00:02:30Z")
        evidence = self.evidence(records=records)
        self.assert_refusal(REFUSALS[8], lambda: CLOSING.prove_backfill_controls(evidence))

    def test_closing_identification_refuses_successor_not_after_close(self) -> None:
        records = self.records(recorded_at="2026-01-01T00:05:00Z")
        evidence = self.evidence(records=records)
        self.assert_refusal(REFUSALS[9], lambda: CLOSING.prove_backfill_controls(evidence))

    def test_archive_time_refuses_nonmonotonic_archive_timestamp(self) -> None:
        evidence = self.evidence(archive_head=self.early_archive)
        self.assert_refusal(REFUSALS[10], lambda: CLOSING.prove_backfill_controls(evidence))

    def test_blocked_admission_refuses_unknown_judgment(self) -> None:
        evidence = self.evidence(records=self.records(judgment="failed"))
        self.assert_refusal(REFUSALS[11], lambda: CLOSING.prove_backfill_controls(evidence))


class BackfillModeTests(GitBackfillFixture):
    def approval_evidence(self, resolution: str):
        return SimpleNamespace(decision={"resolution": resolution})

    def closing_services(self):
        def only_record(records, kind):
            matches = [record for record in records if record.get("type") == kind]
            if len(matches) != 1:
                raise CLOSING.ArchiveRefusal("fixture invalid")
            return matches[0]

        return CLOSING.ClosingServices(
            self.run_git,
            lambda _path: ([], b""),
            only_record,
            lambda _code: None,
            frozenset({"legacy-approval"}),
        )

    def resolution(self, *, target: str | None = None, judgment: str = "passed") -> str:
        return (
            f"backfill-archive: {target or self.run_dir.name} closing HEAD {self.closing}; "
            f"archive HEAD {self.archive_head}; judgment {judgment}; approved history"
        )

    def test_approval_resolution_binds_target_heads_judgment_and_reason(self) -> None:
        evidence = self.approval_evidence(self.resolution())
        with mock.patch.object(CLOSING, "_approval_evidence", return_value=evidence):
            mode = CLOSING.backfill_closing_mode(
                self.repo,
                self.run_dir,
                self.records(),
                self.closing,
                "approval-run:decision-01",
                self.closing_services(),
            )
        self.assertEqual(mode.archive_head, self.archive_head)
        self.assertEqual(mode.backfill_reason, "approved history")
        self.assertTrue(mode.is_backfill)

    def test_real_open_owned_activated_approval_is_accepted(self) -> None:
        approval_run = "run-backfill-approval"
        resolution = self.resolution()
        environment = {"FORGE_SESSION_PID": str(os.getpid())}
        with mock.patch.dict(os.environ, environment):
            ARCHIVE.journal_builders.run_open(
                self.repo,
                approval_run,
                idempotency_key=hashlib.sha256(b"open approval").hexdigest(),
                goal="Approve one retrospective archive",
                scope=["basis.md"],
                plugin_ref="forge-backfill-test",
            )
            outcome = ARCHIVE.journal_builders.decision_add(
                self.repo,
                approval_run,
                idempotency_key=hashlib.sha256(b"approval decision").hexdigest(),
                resolution=resolution,
                task=None,
                finding=None,
                outcome="operator_approval",
                risk=None,
                basis=(),
                binding_chain=None,
                binding_id=None,
            )
            token = f"{approval_run}:{outcome.records[0]['id']}"
            services = replace(
                self.closing_services(),
                stable_journal_snapshot=ARCHIVE.stable_journal_snapshot,
            )
            mode = CLOSING.backfill_closing_mode(
                self.repo,
                self.run_dir,
                self.records(),
                self.closing,
                token,
                services,
            )
        self.assertEqual(mode.backfill_approval, token)

    def test_approval_resolution_mismatch_uses_one_literal(self) -> None:
        cases = (
            self.resolution(target="another-run"),
            self.resolution().replace(self.closing, self.starting, 1),
            self.resolution(judgment="blocked"),
            self.resolution() + "\nsecond line",
        )
        for resolution in cases:
            evidence = self.approval_evidence(resolution)
            with self.subTest(resolution=resolution), mock.patch.object(
                CLOSING, "_approval_evidence", return_value=evidence
            ):
                self.assert_refusal(
                    APPROVAL_REFUSAL,
                    lambda: CLOSING.backfill_closing_mode(
                        self.repo,
                        self.run_dir,
                        self.records(),
                        self.closing,
                        "approval-run:decision-01",
                        self.closing_services(),
                    ),
                )

    def test_blocked_equal_heads_are_admitted_only_in_backfill(self) -> None:
        records = self.records(
            judgment="blocked", recorded_at="2026-01-01T00:07:00Z"
        )
        evidence = self.evidence(
            records=records, closing=self.archive_head, archive_head=self.archive_head
        )
        CLOSING.prove_backfill_controls(evidence)
        CLOSING.require_passed_without_backfill(evidence.closing, "blocked")

    def test_normal_and_legacy_modes_refuse_blocked_judgment(self) -> None:
        modes = (
            CLOSING.ClosingMode(self.closing),
            CLOSING.ClosingMode(
                self.closing, legacy_approval="recovery-run:decision-01"
            ),
        )
        for mode in modes:
            with self.subTest(mode=mode):
                self.assert_refusal(
                    BLOCKED_REFUSAL,
                    lambda mode=mode: CLOSING.require_passed_without_backfill(
                        mode, "blocked"
                    ),
                )

    def test_malformed_normal_journal_precedes_blocked_admission(self) -> None:
        records = self.records(judgment="blocked")
        records[0]["run_id"] = "wrong-run"
        self.assert_refusal(
            "forge: archive refused — invalid run journal",
            lambda: ARCHIVE.render_archive(
                repo=self.repo,
                run_dir=self.run_dir,
                records=records,
                closing=CLOSING.ClosingMode(self.closing),
                post_close=dict(GATED_PAYLOAD),
                audit_fragment="## Commitment audit\n",
                package=ARCHIVE.ChainPackage(None, None, (), ()),
                bindings=ARCHIVE.binding_history.ResolvedBindings({}, {}),
                discrepancies=[],
                documents=(),
            ),
        )

    def test_legacy_approval_refusal_precedes_blocked_admission(self) -> None:
        options = CLOSING.ClosingOptions(None, "not-an-oid", "run:decision", None, None)
        self.assert_refusal(
            CLOSING.LEGACY_APPROVAL_REFUSAL,
            lambda: CLOSING.closing_mode_from_options(
                self.repo,
                self.run_dir,
                self.records(judgment="blocked"),
                options,
                self.closing_services(),
            ),
        )


class BackfillValidationPrecedenceTests(GitBackfillFixture):
    def render_with_payloads(
        self,
        *,
        embedded: dict[str, object],
        supplied: dict[str, object],
        fresh_pre: dict[str, object],
        fresh_post: dict[str, object],
    ) -> None:
        records = self.records(judgment="blocked")
        records[-1]["validation"] = embedded
        closing = CLOSING.ClosingMode(
            self.closing,
            backfill_approval="approval-run:decision-01",
            archive_head=self.archive_head,
            backfill_reason="approved history",
        )
        completed = subprocess.CompletedProcess([], 0, b"", b"")
        patches = (
            mock.patch.object(
                ARCHIVE,
                "stable_archive_journal_snapshot",
                return_value=(records, b"fixture\n", None),
            ),
            mock.patch.object(
                ARCHIVE.closing_engine,
                "closing_mode_from_options",
                return_value=closing,
            ),
            mock.patch.object(ARCHIVE, "run_git", return_value=completed),
            mock.patch.object(ARCHIVE, "read_json_file", return_value=supplied),
            mock.patch.object(ARCHIVE, "run_audit", return_value="audit\n"),
            mock.patch.object(
                ARCHIVE, "recompute_pre_close_validation", return_value=fresh_pre
            ),
            mock.patch.object(ARCHIVE, "validate_run", return_value=fresh_post),
        )
        with contextlib.ExitStack() as stack:
            for patcher in patches:
                stack.enter_context(patcher)
            ARCHIVE._render_archive_candidate(
                repo=self.repo,
                run_dir=self.run_dir,
                closing_head=None,
                legacy_recovered_head=None,
                legacy_approval=None,
                backfill_closing_head=self.closing,
                backfill_approval="approval-run:decision-01",
                archiving_head=self.archive_head,
                post_close_validation=self.base / "post-close.json",
                dispense_targets=(),
                dispense_reason=None,
                prove_legacy_approval=True,
            )

    def assert_validation_refusal(self, expected: str, **payloads) -> None:
        self.assert_refusal(expected, lambda: self.render_with_payloads(**payloads))

    def test_validation_refusals_have_declared_precedence(self) -> None:
        failing = {**GATED_PAYLOAD, "ok": False}
        cases = (
            (
                "forge: archive refused — pre-close gated validation did not pass",
                failing,
                failing,
                failing,
                failing,
            ),
            (
                "forge: archive refused — post-close gated validation did not pass",
                GATED_PAYLOAD,
                failing,
                failing,
                failing,
            ),
            (
                "forge: archive refused — pre-close gated validation is stale or does not "
                "match journal",
                GATED_PAYLOAD,
                GATED_PAYLOAD,
                failing,
                failing,
            ),
            (
                "forge: archive refused — post-close gated validation is stale or does not "
                "match journal",
                GATED_PAYLOAD,
                GATED_PAYLOAD,
                GATED_PAYLOAD,
                failing,
            ),
        )
        for expected, embedded, supplied, fresh_pre, fresh_post in cases:
            with self.subTest(expected=expected):
                self.assert_validation_refusal(
                    expected,
                    embedded=dict(embedded),
                    supplied=dict(supplied),
                    fresh_pre=dict(fresh_pre),
                    fresh_post=dict(fresh_post),
                )

    def test_approval_binding_precedes_validation(self) -> None:
        with mock.patch.object(
            ARCHIVE, "stable_archive_journal_snapshot", return_value=(self.records(), b"", None)
        ), mock.patch.object(
            ARCHIVE.closing_engine,
            "closing_mode_from_options",
            side_effect=CLOSING.ArchiveRefusal(APPROVAL_REFUSAL),
        ):
            self.assert_refusal(
                APPROVAL_REFUSAL,
                lambda: ARCHIVE._render_archive_candidate(
                    repo=self.repo,
                    run_dir=self.run_dir,
                    closing_head=None,
                    legacy_recovered_head=None,
                    legacy_approval=None,
                    backfill_closing_head=self.closing,
                    backfill_approval="approval-run:decision-01",
                    archiving_head=self.archive_head,
                    post_close_validation=self.base / "missing.json",
                    dispense_targets=(),
                    dispense_reason=None,
                    prove_legacy_approval=True,
                ),
            )

    def test_validation_refusal_precedes_remaining_backfill_controls(self) -> None:
        failing = {**GATED_PAYLOAD, "ok": False}
        with mock.patch.object(
            ARCHIVE.closing_engine,
            "prove_backfill_controls",
            side_effect=AssertionError("control proofs ran before validation"),
        ) as prove:
            self.assert_validation_refusal(
                "forge: archive refused — pre-close gated validation did not pass",
                embedded=failing,
                supplied=dict(GATED_PAYLOAD),
                fresh_pre=dict(GATED_PAYLOAD),
                fresh_post=dict(GATED_PAYLOAD),
            )
        prove.assert_not_called()


class BackfillBasisDiscoveryTests(GitBackfillFixture):
    def test_real_renderer_checks_basis_deleted_after_closing(self) -> None:
        path = self.run_dir / "basis.md"
        path.write_text("run-scoped basis\n", encoding="utf-8")
        closing_head = self.commit("run-basis-closing", "2026-01-01T00:07:00+00:00")
        path.unlink()
        archive_head = self.commit("run-basis-deleted", "2026-01-01T00:09:00+00:00")
        records = self.records(recorded_at="2026-01-01T00:08:00Z", chains=())
        records.insert(
            -1,
            {
                "type": "decision",
                "id": "basis-decision",
                "outcome": "operator_decision",
                "basis": ["basis.md"],
            },
        )
        raw = b"".join(
            json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
            + b"\n"
            for record in records
        )
        closing = CLOSING.ClosingMode(
            closing_head,
            backfill_approval="approval-run:decision-01",
            archive_head=archive_head,
            backfill_reason="approved history",
        )
        package = ARCHIVE.ChainPackage(None, None, (), ())

        def render():
            patches = (
                mock.patch.object(
                    ARCHIVE,
                    "stable_archive_journal_snapshot",
                    return_value=(records, raw, None),
                ),
                mock.patch.object(
                    ARCHIVE.closing_engine,
                    "closing_mode_from_options",
                    return_value=closing,
                ),
                mock.patch.object(ARCHIVE, "read_json_file", return_value=GATED_PAYLOAD),
                mock.patch.object(ARCHIVE, "run_audit", return_value="audit\n"),
                mock.patch.object(
                    ARCHIVE, "recompute_pre_close_validation", return_value=GATED_PAYLOAD
                ),
                mock.patch.object(ARCHIVE, "validate_run", return_value=GATED_PAYLOAD),
                mock.patch.object(
                    ARCHIVE, "capture_archive_chain_package", return_value=package
                ),
                mock.patch.object(
                    ARCHIVE,
                    "resolve_archive_bindings",
                    return_value=ARCHIVE.binding_history.ResolvedBindings({}, {}),
                ),
                mock.patch.object(ARCHIVE, "legacy_discrepancies", return_value=[]),
                mock.patch.object(ARCHIVE, "tombstone_discrepancies", return_value=[]),
            )
            with contextlib.ExitStack() as stack:
                for patcher in patches:
                    stack.enter_context(patcher)
                return ARCHIVE._render_archive_candidate(
                    repo=self.repo,
                    run_dir=self.run_dir,
                    closing_head=None,
                    legacy_recovered_head=None,
                    legacy_approval=None,
                    backfill_closing_head=closing_head,
                    backfill_approval="approval-run:decision-01",
                    archiving_head=archive_head,
                    post_close_validation=self.base / "post-close.json",
                    dispense_targets=(),
                    dispense_reason=None,
                    prove_legacy_approval=True,
                )

        expected = REFUSALS[7].replace("<label>", "basis.md")
        self.assert_refusal(expected, render)
        real_basis_documents = ARCHIVE.basis_documents

        def without_missing_references(*args, **kwargs):
            kwargs.pop("basis_references", None)
            return real_basis_documents(*args, **kwargs)

        with mock.patch.object(
            ARCHIVE, "basis_documents", side_effect=without_missing_references
        ):
            rendered = render()
        self.assertIn(b"Backfill closing HEAD:", rendered)


class BackfillCallerSurfaceTests(GitBackfillFixture):
    def direct_arguments(self, *extra: str) -> argparse.Namespace:
        return ARCHIVE.parser().parse_args(
            [
                "--run-dir",
                str(self.run_dir),
                "--post-close-validation",
                str(self.base / "post-close.json"),
                *extra,
            ]
        )

    def cli_arguments(self, *extra: str) -> argparse.Namespace:
        return CLI_PARSER.build_parser().parse_args(
            ["commit", "start", "--archive-run-id", self.run_dir.name, *extra]
        )

    def direct_semantic_refusal(self, expected: str, *extra: str) -> None:
        arguments = self.direct_arguments(*extra)
        failure = AssertionError("repository discovery preceded option validation")
        with mock.patch.object(
            ARCHIVE, "repository_root", side_effect=failure
        ):
            self.assert_refusal(expected, lambda: ARCHIVE.archive(arguments))

    def cli_semantic_refusal(self, expected: str, *extra: str) -> None:
        arguments = self.cli_arguments(*extra)
        for validator in (
            CLI_OPTIONS._validate_commit_start_closing_options,
            CLI_DISPATCH._validate_commit_start_closing_options,
        ):
            with self.subTest(validator=validator.__module__):
                with self.assertRaises(CLI_OPTIONS.Refusal) as raised:
                    validator(arguments)
                self.assertEqual(raised.exception.message, expected)

    def test_both_parsers_accept_the_complete_backfill_pair(self) -> None:
        flags = (
            "--backfill-closing-head",
            self.closing,
            "--backfill-approval",
            "approval-run:decision-01",
        )
        direct = self.direct_arguments(*flags)
        cli = self.cli_arguments(*flags)
        self.assertEqual(direct.backfill_closing_head, self.closing)
        self.assertEqual(cli.backfill_closing_head, self.closing)
        self.assertEqual(direct.backfill_approval, "approval-run:decision-01")
        self.assertEqual(cli.backfill_approval, "approval-run:decision-01")

    def test_half_pair_refuses_identically_on_both_callers(self) -> None:
        incomplete = (
            ("--backfill-closing-head", self.closing),
            ("--backfill-approval", "approval-run:decision-01"),
        )
        for flags in incomplete:
            with self.subTest(flags=flags):
                self.direct_semantic_refusal(APPROVAL_REFUSAL, *flags)
                self.cli_semantic_refusal(APPROVAL_REFUSAL, *flags)

    def test_normal_mode_conflict_refuses_identically_on_both_callers(self) -> None:
        flags = (
            "--closing-head",
            self.closing,
            "--backfill-closing-head",
            self.closing,
            "--backfill-approval",
            "approval-run:decision-01",
        )
        self.direct_semantic_refusal(MODE_CONFLICT, *flags)
        self.cli_semantic_refusal(MODE_CONFLICT, *flags)

    def test_legacy_mode_conflict_refuses_identically_on_both_callers(self) -> None:
        flags = (
            "--legacy-recovered-head",
            self.closing,
            "--legacy-approval",
            "recovery-run:decision-01",
            "--backfill-closing-head",
            self.closing,
            "--backfill-approval",
            "approval-run:decision-01",
        )
        self.direct_semantic_refusal(MODE_CONFLICT, *flags)
        self.cli_semantic_refusal(MODE_CONFLICT, *flags)

    def test_conflict_precedes_half_pair_refusal(self) -> None:
        flags = ("--closing-head", self.closing, "--backfill-closing-head", self.closing)
        self.direct_semantic_refusal(MODE_CONFLICT, *flags)
        self.cli_semantic_refusal(MODE_CONFLICT, *flags)

    def test_cli_policy_lookup_is_pinned_to_captured_archiving_head(self) -> None:
        pinned = "a" * 40
        repository = SimpleNamespace(
            root=self.repo,
            staged_paths=lambda: [],
            head=mock.Mock(return_value="b" * 40),
            policy=mock.Mock(side_effect=RuntimeError("stop after policy lookup")),
        )
        store = SimpleNamespace(admission_lock=lambda _root: contextlib.nullcontext())
        command = SimpleNamespace(
            ctx=SimpleNamespace(repo=repository, store=store),
            _live_chain=lambda: None,
        )
        metadata = {"archiving_head": pinned, "backfill_approval": "approval:decision"}
        with patch_engine("_run_halt"), patch_engine(
            "_prepare_archive_candidate", return_value=(["archive.md"], metadata)
        ), self.assertRaisesRegex(RuntimeError, "stop after policy lookup"):
            CLI_LIFECYCLE.start(command, (), None, archive_run_id="run-backfill")
        repository.policy.assert_called_once_with(pinned)

    def test_backfill_provenance_lines_are_byte_exact(self) -> None:
        mode = self.evidence().closing
        rendered = "\n".join(CLOSING.provenance_lines(mode))
        self.assertEqual(
            rendered,
            f"Backfill closing HEAD: {self.closing}\n\n"
            f"Archiving HEAD: {self.archive_head}\n\n"
            "Backfill approval: approval-run:decision-01\n\n"
            "Backfill reason: operator approved historical recovery\n\n"
            "Closing-head status: recovered after run_closed; not a contemporaneous "
            "FR-172 capture\n",
        )


class BackfillArchiveChainEndToEndTests(cli_fixture.ForgeCLIFixture):
    def dated_commit(self, message: str, when: str) -> str:
        environment = self.environment(
            GIT_AUTHOR_DATE=when,
            GIT_COMMITTER_DATE=when,
        )
        result = subprocess.run(
            ["git", "commit", "--quiet", "-m", message],
            cwd=self.repo,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return self.git("rev-parse", "HEAD")

    def invoke_archive_cli(self, *arguments: str) -> dict[str, object]:
        session_pid = str(os.getpid())
        result = subprocess.run(
            [
                sys.executable, "-c", cli_fixture.CLI_TEST_BOOTSTRAP,
                str(cli_fixture.CLI), str(self.helpers), str(ROOT),
                str(self.helpers / "fake-codex"), str(self.helpers / "fake-claude"),
                "--json", "--repo", str(self.repo),
                *arguments,
            ],
            cwd=self.repo,
            env=self.environment(FORGE_SESSION_PID=session_pid),
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def target_records(self, run_id: str, starting: str) -> list[dict[str, object]]:
        observation = "PASS; 0 CRITICAL/MAJOR findings; iteration 2 of 8."
        opening = {
            "type": "run_started", "run_id": run_id, "goal": "Archive one historical run",
            "repo": str(self.repo.resolve()), "repo_head": starting,
        }
        task = {
            "type": "task", "id": "task-01", "status": "active",
            "goal": "Archive the historical run", "acceptance": ["Bytes match."],
        }
        checks = [
            {
                "type": "verification", "id": f"check-{number}", "task": "task-01",
                "criterion": f"gate-{number}: fixture gate", "check": "fixture check",
                "result": "passed", "observation": observation,
            }
            for number in range(1, 4)
        ]
        complete = {
            "type": "task", "id": "task-01", "status": "complete",
            "outcome": "Archive evidence is complete.",
        }
        closed = {
            "type": "run_closed", "judgment": "passed",
            "recorded_at": "2026-01-01T00:04:00Z",
            "validation": dict(GATED_PAYLOAD), "risks": [], "follow_ups": [],
        }
        return [opening, task, *checks, complete, closed]

    def test_unmocked_archive_chain_matches_direct_backfill_render(self) -> None:
        starting = self.git("rev-parse", "HEAD")
        (self.repo / ".gitignore").write_text(
            "/.codex-orchestrator/\n/.forge/chains/\n/.forge/tmp/\n",
            encoding="utf-8",
        )
        self.git("add", ".gitignore")
        closing = self.dated_commit("closing head", "2026-01-01T00:03:00+00:00")
        (self.repo / "docs/guide.md").write_text(
            "# Guide\n\nArchive successor.\n", encoding="utf-8"
        )
        self.git("add", "docs/guide.md")
        archiving = self.dated_commit(
            "archive successor", "2026-01-01T00:05:00+00:00"
        )

        run_id = "run-backfill-chain-e2e"
        run_dir = self.repo / ".codex-orchestrator/runs" / run_id
        run_dir.mkdir(parents=True)
        approval_run = "run-backfill-chain-approval"
        resolution = (
            f"backfill-archive: {run_id} closing HEAD {closing}; "
            f"archive HEAD {archiving}; judgment passed; end-to-end approval"
        )
        with mock.patch.dict(os.environ, {"FORGE_SESSION_PID": str(os.getpid())}):
            ARCHIVE.journal_builders.run_open(
                self.repo,
                approval_run,
                idempotency_key=hashlib.sha256(b"open e2e approval").hexdigest(),
                goal="Approve one backfill archive",
                scope=["docs/guide.md"],
                plugin_ref="forge-backfill-test",
            )
            decision = ARCHIVE.journal_builders.decision_add(
                self.repo,
                approval_run,
                idempotency_key=hashlib.sha256(b"e2e approval").hexdigest(),
                resolution=resolution,
                task=None,
                finding=None,
                outcome="operator_approval",
                risk=None,
                basis=(),
                binding_chain=None,
                binding_id=None,
            )
            approval = f"{approval_run}:{decision.records[0]['id']}"
            records = self.target_records(run_id, starting)
            (run_dir / "journal.jsonl").write_text(
                "".join(
                    json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
                    for record in records
                ),
                encoding="utf-8",
            )
            post_close = run_dir / "post-close-validation.json"
            post_close.write_text(
                json.dumps(GATED_PAYLOAD, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            direct = ARCHIVE.render_archive_candidate(
                repo=self.repo,
                run_dir=run_dir,
                closing_head=None,
                legacy_recovered_head=None,
                legacy_approval=None,
                backfill_closing_head=closing, backfill_approval=approval,
                archiving_head=archiving,
                post_close_validation=post_close,
            )

        helper_names = (
            "archive-run.py", "audit-commitments.py",
            "archive_closing.py", "commitment_paths.py",
        )
        for name in helper_names:
            (self.helpers / name).symlink_to(FORGE_SCRIPTS / name)
        started = self.invoke_archive_cli(
            "commit",
            "start",
            "--archive-run-id",
            run_id,
            "--backfill-closing-head",
            closing,
            "--backfill-approval",
            approval,
        )
        chain_id = str(started["chain_id"])
        metadata = self.state(chain_id)["staging"]["archive"]
        self.assertEqual(metadata["archiving_head"], archiving)
        self.assertEqual(metadata["backfill_approval"], approval)
        self.invoke_archive_cli("--chain-id", chain_id, "verify")
        self.invoke_archive_cli(
            "--chain-id", chain_id, "commit", "finalize",
            "--message", "Archive historical run",
        )
        committed = self.git_bytes(
            "show", f"HEAD:.forge/history/runs/{run_id}.md"
        )
        self.assertEqual(committed, direct)


def load_tests(loader, suite, _pattern):
    from tests import archive_backfill_regressions

    suite.addTests(loader.loadTestsFromModule(archive_backfill_regressions))
    return suite


if __name__ == "__main__":
    unittest.main()
