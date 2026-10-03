"""Archive-only changelog-step exemption tests."""

from __future__ import annotations

import contextlib
import io
import json
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tests._cli_loader import load_script, package_module, patch_engine

ROOT = Path(__file__).resolve().parents[1]
CLI = load_script(
    "forge_archive_changelog_step_cli", ROOT / "scripts" / "forge" / "cli.py"
)
CHAIN_CORE = package_module("chain_core")
COMMIT_CHAIN = package_module("chain_core._commit_chain")
POLICY = package_module("policy")
RUNTIME = package_module("runtime")
CLI_FIXTURE_SUPPORT = load_script(
    "forge_archive_changelog_step_fixture", ROOT / "tests" / "test_cli_chain.py"
)
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


def parsed_policy(*, changelog: bool) -> object:
    text = (
        CLI_FIXTURE_SUPPORT.policy_with_changelog()
        if changelog
        else CLI_FIXTURE_SUPPORT.POLICY
    )
    return POLICY.parse_policy("f" * 40, text.encode("utf-8"))


def required_step_state(*, archive: bool) -> dict[str, object]:
    staging: dict[str, object] = {}
    if archive:
        staging["archive"] = {"run_id": "run-archive-step"}
    return {
        "paths": [".forge/history/runs/run-archive-step.md"],
        "staging": staging,
        "tier": {"categories": [], "control": False},
    }


class ArchiveChangelogRequiredStepTests(unittest.TestCase):
    def required_steps(
        self, *, changelog: bool, archive: bool
    ) -> list[str]:
        context = SimpleNamespace(policy=parsed_policy(changelog=changelog))
        return CHAIN_CORE._required_steps(
            context, required_step_state(archive=archive)
        )

    def test_archive_only_chain_omits_configured_changelog(self) -> None:
        steps = self.required_steps(changelog=True, archive=True)

        self.assertNotIn("changelog", steps)
        self.assertEqual(steps[0], "gate-1")

    def test_normal_configured_chain_keeps_changelog_first(self) -> None:
        steps = self.required_steps(changelog=True, archive=False)

        self.assertEqual(steps[0], "changelog")

    def test_archive_like_path_without_metadata_is_not_exempt(self) -> None:
        state = required_step_state(archive=False)
        context = SimpleNamespace(policy=parsed_policy(changelog=True))

        self.assertEqual(
            CHAIN_CORE._required_steps(context, state)[0], "changelog"
        )

    def test_no_changelog_policy_is_unchanged(self) -> None:
        normal = self.required_steps(changelog=False, archive=False)
        archive = self.required_steps(changelog=False, archive=True)

        self.assertEqual(archive, normal)
        self.assertNotIn("changelog", archive)

    def test_disabling_control_restores_changelog_requirement(self) -> None:
        with mock.patch.object(
            COMMIT_CHAIN, "ARCHIVE_CHANGELOG_EXEMPTION", frozenset()
        ):
            steps = self.required_steps(changelog=True, archive=True)

        self.assertEqual(steps[0], "changelog")


