"""Adversarial regression coverage for Revision-19 archive backfill."""

from __future__ import annotations

import contextlib
import hashlib
import inspect
import json
import os
import subprocess
import textwrap
from types import FunctionType, SimpleNamespace
from unittest import mock

from tests import test_archive_backfill as support
from tests._cli_loader import package_module

ARCHIVE = support.ARCHIVE
CLOSING = support.CLOSING
APPROVAL_REFUSAL = support.APPROVAL_REFUSAL
GATED_PAYLOAD = support.GATED_PAYLOAD
REFUSALS = support.REFUSALS
REPOSITORY_REFUSAL = support.REPOSITORY_REFUSAL
_DEFAULT_OWNER = object()


def mutated_function(
    function: FunctionType, anchor: str, replacement: str
) -> FunctionType:
    """Compile one exact in-memory mutant with production globals."""

    source = textwrap.dedent(inspect.getsource(function))
    if source.count(anchor) != 1:
        raise AssertionError(f"mutation anchor drifted for {function.__name__}")
    namespace = dict(function.__globals__)
    exec(
        compile(
            source.replace(anchor, replacement, 1),
            function.__code__.co_filename,
            "exec",
        ),
        namespace,
    )
    mutant = namespace[function.__name__]
    if not isinstance(mutant, FunctionType):
        raise AssertionError(f"mutation did not define {function.__name__}")
    return mutant


