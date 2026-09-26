from __future__ import annotations

import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from tests._revision9_coord_constants import key
from tests._revision9_coord_support import Revision9BuilderBatchSupport

from codex_orchestrator import builders, journal

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = ROOT / "scripts/forge/journal-patterns.py"
route_evidence = journal.route_evidence
route_config = route_evidence.route_config


class RouteSnapshotTests(Revision9BuilderBatchSupport, unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.env.pop("CLAUDE_CODE_SESSION_ID", None)
        self.execution_number = 0

    def _commit(self, paths: dict[str, str], message: str = "routes") -> str:
        for relative, content in paths.items():
            target = self.repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        subprocess.run(
            ["git", "-C", str(self.repo), "add", *paths], check=True
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(self.repo),
                "-c",
                "user.name=Forge Tests",
                "-c",
                "user.email=forge-tests@example.invalid",
                "commit",
                "-q",
                "-m",
                message,
            ],
            check=True,
        )
        self.head = subprocess.run(
            ["git", "-C", str(self.repo), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        return self.head

    def _write_local(self, payload: str) -> Path:
        exclude = self.repo / ".git/info/exclude"
        exclude.write_text("/.forge/local/\n", encoding="utf-8")
        target = self.repo / ".forge/local/routes.toml"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(payload, encoding="utf-8")
        target.chmod(0o600)
        return target

    def _write_transcript(self, session_id: str, payload: str) -> None:
        home = Path(self.temporary.name) / f"home-{session_id}"
        self.env.update({"HOME": str(home), "CLAUDE_CODE_SESSION_ID": session_id})
        transcript = (
            home
            / ".claude/projects"
            / route_evidence._project_slug(self.repo)
            / f"{session_id}.jsonl"
        )
        transcript.parent.mkdir(parents=True)
        transcript.write_text(payload, encoding="utf-8")

    def _assert_open_model_degraded(self, run_id: str) -> None:
        expected = {"observed": None, "reason": "unreadable"}
        try:
            opening = self._open(run_id).records[0]
        except Exception as exc:  # pragma: no cover - exercised by control mutants
            self.fail(f"run-open raised {type(exc).__name__}: {exc}")
        journal_path = self.run_dir(self.repo, run_id) / "journal.jsonl"
        written = json.loads(journal_path.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(expected, opening["orchestrator_model"])
        self.assertEqual(expected, written["orchestrator_model"])

    def _open(self, run_id: str):
        with self.api_environment():
            return builders.run_open(
                self.repo,
                run_id,
                idempotency_key=key(f"{run_id}-open"),
                goal="Exercise route snapshot controls",
                scope=[f"scopes/{run_id}/**"],
                plugin_ref="forge-test-route-snapshot",
            )

    def _open_task(self, run_id: str) -> dict[str, object]:
        opening = self._open(run_id).records[0]
        with self.api_environment():
            builders.task_start(
                self.repo,
                run_id,
                idempotency_key=key(f"{run_id}-task"),
                task="task-01",
                goal="Exercise route snapshot controls",
                acceptance=["The route evidence is exact"],
                files=[f"scopes/{run_id}/example.py"],
            )
        run_dir = self.run_dir(self.repo, run_id)
        for relative in ("prompt.md", "events.jsonl", "handoff.md"):
            (run_dir / relative).write_text("evidence\n", encoding="utf-8")
        return opening

    def _execution(
        self,
        run_id: str,
        route: dict[str, object],
        **updates: object,
    ):
        self.execution_number += 1
        arguments = {
            "idempotency_key": key(f"{run_id}-execution-{self.execution_number}"),
            "agent": f"codex-impl-{self.execution_number:02d}",
            "task": "task-01",
            "provider": route["provider"],
            "role": "implementer",
            "mode": "headless",
            "model": route["model"],
            "effort": route["effort"],
            "worktree": str(self.repo.resolve()),
            "head": self.head,
            "prompt": "prompt.md",
            "handoff": "handoff.md",
            "event_source": "exec",
            "events": "events.jsonl",
            "sandbox": route_config.profile_sandbox(
                str(route["provider"]), "implementer"
            ),
            "route_source": route["route_source"],
            "route_sha256": route["route_sha256"],
        }
        arguments.update(updates)
        with self.api_environment():
            return builders.execution_start(self.repo, run_id, **arguments)

    def test_run_open_snapshots_committed_and_local_routes(self) -> None:
        self._commit(
            {
                ".codex/agents/implementer.toml": (
                    'model = "committed-model"\n'
                    'model_reasoning_effort = "high"\n'
                )
            }
        )
        committed = self._open("run-20260925-route-committed").records[0]
        entry = committed["route"]["implementer"]
        self.assertEqual(
            (entry["model"], entry["effort"], entry["route_source"]),
            ("committed-model", "high", "committed-default"),
        )
        self.assertEqual(set(committed["route"]), set(route_config.ROLES))
        self.assertTrue(
            all(
                set(value) == set(route_evidence.ROUTE_FIELDS)
                for value in committed["route"].values()
            )
        )

        self._write_local(
            'schema = "forge-routes/1"\n[implementer]\nprovider = "claude"\n'
            'model = "local-model"\neffort = "max"\n'
        )
        local = self._open("run-20260925-route-local").records[0]["route"]
        self.assertEqual(local["implementer"]["route_source"], "local")
        self.assertEqual(local["implementer"]["model"], "local-model")

    def test_resolve_snapshot_loads_one_coherent_route_resolution(self) -> None:
        resolution = route_config.load(self.repo, head=self.head)
        expected = {
            role: {
                field: getattr(resolution.for_role(role), field)
                for field in route_evidence.ROUTE_FIELDS
            }
            for role in route_config.ROLES
        }
        with mock.patch.object(
            route_config,
            "load",
            side_effect=(resolution, AssertionError("route configuration reloaded")),
        ) as load:
            actual = route_evidence.resolve_snapshot(self.repo, self.head)

        load.assert_called_once_with(self.repo, head=self.head)
        self.assertEqual(list(actual), list(route_config.ROLES))
        self.assertEqual(actual, expected)

    def test_malformed_local_route_refuses_verbatim(self) -> None:
        self._write_local('schema = "foreign-routes/9"\n')
        with self.assertRaises(journal.CoordinationRefusal) as caught:
            self._open("run-20260925-route-malformed")
        self.assertEqual(
            "forge: routes file refused — malformed line 1", str(caught.exception)
        )

    def test_orchestrator_model_unset_fixture_and_unreadable(self) -> None:
        unset = self._open("run-20260925-route-model-unset").records[0]
        self.assertEqual(
            unset["orchestrator_model"],
            {"observed": None, "reason": "var-unset"},
        )

        home = Path(self.temporary.name) / "home"
        session_id = "session-fixture"
        self.env.update({"HOME": str(home), "CLAUDE_CODE_SESSION_ID": session_id})
        transcript = (
            home
            / ".claude/projects"
            / "-tmp-x-y-wt"
            / f"{session_id}.jsonl"
        )
        dotted_repo = Path("fixture-repo")

        def fixture_model() -> dict[str, object]:
            with mock.patch.object(
                Path, "resolve", return_value=Path("/tmp/x.y/wt")
            ), self.api_environment():
                return route_evidence.orchestrator_model(dotted_repo)

        absent = fixture_model()
        self.assertEqual(
            absent,
            {"observed": None, "reason": "transcript-absent"},
        )
        transcript.parent.mkdir(parents=True)
        transcript.write_text(
            '{"type":"assistant","message":{"model":"sonnet"}}\n'
            '{"type":"user","message":{"model":"ignored"}}\n'
            '{"type":"assistant","message":{"model":"opus"}}\n',
            encoding="utf-8",
        )
        observed = fixture_model()
        self.assertEqual(observed, {"observed": "opus"})

        transcript.unlink()
        transcript.mkdir()
        unreadable = fixture_model()
        self.assertEqual(
            unreadable,
            {"observed": None, "reason": "unreadable"},
        )

    def test_run_open_degrades_non_object_transcript_record(self) -> None:
        self._write_transcript("session-non-object", "[]\n")
        self._assert_open_model_degraded("run-20260925-route-model-non-object")

        with mock.patch.object(
            route_evidence, "_as_transcript_record", side_effect=lambda value: value
        ):
            with self.assertRaises(AssertionError):
                self._assert_open_model_degraded(
                    "run-20260925-route-model-non-object-disabled"
                )

    def test_run_open_degrades_invalid_transcript_model(self) -> None:
        self._write_transcript(
            "session-invalid-model",
            '{"type":"assistant","message":{"model":"opus foo"}}\n',
        )
        self._assert_open_model_degraded("run-20260925-route-model-invalid")

        with mock.patch.object(
            route_evidence, "_valid_transcript_model", return_value=True
        ):
            with self.assertRaises(AssertionError):
                self._assert_open_model_degraded(
                    "run-20260925-route-model-invalid-disabled"
                )

    def test_orchestrator_model_reason_vocabulary_is_closed(self) -> None:
        for reason in ("var-unset", "transcript-absent", "unreadable"):
            with self.subTest(reason=reason):
                route_evidence.validate_run_started(
                    {"orchestrator_model": {"observed": None, "reason": reason}},
                    historical=False,
                    refusal=journal.CoordinationRefusal,
                )

        invalid = {
            "orchestrator_model": {
                "observed": None,
                "reason": "operator-defined",
            }
        }
        expected = (
            "forge: journal append refused — invalid journal record: "
            "run_started.orchestrator_model must be exactly {observed: <model>} "
            "or {observed: null, reason: var-unset | transcript-absent | unreadable}"
        )

        def assertion() -> None:
            with self.assertRaises(journal.CoordinationRefusal) as caught:
                route_evidence.validate_run_started(
                    invalid,
                    historical=False,
                    refusal=journal.CoordinationRefusal,
                )
            self.assertEqual(expected, str(caught.exception))

        assertion()
        with mock.patch.object(
            route_evidence,
            "ORCHESTRATOR_REASONS",
            route_evidence.ORCHESTRATOR_REASONS | {"operator-defined"},
        ):
            with self.assertRaises(AssertionError):
                assertion()

    def test_run_started_schema_control_is_load_bearing(self) -> None:
        opening = copy.deepcopy(
            self._open("run-20260925-route-opening-schema").records[0]
        )
        opening["route"]["implementer"]["route_sha256"] = "0" * 64

        def assertion() -> None:
            with self.assertRaises(journal.CoordinationRefusal):
                journal._validate_proposed_record(
                    opening,
                    run_id=str(opening["run_id"]),
                    repo_root=self.repo.resolve(),
                    scope=tuple(opening["scope"]),
                )

        assertion()
        with mock.patch.object(route_evidence, "validate_run_started", return_value=None):
            with self.assertRaises(AssertionError):
                assertion()

    def test_run_open_snapshot_writer_control_is_load_bearing(self) -> None:
        baseline = self._open("run-20260925-route-writer-control").records[0]
        expected = baseline["route"]["implementer"]["model"]
        mutant = copy.deepcopy(baseline["route"])
        mutant["implementer"]["model"] = "mutant-model"
        mutant["implementer"]["route_sha256"] = route_evidence.route_digest(
            "implementer", mutant["implementer"]
        )
        with mock.patch.object(
            route_evidence, "resolve_snapshot", return_value=mutant
        ):
            with self.assertRaises(AssertionError):
                opening = self._open(
                    "run-20260925-route-writer-control-disabled"
                ).records[0]
                self.assertEqual(
                    opening["route"]["implementer"]["model"], expected
                )

    def test_matching_execution_route_is_accepted(self) -> None:
        run_id = "run-20260925-route-execution-match"
        opening = self._open_task(run_id)
        route = opening["route"]["implementer"]
        execution = self._execution(run_id, route).records[0]
        for field in (*route_evidence.ROUTE_FIELDS, "sandbox"):
            expected = (
                route_config.profile_sandbox(str(route["provider"]), "implementer")
                if field == "sandbox"
                else route[field]
            )
            self.assertEqual(execution[field], expected)

    def test_each_snapshot_divergence_names_its_first_field(self) -> None:
        cases = {
            "provider": "claude",
            "model": "different-model",
            "effort": "low",
            "route_source": "local",
            "route_sha256": "0" * 64,
            "sandbox": "read-only",
        }
        for index, (field, value) in enumerate(cases.items(), 1):
            with self.subTest(field=field):
                run_id = f"run-20260925-route-mismatch-{index}"
                route = self._open_task(run_id)["route"]["implementer"]
                expected = (
                    "forge: execution refused — route diverges from run snapshot "
                    f"for implementer: {field}"
                )
                with self.assertRaises(journal.CoordinationRefusal) as caught:
                    self._execution(run_id, route, **{field: value})
                self.assertEqual(expected, str(caught.exception))

    def test_snapshot_comparison_control_is_load_bearing(self) -> None:
        run_id = "run-20260925-route-mismatch-control"
        route = self._open_task(run_id)["route"]["implementer"]

        def assertion() -> None:
            with self.assertRaises(journal.CoordinationRefusal):
                self._execution(run_id, route, model="different-model")

        assertion()
        with mock.patch.object(route_evidence, "validate_execution", return_value=None):
            with self.assertRaises(AssertionError):
                assertion()

    def test_route_trio_for_role_absent_from_snapshot_fails_closed(self) -> None:
        expected = (
            "forge: execution refused — role monitoring has no frozen route "
            "in the run snapshot"
        )

        def assertion(run_id: str) -> None:
            route = self._open_task(run_id)["route"]["implementer"]
            with self.assertRaises(journal.CoordinationRefusal) as caught:
                self._execution(run_id, route, role="monitoring")
            self.assertEqual(expected, str(caught.exception))

        assertion("run-20260925-route-monitoring")

        def old_snapshot_diagnostic(
            snapshot: dict[str, object],
            role: str,
            refusal: type[Exception],
        ) -> None:
            del snapshot
            route_evidence._refuse_divergence(role, "provider", refusal)

        with mock.patch.object(
            route_evidence, "_snapshot_route", side_effect=old_snapshot_diagnostic
        ):
            with self.assertRaises(AssertionError):
                assertion("run-20260925-route-monitoring-disabled")

    def test_partial_trio_refuses_and_no_trio_projects_unrecorded(self) -> None:
        partial_id = "run-20260925-route-partial"
        route = self._open_task(partial_id)["route"]["implementer"]
        with self.assertRaises(journal.CoordinationRefusal) as caught:
            self._execution(
                partial_id,
                route,
                route_source=None,
                route_sha256=None,
            )
        self.assertEqual(
            "forge: journal append refused — invalid journal record: execution route "
            "fields must be given together (sandbox, route_source, route_sha256)",
            str(caught.exception),
        )

        run_id = "run-20260925-route-unrecorded"
        opening = self._open_task(run_id)
        route = opening["route"]["implementer"]
        outcome = self._execution(
            run_id,
            route,
            sandbox=None,
            route_source=None,
            route_sha256=None,
        )
        self.assertNotIn("route_source", outcome.records[0])
        result = subprocess.run(
            [
                sys.executable,
                str(PATTERNS),
                "--repo",
                str(self.repo),
                str(self.run_dir(self.repo, run_id) / "journal.jsonl"),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["routing"][0]["route_source"], "unrecorded")

    def test_pre_snapshot_run_skips_route_comparison(self) -> None:
        run_id = "run-20260925-route-legacy"
        with self.api_environment():
            self._open_legacy_run(
                self.repo, run_id, scope=[f"scopes/{run_id}/**"]
            )
            builders.task_start(
                self.repo,
                run_id,
                idempotency_key=key(f"{run_id}-task"),
                task="task-01",
                goal="Exercise pre-route compatibility",
                acceptance=["The execution is accepted"],
                files=[f"scopes/{run_id}/example.py"],
            )
        run_dir = self.run_dir(self.repo, run_id)
        for relative in ("prompt.md", "events.jsonl", "handoff.md"):
            (run_dir / relative).write_text("evidence\n", encoding="utf-8")
        route = {
            "provider": "codex",
            "model": "legacy-route-model",
            "effort": "low",
            "route_source": "local",
            "route_sha256": "a" * 64,
        }
        execution = self._execution(
            run_id, route, sandbox="read-only"
        ).records[0]
        self.assertEqual(execution["route_source"], "local")
        self.assertEqual(execution["sandbox"], "read-only")


if __name__ == "__main__":
    unittest.main()
