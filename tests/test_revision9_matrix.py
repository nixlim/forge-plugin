"""Integration matrix coverage for Revision-9 ingest and archive fidelity."""

from __future__ import annotations

import base64
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import re
import sys
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
CLI_PATH = ROOT / "scripts" / "forge" / "cli.py"
ARCHIVE_PATH = ROOT / "scripts" / "forge" / "archive-run.py"


from tests._cli_loader import load_cached as load_module  # cli split phase 0: one shared loader


def canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


CLI_FIXTURE_SUPPORT = load_module(
    "_forge_revision9_matrix_cli_fixture_support",
    ROOT / "tests" / "test_cli_chain.py",
)
CLI = load_module("_forge_revision9_matrix_cli", CLI_PATH)
ARCHIVE = load_module("_forge_revision9_matrix_archive", ARCHIVE_PATH)


class Revision9MergeIngestArchiveMatrixTests(CLI_FIXTURE_SUPPORT.ForgeCLIFixture):
    """Exercise the real DM-014 reducer -> ingest -> archive data plane."""

    run_id = "run-20260828-merge-ingest-matrix"
    task_id = "task-merge"
    chain_id = "c-2026-08-28T120000Z-abcd"

    @contextlib.contextmanager
    def cli_context(self):
        environment = self.environment(FORGE_SESSION_PID=str(os.getpid()))
        with mock.patch.dict(os.environ, environment, clear=True), mock.patch.object(
            CLI, "SCRIPT_DIR", self.helpers
        ), mock.patch.object(CLI, "PLUGIN_ROOT", ROOT), mock.patch.object(
            CLI, "CODEX_EXECUTABLE", str(self.helpers / "fake-codex")
        ):
            yield

    def invoke_cli(self, *argv: str) -> dict[str, object]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with self.cli_context(), contextlib.redirect_stdout(
            stdout
        ), contextlib.redirect_stderr(stderr):
            exit_code = CLI.main(["--json", "--repo", str(self.repo), *argv])
        self.assertEqual(exit_code, 0, stderr.getvalue() or stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")
        envelope = json.loads(stdout.getvalue())
        self.assertTrue(envelope["ok"], envelope)
        return envelope

    def assert_rendered_chain_bytes(
        self,
        rendered: str,
        *,
        family: str,
        state_raw: bytes,
        events_raw: bytes,
        closing_head: str,
    ) -> None:
        self.assertIn(f"Chain family: {family}", rendered)
        self.assertIn(f"Closing HEAD: {closing_head}", rendered)
        state_evidence = re.search(
            r"<!-- FORGE:CHAIN-STATE v1 bytes=(\d+) sha256=([0-9a-f]{64}) "
            r"fence=(\d+) -->\n(?P<fence>`+)json\n(?P<state>.*?)"
            r"(?P=fence)\n<!-- /FORGE:CHAIN-STATE -->",
            rendered,
            re.DOTALL,
        )
        self.assertIsNotNone(state_evidence)
        decoded_state = state_evidence.group("state").encode("utf-8")
        self.assertEqual(decoded_state, state_raw)
        self.assertEqual(int(state_evidence.group(1)), len(state_raw))
        self.assertEqual(
            state_evidence.group(2), hashlib.sha256(state_raw).hexdigest()
        )
        self.assertEqual(
            int(state_evidence.group(3)), len(state_evidence.group("fence"))
        )

        event_evidence = re.search(
            r"<!-- FORGE:CHAIN-EVIDENCE v1 encoding=base64url bytes=(\d+) "
            r"sha256=([0-9a-f]{64}) -->\n([^\n]*)\n"
            r"<!-- /FORGE:CHAIN-EVIDENCE -->",
            rendered,
        )
        self.assertIsNotNone(event_evidence)
        encoded = event_evidence.group(3)
        decoded_events = base64.urlsafe_b64decode(
            encoded + "=" * (-len(encoded) % 4)
        )
        self.assertEqual(decoded_events, events_raw)
        self.assertEqual(int(event_evidence.group(1)), len(events_raw))
        self.assertEqual(
            event_evidence.group(2), hashlib.sha256(events_raw).hexdigest()
        )

    def append_merge_event(
        self,
        events: list[dict[str, object]],
        state: dict[str, object] | None,
        *,
        at: str,
        event_name: str,
        generation_digest: str | None,
        delta: dict[str, object] | None = None,
        direct_payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        self.assertNotEqual(delta is None, direct_payload is None)
        unsigned = {
            "schema": "forge-merge-event/1",
            "chain_id": self.chain_id,
            "sequence": len(events) + 1,
            "at": at,
            "event": event_name,
            "generation_digest": generation_digest,
            "previous_digest": (
                str(events[-1]["digest"]) if events else "0" * 64
            ),
            "payload": (
                {"delta": delta}
                if direct_payload is None
                else direct_payload
            ),
        }
        event = {
            **unsigned,
            "digest": hashlib.sha256(canonical(unsigned)).hexdigest(),
        }
        reduced = CLI.reduce_merge_event(state, event)
        events.append(event)
        return reduced

    def build_real_merge_package(
        self,
    ) -> tuple[bytes, bytes, bytes, str, str, tuple[object, ...]]:
        origin = self.temp_root / "origin.git"
        self.git("init", "--bare", "--quiet", str(origin))
        self.git("remote", "add", "origin", str(origin))
        base = self.git("rev-parse", "HEAD")
        self.git("push", "--quiet", "origin", "HEAD:refs/heads/fixture-main")

        self.change("docs/guide.md", "# Replay-valid DM-014 merge package\n")
        self.git("add", "docs/guide.md")
        self.git("commit", "--quiet", "-m", "Create merge ingest candidate")
        candidate_head = self.git("rev-parse", "HEAD")
        diff_sha256 = hashlib.sha256(
            self.git_bytes("diff", f"{base}...{candidate_head}")
        ).hexdigest()
        self.git("push", "--quiet", "origin", "HEAD:refs/heads/fixture-main")
        remote_head = self.git(
            "--git-dir", str(origin), "rev-parse", "refs/heads/fixture-main"
        )
        self.assertEqual(remote_head, candidate_head)

        policy_raw = self.git_bytes("show", f"{candidate_head}:forge-project.md")
        policy_digest = hashlib.sha256(policy_raw).hexdigest()
        package_path = self.repo / "review" / "merge-package.txt"
        package_path.parent.mkdir()
        package_raw = (
            f"candidate: {candidate_head}\nbase: {base}\n".encode("utf-8")
        )
        package_path.write_bytes(package_raw)
        package_digest = hashlib.sha256(package_raw).hexdigest()

        git_dir = (self.repo / self.git("rev-parse", "--git-dir")).resolve()
        common_dir = (
            self.repo / self.git("rev-parse", "--git-common-dir")
        ).resolve()
        worktree_identity = {
            "path": str(self.repo.resolve()),
            "git_dir": str(git_dir),
            "common_dir": str(common_dir),
        }
        generation_preimage = {
            "remote": "origin",
            "destination_ref": "refs/heads/fixture-main",
            "remote_tip": base,
            "candidate_head": candidate_head,
            "diff_sha256": diff_sha256,
            "policy_commit": candidate_head,
            "policy_digest": policy_digest,
            "worktree_identity": worktree_identity,
            "generation": 1,
        }
        generation_digest = hashlib.sha256(
            canonical(generation_preimage)
        ).hexdigest()
        candidate = {
            **generation_preimage,
            "generation_digest": generation_digest,
        }

        worktree_digest = hashlib.sha256(canonical(worktree_identity)).hexdigest()
        claim_path = str(
            Path(common_dir).parent
            / ".forge"
            / "chains"
            / "owners"
            / f"{worktree_digest}.claim"
        )
        owner = {
            "pid": os.getpid(),
            "host": "revision9-matrix",
            "session": "revision9-matrix-session",
            "started_at": "2026-08-28T12:00:00Z",
        }
        ownership_digest = hashlib.sha256(
            canonical(
                {
                    "chain_id": self.chain_id,
                    "host": owner["host"],
                    "pid": owner["pid"],
                    "session": owner["session"],
                    "started_at": owner["started_at"],
                    "worktree_digest": worktree_digest,
                }
            )
        ).hexdigest()
        integration_baseline = {
            "condition": "none",
            "primary_condition": "none",
            "epoch": None,
            "remote_movement_count": 0,
            "intent": None,
            "observed": None,
            "pre_rebase": None,
            "conflict": None,
            "push": None,
        }
        initial = {
            "schema": "forge-merge-chain/1",
            "chain_id": self.chain_id,
            "kind": "merge",
            "state": "classifying",
            "created_at": "2026-08-28T12:00:00Z",
            "owner": owner,
            "run": None,
            "repository": str(self.repo.resolve()),
            "worktree": {
                **worktree_identity,
                "claim": {
                    "status": "unpublished",
                    "path": claim_path,
                    "inode": None,
                    "digest": None,
                },
            },
            "branch": f"refs/heads/{self.git('branch', '--show-current')}",
            "target": {
                "remote": "origin",
                "destination_ref": "refs/heads/fixture-main",
                "manifest_commit": candidate_head,
            },
            "policy_source": {
                "commit": candidate_head,
                "digest": policy_digest,
            },
            "candidate": None,
            "tier": None,
            "steps": {},
            "review": {},
            "approval": {},
            "authorization": {},
            "integration": integration_baseline,
            "cleanup": {"condition": "none"},
            "run_binding": None,
        }
        events: list[dict[str, object]] = []
        state = self.append_merge_event(
            events,
            None,
            at="2026-08-28T12:00:00Z",
            event_name="chain_started",
            generation_digest=None,
            delta=initial,
        )
        state = self.append_merge_event(
            events,
            state,
            at="2026-08-28T12:00:01Z",
            event_name="ownership_intent",
            generation_digest=None,
            direct_payload={
                "worktree_digest": worktree_digest,
                "claim_path": claim_path,
                "intended_claim_digest": ownership_digest,
                "predecessor_chain_id": None,
                "predecessor_release_digest": None,
            },
        )
        ownership_intent_digest = str(events[-1]["digest"])
        state = self.append_merge_event(
            events,
            state,
            at="2026-08-28T12:00:02Z",
            event_name="ownership_claimed",
            generation_digest=None,
            direct_payload={
                "ownership_intent_digest": ownership_intent_digest,
                "claim_inode": 1,
                "claim_digest": ownership_digest,
                "predecessor_chain_id": None,
                "predecessor_release_digest": None,
            },
        )
        bootstrap_nonce = hashlib.sha256(b"bootstrap-fetch").hexdigest()[:32]
        state = self.append_merge_event(
            events,
            state,
            at="2026-08-28T12:00:03Z",
            event_name="fetch_intent",
            generation_digest=None,
            direct_payload={
                "repository": str(self.repo.resolve()),
                "worktree": worktree_identity,
                "branch": initial["branch"],
                "target": initial["target"],
                "pre_fetch_head": candidate_head,
                "policy_digest": policy_digest,
                "operation_nonce": bootstrap_nonce,
                "attempt": 1,
            },
        )
        state = self.append_merge_event(
            events,
            state,
            at="2026-08-28T12:00:04Z",
            event_name="fetch_result",
            generation_digest=generation_digest,
            delta={
                "candidate": candidate,
                "tier": {"control": False, "categories": []},
                "state": "verifying",
                "integration": {
                    **integration_baseline,
                    "intent": {
                        "operation": "fetch-result",
                        "operation_nonce": bootstrap_nonce,
                        "attempt": 1,
                        "result": "success",
                        "resolved_tip": base,
                    },
                },
            },
        )
        gate_one = {
            "result": "passed",
            "generation_digest": generation_digest,
            "criterion": "gate-1: full unittest discovery",
            "command_argv": ["python3", "-m", "unittest", "discover", "-s", "tests"],
        }
        state = self.append_merge_event(
            events,
            state,
            at="2026-08-28T12:00:05Z",
            event_name="gate_recorded",
            generation_digest=generation_digest,
            delta={"steps": {"gate-1": [gate_one]}},
        )
        assertion_gate = {
            "result": "passed",
            "generation_digest": generation_digest,
            "criterion": "gate-2: assertion-quality sensor",
            "command_argv": ["python3", "scripts/forge/check-test-quality.py"],
        }
        state = self.append_merge_event(
            events,
            state,
            at="2026-08-28T12:00:06Z",
            event_name="gate_recorded",
            generation_digest=generation_digest,
            delta={
                "state": "reviewing",
                "steps": {
                    "gate-1": [gate_one],
                    "assertion-sensor": assertion_gate,
                }
            },
        )
        review = {
            "iteration": 1,
            "request": {
                "candidate": candidate_head,
                "package": package_path.relative_to(self.repo).as_posix(),
                "package_digest": package_digest,
                "reviewer": "review-final",
                "iteration": 1,
            },
        }
        state = self.append_merge_event(
            events,
            state,
            at="2026-08-28T12:00:07Z",
            event_name="review_requested",
            generation_digest=generation_digest,
            delta={"review": review},
        )
        review = {
            **review,
            "verdict": {
                "verdict": "PASS",
                "candidate": candidate_head,
                "package_digest": package_digest,
                "reviewer_role": "review-final",
                "iteration": 1,
            },
        }
        authorization = {
            "candidate_head": candidate_head,
            "generation_digest": generation_digest,
            "diff_summary": "fixture merge diff",
            "control_paths": [],
            "review_verdict": "PASS",
            "recorded_at": "2026-08-28T12:00:08Z",
        }
        state = self.append_merge_event(
            events,
            state,
            at="2026-08-28T12:00:08Z",
            event_name="review_attached",
            generation_digest=generation_digest,
            delta={
                "review": review,
                "state": "authorized",
                "authorization": authorization,
            },
        )
        epoch_nonce = hashlib.sha256(b"merge-epoch").hexdigest()[:32]
        projected_epoch = {
            "operation_nonce": epoch_nonce,
            "generation_digest": generation_digest,
            "intent_digest": None,
            "started_at": "2026-08-28T12:00:09Z",
        }
        state = self.append_merge_event(
            events,
            state,
            at="2026-08-28T12:00:09Z",
            event_name="epoch_intent",
            generation_digest=generation_digest,
            delta={
                "state": "rebasing",
                "integration": {
                    **integration_baseline,
                    "epoch": projected_epoch,
                    "intent": {
                        "operation": "epoch",
                        "operation_nonce": epoch_nonce,
                        "generation_digest": generation_digest,
                        "intent_digest": None,
                    },
                },
            },
        )
        epoch_intent_digest = str(events[-1]["digest"])
        epoch_payload = events[-1]["payload"]
        self.assertIsNone(
            epoch_payload["delta"]["integration"]["epoch"]["intent_digest"]
        )
        epoch = dict(state["integration"]["epoch"])
        self.assertEqual(epoch["intent_digest"], epoch_intent_digest)
        state = self.append_merge_event(
            events,
            state,
            at="2026-08-28T12:00:10Z",
            event_name="fetch_intent",
            generation_digest=generation_digest,
            delta={
                "integration": {
                    **integration_baseline,
                    "epoch": epoch,
                    "intent": {
                        "operation": "fetch",
                        "operation_nonce": epoch_nonce,
                        "generation_digest": generation_digest,
                        "attempt": 2,
                    },
                }
            },
        )
        state = self.append_merge_event(
            events,
            state,
            at="2026-08-28T12:00:11Z",
            event_name="fetch_result",
            generation_digest=generation_digest,
            delta={
                "integration": {
                    **integration_baseline,
                    "epoch": epoch,
                    "intent": {
                        "operation": "fetch-result",
                        "operation_nonce": epoch_nonce,
                        "generation_digest": generation_digest,
                        "result": "unchanged",
                        "resolved_tip": base,
                    },
                }
            },
        )
        pre_rebase = {
            "head": candidate_head,
            "remote_tip": base,
            "generation_digest": generation_digest,
            "operation_nonce": epoch_nonce,
        }
        state = self.append_merge_event(
            events,
            state,
            at="2026-08-28T12:00:12Z",
            event_name="rebase_intent",
            generation_digest=generation_digest,
            delta={
                "integration": {
                    **integration_baseline,
                    "epoch": epoch,
                    "intent": {
                        "operation": "rebase",
                        "operation_nonce": epoch_nonce,
                        "generation_digest": generation_digest,
                        "pre_rebase": pre_rebase,
                    },
                    "pre_rebase": pre_rebase,
                }
            },
        )
        state = self.append_merge_event(
            events,
            state,
            at="2026-08-28T12:00:13Z",
            event_name="rebase_result",
            generation_digest=generation_digest,
            delta={
                "integration": {
                    **integration_baseline,
                    "epoch": epoch,
                    "intent": {
                        "operation": "rebase-result",
                        "operation_nonce": epoch_nonce,
                        "generation_digest": generation_digest,
                        "result": "unchanged-fast-forward",
                        "head": candidate_head,
                    },
                    "pre_rebase": pre_rebase,
                }
            },
        )
        push_intent = {
            "expected_old_tip": base,
            "intended_head": candidate_head,
            "destination_ref": "refs/heads/fixture-main",
            "intended_at": "2026-08-28T12:00:14Z",
            "result": None,
            "attempted_heads": [candidate_head],
            "landed_head": None,
        }
        state = self.append_merge_event(
            events,
            state,
            at="2026-08-28T12:00:14Z",
            event_name="push_intent",
            generation_digest=generation_digest,
            delta={
                "state": "pushing",
                "integration": {
                    **integration_baseline,
                    "epoch": epoch,
                    "intent": {
                        "operation": "push",
                        "operation_nonce": epoch_nonce,
                        "generation_digest": generation_digest,
                        "intended_head": candidate_head,
                    },
                    "pre_rebase": pre_rebase,
                    "push": push_intent,
                },
            },
        )
        push_intent_digest = str(events[-1]["digest"])
        push_result = {
            "classification": "success",
            "exit": 0,
            "inflight_digest": hashlib.sha256(b"merge-inflight").hexdigest(),
            "output_digest": hashlib.sha256(b"merge-output").hexdigest(),
            "launch_failed": False,
            "timed_out": False,
            "output_limit_exceeded": False,
            "recorded_at": "2026-08-28T12:00:15Z",
        }
        push = {
            **push_intent,
            "result": push_result,
            "landed_head": candidate_head,
        }
        observed = {
            "exists": True,
            "oid": remote_head,
            "contains_intended_head": True,
            "attempted_head_containment": [
                {"head": candidate_head, "contained": True}
            ],
            "observed_at": "2026-08-28T12:00:15Z",
            "inflight_digest": push_result["inflight_digest"],
            "output_digest": push_result["output_digest"],
        }
        state = self.append_merge_event(
            events,
            state,
            at="2026-08-28T12:00:15Z",
            event_name="push_observed",
            generation_digest=generation_digest,
            delta={
                "state": "pushed",
                "integration": {
                    **integration_baseline,
                    "epoch": epoch,
                    "intent": {
                        "schema": "forge-remote-observation-intent/1",
                        "transaction": "merge",
                        "chain_id": self.chain_id,
                        "attempt_identity": epoch_intent_digest,
                        "phase": "post-push",
                        "push_intent_digest": push_intent_digest,
                    },
                    "observed": observed,
                    "pre_rebase": pre_rebase,
                    "push": push,
                },
            },
        )
        state = self.append_merge_event(
            events,
            state,
            at="2026-08-28T12:00:16Z",
            event_name="cleanup_intent",
            generation_digest=generation_digest,
            delta={
                "cleanup": {
                    "condition": "none",
                    "intent": {
                        "operation_nonce": epoch_nonce,
                        "generation_digest": generation_digest,
                        "started_at": "2026-08-28T12:00:16Z",
                    },
                }
            },
        )
        state = self.append_merge_event(
            events,
            state,
            at="2026-08-28T12:00:17Z",
            event_name="cleanup_result",
            generation_digest=generation_digest,
            delta={"cleanup": {"condition": "none"}},
        )
        terminal_preconditions_digest = hashlib.sha256(
            canonical(
                {
                    "state": state["state"],
                    "candidate": state["candidate"],
                    "integration": state["integration"],
                    "cleanup": state["cleanup"],
                    "claim": state["worktree"]["claim"],
                }
            )
        ).hexdigest()
        state = self.append_merge_event(
            events,
            state,
            at="2026-08-28T12:00:18Z",
            event_name="ownership_release_intent",
            generation_digest=generation_digest,
            direct_payload={
                "target_terminal": "closed",
                "terminal_disposition": "ordinary",
                "source_state": "pushed",
                "terminal_preconditions_digest": terminal_preconditions_digest,
                "release_mode": "acquired",
            },
        )
        release_intent_digest = str(events[-1]["digest"])
        claim_observation_digest = hashlib.sha256(
            canonical(
                {
                    "claim_path": claim_path,
                    "exists": True,
                    "inode": 1,
                    "digest": ownership_digest,
                }
            )
        ).hexdigest()
        state = self.append_merge_event(
            events,
            state,
            at="2026-08-28T12:00:19Z",
            event_name="ownership_released",
            generation_digest=generation_digest,
            direct_payload={
                "release_intent_digest": release_intent_digest,
                "release_mode": "acquired",
                "terminal_disposition": "ordinary",
                "claim_inode": 1,
                "claim_digest": ownership_digest,
                "claim_observation_digest": claim_observation_digest,
            },
        )
        state = self.append_merge_event(
            events,
            state,
            at="2026-08-28T12:00:20Z",
            event_name="closed",
            generation_digest=generation_digest,
            delta={"state": "closed"},
        )

        events_raw = b"".join(canonical(event) + b"\n" for event in events)
        state_raw = canonical(state) + b"\n"
        decoded, family, _first_at, _last_at = ARCHIVE.decode_event_log(
            self.chain_id, events_raw
        )
        self.assertEqual(family, "merge")
        replay_entries = ARCHIVE.replay_captured_unbound_chain(
            self.chain_id, state, decoded, family
        )
        eligible = ARCHIVE.derive_captured_ingest_eligible_records(
            self.repo, state, replay_entries, family, self.task_id
        )
        selected: list[str] = []
        for descriptor in eligible:
            if descriptor.event_digest not in selected:
                selected.append(descriptor.event_digest)
        self.assertEqual(len(selected), 4)
        outcome_map = {
            "schema": "forge-chain-ingest-outcome-map/1",
            "chain_id": self.chain_id,
            "task": self.task_id,
            "task_status": "complete",
            "event_digests": selected,
        }
        return (
            state_raw,
            events_raw,
            canonical(outcome_map) + b"\n",
            candidate_head,
            base,
            eligible,
        )

    def test_real_merge_ingest_closes_and_renders_deterministically(self) -> None:
        CLI.register_coordination_seams()
        ARCHIVE._CLI_INGEST_AUTHORITY = CLI
        (
            state_raw,
            events_raw,
            outcome_raw,
            candidate_head,
            base,
            eligible,
        ) = self.build_real_merge_package()

        chains = self.repo / ".forge" / "chains"
        chains.mkdir(parents=True)
        (chains / f"{self.chain_id}.json").write_bytes(state_raw)
        (chains / f"{self.chain_id}.events.jsonl").write_bytes(events_raw)

        with self.cli_context():
            _batch, builders, journal = CLI._coordination_modules()
            builders.run_open(
                self.repo,
                self.run_id,
                idempotency_key=hashlib.sha256(b"merge-matrix-open").hexdigest(),
                goal="Ingest one already-landed merge chain",
                scope=["docs/**"],
                plugin_ref="forge-revision9-matrix",
            )
            builders.task_start(
                self.repo,
                self.run_id,
                idempotency_key=hashlib.sha256(b"merge-matrix-task").hexdigest(),
                task=self.task_id,
                goal="Prove merge ingest and archive parity",
                acceptance=["Replay, ingest, close, and rerender are exact"],
                files=["docs/guide.md"],
            )

        source_dir = self.repo / "external-merge"
        source_dir.mkdir()
        sources = {
            "state-file": ("external-merge/state.json", state_raw),
            "events-file": ("external-merge/events.jsonl", events_raw),
            "outcome-map": ("external-merge/outcome-map.json", outcome_raw),
        }
        for _name, (relative, raw) in sources.items():
            (self.repo / relative).write_bytes(raw)
        ingest_key = hashlib.sha256(b"merge-matrix-ingest").hexdigest()
        ingest_argv = (
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
            ingest_key,
        )
        result = self.invoke_cli(*ingest_argv)
        self.assertEqual(result["reason_code"], "ok")

        run_dir = self.repo / ".codex-orchestrator" / "runs" / self.run_id
        journal_path = run_dir / "journal.jsonl"
        receipts_path = run_dir / journal.BATCH_RECEIPTS_NAME
        records, _journal_raw = ARCHIVE.stable_journal_snapshot(run_dir)
        bound = [
            record
            for record in records
            if record.get("type") in {"verification", "decision"}
            and isinstance(record.get("binding"), dict)
        ]
        self.assertEqual(len(bound), len(eligible))
        self.assertTrue(
            all(
                record["binding"]["candidate"]
                == {
                    "kind": "git-range",
                    "value": {"base": base, "head": candidate_head},
                }
                for record in bound
            )
        )
        self.assertEqual(
            [record["type"] for record in records[-2:]], ["decision", "task"]
        )
        self.assertEqual(records[-2]["outcome"], "chain-landing")
        self.assertEqual(records[-1]["status"], "complete")

        journal_before_retry = journal_path.read_bytes()
        receipts_before_retry = receipts_path.read_bytes()
        retry = self.invoke_cli(*ingest_argv)
        self.assertEqual(retry["reason_code"], "ok")
        self.assertEqual(journal_path.read_bytes(), journal_before_retry)
        self.assertEqual(receipts_path.read_bytes(), receipts_before_retry)
        self.assertFalse((run_dir / journal.BATCH_INTENT_NAME).exists())

        with self.cli_context():
            pre_close = journal.validate_run(run_dir, gates=True)
            self.assertEqual(pre_close["issues"], [], pre_close)
            self.assertTrue(pre_close["ok"], pre_close)
            builders.run_close(
                self.repo,
                self.run_id,
                idempotency_key=hashlib.sha256(b"merge-matrix-close").hexdigest(),
                judgment="passed",
                summary="The retrospective merge proof is journal-complete",
                risks=[],
                follow_ups=[],
            )
            post_close = journal.validate_run(run_dir, gates=True)
        self.assertEqual(post_close["issues"], [])
        self.assertTrue(post_close["ok"])
        post_close_path = run_dir / "post-close-validation.json"
        post_close_path.write_bytes(canonical(post_close) + b"\n")

        closed_records, _closed_raw = ARCHIVE.stable_journal_snapshot(run_dir)
        embedded_pre_close = next(
            record["validation"]
            for record in closed_records
            if record.get("type") == "run_closed"
        )
        fresh_pre_close = ARCHIVE.recompute_pre_close_validation(
            run_dir, closed_records
        )
        self.assertEqual(
            fresh_pre_close,
            embedded_pre_close,
            {"fresh": fresh_pre_close, "embedded": embedded_pre_close},
        )
        required_ids = ARCHIVE.binding_chain_ids(closed_records, True)
        package = ARCHIVE.capture_archive_chain_package(
            self.repo,
            run_dir,
            closed_records,
            required_ids,
            activated=True,
        )
        self.assertEqual(len(package.captured), 1)
        captured = package.captured[0]
        self.assertEqual(captured.chain.family, "merge")
        self.assertEqual(captured.chain.state_file.raw, state_raw)
        self.assertEqual(captured.chain.events_file.raw, events_raw)
        self.assertEqual(captured.eligible_records, eligible)

        with self.cli_context():
            first = ARCHIVE.render_archive_candidate(
                repo=self.repo,
                run_dir=run_dir,
                closing_head=candidate_head,
                legacy_recovered_head=None,
                legacy_approval=None,
                post_close_validation=post_close_path,
            )
            second = ARCHIVE.render_archive_candidate(
                repo=self.repo,
                run_dir=run_dir,
                closing_head=candidate_head,
                legacy_recovered_head=None,
                legacy_approval=None,
                post_close_validation=post_close_path,
            )
        self.assertEqual(first, second)
        rendered = first.decode("utf-8")
        self.assert_rendered_chain_bytes(
            rendered,
            family="merge",
            state_raw=state_raw,
            events_raw=events_raw,
            closing_head=candidate_head,
        )

    def test_real_commit_ingest_closes_and_renders_deterministically(self) -> None:
        CLI.register_coordination_seams()
        ARCHIVE._CLI_INGEST_AUTHORITY = CLI
        self.change("src/app.py", "VALUE = 2\n")
        started = self.invoke_cli(
            "commit",
            "start",
            "--paths",
            "src/app.py",
            "--declare-tier",
            "hard",
        )
        chain_id = str(started["chain_id"])
        self.assertEqual(self.state(chain_id)["tier"]["effective"], "hard")
        verified = self.invoke_cli("--chain-id", chain_id, "verify")
        self.assertEqual(verified["state"], "reviewing")
        requested = self.invoke_cli(
            "--chain-id", chain_id, "review", "request"
        )
        self.assertEqual(requested["state"], "reviewing")
        request = self.state(chain_id)["review"]["request"]
        self.assertIsInstance(request, dict)
        self.assertEqual(request["reviewer"], "review-final")
        verdict = self.write_verdict("revision9-matrix-pass.txt", "PASS", request)
        reviewed = self.invoke_cli(
            "--chain-id",
            chain_id,
            "review",
            "attach",
            "--verdict-file",
            str(verdict),
        )
        self.assertEqual(reviewed["state"], "authorized")
        finalized = self.invoke_cli(
            "--chain-id",
            chain_id,
            "commit",
            "finalize",
            "--message",
            "Create real commit archive parity fixture",
        )
        self.assertEqual(finalized["state"], "closed")

        state_raw = self.state_path(chain_id).read_bytes()
        events_raw = self.events_path(chain_id).read_bytes()
        state = json.loads(state_raw)
        events, family, _first_at, _last_at = ARCHIVE.decode_event_log(
            chain_id, events_raw
        )
        self.assertEqual(family, "commit")
        replay_entries = ARCHIVE.replay_captured_unbound_chain(
            chain_id, state, events, family
        )
        eligible = ARCHIVE.derive_captured_ingest_eligible_records(
            self.repo, state, replay_entries, family, self.task_id
        )
        self.assertEqual(
            sum(
                descriptor.criterion == "gate-3: review-final verdict"
                for descriptor in eligible
            ),
            1,
        )
        self.assertEqual(
            sum(descriptor.outcome == "chain-approval" for descriptor in eligible),
            0,
        )
        self.assertEqual(
            sum(descriptor.outcome == "chain-landing" for descriptor in eligible),
            1,
        )
        selected: list[str] = []
        for descriptor in eligible:
            if descriptor.event_digest not in selected:
                selected.append(descriptor.event_digest)
        self.assertGreater(len(selected), 1)

        run_id = "run-20260828-commit-ingest-matrix"
        with self.cli_context():
            _batch, builders, journal = CLI._coordination_modules()
            builders.run_open(
                self.repo,
                run_id,
                idempotency_key=hashlib.sha256(b"commit-matrix-open").hexdigest(),
                goal="Ingest one produced commit chain",
                scope=["src/**"],
                plugin_ref="forge-revision9-matrix",
            )
            builders.task_start(
                self.repo,
                run_id,
                idempotency_key=hashlib.sha256(b"commit-matrix-task").hexdigest(),
                task=self.task_id,
                goal="Prove commit ingest and archive parity",
                acceptance=["Replay, ingest, close, and rerender are exact"],
                files=["src/app.py"],
            )

        external = self.repo / "external-commit"
        external.mkdir()
        outcome_map = {
            "schema": "forge-chain-ingest-outcome-map/1",
            "chain_id": chain_id,
            "task": self.task_id,
            "task_status": "complete",
            "event_digests": selected,
        }
        sources = {
            "state-file": ("external-commit/state.json", state_raw),
            "events-file": ("external-commit/events.jsonl", events_raw),
            "outcome-map": (
                "external-commit/outcome-map.json",
                canonical(outcome_map) + b"\n",
            ),
        }
        for _field, (relative, raw) in sources.items():
            (self.repo / relative).write_bytes(raw)
        closing_head = self.git("rev-parse", "HEAD")
        ingest_key = hashlib.sha256(b"commit-matrix-ingest").hexdigest()
        ingest_argv = (
            "--run-id",
            run_id,
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
            closing_head,
            "--task-status",
            "complete",
            "--idempotency-key",
            ingest_key,
        )
        ingested = self.invoke_cli(*ingest_argv)
        self.assertEqual(ingested["reason_code"], "ok")

        run_dir = self.repo / ".codex-orchestrator" / "runs" / run_id
        journal_path = run_dir / "journal.jsonl"
        receipts_path = run_dir / journal.BATCH_RECEIPTS_NAME
        records, _journal_raw = ARCHIVE.stable_journal_snapshot(run_dir)
        bound = [
            record
            for record in records
            if record.get("type") in {"verification", "decision"}
            and isinstance(record.get("binding"), dict)
        ]
        self.assertEqual(len(bound), len(eligible))
        candidate_digest = state["candidate"]["sha256"]
        self.assertTrue(
            all(
                record["binding"]["candidate"]
                == {"kind": "staged-diff-sha256", "value": candidate_digest}
                for record in bound
            )
        )

        journal_before_retry = journal_path.read_bytes()
        receipts_before_retry = receipts_path.read_bytes()
        retry = self.invoke_cli(*ingest_argv)
        self.assertEqual(retry["reason_code"], "ok")
        self.assertEqual(journal_path.read_bytes(), journal_before_retry)
        self.assertEqual(receipts_path.read_bytes(), receipts_before_retry)
        self.assertFalse((run_dir / journal.BATCH_INTENT_NAME).exists())

        with self.cli_context():
            pre_close = journal.validate_run(run_dir, gates=True)
            self.assertEqual(pre_close["issues"], [], pre_close)
            self.assertTrue(pre_close["ok"], pre_close)
            builders.run_close(
                self.repo,
                run_id,
                idempotency_key=hashlib.sha256(b"commit-matrix-close").hexdigest(),
                judgment="passed",
                summary="The retrospective commit proof is journal-complete",
                risks=[],
                follow_ups=[],
            )
            post_close = journal.validate_run(run_dir, gates=True)
        self.assertEqual(post_close["issues"], [])
        self.assertTrue(post_close["ok"])
        post_close_path = run_dir / "post-close-validation.json"
        post_close_path.write_bytes(canonical(post_close) + b"\n")

        closed_records, _closed_raw = ARCHIVE.stable_journal_snapshot(run_dir)
        required_ids = ARCHIVE.binding_chain_ids(closed_records, True)
        package = ARCHIVE.capture_archive_chain_package(
            self.repo,
            run_dir,
            closed_records,
            required_ids,
            activated=True,
        )
        self.assertEqual(len(package.captured), 1)
        captured = package.captured[0]
        self.assertEqual(captured.chain.family, "commit")
        self.assertEqual(captured.chain.state_file.raw, state_raw)
        self.assertEqual(captured.chain.events_file.raw, events_raw)
        self.assertEqual(captured.eligible_records, eligible)

        with self.cli_context():
            first = ARCHIVE.render_archive_candidate(
                repo=self.repo,
                run_dir=run_dir,
                closing_head=closing_head,
                legacy_recovered_head=None,
                legacy_approval=None,
                post_close_validation=post_close_path,
            )
            second = ARCHIVE.render_archive_candidate(
                repo=self.repo,
                run_dir=run_dir,
                closing_head=closing_head,
                legacy_recovered_head=None,
                legacy_approval=None,
                post_close_validation=post_close_path,
            )
        self.assertEqual(first, second)
        self.assert_rendered_chain_bytes(
            first.decode("utf-8"),
            family="commit",
            state_raw=state_raw,
            events_raw=events_raw,
            closing_head=closing_head,
        )