class RecordedRepositoryBackfillTests(support.GitBackfillFixture):
    def test_safe_absent_worktree_has_exact_provenance(self) -> None:
        recorded = self.repo / ".worktrees/retired-task"
        self.assertEqual(
            ARCHIVE.recorded_repository_provenance(
                self.repo, self.run_dir, str(recorded)
            ),
            "Recorded repository: absent worktree .worktrees/retired-task; "
            "resolved to the state root",
        )

    def test_absent_worktree_line_immediately_follows_starting_head(self) -> None:
        recorded = self.repo / ".worktrees/retired-task"
        records = [
            {
                "type": "run_started",
                "run_id": self.run_dir.name,
                "goal": "Archive one retired worktree run",
                "repo": str(recorded),
                "repo_head": self.starting,
            },
            {
                "type": "run_closed",
                "judgment": "passed",
                "validation": dict(GATED_PAYLOAD),
                "risks": [],
                "follow_ups": [],
            },
        ]
        rendered = ARCHIVE.render_archive(
            repo=self.repo,
            run_dir=self.run_dir,
            records=records,
            closing=CLOSING.ClosingMode(self.archive_head),
            post_close=dict(GATED_PAYLOAD),
            audit_fragment="## Commitment audit\n\nNone.\n",
            package=ARCHIVE.ChainPackage(None, None, (), ()),
            bindings=ARCHIVE.binding_history.ResolvedBindings({}, {}),
            discrepancies=[],
            documents=(),
        )
        expected = (
            f"Starting HEAD: {self.starting}\n\n"
            "Recorded repository: absent worktree .worktrees/retired-task; "
            "resolved to the state root\n\n"
            f"Closing HEAD: {self.archive_head}"
        )
        self.assertIn(expected, rendered)

    def test_hostile_absent_path_refuses(self) -> None:
        recorded = self.base / "outside-state-root"
        self.assert_refusal(
            REPOSITORY_REFUSAL,
            lambda: ARCHIVE.recorded_repository_provenance(
                self.repo, self.run_dir, str(recorded)
            ),
        )

    def test_present_linked_worktree_does_not_match_main_checkout(self) -> None:
        linked = self.repo / ".worktrees/linked-task"
        result = subprocess.run(
            [
                "git",
                "worktree",
                "add",
                "--quiet",
                "-b",
                "backfill-linked",
                str(linked),
                self.archive_head,
            ],
            cwd=self.repo,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_refusal(
            REPOSITORY_REFUSAL,
            lambda: ARCHIVE.recorded_repository_provenance(
                self.repo, self.run_dir, str(linked)
            ),
        )

    def test_absent_worktree_control_has_disable_in_memory_leg(self) -> None:
        recorded = self.repo / ".worktrees/retired-task"
        resolver = ARCHIVE.recorded_repository_engine
        with mock.patch.object(resolver, "RECORDED_REPOSITORY_LEGS", frozenset()):
            self.assert_refusal(
                REPOSITORY_REFUSAL,
                lambda: ARCHIVE.recorded_repository_provenance(
                    self.repo, self.run_dir, str(recorded)
                ),
            )

    def test_c0_and_c1_absent_worktree_text_refuses_and_has_disable_leg(self) -> None:
        anchor = (
            "    if any(ord(character) <= 0x1F or 0x7F <= ord(character) <= 0x9F "
            "for character in rendered):\n"
        )
        mutant = mutated_function(
            ARCHIVE.recorded_repository_provenance,
            anchor,
            "    if False:\n",
        )
        for hostile in ("retired\x1f-task", "retired\x85-task"):
            recorded = self.repo / ".worktrees" / hostile
            with self.subTest(hostile=repr(hostile)):
                self.assert_refusal(
                    REPOSITORY_REFUSAL,
                    lambda recorded=recorded: ARCHIVE.recorded_repository_provenance(
                        self.repo, self.run_dir, str(recorded)
                    ),
                )
                rendered = mutant(self.repo, self.run_dir, str(recorded))
                self.assertIn(hostile, rendered)


class RendererPathRegressionTests(support.GitBackfillFixture):
    @contextlib.contextmanager
    def renderer_inputs(
        self,
        records: list[dict[str, object]],
        closing: object,
        package: object | None = None,
        documents: tuple[object, ...] = (),
    ):
        raw = b"".join(
            json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
            + b"\n"
            for record in records
        )
        captured = package or ARCHIVE.ChainPackage(None, None, (), ())
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
                ARCHIVE,
                "recompute_pre_close_validation",
                return_value=GATED_PAYLOAD,
            ),
            mock.patch.object(ARCHIVE, "validate_run", return_value=GATED_PAYLOAD),
            mock.patch.object(
                ARCHIVE, "capture_archive_chain_package", return_value=captured
            ),
            mock.patch.object(
                ARCHIVE,
                "resolve_archive_bindings",
                return_value=ARCHIVE.binding_history.ResolvedBindings({}, {}),
            ),
            mock.patch.object(ARCHIVE, "legacy_discrepancies", return_value=[]),
            mock.patch.object(ARCHIVE, "tombstone_discrepancies", return_value=[]),
            mock.patch.object(ARCHIVE, "basis_documents", return_value=documents),
            mock.patch.object(ARCHIVE, "run_git", wraps=ARCHIVE.run_git),
        )
        with contextlib.ExitStack() as stack:
            for patcher in patches:
                stack.enter_context(patcher)
            yield

    def render_candidate(
        self,
        records: list[dict[str, object]],
        closing: object,
        archiving_head: str,
    ) -> bytes:
        with self.renderer_inputs(records, closing):
            return ARCHIVE._render_archive_candidate(
                repo=self.repo,
                run_dir=self.run_dir,
                closing_head=None,
                legacy_recovered_head=None,
                legacy_approval=None,
                backfill_closing_head=(closing.head if closing.is_backfill else None),
                backfill_approval=(
                    closing.backfill_approval if closing.is_backfill else None
                ),
                archiving_head=archiving_head,
                post_close_validation=self.base / "post-close.json",
                dispense_targets=(),
                dispense_reason=None,
                prove_legacy_approval=True,
            )

    def test_real_renderer_invokes_backfill_controls(self) -> None:
        records = self.records(chains=())
        closing = CLOSING.ClosingMode(
            self.closing,
            backfill_approval="approval-run:decision-01",
            archive_head=self.archive_head,
            backfill_reason="approved history",
        )
        self.assert_refusal(
            REFUSALS[1],
            lambda: self.render_candidate(records, closing, self.starting),
        )
        with mock.patch.object(
            ARCHIVE.closing_engine, "prove_backfill_controls", return_value=None
        ):
            rendered = self.render_candidate(records, closing, self.starting)
        self.assertIn(b"Backfill closing HEAD:", rendered)

    def test_invalid_journal_precedes_blocked_admission_in_real_renderer(self) -> None:
        mode = CLOSING.ClosingMode(self.closing)
        cases = []
        wrong_run = self.records(judgment="blocked", chains=())
        wrong_run[0]["run_id"] = "wrong-run"
        cases.append(wrong_run)
        cases.append(self.records(judgment="bogus", chains=()))
        for records in cases:
            with self.subTest(closed=records[-1]):
                self.assert_refusal(
                    "forge: archive refused — invalid run journal",
                    lambda records=records: self.render_candidate(
                        records, mode, self.archive_head
                    ),
                )

    def test_blocked_equal_head_renders_through_real_candidate_path(self) -> None:
        records = self.records(
            judgment="blocked",
            recorded_at="2026-01-01T00:07:00Z",
            chains=(),
        )
        closing = CLOSING.ClosingMode(
            self.archive_head,
            backfill_approval="approval-run:decision-01",
            archive_head=self.archive_head,
            backfill_reason="approved blocked history",
        )
        rendered = self.render_candidate(records, closing, self.archive_head)
        self.assertIn(
            f"Backfill closing HEAD: {self.archive_head}".encode(), rendered
        )


