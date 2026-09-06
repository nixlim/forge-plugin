"""Predicate-negative coverage for Revision-9 retrospective chain ingest."""

from __future__ import annotations

import contextlib
import copy
import datetime as dt
import hashlib
import importlib.util
import io
import json
import os
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
CLI_PATH = ROOT / "scripts" / "forge" / "cli.py"
ENVELOPE_KEYS = {
    "chain_id",
    "evidence_refs",
    "expected",
    "message",
    "next_required_step",
    "observed",
    "ok",
    "reason_code",
    "remediation",
    "schema",
    "state",
}


from tests._cli_loader import load_script, package_module  # cli split phase 0: one shared loader


CLI = load_script("forge_revision9_ingest_negative_cli", CLI_PATH)
RUNTIME = package_module("runtime")  # cli split phase 2a: canonical patch seam for runtime controls
CLI_FIXTURE_SUPPORT = load_script(
    "forge_revision9_ingest_negative_fixture_support",
    ROOT / "tests" / "test_cli_chain.py",
)


def key(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


class Revision9IngestPredicateNegativeTests(
    CLI_FIXTURE_SUPPORT.ForgeCLIFixture
):
    def revision9_environment(self) -> dict[str, str]:
        return self.environment(FORGE_SESSION_PID=str(os.getpid()))

    @contextlib.contextmanager
    def cli_process_context(self):
        with mock.patch.dict(
            os.environ, self.revision9_environment(), clear=True
        ), mock.patch.object(
            RUNTIME, "SCRIPT_DIR", self.helpers
        ), mock.patch.object(
            RUNTIME, "PLUGIN_ROOT", ROOT
        ), mock.patch.object(
            CLI, "CODEX_EXECUTABLE", str(self.helpers / "fake-codex")
        ):
            yield

    def invoke_cli(self, *argv: str) -> tuple[int, dict[str, object]]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with self.cli_process_context(), contextlib.redirect_stdout(
            stdout
        ), contextlib.redirect_stderr(stderr):
            exit_code = CLI.main(
                ["--json", "--repo", str(self.repo), *argv]
            )
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(stdout.getvalue().count("\n"), 1)
        envelope = json.loads(stdout.getvalue())
        self.assertEqual(set(envelope), ENVELOPE_KEYS)
        return exit_code, envelope

    def open_run_and_task(
        self,
        run_id: str,
        *,
        scope: tuple[str, ...],
        files: tuple[str, ...],
    ) -> None:
        _batch, builders, _journal = CLI._coordination_modules()
        with self.cli_process_context():
            builders.run_open(
                self.repo,
                run_id,
                idempotency_key=key(f"{run_id}-open"),
                goal="Exercise retrospective ingest predicates",
                scope=list(scope),
                plugin_ref="forge-revision9-ingest-negative-tests",
            )
            builders.task_start(
                self.repo,
                run_id,
                idempotency_key=key(f"{run_id}-task"),
                task="task-01",
                goal="Ingest one already-landed chain",
                acceptance=["All ordered ingest proofs must hold"],
                files=list(files),
            )

    @staticmethod
    def selected_commit_ingest_event_digests(
        materialized: dict[str, object],
        events: list[dict[str, object]],
    ) -> list[str]:
        selected: list[str] = []
        final_candidate = materialized["candidate"]["sha256"]
        tier = materialized["tier"]
        review = materialized["review"]
        approval = materialized["approval"]
        approval_required = bool(
            tier["control"] or review["operator_cosign_required"]
        )
        prior_state: dict[str, object] | None = None
        for event in events:
            payload = event["payload"]
            details = payload["details"]
            event_state = payload["state"]
            event_name = payload["event"]
            active = False
            if event_name == "step_recorded":
                active = CLI._ingest_step_is_current(
                    materialized, event_state, details
                )
            elif event_name == "secret_scan_recorded":
                active = CLI._ingest_secret_scan_is_current(
                    materialized, event, prior_state, event_state
                )
            elif event_name in {"review_passed", "review_blocked"}:
                active = bool(
                    tier["effective"] == "hard"
                    and event_name == "review_passed"
                    and event_state["review"]["verdict"]
                    == review["verdict"]
                )
            elif event_name == "operator_approved":
                active = bool(
                    approval_required
                    and event_state["approval"] == approval
                )
            elif event_name == "operator_skip":
                gate_id = details.get("gate_id")
                active = bool(
                    isinstance(gate_id, str)
                    and CLI._user_skip(materialized, gate_id)
                    == CLI._user_skip(event_state, gate_id)
                )
            elif event_name in {
                "commit_produced",
                "commit_close_recovered",
            }:
                active = (
                    details.get("commit_sha")
                    == materialized["commit_result"]["commit_sha"]
                )
            if (
                active
                and event_state["candidate"]["sha256"] == final_candidate
            ):
                selected.append(str(event["digest"]))
            prior_state = event_state
        return selected

    def prepare_terminal_ingest(
        self,
        run_id: str,
        *,
        control: bool = False,
        run_scope: tuple[str, ...] | None = None,
        task_files: tuple[str, ...] | None = None,
        configured_changelog: bool = False,
    ) -> SimpleNamespace:
        if configured_changelog:
            (self.repo / "forge-project.md").write_text(
                CLI_FIXTURE_SUPPORT.policy_with_changelog(), encoding="utf-8"
            )
            (self.repo / "CHANGELOG.md").write_text(
                "# Changes\n", encoding="utf-8"
            )
            self.git("add", "--", "forge-project.md", "CHANGELOG.md")
            self.git("commit", "--quiet", "-m", "configure changelog gate")
        if control:
            changed_path = "scripts/tool.py"
            self.change(changed_path, "CONTROL = 2\n")
        else:
            changed_path = "docs/guide.md"
            self.change(
                changed_path,
                f"# Retrospective source for {run_id}\n",
            )

        exit_code, started = self.invoke_cli(
            "commit", "start", "--paths", changed_path
        )
        self.assertEqual(exit_code, 0, started)
        self.assertEqual(started["schema"], "forge-cli/1")
        chain_id = str(started["chain_id"])

        if configured_changelog:
            exit_code, changelog = self.invoke_cli(
                "--chain-id", chain_id, "gate", "run", "changelog"
            )
            self.assertEqual(exit_code, 0, changelog)

        exit_code, verified = self.invoke_cli(
            "--chain-id", chain_id, "verify"
        )
        self.assertEqual(exit_code, 0, verified)
        if control:
            self.assertEqual(verified["state"], "reviewing")
            exit_code, requested = self.invoke_cli(
                "--chain-id", chain_id, "review", "request"
            )
            self.assertEqual(exit_code, 0, requested)
            request = self.state(chain_id)["review"]["request"]
            verdict = self.write_verdict(
                f"{run_id}-pass.txt", "PASS", request
            )
            exit_code, attached = self.invoke_cli(
                "--chain-id",
                chain_id,
                "review",
                "attach",
                "--verdict-file",
                str(verdict),
            )
            self.assertEqual(exit_code, 0, attached)
            self.assertEqual(attached["state"], "awaiting_approval")
            candidate = str(self.state(chain_id)["candidate"]["sha256"])
            exit_code, approved = self.invoke_cli(
                "--chain-id",
                chain_id,
                "commit",
                "approve",
                "--candidate",
                candidate,
            )
            self.assertEqual(exit_code, 0, approved)
            self.assertEqual(approved["state"], "authorized")
        else:
            self.assertEqual(verified["state"], "authorized")

        exit_code, finalized = self.invoke_cli(
            "--chain-id",
            chain_id,
            "commit",
            "finalize",
            "--message",
            f"Finalize retrospective source for {run_id}",
        )
        self.assertEqual(exit_code, 0, finalized)
        self.assertEqual(finalized["state"], "closed")

        materialized = self.state(chain_id)
        events = self.events(chain_id)
        state_raw = self.state_path(chain_id).read_bytes()
        events_raw = self.events_path(chain_id).read_bytes()
        self.assertEqual(materialized["state"], "closed")
        self.assertIsNone(materialized["run_binding"])
        self.assertIsNone(materialized["journal_outbox"])
        self.assertEqual(
            state_raw, CLI.canonical_bytes(materialized) + b"\n"
        )
        self.assertEqual(
            events_raw,
            b"".join(
                CLI.canonical_bytes(event) + b"\n" for event in events
            ),
        )

        selected_digests = self.selected_commit_ingest_event_digests(
            materialized, events
        )
        outcome_map = {
            "schema": "forge-chain-ingest-outcome-map/1",
            "chain_id": chain_id,
            "task": "task-01",
            "task_status": "complete",
            "event_digests": selected_digests,
        }
        outcome_raw = CLI.canonical_bytes(outcome_map) + b"\n"
        source_paths = {
            "state_file": "external/source-state.json",
            "events_file": "external/source-events.jsonl",
            "outcome_map": "external/source-outcome-map.json",
        }
        source_data = {
            "state_file": state_raw,
            "events_file": events_raw,
            "outcome_map": outcome_raw,
        }
        external = self.repo / "external"
        external.mkdir(exist_ok=True)
        for field, relative in source_paths.items():
            (self.repo / relative).write_bytes(source_data[field])

        admitted_scope = run_scope or (f"{Path(changed_path).parent}/**",)
        admitted_files = task_files or (changed_path,)
        self.open_run_and_task(
            run_id, scope=admitted_scope, files=admitted_files
        )
        closing_head = self.git("rev-parse", "HEAD")
        ingest_argv = (
            "--run-id",
            run_id,
            "journal",
            "ingest-chain",
            "--task",
            "task-01",
            "--state-file",
            source_paths["state_file"],
            "--events-file",
            source_paths["events_file"],
            "--outcome-map",
            source_paths["outcome_map"],
            "--closing-head",
            closing_head,
            "--task-status",
            "complete",
            "--idempotency-key",
            key(f"{run_id}-ingest"),
        )
        return SimpleNamespace(
            run_id=run_id,
            run_dir=(
                self.repo
                / ".codex-orchestrator"
                / "runs"
                / run_id
            ),
            chain_id=chain_id,
            materialized=materialized,
            events=events,
            selected_digests=selected_digests,
            source_paths=source_paths,
            source_data=source_data,
            outcome_map=outcome_map,
            ingest_argv=ingest_argv,
            changed_path=changed_path,
            state_raw=state_raw,
            events_raw=events_raw,
        )

    def prepare_bound_fast_ingest(self, run_id: str) -> SimpleNamespace:
        self.open_run_and_task(
            run_id, scope=("docs/**",), files=("docs/guide.md",)
        )
        self.change("docs/guide.md", "# Bound autoappend source\n")
        exit_code, started = self.invoke_cli(
            "--run-id",
            run_id,
            "commit",
            "start",
            "--paths",
            "docs/guide.md",
            "--task",
            "task-01",
        )
        self.assertEqual(exit_code, 0, started)
        chain_id = str(started["chain_id"])
        exit_code, verified = self.invoke_cli(
            "--chain-id", chain_id, "verify"
        )
        self.assertEqual(exit_code, 0, verified)
        self.assertEqual(verified["state"], "authorized")
        exit_code, finalized = self.invoke_cli(
            "--chain-id",
            chain_id,
            "commit",
            "finalize",
            "--message",
            "Finalize bound autoappend source",
        )
        self.assertEqual(exit_code, 0, finalized)
        self.assertEqual(finalized["state"], "closed")

        materialized = self.state(chain_id)
        events = self.events(chain_id)
        selected = self.selected_commit_ingest_event_digests(
            materialized, events
        )
        outcome = {
            "schema": "forge-chain-ingest-outcome-map/1",
            "chain_id": chain_id,
            "task": "task-01",
            "task_status": "complete",
            "event_digests": selected,
        }
        external = self.repo / "external"
        external.mkdir(exist_ok=True)
        paths = {
            "state_file": "external/bound-state.json",
            "events_file": "external/bound-events.jsonl",
            "outcome_map": "external/bound-outcome-map.json",
        }
        data = {
            "state_file": self.state_path(chain_id).read_bytes(),
            "events_file": self.events_path(chain_id).read_bytes(),
            "outcome_map": CLI.canonical_bytes(outcome) + b"\n",
        }
        for field, relative in paths.items():
            (self.repo / relative).write_bytes(data[field])
        ingest_argv = (
            "--run-id",
            run_id,
            "journal",
            "ingest-chain",
            "--task",
            "task-01",
            "--state-file",
            paths["state_file"],
            "--events-file",
            paths["events_file"],
            "--outcome-map",
            paths["outcome_map"],
            "--closing-head",
            self.git("rev-parse", "HEAD"),
            "--task-status",
            "complete",
            "--idempotency-key",
            key(f"{run_id}-duplicate-ingest"),
        )
        return SimpleNamespace(
            run_id=run_id,
            run_dir=(
                self.repo
                / ".codex-orchestrator"
                / "runs"
                / run_id
            ),
            chain_id=chain_id,
            ingest_argv=ingest_argv,
        )

    @staticmethod
    def event_name(event: dict[str, object]) -> str:
        return str(event["payload"]["event"])

    @staticmethod
    def canonical_event_bytes(events: list[dict[str, object]]) -> bytes:
        return b"".join(
            CLI.canonical_bytes(event) + b"\n" for event in events
        )

    @staticmethod
    def rewrite_event_chain(
        events: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        rewritten = copy.deepcopy(events)
        previous = CLI.ZERO_DIGEST
        for sequence, event in enumerate(rewritten, 1):
            event["sequence"] = sequence
            event["prev_digest"] = previous
            event.pop("digest", None)
            event["digest"] = hashlib.sha256(
                CLI.canonical_bytes(event)
            ).hexdigest()
            previous = str(event["digest"])
        return rewritten

    def write_package(
        self,
        prepared: SimpleNamespace,
        *,
        state: dict[str, object] | None = None,
        events: list[dict[str, object]] | None = None,
        outcome: dict[str, object] | None = None,
        live: bool = False,
    ) -> None:
        state_raw = (
            prepared.source_data["state_file"]
            if state is None
            else CLI.canonical_bytes(state) + b"\n"
        )
        events_raw = (
            prepared.source_data["events_file"]
            if events is None
            else self.canonical_event_bytes(events)
        )
        outcome_raw = (
            prepared.source_data["outcome_map"]
            if outcome is None
            else CLI.canonical_bytes(outcome) + b"\n"
        )
        (self.repo / prepared.source_paths["state_file"]).write_bytes(
            state_raw
        )
        (self.repo / prepared.source_paths["events_file"]).write_bytes(
            events_raw
        )
        (self.repo / prepared.source_paths["outcome_map"]).write_bytes(
            outcome_raw
        )
        if live:
            self.state_path(prepared.chain_id).write_bytes(state_raw)
            self.events_path(prepared.chain_id).write_bytes(events_raw)

    def reset_package(self, prepared: SimpleNamespace) -> None:
        self.write_package(prepared)
        self.state_path(prepared.chain_id).write_bytes(prepared.state_raw)
        self.events_path(prepared.chain_id).write_bytes(
            prepared.events_raw
        )

    def carry_state_change(
        self,
        prepared: SimpleNamespace,
        start_event: str,
        mutate_state,
        *,
        mutate_start_details=None,
    ) -> tuple[dict[str, object], list[dict[str, object]]]:
        state = copy.deepcopy(prepared.materialized)
        events = copy.deepcopy(prepared.events)
        start = next(
            index
            for index, event in enumerate(events)
            if self.event_name(event) == start_event
        )
        for event in events[start:]:
            mutate_state(event["payload"]["state"])
        mutate_state(state)
        if mutate_start_details is not None:
            mutate_start_details(events[start]["payload"]["details"])
        return state, self.rewrite_event_chain(events)

    def run_snapshot(self, prepared: SimpleNamespace) -> SimpleNamespace:
        _batch, _builders, journal = CLI._coordination_modules()
        journal_path = prepared.run_dir / "journal.jsonl"
        receipts_path = prepared.run_dir / journal.BATCH_RECEIPTS_NAME
        intent_path = prepared.run_dir / journal.BATCH_INTENT_NAME
        self.assertFalse(intent_path.exists())
        return SimpleNamespace(
            journal=journal,
            journal_path=journal_path,
            receipts_path=receipts_path,
            intent_path=intent_path,
            journal_bytes=journal_path.read_bytes(),
            receipt_bytes=receipts_path.read_bytes(),
        )

    def assert_snapshot_unchanged(
        self, prepared: SimpleNamespace, snapshot: SimpleNamespace
    ) -> None:
        self.assertEqual(
            snapshot.journal_path.read_bytes(), snapshot.journal_bytes
        )
        self.assertEqual(
            snapshot.receipts_path.read_bytes(), snapshot.receipt_bytes
        )
        self.assertFalse(snapshot.intent_path.exists())
        records, issues = snapshot.journal.read_journal(
            snapshot.journal_path
        )
        self.assertEqual(issues, [])
        tasks = [
            record
            for record in records
            if record.get("type") == "task"
            and record.get("id") == "task-01"
        ]
        self.assertTrue(tasks)
        self.assertEqual(tasks[-1]["status"], "active")

    def local_ingest_globals(self) -> dict[str, object]:
        with self.cli_process_context():
            CLI.register_coordination_seams()
        verifier = CLI._ingest_proof_verifier
        self.assertIs(verifier.__globals__, vars(CLI))
        self.assertIs(getattr(verifier, "_forge_cli_revision9_seam", None), True)
        return verifier.__globals__

    def assert_ingest_refusal(
        self,
        prepared: SimpleNamespace,
        boundary: str,
        *,
        argv: tuple[str, ...] | None = None,
    ) -> tuple[dict[str, object], list[str]]:
        _batch, builders, _journal = CLI._coordination_modules()
        snapshot = self.run_snapshot(prepared)
        authority_globals = self.local_ingest_globals()
        original_require = authority_globals["_require_ingest_proof"]
        observed: list[str] = []

        def track(
            name: str, completed_proofs: list[str] | None = None
        ) -> None:
            observed.append(name)
            original_require(name, completed_proofs)

        with mock.patch.dict(
            authority_globals, {"_require_ingest_proof": track}
        ):
            exit_code, envelope = self.invoke_cli(
                *(argv or prepared.ingest_argv)
            )
        self.assertEqual(exit_code, 1, envelope)
        self.assertFalse(envelope["ok"])
        self.assertEqual(envelope["schema"], "forge-cli/2")
        self.assertEqual(envelope["reason_code"], "ingest-proof-invalid")
        self.assertEqual(envelope["message"], builders.INGEST_PROOF_INVALID)
        position = CLI.INGEST_PROOF_ORDER.index(boundary)
        self.assertEqual(
            observed, list(CLI.INGEST_PROOF_ORDER[: position + 1])
        )
        self.assert_snapshot_unchanged(prepared, snapshot)
        return envelope, observed

    def assert_capture_refusal(
        self,
        prepared: SimpleNamespace,
        argv: tuple[str, ...],
        expected_message: str,
    ) -> dict[str, object]:
        snapshot = self.run_snapshot(prepared)
        exit_code, envelope = self.invoke_cli(*argv)
        self.assertEqual(exit_code, 1, envelope)
        self.assertFalse(envelope["ok"])
        self.assertEqual(envelope["schema"], "forge-cli/2")
        self.assertEqual(envelope["reason_code"], "citation-out-of-root")
        self.assertEqual(envelope["message"], expected_message)
        self.assert_snapshot_unchanged(prepared, snapshot)
        return envelope

    def test_fast_predicate_negatives_refuse_at_ordered_boundaries(self) -> None:
        prepared = self.prepare_terminal_ingest(
            "run-20260828-ingest-predicate-fast"
        )

        cases = (
            "event-digest",
            "predecessor-link",
            "materialized-state",
            "repository",
            "policy",
            "generation",
            "current-gates",
            "landing-proof",
            "closing-head-containment",
            "task-membership",
        )
        for case in cases:
            with self.subTest(case=case):
                self.reset_package(prepared)
                argv = prepared.ingest_argv
                boundary = case

                if case == "event-digest":
                    events = copy.deepcopy(prepared.events)
                    events[0]["digest"] = (
                        "f" * 64
                        if events[0]["digest"] != "f" * 64
                        else "e" * 64
                    )
                    self.write_package(prepared, events=events)
                    boundary = "chain-schema-and-digest-replay"
                elif case == "predecessor-link":
                    events = copy.deepcopy(prepared.events)
                    events[1]["prev_digest"] = CLI.ZERO_DIGEST
                    self.write_package(prepared, events=events)
                    boundary = "chain-schema-and-digest-replay"
                elif case == "materialized-state":
                    state = copy.deepcopy(prepared.materialized)
                    state["inactive_after"] = "2099-01-01T00:00:00Z"
                    self.write_package(prepared, state=state)
                elif case == "repository":
                    state = copy.deepcopy(prepared.materialized)
                    events = copy.deepcopy(prepared.events)
                    wrong_root = str((self.temp_root / "other-repo").resolve())
                    state["staging"]["worktree_root"] = wrong_root
                    events[-1]["payload"]["state"]["staging"][
                        "worktree_root"
                    ] = wrong_root
                    events = self.rewrite_event_chain(events)
                    self.write_package(
                        prepared, state=state, events=events
                    )
                elif case == "policy":
                    state = copy.deepcopy(prepared.materialized)
                    events = copy.deepcopy(prepared.events)
                    wrong_digest = "0" * 64
                    state["policy_source"]["digest"] = wrong_digest
                    events[-1]["payload"]["state"]["policy_source"][
                        "digest"
                    ] = wrong_digest
                    events = self.rewrite_event_chain(events)
                    self.write_package(
                        prepared, state=state, events=events
                    )
                elif case == "generation":
                    live_state = copy.deepcopy(prepared.materialized)
                    live_events = copy.deepcopy(prepared.events)
                    final = live_events[-1]
                    at = CLI.parse_time(final["payload"]["at"]) + dt.timedelta(
                        seconds=1
                    )
                    shifted_at = CLI.iso_z(at)
                    shifted_inactive = CLI.iso_z(
                        at + dt.timedelta(seconds=CLI.INACTIVE_SECONDS)
                    )
                    final["payload"]["at"] = shifted_at
                    final["payload"]["state"]["last_event_at"] = shifted_at
                    final["payload"]["state"][
                        "inactive_after"
                    ] = shifted_inactive
                    live_state["last_event_at"] = shifted_at
                    live_state["inactive_after"] = shifted_inactive
                    live_events = self.rewrite_event_chain(live_events)
                    self.state_path(prepared.chain_id).write_bytes(
                        CLI.canonical_bytes(live_state) + b"\n"
                    )
                    self.events_path(prepared.chain_id).write_bytes(
                        self.canonical_event_bytes(live_events)
                    )
                elif case == "current-gates":
                    state = copy.deepcopy(prepared.materialized)
                    events = copy.deepcopy(prepared.events)
                    start = next(
                        index
                        for index, event in enumerate(events)
                        if self.event_name(event) == "step_recorded"
                        and event["payload"]["details"].get("step_id")
                        == "stack:docs"
                    )
                    for event in events[start:]:
                        event["payload"]["state"]["steps"]["stack:docs"][
                            -1
                        ]["result"] = "failed"
                    state["steps"]["stack:docs"][-1]["result"] = "failed"
                    events[start]["payload"]["details"]["result"] = "failed"
                    events = self.rewrite_event_chain(events)
                    self.write_package(
                        prepared, state=state, events=events, live=True
                    )
                elif case == "landing-proof":
                    def stale_message_digest(state):
                        state["commit_result"]["intent"][
                            "message_digest"
                        ] = "0" * 64

                    state, events = self.carry_state_change(
                        prepared, "commit_intent", stale_message_digest
                    )
                    self.write_package(
                        prepared, state=state, events=events, live=True
                    )
                elif case == "closing-head-containment":
                    parent = prepared.materialized["commit_result"]["intent"][
                        "pre_head"
                    ]
                    argv_list = list(prepared.ingest_argv)
                    closing = argv_list.index("--closing-head") + 1
                    argv_list[closing] = str(parent)
                    argv = tuple(argv_list)
                elif case == "task-membership":
                    outcome = copy.deepcopy(prepared.outcome_map)
                    outcome["task"] = "task-not-in-this-run"
                    self.write_package(prepared, outcome=outcome)

                self.assert_ingest_refusal(
                    prepared, boundary, argv=argv
                )

        self.reset_package(prepared)

    def test_review_and_approval_predicates_are_independently_false(self) -> None:
        prepared = self.prepare_terminal_ingest(
            "run-20260828-ingest-predicate-control", control=True
        )
        cases = (
            "review-package",
            "reviewer-role",
            "reviewer-iteration",
            "reviewer-verdict",
            "operator-approval",
        )
        for boundary in cases:
            with self.subTest(boundary=boundary):
                self.reset_package(prepared)
                if boundary == "review-package":
                    def mutate_request(state):
                        state["review"]["request"][
                            "package_digest"
                        ] = "0" * 64

                    def mutate_details(details):
                        details["package_digest"] = "0" * 64

                    state, events = self.carry_state_change(
                        prepared,
                        "review_requested",
                        mutate_request,
                        mutate_start_details=mutate_details,
                    )
                elif boundary == "reviewer-role":
                    def mutate_request(state):
                        state["review"]["request"][
                            "reviewer"
                        ] = "review-cheap"

                    def mutate_details(details):
                        details["reviewer"] = "review-cheap"

                    state, events = self.carry_state_change(
                        prepared,
                        "review_requested",
                        mutate_request,
                        mutate_start_details=mutate_details,
                    )
                elif boundary == "reviewer-iteration":
                    def mutate_iteration(state):
                        state["review"]["iteration"] = 2

                    state, events = self.carry_state_change(
                        prepared, "review_requested", mutate_iteration
                    )
                elif boundary == "reviewer-verdict":
                    def mutate_verdict(state):
                        state["review"]["verdict"][
                            "candidate"
                        ] = "0" * 64

                    state, events = self.carry_state_change(
                        prepared, "review_passed", mutate_verdict
                    )
                else:
                    state = copy.deepcopy(prepared.materialized)
                    events = copy.deepcopy(prepared.events)
                    approval_index = next(
                        index
                        for index, event in enumerate(events)
                        if self.event_name(event) == "operator_approved"
                    )
                    review_index = next(
                        index
                        for index, event in enumerate(events)
                        if self.event_name(event) == "review_passed"
                    )
                    absent_approval = copy.deepcopy(
                        events[approval_index - 1]["payload"]["state"][
                            "approval"
                        ]
                    )
                    authorization = copy.deepcopy(
                        events[approval_index]["payload"]["state"][
                            "authorization"
                        ]
                    )
                    events[review_index]["payload"]["state"][
                        "state"
                    ] = "authorized"
                    events[review_index]["payload"]["state"][
                        "authorization"
                    ] = authorization
                    events[review_index]["payload"]["details"][
                        "awaiting_approval"
                    ] = False
                    del events[approval_index]
                    for event in events[review_index:]:
                        event["payload"]["state"][
                            "approval"
                        ] = copy.deepcopy(absent_approval)
                    state["approval"] = absent_approval
                    events = self.rewrite_event_chain(events)

                self.write_package(
                    prepared, state=state, events=events, live=True
                )
                self.assert_ingest_refusal(prepared, boundary)

        self.reset_package(prepared)

    def test_scope_membership_refuses_landed_path_outside_task_and_run(self) -> None:
        prepared = self.prepare_terminal_ingest(
            "run-20260828-ingest-predicate-scope",
            run_scope=("src/**",),
            task_files=("src/app.py",),
        )
        self.assert_ingest_refusal(prepared, "scope-membership")

    def test_committed_changelog_output_is_exempt_from_ingest_scope(self) -> None:
        prepared = self.prepare_terminal_ingest(
            "run-20260831-ingest-changelog-output",
            configured_changelog=True,
        )

        with mock.patch.object(
            CLI, "_committed_changelog_output_paths", return_value=frozenset()
        ):
            self.assert_ingest_refusal(prepared, "scope-membership")

        exit_code, ingested = self.invoke_cli(*prepared.ingest_argv)
        self.assertEqual(exit_code, 0, ingested)
        self.assertTrue(ingested["ok"])

    def test_digest_valid_illegal_transition_reaches_monotonic_proof(self) -> None:
        prepared = self.prepare_terminal_ingest(
            "run-20260828-ingest-illegal-transition"
        )
        events = copy.deepcopy(prepared.events)
        close_index = next(
            index
            for index, event in enumerate(events)
            if self.event_name(event) == "chain_closed"
        )
        self.assertGreater(close_index, 0)
        events[close_index - 1]["payload"]["state"][
            "state"
        ] = "authorized"
        events = self.rewrite_event_chain(events)
        self.write_package(
            prepared,
            state=copy.deepcopy(prepared.materialized),
            events=events,
            live=True,
        )
        _envelope, observed = self.assert_ingest_refusal(
            prepared, "monotonic-transitions"
        )
        self.assertEqual(observed[-1], "monotonic-transitions")

    def test_public_ingest_refuses_hostile_source_path_spellings(self) -> None:
        prepared = self.prepare_terminal_ingest(
            "run-20260828-ingest-hostile-source-paths"
        )
        source_option = list(prepared.ingest_argv).index("--state-file") + 1
        source = self.repo / prepared.source_paths["state_file"]
        symlink = self.repo / "external" / "state-link.json"
        symlink.symlink_to(source.name)
        nonregular = self.repo / "external" / "state-directory"
        nonregular.mkdir()
        spellings = (
            str(source),
            "../outside-state.json",
            symlink.relative_to(self.repo).as_posix(),
            nonregular.relative_to(self.repo).as_posix(),
        )
        for spelling in spellings:
            with self.subTest(spelling=spelling):
                argv = list(prepared.ingest_argv)
                argv[source_option] = spelling
                self.assert_capture_refusal(
                    prepared,
                    tuple(argv),
                    "forge: journal append refused — record cites path outside "
                    "run or repository: ingest.state_file: " + spelling,
                )

    def test_public_ingest_refuses_captured_destination_substitution(self) -> None:
        prepared = self.prepare_terminal_ingest(
            "run-20260828-ingest-capture-substitution"
        )
        digest = hashlib.sha256(
            prepared.source_data["state_file"]
        ).hexdigest()
        destination = (
            prepared.run_dir
            / "captured"
            / "sha256"
            / digest
            / "state.json"
        )
        destination.parent.mkdir(parents=True)
        destination.symlink_to(
            self.repo / prepared.source_paths["state_file"]
        )
        self.assert_capture_refusal(
            prepared,
            prepared.ingest_argv,
            "forge: journal append refused — record cites path outside run or "
            "repository: ingest.captured_package: state.json",
        )

    def test_public_ingest_detects_captured_destination_replacement_race(
        self,
    ) -> None:
        prepared = self.prepare_terminal_ingest(
            "run-20260828-ingest-capture-race"
        )
        digest = hashlib.sha256(
            prepared.source_data["state_file"]
        ).hexdigest()
        destination = (
            prepared.run_dir
            / "captured"
            / "sha256"
            / digest
            / "state.json"
        )
        attacker = destination.with_name("attacker-state.json")
        original_write = os.write
        replaced = False

        def replace_destination(descriptor: int, data: bytes) -> int:
            nonlocal replaced
            written = original_write(descriptor, data)
            if not replaced and destination.exists():
                attacker.write_bytes(b"substituted captured bytes\n")
                os.replace(attacker, destination)
                replaced = True
            return written

        with mock.patch.object(
            CLI.os, "write", side_effect=replace_destination
        ):
            self.assert_capture_refusal(
                prepared,
                prepared.ingest_argv,
                "forge: journal append refused — record cites path outside run "
                "or repository: ingest.captured_package: state.json",
            )
        self.assertTrue(replaced)

    def test_bound_autoappend_then_ingest_never_duplicates_records(self) -> None:
        prepared = self.prepare_bound_fast_ingest(
            "run-20260828-autoappend-ingest-dedupe"
        )
        _batch, _builders, journal = CLI._coordination_modules()
        journal_path = prepared.run_dir / "journal.jsonl"
        before, issues = journal.read_journal(journal_path)
        self.assertEqual(issues, [])
        bound_before = [
            record
            for record in before
            if isinstance(record.get("binding"), dict)
            and record["binding"].get("source_record", {}).get("chain_id")
            == prepared.chain_id
        ]
        self.assertTrue(bound_before)
        self.assertEqual(
            len({record["id"] for record in bound_before}),
            len(bound_before),
        )

        self.assert_ingest_refusal(
            prepared, "chain-schema-and-digest-replay"
        )

        after, issues = journal.read_journal(journal_path)
        self.assertEqual(issues, [])
        bound_after = [
            record
            for record in after
            if isinstance(record.get("binding"), dict)
            and record["binding"].get("source_record", {}).get("chain_id")
            == prepared.chain_id
        ]
        self.assertEqual(bound_after, bound_before)

    def test_successful_failed_task_ingest_then_failed_pass_close_stays_open(
        self,
    ) -> None:
        prepared = self.prepare_terminal_ingest(
            "run-20260828-ingest-then-failed-close"
        )
        outcome = copy.deepcopy(prepared.outcome_map)
        outcome["task_status"] = "failed"
        self.write_package(prepared, outcome=outcome)
        argv = list(prepared.ingest_argv)
        task_status = argv.index("--task-status") + 1
        argv[task_status] = "failed"

        exit_code, ingested = self.invoke_cli(*argv)
        self.assertEqual(exit_code, 0, ingested)
        self.assertTrue(ingested["ok"])
        self.assertEqual(ingested["schema"], "forge-cli/2")
        self.assertEqual(ingested["state"], "closed")

        _batch, builders, journal = CLI._coordination_modules()
        journal_path = prepared.run_dir / "journal.jsonl"
        receipts_path = prepared.run_dir / journal.BATCH_RECEIPTS_NAME
        intent_path = prepared.run_dir / journal.BATCH_INTENT_NAME
        journal_before_close = journal_path.read_bytes()
        receipts_before_close = receipts_path.read_bytes()
        self.assertFalse(intent_path.exists())

        with self.cli_process_context(), self.assertRaises(
            journal.CoordinationRefusal
        ) as raised:
            builders.run_close(
                self.repo,
                prepared.run_id,
                idempotency_key=key(f"{prepared.run_id}-passed-close"),
                judgment="passed",
                summary="This close must fail validation",
                risks=[],
                follow_ups=[],
            )
        self.assertEqual(
            str(raised.exception), builders.RUN_CLOSE_VALIDATION_REFUSAL
        )
        self.assertEqual(journal_path.read_bytes(), journal_before_close)
        self.assertEqual(receipts_path.read_bytes(), receipts_before_close)
        self.assertFalse(intent_path.exists())
        run_state = journal._scan_run(prepared.run_dir)
        self.assertEqual(run_state.disposition, "open")
        self.assertIsNone(run_state.close_judgment)
        self.assertFalse(
            any(record.get("type") == "run_closed" for record in run_state.records)
        )


if __name__ == "__main__":
    unittest.main()
