"""Kept CLI singleton, abort, tombstone and legacy-reader contracts."""

from __future__ import annotations

import contextlib
import io
import json
import os
import stat
import unittest
from pathlib import Path
from unittest import mock

from tests._cli_loader import load_script, package_module, patch_engine

ROOT = Path(__file__).resolve().parents[1]
CLI = load_script("forge_chain_compatibility_tests", ROOT / "scripts/forge/cli.py")
RUNTIME = package_module("runtime")
CLI_FIXTURE_SUPPORT = load_script(
    "forge_chain_compatibility_fixture", ROOT / "tests/test_cli_chain.py"
)
ENVELOPE_KEYS = CLI_FIXTURE_SUPPORT.ENVELOPE_KEYS


class ChainParsingTests(unittest.TestCase):
    def invoke_before_repository(self, argv: list[str]) -> tuple[int, dict[str, object]]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch.object(CLI.Repository, "discover") as discover,
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            discover.side_effect = AssertionError("repository discovery was reached")
            exit_code = CLI.main(["--json", *argv])
        discover.assert_not_called()
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(stdout.getvalue().count("\n"), 1)
        envelope = json.loads(stdout.getvalue())
        self.assertEqual(set(envelope), ENVELOPE_KEYS)
        return exit_code, envelope

    def assert_revision9_refusal(
        self,
        argv: list[str],
        *,
        reason: str,
        message: str | None = None,
    ) -> dict[str, object]:
        exit_code, envelope = self.invoke_before_repository(argv)
        self.assertEqual(exit_code, 1, envelope)
        self.assertFalse(envelope["ok"])
        self.assertEqual(envelope["schema"], "forge-cli/2")
        self.assertEqual(envelope["reason_code"], reason)
        if message is not None:
            self.assertEqual(envelope["message"], message)
        self.assertIsInstance(envelope["remediation"], str)
        self.assertTrue(str(envelope["remediation"]).strip())
        self.assertIsInstance(envelope["next_required_step"], str)
        self.assertTrue(str(envelope["next_required_step"]).strip())
        return envelope

    def test_singleton_duplicates_refuse_exactly_before_repository_selection(self) -> None:
        values = {
            "--repo": "/definitely/not/a/repository",
            "--run-id": "run-revision9-cli",
            "--chain-id": "c-2026-08-28T120000Z-cafe",
        }
        for option, value in values.items():
            spellings = (
                [option, value, f"{option}={value}"],
                [f"{option}={value}", option, value],
            )
            for repeated in spellings:
                with self.subTest(option=option, repeated=repeated):
                    self.assert_revision9_refusal(
                        [
                            "--repo",
                            "/definitely/not/a/repository",
                            *repeated,
                            "status",
                        ]
                        if option != "--repo"
                        else [*repeated, "status"],
                        reason="option-duplicate",
                        message=f"forge: CLI option refused — duplicate {option}",
                    )

    def test_singleton_empty_values_refuse_exactly_before_repository_selection(self) -> None:
        for option in ("--repo", "--run-id", "--chain-id"):
            for spelling in ([f"{option}="], [option, ""]):
                with self.subTest(option=option, spelling=spelling):
                    prefix = (
                        [] if option == "--repo" else ["--repo", "/definitely/not/a/repository"]
                    )
                    self.assert_revision9_refusal(
                        [*prefix, *spelling, "status"],
                        reason="option-empty",
                        message=f"forge: CLI option refused — empty {option}",
                    )