class DirectArchiveEntryPointEndToEndTests(
    support.BackfillArchiveChainEndToEndTests
):
    test_unmocked_archive_chain_matches_direct_backfill_render = None

    def test_direct_archive_backfill_matches_unmocked_renderer(self) -> None:
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
        run_id = "run-direct-backfill-e2e"
        run_dir = self.repo / ".codex-orchestrator/runs" / run_id
        run_dir.mkdir(parents=True)
        approval_run = "run-direct-backfill-approval"
        resolution = (
            f"backfill-archive: {run_id} closing HEAD {closing}; "
            f"archive HEAD {archiving}; judgment passed; direct archive approval"
        )
        session_environment = {"FORGE_SESSION_PID": str(os.getpid())}
        with mock.patch.dict(os.environ, session_environment):
            ARCHIVE.journal_builders.run_open(
                self.repo,
                approval_run,
                idempotency_key=hashlib.sha256(b"open direct approval").hexdigest(),
                goal="Approve the direct backfill archive",
                scope=["docs/guide.md"],
                plugin_ref="forge-backfill-test",
            )
            decision = ARCHIVE.journal_builders.decision_add(
                self.repo,
                approval_run,
                idempotency_key=hashlib.sha256(b"direct approval").hexdigest(),
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
                json.dumps(GATED_PAYLOAD, sort_keys=True, separators=(",", ":"))
                + "\n",
                encoding="utf-8",
            )
            expected = ARCHIVE.render_archive_candidate(
                repo=self.repo,
                run_dir=run_dir,
                closing_head=None,
                legacy_recovered_head=None,
                legacy_approval=None,
                backfill_closing_head=closing,
                backfill_approval=approval,
                archiving_head=archiving,
                post_close_validation=post_close,
            )
            arguments = ARCHIVE.parser().parse_args(
                [
                    "--run-dir",
                    str(run_dir),
                    "--backfill-closing-head",
                    closing,
                    "--backfill-approval",
                    approval,
                    "--post-close-validation",
                    str(post_close),
                ]
            )
            self.assertEqual(arguments.backfill_closing_head, closing)
            self.assertEqual(arguments.backfill_approval, approval)
            with mock.patch.object(ARCHIVE, "repository_root", return_value=self.repo):
                relative = ARCHIVE.archive(arguments)

        self.assertEqual(self.git_bytes("show", f":{relative}"), expected)
        self.assertEqual(self.git("diff", "--cached", "--name-only"), relative)


