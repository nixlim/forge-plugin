from __future__ import annotations

import copy
import contextlib
import datetime as dt
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
CLI_PATH = ROOT / "scripts/forge/cli.py"
CHAIN_ID = "c-2026-08-21T120000Z-0001"


def load_script(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


CLI = load_script("forge_cli_chain_finalize_tests", CLI_PATH)


POLICY = """\
<!-- FORGE:REGION project-overview BEGIN -->
Finalize test fixture.
<!-- FORGE:REGION project-overview END -->
<!-- FORGE:REGION file-categories BEGIN -->
| Category | File patterns |
|---|---|
| docs | `*.txt` |
<!-- FORGE:REGION file-categories END -->
<!-- FORGE:REGION stack-validations BEGIN -->
```bash
true
```
<!-- FORGE:REGION stack-validations END -->
<!-- FORGE:REGION gate1-test-command BEGIN -->
```bash
true
```
<!-- FORGE:REGION gate1-test-command END -->
<!-- FORGE:REGION changelog-policy BEGIN -->
No changelog gate is configured for this repository.
<!-- FORGE:REGION changelog-policy END -->
<!-- FORGE:REGION review-prompt-project-focus BEGIN -->
Review the exact staged bytes.
<!-- FORGE:REGION review-prompt-project-focus END -->
<!-- FORGE:REGION project-triggers BEGIN -->
No extra triggers.
<!-- FORGE:REGION project-triggers END -->
<!-- FORGE:REGION completeness-project-items BEGIN -->
- [ ] Focused tests pass.
<!-- FORGE:REGION completeness-project-items END -->
<!-- FORGE:REGION agent-project-context BEGIN -->
Fixture only.
<!-- FORGE:REGION agent-project-context END -->
<!-- FORGE:REGION mutation-testing BEGIN -->
Assertion-quality fallback.
<!-- FORGE:REGION mutation-testing END -->
<!-- FORGE:REGION invariants BEGIN -->
| invariant | check command | enforcement point |
|---|---|---|
<!-- FORGE:REGION invariants END -->
<!-- FORGE:REGION risk-tiers BEGIN -->
Fixture risk rules.
<!-- FORGE:REGION risk-tiers END -->
<!-- FORGE:REGION drift-config BEGIN -->
cadence: 14d
<!-- FORGE:REGION drift-config END -->
<!-- FORGE:REGION trigger-paths BEGIN -->
| Path pattern |
|---|
<!-- FORGE:REGION trigger-paths END -->
"""


def process_result(
    argv: list[str] | tuple[str, ...],
    *,
    returncode: int = 0,
    output: bytes = b"",
    timed_out: bool = False,
    output_limit: bool = False,
):
    return CLI.ProcessResult(
        argv=list(argv),
        returncode=returncode,
        duration_seconds=0.001,
        output=output,
        output_digest=hashlib.sha256(output).hexdigest(),
        timed_out=timed_out,
        output_limit=output_limit,
    )


def helper_name(argv: list[str] | tuple[str, ...]) -> str:
    if len(argv) >= 2 and Path(str(argv[0])).name == "bash":
        return Path(str(argv[1])).name
    return Path(str(argv[-1])).name


class FinalizeFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="forge-finalize-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.hooks = self.root / ".git-hooks-disabled"
        self.hooks.mkdir()
        self.git("init", "-q")
        self.git("config", "user.name", "Forge Test")
        self.git("config", "user.email", "forge-test@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        self.git("config", "core.hooksPath", str(self.hooks))
        (self.root / "forge-project.md").write_text(POLICY, encoding="utf-8")
        (self.root / "tracked.txt").write_text("base\n", encoding="utf-8")
        (self.root / "other.txt").write_text("other base\n", encoding="utf-8")
        self.git("add", "forge-project.md", "tracked.txt", "other.txt")
        self.git("commit", "-q", "-m", "fixture base")

        (self.root / "tracked.txt").write_text("candidate one\n", encoding="utf-8")
        self.git("add", "tracked.txt")
        self.repo = CLI.Repository(self.root)
        policy_sha, policy_raw = self.repo.policy()
        self.policy = CLI.parse_policy(policy_sha, policy_raw)
        self.candidate = self.repo.candidate_hash()
        self.state = CLI._new_state(
            CHAIN_ID,
            self.repo,
            self.repo.head(),
            self.policy,
            ["tracked.txt"],
            "standard",
        )
        self.state["staging"].update(
            {
                "staged_paths": ["tracked.txt"],
                "staged_at": CLI.iso_z(),
            }
        )
        self.state["candidate"] = {
            "sha256": self.candidate,
            "computed_at": CLI.iso_z(),
        }
        self.state["tier"].update(
            {
                "derived": "standard",
                "effective": "standard",
                "control": False,
                "categories": [],
                "classification": {"fixture": True},
            }
        )
        passed = {"candidate": self.candidate, "result": "passed"}
        self.state["steps"] = {
            "classification": [dict(passed)],
            "gate-1": [
                {**passed, "env_fingerprint": "fixture-context"},
                {**passed, "env_fingerprint": "fixture-context"},
            ],
            "assertion-sensor": [dict(passed)],
            "secret-scan": [dict(passed)],
        }
        self.state["review"]["verdict"] = {
            "verdict": "PASS",
            "candidate": self.candidate,
        }
        CLI._transition_state(self.state, "verifying")
        CLI._transition_state(self.state, "reviewing")
        CLI._issue_authorization(self.state)
        self.store = CLI.ChainStore(self.repo.common_root())
        self.store.create(self.state, "fixture_authorized", {"fixture": True})
        self.options = CLI.CLIOptions(
            chain_id=CHAIN_ID,
            repo=str(self.root),
            original_argv=("commit", "finalize", "--message", "fixture commit"),
        )
        self.context = CLI.CommandContext(
            repo=self.repo,
            store=self.store,
            options=self.options,
            policy=self.policy,
        )
        self.engine = CLI.Engine(self.context)

    def git(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["git", *arguments],
            cwd=self.root,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            self.fail(
                f"git {' '.join(arguments)} failed ({result.returncode}): "
                f"{result.stderr}"
            )
        return result

    def persist(self, event: str = "fixture_adjusted") -> None:
        self.store.persist(self.state, event, {"fixture": True})

    def helper_runner(
        self,
        *,
        fail: str | None = None,
        failure_output: bytes = b"fixture helper refusal",
    ):
        calls: list[str] = []

        def run(argv, **_kwargs):
            helper = helper_name(argv)
            if helper == "check-halt.sh":
                self.assertEqual(list(argv)[2:], ["commit"])
            calls.append(helper)
            if helper == fail:
                return process_result(argv, returncode=1, output=failure_output)
            return process_result(argv)

        return calls, run

    @contextlib.contextmanager
    def patched_helpers(self, *, fail: str | None = None, output: bytes = b""):
        calls, runner = self.helper_runner(
            fail=fail,
            failure_output=output or b"fixture helper refusal",
        )
        with mock.patch.object(CLI, "run_bounded", side_effect=runner), mock.patch.object(
            CLI.Engine, "_emit_decision", autospec=True
        ):
            yield calls

    def assert_refusal(
        self,
        expected_code,
        expected_message: str,
        *,
        fail_helper: str | None = None,
        helper_output: bytes = b"",
    ):
        with self.patched_helpers(fail=fail_helper, output=helper_output):
            with self.assertRaises(CLI.Refusal) as raised:
                self.engine.finalize("fixture commit")
        refusal = raised.exception
        self.assertIs(refusal.reason_code, expected_code)
        self.assertEqual(refusal.message, expected_message)
        self.assertEqual(refusal.chain["chain_id"], CHAIN_ID)
        return refusal

    def assert_check_can_be_replaced(
        self,
        check_name: str,
        *,
        fail_helper: str | None = None,
    ) -> None:
        replacement = mock.Mock(return_value=True)
        with mock.patch.dict(CLI.FINALIZE_CHECKS, {check_name: replacement}):
            with self.patched_helpers(fail=fail_helper):
                outcome = self.engine.finalize("fixture commit")
        self.assertTrue(outcome.ok)
        self.assertEqual(outcome.state, "closed")
        replacement.assert_called_once()

    def enter_committing(
        self, *, consumed: bool = False, message: str = "fixture commit"
    ) -> str:
        pre_head = self.repo.head()
        self.state["state"] = "committing"
        self.state["authorization"]["consumed"] = consumed
        self.state["authorization"]["consumed_at"] = (
            CLI.iso_z() if consumed else None
        )
        self.state["commit_result"] = {
            "intent": {
                "candidate": self.candidate,
                "pre_head": pre_head,
                "message_digest": CLI.sha256_bytes(
                    CLI.commit_message_bytes(message)
                ),
                "written_at": CLI.iso_z(),
                "lock_session_pid": "4242",
            }
        }
        self.persist("fixture_commit_intent")
        return pre_head


class ChainStoreConcurrencyTests(FinalizeFixture):
    def test_stale_snapshot_cannot_append_or_overwrite_newer_chain_state(self) -> None:
        left = self.store.load(CHAIN_ID)
        right = self.store.load(CHAIN_ID)
        before = self.store._events(CHAIN_ID)
        left["staging"]["anomalies"].append({"kind": "winner"})
        self.store.persist(left, "winner_persisted", {"writer": "left"})

        right["staging"]["anomalies"].append({"kind": "loser"})
        with self.assertRaises(CLI.Refusal) as caught:
            self.store.persist(right, "loser_persisted", {"writer": "right"})

        self.assertIs(caught.exception.reason_code, CLI.ReasonCode.STATE_PRECONDITION)
        after = self.store._events(CHAIN_ID)
        self.assertEqual(len(after), len(before) + 1)
        self.assertEqual(after[-1]["payload"]["event"], "winner_persisted")
        self.assertEqual(after[-1]["sequence"], after[-2]["sequence"] + 1)
        self.assertEqual(after[-1]["prev_digest"], after[-2]["digest"])
        durable = self.store.load(CHAIN_ID)
        self.assertIn({"kind": "winner"}, durable["staging"]["anomalies"])
        self.assertNotIn({"kind": "loser"}, durable["staging"]["anomalies"])


class AuthorizationTests(FinalizeFixture):
    def test_authorization_ttl_is_exactly_thirty_minutes_from_issuance(self) -> None:
        issued = dt.datetime(2026, 8, 21, 12, 34, 56, tzinfo=dt.timezone.utc)
        self.state["created_at"] = "2025-01-01T00:00:00Z"
        self.state["last_event_at"] = "2026-08-20T00:00:00Z"

        with mock.patch.object(CLI, "utc_now", return_value=issued):
            CLI._issue_authorization(self.state)

        authorization = self.state["authorization"]
        self.assertEqual(authorization["issued_at"], "2026-08-21T12:34:56Z")
        self.assertEqual(authorization["expires_at"], "2026-08-21T13:04:56Z")
        self.assertEqual(
            CLI.parse_time(authorization["expires_at"])
            - CLI.parse_time(authorization["issued_at"]),
            dt.timedelta(seconds=CLI.TOKEN_TTL_SECONDS),
        )
        self.assertEqual(authorization["candidate"], self.candidate)
        self.assertFalse(authorization["consumed"])
        self.assertIsNone(authorization["consumed_at"])

    def test_authorization_expiry_boundary_is_fail_closed(self) -> None:
        issued = dt.datetime(2026, 8, 21, 12, 0, 0, tzinfo=dt.timezone.utc)
        with mock.patch.object(CLI, "utc_now", return_value=issued):
            CLI._issue_authorization(self.state)

        with mock.patch.object(
            CLI, "utc_now", return_value=issued + dt.timedelta(minutes=30, seconds=-1)
        ):
            self.assertIsNone(CLI._authorization_problem(self.state))

        boundary = issued + dt.timedelta(minutes=30)
        with mock.patch.object(CLI, "utc_now", return_value=boundary):
            problem = CLI._authorization_problem(self.state)

        self.assertIsNotNone(problem)
        self.assertIs(problem.reason_code, CLI.ReasonCode.TTL_EXPIRED)
        self.assertEqual(
            problem.message,
            "authorization token expired 30 minutes after issuance",
        )
        self.assertEqual(problem.expected, "current time before 2026-08-21T12:30:00Z")
        self.assertEqual(problem.observed, "2026-08-21T12:30:00Z")

    def test_consumed_token_refusal_precedes_expiry_and_pins_diagnostic(self) -> None:
        self.state["authorization"].update(
            {
                "consumed": True,
                "consumed_at": CLI.iso_z(),
                "expires_at": "2000-01-01T00:00:00Z",
            }
        )

        problem = CLI._authorization_problem(self.state)

        self.assertIsNotNone(problem)
        self.assertIs(problem.reason_code, CLI.ReasonCode.TOKEN_CONSUMED)
        self.assertEqual(problem.message, "authorization token was already consumed")
        self.assertEqual(problem.expected, "consumed=false")
        self.assertEqual(problem.observed, "consumed=true")
        self.assertEqual(problem.remediation, f"forge status --chain-id {CHAIN_ID}")

    def test_missing_or_malformed_authorization_token_fails_closed(self) -> None:
        for token in (None, "short", "G" * 32, "a" * 31, "a" * 33):
            with self.subTest(token=token):
                authorization = copy.deepcopy(self.state["authorization"])
                if token is None:
                    authorization.pop("token", None)
                else:
                    authorization["token"] = token
                candidate_state = copy.deepcopy(self.state)
                candidate_state["authorization"] = authorization
                problem = CLI._authorization_problem(candidate_state)
                self.assertIsNotNone(problem)
                self.assertIs(
                    problem.reason_code, CLI.ReasonCode.EVIDENCE_INCOMPLETE
                )
                self.assertEqual(
                    problem.message,
                    "authorization record has no valid 32-hex token",
                )

    def test_authorization_rejects_a_stored_ttl_not_derived_from_issuance(self) -> None:
        issued = dt.datetime(2026, 8, 21, 12, 0, 0, tzinfo=dt.timezone.utc)
        with mock.patch.object(CLI, "utc_now", return_value=issued):
            CLI._issue_authorization(self.state)
        self.state["authorization"]["expires_at"] = "2026-08-21T12:31:00Z"

        with mock.patch.object(
            CLI, "utc_now", return_value=issued + dt.timedelta(minutes=1)
        ):
            problem = CLI._authorization_problem(self.state)

        self.assertIsNotNone(problem)
        self.assertIs(problem.reason_code, CLI.ReasonCode.EVIDENCE_INCOMPLETE)
        self.assertEqual(
            problem.message,
            "authorization TTL is not exactly 30 minutes from issuance",
        )
        self.assertEqual(problem.expected, "2026-08-21T12:30:00Z")
        self.assertEqual(problem.observed, "2026-08-21T12:31:00Z")


class FinalizeCheckTests(FinalizeFixture):
    def test_finalize_registry_has_exact_independent_check_functions(self) -> None:
        self.assertEqual(
            CLI.FINALIZE_CHECKS,
            {
                "evidence-completeness": CLI._finalize_evidence,
                "candidate-byte-identity": CLI._finalize_candidate,
                "ttl-token": CLI._finalize_ttl,
                "tree-index-drift": CLI._finalize_tree_drift,
                "halt": CLI._finalize_halt,
                "lock": CLI._finalize_lock,
            },
        )
        originals = dict(CLI.FINALIZE_CHECKS)
        for name in originals:
            with self.subTest(name=name):
                replacement = mock.Mock(return_value=True)
                with mock.patch.dict(CLI.FINALIZE_CHECKS, {name: replacement}):
                    self.assertIs(CLI.FINALIZE_CHECKS[name], replacement)
                    self.assertEqual(
                        {key: value for key, value in CLI.FINALIZE_CHECKS.items() if key != name},
                        {key: value for key, value in originals.items() if key != name},
                    )

    def test_halt_check_is_load_bearing_and_has_an_independent_seam(self) -> None:
        refusal = self.assert_refusal(
            CLI.ReasonCode.HALT_ENGAGED,
            "operator halt check refused state mutation",
            fail_helper="check-halt.sh",
            helper_output=b"forge: halted by AGENT_HALT",
        )
        self.assertEqual(refusal.expected, "check-halt.sh exit 0")
        self.assertEqual(refusal.observed, "forge: halted by AGENT_HALT")
        self.assertEqual(
            refusal.remediation,
            "operator must inspect and clear the applicable AGENT_HALT sentinel",
        )
        self.assert_check_can_be_replaced(
            "halt", fail_helper="check-halt.sh"
        )

    def test_lock_check_is_load_bearing_and_has_an_independent_seam(self) -> None:
        refusal = self.assert_refusal(
            CLI.ReasonCode.LOCK_UNAVAILABLE,
            "commit lock acquisition failed or timed out",
            fail_helper="acquire-commit-lock.sh",
            helper_output=b"forge: commit lock held by 99",
        )
        self.assertEqual(refusal.expected, "acquire-commit-lock.sh exit 0")
        self.assertEqual(refusal.observed, "forge: commit lock held by 99")
        self.assertEqual(
            refusal.remediation,
            f"forge commit finalize --message <message> --chain-id {CHAIN_ID}",
        )
        self.assert_check_can_be_replaced(
            "lock", fail_helper="acquire-commit-lock.sh"
        )

    def test_candidate_check_is_load_bearing_and_has_an_independent_seam(self) -> None:
        (self.root / "tracked.txt").write_text("candidate two\n", encoding="utf-8")
        self.git("add", "tracked.txt")
        observed = self.repo.candidate_hash()

        refusal = self.assert_refusal(
            CLI.ReasonCode.CANDIDATE_STALE,
            "finalize candidate byte-identity check failed",
        )
        self.assertEqual(refusal.expected, self.candidate)
        self.assertEqual(refusal.observed, observed)
        self.assertEqual(
            refusal.remediation,
            f"forge commit restage --paths <path>... --chain-id {CHAIN_ID}",
        )
        self.assert_check_can_be_replaced("candidate-byte-identity")

    def test_evidence_check_is_load_bearing_and_has_an_independent_seam(self) -> None:
        del self.state["steps"]["assertion-sensor"]
        self.persist()

        refusal = self.assert_refusal(
            CLI.ReasonCode.EVIDENCE_INCOMPLETE,
            "finalize evidence is incomplete at required step: assertion-sensor",
        )
        self.assertEqual(
            refusal.expected,
            "every required mechanical step current-candidate PASS or operator skip",
        )
        self.assertEqual(refusal.observed, "assertion-sensor")
        self.assertEqual(refusal.remediation, f"forge verify --chain-id {CHAIN_ID}")
        self.assert_check_can_be_replaced("evidence-completeness")

    def test_classification_evidence_is_current_and_load_bearing(self) -> None:
        stale = "0" * 64
        self.state["steps"]["classification"] = [
            {"candidate": stale, "result": "passed"}
        ]
        self.persist()

        refusal = self.assert_refusal(
            CLI.ReasonCode.EVIDENCE_INCOMPLETE,
            "finalize requires current-candidate classification evidence",
        )
        self.assertEqual(
            refusal.expected, f"classification PASS naming {self.candidate}"
        )
        self.assertEqual(
            refusal.observed,
            str([{"candidate": stale, "result": "passed"}]),
        )
        self.assertEqual(refusal.remediation, f"forge classify --chain-id {CHAIN_ID}")
        self.assert_check_can_be_replaced("evidence-completeness")

    def test_ttl_check_is_load_bearing_and_has_an_independent_seam(self) -> None:
        self.state["authorization"].update(
            {
                "issued_at": "1999-12-31T23:30:00Z",
                "expires_at": "2000-01-01T00:00:00Z",
            }
        )
        self.persist()

        refusal = self.assert_refusal(
            CLI.ReasonCode.TTL_EXPIRED,
            "authorization token expired 30 minutes after issuance",
        )
        self.assertEqual(refusal.expected, "current time before 2000-01-01T00:00:00Z")
        self.assertRegex(refusal.observed, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        self.assertEqual(
            refusal.remediation,
            f"forge commit restage --paths <path>... --chain-id {CHAIN_ID}",
        )
        self.assert_check_can_be_replaced("ttl-token")

    def test_tree_drift_check_is_load_bearing_and_has_an_independent_seam(self) -> None:
        (self.root / "tracked.txt").write_text(
            "candidate one\nnew unstaged work\n", encoding="utf-8"
        )

        refusal = self.assert_refusal(
            CLI.ReasonCode.DRIFT_TREE_INDEX,
            "working tree differs from staged candidate at finalize: tracked.txt",
        )
        self.assertEqual(
            refusal.expected,
            "tree bytes equal staged bytes or operator index-drift skip",
        )
        self.assertEqual(refusal.observed, "tracked.txt")
        self.assertEqual(
            refusal.remediation,
            f"forge commit restage --paths <path>... --chain-id {CHAIN_ID}",
        )
        self.assert_check_can_be_replaced("tree-index-drift")

    def test_operator_index_drift_skip_is_honored_by_finalize(self) -> None:
        (self.root / "tracked.txt").write_text(
            "candidate one\nnew unstaged work\n", encoding="utf-8"
        )
        self.state["steps"]["user_skips"] = {
            "index-drift": {
                "directed_by": "operator",
                "reason": "commit the staged snapshot",
                "argv_digest": "a" * 64,
                "journaled_at": CLI.iso_z(),
            }
        }
        self.persist()

        with self.patched_helpers():
            outcome = self.engine.finalize("fixture commit")

        self.assertTrue(outcome.ok)
        self.assertEqual(outcome.state, "closed")
        committed = self.git("show", "HEAD:tracked.txt").stdout
        self.assertEqual(committed, "candidate one\n")
        self.assertEqual(
            (self.root / "tracked.txt").read_text(encoding="utf-8"),
            "candidate one\nnew unstaged work\n",
        )


class FinalizeSuccessTests(FinalizeFixture):
    def test_successful_finalize_records_two_phase_order_and_closes(self) -> None:
        pre_head = self.repo.head()
        trace: list[str] = []
        originals = dict(CLI.FINALIZE_CHECKS)

        def traced_check(name: str):
            def run(context):
                result = originals[name](context)
                trace.append(name)
                return result

            return run

        original_persist = self.store.persist

        def traced_persist(state, event, details, **kwargs):
            result = original_persist(state, event, details, **kwargs)
            labels = {
                "commit_intent": "intent-persisted",
                "commit_produced": "sha-persisted",
                "chain_closed": "closed-persisted",
            }
            if event in labels:
                trace.append(labels[event])
            return result

        original_git = self.repo.git

        def traced_git(arguments, **kwargs):
            result = original_git(arguments, **kwargs)
            if list(arguments[:1]) == ["commit"]:
                trace.append("git-commit")
            return result

        original_release = self.engine._release_lock

        def traced_release(session_pid):
            result = original_release(session_pid)
            trace.append("lock-released")
            return result

        replacements = {
            "halt": traced_check("halt"),
            "lock": traced_check("lock"),
            "candidate-byte-identity": traced_check("candidate-byte-identity"),
        }
        with self.patched_helpers() as helper_calls, mock.patch.dict(
            CLI.FINALIZE_CHECKS, replacements
        ), mock.patch.object(
            self.store, "persist", side_effect=traced_persist
        ), mock.patch.object(
            self.repo, "git", side_effect=traced_git
        ), mock.patch.object(
            self.engine, "_release_lock", side_effect=traced_release
        ):
            outcome = self.engine.finalize("subject: commit through Forge")

        self.assertTrue(outcome.ok)
        self.assertIs(outcome.reason_code, CLI.ReasonCode.OK)
        self.assertEqual(outcome.state, "closed")
        self.assertEqual(outcome.next_required_step, "none — chain closed")
        self.assertRegex(
            outcome.message,
            r"^commit [0-9a-f]{40}(?:[0-9a-f]{24})? created and chain closed$",
        )
        self.assertEqual(
            helper_calls,
            ["check-halt.sh", "acquire-commit-lock.sh", "release-commit-lock.sh"],
        )
        self.assertEqual(
            trace,
            [
                "halt",
                "lock",
                "candidate-byte-identity",
                "intent-persisted",
                "git-commit",
                "sha-persisted",
                "closed-persisted",
                "lock-released",
            ],
        )

        closed = self.store.load(CHAIN_ID)
        produced = self.repo.head()
        self.assertNotEqual(produced, pre_head)
        self.assertEqual(closed["state"], "closed")
        self.assertTrue(closed["authorization"]["consumed"])
        self.assertIsNotNone(closed["authorization"]["consumed_at"])
        self.assertEqual(closed["commit_result"]["commit_sha"], produced)
        self.assertEqual(closed["commit_result"]["head_at_commit"], produced)
        self.assertEqual(
            self.git("show", "-s", "--format=%B", "HEAD").stdout,
            "subject: commit through Forge\n\n",
        )
        self.assertEqual(self.git("show", "HEAD:tracked.txt").stdout, "candidate one\n")
        events = [
            record["payload"]["event"] for record in self.store._events(CHAIN_ID)
        ]
        self.assertEqual(
            events[-4:],
            [
                "commit_intent",
                "authorization_consumed",
                "commit_produced",
                "chain_closed",
            ],
        )

    def test_interleaved_finalizers_cannot_reopen_the_closed_chain(self) -> None:
        pre_head = self.repo.head()
        winner: list[CLI.Outcome] = []

        def release_waiting_finalizer(_context):
            with mock.patch.dict(
                CLI.FINALIZE_CHECKS, {"lock": lambda _inner_context: True}
            ):
                winner.append(
                    CLI.Engine(self.context).finalize("winning concurrent commit")
                )
            return True

        with self.patched_helpers(), mock.patch.dict(
            CLI.FINALIZE_CHECKS, {"lock": release_waiting_finalizer}
        ):
            try:
                self.engine.finalize("stale concurrent commit")
            except CLI.Refusal:
                pass

        self.assertEqual(len(winner), 1)
        self.assertTrue(winner[0].ok)
        self.assertEqual(winner[0].state, "closed")
        closed = self.store.load(CHAIN_ID)
        self.assertEqual(closed["state"], "closed")
        self.assertEqual(closed["commit_result"]["commit_sha"], self.repo.head())
        self.assertTrue(closed["authorization"]["consumed"])
        self.assertEqual(
            self.git("rev-list", "--count", f"{pre_head}..HEAD").stdout.strip(),
            "1",
        )
        self.assertEqual(
            self.git("show", "-s", "--format=%B", "HEAD").stdout,
            "winning concurrent commit\n\n",
        )

    def test_finalize_serializes_a_concurrent_restage_until_after_close(self) -> None:
        original_candidate_check = CLI.FINALIZE_CHECKS["candidate-byte-identity"]
        attempted = threading.Event()
        restage_errors: list[BaseException] = []
        restage_thread: list[threading.Thread] = []

        def run_restage() -> None:
            (self.root / "tracked.txt").write_text(
                "candidate changed during finalize\n", encoding="utf-8"
            )
            attempted.set()
            try:
                CLI.Engine(self.context).restage(["tracked.txt"])
            except BaseException as exc:
                restage_errors.append(exc)

        def candidate_then_contend(context) -> bool:
            result = original_candidate_check(context)
            worker = threading.Thread(target=run_restage, daemon=True)
            restage_thread.append(worker)
            worker.start()
            self.assertTrue(attempted.wait(2.0))
            self.assertTrue(worker.is_alive())
            return result

        with self.patched_helpers(), mock.patch.dict(
            CLI.FINALIZE_CHECKS,
            {"candidate-byte-identity": candidate_then_contend},
        ):
            outcome = self.engine.finalize("serialized candidate")
            restage_thread[0].join(2.0)

        self.assertTrue(outcome.ok)
        self.assertFalse(restage_thread[0].is_alive())
        self.assertEqual(len(restage_errors), 1)
        self.assertIsInstance(restage_errors[0], CLI.Refusal)
        self.assertIs(
            restage_errors[0].reason_code, CLI.ReasonCode.STATE_PRECONDITION
        )
        self.assertEqual(self.store.load(CHAIN_ID)["state"], "closed")
        self.assertEqual(
            self.git("show", "HEAD:tracked.txt").stdout,
            "candidate one\n",
        )


class FinalizeRecoveryTests(FinalizeFixture):
    def assert_recovery_uses_current_lock(
        self, invoke, *, post_commit: bool
    ) -> None:
        pre_head = self.enter_committing(consumed=post_commit)
        if post_commit:
            self.git("commit", "-q", "-m", "fixture commit")
            self.assertNotEqual(self.repo.head(), pre_head)
        trace: list[str] = []
        lock_sessions: list[str | None] = []
        release_sessions: list[str | None] = []
        load_count = 0
        original_load = self.store.load
        original_persist = self.store.persist

        def traced_load(chain_id):
            nonlocal load_count
            load_count += 1
            trace.append("initial-load" if load_count == 1 else "reload-under-lock")
            loaded = original_load(chain_id)
            if load_count == 1:
                stale = copy.deepcopy(loaded)
                if post_commit:
                    stale["commit_result"]["intent"]["message_digest"] = "0" * 64
                else:
                    stale["authorization"]["consumed"] = True
                    stale["authorization"]["consumed_at"] = CLI.iso_z()
                return stale
            return loaded

        def traced_persist(state, event, details, **kwargs):
            result = original_persist(state, event, details, **kwargs)
            if event in {"commit_intent_rolled_back", "commit_close_recovered"}:
                trace.append("recovery-persisted")
            return result

        def traced_helpers(argv, **kwargs):
            helper = helper_name(argv)
            if helper == "check-halt.sh":
                self.assertEqual(list(argv)[2:], ["commit"])
                trace.append("halt")
            elif helper == "acquire-commit-lock.sh":
                trace.append("lock-acquired")
                lock_sessions.append(kwargs.get("env", {}).get("FORGE_SESSION_PID"))
            elif helper == "release-commit-lock.sh":
                trace.append("lock-released")
                release_sessions.append(kwargs.get("env", {}).get("FORGE_SESSION_PID"))
            return process_result(argv)

        with mock.patch.dict(os.environ, {"FORGE_SESSION_PID": "7777"}), mock.patch.object(
            CLI, "run_bounded", side_effect=traced_helpers
        ), mock.patch.object(
            CLI.Engine, "_emit_decision", autospec=True
        ), mock.patch.object(
            self.store, "load", side_effect=traced_load
        ), mock.patch.object(
            self.store, "persist", side_effect=traced_persist
        ):
            outcome = invoke()

        self.assertTrue(outcome.ok)
        self.assertEqual(outcome.state, "closed" if post_commit else "authorized")
        if not post_commit:
            self.assertEqual(self.repo.head(), pre_head)
        self.assertEqual(
            trace,
            [
                "initial-load",
                "halt",
                "lock-acquired",
                "reload-under-lock",
                "recovery-persisted",
                "lock-released",
            ],
        )
        self.assertEqual(lock_sessions, ["7777"])
        self.assertEqual(release_sessions, ["7777"])
        self.assertNotIn("4242", release_sessions)
        recovered = self.store.load(CHAIN_ID)
        self.assertEqual(
            recovered["state"], "closed" if post_commit else "authorized"
        )
        self.assertEqual(recovered["authorization"]["consumed"], post_commit)

    def test_status_recovery_halts_locks_reloads_and_releases_current_lock(self) -> None:
        self.assert_recovery_uses_current_lock(self.engine.status, post_commit=False)

    def test_finalize_recovery_halts_locks_reloads_and_releases_current_lock(self) -> None:
        self.assert_recovery_uses_current_lock(
            lambda: self.engine.finalize("ignored during recovery"), post_commit=False
        )

    def test_status_post_commit_recovery_uses_and_releases_current_lock(self) -> None:
        self.assert_recovery_uses_current_lock(self.engine.status, post_commit=True)

    def test_finalize_post_commit_recovery_uses_and_releases_current_lock(self) -> None:
        self.assert_recovery_uses_current_lock(
            lambda: self.engine.finalize("ignored during recovery"), post_commit=True
        )

    def test_status_cannot_impersonate_or_release_a_live_finalizer_lock(self) -> None:
        self.enter_committing(consumed=False)
        helper_calls: list[str] = []
        acquire_sessions: list[str | None] = []
        release_sessions: list[str | None] = []

        def live_owner(argv, **kwargs):
            helper = helper_name(argv)
            if helper == "check-halt.sh":
                self.assertEqual(list(argv)[2:], ["commit"])
            helper_calls.append(helper)
            session = kwargs.get("env", {}).get("FORGE_SESSION_PID")
            if helper == "acquire-commit-lock.sh":
                acquire_sessions.append(session)
                return process_result(
                    argv,
                    returncode=1,
                    output=b"forge: commit lock held by live session 4242",
                )
            if helper == "release-commit-lock.sh":
                release_sessions.append(session)
            return process_result(argv)

        with mock.patch.dict(os.environ, {"FORGE_SESSION_PID": "7777"}), mock.patch.object(
            CLI, "run_bounded", side_effect=live_owner
        ), mock.patch.object(CLI.Engine, "_emit_decision", autospec=True):
            with self.assertRaises(CLI.Refusal) as raised:
                self.engine.status()

        refusal = raised.exception
        self.assertIs(refusal.reason_code, CLI.ReasonCode.LOCK_UNAVAILABLE)
        self.assertEqual(
            refusal.message, "commit lock acquisition failed or timed out"
        )
        self.assertEqual(
            refusal.observed, "forge: commit lock held by live session 4242"
        )
        self.assertEqual(
            helper_calls, ["check-halt.sh", "acquire-commit-lock.sh"]
        )
        self.assertEqual(acquire_sessions, ["7777"])
        self.assertEqual(release_sessions, [])
        self.assertEqual(self.store.load(CHAIN_ID)["state"], "committing")

    def test_pre_commit_crash_restores_unexpired_unconsumed_authorization(self) -> None:
        pre_head = self.enter_committing(consumed=False)

        with self.patched_helpers() as helper_calls:
            outcome = self.engine.status()

        self.assertTrue(outcome.ok)
        self.assertEqual(outcome.state, "authorized")
        self.assertEqual(self.repo.head(), pre_head)
        self.assertEqual(
            outcome.message,
            "recovered pre-commit crash window: HEAD unchanged; authorization restored",
        )
        self.assertEqual(
            outcome.next_required_step,
            f"forge commit finalize --message <message> --chain-id {CHAIN_ID}",
        )
        self.assertEqual(
            helper_calls,
            ["check-halt.sh", "acquire-commit-lock.sh", "release-commit-lock.sh"],
        )
        recovered = self.store.load(CHAIN_ID)
        self.assertEqual(recovered["state"], "authorized")
        self.assertFalse(recovered["authorization"]["consumed"])
        self.assertEqual(
            recovered["commit_result"]["recovery"],
            "intent-before-git-commit; HEAD unchanged",
        )

    def test_pre_commit_crash_refuses_consumed_or_expired_fallback_with_facts(self) -> None:
        pre_head = self.enter_committing(consumed=True)
        with self.patched_helpers():
            with self.assertRaises(CLI.Refusal) as consumed_raised:
                self.engine.status()
        consumed = consumed_raised.exception
        self.assertIs(consumed.reason_code, CLI.ReasonCode.TOKEN_CONSUMED)
        self.assertEqual(
            consumed.message,
            "pre-commit crash window cannot fall back: "
            f"HEAD unchanged=True; token consumed=True; "
            f"token expires_at={self.state['authorization']['expires_at']}",
        )
        self.assertIn(f"HEAD unchanged={self.repo.head() == pre_head}", consumed.observed)
        self.assertIn("token consumed=True", consumed.observed)

        self.state = self.store.load(CHAIN_ID)
        self.state["authorization"]["consumed"] = False
        self.state["authorization"]["consumed_at"] = None
        self.state["authorization"].update(
            {
                "issued_at": "1999-12-31T23:30:00Z",
                "expires_at": "2000-01-01T00:00:00Z",
            }
        )
        self.persist("fixture_expired_commit_intent")
        with self.patched_helpers():
            with self.assertRaises(CLI.Refusal) as expired_raised:
                self.engine.status()
        expired = expired_raised.exception
        self.assertIs(expired.reason_code, CLI.ReasonCode.TTL_EXPIRED)
        self.assertIn("HEAD unchanged=True", expired.message)
        self.assertIn("token consumed=False", expired.message)
        self.assertIn("token expires_at=2000-01-01T00:00:00Z", expired.message)

    def test_post_commit_crash_verifies_candidate_and_closes_idempotently(self) -> None:
        pre_head = self.enter_committing(consumed=True)
        self.git("commit", "-q", "-m", "fixture commit")
        committed = self.repo.head()
        self.assertNotEqual(committed, pre_head)

        with self.patched_helpers() as helper_calls:
            outcome = self.engine.finalize("ignored during recovery")

        self.assertTrue(outcome.ok)
        self.assertEqual(outcome.state, "closed")
        self.assertEqual(
            outcome.message,
            f"recovered committed candidate {committed} and closed chain",
        )
        self.assertEqual(
            helper_calls,
            ["check-halt.sh", "acquire-commit-lock.sh", "release-commit-lock.sh"],
        )
        closed = self.store.load(CHAIN_ID)
        self.assertEqual(closed["commit_result"]["commit_sha"], committed)
        self.assertEqual(
            closed["commit_result"]["recovery"],
            "git-commit-before-close; commit identity verified",
        )
        self.assertTrue(closed["authorization"]["consumed"])

        status = self.engine.status()
        self.assertTrue(status.ok)
        self.assertEqual(status.state, "closed")
        self.assertEqual(status.next_required_step, "none — chain closed")

    def test_post_commit_recovery_preserves_trailing_newline_message_bytes(self) -> None:
        message = "subject\n\nbody ending with newline\n"
        pre_head = self.enter_committing(consumed=True, message=message)
        self.git("commit", "-q", "-m", message)
        committed = self.repo.head()
        self.assertNotEqual(committed, pre_head)
        commit_object = self.repo.git(["cat-file", "commit", committed]).stdout
        self.assertEqual(
            commit_object.split(b"\n\n", 1)[1], CLI.commit_message_bytes(message)
        )

        with self.patched_helpers() as helper_calls:
            outcome = self.engine.status()

        self.assertTrue(outcome.ok)
        self.assertEqual(outcome.state, "closed")
        self.assertEqual(
            outcome.message,
            f"recovered committed candidate {committed} and closed chain",
        )
        self.assertEqual(
            helper_calls,
            ["check-halt.sh", "acquire-commit-lock.sh", "release-commit-lock.sh"],
        )
        closed = self.store.load(CHAIN_ID)
        self.assertEqual(closed["state"], "closed")
        self.assertEqual(closed["commit_result"]["commit_sha"], committed)

    def test_post_commit_crash_with_different_message_freezes_as_foreign(self) -> None:
        pre_head = self.enter_committing(consumed=True)
        self.git("commit", "-q", "-m", "different message")
        self.assertNotEqual(self.repo.head(), pre_head)

        with self.patched_helpers():
            with self.assertRaises(CLI.FrozenError) as raised:
                self.engine.status()

        frozen = raised.exception
        self.assertEqual(
            frozen.message,
            "foreign HEAD in committing: HEAD matches neither the pre-finalize state "
            "nor an exact candidate commit",
        )
        self.assertEqual(frozen.chain_id, CHAIN_ID)
        self.assertEqual(frozen.state, "committing")
        self.assertIn("message", frozen.observed)
        self.assertEqual(self.store.load(CHAIN_ID)["state"], "committing")

    def test_foreign_head_in_commit_window_freezes_chain(self) -> None:
        pre_head = self.enter_committing(consumed=True)
        self.git("reset", "-q", "HEAD", "--", "tracked.txt")
        (self.root / "other.txt").write_text("foreign change\n", encoding="utf-8")
        self.git("add", "other.txt")
        self.git("commit", "-q", "-m", "foreign commit")

        with self.patched_helpers():
            with self.assertRaises(CLI.FrozenError) as raised:
                self.engine.status()

        frozen = raised.exception
        self.assertEqual(
            frozen.message,
            "foreign HEAD in committing: HEAD matches neither the pre-finalize state "
            "nor an exact candidate commit",
        )
        self.assertEqual(frozen.chain_id, CHAIN_ID)
        self.assertEqual(frozen.state, "committing")
        self.assertIn(f"pre_head={pre_head}", frozen.observed)
        self.assertIn(f"current={self.repo.head()}", frozen.observed)
        self.assertIn(f"candidate={self.candidate}", frozen.observed)
        self.assertEqual(self.store.load(CHAIN_ID)["state"], "committing")


class CommittingStateTests(FinalizeFixture):
    def test_every_non_recovery_engine_verb_refuses_in_committing(self) -> None:
        self.enter_committing(consumed=False)
        verbs = {
            "abort": (lambda: self.engine.abort("stop"), "commit abort"),
            "classify": (self.engine.classify, "classify"),
            "restage": (
                lambda: self.engine.restage(["tracked.txt"]),
                "commit restage",
            ),
            "rebase": (self.engine.rebase, "commit rebase"),
            "verify": (self.engine.verify, "verify"),
            "gate run": (lambda: self.engine.gate_run("gate-1"), "gate run gate-1"),
            "scan secrets": (self.engine.scan_secrets, "scan secrets"),
            "review request": (self.engine.review_request, "review request"),
            "review collect": (self.engine.review_collect, "review collect"),
            "review attach": (
                lambda: self.engine.review_attach("missing-verdict.txt"),
                "review attach",
            ),
            "review disposition": (
                lambda: self.engine.review_disposition(1, "MINOR", "resolved"),
                "review disposition",
            ),
            "commit approve": (
                lambda: self.engine.approve(self.candidate),
                "commit approve",
            ),
            "commit skip": (
                lambda: self.engine.skip("gate-1", False, "operator"),
                "commit skip",
            ),
        }
        with mock.patch.object(CLI, "_run_halt", autospec=True) as halt:
            for verb, (invoke, observed) in verbs.items():
                with self.subTest(verb=verb):
                    with self.assertRaises(CLI.Refusal) as raised:
                        invoke()
                    refusal = raised.exception
                    self.assertIs(
                        refusal.reason_code, CLI.ReasonCode.STATE_PRECONDITION
                    )
                    self.assertEqual(
                        refusal.message,
                        "chain is in the finalize crash window; non-recovery verb refused",
                    )
                    self.assertEqual(refusal.expected, "status or commit finalize recovery")
                    self.assertEqual(refusal.observed, observed)
                    self.assertEqual(
                        refusal.remediation, f"forge status --chain-id {CHAIN_ID}"
                    )
            self.assertEqual(halt.call_count, len(verbs))
        self.assertEqual(self.store.load(CHAIN_ID)["state"], "committing")


class OutputContractTests(FinalizeFixture):
    def refusal_outcome(self):
        return CLI.Refusal(
            CLI.ReasonCode.TOKEN_CONSUMED,
            "authorization token was already consumed",
            expected="consumed=false",
            observed="consumed=true",
            remediation=f"forge status --chain-id {CHAIN_ID}",
            chain=self.state,
            evidence_refs=(f".forge/chains/{CHAIN_ID}/evidence.txt",),
        ).outcome()

    def test_human_output_is_self_contained_and_ends_with_one_next_step(self) -> None:
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            CLI.render(self.refusal_outcome(), as_json=False)

        self.assertEqual(
            stream.getvalue().splitlines(),
            [
                "authorization token was already consumed",
                "reason code: token-consumed",
                "state: authorized",
                "expected: consumed=false",
                "observed: consumed=true",
                f"remediation: forge status --chain-id {CHAIN_ID}",
                f"next required step: forge status --chain-id {CHAIN_ID}",
            ],
        )
        self.assertEqual(stream.getvalue().count("next required step:"), 1)
        self.assertTrue(
            stream.getvalue().endswith(
                f"next required step: forge status --chain-id {CHAIN_ID}\n"
            )
        )

    def test_json_output_is_one_canonical_exact_envelope(self) -> None:
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            CLI.render(self.refusal_outcome(), as_json=True)

        raw = stream.getvalue()
        self.assertEqual(raw.count("\n"), 1)
        self.assertNotIn("next required step:", raw)
        envelope = json.loads(raw)
        self.assertEqual(set(envelope), CLI.ENVELOPE_KEYS)
        self.assertEqual(envelope["schema"], "forge-cli/1")
        self.assertFalse(envelope["ok"])
        self.assertEqual(envelope["reason_code"], "token-consumed")
        self.assertEqual(envelope["chain_id"], CHAIN_ID)
        self.assertEqual(envelope["state"], "authorized")
        self.assertEqual(
            envelope["next_required_step"], f"forge status --chain-id {CHAIN_ID}"
        )
        self.assertEqual(
            envelope["evidence_refs"],
            [f".forge/chains/{CHAIN_ID}/evidence.txt"],
        )
        self.assertEqual(
            raw,
            json.dumps(envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n",
        )

    def test_main_finalize_refusal_obeys_json_contract_and_exit_class(self) -> None:
        self.state["authorization"]["consumed"] = True
        self.state["authorization"]["consumed_at"] = CLI.iso_z()
        self.persist()
        stream = io.StringIO()
        argv = [
            "--json",
            "--repo",
            str(self.root),
            "--chain-id",
            CHAIN_ID,
            "commit",
            "finalize",
            "--message",
            "must refuse",
        ]

        with self.patched_helpers(), contextlib.redirect_stdout(stream):
            exit_code = CLI.main(argv)

        self.assertEqual(exit_code, 1)
        self.assertEqual(stream.getvalue().count("\n"), 1)
        envelope = json.loads(stream.getvalue())
        self.assertEqual(set(envelope), CLI.ENVELOPE_KEYS)
        self.assertEqual(envelope["reason_code"], "token-consumed")
        self.assertEqual(envelope["state"], "authorized")
        self.assertEqual(envelope["expected"], "consumed=false")
        self.assertEqual(envelope["observed"], "consumed=true")
        self.assertEqual(
            envelope["remediation"], f"forge status --chain-id {CHAIN_ID}"
        )
        self.assertEqual(
            envelope["next_required_step"], f"forge status --chain-id {CHAIN_ID}"
        )


if __name__ == "__main__":
    unittest.main()
