from __future__ import annotations

import inspect
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from contextlib import AbstractContextManager, contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from types import FunctionType
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
TOOLS = SCRIPTS / "codex_orch_tools.py"
MERGE_SKILL = (ROOT / "skills/worktree-merge/SKILL.md").read_text(encoding="utf-8")
WORKFLOW_SKILL = (ROOT / "skills/workflow/SKILL.md").read_text(encoding="utf-8")
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from tests._git_env import init_quiet_repository  # noqa: E402

from codex_orchestrator import worktree_guard  # noqa: E402

GIT_TEST_ENV = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}


def mutated_function(function: FunctionType, anchor: str, replacement: str) -> FunctionType:
    source = textwrap.dedent(inspect.getsource(function))
    if source.count(anchor) != 1:
        raise AssertionError(f"mutation anchor drifted for {function.__name__}")
    namespace = dict(function.__globals__)
    exec(compile(source.replace(anchor, replacement, 1),
                 function.__code__.co_filename, "exec"), namespace)
    mutant = namespace[function.__name__]
    if not isinstance(mutant, FunctionType):
        raise AssertionError(f"mutation did not define {function.__name__}")
    return mutant


def legacy_drop_citation(value: str, roots: tuple[Path, ...]) -> Path:
    selected = worktree_guard.resolve_contained_path(value, roots)
    if selected is not None and selected.contained:
        return selected.resolved
    return roots[-1].resolve()


def run_git(repository: Path, *arguments: str) -> None:
    subprocess.run(["git", "-C", str(repository), *arguments], env=GIT_TEST_ENV,
                   check=True, capture_output=True)


def file_snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*")
        if path.is_file()
    }


def assert_cleanup_status_contract(
    case: unittest.TestCase, skill: str, status_variable: str, outcome_variable: str,
    capture_fragment: str,
) -> tuple[str, ...]:
    case.assertEqual(capture_fragment.count(f"|| {status_variable}=$?"), 1)
    case.assertEqual(skill.count(capture_fragment), 1)
    marker = f'case "${status_variable}" in'
    status_block = skill.split(marker, maxsplit=1)[1].split("esac", maxsplit=1)[0]
    fragments = (
        f'  1)\n    {outcome_variable}="cleanup deferred"',
        "  2)\n    exit 2\n    ;;",
        "  *)\n    echo \"forge: worktree check refused — unexpected exit "
        f"${status_variable}\" >&2\n    exit 2\n    ;;",
    )
    for fragment in fragments:
        case.assertEqual(status_block.count(fragment), 1)
    deferred = status_block.split("  1)\n", 1)[1].split("  2)\n", 1)[0]
    for command in ("worktree remove", "update-ref -d", "update-ref --delete",
                    "branch -d", "branch -D", "branch --delete"):
        case.assertNotIn(command, deferred)
    return (capture_fragment, *fragments)


def guard_skill_fragments() -> tuple[tuple[str, str], ...]:
    quoted = tuple(f"`{label}`"
                   for label in worktree_guard.WORKTREE_GUARD_CITATION_SURFACES)
    surfaces = ", ".join((*quoted[:-1], f"and {quoted[-1]}"))
    return (
        ("merge", "The check treats cited evidence as exactly the FR-017 journal-record "
         f"surfaces, in order: {surfaces}. It uses the shared per-surface tokenizer and "
         "resolves relative citations against the run directory first and the "
         "layout-derived repository root second."),
        ("merge", "It classifies runs-root children in bytewise name order. A non-dot "
         "regular file is skipped. A non-dot real non-symlink directory is skipped only "
         "when it is completely empty, ownerless, and has no `journal.jsonl`; this read-only "
         "check does not need the registry to recognize that inert placeholder. A directory "
         "containing `journal.jsonl` is scanned. Dot-prefixed entries or unsafe directory "
         "names, symlinks or broken links, other non-regular children, unreadable directories, "
         "owner-bearing or nonempty journal-less directories, empty, unreadable, symlinked, "
         "broken, or non-file journals, malformed scanned journals, and inspection errors all "
         "produce exit 2 with the unreadable-input diagnostic; none is silently skipped."),
        ("workflow", f"The complete journal-record surface list is {surfaces}. Relative "
         "citations use the shared FR-017 resolution order: the run directory first, then "
         "the layout-derived repository root."),
    )


def assert_guard_skill_contract(
    case: unittest.TestCase, merge: str, workflow: str
) -> tuple[tuple[str, str], ...]:
    sources = {"merge": " ".join(merge.split()), "workflow": " ".join(workflow.split())}
    fragments = guard_skill_fragments()
    for scope, fragment in fragments:
        case.assertEqual(sources[scope].count(fragment), 1)
    return fragments


