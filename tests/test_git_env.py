from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Mapping
from pathlib import Path
from unittest import mock

from tests import _git_env
from tests._git_env import (
    QUIET_GIT_SETTINGS,
    init_quiet_repository,
    quiet_repository,
    with_quiet_git,
)

ROOT = Path(__file__).resolve().parents[1]
THIS_MODULE = "tests/test_git_env.py"
GIT_ENV_HELPER = "tests/_git_env.py"
PENDING_ADOPTION = frozenset(
    {
        "tests/test_archive_replay_vocabulary.py",
        "tests/test_archive_run.py",
        "tests/test_audit_commitments.py",
        "tests/test_candidate_identity.py",
        "tests/test_cli_chain_finalize.py",
        "tests/test_cli_common_lock.py",
        "tests/test_cli_hook_integration.py",
        "tests/test_cli_merge_integration.py",
        "tests/test_cli_phase0_contracts.py",
        "tests/test_d13_concurrency.py",
        "tests/test_d14_learn_concurrency.py",
        "tests/test_drift_check.py",
        "tests/test_e2e_smoke.py",
        "tests/test_evals.py",
        "tests/test_fr223_v2_hook.py",
        "tests/test_gate_one_once.py",
        "tests/test_governance_scripts.py",
        # Landed after this candidate's repository-creation adoption sweep.
        "tests/test_ingest_changed_paths_renames.py",
        "tests/test_installer.py",
        "tests/test_invariant_guard.py",
        "tests/test_journal_patterns.py",
        "tests/test_launch_init_step.py",
        "tests/test_learn_proposals.py",
        "tests/test_migration.py",
        "tests/test_mutation_runner.py",
        "tests/test_revision9_archive.py",
        "tests/test_revision9_coordination.py",
        "tests/test_revision9_matrix.py",
        "tests/test_risk_tier.py",
        "tests/test_route_config_ownership.py",
        "tests/test_run_coordination.py",
        "tests/test_tree_index_drift_flags.py",
        "tests/test_vocab_readers.py",
        "tests/test_vocab_writers.py",
        "tests/test_worktree_merge_skill.py",
    }
)
SHELL_CREATION = re.compile(r"(?<![\w-])git\s+(?:init|clone)\b")