class ChainProcessFixture(CLI_FIXTURE_SUPPORT.ForgeCLIFixture):
    def start_candidate(self, *, fast=False):
        path = "README.md" if fast else "src/app.py"
        self.change(path, "candidate update\n")
        chain_id = str(self.start(path)["chain_id"])
        if fast:
            self.cli("--chain-id", chain_id, "verify", expected=0)
        return chain_id

    def revision9_environment(self) -> dict[str, str]:
        return self.environment(FORGE_SESSION_PID=str(os.getpid()))

    @contextlib.contextmanager
    def cli_process_context(self):
        with (
            mock.patch.dict(os.environ, self.revision9_environment(), clear=True),
            mock.patch.object(RUNTIME, "SCRIPT_DIR", self.helpers),
            mock.patch.object(RUNTIME, "PLUGIN_ROOT", ROOT),
            patch_engine("CODEX_EXECUTABLE", str(self.helpers / "fake-codex")),
            patch_engine("CLAUDE_EXECUTABLE", str(self.helpers / "fake-claude")),
        ):
            yield

    def invoke_cli(self, *argv: str) -> tuple[int, dict[str, object]]:
        return self.invoke_cli_at(self.repo, *argv)

    def invoke_cli_at(self, repository: Path, *argv: str) -> tuple[int, dict[str, object]]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            self.cli_process_context(),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            exit_code = CLI.main(["--json", "--repo", str(repository), *argv])
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(stdout.getvalue().count("\n"), 1)
        envelope = json.loads(stdout.getvalue())
        self.assertEqual(set(envelope), ENVELOPE_KEYS)
        return exit_code, envelope