class ArchiveChangelogCLIIntegrationTests(
    CLI_FIXTURE_SUPPORT.ForgeCLIFixture
):
    ARCHIVE_BYTES = b"# Archived run\n"

    @contextlib.contextmanager
    def cli_process_context(self):
        environment = self.environment(FORGE_SESSION_PID=str(os.getpid()))
        with mock.patch.dict(
            os.environ, environment, clear=True
        ), mock.patch.object(
            RUNTIME, "SCRIPT_DIR", self.helpers
        ), mock.patch.object(
            RUNTIME, "PLUGIN_ROOT", ROOT
        ), patch_engine(
            "CODEX_EXECUTABLE", str(self.helpers / "fake-codex")
        ), patch_engine(
            "CLAUDE_EXECUTABLE", str(self.helpers / "fake-claude")
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

    def configure_changelog_gate(self) -> None:
        (self.repo / "forge-project.md").write_text(
            CLI_FIXTURE_SUPPORT.policy_with_changelog(), encoding="utf-8"
        )
        (self.repo / "CHANGELOG.md").write_text(
            "# Changes\n", encoding="utf-8"
        )
        (self.repo / ".gitignore").write_text(
            "/.forge/chains/\n", encoding="utf-8"
        )
        self.git(
            "add", "--", "forge-project.md", "CHANGELOG.md", ".gitignore"
        )
        self.git("commit", "--quiet", "-m", "configure changelog gate")

    def start_archive(self, run_id: str) -> str:
        exit_code, started = self.invoke_cli(
            "commit", "start", "--archive-run-id", run_id
        )
        self.assertEqual(exit_code, 0, started)
        self.assertEqual(started["schema"], "forge-cli/2")
        return str(started["chain_id"])

    def test_archive_chain_reaches_finalize_without_changelog_skip(self) -> None:
        self.configure_changelog_gate()
        run_id = "run-archive-changelog-e2e"
        archive_path = f".forge/history/runs/{run_id}.md"

        with patch_engine(
            "_render_archive_bytes", return_value=self.ARCHIVE_BYTES
        ):
            chain_id = self.start_archive(run_id)

            exit_code, status = self.invoke_cli(
                "--chain-id", chain_id, "status"
            )
            self.assertEqual(exit_code, 0, status)
            self.assertEqual(status["state"], "verifying")
            self.assertIn(" verify", str(status["next_required_step"]))

            exit_code, refused = self.invoke_cli(
                "--chain-id", chain_id, "gate", "run", "changelog"
            )
            self.assertEqual(exit_code, 1, refused)
            self.assertEqual(refused["reason_code"], "binding-invalid")
            self.assertEqual(
                refused["message"],
                "forge: archive refused — archive-only index cannot admit a mutating gate",
            )

            exit_code, verified = self.invoke_cli(
                "--chain-id", chain_id, "verify"
            )
            self.assertEqual(exit_code, 0, verified)
            self.assertEqual(verified["state"], "authorized")

            state = self.state(chain_id)
            self.assertEqual(state["paths"], [archive_path])
            self.assertNotIn("changelog", state["steps"])
            self.assertNotIn(
                "changelog", state["steps"].get("user_skips", {})
            )
            self.assertNotIn("changelog", self.gate_lines())
            self.assertEqual(
                (self.repo / "CHANGELOG.md").read_text(encoding="utf-8"),
                "# Changes\n",
            )

            exit_code, finalized = self.invoke_cli(
                "--chain-id",
                chain_id,
                "commit",
                "finalize",
                "--message",
                "Archive completed run",
            )
            self.assertEqual(exit_code, 0, finalized)
            self.assertEqual(finalized["state"], "closed")

    def test_disabled_control_makes_verify_require_changelog(self) -> None:
        self.configure_changelog_gate()
        run_id = "run-archive-changelog-disabled"

        with mock.patch.object(
            COMMIT_CHAIN, "ARCHIVE_CHANGELOG_EXEMPTION", frozenset()
        ), patch_engine(
            "_render_archive_bytes", return_value=self.ARCHIVE_BYTES
        ):
            chain_id = self.start_archive(run_id)
            exit_code, refused = self.invoke_cli(
                "--chain-id", chain_id, "verify"
            )

        self.assertEqual(exit_code, 1, refused)
        self.assertEqual(refused["reason_code"], "binding-invalid")
        self.assertEqual(
            refused["message"],
            "forge: archive refused — archive-only index cannot admit a mutating gate",
        )
        self.assertEqual(refused["observed"], "configured changelog mutation")
        state = self.state(chain_id)
        self.assertEqual(state["state"], "verifying")
        self.assertNotIn("changelog", state["steps"].get("user_skips", {}))


if __name__ == "__main__":
    unittest.main()
