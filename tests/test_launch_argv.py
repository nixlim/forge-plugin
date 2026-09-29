"""Exact argv and committed-prompt tests for typed launches."""

from __future__ import annotations

import os
import shutil
import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace

from tests._cli_loader import patch_engine
from tests._launch_support import (
    ENGINE,
    LAUNCH_LANE,
    ROOT,
    STRIPPED_PATH,
    LaunchLaneSupport,
    digest,
)


class LaunchArgvTests(LaunchLaneSupport, unittest.TestCase):
    def test_exact_provider_argv_for_all_four_launch_cells(self) -> None:
        staging = self.scratch / "handoff.staging"
        codex = str(self.bin_dir / "codex")
        claude = str(self.bin_dir / "claude")
        common_codex = (
            codex,
            "exec",
            "--json",
            "--output-last-message",
            str(staging),
        )
        cases = {
            ("codex", "implementer"): common_codex
            + (
                "-s", "workspace-write", "-c", "approval_policy=never", "-c",
                "model=gpt-fixture", "-c", "model_reasoning_effort=opaque",
                "-C", str(self.linked_worktree), "-",
            ),
            ("codex", "plan"): common_codex
            + (
                "-s", "read-only", "-c", "approval_policy=never", "-c",
                "model=gpt-fixture", "-c", "model_reasoning_effort=opaque",
                "-C", str(self.linked_worktree), "-",
            ),
            ("claude", "implementer"): (
                claude, "-p", "--safe-mode", "--strict-mcp-config",
                "--output-format", "stream-json", "--verbose", "--model",
                "gpt-fixture", "--effort", "opaque", "--append-system-prompt-file",
                str(ROOT / "system/claude/prompts/implementer.md"), "--tools",
                "Read,Write,Edit,Bash,Grep,Glob", "--permission-mode", "acceptEdits",
                "--allowedTools", "Bash", "--permission-prompts", "none",
                "--no-session-persistence",
            ),
            ("claude", "plan"): (
                claude, "-p", "--safe-mode", "--strict-mcp-config",
                "--output-format", "stream-json", "--verbose", "--model",
                "gpt-fixture", "--effort", "opaque", "--system-prompt-file",
                str(ROOT / "system/claude/prompts/plan.md"), "--tools",
                "Read,Grep,Glob", "--permission-prompts", "none",
                "--no-session-persistence",
            ),
        }
        for (provider, role), expected in cases.items():
            with self.subTest(provider=provider, role=role):
                actual = LAUNCH_LANE.launch_argv(
                    provider,
                    role,
                    "gpt-fixture",
                    "opaque",
                    worktree=self.linked_worktree,
                    plugin_root=ROOT,
                    staging=staging,
                )
                self.assertEqual(actual, expected)

    def test_every_cell_uses_selected_cwd_and_exact_saved_stdin(self) -> None:
        for index, (provider, role) in enumerate(
            (
                ("codex", "implementer"),
                ("codex", "plan"),
                ("claude", "implementer"),
                ("claude", "plan"),
            ),
            start=1,
        ):
            with self.subTest(provider=provider, role=role):
                self.configure_route(role, provider)
                run_id = f"run-20260928-launch-cell-{index}"
                engine = self.ready_engine(run_id)
                expected = LAUNCH_LANE.prepare_prompt(
                    engine.ctx,
                    LAUNCH_LANE.PromptRequest(
                        role, provider, self.linked_worktree, self.head, self.brief
                    ),
                ).prompt
                calls: list[tuple[tuple[str, ...], dict[str, object]]] = []

                def capture(
                    launcher_argv: tuple[str, ...],
                    *,
                    _calls: list[tuple[tuple[str, ...], dict[str, object]]] = calls,
                    _index: int = index,
                    **kwargs: object,
                ) -> SimpleNamespace:
                    _calls.append((tuple(launcher_argv), dict(kwargs)))
                    return SimpleNamespace(pid=420_000 + _index)

                with patch_engine("spawn_wrapper", side_effect=capture):
                    outcome = self.launch_direct(
                        role=role, engine=engine, worktree=self.linked_worktree
                    )
                self.assertTrue(outcome.ok)
                self.assertEqual(calls[0][1]["cwd"], self.linked_worktree)
                records = self.execution_records(run_id)
                directory = (
                    self.run_dir(self.repo, run_id)
                    / str(records[0]["agent"])
                    / str(records[0]["execution"])
                )
                self.assertEqual((directory / "prompt.md").read_bytes(), expected)

    def test_prompt_uses_committed_context_and_ignores_untracked_gotchas(self) -> None:
        committed = subprocess.run(
            ["git", "-C", str(self.linked_worktree), "show", f"{self.head}:forge-project.md"],
            check=True,
            capture_output=True,
        ).stdout
        begin = b"<!-- FORGE:REGION agent-project-context BEGIN -->\n"
        end = b"<!-- FORGE:REGION agent-project-context END -->"
        context = committed.split(begin, 1)[1].split(end, 1)[0]
        project = self.linked_worktree / "forge-project.md"
        project.write_bytes(committed.replace(context, b"dirty context\n", 1))
        untracked = self.linked_worktree / ".forge/history/gotchas.md"
        untracked.parent.mkdir(parents=True, exist_ok=True)
        untracked.write_text("dirty untracked gotcha\n", encoding="utf-8")
        engine = self.ready_engine(open_task=False)
        for provider, role in (("codex", "plan"), ("claude", "plan")):
            with self.subTest(provider=provider):
                body_path = ROOT / f"system/{provider}/prompts/{role}.md"
                body = body_path.read_bytes()
                material = LAUNCH_LANE.prepare_prompt(
                    engine.ctx,
                    LAUNCH_LANE.PromptRequest(
                        role, provider, self.linked_worktree, self.head, self.brief
                    ),
                )
                prefix = body + b"\n" if provider == "codex" else b"\n"
                self.assertEqual(
                    material.prompt,
                    prefix
                    + b"--- committed agent-project-context ---\n"
                    + context
                    + b"\n--- committed gotchas (optional; empty when absent) ---\n"
                    + b"\n--- task assignment ---\n"
                    + self.brief.read_bytes(),
                )
                self.assertEqual(material.role_body_path, body_path)
                self.assertEqual(material.role_body_sha256, digest(body))

    def test_prompt_reads_committed_gotchas_not_working_tree(self) -> None:
        gotchas = self.repo / ".forge/history/gotchas.md"
        gotchas.parent.mkdir(parents=True, exist_ok=True)
        gotchas.write_text("committed gotcha\n", encoding="utf-8")
        subprocess.run(
            ["git", "-C", str(self.repo), "add", ".forge/history/gotchas.md"],
            check=True,
        )
        subprocess.run(
            [
                "git", "-C", str(self.repo), "-c", "user.name=Forge Tests",
                "-c", "user.email=forge-tests@example.invalid", "commit", "--quiet",
                "-m", "fixture gotchas",
            ],
            check=True,
        )
        self.head = subprocess.run(
            ["git", "-C", str(self.repo), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        subprocess.run(
            ["git", "-C", str(self.linked_worktree), "merge", "--ff-only", self.head],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        linked_gotchas = self.linked_worktree / ".forge/history/gotchas.md"
        linked_gotchas.write_text("dirty gotcha\n", encoding="utf-8")
        engine = self.ready_engine(open_task=False)
        for provider in ("codex", "claude"):
            material = LAUNCH_LANE.prepare_prompt(
                engine.ctx,
                LAUNCH_LANE.PromptRequest(
                    "implementer", provider, self.linked_worktree, self.head, self.brief
                ),
            )
            self.assertIn(b"committed gotcha\n", material.prompt)
            self.assertNotIn(b"dirty gotcha", material.prompt)

    def test_brief_validation_refuses_every_unsafe_shape(self) -> None:
        diagnostic = (
            "forge: launch refused — brief must be an owner-controlled regular "
            "UTF-8 file of at most 1 MiB"
        )
        invalid: list[Path] = []
        missing = self.scratch / "missing.md"
        invalid.append(missing)
        directory = self.scratch / "brief-dir"
        directory.mkdir()
        invalid.append(directory)
        symlink = self.scratch / "brief-link"
        symlink.symlink_to(self.brief)
        invalid.append(symlink)
        nul = self.scratch / "brief-nul"
        nul.write_bytes(b"bad\0brief")
        invalid.append(nul)
        non_utf8 = self.scratch / "brief-non-utf8"
        non_utf8.write_bytes(b"\xff")
        invalid.append(non_utf8)
        oversized = self.scratch / "brief-oversized"
        oversized.write_bytes(b"x" * (LAUNCH_LANE.BRIEF_LIMIT_BYTES + 1))
        invalid.append(oversized)
        for path in invalid:
            with self.subTest(path=path.name), self.assertRaises(ENGINE.Refusal) as caught:
                LAUNCH_LANE.read_brief(path)
            self.assertEqual(caught.exception.message, diagnostic)
        self.assertEqual(LAUNCH_LANE.read_brief(self.brief), self.brief.read_bytes())

    def test_launch_argv_is_hermetic_under_stripped_path(self) -> None:
        self.assertEqual(os.environ["PATH"], STRIPPED_PATH)
        self.assertIsNone(shutil.which("codex", path=STRIPPED_PATH))
        self.assertIsNone(shutil.which("claude", path=STRIPPED_PATH))
        self.assertTrue(Path(LAUNCH_LANE.CODEX_EXECUTABLE).is_absolute())
        self.assertTrue(Path(LAUNCH_LANE.CLAUDE_EXECUTABLE).is_absolute())
        self.assertEqual(
            LAUNCH_LANE.launch_argv(
                "codex", "plan", "model", "opaque", worktree=self.linked_worktree,
                plugin_root=ROOT, staging=self.scratch / "handoff.staging",
            )[0],
            str(self.bin_dir / "codex"),
        )


if __name__ == "__main__":
    unittest.main()