class ChainCompatibilityTests(ChainProcessFixture):
    def test_frozen_abort_writes_explicit_tombstone_without_replay(self) -> None:
        chain_id = self.start_candidate()
        state_before = self.state_path(chain_id).read_bytes()
        self.events_path(chain_id).write_bytes(b"{malformed-event}\n")
        events_before = self.events_path(chain_id).read_bytes()

        exit_code, aborted = self.invoke_cli(
            "--chain-id",
            chain_id,
            "commit",
            "abort",
            "--reason",
            "operator quarantined malformed replay",
        )

        self.assertEqual(exit_code, 0, aborted)
        self.assertEqual(aborted["state"], "aborted")
        tombstone_path = self.state_path(chain_id).parent / "tombstones" / f"{chain_id}.json"
        tombstone = json.loads(tombstone_path.read_bytes())
        self.assertEqual(tombstone["schema"], CLI.CHAIN_TOMBSTONE_SCHEMA)
        self.assertEqual(tombstone["event"], CLI.CHAIN_TOMBSTONE_EVENT)
        self.assertEqual(tombstone["artifacts"]["state"]["status"], "captured")
        self.assertEqual(tombstone["artifacts"]["events"]["status"], "captured")
        self.assertEqual(self.state_path(chain_id).read_bytes(), state_before)
        self.assertEqual(self.events_path(chain_id).read_bytes(), events_before)

        exit_code, status = self.invoke_cli("--chain-id", chain_id, "status")
        self.assertEqual(exit_code, 0, status)
        self.assertEqual(status["state"], "aborted")

        self.events_path(chain_id).write_bytes(events_before + b"changed\n")
        code, refused = self.invoke_cli("--chain-id", chain_id, "status")
        self.assertEqual(code, 2, refused)
        self.assertEqual(refused["reason_code"], "frozen-chain")

    def test_abort_refuses_terminal_chains_before_any_mutation(self) -> None:
        """Bead forge-plugin-437 iteration 2: an abort is never retried."""
        # A retried abort must not append an event or change state.
        chain_id = self.start_candidate(fast=True)
        exit_code, aborted = self.invoke_cli(
            "--chain-id", chain_id, "commit", "abort", "--reason", "first"
        )
        self.assertEqual(exit_code, 0, aborted)
        events_before = self.events_path(chain_id).read_bytes()
        state_before = self.state_path(chain_id).read_bytes()
        exit_code, retried = self.invoke_cli(
            "--chain-id", chain_id, "commit", "abort", "--reason", "second"
        )
        self.assertEqual(exit_code, 1, retried)
        self.assertEqual(retried["reason_code"], "state-precondition")
        self.assertEqual(self.events_path(chain_id).read_bytes(), events_before)
        self.assertEqual(self.state_path(chain_id).read_bytes(), state_before)
        exit_code, status = self.invoke_cli("--chain-id", chain_id, "status")
        self.assertEqual(exit_code, 0, status)
        self.assertEqual(status["state"], "aborted")

    def test_abort_refuses_landed_chain_and_keeps_its_landing(self) -> None:
        """Bead forge-plugin-437 iteration 2: a landing is never rewritten."""
        chain_id = self.start_candidate(fast=True)
        exit_code, finalized = self.invoke_cli(
            "--chain-id", chain_id, "commit", "finalize", "--message", "land it"
        )
        self.assertEqual(exit_code, 0, finalized)
        self.assertEqual(finalized["state"], "closed")
        events_before = self.events_path(chain_id).read_bytes()
        landed = self.state(chain_id)
        commit_sha = landed["commit_result"]["commit_sha"]
        exit_code, aborted = self.invoke_cli(
            "--chain-id", chain_id, "commit", "abort", "--reason", "too late"
        )
        self.assertEqual(exit_code, 1, aborted)
        self.assertEqual(aborted["reason_code"], "state-precondition")
        after = self.state(chain_id)
        self.assertEqual(after["state"], "closed")
        self.assertEqual(after["commit_result"]["commit_sha"], commit_sha)
        self.assertEqual(self.events_path(chain_id).read_bytes(), events_before)

    def test_disabled_tombstone_control_cannot_seal_a_chain(self):
        chain_id = "c-2026-08-31T120000Z-abcd"
        with mock.patch.object(
            package_module("engine._verbs_tombstone"), "TOMBSTONE_CONTROLS", frozenset()
        ):
            code, refused = self.invoke_cli(
                "--chain-id", chain_id, "chain", "tombstone", "--reason", "seal"
            )
        self.assertEqual(code, 2, refused)
        self.assertEqual(refused["reason_code"], "frozen-chain")
        self.assertFalse((self.repo / ".forge/chains/tombstones" / f"{chain_id}.json").exists())

    def test_operator_tombstone_admits_absent_chain_and_refuses_healthy_chain(self) -> None:
        absent_id = "c-2026-08-31T120000Z-abcd"
        exit_code, unknown = self.invoke_cli(
            "--chain-id",
            absent_id,
            "commit",
            "abort",
            "--reason",
            "must not guess an unknown chain family",
        )
        self.assertEqual(exit_code, 1, unknown)
        self.assertEqual(unknown["reason_code"], "state-precondition")
        self.assertIn(
            "commit-family identity is not authenticated",
            str(unknown["message"]),
        )
        self.assertFalse((self.repo / ".forge/chains/tombstones" / f"{absent_id}.json").exists())

        exit_code, absent = self.invoke_cli(
            "--chain-id",
            absent_id,
            "chain",
            "tombstone",
            "--reason",
            "artifacts were explicitly quarantined",
        )
        self.assertEqual(exit_code, 0, absent)
        self.assertEqual(absent["state"], "aborted")

        self.change("src/app.py", "VALUE = 2\n")
        exit_code, started = self.invoke_cli("commit", "start", "--paths", "src/app.py")
        self.assertEqual(exit_code, 0, started)
        healthy_id = str(started["chain_id"])
        exit_code, refused = self.invoke_cli(
            "--chain-id",
            healthy_id,
            "chain",
            "tombstone",
            "--reason",
            "must not seal a healthy chain",
        )
        self.assertEqual(exit_code, 1, refused)
        self.assertEqual(refused["reason_code"], "state-precondition")
        self.assertIn("readable chain is not frozen", str(refused["message"]))

    def test_tombstone_publication_recovers_only_authenticated_temp_alias(self) -> None:
        chain_id = "c-2026-08-31T120001Z-abcd"
        exit_code, created = self.invoke_cli(
            "--chain-id",
            chain_id,
            "chain",
            "tombstone",
            "--reason",
            "simulate an interrupted final-link publication",
        )
        self.assertEqual(exit_code, 0, created)
        tombstones = self.repo / ".forge/chains/tombstones"
        final = tombstones / f"{chain_id}.json"
        temporary_alias = tombstones / (f".{chain_id}.{os.getpid()}.0123456789abcdef.tmp")
        os.link(final, temporary_alias)
        self.assertEqual(final.stat().st_nlink, 2)

        exit_code, status = self.invoke_cli("--chain-id", chain_id, "status")
        self.assertEqual(exit_code, 0, status)
        self.assertTrue(temporary_alias.exists())

        exit_code, recovered = self.invoke_cli(
            "--chain-id",
            chain_id,
            "chain",
            "tombstone",
            "--reason",
            "recover the interrupted publication",
        )
        self.assertEqual(exit_code, 0, recovered)
        self.assertFalse(temporary_alias.exists())
        self.assertEqual(final.stat().st_nlink, 1)

        foreign_alias = tombstones / "foreign-hardlink"
        os.link(final, foreign_alias)
        exit_code, refused = self.invoke_cli("--chain-id", chain_id, "status")
        self.assertEqual(exit_code, 2, refused)
        self.assertEqual(refused["reason_code"], "frozen-chain")
        self.assertIn("unsafe hardlink topology", str(refused["message"]))

    def test_tombstone_publication_retries_prelink_and_postunlink_failures(self) -> None:
        repository = CLI.Repository(self.repo)

        prelink_id = "c-2026-08-31T120002Z-abcd"
        prelink_store = CLI.ChainStore(repository.common_root())
        with (
            self.cli_process_context(),
            mock.patch.object(CLI.os, "link", side_effect=OSError("failure before final link")),
            self.assertRaisesRegex(CLI.FrozenError, "chain tombstone publication failed"),
        ):
            prelink_store.create_tombstone(
                prelink_id,
                "pre-link publication failure",
                frozen_proven=True,
            )
        tombstones = self.repo / ".forge/chains/tombstones"
        self.assertFalse((tombstones / f"{prelink_id}.json").exists())
        self.assertEqual(list(tombstones.glob(f".{prelink_id}.*.tmp")), [])
        with self.cli_process_context():
            prelink_record = prelink_store.create_tombstone(
                prelink_id,
                "pre-link publication retry",
                frozen_proven=True,
            )
        self.assertEqual(prelink_record["chain_id"], prelink_id)

        postunlink_id = "c-2026-08-31T120003Z-abcd"
        stages: list[str] = []
        postunlink_store = CLI.ChainStore(repository.common_root(), boundary=stages.append)
        real_fsync = CLI.os.fsync

        def fail_directory_fsync(descriptor: int) -> None:
            if (
                stages
                and stages[-1] == "tombstone-temp-unlinked"
                and stat.S_ISDIR(os.fstat(descriptor).st_mode)
            ):
                raise OSError("failure before tombstone directory fsync")
            real_fsync(descriptor)

        with (
            self.cli_process_context(),
            mock.patch.object(CLI.os, "fsync", side_effect=fail_directory_fsync),
            self.assertRaisesRegex(CLI.FrozenError, "chain tombstone publication failed"),
        ):
            postunlink_store.create_tombstone(
                postunlink_id,
                "post-unlink publication failure",
                frozen_proven=True,
            )
        postunlink_final = tombstones / f"{postunlink_id}.json"
        self.assertTrue(postunlink_final.exists())
        self.assertEqual(postunlink_final.stat().st_nlink, 1)
        self.assertIn("tombstone-temp-unlinked", stages)
        self.assertNotIn("tombstone-directory-fsynced", stages)

        with self.cli_process_context():
            postunlink_record = postunlink_store.create_tombstone(
                postunlink_id,
                "post-unlink publication retry",
                frozen_proven=True,
            )
        self.assertEqual(postunlink_record["chain_id"], postunlink_id)

    def test_replay_refuses_noncanonical_event_without_state_repair(self) -> None:
        chain_id = self.start_candidate()
        event_path = self.events_path(chain_id)
        lines = event_path.read_bytes().splitlines(keepends=True)
        canonical_line = lines[0]
        noncanonical_line = canonical_line[:-1] + b" \n"
        self.assertEqual(json.loads(noncanonical_line), json.loads(canonical_line))
        self.assertNotEqual(noncanonical_line, canonical_line)
        lines[0] = noncanonical_line
        tampered_events = b"".join(lines)
        event_path.write_bytes(tampered_events)

        state_path = self.state_path(chain_id)
        state_path.unlink()
        repository = CLI.Repository(self.repo)
        context = CLI.CommandContext(
            repo=repository,
            store=CLI.ChainStore(repository.common_root()),
            options=CLI.CLIOptions(
                repo=str(self.repo),
                chain_id=chain_id,
                revision9_face=True,
            ),
        )

        with (
            self.cli_process_context(),
            self.assertRaisesRegex(CLI.FrozenError, "chain event 1 is not canonical"),
        ):
            CLI.Engine(context).status()

        self.assertFalse(state_path.exists())
        self.assertEqual(event_path.read_bytes(), tampered_events)


