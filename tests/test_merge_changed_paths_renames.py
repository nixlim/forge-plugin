"""Regression coverage for rename sources in merge changed-path evidence."""

from __future__ import annotations

import subprocess
import textwrap
from collections.abc import Sequence
from typing import Any
from unittest import mock

from tests import test_cli_merge_adapters as ADAPTERS
from tests._cli_loader import package_module

CLI = ADAPTERS.CLI
CORE = ADAPTERS.CORE


class MergeChangedPathsRenameTests(ADAPTERS.MergeAdapterFixture):
    def setUp(self) -> None:
        super().setUp()
        stock_classifier = textwrap.dedent(
            ADAPTERS.RANGE_RISK_TIER_HELPER
        ).lstrip()
        name_only_line = '        "--name-only",'
        self.assertEqual(stock_classifier.count(name_only_line), 1)
        rename_free_classifier = stock_classifier.replace(
            name_only_line,
            '        "--no-renames",\n' + name_only_line,
        )
        (self.helpers / "risk_tier.py").write_text(
            rename_free_classifier, encoding="utf-8"
        )
        self.stock_classifier = stock_classifier

        self.git_at(self.worktree, "mv", "scripts/tool.py", "docs/tool.md")
        self.git_at(
            self.worktree,
            "commit",
            "--quiet",
            "-m",
            "rename control file as documentation",
        )
        self.candidate_head = self.git_at(self.worktree, "rev-parse", "HEAD")

        detected_paths = self.git_at(
            self.worktree,
            "diff",
            "--name-only",
            f"{self.base}...HEAD",
            "--",
        ).splitlines()
        self.assertIn("docs/tool.md", detected_paths)
        self.assertNotIn("scripts/tool.py", detected_paths)

    def test_generation_includes_both_rename_sides_and_control_floor(self) -> None:
        self.assertIs(package_module("runtime").MERGE_LIFECYCLE_ACTIVE, False)
        admission, generation = self.admission_and_generation()

        self.assertIn("docs/tool.md", generation.changed_paths)
        self.assertIn("scripts/tool.py", generation.changed_paths)
        self.assertIs(generation.tier["control"], True)

        (self.helpers / "risk_tier.py").write_text(
            self.stock_classifier, encoding="utf-8"
        )
        original_git = CORE.Repository.git

        def detect_renames(
            repository: Any,
            args: Sequence[str],
            **kwargs: Any,
        ) -> subprocess.CompletedProcess[bytes]:
            selected = list(args)
            if "--name-only" in selected:
                selected = [arg for arg in selected if arg != "--no-renames"]
            return original_git(repository, selected, **kwargs)

        with mock.patch.object(
            CORE.Repository,
            "git",
            autospec=True,
            side_effect=detect_renames,
        ):
            disabled = CLI.MergeEngine(self.context()).bind_candidate(
                admission, self.base
            )

        self.assertIn("docs/tool.md", disabled.changed_paths)
        self.assertNotIn("scripts/tool.py", disabled.changed_paths)
        self.assertIs(disabled.tier["control"], False)

    def test_current_candidate_observation_includes_both_rename_sides(self) -> None:
        admission, generation = self.admission_and_generation()
        _store, state = self.create_chain(admission, generation)
        observation_module = package_module("app._candidate_observation")

        _repository, _policy, changed_paths = (
            observation_module._observe_current_merge_candidate(
                self.context(chain_id=self.chain_id),
                state,
                verb="merge verify",
                observation=None,
            )
        )
        self.assertIn("docs/tool.md", changed_paths)
        self.assertIn("scripts/tool.py", changed_paths)

        original_git = CORE.Repository.git

        def detect_renames(
            repository: Any,
            args: Sequence[str],
            **kwargs: Any,
        ) -> subprocess.CompletedProcess[bytes]:
            selected = list(args)
            if "--name-only" in selected:
                selected = [arg for arg in selected if arg != "--no-renames"]
            return original_git(repository, selected, **kwargs)

        with mock.patch.object(
            CORE.Repository,
            "git",
            autospec=True,
            side_effect=detect_renames,
        ):
            _repository, _policy, disabled_paths = (
                observation_module._observe_current_merge_candidate(
                    self.context(chain_id=self.chain_id),
                    state,
                    verb="merge verify",
                    observation=None,
                )
            )

        self.assertIn("docs/tool.md", disabled_paths)
        self.assertNotIn("scripts/tool.py", disabled_paths)

    def test_observation_names_step_lists_both_rename_sides(self) -> None:
        admission, generation = self.admission_and_generation()
        _store, state = self.create_chain(admission, generation)
        specs = CORE._merge_candidate_observation_step_specs(
            state,
            remote_tip=self.base,
            expected_head=self.candidate_head,
            classify=False,
            declared_tier=None,
        )
        self.assertIsNotNone(specs)
        names_specs = [spec for spec in specs or () if spec[0] == "names"]
        self.assertEqual(len(names_specs), 1)
        _name, cwd, argv = names_specs[0]
        self.assertIn("--no-renames", argv)
        self.assertIn("--no-ext-diff", argv)
        self.assertIn("--no-textconv", argv)

        result = subprocess.run(
            argv,
            cwd=cwd,
            env=self.environment(),
            capture_output=True,
            check=True,
        )
        changed_paths = {
            item.decode("utf-8") for item in result.stdout.split(b"\0") if item
        }
        self.assertIn("docs/tool.md", changed_paths)
        self.assertIn("scripts/tool.py", changed_paths)

        rename_detecting_argv = [
            arg for arg in argv if arg != "--no-renames"
        ]
        disabled = subprocess.run(
            rename_detecting_argv,
            cwd=cwd,
            env=self.environment(),
            capture_output=True,
            check=True,
        )
        disabled_paths = {
            item.decode("utf-8") for item in disabled.stdout.split(b"\0") if item
        }
        self.assertIn("docs/tool.md", disabled_paths)
        self.assertNotIn("scripts/tool.py", disabled_paths)