class _WorktreeGuardFixture:
    def setUp(self) -> None:
        environment_patch = mock.patch.dict(os.environ, GIT_TEST_ENV, clear=True)
        environment_patch.start()
        self.addCleanup(environment_patch.stop)
        self.temporary = tempfile.TemporaryDirectory(prefix="forge-worktree-guard-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.repo = self.base / "repo"
        init_quiet_repository(self.repo, "--quiet").check_returncode()
        (self.repo / "README.md").write_text("guard fixture\n", encoding="utf-8")
        self._git("add", "--", "README.md")
        self._git("-c", "user.name=Forge Tests", "-c", "user.email=forge-tests@example.invalid",
                  "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "base")
        self.worktree = self.repo / ".worktrees" / "topic"
        self.worktree.parent.mkdir()
        self._git("worktree", "add", "--quiet", "-b", "guard-topic",
                  str(self.worktree), "HEAD")

    def _git(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(self.repo), *arguments], check=True, capture_output=True,
            text=True,
        )

    def _commit(self, message: str, *paths: Path) -> None:
        relative = (path.relative_to(self.repo).as_posix() for path in paths)
        self._git("add", "--", *relative)
        self._git("-c", "user.name=Forge Tests", "-c", "user.email=forge-tests@example.invalid",
                  "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", message)

    def _write_journal(
        self, run_id: str, records: list[dict[str, object]], *, owner: bool = True
    ) -> Path:
        run_dir = self.repo / ".codex-orchestrator" / "runs" / run_id
        run_dir.mkdir(parents=True)
        payload = "".join(json.dumps(record, sort_keys=True, separators=(",", ":"))
                          + "\n" for record in records)
        journal = run_dir / "journal.jsonl"
        journal.write_text(payload, encoding="utf-8")
        if owner:
            (run_dir / "owner").write_text(
                "pid: 1\nhost: forge-tests\nstarted_at: 2026-08-13T00:00:00Z\n")
        return journal

    def _opening(self, run_id: str, repository: Path) -> dict[str, object]:
        return {"type": "run_started", "run_id": run_id, "repo": str(repository)}

    def _command(self) -> tuple[int, str, str]:
        command = (sys.executable, str(TOOLS), "worktree-check", "--repo", str(self.repo),
                   "--worktree", str(self.worktree))
        result = subprocess.run(command, cwd=self.repo, check=False,
                                capture_output=True, text=True)
        return result.returncode, result.stdout, result.stderr

    def _in_process(
        self, worktree: Path | None = None, repo: Path | None = None
    ) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            selected_repo = self.repo if repo is None else repo
            selected_worktree = self.worktree if worktree is None else worktree
            result = worktree_guard.main(selected_repo, selected_worktree)
        return result, stdout.getvalue(), stderr.getvalue()

    def _expected_deferral(self, run_id: str) -> str:
        return (
            f"forge: worktree cleanup deferred — run {run_id} has no committed "
            "archive and depends on .worktrees/topic\n"
        )

    def _expected_input_refusal(self, run_id: str | None = None) -> str:
        diagnostic = worktree_guard.INPUT_DIAGNOSTIC + "\n"
        if run_id is not None:
            diagnostic += worktree_guard.RUN_INPUT_DIAGNOSTIC.format(run_id=run_id) + "\n"
        return diagnostic

    def _expected_result(self, status: int, run_id: str = "") -> tuple[int, str, str]:
        stderr = (self._expected_input_refusal() if status == 2 else
                  self._expected_deferral(run_id) if status == 1 else "")
        return status, "", stderr

    def _directory_child(
        self, directory: Path, name: str, content: str | None = ""
    ) -> Path:
        directory.mkdir()
        child = directory / name
        child.mkdir() if content is None else child.write_text(content)
        return child

    def _assert_shape_refusal_is_load_bearing(
        self, patcher: AbstractContextManager[object], *, refusal_run_id: str | None = None,
    ) -> None:
        expected = (2, "", self._expected_input_refusal(refusal_run_id))
        self.assertEqual(self._in_process(), expected)
        with patcher:
            self.assertEqual(self._in_process(), (0, "", ""))

    def _assert_stale_entry_recheck(
        self, name: str, directory: bool, function: FunctionType, anchor: str
    ) -> None:
        runs_root = self.repo / ".codex-orchestrator" / "runs"
        runs_root.mkdir(parents=True)
        path = runs_root / name
        builder = Path.mkdir if directory else Path.touch
        builder(path)
        with os.scandir(runs_root) as iterator:
            entry = next(iterator)
            observed = entry.stat(follow_symlinks=False)
        path.rename(path.with_name(f"{name}-observed"))
        builder(path)
        self.assertNotEqual(observed.st_ino, path.lstat().st_ino)
        mutant = mutated_function(function, anchor, "")
        with mock.patch.object(worktree_guard, "_runs_root_entries", return_value=(entry,)):
            self.assertEqual(self._in_process(), self._expected_result(2))
            with mock.patch.object(worktree_guard, function.__name__, mutant):
                self.assertEqual(self._in_process(), self._expected_result(0))

    def _cited_records(self, run_id: str) -> list[dict[str, object]]:
        evidence = self.worktree / "evidence" / "proof.txt"
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text("proof\n", encoding="utf-8")
        citation = evidence.relative_to(self.repo).as_posix()
        return [
            self._opening(run_id, self.repo),
            {"type": "verification", "id": "check-01", "evidence": [citation]},
            {"type": "run_closed", "judgment": "passed"},
        ]

    def _legacy_records(self, run_id: str, evidence: str) -> list[dict[str, object]]:
        return [
            self._opening(run_id, self.repo),
            {"type": "observation", "detail": "legacy narrative"},
            {"type": "execution", "agent": "legacy", "execution": "execution-01",
             "events": ""},
            {"type": "verification", "id": "legacy-check", "evidence": evidence},
            {
                "type": "decision",
                "id": "journal-dialect-compat",
                "resolution": "legacy-dialect-compat: operator-approved migration",
            },
        ]

    def _legacy_opening(self, run_id: str, repository: Path) -> dict[str, object]:
        return {"type": "run_started", "id": run_id, "repo": str(repository)}


class WorktreeGuardTests(_WorktreeGuardFixture, unittest.TestCase):

    def test_open_run_recorded_repo_realpath_defers_cleanup(self) -> None:
        run_id = "run-open-worktree"
        alias = self.base / "worktree-alias"
        alias.symlink_to(self.worktree, target_is_directory=True)
        self._write_journal(run_id, [self._opening(run_id, alias)])

        self.assertEqual(self._command(), (1, "", self._expected_deferral(run_id)))

    def test_unarchived_closed_run_citing_worktree_defers_cleanup(self) -> None:
        run_id = "run-closed-citation"
        self._write_journal(run_id, self._cited_records(run_id))

        self.assertEqual(self._command(), (1, "", self._expected_deferral(run_id)))

    def test_only_archive_committed_at_head_releases_cleanup(self) -> None:
        run_id = "run-archived"
        self._write_journal(run_id, [self._opening(run_id, self.worktree)])
        archive = self.repo / ".forge" / "history" / "runs" / f"{run_id}.md"
        archive.parent.mkdir(parents=True)
        archive.write_text("# Archived\n", encoding="utf-8")
        self._git("add", "--", archive.relative_to(self.repo).as_posix())

        staged = self._command()
        self.assertEqual(staged[0], 1)

        self._commit("archive run", archive)
        self._git("cat-file", "-e", f"HEAD:{archive.relative_to(self.repo).as_posix()}")

        committed = self._command()
        self.assertEqual(committed, (0, "", ""))

    def test_archive_tree_does_not_release_cleanup(self) -> None:
        run_id = "run-archive-tree"
        self._write_journal(run_id, [self._opening(run_id, self.worktree)])
        archive = self.repo / ".forge/history/runs" / f"{run_id}.md"
        archive.mkdir(parents=True)
        child = archive / "child"
        child.write_text("not an archive blob\n", encoding="utf-8")
        self._commit("archive tree", child)
        self.assertEqual(self._in_process(), (1, "", self._expected_deferral(run_id)))

        def any_object(repository: Path, head: str, candidate: str) -> bool:
            rev = f"{head}:.forge/history/runs/{candidate}.md"
            return worktree_guard._run_git(repository, "cat-file", "-e", rev).returncode == 0

        with mock.patch.object(worktree_guard, "_archive_is_committed", any_object):
            self.assertEqual(self._in_process(), (0, "", ""))


class WorktreeGuardValidationTests(_WorktreeGuardFixture, unittest.TestCase):

    def test_archive_inspection_failure_refuses_load_bearing(self) -> None:
        run_id = "run-archive-inspection"
        self._write_journal(run_id, [self._opening(run_id, self.repo)])
        real_run_git = worktree_guard._run_git

        def fail_archive(
            repository: Path, *arguments: str
        ) -> subprocess.CompletedProcess[bytes]:
            if arguments[0] in {"cat-file", "ls-tree"}:
                return subprocess.CompletedProcess(arguments, 128, b"", b"")
            return real_run_git(repository, *arguments)

        with mock.patch.object(worktree_guard, "_run_git", side_effect=fail_archive):
            self.assertEqual(
                self._in_process(), (2, "", self._expected_input_refusal(run_id))
            )
        with mock.patch.object(worktree_guard, "_archive_is_committed", return_value=False):
            self.assertEqual(self._in_process(), (0, "", ""))

    def test_ownerless_precoordination_run_passes(self) -> None:
        run_id = "run-unreferenced"
        self._write_journal(run_id, [self._opening(run_id, self.repo)], owner=False)

        self.assertEqual(self._command(), (0, "", ""))

    def test_ownerless_legacy_forms_do_not_block_unreferenced_worktree(self) -> None:
        run_id = "run-legacy-unreferenced"
        journal = self._write_journal(
            run_id, self._legacy_records(run_id, "evidence/legacy.txt"), owner=False
        )
        evidence = journal.parent / "evidence" / "legacy.txt"
        evidence.parent.mkdir()
        evidence.write_text("legacy\n", encoding="utf-8")

        self.assertEqual(self._command(), (0, "", ""))

    def test_ownerless_current_run_refuses_load_bearing(self) -> None:
        run_id = "run-ownerless-current"
        opening = self._opening(run_id, self.repo)
        opening["scope"] = ["src/**"]
        self._write_journal(run_id, [opening], owner=False)
        self.assertEqual(
            self._in_process(), (2, "", self._expected_input_refusal(run_id))
        )
        with mock.patch.object(worktree_guard, "_require_current_owner"):
            self.assertEqual(self._in_process(), (0, "", ""))

    def test_dm011_lifecycle_validation_is_load_bearing(self) -> None:
        for name, records in (
            ("invalid-scope", [{"scope": []}]),
            ("scopeless-retired", [{}, {"type": "decision",
             "id": "forge-run-retired",
             "resolution": worktree_guard.journal.RETIREMENT_RESOLUTION}]),
        ):
            run_id = f"run-{name}"
            opening = self._opening(run_id, self.repo) | records[0]
            journal_path = self._write_journal(run_id, [opening, *records[1:]])
            with self.subTest(shape=name):
                self.assertEqual(
                    self._in_process(), (2, "", self._expected_input_refusal(run_id))
                )
                state = mock.Mock(legacy=False, pre_coordination=False)
                with mock.patch.object(worktree_guard.journal, "_scan_run",
                                       return_value=state):
                    self.assertEqual(self._in_process(), (0, "", ""))
            shutil.rmtree(journal_path.parent)

    def test_unborn_head_refusal_is_load_bearing(self) -> None:
        unborn = self.base / "unborn"
        init_quiet_repository(unborn, "--quiet").check_returncode()
        target = unborn / "target"
        target.mkdir()
        self.assertEqual(
            self._in_process(target, unborn), (2, "", self._expected_input_refusal())
        )
        with mock.patch.object(worktree_guard, "_require_head"):
            self.assertEqual(self._in_process(target, unborn), (0, "", ""))

    def test_head_change_refuses_load_bearing(self) -> None:
        with mock.patch.object(worktree_guard, "_require_head",
                               side_effect=("old-head", "new-head")):
            self.assertEqual(
                self._in_process(), (2, "", self._expected_input_refusal())
            )
        with mock.patch.object(worktree_guard, "_require_head", return_value="old-head"):
            self.assertEqual(self._in_process(), (0, "", ""))

    def test_declared_legacy_string_evidence_is_scanned(self) -> None:
        run_id = "run-legacy-citation"
        evidence = self.worktree / "evidence" / "legacy.txt"
        evidence.parent.mkdir(parents=True)
        evidence.write_text("legacy\n", encoding="utf-8")
        citation = evidence.relative_to(self.repo).as_posix()
        self._write_journal(run_id, self._legacy_records(run_id, citation))

        self.assertEqual(self._command(), (1, "", self._expected_deferral(run_id)))

    def test_lifecycle_legacy_tail_matches_authoritative_reader(self) -> None:
        run_id = "run-legacy-tail"
        journal_path = self._write_journal(
            run_id,
            [
                self._legacy_opening(run_id, self.worktree),
                {"type": "run_closed"},
                {"type": "decision", "id": "legacy-followup",
                 "resolution": "legacy follow-up"},
            ],
        )
        state = worktree_guard.journal._scan_run(journal_path.parent)
        self.assertTrue(state.legacy)

        self.assertEqual(
            self._in_process(), (1, "", self._expected_deferral(run_id))
        )

    def test_recorded_repo_descendant_defers_cleanup(self) -> None:
        run_id = "run-recorded-repo-descendant"
        recorded_repo = self.worktree / "scripts"
        recorded_repo.mkdir()
        self._write_journal(run_id, [self._opening(run_id, recorded_repo)])

        self.assertEqual(
            self._in_process(), (1, "", self._expected_deferral(run_id))
        )

        def equality_only(recorded: Path, worktree: Path) -> bool:
            return (
                "recorded-repo" in worktree_guard.WORKTREE_GUARD_LEGS
                and recorded == worktree
            )

        with mock.patch.object(worktree_guard, "_depends_on_recorded_repo", equality_only):
            self.assertEqual(self._in_process(), (0, "", ""))

    def test_physical_citation_spellings_are_load_bearing(self) -> None:
        absolute_without_physical_resolution = mutated_function(worktree_guard._resolve_citation,
            "            return candidate.resolve(strict=False)\n",
            "            return Path(os.path.abspath(candidate))\n")
        for spelling in ("absolute", "absolute-symlink", "escape", "symlink"):
            run_id = f"run-{spelling}-citation"
            run_dir = self.repo / ".codex-orchestrator" / "runs" / run_id
            evidence = self.worktree / "evidence" / f"{spelling}.txt"
            evidence.parent.mkdir(parents=True, exist_ok=True)
            evidence.write_text("citation\n", encoding="utf-8")
            citation = str(evidence)
            if spelling == "absolute-symlink":
                alias = self.base / "absolute-citation-link"
                alias.symlink_to(self.worktree, target_is_directory=True)
                citation = str(alias / evidence.relative_to(self.worktree))
            elif spelling == "escape":
                citation = Path(os.path.relpath(evidence, run_dir)).as_posix()
            elif spelling == "symlink":
                citation = "evidence-link/symlink.txt"
            records = [self._legacy_opening(run_id, self.repo),
                       {"type": "verification", "id": "physical-check",
                        "evidence": [citation]}, {"type": "run_closed"}]
            journal_path = self._write_journal(run_id, records)
            if spelling == "symlink":
                (journal_path.parent / "evidence-link").symlink_to(
                    evidence.parent, target_is_directory=True
                )
            with self.subTest(spelling=spelling):
                self.assertEqual(
                    self._in_process(), (1, "", self._expected_deferral(run_id))
                )
                with mock.patch.object(worktree_guard, "_resolve_citation",
                                       legacy_drop_citation):
                    self.assertEqual(self._in_process(), (0, "", ""))
                if spelling == "absolute-symlink":
                    with mock.patch.object(
                        worktree_guard, "_resolve_citation", absolute_without_physical_resolution,
                    ):
                        self.assertEqual(self._in_process(), (0, "", ""))
            shutil.rmtree(journal_path.parent)

    def test_indeterminate_citation_resolution_refuses_load_bearing(self) -> None:
        run_id = "run-indeterminate-citation"
        records = [self._legacy_opening(run_id, self.worktree),
                   {"type": "verification", "id": "loop-check",
                    "evidence": ["loop/proof.txt"]}, {"type": "run_closed"}]
        self._write_journal(run_id, records)
        with mock.patch.object(worktree_guard, "resolve_contained_path", return_value=None):
            self.assertEqual(
                self._in_process(), (2, "", self._expected_input_refusal(run_id))
            )
            with mock.patch.object(
                worktree_guard, "_resolve_citation", return_value=self.repo
            ):
                self.assertEqual(
                    self._in_process(), (1, "", self._expected_deferral(run_id))
                )

    def test_malformed_journal_fails_closed_and_names_known_run(self) -> None:
        run_id = "run-malformed"
        opening = self._opening(run_id, self.repo)
        journal = self._write_journal(run_id, [opening])
        with journal.open("a", encoding="utf-8") as handle:
            handle.write("{bad\n")
        archive = self.repo / ".forge/history/runs" / f"{run_id}.md"
        archive.parent.mkdir(parents=True)
        archive.write_text("# Archived\n", encoding="utf-8")
        self._commit("archive malformed run", archive)

        self.assertEqual(
            self._command(), (2, "", self._expected_input_refusal(run_id))
        )
        with mock.patch.object(
            worktree_guard, "_validated_journal", return_value=(opening, [opening])
        ):
            self.assertEqual(self._in_process(), (0, "", ""))

        def assert_named_refusal() -> None:
            disabled_result = self._in_process()
            self.assertEqual(disabled_result[2], self._expected_input_refusal(run_id))

        without_run = (worktree_guard.INPUT_DIAGNOSTIC,)
        with mock.patch.object(worktree_guard, "_input_diagnostics",
                               return_value=without_run), self.assertRaises(AssertionError):
            assert_named_refusal()

    def test_unknown_record_type_fails_closed(self) -> None:
        run_id = "run-unknown-record"
        self._write_journal(
            run_id,
            [
                self._opening(run_id, self.repo),
                {"type": "unknown", "evidence": [".worktrees/topic/proof.txt"]},
            ],
        )

        self.assertEqual(
            self._command(), (2, "", self._expected_input_refusal(run_id))
        )

    def test_malformed_citation_field_fails_closed(self) -> None:
        run_id = "run-malformed-evidence"
        self._write_journal(
            run_id,
            [
                self._opening(run_id, self.repo),
                {"type": "verification", "evidence": ".worktrees/topic/proof.txt"},
            ],
        )

        self.assertEqual(
            self._command(), (2, "", self._expected_input_refusal(run_id))
        )

    def test_unexpected_exception_exits_two_without_traceback(self) -> None:
        with mock.patch.object(
            worktree_guard,
            "find_dependency",
            side_effect=KeyError("unexpected"),
        ):
            mutant = mutated_function(
                worktree_guard.main,
                "    except Exception:\n",
                "    except WorktreeGuardError:\n",
            )
            intact = self._in_process()

        self.assertEqual(intact, (2, "", self._expected_input_refusal()))
        with self.assertRaises(KeyError):
            mutant(self.repo, self.worktree)

    def test_worktree_check_argparse_usage_error_exits_two(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(TOOLS),
                "worktree-check",
                "--repo",
                str(self.repo),
            ],
            cwd=self.repo,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr.splitlines()[0], worktree_guard.INPUT_DIAGNOSTIC)
        self.assertIn("usage:", result.stderr)
        self.assertIn("--worktree", result.stderr)


