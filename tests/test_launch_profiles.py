"""FR-245 profile-table conformance for review and typed-launch cells."""

from __future__ import annotations

import importlib
import json
import re
import shlex
import unittest
from types import SimpleNamespace

from tests._cli_loader import patch_engine
from tests._launch_support import LAUNCH_LANE, ROOT, LaunchLaneSupport

REVIEW_LAUNCH = importlib.import_module("forge_cli.engine._review_launch")
SPEC = ROOT / "docs/specs/forge-plugin-spec.md"


class LaunchProfileTests(LaunchLaneSupport, unittest.TestCase):
    def test_agent_allocation_requires_exact_task_profile_and_two_digit_name(self) -> None:
        base = {
            "task": self.task_id, "provider": "codex",
            "role": "implementer", "execution": "execution-01",
        }
        records = [
            dict(base, agent="codex-implementer-1"),
            dict(base, agent="codex-implementer-100"),
            dict(base, task="task-other", agent="codex-implementer-09"),
            dict(base, agent="codex-implementer-07"),
        ]
        self.assertEqual(
            LAUNCH_LANE.allocate_agent(records, "codex", "implementer", self.task_id),
            "codex-implementer-07",
        )
        self.assertEqual(
            LAUNCH_LANE.allocate_agent(
                records[:-1], "codex", "implementer", "task-fresh"
            ),
            "codex-implementer-01",
        )

    def test_agent_is_reused_for_same_task_provider_and_role(self) -> None:
        engine = self.ready_engine()
        self.seed_launch(engine=engine)
        first = self.execution_records()[0]
        marker = self.marker(first)
        marker["collected_at"] = "2026-09-28T12:00:00Z"
        marker["collected_status"] = "failed"
        LAUNCH_LANE.write_marker(self.paths(first).leaf("launch.json"), marker)
        completion = self.paths(first).leaf("completion.json")
        completion.write_text("{}", encoding="utf-8")
        completion.chmod(0o600)
        self.seed_launch(engine=engine)
        first, second = self.execution_records()
        self.assertEqual(first["agent"], second["agent"])
        self.assertEqual(
            (first["execution"], second["execution"]),
            ("execution-01", "execution-02"),
        )
        first_marker = self.marker(first)
        hostile = [
            dict(first_marker, task="task-other", agent="codex-implementer-99"),
            dict(first_marker, agent="bad"),
            first_marker,
        ]
        allocated = LAUNCH_LANE.allocate_agent(
            hostile,
            "codex",
            "implementer",
            self.task_id,
        )
        self.assertEqual(allocated, first["agent"])

    def test_spec_table_matches_reviewers_and_non_deferred_launch_cells(self) -> None:
        text = SPEC.read_text(encoding="utf-8")
        header = "| role | `codex` profile | `claude` profile |"
        lines = text[text.index(header) :].splitlines()
        rows: dict[str, tuple[str, str]] = {}
        for line in lines[2:]:
            line = line.strip()
            if not line.startswith("|"):
                break
            columns = [column.strip() for column in line.strip().strip("|").split("|")]
            rows[columns[0].strip("`")] = (columns[1], columns[2])
        self.assertEqual(
            set(rows), {"implementer", "review-cheap", "review-final", "plan"}
        )
        staging = self.scratch / "capture.staging"
        final_body = self.scratch / "review-final-body.md"
        paths = SimpleNamespace(
            staging_path=staging,
            worktree=self.linked_worktree,
            plugin_root=ROOT,
            role_body_path=final_body,
        )
        replacements = {
            "<m>": "model-fixture",
            "<e>": "opaque-effort",
            "<worktree>": str(self.linked_worktree),
            "<handoff>": str(staging),
            "<verdict>": str(staging),
            "<plugin>": str(ROOT),
            "<derived-review-final-body>": str(final_body),
        }
        for role in ("review-cheap", "review-final"):
            for index, provider in enumerate(("codex", "claude")):
                with self.subTest(provider=provider, role=role):
                    command = re.search(r"`([^`]*)`", rows[role][index])
                    self.assertIsNotNone(command)
                    rendered = command.group(1)
                    for old, new in replacements.items():
                        rendered = rendered.replace(old, new)
                    expected = shlex.split(rendered)
                    expected[0] = str(self.bin_dir / provider)
                    actual = REVIEW_LAUNCH.reviewer_argv(
                        provider, role, "model-fixture", "opaque-effort", paths
                    )
                    self.assertEqual(actual, expected)
        for role in ("implementer", "plan"):
            command = re.search(r"`([^`]*)`", rows[role][0])
            self.assertIsNotNone(command)
            rendered = command.group(1)
            for old, new in replacements.items():
                rendered = rendered.replace(old, new)
            expected = shlex.split(rendered)
            expected[0] = str(self.bin_dir / "codex")
            self.assertEqual(
                list(
                    LAUNCH_LANE.launch_argv(
                        "codex", role, "model-fixture", "opaque-effort",
                        worktree=self.linked_worktree, plugin_root=ROOT, staging=staging,
                    )
                ),
                expected,
            )

    def test_spec_table_matches_active_claude_launch_cells(self) -> None:
        text = SPEC.read_text(encoding="utf-8")
        header = "| role | `codex` profile | `claude` profile |"
        lines = text[text.index(header) :].splitlines()
        cells: dict[str, str] = {}
        for line in lines[2:]:
            line = line.strip()
            if not line.startswith("|"):
                break
            columns = [column.strip() for column in line.strip().strip("|").split("|")]
            role = columns[0].strip("`")
            if role in {"implementer", "plan"}:
                command = re.search(r"`([^`]*)`", columns[2])
                self.assertIsNotNone(command)
                cells[role] = command.group(1)
        for role in ("implementer", "plan"):
            rendered = (
                cells[role]
                .replace("<m>", "model-fixture")
                .replace("<e>", "opaque-effort")
                .replace("<plugin>", str(ROOT))
            )
            expected = shlex.split(rendered)
            expected[0] = str(self.bin_dir / "claude")
            actual = list(
                LAUNCH_LANE.launch_argv(
                    "claude", role, "model-fixture", "opaque-effort",
                    worktree=self.linked_worktree, plugin_root=ROOT,
                    staging=self.scratch / "handoff.staging",
                )
            )
            self.assertEqual(actual, expected)

    def test_ruled_claude_launch_controls_are_load_bearing(self) -> None:
        staging = self.scratch / "handoff.staging"
        implementer = LAUNCH_LANE.launch_argv(
            "claude", "implementer", "model", "opaque",
            worktree=self.linked_worktree, plugin_root=ROOT, staging=staging,
        )
        plan = LAUNCH_LANE.launch_argv(
            "claude", "plan", "model", "opaque",
            worktree=self.linked_worktree, plugin_root=ROOT, staging=staging,
        )
        implementer_mutants = []
        for control in ("--no-session-persistence", "--permission-mode", "--allowedTools"):
            mutant = list(implementer)
            position = mutant.index(control)
            del mutant[position : position + (1 if control.startswith("--no-session") else 2)]
            implementer_mutants.append(tuple(mutant))
        plan_mutants = []
        for replacement in ("Read,Grep,Glob,LS", "Read,Grep,Glob,Bash"):
            mutant = list(plan)
            mutant[mutant.index("Read,Grep,Glob")] = replacement
            plan_mutants.append(tuple(mutant))
        plan_mutants.append(tuple(item for item in plan if item != "--no-session-persistence"))
        bypass = list(plan)
        bypass.insert(-1, "--dangerously-skip-permissions")
        plan_mutants.append(tuple(bypass))
        for mutant in implementer_mutants:
            with self.assertRaises(AssertionError):
                self.assertEqual(mutant, implementer)
        for mutant in plan_mutants:
            with self.assertRaises(AssertionError):
                self.assertEqual(mutant, plan)

    def test_launch_timeouts_follow_the_shared_profile_table(self) -> None:
        for role in ("implementer", "plan"):
            self.configure_route(role, "codex")
            run_id = f"run-20260928-timeout-{role}"
            engine = self.ready_engine(run_id)
            calls: list[tuple[tuple[str, ...], dict[str, object]]] = []

            def capture(
                launcher_argv: tuple[str, ...],
                *,
                _calls: list[tuple[tuple[str, ...], dict[str, object]]] = calls,
                **kwargs: object,
            ) -> SimpleNamespace:
                _calls.append((tuple(launcher_argv), dict(kwargs)))
                return SimpleNamespace(pid=430_001)

            with patch_engine("spawn_wrapper", side_effect=capture):
                self.launch_direct(role=role, engine=engine)
            config = json.loads(calls[0][0][-1])
            self.assertEqual(
                config["timeout"], REVIEW_LAUNCH.PROFILE_TIMEOUT_SECONDS[role]
            )
        self.assertEqual(REVIEW_LAUNCH.PROFILE_TIMEOUT_SECONDS["plan"], 1200)


if __name__ == "__main__":
    unittest.main()