def _literal_text(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(
            value.value
            for value in node.values
            if isinstance(value, ast.Constant) and isinstance(value.value, str)
        )
    return None


def _call_label(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_label(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _sequence_creates_repository(nodes: list[ast.AST]) -> bool:
    values = [_literal_text(node) for node in nodes]
    return any(
        value == "git"
        and any(action in {"init", "clone"} for action in values[index + 1 :])
        for index, value in enumerate(values)
    )


def _node_creates_repository(node: ast.AST) -> bool:
    if isinstance(node, ast.Call):
        if _sequence_creates_repository(node.args):
            return True
        if _call_label(node.func) in {"git", "self.git", "git_at", "self.git_at"}:
            return any(
                _literal_text(argument) in {"init", "clone"}
                for argument in node.args
            )
    if isinstance(node, (ast.List, ast.Tuple)):
        return _sequence_creates_repository(node.elts)
    text = _literal_text(node)
    return text is not None and SHELL_CREATION.search(text) is not None


def _dynamic_git_argv(node: ast.AST) -> bool:
    return (
        isinstance(node, (ast.List, ast.Tuple))
        and bool(node.elts)
        and _literal_text(node.elts[0]) == "git"
        and any(isinstance(element, ast.Starred) for element in node.elts)
    )


def _action_sequence(node: ast.AST) -> bool:
    return (
        isinstance(node, (ast.List, ast.Tuple))
        and bool(node.elts)
        and _literal_text(node.elts[0]) in {"init", "clone"}
    )


def _creates_git_repository(source: str) -> bool:
    nodes = tuple(ast.walk(ast.parse(source)))
    if any(_node_creates_repository(node) for node in nodes):
        return True
    return any(_dynamic_git_argv(node) for node in nodes) and any(
        _action_sequence(node) for node in nodes
    )


def _imports_git_env(source: str) -> bool:
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            if any(alias.name == "tests._git_env" for alias in node.names):
                return True
        if isinstance(node, ast.ImportFrom) and node.module == "tests._git_env":
            return True
        if isinstance(node, ast.ImportFrom) and node.module == "tests":
            if any(alias.name == "_git_env" for alias in node.names):
                return True
    return False


def _adoption_issues(
    sources: Mapping[str, str], pending: frozenset[str] = PENDING_ADOPTION
) -> list[str]:
    issues = [
        f"{label}: listed file no longer creates repositories"
        for label in sorted(pending - sources.keys())
    ]
    for label, source in sorted(sources.items()):
        if label == THIS_MODULE:
            continue
        creates = _creates_git_repository(source)
        imports_helper = _imports_git_env(source)
        if label in pending and imports_helper:
            issues.append(f"{label}: listed file already imports tests._git_env")
        elif label in pending and not creates:
            issues.append(f"{label}: listed file no longer creates repositories")
        elif (
            label not in pending
            and creates
            and not imports_helper
            and label != GIT_ENV_HELPER
        ):
            issues.append(f"{label}: unlisted repository creator")
    return issues


def _test_sources() -> dict[str, str]:
    return {
        path.relative_to(ROOT).as_posix(): path.read_text(encoding="utf-8")
        for path in (ROOT / "tests").glob("*.py")
    }


class GitEnvironmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="forge-git-env-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def trace_environment(self) -> dict[str, str]:
        environment = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("GIT_CONFIG_")
        }
        environment.update(
            {
                "GIT_TRACE": "1",
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_AUTHOR_NAME": "Forge Tests",
                "GIT_AUTHOR_EMAIL": "forge-tests@example.invalid",
                "GIT_COMMITTER_NAME": "Forge Tests",
                "GIT_COMMITTER_EMAIL": "forge-tests@example.invalid",
                "GIT_TERMINAL_PROMPT": "0",
                "LC_ALL": "C",
            }
        )
        return environment

    def git(
        self, repository: Path, *arguments: str, environment: Mapping[str, str]
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(repository), *arguments],
            env=environment,
            capture_output=True,
            text=True,
            check=True,
        )

    def repo_local_scenario(self, name: str) -> tuple[str, Path, Path]:
        scenario = self.root / name
        scenario.mkdir()
        local = scenario / "local"
        remote = scenario / "origin.git"
        environment = self.trace_environment()
        local_init = init_quiet_repository(local, "--quiet", environment=environment)
        remote_init = init_quiet_repository(
            remote, "--bare", "--quiet", environment=environment
        )
        self.assertEqual((local_init.returncode, remote_init.returncode), (0, 0))
        self.assertIsInstance(local_init.stdout, str)
        traces = []
        traces.append(
            self.git(
                local,
                "commit",
                "--allow-empty",
                "--quiet",
                "-m",
                "initial",
                environment=environment,
            ).stderr
        )
        self.git(local, "remote", "add", "origin", str(remote), environment=environment)
        traces.append(
            self.git(
                local,
                "push",
                "--quiet",
                "--set-upstream",
                "origin",
                "HEAD",
                environment=environment,
            ).stderr
        )
        traces.append(self.git(local, "fetch", "origin", environment=environment).stderr)
        return "\n".join(traces), local, remote

    def assert_settings_readable(self, repository: Path) -> None:
        environment = self.trace_environment()
        for key, value in QUIET_GIT_SETTINGS:
            with self.subTest(repository=repository.name, key=key):
                result = self.git(
                    repository, "config", "--get", key, environment=environment
                )
                self.assertEqual(result.stdout.strip(), value)

    def plain_fetch_trace(self, name: str, *, quiet_environment: bool) -> str:
        scenario = self.root / name
        scenario.mkdir()
        local = scenario / "local"
        remote = scenario / "origin.git"
        environment = self.trace_environment()
        subprocess.run(
            ["git", "init", "--quiet", str(local)],
            env=environment,
            check=True,
            capture_output=True,
        )
        init_quiet_repository(remote, "--bare", "--quiet", environment=environment)
        setup_environment = with_quiet_git(environment)
        self.git(
            local,
            "commit",
            "--allow-empty",
            "--quiet",
            "-m",
            "seed",
            environment=setup_environment,
        )
        self.git(local, "remote", "add", "origin", str(remote), environment=setup_environment)
        self.git(local, "push", "--quiet", "origin", "HEAD", environment=setup_environment)
        selected = with_quiet_git(environment) if quiet_environment else environment
        return self.git(local, "fetch", str(remote), environment=selected).stderr

    def linked_worktree_fixture(self, name: str) -> tuple[Path, Path]:
        main = self.root / f"{name}-main"
        linked = self.root / f"{name}-linked"
        environment = with_quiet_git(self.trace_environment())
        subprocess.run(
            ["git", "init", "--quiet", str(main)],
            env=environment,
            check=True,
            capture_output=True,
        )
        self.git(
            main,
            "commit",
            "--allow-empty",
            "--quiet",
            "-m",
            "linked worktree base",
            environment=environment,
        )
        self.git(
            main,
            "worktree",
            "add",
            "--quiet",
            "-b",
            f"{name}-branch",
            str(linked),
            environment=environment,
        )
        return main, linked

    def assert_preserving_merge(self) -> None:
        original = {
            "SENTINEL": "kept",
            "GIT_CONFIG_COUNT": "2",
            "GIT_CONFIG_KEY_0": "user.name",
            "GIT_CONFIG_VALUE_0": "Existing User",
            "GIT_CONFIG_KEY_1": "user.email",
            "GIT_CONFIG_VALUE_1": "existing@example.invalid",
        }
        untouched = dict(original)
        merged = _git_env.with_quiet_git(original)
        self.assertEqual(original, untouched)
        self.assertIsNot(merged, original)
        self.assertEqual(merged["SENTINEL"], "kept")
        self.assertEqual(merged["GIT_CONFIG_COUNT"], "7")
        for index in range(2):
            self.assertEqual(merged[f"GIT_CONFIG_KEY_{index}"], original[f"GIT_CONFIG_KEY_{index}"])
            self.assertEqual(
                merged[f"GIT_CONFIG_VALUE_{index}"],
                original[f"GIT_CONFIG_VALUE_{index}"],
            )
        for offset, (key, value) in enumerate(QUIET_GIT_SETTINGS, start=2):
            self.assertEqual(merged[f"GIT_CONFIG_KEY_{offset}"], key)
            self.assertEqual(merged[f"GIT_CONFIG_VALUE_{offset}"], value)

    def test_repo_local_settings_survive_environment_scrubbing(self) -> None:
        trace, local, remote = self.repo_local_scenario("quiet")
        self.assertNotIn("maintenance run", trace)
        self.assert_settings_readable(local)
        self.assert_settings_readable(remote)

        with mock.patch.object(_git_env, "QUIET_GIT_SETTINGS", ()):
            disabled_trace, _disabled_local, _disabled_remote = self.repo_local_scenario(
                "disabled"
            )
        maintenance = [
            line
            for line in disabled_trace.splitlines()
            if "maintenance run --auto" in line
        ]
        self.assertTrue(any(not line.startswith("remote:") for line in maintenance))
        self.assertTrue(any(line.startswith("remote:") for line in maintenance))

    def test_environment_layer_suppresses_fetch_maintenance(self) -> None:
        quiet_trace = self.plain_fetch_trace("environment-quiet", quiet_environment=True)
        disabled_trace = self.plain_fetch_trace(
            "environment-disabled", quiet_environment=False
        )
        self.assertNotIn("maintenance run", quiet_trace)
        self.assertIn("maintenance run --auto", disabled_trace)

    def test_environment_merge_preserves_entries_and_detects_overwrite(self) -> None:
        self.assert_preserving_merge()

        def overwrite(environment: Mapping[str, str]) -> dict[str, str]:
            merged = dict(environment)
            for index, (key, value) in enumerate(QUIET_GIT_SETTINGS):
                merged[f"GIT_CONFIG_KEY_{index}"] = key
                merged[f"GIT_CONFIG_VALUE_{index}"] = value
            merged["GIT_CONFIG_COUNT"] = str(len(QUIET_GIT_SETTINGS))
            return merged

        with mock.patch.object(_git_env, "with_quiet_git", side_effect=overwrite):
            with self.assertRaises(AssertionError):
                self.assert_preserving_merge()

    def test_environment_merge_rejects_malformed_counts(self) -> None:
        malformed = (
            {"GIT_CONFIG_COUNT": "x"},
            {"GIT_CONFIG_COUNT": "-1"},
            {
                "GIT_CONFIG_COUNT": "2",
                "GIT_CONFIG_KEY_0": "user.name",
                "GIT_CONFIG_VALUE_0": "Forge",
                "GIT_CONFIG_VALUE_1": "missing key",
            },
        )
        for environment in malformed:
            with self.subTest(environment=environment):
                with self.assertRaises(ValueError):
                    with_quiet_git(environment)

    def test_environment_merge_is_idempotent(self) -> None:
        original = {"SENTINEL": "unchanged"}
        once = with_quiet_git(original)
        twice = with_quiet_git(once)
        self.assertEqual(once, twice)
        self.assertIsNot(once, twice)
        self.assertEqual(original, {"SENTINEL": "unchanged"})

    def test_init_runs_once_and_missing_config_fails_closed(self) -> None:
        completed = subprocess.CompletedProcess(
            ["git", "init"], returncode=1, stdout="failed stdout", stderr="failed stderr"
        )
        target = self.root / "absent"
        with mock.patch.object(_git_env.subprocess, "run", return_value=completed) as run:
            with self.assertRaises(FileNotFoundError):
                init_quiet_repository(
                    target,
                    "--quiet",
                    cwd=self.root,
                    environment={"PATH": os.environ.get("PATH", os.defpath)},
                )
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0], ["git", "init", "--quiet", str(target)])
        self.assertTrue(run.call_args.kwargs["text"])
        self.assertTrue(run.call_args.kwargs["capture_output"])

    def test_quiet_repository_detects_regular_and_bare_layouts(self) -> None:
        environment = self.trace_environment()
        regular = self.root / "regular"
        bare = self.root / "bare.git"
        subprocess.run(
            ["git", "init", "--quiet", str(regular)],
            env=environment,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "init", "--bare", "--quiet", str(bare)],
            env=environment,
            check=True,
            capture_output=True,
        )
        quiet_repository(regular)
        quiet_repository(bare)
        self.assert_settings_readable(regular)
        self.assert_settings_readable(bare)
        with self.assertRaises(FileNotFoundError):
            quiet_repository(self.root / "not-a-repository")
        false_bare = self.root / "false-bare"
        false_bare.mkdir()
        (false_bare / "config").write_text("[core]\n\tbare = true\n", encoding="utf-8")
        with self.assertRaises(FileNotFoundError):
            quiet_repository(false_bare)

    def test_quiet_repository_persists_linked_worktree_shared_config(self) -> None:
        main, linked = self.linked_worktree_fixture("shared")
        common_config = main / ".git" / "config"
        self.assertNotIn("maintenance", common_config.read_text(encoding="utf-8"))

        quiet_repository(linked)

        self.assertEqual(_git_env._repository_config(linked), common_config)
        self.assert_settings_readable(main)
        self.assert_settings_readable(linked)

        _disabled_main, disabled_linked = self.linked_worktree_fixture("disabled")
        with mock.patch.object(_git_env, "_linked_worktree_config", return_value=None):
            with self.assertRaises(FileNotFoundError):
                quiet_repository(disabled_linked)

    def test_repository_creation_adoption_is_an_exact_ratchet(self) -> None:
        self.assertEqual(len(PENDING_ADOPTION), 35)
        self.assertEqual(_adoption_issues(_test_sources()), [])

    def test_repo_conformance_imports_in_commitment_audit_script_mode(self) -> None:
        run_dir = self.root / "conformance-run"
        run_dir.mkdir()
        (run_dir / "journal.jsonl").write_text("", encoding="utf-8")
        environment = {
            key: value for key, value in os.environ.items() if key != "PYTHONPATH"
        }

        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tests/test_repo_conformance.py"),
                "--run-dir",
                str(run_dir),
            ],
            cwd=ROOT,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(
            result.stdout,
            "## Historical Routing Findings\n\nNone recorded\n",
        )

    def test_adoption_scanner_flags_an_unlisted_creator_when_disabled(self) -> None:
        synthetic = {
            "tests/test_unlisted_creator.py": (
                'subprocess.run(["git", "init", "--quiet", str(repo)])\n'
            )
        }
        self.assertEqual(
            _adoption_issues(synthetic, frozenset()),
            ["tests/test_unlisted_creator.py: unlisted repository creator"],
        )

    def test_adoption_scanner_excludes_known_init_false_positives(self) -> None:
        source = (
            'record = {"subtype": "init"}\n'
            'invoke("init", "--project", "fixture")\n'
        )
        self.assertFalse(_creates_git_repository(source))


if __name__ == "__main__":
    unittest.main()