class WorktreeGuardFixFourTests(_WorktreeGuardFixture, unittest.TestCase):

    def test_unsafe_worktree_names_refuse_before_deferral(self) -> None:
        undecodable = os.fsdecode(b"topic-\xff")
        self.assertEqual(os.fsencode(undecodable), b"topic-\xff")
        for label, name in (("c1", "topic-\x85"), ("undecodable", undecodable)):
            target = self.worktree.parent / name
            target.mkdir()
            run_id = f"run-unsafe-worktree-{label}"
            self._write_journal(run_id, [self._opening(run_id, target)])

            intact = self._in_process(target)
            with mock.patch.object(
                worktree_guard, "_safe_output_text", return_value=True
            ):
                weakened = self._in_process(target)

            relative = Path(os.path.relpath(target, self.repo)).as_posix()
            expected_deferral = (
                f"forge: worktree cleanup deferred — run {run_id} has no "
                f"committed archive and depends on {relative}\n"
            )
            with self.subTest(path_kind=label):
                self.assertEqual(intact, (2, "", self._expected_input_refusal()))
                self.assertEqual(weakened, (1, "", expected_deferral))

    def test_cleanup_skills_treat_only_exit_one_as_deferral(self) -> None:
        cases = (
            (MERGE_SKILL, "WORKTREE_CHECK_STATUS", "CLEANUP_OUTCOME",
             '  --repo "$MAIN_WORKTREE" --worktree "$WORKTREE_DIR" '
             '|| WORKTREE_CHECK_STATUS=$?'),
            (WORKFLOW_SKILL, "DEFERRED_CHECK_STATUS", "DEFERRED_CLEANUP_OUTCOME",
             '  --repo "$REPO" --worktree "$DEFERRED_WORKTREE" '
             '|| DEFERRED_CHECK_STATUS=$?'),
        )
        for skill, status_variable, outcome_variable, capture in cases:
            fragments = assert_cleanup_status_contract(
                self, skill, status_variable, outcome_variable, capture
            )
            for fragment in fragments:
                mutated = skill.replace(fragment, "DISABLED_STATUS_CONTROL", 1)
                with self.subTest(status=status_variable,
                                  disabled=fragment.splitlines()[0]), \
                        self.assertRaises(AssertionError):
                    assert_cleanup_status_contract(
                        self, mutated, status_variable, outcome_variable, capture
                    )
            deferred = f'    {outcome_variable}="cleanup deferred"'
            mutants = (
                skill.replace(capture, capture.replace("=$?", "=0"), 1),
                *(skill.replace(deferred, f"{deferred}\n    {command}", 1) for command in (
                    'git -C "$REPO" worktree remove "$WORKTREE_DIR"',
                    'git -C "$REPO" branch --delete "$BRANCH"')),
            )
            for mutant in mutants:
                with self.subTest(status=status_variable, weakened="capture-or-deferred"), \
                        self.assertRaises(AssertionError):
                    assert_cleanup_status_contract(
                        self, mutant, status_variable, outcome_variable, capture)

    def test_cleanup_blocks_execute_guard_deferral_and_refusal(self) -> None:
        from tests.test_worktree_merge_skill import run_cleanup_case

        for scenario, expected_status in (("dependent", 0), ("guard-refusal", 2)):
            for kind in ("merge", "workflow"):
                outcome = run_cleanup_case(kind, scenario)
                with self.subTest(block=kind, scenario=scenario):
                    self.assertEqual(outcome.process.returncode,
                                     expected_status or kind == "workflow")
                    if scenario == "dependent":
                        self.assertIn("cleanup deferred", outcome.process.stderr)
                    else:
                        self.assertEqual(
                            outcome.process.stderr,
                            self._expected_input_refusal("run-cleanup-block"),
                        )
                    self.assertTrue(outcome.worktree_exists)
                    self.assertEqual(outcome.branch_tip, outcome.expected_tip)


