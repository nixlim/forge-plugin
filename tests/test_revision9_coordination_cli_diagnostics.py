from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from tests._revision9_coord_constants import key
from tests._revision9_coord_support import Revision9BuilderBatchSupport

import codex_orch_tools as ORCH_TOOLS
from codex_orchestrator import journal


class Revision9CliDiagnosticsTests(Revision9BuilderBatchSupport, unittest.TestCase):

    def test_legacy_open_without_stderr_never_falls_back_to_stdout(self) -> None:
        run_id = "run-20260910-legacy-open-without-stderr"
        record_path = Path(self.temporary.name) / "legacy-open-no-stderr.json"
        record_path.write_text(
            json.dumps(
                {
                    "type": "run_started",
                    "recorded_at": "2026-09-10T12:00:00Z",
                    "run_id": run_id,
                    "goal": "Keep an unavailable advisory stream off stdout",
                    "repo": str(self.repo.resolve()),
                    "repo_head": self.head,
                    "repo_status": [],
                    "plugin_ref": "forge-test-revision-9",
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        captured_stdout = io.StringIO()
        with self.api_environment(), mock.patch.object(
            ORCH_TOOLS.sys, "stderr", None
        ), redirect_stdout(captured_stdout):
            exit_code = ORCH_TOOLS._coordination_main(
                [
                    "run-open",
                    "--repo",
                    str(self.repo),
                    "--run-id",
                    run_id,
                    "--scope",
                    "src/**",
                    "--record-json",
                    str(record_path),
                ]
            )
        target = self.run_dir(self.repo, run_id)
        self.assertEqual(exit_code, 0)
        self.assertEqual(captured_stdout.getvalue(), str(target) + "\n")
        self.assertTrue(target.is_dir())

    def test_legacy_open_broken_stderr_never_changes_durable_success(self) -> None:
        class BrokenDiagnostic:
            def write(self, _value: str) -> int:
                raise OSError("diagnostic stream unavailable")

            def flush(self) -> None:
                raise OSError("diagnostic stream unavailable")

        run_id = "run-20260910-legacy-open-broken-stderr"
        record_path = Path(self.temporary.name) / "legacy-open-broken-stderr.json"
        record_path.write_text(
            json.dumps(
                {
                    "type": "run_started",
                    "recorded_at": "2026-09-10T12:00:00Z",
                    "run_id": run_id,
                    "goal": "Keep a broken advisory stream from changing success",
                    "repo": str(self.repo.resolve()),
                    "repo_head": self.head,
                    "repo_status": [],
                    "plugin_ref": "forge-test-revision-9",
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        captured_stdout = io.StringIO()
        with self.api_environment(), mock.patch.object(
            ORCH_TOOLS.sys, "stderr", BrokenDiagnostic()
        ), redirect_stdout(captured_stdout):
            exit_code = ORCH_TOOLS._coordination_main(
                [
                    "run-open",
                    "--repo",
                    str(self.repo),
                    "--run-id",
                    run_id,
                    "--scope",
                    "src/**",
                    "--record-json",
                    str(record_path),
                ]
            )
        target = self.run_dir(self.repo, run_id)
        self.assertEqual(exit_code, 0)
        self.assertEqual(captured_stdout.getvalue(), str(target) + "\n")
        self.assertTrue(target.is_dir())

    def test_cli_legacy_open_notice_is_stderr_only_and_typed_open_is_quiet(
        self,
    ) -> None:
        refused_run_id = "run-20260910-cli-raw-contract-refused"
        refused_path = Path(self.temporary.name) / "raw-contract-refused.json"
        refused_path.write_text(
            json.dumps(
                {
                    "type": "run_started",
                    "recorded_at": "2026-09-10T11:59:59Z",
                    "run_id": refused_run_id,
                    "goal": "Prove raw activation is refused",
                    "repo": str(self.repo.resolve()),
                    "repo_head": self.head,
                    "repo_status": [],
                    "plugin_ref": "forge-test-revision-9",
                    "writer_contract": journal.WRITER_CONTRACT,
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        refused = self.command(
            "run-open",
            "--repo",
            str(self.repo),
            "--run-id",
            refused_run_id,
            "--scope",
            "src/**",
            "--record-json",
            str(refused_path),
        )
        self.assertEqual(refused.returncode, 1)
        self.assertEqual(refused.stdout, "")
        self.assertEqual(
            refused.stderr,
            "forge: run open refused — writer_contract is builder-injected; use "
            "typed run-open: codex_orch_tools.py run-open --repo <repo> --run-id "
            "<id> --idempotency-key <64-hex> --goal <goal> --plugin-ref "
            "<plugin-ref> --scope <pathspec>\n",
        )
        self.assertFalse(
            self.run_dir(self.repo, refused_run_id).parent.parent.exists()
        )

        legacy_run_id = "run-20260910-cli-legacy-open-notice"
        opening_path = Path(self.temporary.name) / "legacy-open-notice.json"
        opening_path.write_text(
            json.dumps(
                {
                    "type": "run_started",
                    "recorded_at": "2026-09-10T12:00:00Z",
                    "run_id": legacy_run_id,
                    "goal": "Prove legacy opening diagnostics",
                    "repo": str(self.repo.resolve()),
                    "repo_head": self.head,
                    "repo_status": [],
                    "plugin_ref": "forge-test-revision-9",
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        legacy = self.command(
            "run-open",
            "--repo",
            str(self.repo),
            "--run-id",
            legacy_run_id,
            "--scope",
            "src/**",
            "--record-json",
            str(opening_path),
        )
        self.assertEqual(legacy.returncode, 0, legacy.stderr)
        self.assertEqual(
            legacy.stdout,
            str(self.run_dir(self.repo, legacy_run_id)) + "\n",
        )
        self.assertEqual(
            legacy.stderr,
            "forge: notice — run opened in legacy mode (no writer_contract); its "
            "first typed mutation will activate it in place; prefer typed run-open\n",
        )

        typed_run_id = "run-20260910-cli-typed-open-no-notice"
        typed = self.command(
            "run-open",
            "--repo",
            str(self.repo),
            "--run-id",
            typed_run_id,
            "--idempotency-key",
            key("cli-typed-open-no-notice"),
            "--goal",
            "Prove typed opening stays quiet",
            "--scope",
            "docs/**",
            "--plugin-ref",
            "forge-test-revision-9",
        )
        self.assertEqual(typed.returncode, 0, typed.stderr)
        self.assertEqual(typed.stderr, "")
        self.assertEqual(typed.stdout.count("\n"), 1)
        self.assertIsInstance(json.loads(typed.stdout), dict)

    def test_cli_singleton_and_idempotency_key_diagnostics(self) -> None:
        base = [
            "run-open", "--repo", str(self.repo), "--run-id", "run-20260828-cli",
            "--idempotency-key", key("cli"), "--goal", "goal", "--scope", "src/**",
            "--plugin-ref", "forge-test",
        ]
        duplicate = self.command(*(base + ["--goal", "other"]))
        self.assertEqual(duplicate.returncode, 1)
        self.assertEqual(duplicate.stderr.strip(), "forge: CLI option refused — duplicate --goal")

        empty = list(base)
        empty[empty.index("goal")] = ""
        refused_empty = self.command(*empty)
        self.assertEqual(refused_empty.returncode, 1)
        self.assertEqual(refused_empty.stderr.strip(), "forge: CLI option refused — empty --goal")

        invalid = list(base)
        invalid[invalid.index(key("cli"))] = "BAD"
        refused_key = self.command(*invalid)
        self.assertEqual(refused_key.returncode, 1)
        self.assertEqual(refused_key.stderr.strip(), journal.BATCH_KEY_REFUSAL)

        recovery_key = self.command(
            "journal", "batch-recover", "--repo", str(self.repo),
            "--run-id", "run-20260828-cli", "--idempotency-key", key("cli"),
        )
        self.assertEqual(recovery_key.returncode, 1)
        self.assertEqual(recovery_key.stderr.strip(), journal.BATCH_KEY_REFUSAL)