class WriteAndStageHeadFenceTests(support.GitBackfillFixture):
    def setUp(self) -> None:
        super().setUp()
        (self.repo / ".gitignore").write_text(
            "/.codex-orchestrator/\n", encoding="utf-8"
        )
        self.expected_head = self.commit(
            "archive-fixture", "2026-01-01T00:07:00+00:00"
        )
        self.moved_head = self.commit_tree(
            self.expected_head, "2026-01-01T00:08:00+00:00"
        )
        self.relative = f".forge/history/runs/{self.run_dir.name}.md"
        self.arguments = ARCHIVE.parser().parse_args(
            [
                "--run-dir",
                str(self.run_dir),
                "--backfill-closing-head",
                self.closing,
                "--backfill-approval",
                "approval-run:decision-01",
                "--post-close-validation",
                str(self.base / "post-close.json"),
            ]
        )

    def move_head(self, new: str, old: str) -> None:
        self.git_text("update-ref", "HEAD", new, old)

    def assert_rolled_back(self) -> None:
        self.assertFalse((self.repo / self.relative).exists())
        self.assertEqual(self.git_text("diff", "--cached", "--name-only"), "")

    @contextlib.contextmanager
    def archive_patches(self, renderer):
        with mock.patch.object(
            ARCHIVE, "repository_root", return_value=self.repo
        ), mock.patch.object(
            ARCHIVE, "render_archive_candidate", side_effect=renderer
        ):
            yield

    def test_first_head_fence_runs_before_archive_creation(self) -> None:
        real_create = ARCHIVE.create_archive_file

        def renderer(**_kwargs):
            self.move_head(self.moved_head, self.expected_head)
            return b"archive\n"

        def restore_then_create(*args, **kwargs):
            self.move_head(self.expected_head, self.moved_head)
            return real_create(*args, **kwargs)

        with self.archive_patches(renderer), mock.patch.object(
            ARCHIVE, "create_archive_file", side_effect=restore_then_create
        ):
            self.assert_refusal(REFUSALS[1], lambda: ARCHIVE.archive(self.arguments))
        self.assert_rolled_back()

    def test_second_head_fence_runs_before_index_inspection(self) -> None:
        real_create = ARCHIVE.create_archive_file
        real_git_stdout = ARCHIVE.git_stdout
        moved = False

        def create_then_move(*args, **kwargs):
            nonlocal moved
            created = real_create(*args, **kwargs)
            self.move_head(self.moved_head, self.expected_head)
            moved = True
            return created

        def restore_before_cached(repo, *arguments):
            nonlocal moved
            if moved and arguments == ("diff", "--cached", "--name-only", "-z"):
                self.move_head(self.expected_head, self.moved_head)
                moved = False
            return real_git_stdout(repo, *arguments)

        with self.archive_patches(lambda **_kwargs: b"archive\n"), mock.patch.object(
            ARCHIVE, "create_archive_file", side_effect=create_then_move
        ), mock.patch.object(
            ARCHIVE, "git_stdout", side_effect=restore_before_cached
        ):
            self.assert_refusal(REFUSALS[1], lambda: ARCHIVE.archive(self.arguments))
        self.assert_rolled_back()

    def test_third_head_fence_runs_after_archive_only_stage_proof(self) -> None:
        real_git_stdout = ARCHIVE.git_stdout
        untracked_calls = 0

        def move_after_final_untracked(repo, *arguments):
            nonlocal untracked_calls
            result = real_git_stdout(repo, *arguments)
            if arguments == (
                "ls-files",
                "--others",
                "--exclude-standard",
                "-z",
            ):
                untracked_calls += 1
                if untracked_calls == 2:
                    self.move_head(self.moved_head, self.expected_head)
            return result

        with self.archive_patches(lambda **_kwargs: b"archive\n"), mock.patch.object(
            ARCHIVE, "git_stdout", side_effect=move_after_final_untracked
        ):
            self.assert_refusal(REFUSALS[1], lambda: ARCHIVE.archive(self.arguments))
        self.assertEqual(untracked_calls, 2)
        self.assert_rolled_back()