class WorktreeGuardFixFiveTests(_WorktreeGuardFixture, unittest.TestCase):

    def test_fix_five_skill_paragraphs_are_load_bearing(self) -> None:
        fragments = assert_guard_skill_contract(self, MERGE_SKILL, WORKFLOW_SKILL)
        sources = {
            "merge": " ".join(MERGE_SKILL.split()),
            "workflow": " ".join(WORKFLOW_SKILL.split()),
        }
        weakenings = (
            ("run directory first and the layout-derived repository root second",
             "layout-derived repository root first and the run directory second"),
            ("none is silently skipped", "some may be silently skipped"),
            ("run directory first, then the layout-derived repository root",
             "layout-derived repository root first, then the run directory"),
        )
        for (scope, paragraph), (strong, weak) in zip(fragments, weakenings, strict=True):
            for replacement in ("DISABLED_CONTROL", paragraph.replace(strong, weak)):
                mutated = sources[scope].replace(paragraph, replacement, 1)
                merge = mutated if scope == "merge" else sources["merge"]
                workflow = mutated if scope == "workflow" else sources["workflow"]
                with self.subTest(scope=scope, replacement=replacement[:20]), \
                        self.assertRaises(AssertionError):
                    assert_guard_skill_contract(self, merge, workflow)

    def test_relative_citation_uses_layout_root_not_recorded_repo(self) -> None:
        run_id = "run-layout-root-citation"
        recorded_repo = self.base / "recorded-repo"
        recorded_repo.mkdir()
        proof = self.worktree / "evidence" / "layout-root.txt"
        proof.parent.mkdir(parents=True)
        proof.write_text("proof\n", encoding="utf-8")
        citation = proof.relative_to(self.repo).as_posix()
        records = [self._opening(run_id, recorded_repo),
                   {"type": "verification", "evidence": [citation]}]
        journal = self._write_journal(run_id, records)
        self.assertFalse(worktree_guard._is_inside(self.worktree, recorded_repo))
        self.assertFalse((journal.parent / citation).exists())
        anchor = "            repository=common_root,\n"
        mutant = mutated_function(worktree_guard._dependency_for_journal, anchor,
                                  "            repository=recorded_repo,\n")
        self.assertEqual(self._in_process(), self._expected_result(1, run_id))
        with mock.patch.object(worktree_guard, "_dependency_for_journal", mutant):
            self.assertEqual(self._in_process(), self._expected_result(0))

    def test_regular_file_entry_recheck_detects_replacement(self) -> None:
        self._assert_stale_entry_recheck(
            "stub", False, worktree_guard._journal_path_for_entry,
            "        _require_same_entry(entry_path, observed)\n")

    def test_run_directory_recheck_detects_replacement(self) -> None:
        self._assert_stale_entry_recheck(
            "run-stale", True, worktree_guard._journal_for_directory,
            "    _require_same_entry(entry_path, observed)\n")

    def test_runs_root_recheck_detects_replacement(self) -> None:
        runs_root = self.repo / ".codex-orchestrator" / "runs"
        observed_root = runs_root.with_name("runs-observed")
        real_scandir = os.scandir
        anchor = "    _require_same_entry(runs_root, root_stat)\n"
        mutant = mutated_function(worktree_guard._runs_root_entries, anchor, "")

        @contextmanager
        def swapping_scandir(path: Path):
            with real_scandir(path) as iterator:
                yield iterator
            Path(path).rename(observed_root)
            Path(path).mkdir()

        def outcome(function: FunctionType) -> tuple[int, str, str]:
            for path in (runs_root, observed_root):
                if path.exists():
                    shutil.rmtree(path)
            runs_root.mkdir(parents=True)
            with mock.patch.object(worktree_guard.os, "scandir", swapping_scandir), \
                    mock.patch.object(worktree_guard, "_runs_root_entries", function):
                return self._in_process()

        self.assertEqual(outcome(worktree_guard._runs_root_entries), self._expected_result(2))
        self.assertEqual(outcome(mutant), self._expected_result(0))

    def test_runs_root_child_classes_are_load_bearing(self) -> None:
        runs_root = self.repo / ".codex-orchestrator" / "runs"
        add_child = self._directory_child
        journal = "journal.jsonl"
        valid = json.dumps(self._opening("run-valid", self.worktree)) + "\n"
        cases = (
            ("stub", Path.touch, 0),
            ("placeholder", Path.mkdir, 0),
            ("run-valid", lambda path: add_child(path, journal, valid), 1),
            (".crash-file", Path.touch, 2),
            ("live-link", lambda path: path.symlink_to(self.repo, True), 2),
            ("broken-link", lambda path: path.symlink_to(self.base / "missing"), 2),
            ("fifo", os.mkfifo, 2),
            ("unreadable-dir", lambda path: path.mkdir(mode=0), 2),
            ("owner-only", lambda path: add_child(path, "owner"), 2),
            ("nonempty", lambda path: add_child(path, "notes.txt"), 2),
            ("empty-journal", lambda path: add_child(path, journal), 2),
            ("unreadable", lambda path: add_child(path, journal, "{}\n").chmod(0), 2),
            ("nonfile-journal", lambda path: add_child(path, journal, None), 2),
        )
        for name, build, status in cases:
            runs_root.mkdir(parents=True)
            build(runs_root / name)
            disabled_status = 2 if status == 0 else 0

            def disabled(*_args: object, expected: int = status) -> None:
                if expected == 0:
                    raise worktree_guard.WorktreeGuardError

            with self.subTest(child=name):
                self.assertEqual(self._in_process(), self._expected_result(status, name))
                with mock.patch.object(
                    worktree_guard, "_journal_path_for_entry", side_effect=disabled
                ):
                    self.assertEqual(
                        self._in_process(), self._expected_result(disabled_status)
                    )
            if name == "unreadable-dir":
                (runs_root / name).chmod(0o700)
            shutil.rmtree(runs_root)

    def test_hostile_names_refuse_only_when_bytewise_scan_reaches_them(self) -> None:
        runs_root = self.repo / ".codex-orchestrator" / "runs"
        cases = (
            ("z-\x85-hostile", "a-dependent", 1),
            ("a-\x85-hostile", "z-dependent", 2),
        )
        for hostile, dependent, status in cases:
            runs_root.mkdir(parents=True)
            payload = json.dumps(self._opening(dependent, self.worktree)) + "\n"
            self._directory_child(runs_root / dependent, "journal.jsonl", payload)
            (runs_root / hostile).mkdir()
            with self.subTest(hostile=ascii(hostile)):
                self.assertEqual(
                    self._in_process(), self._expected_result(status, dependent)
                )
            shutil.rmtree(runs_root)

    def test_every_audit_record_citation_surface_defers(self) -> None:
        expected = (
            "execution.prompt", "execution.events", "execution.handoff",
            "execution_result.handoff", "verification.evidence",
            "decision.basis", "verification.observation",
        )
        shared = tuple(
            surface
            for surface in worktree_guard.commitment_surfaces(enforcement="audit")
            if surface.owner == "record"
        )
        self.assertEqual(worktree_guard.WORKTREE_GUARD_CITATION_SURFACES, expected)
        self.assertEqual(tuple(surface.label for surface in shared), expected)
        self.assertEqual(
            tuple(surface.roots for surface in shared),
            (("run", "repository"),) * len(expected),
        )
        proof = self.worktree / "evidence" / "proof.txt"
        proof.parent.mkdir(parents=True)
        proof.write_text("proof\n")
        citation = proof.relative_to(self.repo).as_posix()
        wrapped = f"`{citation}`"
        values = {
            "direct": citation, "array": [citation],
            "token-array": [wrapped], "tokens": wrapped,
        }
        run_id = "run-citation-surfaces"
        journal_path = self._write_journal(run_id, [self._opening(run_id, self.repo)])
        for surface in shared:
            assert surface.record_type is not None and surface.field is not None
            record: dict[str, object] = {"type": surface.record_type}
            record[surface.field] = values[surface.extraction]
            journal_path.write_text(
                json.dumps(self._opening(run_id, self.repo))
                + "\n"
                + json.dumps(record)
                + "\n"
            )
            enabled = tuple(item for item in expected if item != surface.label)
            with self.subTest(surface=surface.label):
                self.assertEqual(self._in_process(), self._expected_result(1, run_id))
                with mock.patch.object(
                    worktree_guard, "WORKTREE_GUARD_CITATION_SURFACES", enabled
                ):
                    self.assertEqual(self._in_process(), self._expected_result(0))

        shadow = journal_path.parent / citation
        shadow.parent.mkdir(parents=True)
        shadow.write_text("run-root shadow\n")
        self.assertEqual(self._in_process(), self._expected_result(0))
        real_roots = worktree_guard.surface_roots
        with mock.patch.object(
            worktree_guard,
            "surface_roots",
            side_effect=lambda *args, **kwargs: tuple(
                reversed(real_roots(*args, **kwargs))
            ),
        ):
            self.assertEqual(self._in_process(), self._expected_result(1, run_id))