class LegacyChainKeySetTests(unittest.TestCase):
    def test_legacy_keysets_are_not_migrated(self) -> None:
        module = CLI
        legacy = {key: None for key in module.STATE_KEYS - {"run_binding", "journal_outbox"}}
        legacy["chain_id"] = "c-2026-08-21T223925Z-1490"
        legacy["schema"] = "forge-chain/1"
        probe = dict(legacy)
        try:
            module.validate_state(probe, legacy["chain_id"])
        except module.FrozenError as error:
            self.assertNotIn("invalid top-level key set", str(error))
        self.assertNotIn("run_binding", probe)
        self.assertNotIn("journal_outbox", probe)
        broken = dict(legacy)
        broken.pop("steps")
        with self.assertRaises(module.FrozenError) as caught:
            module.validate_state(dict(broken), legacy["chain_id"])
        self.assertIn("invalid top-level key set", str(caught.exception))


class GateEnvironmentScrubTests(unittest.TestCase):
    def test_gate_run_source_retains_the_scrub(self) -> None:
        # Supplementary source pin; the behavioral proof lives in
        # GateEnvironmentScrubBehaviorTests below.
        import inspect

        source = inspect.getsource(CLI.Engine.gate_run)
        self.assertIn('environment.pop("FORGE_SESSION_PID", None)', source)