class ApprovalBindingSubcheckTests(support.GitBackfillFixture):
    def setUp(self) -> None:
        super().setUp()
        self.approval_run = "run-backfill-approval"
        self.approval_dir = self.run_dir.parent / self.approval_run
        self.approval_dir.mkdir()
        self.current_owner = SimpleNamespace(pid=41, host="fixture-host")
        self.owner_observation = ("owner-bytes", self.current_owner)

    def approval_records(self, run_id: str | None = None) -> list[dict[str, object]]:
        return [
            {
                "type": "run_started",
                "run_id": run_id or self.approval_run,
                "repo": str(self.repo),
                "scope": ["basis.md"],
            },
            {
                "type": "decision",
                "id": "decision-01",
                "outcome": "operator_approval",
                "resolution": (
                    f"backfill-archive: {self.run_dir.name} closing HEAD {self.closing}; "
                    f"archive HEAD {self.archive_head}; judgment passed; approved history"
                ),
            },
        ]

    def resolve_approval(
        self,
        records: list[dict[str, object]],
        *,
        token: str | None = None,
        active: bool = True,
        owner_observation: object = _DEFAULT_OWNER,
    ):
        services = CLOSING.ClosingServices(
            self.run_git,
            lambda _directory: (records, b"approval\n"),
            lambda values, kind: [
                value for value in values if value.get("type") == kind
            ][0],
            lambda _code: None,
            frozenset({"legacy-approval"}),
        )
        observed = (
            self.owner_observation
            if owner_observation is _DEFAULT_OWNER
            else owner_observation
        )
        with mock.patch.object(
            CLOSING.journal_engine, "_session_owner", return_value=self.current_owner
        ), mock.patch.object(
            CLOSING.journal_engine,
            "_read_owner_observation",
            return_value=observed,
        ), mock.patch.object(
            CLOSING.journal_engine,
            "writer_contract_active",
            return_value=active,
        ), mock.patch.object(
            CLOSING, "_replay_approval", return_value=None
        ), mock.patch.object(
            CLOSING, "_recheck_approval", return_value=None
        ):
            return CLOSING.backfill_closing_mode(
                self.repo,
                self.run_dir,
                self.records(),
                self.closing,
                token or f"{self.approval_run}:decision-01",
                services,
            )

    def test_closed_approval_run_refuses(self) -> None:
        records = self.approval_records()
        records.append({"type": "run_closed", "judgment": "passed"})
        self.assert_refusal(
            APPROVAL_REFUSAL, lambda: self.resolve_approval(records)
        )

    def test_non_operator_approval_outcome_refuses(self) -> None:
        records = self.approval_records()
        records[1]["outcome"] = "chain-approval"
        self.assert_refusal(
            APPROVAL_REFUSAL, lambda: self.resolve_approval(records)
        )

    def test_unactivated_approval_run_refuses(self) -> None:
        self.assert_refusal(
            APPROVAL_REFUSAL,
            lambda: self.resolve_approval(self.approval_records(), active=False),
        )

    def test_session_owner_mismatch_refuses(self) -> None:
        mismatches = (
            None,
            ("owner-bytes", SimpleNamespace(pid=42, host="fixture-host")),
            ("owner-bytes", SimpleNamespace(pid=41, host="other-host")),
        )
        for observed in mismatches:
            with self.subTest(observed=observed):
                self.assert_refusal(
                    APPROVAL_REFUSAL,
                    lambda observed=observed: self.resolve_approval(
                        self.approval_records(), owner_observation=observed
                    ),
                )

    def test_recorded_repository_mismatch_refuses(self) -> None:
        linked = self.repo / ".worktrees/approval-linked"
        result = subprocess.run(
            [
                "git",
                "worktree",
                "add",
                "--quiet",
                "-b",
                "approval-linked",
                str(linked),
                self.archive_head,
            ],
            cwd=self.repo,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        records = self.approval_records()
        records[0]["repo"] = str(linked)
        self.assert_refusal(
            APPROVAL_REFUSAL, lambda: self.resolve_approval(records)
        )

    def test_approval_run_must_differ_from_target(self) -> None:
        records = self.approval_records(self.run_dir.name)
        self.assert_refusal(
            APPROVAL_REFUSAL,
            lambda: self.resolve_approval(
                records, token=f"{self.run_dir.name}:decision-01"
            ),
        )

    def test_approval_snapshot_recheck_cannot_be_skipped(self) -> None:
        records = self.approval_records()

        def only_record(values, kind):
            return [value for value in values if value.get("type") == kind][0]

        services = CLOSING.ClosingServices(
            self.run_git,
            lambda _directory: (records, b"approval\n"),
            only_record,
            ARCHIVE.authoritative_discrepancy,
            frozenset({"legacy-approval"}),
        )

        def resolve():
            return CLOSING.backfill_closing_mode(
                self.repo,
                self.run_dir,
                self.records(),
                self.closing,
                f"{self.approval_run}:decision-01",
                services,
            )

        patches = (
            mock.patch.object(
                CLOSING.journal_engine,
                "_session_owner",
                return_value=self.current_owner,
            ),
            mock.patch.object(
                CLOSING.journal_engine,
                "_read_owner_observation",
                return_value=self.owner_observation,
            ),
            mock.patch.object(
                CLOSING.journal_engine, "writer_contract_active", return_value=True
            ),
            mock.patch.object(CLOSING, "_replay_approval", return_value=None),
            mock.patch.object(
                CLOSING.journal_engine,
                "_stable_journal_read",
                return_value=b"changed approval\n",
            ),
        )
        with contextlib.ExitStack() as stack:
            for patcher in patches:
                stack.enter_context(patcher)
            self.assert_refusal(
                "forge: archive refused — authoritative chain discrepancy: snapshot_changed",
                resolve,
            )
            mutant = mutated_function(
                CLOSING._approval_evidence,
                "    _recheck_approval(evidence, current_owner, services)\n",
                "",
            )
            with mock.patch.object(CLOSING, "_approval_evidence", mutant):
                mode = resolve()
        self.assertEqual(mode.backfill_approval, f"{self.approval_run}:decision-01")

    def test_each_approval_subcheck_has_a_fail_closed_disable_leg(self) -> None:
        required = CLOSING.APPROVAL_BINDING_CHECKS
        for check in required:
            enabled = tuple(item for item in required if item != check)
            with self.subTest(check=check), mock.patch.object(
                CLOSING, "APPROVAL_BINDING_CHECKS", enabled
            ):
                self.assert_refusal(
                    APPROVAL_REFUSAL,
                    lambda: self.resolve_approval(self.approval_records()),
                )


class BackfillProofBoundaryTests(support.GitBackfillFixture):
    def target_services(self):
        def only_record(records, kind):
            matches = [record for record in records if record.get("type") == kind]
            if len(matches) != 1:
                raise CLOSING.ArchiveRefusal("fixture invalid")
            return matches[0]

        return SimpleNamespace(only_record=only_record, run_git=self.run_git, renderer_controls=())

    def test_legacy_preview_refuses_target_approval_with_disable_leg(self) -> None:
        request = CLOSING.LegacyRequest(
            self.records(), self.closing, f"{self.run_dir.name}:decision-01", False
        )
        arguments = (self.repo, self.run_dir, request, self.target_services())
        self.assert_refusal(
            CLOSING.LEGACY_APPROVAL_REFUSAL,
            lambda: CLOSING.legacy_closing_mode(*arguments),
        )
        mutant = mutated_function(
            CLOSING.legacy_closing_mode, "approval_run_id == target.name", "False"
        )
        self.assertEqual(mutant(*arguments).legacy_approval, request.approval)

    def test_target_run_id_check_has_disable_leg(self) -> None:
        records = self.records()
        records[0]["run_id"] = "wrong-run"

        def call(function):
            return function(
                records, self.run_dir, self.target_services(), APPROVAL_REFUSAL
            )

        self.assert_refusal(APPROVAL_REFUSAL, lambda: call(CLOSING._target_parts))
        mutant = mutated_function(
            CLOSING._target_parts,
            '        started.get("run_id") != target.name\n',
            "        False\n",
        )
        started, _closed = call(mutant)
        self.assertEqual(started["run_id"], "wrong-run")

    def test_target_closure_must_be_last_record_and_has_disable_leg(self) -> None:
        records = self.records()
        records.append({"type": "decision", "id": "after-close"})

        def call(function):
            return function(
                records, self.run_dir, self.target_services(), APPROVAL_REFUSAL
            )

        self.assert_refusal(APPROVAL_REFUSAL, lambda: call(CLOSING._target_parts))
        mutant = mutated_function(
            CLOSING._target_parts,
            "        or records[-1] is not closed\n",
            "        or False\n",
        )
        _started, closed = call(mutant)
        self.assertEqual(closed["type"], "run_closed")

    def test_archive_head_must_name_a_commit_and_has_disable_leg(self) -> None:
        tree = self.git_text("rev-parse", "HEAD^{tree}")
        evidence = self.evidence(archive_head=tree)
        self.assert_refusal(
            REFUSALS[1], lambda: CLOSING._prove_archive_head(evidence)
        )
        mutant = mutated_function(
            CLOSING._prove_archive_head,
            "        or not _git_success(\n"
            "            evidence, \"cat-file\", \"-e\", "
            "f\"{evidence.archiving_head}^{{commit}}\"\n"
            "        )\n",
            "        or False\n",
        )
        mutant(evidence)

    def test_duplicate_captured_chain_id_refuses_and_has_disable_leg(self) -> None:
        records = self.records(chains=("chain-commit",))
        chain = self.package().chains[0]
        package = SimpleNamespace(chains=(chain, chain), tombstones=())
        evidence = self.evidence(records=records, package=package)
        self.assert_refusal(
            REFUSALS[5], lambda: CLOSING._enumerate_landed_commits(evidence)
        )
        mutant = mutated_function(
            CLOSING._enumerate_landed_commits,
            "if len(matches) == 1 else None",
            "if matches else None",
        )
        self.assertEqual(mutant(evidence), (self.commit_landing,))

    def test_missing_or_invalid_recorded_time_uses_control_refusal(self) -> None:
        cases = (None, "not-a-time", "2026-01-01T00:04:00")
        mutant = mutated_function(
            CLOSING._prove_closing_time,
            "    if recorded is None or committed is None or committed > recorded:\n",
            "    if committed > recorded:\n",
        )
        for recorded_at in cases:
            records = self.records()
            if recorded_at is None:
                records[-1].pop("recorded_at")
            else:
                records[-1]["recorded_at"] = recorded_at
            evidence = self.evidence(records=records)
            with self.subTest(recorded_at=recorded_at):
                self.assert_refusal(
                    REFUSALS[8],
                    lambda evidence=evidence: CLOSING._prove_closing_time(evidence),
                )
                with self.assertRaises(TypeError):
                    mutant(evidence)

    def test_first_parent_successor_must_descend_directly_from_closing(self) -> None:
        successor = "d" * 40
        other_parent = "e" * 40

        def run_git(_repo, *arguments):
            if arguments[0] == "rev-list":
                output = f"{successor}\n".encode()
            elif arguments[0] == "rev-parse":
                output = f"{other_parent}\n".encode()
            elif arguments[0] == "show":
                output = b"9999999999\n"
            else:
                raise AssertionError(arguments)
            return subprocess.CompletedProcess(arguments, 0, output, b"")

        evidence = SimpleNamespace(
            repo=self.repo,
            archiving_head=self.archive_head,
            closing=CLOSING.ClosingMode(self.closing),
            run_git=run_git,
        )
        self.assert_refusal(
            REFUSALS[9],
            lambda: CLOSING._prove_closing_identification(evidence, 0.0),
        )
        mutant = mutated_function(
            CLOSING._first_parent_successor,
            "    return values[0] if parent == evidence.closing.head else None\n",
            "    return values[0]\n",
        )
        with mock.patch.object(CLOSING, "_first_parent_successor", mutant):
            CLOSING._prove_closing_identification(evidence, 0.0)

    def test_closing_timestamp_equality_is_accepted_and_strict_mutant_fails(self) -> None:
        evidence = self.evidence(records=self.records(recorded_at="2026-01-01T00:03:00Z"))
        CLOSING.prove_backfill_controls(evidence)
        mutant = mutated_function(
            CLOSING._prove_closing_time, "committed > recorded", "committed >= recorded"
        )
        with mock.patch.object(CLOSING, "_prove_closing_time", mutant):
            self.assert_refusal(REFUSALS[8], lambda: CLOSING.prove_backfill_controls(evidence))

    def test_archive_timestamp_equality_is_accepted_and_strict_mutant_fails(self) -> None:
        equal_archive = self.commit_tree(self.successor, "2026-01-01T00:04:00+00:00")
        evidence = self.evidence(
            records=self.records(recorded_at="2026-01-01T00:04:00Z"),
            archive_head=equal_archive,
        )
        CLOSING.prove_backfill_controls(evidence)
        mutant = mutated_function(
            CLOSING._prove_archive_time, "archived < recorded", "archived <= recorded"
        )
        with mock.patch.object(CLOSING, "_prove_archive_time", mutant):
            self.assert_refusal(REFUSALS[10], lambda: CLOSING.prove_backfill_controls(evidence))

    def test_landed_oid_must_name_an_existing_commit(self) -> None:
        absent = "f" * 40
        evidence = self.evidence(package=self.package(commit_oid=absent))
        self.assert_refusal(
            REFUSALS[5], lambda: CLOSING._enumerate_landed_commits(evidence)
        )
        original = CLOSING._git_success

        def without_cat_file(current, *arguments):
            if arguments[:2] == ("cat-file", "-e"):
                return True
            return original(current, *arguments)

        with mock.patch.object(CLOSING, "_git_success", without_cat_file):
            landed = CLOSING._enumerate_landed_commits(evidence)
        self.assertIn(absent, landed)

    def test_landing_chain_id_must_be_a_string(self) -> None:
        records = self.records(chains=("7",))
        records[1]["binding"]["source_record"]["chain_id"] = 7
        chain = SimpleNamespace(
            chain_id="7",
            family="commit",
            state={"commit_result": {"commit_sha": self.commit_landing}},
        )
        evidence = self.evidence(
            records=records,
            package=SimpleNamespace(chains=(chain,), tombstones=()),
        )
        self.assert_refusal(
            REFUSALS[5], lambda: CLOSING._enumerate_landed_commits(evidence)
        )
        with mock.patch.object(CLOSING, "_landing_chain_ids", return_value=("7",)):
            self.assertEqual(
                CLOSING._enumerate_landed_commits(evidence),
                (self.commit_landing,),
            )

    def test_basis_added_beyond_closing_tree_is_checked(self) -> None:
        document = SimpleNamespace(label="late-plan", path=self.repo / "archive.txt")
        evidence = self.evidence(documents=(document,))
        expected = REFUSALS[7].replace("<label>", "late-plan")
        self.assert_refusal(expected, lambda: CLOSING._prove_basis_stability(evidence))
        original = CLOSING._tree_tracks

        def closing_tree_only(current, head, relative):
            if head != current.closing.head:
                return False
            return original(current, head, relative)

        with mock.patch.object(CLOSING, "_tree_tracks", closing_tree_only):
            CLOSING._prove_basis_stability(evidence)

    def test_basis_deleted_after_closing_tree_is_checked(self) -> None:
        path = self.repo / "basis.md"
        path.unlink()
        archive_head = self.commit("basis-deleted", "2026-01-01T00:07:00+00:00")
        document = SimpleNamespace(label="retired-plan", path=path)
        evidence = self.evidence(archive_head=archive_head, documents=(document,))
        expected = REFUSALS[7].replace("<label>", "retired-plan")
        self.assert_refusal(expected, lambda: CLOSING._prove_basis_stability(evidence))
        original = CLOSING._tree_tracks

        def archive_tree_only(current, head, relative):
            if head != current.archiving_head:
                return False
            return original(current, head, relative)

        with mock.patch.object(CLOSING, "_tree_tracks", archive_tree_only):
            CLOSING._prove_basis_stability(evidence)

    def test_magic_pathspec_basis_is_literal_and_has_disable_leg(self) -> None:
        path = self.repo / ":(top)x"
        path.write_text("before\n", encoding="utf-8")
        closing = self.commit("literal-closing", "2026-01-01T00:07:00+00:00")
        path.write_text("after\n", encoding="utf-8")
        archive_head = self.commit("literal-archive", "2026-01-01T00:08:00+00:00")
        document = SimpleNamespace(label="magic-plan", path=path)
        evidence = support.replace(
            self.evidence(closing=closing, archive_head=archive_head, documents=(document,)),
            run_git=ARCHIVE.run_git,
        )
        expected = REFUSALS[7].replace("<label>", "magic-plan")
        self.assert_refusal(expected, lambda: CLOSING._prove_basis_stability(evidence))
        mutant = mutated_function(ARCHIVE.run_git, '("--literal-pathspecs",)', "()")
        CLOSING._prove_basis_stability(support.replace(evidence, run_git=mutant))


class SharedDefinitionAndParserTests(support.GitBackfillFixture):
    def test_backfill_refusal_literals_match_across_runtime_surfaces(self) -> None:
        engine_archive = package_module("engine._archive")
        cli_options = package_module("engine._cli_options")
        dispatch = package_module("app._dispatch")
        self.assertEqual(
            engine_archive._BACKFILL_MODE_CONFLICT,
            CLOSING.BACKFILL_MODE_CONFLICT,
        )
        self.assertEqual(
            cli_options._BACKFILL_MODE_CONFLICT,
            CLOSING.BACKFILL_MODE_CONFLICT,
        )
        self.assertEqual(
            engine_archive._BACKFILL_APPROVAL_REFUSAL,
            CLOSING.BACKFILL_APPROVAL_REFUSAL,
        )
        self.assertEqual(
            cli_options._BACKFILL_APPROVAL_REFUSAL,
            CLOSING.BACKFILL_APPROVAL_REFUSAL,
        )
        self.assertIs(
            dispatch._BACKFILL_APPROVAL_REFUSAL,
            cli_options._BACKFILL_APPROVAL_REFUSAL,
        )

    def test_archive_metadata_validator_has_one_shared_definition(self) -> None:
        engine_archive = package_module("engine._archive")
        chain_state = package_module("chain_core._chain_state")
        self.assertIs(
            engine_archive._archive_metadata_mode_is_valid,
            chain_state._archive_metadata_mode_is_valid,
        )

    def test_commit_start_closing_validator_has_one_shared_definition(self) -> None:
        cli_options = package_module("engine._cli_options")
        dispatch = package_module("app._dispatch")
        self.assertIs(
            cli_options._validate_commit_start_closing_options,
            dispatch._validate_commit_start_closing_options,
        )

    def test_direct_parser_refuses_neither_mode_as_invalid_invocation(self) -> None:
        with self.assertRaises(CLOSING.ArchiveRefusal) as raised:
            ARCHIVE.parser().parse_args(
                [
                    "--run-dir",
                    str(self.run_dir),
                    "--post-close-validation",
                    str(self.base / "post-close.json"),
                ]
            )
        self.assertEqual(
            raised.exception.message,
            "forge: archive refused — invalid invocation: one archive closing mode is required",
        )

    def test_direct_parser_refuses_normal_and_legacy_as_invalid_invocation(self) -> None:
        with self.assertRaises(CLOSING.ArchiveRefusal) as raised:
            ARCHIVE.parser().parse_args(
                [
                    "--run-dir",
                    str(self.run_dir),
                    "--closing-head",
                    self.closing,
                    "--legacy-recovered-head",
                    self.closing,
                    "--legacy-approval",
                    "approval-run:decision-01",
                    "--post-close-validation",
                    str(self.base / "post-close.json"),
                ]
            )
        self.assertTrue(
            raised.exception.message.startswith(
                "forge: archive refused — invalid invocation:"
            )
        )