class WorktreeGuardShapeTests(_WorktreeGuardFixture, unittest.TestCase):

    def test_invalid_recorded_repo_shapes_are_load_bearing(self) -> None:
        def accept(candidate: dict[str, object], _common_root: Path) -> Path:
            recorded = candidate["repo"]
            if isinstance(recorded, dict):
                recorded = recorded["path"]
            return Path(os.path.realpath(str(recorded)))

        cases: tuple[tuple[str, object], ...] = (
            ("relative", "."), ("mapping", {"path": str(self.repo)})
        )
        for name, recorded in cases:
            run_id = f"run-{name}-repo"
            opening = self._opening(run_id, self.repo)
            opening["repo"] = recorded
            journal_path = self._write_journal(run_id, [opening])
            archive = self.repo / ".forge/history/runs" / f"{run_id}.md"
            archive.parent.mkdir(parents=True, exist_ok=True)
            archive.write_text("# Archived\n", encoding="utf-8")
            self._commit(f"archive {name} repo", archive)
            with self.subTest(shape=name):
                self._assert_shape_refusal_is_load_bearing(
                    mock.patch.object(worktree_guard, "_recorded_repository", accept),
                    refusal_run_id=run_id,
                )
            shutil.rmtree(journal_path.parent)

    def test_unsafe_run_id_refusal_is_load_bearing(self) -> None:
        run_id = "run-\x85"
        self._write_journal(run_id, [self._opening(run_id, self.repo)])

        self._assert_shape_refusal_is_load_bearing(
            mock.patch.object(worktree_guard, "_safe_run_id", return_value=True)
        )
        unsafe_ids = (
            ".unsafe-run",
            "run/child",
            "run\\child",
            "run\x00child",
            "run\nchild",
            "run\rchild",
            "run\x1fchild",
            "run\x7fchild",
            "run\x80child",
            "run\x9fchild",
            os.fsdecode(b"run-\xff"),
            "run-" + chr(0xD800),
        )
        for run_id in unsafe_ids:
            with self.subTest(run_id=ascii(run_id)):
                self.assertFalse(worktree_guard._safe_run_id(run_id))

    def test_cleanup_scratch_repo_ignores_inherited_git_redirects(self) -> None:
        decoy = self.base / "decoy"
        init_quiet_repository(decoy, "--quiet", environment=GIT_TEST_ENV).check_returncode()
        (decoy / "tracked.txt").write_text("decoy\n", encoding="utf-8")
        run_git(decoy, "add", "--", "tracked.txt")
        run_git(decoy, "-c", "user.name=Forge Tests", "-c",
                "user.email=forge-tests@example.invalid", "commit", "--quiet", "-m", "decoy")
        before = file_snapshot(decoy)
        script = textwrap.dedent(
            """
            from tests.test_worktree_merge_skill import run_cleanup_case

            outcome = run_cleanup_case("merge", "clean")
            assert outcome.process.returncode == 0, outcome.process.stderr
            assert not outcome.worktree_exists
            assert outcome.branch_tip is None
            """
        )
        redirects = {
            "GIT_DIR": str(decoy / ".git"),
            "GIT_INDEX_FILE": str(decoy / ".git" / "index"),
        }
        with mock.patch.dict(os.environ, redirects):
            completed = subprocess.run(
                [sys.executable, "-c", script],
                cwd=ROOT,
                env=dict(os.environ),
                check=False,
                capture_output=True,
                text=True,
                timeout=90,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(file_snapshot(decoy), before)

    def test_runs_root_not_directory_refusal_is_load_bearing(self) -> None:
        orchestration_root = self.repo / ".codex-orchestrator"
        orchestration_root.mkdir()
        (orchestration_root / "runs").write_text("not a directory\n")

        self._assert_shape_refusal_is_load_bearing(
            mock.patch.object(
                worktree_guard, "_runs_root_entries", return_value=None
            )
        )

    def test_journal_not_regular_file_refusal_is_load_bearing(self) -> None:
        run_dir = self.repo / ".codex-orchestrator" / "runs" / "run-dir-journal"
        run_dir.mkdir(parents=True)
        (run_dir / "journal.jsonl").mkdir()

        self._assert_shape_refusal_is_load_bearing(
            mock.patch.object(
                worktree_guard, "_journal_path_for_entry", return_value=None
            )
        )

    def test_control_character_relative_path_refusal_is_load_bearing(self) -> None:
        real_ord = ord
        for control in ("\n", "\x7f", "\x80", "\x9f"):
            relative = f"bad{control}path"

            def ignore_control(character: str, target: str = control) -> int:
                return 32 if character == target else real_ord(character)

            with self.subTest(control=ascii(control)), mock.patch.object(
                worktree_guard.os.path, "relpath", return_value=relative
            ):
                self.assertEqual(
                    self._in_process(), (2, "", self._expected_input_refusal())
                )
            with self.subTest(control=ascii(control)), mock.patch.object(
                worktree_guard.os.path, "relpath", return_value=relative
            ), mock.patch("builtins.ord", side_effect=ignore_control):
                self.assertEqual(self._in_process(), (0, "", ""))

    def test_symlinked_runs_root_refusal_is_load_bearing(self) -> None:
        orchestration_root = self.repo / ".codex-orchestrator"
        orchestration_root.mkdir()
        target = self.base / "symlinked-runs-root-target"
        target.mkdir()
        (orchestration_root / "runs").symlink_to(
            target, target_is_directory=True
        )

        self.assertEqual(self._in_process(), self._expected_result(2))

        enabled = worktree_guard.WORKTREE_INPUT_CONTROLS - {
            "symlinked-runs-root"
        }
        with mock.patch.object(worktree_guard, "WORKTREE_INPUT_CONTROLS", enabled):
            self.assertEqual(self._in_process(), self._expected_result(0))

    def test_symlinked_run_directory_refusal_is_load_bearing(self) -> None:
        run_id = "run-symlinked-directory"
        runs_root = self.repo / ".codex-orchestrator" / "runs"
        runs_root.mkdir(parents=True)
        target = self.base / "symlinked-run-target"
        target.mkdir()
        payload = json.dumps(
            self._opening(run_id, self.worktree),
            sort_keys=True,
            separators=(",", ":"),
        )
        (target / "journal.jsonl").write_text(payload + "\n", encoding="utf-8")
        (runs_root / run_id).symlink_to(target, target_is_directory=True)

        self.assertEqual(self._in_process(), self._expected_result(2))

        enabled = worktree_guard.WORKTREE_INPUT_CONTROLS - {
            "symlinked-run-directory"
        }
        with mock.patch.object(worktree_guard, "WORKTREE_INPUT_CONTROLS", enabled):
            self.assertEqual(self._in_process(), self._expected_result(0))

    def test_symlinked_journal_refusal_is_load_bearing(self) -> None:
        run_id = "run-symlinked-journal"
        run_dir = self.repo / ".codex-orchestrator" / "runs" / run_id
        run_dir.mkdir(parents=True)
        target = self.base / "symlinked-journal-target.jsonl"
        payload = json.dumps(
            self._opening(run_id, self.worktree),
            sort_keys=True,
            separators=(",", ":"),
        )
        target.write_text(payload + "\n", encoding="utf-8")
        journal_path = run_dir / "journal.jsonl"
        journal_path.symlink_to(target)

        with self.assertRaises(worktree_guard.WorktreeGuardError):
            worktree_guard._journal_paths(self.repo)

        enabled = worktree_guard.WORKTREE_INPUT_CONTROLS - {"symlinked-journal"}
        with mock.patch.object(worktree_guard, "WORKTREE_INPUT_CONTROLS", enabled):
            self.assertEqual(
                worktree_guard._journal_paths(self.repo), (journal_path,)
            )

    def test_journal_scan_error_fails_closed(self) -> None:
        runs_root = self.repo / ".codex-orchestrator" / "runs"
        runs_root.mkdir(parents=True)
        with mock.patch.object(
            worktree_guard.os,
            "scandir",
            side_effect=PermissionError("unreadable runs"),
        ):
            intact = self._in_process()
            with mock.patch.object(
                worktree_guard, "_runs_root_entries", return_value=()
            ):
                disabled = self._in_process()

        self.assertEqual(intact, self._expected_result(2))
        self.assertEqual(disabled, self._expected_result(0))

    def test_control_inventories_are_exact(self) -> None:
        self.assertEqual(
            worktree_guard.WORKTREE_GUARD_LEGS,
            frozenset({"recorded-repo", "cited-evidence"}),
        )
        self.assertEqual(
            worktree_guard.WORKTREE_INPUT_CONTROLS,
            frozenset(
                {
                    "symlinked-runs-root",
                    "symlinked-run-directory",
                    "symlinked-journal",
                }
            ),
        )

    def _assert_control_leg_is_load_bearing(
        self, leg: str, run_id: str, records: list[dict[str, object]]
    ) -> None:
        self._write_journal(run_id, records)
        self.assertEqual(self._in_process(), self._expected_result(1, run_id))
        enabled = worktree_guard.WORKTREE_GUARD_LEGS - {leg}
        with mock.patch.object(worktree_guard, "WORKTREE_GUARD_LEGS", enabled):
            self.assertEqual(self._in_process(), self._expected_result(0))

    def test_recorded_repo_control_leg_is_load_bearing(self) -> None:
        run_id = "run-disable-recorded-repo"
        self._assert_control_leg_is_load_bearing(
            "recorded-repo",
            run_id,
            [self._opening(run_id, self.worktree)],
        )

    def test_cited_evidence_control_leg_is_load_bearing(self) -> None:
        run_id = "run-disable-cited-evidence"
        self._assert_control_leg_is_load_bearing(
            "cited-evidence",
            run_id,
            self._cited_records(run_id),
        )


if __name__ == "__main__":
    unittest.main()
