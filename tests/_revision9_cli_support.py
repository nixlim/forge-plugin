from __future__ import annotations

import contextlib
import io
import json
import os
import warnings
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tests._cli_loader import patch_engine
from tests._revision9_cli_constants import (
    CLI,
    CLI_FIXTURE_SUPPORT,
    ENVELOPE_KEYS,
    ROOT,
    RUNTIME,
    key,
)


class Revision9CliSupport:
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
        ), patch_engine(
            "CODEX_EXECUTABLE", str(self.helpers / "fake-codex")
        ):
            yield

    def invoke_cli(self, *argv: str) -> tuple[int, dict[str, object]]:
        return self.invoke_cli_at(self.repo, *argv)

    def invoke_cli_at(
        self, repository: Path, *argv: str
    ) -> tuple[int, dict[str, object]]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with self.cli_process_context(), contextlib.redirect_stdout(
            stdout
        ), contextlib.redirect_stderr(stderr):
            exit_code = CLI.main(
                ["--json", "--repo", str(repository), *argv]
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
        scope: tuple[str, ...] = ("src/**",),
        files: tuple[str, ...] = ("src/app.py",),
        legacy: bool = False,
    ) -> None:
        _batch, builders, journal = CLI._coordination_modules()
        with self.cli_process_context():
            if legacy:
                journal.open_run(
                    self.repo,
                    run_id,
                    list(scope),
                    {
                        "type": "run_started",
                        "recorded_at": "2026-08-28T12:00:00Z",
                        "run_id": run_id,
                        "goal": "Exercise legacy first-use ingest",
                        "repo": str(self.repo.resolve()),
                        "repo_head": self.git("rev-parse", "HEAD"),
                        "repo_status": self.git(
                            "status", "--short"
                        ).splitlines(),
                        "plugin_ref": "forge-revision9-cli-tests",
                    },
                )
                journal.append_run_record(
                    self.repo,
                    run_id,
                    {
                        "type": "task",
                        "recorded_at": "2026-08-28T12:01:00Z",
                        "run_id": run_id,
                        "id": "task-01",
                        "status": "active",
                        "goal": "Bind one retrospective commit chain",
                        "acceptance": [
                            "The first typed use activates and ingests atomically"
                        ],
                        "files": list(files),
                    },
                )
                # The historical target predates the batch sidecars.  The raw
                # task append above uses today's guarded setup path, so remove
                # only that empty test-created lock to restore the old shape.
                legacy_lock = (
                    self.repo
                    / ".codex-orchestrator"
                    / "runs"
                    / run_id
                    / journal.BATCH_LOCK_NAME
                )
                self.assertTrue(legacy_lock.is_file())
                legacy_lock.unlink()
                return
            builders.run_open(
                self.repo,
                run_id,
                idempotency_key=key(f"{run_id}-open"),
                goal="Exercise the Revision-9 CLI surface",
                scope=list(scope),
                plugin_ref="forge-revision9-cli-tests",
            )
            builders.task_start(
                self.repo,
                run_id,
                idempotency_key=key(f"{run_id}-task"),
                task="task-01",
                goal="Bind one commit chain",
                acceptance=["The exact binding and outbox controls pass"],
                files=list(files),
            )

    def start_bound_chain(self, run_id: str) -> str:
        self.open_run_and_task(run_id)
        self.change("src/app.py", "VALUE = 2\n")
        exit_code, envelope = self.invoke_cli(
            "--run-id",
            run_id,
            "commit",
            "start",
            "--paths",
            "src/app.py",
            "--task",
            "task-01",
        )
        self.assertEqual(exit_code, 0, envelope)
        self.assertTrue(envelope["ok"])
        self.assertEqual(envelope["schema"], "forge-cli/2")
        chain_id = envelope["chain_id"]
        self.assertIsInstance(chain_id, str)
        return str(chain_id)

    def start_bound_fast_chain(self, run_id: str) -> str:
        self.open_run_and_task(
            run_id,
            scope=("docs/**",),
            files=("docs/guide.md",),
        )
        self.change("docs/guide.md", "# Revision-9 fast landing\n")
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
        self.assertEqual(verified["schema"], "forge-cli/2")
        self.assertEqual(verified["state"], "authorized")
        self.assertEqual(self.state(chain_id)["tier"]["effective"], "fast")
        return chain_id

    def configure_changelog_gate(self) -> None:
        (self.repo / "forge-project.md").write_text(
            CLI_FIXTURE_SUPPORT.policy_with_changelog(), encoding="utf-8"
        )
        (self.repo / "CHANGELOG.md").write_text(
            "# Changes\n", encoding="utf-8"
        )
        self.git("add", "--", "forge-project.md", "CHANGELOG.md")
        self.git("commit", "--quiet", "-m", "configure changelog gate")

    def start_bound_multicell_stack_chain(
        self, run_id: str, *, cell_count: int = 2
    ) -> str:
        policy = CLI_FIXTURE_SUPPORT.policy_with_changelog()
        first_cell = (
            "```bash\n"
            'python3 "$FORGE_CLI_SCRIPTS_DIR/gate.py" stack:python "$@"\n'
            "```"
        )
        self.assertGreaterEqual(cell_count, 2)
        cells = [first_cell]
        cells.extend(
            "```bash\n"
            f'python3 "$FORGE_CLI_SCRIPTS_DIR/gate.py" stack:python-cell-{index} "$@"\n'
            "```"
            for index in range(2, cell_count + 1)
        )
        self.assertEqual(policy.count(first_cell), 1)
        (self.repo / "forge-project.md").write_text(
            policy.replace(first_cell, "\n".join(cells), 1),
            encoding="utf-8",
        )
        (self.repo / "CHANGELOG.md").write_text("# Changes\n", encoding="utf-8")
        self.git("add", "--", "forge-project.md", "CHANGELOG.md")
        self.git("commit", "--quiet", "-m", "configure two-cell stack")

        self.open_run_and_task(
            run_id,
            scope=("src/**", "CHANGELOG.md"),
            files=("src/app.py", "CHANGELOG.md"),
        )
        self.change("src/app.py", "VALUE = 2\n")
        exit_code, started = self.invoke_cli(
            "--run-id",
            run_id,
            "commit",
            "start",
            "--paths",
            "src/app.py",
            "--task",
            "task-01",
        )
        self.assertEqual(exit_code, 0, started)
        return str(started["chain_id"])

    def selected_commit_ingest_event_digests(
        self,
        materialized: dict[str, object],
        events: list[dict[str, object]],
    ) -> list[str]:
        """Derive the implementation-owned outcome map from live event facts."""

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
                    and event_state["review"]["verdict"] == review["verdict"]
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
            elif event_name == "commit_identity_checked":
                active = bool(
                    event_state.get("commit_result", {}).get("identity")
                    == materialized.get("commit_result", {}).get("identity")
                    and details.get("result") == "passed"
                )
            elif event_name in {"commit_produced", "commit_close_recovered"}:
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

    @staticmethod
    def normalized_journal_records(
        records: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        return [
            {name: value for name, value in record.items() if name != "_line"}
            for record in records
        ]

    def prepare_unbound_fast_ingest(
        self,
        run_id: str,
        *,
        install_captures: bool,
        mechanical_skip: bool = False,
        legacy_run: bool = False,
        multicell_stack: bool = False,
    ) -> SimpleNamespace:
        """Finalize a native unbound chain and capture its exact live package."""

        source_path = "docs/guide.md"
        source_scope = ("docs/**",)
        source_content = f"# Retrospective source for {run_id}\n"
        if multicell_stack:
            self.assertFalse(mechanical_skip)
            policy = (self.repo / "forge-project.md").read_text(encoding="utf-8")
            first_cell = (
                "```bash\n"
                'python3 "$FORGE_CLI_SCRIPTS_DIR/gate.py" stack:python "$@"\n'
                "```"
            )
            second_cell = (
                "```bash\n"
                'python3 "$FORGE_CLI_SCRIPTS_DIR/gate.py" '
                'stack:python-cell-2 "$@"\n'
                "```"
            )
            self.assertEqual(policy.count(first_cell), 1)
            (self.repo / "forge-project.md").write_text(
                policy.replace(first_cell, f"{first_cell}\n{second_cell}", 1),
                encoding="utf-8",
            )
            self.git("add", "--", "forge-project.md")
            self.git("commit", "--quiet", "-m", "configure retrospective stack")
            source_path = "src/app.py"
            source_scope = ("src/**",)
            source_content = "VALUE = 2\n"
        self.change(
            source_path,
            source_content,
        )
        exit_code, started = self.invoke_cli(
            "commit", "start", "--paths", source_path
        )
        self.assertEqual(exit_code, 0, started)
        self.assertEqual(started["schema"], "forge-cli/1")
        chain_id = str(started["chain_id"])

        construction_bypass = (
            mock.patch.object(RUNTIME, "_fast_mechanical_skips", return_value=[])
            if mechanical_skip
            else contextlib.nullcontext()
        )
        with construction_bypass:
            if mechanical_skip:
                exit_code, skipped = self.invoke_cli(
                    "--chain-id",
                    chain_id,
                    "commit",
                    "skip",
                    "assertion-sensor",
                    "--reason",
                    "construct a terminal hostile retrospective package",
                )
                self.assertEqual(exit_code, 0, skipped)
            exit_code, verified = self.invoke_cli(
                "--chain-id", chain_id, "verify"
            )
            self.assertEqual(exit_code, 0, verified)
            self.assertEqual(
                verified["state"], "reviewing" if multicell_stack else "authorized"
            )
            if multicell_stack:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", ResourceWarning)
                    exit_code, requested = self.invoke_cli(
                        "--chain-id", chain_id, "review", "request"
                    )
                self.assertEqual(exit_code, 0, requested)
                request = self.state(chain_id)["review"]["request"]
                self.wait_for_review_completion(request)
                exit_code, collected = self.invoke_cli(
                    "--chain-id", chain_id, "review", "collect"
                )
                self.assertEqual(exit_code, 0, collected)
                self.assertEqual(collected["state"], "authorized")
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
        self.assertEqual(materialized["kind"], "commit")
        self.assertEqual(materialized["state"], "closed")
        self.assertEqual(
            materialized["tier"]["effective"],
            "standard" if multicell_stack else "fast",
        )
        self.assertIsNone(materialized["run_binding"])
        self.assertIsNone(materialized["journal_outbox"])
        self.assertEqual(
            materialized["commit_result"]["commit_sha"],
            self.git("rev-parse", "HEAD"),
        )
        self.assertEqual(state_raw, CLI.canonical_bytes(materialized) + b"\n")
        self.assertEqual(
            events_raw,
            b"".join(CLI.canonical_bytes(event) + b"\n" for event in events),
        )

        selected_digests = self.selected_commit_ingest_event_digests(
            materialized, events
        )
        selected_events = [
            event for event in events if event["digest"] in selected_digests
        ]
        selected_identities = tuple(
            event["payload"]["details"].get(
                "step_id", event["payload"]["event"]
            )
            for event in selected_events
        )
        if mechanical_skip:
            self.assertEqual(
                CLI._fast_mechanical_skips(materialized),
                ["assertion-sensor"],
            )
            self.assertIn("operator_skip", selected_identities)
            self.assertNotIn("assertion-sensor", selected_identities)
        elif not multicell_stack:
            self.assertEqual(
                selected_identities,
                (
                    "gate-1",
                    "gate-1",
                    "stack:docs",
                    "assertion-sensor",
                    "invariant:1",
                    "secret_scan_recorded",
                    "commit_identity_checked",
                    "commit_produced",
                ),
            )
        else:
            self.assertEqual(selected_identities.count("stack:python"), 2)
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
        external = self.repo / "external"
        external.mkdir()
        source_data = {
            "state_file": state_raw,
            "events_file": events_raw,
            "outcome_map": outcome_raw,
        }
        for field, relative in source_paths.items():
            (self.repo / relative).write_bytes(source_data[field])

        self.open_run_and_task(
            run_id,
            scope=source_scope,
            files=(source_path,),
            legacy=legacy_run,
        )
        with self.cli_process_context():
            (
                canonical_repository,
                run_dir,
                read_data,
                captured,
                digests,
            ) = CLI._read_ingest_sources(
                self.repo,
                run_id,
                state_file=source_paths["state_file"],
                events_file=source_paths["events_file"],
                outcome_map=source_paths["outcome_map"],
            )
            self.assertEqual(read_data, source_data)
            for field, name in (
                ("state_file", "state.json"),
                ("events_file", "events.jsonl"),
                ("outcome_map", "outcome-map.json"),
            ):
                self.assertEqual(
                    captured[field],
                    f"captured/sha256/{digests[field]}/{name}",
                )
                self.assertFalse(captured[field].startswith(".codex-orchestrator/"))
            if install_captures:
                CLI._install_ingest_sources(
                    canonical_repository, run_dir, read_data, digests
                )

        closing_head = self.git("rev-parse", "HEAD")
        verifier_inputs = {
            "task": "task-01",
            **source_paths,
            "state_file_sha256": digests["state_file"],
            "events_file_sha256": digests["events_file"],
            "outcome_map_sha256": digests["outcome_map"],
            "closing_head": closing_head,
            "task_status": "complete",
        }
        idempotency_key = key(f"{run_id}-ingest")
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
            idempotency_key,
        )
        return SimpleNamespace(
            run_id=run_id,
            run_dir=run_dir,
            chain_id=chain_id,
            materialized=materialized,
            events=events,
            selected_digests=selected_digests,
            source_data=source_data,
            captured=captured,
            digests=digests,
            verifier_inputs=verifier_inputs,
            ingest_argv=ingest_argv,
        )

    def _quarantine_and_tombstone(self, chain_id: str) -> Path:
        """Reproduce the gse freeze outcome: artifacts moved out, operator tombstone sealed."""
        quarantine = self.repo / ".forge/tmp/quarantine-test"
        quarantine.mkdir(parents=True, exist_ok=True)
        for name in (f"{chain_id}.json", f"{chain_id}.events.jsonl"):
            (self.repo / ".forge/chains" / name).rename(quarantine / name)
        exit_code, sealed = self.invoke_cli(
            "--chain-id", chain_id, "chain", "tombstone",
            "--reason", "operator direction: chain froze; artifacts quarantined",
        )
        self.assertEqual(exit_code, 0, sealed)
        tombstone = self.repo / ".forge/chains/tombstones" / f"{chain_id}.json"
        self.assertTrue(tombstone.exists())
        return tombstone

    def _journal_records(self, run_dir: Path) -> list[dict[str, object]]:
        return [
            json.loads(line)
            for line in (run_dir / "journal.jsonl").read_text(encoding="utf-8").splitlines()
            if line
        ]

    def assert_commit_identity_drain_crash_replays_once(
        self, boundary: str
    ) -> None:
        run_id = f"run-20260907-identity-{boundary}"
        chain_id = self.start_bound_fast_chain(run_id)
        batch, _builders, journal = CLI._coordination_modules()
        repository = CLI.Repository(self.repo)
        context = CLI.CommandContext(
            repo=repository,
            store=CLI.ChainStore(repository.common_root()),
            options=CLI.CLIOptions(
                repo=str(self.repo),
                chain_id=chain_id,
                revision9_face=True,
                original_argv=(
                    "commit",
                    "finalize",
                    "--message",
                    "Revision-9 identity outbox",
                ),
            ),
        )
        original_drain = batch.drain_chain_batch
        original_append = batch._append_missing_prefix
        crashed = False

        def crash_identity_drain(*args: object, **kwargs: object):
            nonlocal crashed
            records = kwargs.get("records")
            if (
                not crashed
                and isinstance(records, (list, tuple))
                and any(
                    isinstance(record, dict)
                    and record.get("type") == "verification"
                    and record.get("criterion")
                    == "gate-2: produced commit identity"
                    for record in records
                )
                and boundary == "before-drain"
            ):
                crashed = True
                raise RuntimeError(f"injected identity {boundary} crash")
            return original_drain(*args, **kwargs)

        def append_then_crash(*args: object, **kwargs: object):
            nonlocal crashed
            result = original_append(*args, **kwargs)
            name = args[1] if len(args) > 1 else kwargs.get("name")
            expected_name = {
                "after-journal": "journal.jsonl",
                "after-receipt": journal.BATCH_RECEIPTS_NAME,
            }.get(boundary)
            if not crashed and expected_name is not None and name == expected_name:
                crashed = True
                raise RuntimeError(f"injected identity {boundary} crash")
            return result

        with self.cli_process_context(), mock.patch.object(
            batch, "drain_chain_batch", side_effect=crash_identity_drain
        ), mock.patch.object(
            batch, "_append_missing_prefix", side_effect=append_then_crash
        ), self.assertRaisesRegex(RuntimeError, f"identity {boundary} crash"):
            CLI.Engine(context).finalize("Revision-9 identity outbox")

        crashed_state = self.state(chain_id)
        pending = crashed_state["journal_outbox"]
        self.assertIsInstance(pending, dict)
        self.assertEqual(crashed_state["state"], "committing")
        self.assertEqual(
            crashed_state["commit_result"]["identity"]["result"], "passed"
        )
        carrier = self.events(chain_id)[-1]
        self.assertEqual(carrier["payload"]["event"], "commit_identity_checked")
        carried = carrier["payload"]["details"]["journal_batch"]["records"]
        self.assertEqual(len(carried), 1)
        self.assertEqual(carried[0]["type"], "verification")
        self.assertEqual(
            carried[0]["criterion"], "gate-2: produced commit identity"
        )

        with self.cli_process_context():
            recovered = CLI.Engine(context).status()
        self.assertTrue(recovered.ok)
        self.assertEqual(recovered.state, "closed")
        final_state = self.state(chain_id)
        self.assertIsNone(final_state["journal_outbox"])
        event_names = [
            event["payload"]["event"] for event in self.events(chain_id)
        ]
        self.assertEqual(event_names.count("commit_identity_checked"), 1)
        self.assertEqual(event_names.count("authorization_consumed"), 1)
        self.assertEqual(event_names.count("commit_close_recovered"), 1)
        self.assertEqual(event_names.count("chain_closed"), 1)
        records, issues = journal.read_journal(
            self.repo
            / ".codex-orchestrator"
            / "runs"
            / run_id
            / "journal.jsonl"
        )
        self.assertEqual(issues, [])
        identity_records = [
            record
            for record in records
            if record.get("type") == "verification"
            and record.get("criterion") == "gate-2: produced commit identity"
        ]
        self.assertEqual(len(identity_records), 1)
        self.assertEqual(identity_records[0]["result"], "passed")
        self.assertEqual(
            sum(record.get("outcome") == "chain-landing" for record in records),
            1,
        )