class GateEnvironmentScrubBehaviorTests(CLI_FIXTURE_SUPPORT.ForgeCLIFixture):
    def test_every_stack_cell_child_env_lacks_the_session_identity(self) -> None:
        # Regression: a live inherited FORGE_SESSION_PID leaked into gate
        # children and collided with hermetic fixture owners; the scrub must
        # cover the first cell AND every remaining cell of a multi-cell
        # stack, which previously inherited the unscrubbed environment.
        policy_path = self.repo / "forge-project.md"
        policy = policy_path.read_text(encoding="utf-8")
        original_region = (
            "<!-- FORGE:REGION stack-validations BEGIN -->\n"
            "```bash\n"
            'python3 "$FORGE_CLI_SCRIPTS_DIR/gate.py" stack:python "$@"\n'
            "```\n"
            "<!-- FORGE:REGION stack-validations END -->"
        )
        probe_region = (
            "<!-- FORGE:REGION stack-validations BEGIN -->\n"
            "```bash\n"
            'printf "cell1:%s\\n" "${FORGE_SESSION_PID:-unset}" >> "$FORGE_TEST_GATE_LOG"\n'
            "```\n"
            "```bash\n"
            'printf "cell2:%s\\n" "${FORGE_SESSION_PID:-unset}" >> "$FORGE_TEST_GATE_LOG"\n'
            "```\n"
            "<!-- FORGE:REGION stack-validations END -->"
        )
        self.assertIn(original_region, policy)
        policy_path.write_text(policy.replace(original_region, probe_region, 1), encoding="utf-8")
        self.git("add", "--all")
        self.git("commit", "--quiet", "-m", "two-cell stack probe policy")

        self.change("src/app.py", "VALUE = 3\n")
        chain_id = str(self.start("src/app.py")["chain_id"])
        self.cli(
            "gate",
            "run",
            "stack:python",
            "--chain-id",
            chain_id,
            expected=0,
            FORGE_SESSION_PID="424242",
        )
        lines = [
            line
            for line in self.gate_log.read_text(encoding="utf-8").splitlines()
            if line.startswith("cell")
        ]
        self.assertEqual(lines, ["cell1:unset", "cell2:unset"])
