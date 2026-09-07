from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

from tests._cli_loader import package_module


CANDIDATE = package_module("candidate")
ENGINE = package_module("engine")


class CandidateIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.git("init", "-q")
        self.git("config", "user.email", "forge@example.invalid")
        self.git("config", "user.name", "Forge Test")
        (self.root / "tracked.txt").write_text("base\n", encoding="utf-8")
        self.git("add", "tracked.txt")
        self.git("commit", "-qm", "base")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def git(
        self, *arguments: str, env: dict[str, str] | None = None, check: bool = True
    ) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            ["git", *arguments],
            cwd=self.root,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=check,
        )

    def snapshot(self, *, environment: dict[str, str] | None = None):
        context = CANDIDATE.discover_context(self.root, environment=environment)
        return CANDIDATE.snapshot(
            context, computed_at="2026-09-07T12:00:00Z"
        )

    def test_v2_identity_is_domain_separated_tree_identity(self) -> None:
        (self.root / "tracked.txt").write_text("candidate\n", encoding="utf-8")
        self.git("add", "tracked.txt")

        snapshot = self.snapshot()

        expected = hashlib.sha256(
            b"forge-commit-candidate/2\0"
            + snapshot.object_format.encode("ascii")
            + b"\0"
            + snapshot.tree_oid.encode("ascii")
            + b"\n"
        ).hexdigest()
        self.assertEqual(snapshot.authorization_id, expected)
        self.assertEqual(snapshot.paths, ("tracked.txt",))
        self.assertEqual(snapshot.review_diff_sha256, hashlib.sha256(snapshot.review_diff).hexdigest())
        self.assertEqual(snapshot.review_diff_byte_count, len(snapshot.review_diff))
        record = snapshot.state_record()
        self.assertEqual(record["schema"], "forge-commit-candidate/2")
        self.assertEqual(record["sha256"], expected)
        self.assertEqual(record["authorization_id"], expected)

    def test_binary_review_patch_is_exact_and_separate_from_authorization(self) -> None:
        (self.root / "binary.bin").write_bytes(bytes(range(256)) * 8)
        self.git("add", "binary.bin")

        snapshot = self.snapshot()

        self.assertIn(b"GIT binary patch", snapshot.review_diff)
        self.assertNotEqual(snapshot.review_diff_sha256, snapshot.authorization_id)
        self.assertIn("binary.bin", snapshot.paths)

    def test_presentation_configuration_and_external_diff_do_not_change_snapshot(self) -> None:
        (self.root / "alpha.txt").write_text("alpha\n", encoding="utf-8")
        (self.root / "tracked.txt").write_text("changed\n", encoding="utf-8")
        self.git("add", "alpha.txt", "tracked.txt")
        baseline = self.snapshot()
        sentinel = self.root / "external-ran"
        helper = self.root / "external-diff.sh"
        helper.write_text(
            "#!/bin/sh\nprintf ran > \"$FORGE_EXTERNAL_SENTINEL\"\nexit 7\n",
            encoding="utf-8",
        )
        helper.chmod(0o700)
        order = self.root / "order"
        order.write_text("tracked.txt\nalpha.txt\n", encoding="utf-8")
        for key, value in (
            ("diff.ignoreSubmodules", "all"),
            ("diff.renames", "copies"),
            ("diff.algorithm", "histogram"),
            ("diff.suppressBlankEmpty", "true"),
            ("diff.orderFile", str(order)),
            ("color.ui", "always"),
            ("core.abbrev", "5"),
            ("diff.external", str(helper)),
        ):
            self.git("config", key, value)
        environment = os.environ.copy()
        environment.update(
            {
                "GIT_EXTERNAL_DIFF": str(helper),
                "FORGE_EXTERNAL_SENTINEL": str(sentinel),
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": "diff.context",
                "GIT_CONFIG_VALUE_0": "0",
                "GIT_PAGER": "false",
                "GIT_LITERAL_PATHSPECS": "1",
                "GIT_NOGLOB_PATHSPECS": "1",
                "GIT_ICASE_PATHSPECS": "1",
            }
        )

        configured = self.snapshot(environment=environment)

        self.assertEqual(configured.authorization_id, baseline.authorization_id)
        self.assertEqual(configured.paths, baseline.paths)
        self.assertEqual(configured.review_diff, baseline.review_diff)
        self.assertFalse(sentinel.exists())

    def test_live_and_info_attributes_cannot_change_immutable_review_patch(self) -> None:
        (self.root / "tracked.txt").write_text("changed\n", encoding="utf-8")
        self.git("add", "tracked.txt")
        baseline = self.snapshot()

        # Neither file is part of the candidate tree. Ordinary `git diff-tree`
        # nevertheless consults both, so this is a direct TOCTOU regression pin.
        (self.root / ".gitattributes").write_text("tracked.txt -diff\n", encoding="utf-8")
        (self.root / ".git" / "info" / "attributes").write_text(
            "tracked.txt diff=hostile\n", encoding="utf-8"
        )
        self.git("config", "diff.hostile.binary", "true")

        repeated = self.snapshot()

        self.assertEqual(repeated.authorization_id, baseline.authorization_id)
        self.assertEqual(repeated.paths, baseline.paths)
        self.assertEqual(repeated.review_diff, baseline.review_diff)

    def test_inter_hunk_context_cannot_change_immutable_review_patch(self) -> None:
        lines = [f"line {index}\n" for index in range(20)]
        (self.root / "tracked.txt").write_text("".join(lines), encoding="utf-8")
        self.git("add", "tracked.txt")
        self.git("commit", "-qm", "separated hunk base")
        lines[1] = "changed near start\n"
        lines[15] = "changed near end\n"
        (self.root / "tracked.txt").write_text("".join(lines), encoding="utf-8")
        self.git("add", "tracked.txt")
        baseline = self.snapshot()
        self.git("config", "diff.interHunkContext", "20")

        configured = self.snapshot()

        self.assertEqual(configured.authorization_id, baseline.authorization_id)
        self.assertEqual(configured.review_diff, baseline.review_diff)

    def test_shared_run_scope_path_contract_rejects_noncanonical_paths(self) -> None:
        for value in (
            "src/trailing ",
            " src/leading",
            "-option",
            ":(literal)path",
            "./relative",
            "src//file",
            "src/../file",
            ".forge/history/run.md",
            ".codex-orchestrator/runs/state",
            ".worktrees/other/file",
            "top*/file",
        ):
            with self.subTest(value=value):
                self.assertFalse(CANDIDATE.valid_scope_path(value))
        self.assertTrue(CANDIDATE.valid_scope_path("src/ordinary file.txt"))

    def test_run_bound_snapshot_install_rejects_actual_noncanonical_path(self) -> None:
        (self.root / "tracked.txt").write_text("candidate\n", encoding="utf-8")
        self.git("add", "tracked.txt")
        baseline = self.snapshot()
        hostile = dataclasses.replace(
            baseline,
            paths=("src/trailing ",),
            path_bytes=(b"src/trailing ",),
        )
        state = {
            "chain_id": "c-2026-09-07T120000Z-abcd",
            "run_binding": {"run_id": "run-bound"},
            "candidate": {},
            "paths": [],
            "staging": {"staged_paths": []},
        }

        with self.assertRaises(ENGINE.Refusal) as caught:
            ENGINE._install_candidate_snapshot(mock.Mock(), state, hostile)

        self.assertEqual(caught.exception.reason_code.value, "run-task-binding-invalid")
        self.assertEqual(state["candidate"], {})
        self.assertEqual(state["paths"], [])

    def test_global_diff_driver_cannot_change_candidate_tree_attributes(self) -> None:
        (self.root / "tracked.txt").write_text("changed\n", encoding="utf-8")
        (self.root / ".gitattributes").write_text(
            "tracked.txt diff=hostile\n", encoding="utf-8"
        )
        self.git("add", "tracked.txt", ".gitattributes")
        baseline = self.snapshot()
        fake_home = self.root / "fake-home"
        fake_home.mkdir()
        (fake_home / ".gitconfig").write_text(
            "[diff \"hostile\"]\n\tbinary = true\n"
            "[core]\n\tattributesFile = /dev/null\n",
            encoding="utf-8",
        )
        environment = os.environ.copy()
        environment["HOME"] = str(fake_home)
        environment["XDG_CONFIG_HOME"] = str(fake_home)

        configured = self.snapshot(environment=environment)

        self.assertEqual(configured.authorization_id, baseline.authorization_id)
        self.assertEqual(configured.review_diff, baseline.review_diff)

    def test_gitlink_transition_matrix_ignores_suppression_configuration(self) -> None:
        first_commit = self.git("rev-parse", "HEAD").stdout.decode("ascii").strip()
        tree = self.git("rev-parse", "HEAD^{tree}").stdout.decode("ascii").strip()
        second_commit = self.git(
            "commit-tree", tree, "-p", first_commit, "-m", "gitlink target"
        ).stdout.decode("ascii").strip()
        self.git("config", "diff.ignoreSubmodules", "all")
        self.git("config", "submodule.vendor.ignore", "all")
        environment = os.environ.copy()
        environment.update(
            {
                "GIT_CONFIG_COUNT": "2",
                "GIT_CONFIG_KEY_0": "diff.ignoreSubmodules",
                "GIT_CONFIG_VALUE_0": "all",
                "GIT_CONFIG_KEY_1": "submodule.vendor.ignore",
                "GIT_CONFIG_VALUE_1": "all",
            }
        )

        before = self.snapshot(environment=environment)
        self.git(
            "update-index", "--add", "--cacheinfo", f"160000,{first_commit},vendor"
        )
        added = self.snapshot(environment=environment)

        self.assertNotEqual(added.authorization_id, before.authorization_id)
        self.assertEqual(added.paths, ("vendor",))
        self.assertIn(first_commit.encode("ascii"), added.review_diff)

        self.git("commit", "-qm", "add gitlink")
        pre_existing = self.snapshot(environment=environment)
        self.assertEqual(pre_existing.paths, ())
        self.assertEqual(pre_existing.review_diff, b"")

        self.git(
            "update-index", "--cacheinfo", f"160000,{second_commit},vendor"
        )
        changed = self.snapshot(environment=environment)
        self.assertEqual(changed.paths, ("vendor",))
        self.assertIn(first_commit.encode("ascii"), changed.review_diff)
        self.assertIn(second_commit.encode("ascii"), changed.review_diff)

        self.git("commit", "-qm", "change gitlink")
        self.git("update-index", "--force-remove", "vendor")
        deleted = self.snapshot(environment=environment)

        self.assertEqual(deleted.paths, ("vendor",))
        self.assertIn(second_commit.encode("ascii"), deleted.review_diff)

    def test_sha256_repository_uses_full_tree_oid_in_domain_identity(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            subprocess.run(
                ["git", "init", "-q", "--object-format=sha256"],
                cwd=root,
                check=True,
            )
            subprocess.run(["git", "config", "user.name", "Forge"], cwd=root, check=True)
            subprocess.run(
                ["git", "config", "user.email", "forge@example.invalid"],
                cwd=root,
                check=True,
            )
            (root / "value").write_text("base\n", encoding="utf-8")
            subprocess.run(["git", "add", "value"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "base"], cwd=root, check=True)
            (root / "value").write_text("next\n", encoding="utf-8")
            subprocess.run(["git", "add", "value"], cwd=root, check=True)

            snapshot = CANDIDATE.snapshot(
                CANDIDATE.discover_context(root),
                computed_at="2026-09-07T12:00:00Z",
            )

        self.assertEqual(snapshot.object_format, "sha256")
        self.assertRegex(snapshot.tree_oid, r"^[0-9a-f]{64}$")
        self.assertEqual(
            snapshot.authorization_id,
            CANDIDATE.authorization_id("sha256", snapshot.tree_oid),
        )

    def test_unborn_head_uses_repository_format_empty_tree(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            (root / "first.txt").write_text("first\n", encoding="utf-8")
            subprocess.run(["git", "add", "first.txt"], cwd=root, check=True)
            context = CANDIDATE.discover_context(root)

            snapshot = CANDIDATE.snapshot(
                context, computed_at="2026-09-07T12:00:00Z"
            )
            expected_empty = subprocess.run(
                ["git", "mktree"],
                cwd=root,
                input=b"",
                check=True,
                stdout=subprocess.PIPE,
            ).stdout.decode("ascii").strip()

        self.assertIsNone(snapshot.base_commit_oid)
        self.assertEqual(snapshot.base_tree_oid, expected_empty)
        self.assertEqual(snapshot.paths, ("first.txt",))

    def test_corrupt_head_is_not_misclassified_as_unborn(self) -> None:
        context = CANDIDATE.discover_context(self.root)
        (context.git_dir / "HEAD").write_text("not-a-valid-head\n", encoding="ascii")

        with self.assertRaises(CANDIDATE.CandidateError) as caught:
            CANDIDATE.snapshot(
                context, computed_at="2026-09-07T12:00:00Z"
            )
        self.assertNotIn("empty tree", str(caught.exception))

    def test_raw_commit_reader_ignores_replacement_refs(self) -> None:
        head = self.git("rev-parse", "HEAD").stdout.decode().strip()
        tree = self.git("rev-parse", "HEAD^{tree}").stdout.decode().strip()
        replacement = self.git(
            "commit-tree", tree, "-m", "replacement message"
        ).stdout.decode().strip()
        self.git("replace", head, replacement)

        parsed = CANDIDATE.read_commit_object(
            CANDIDATE.discover_context(self.root), head
        )

        self.assertEqual(parsed.sha, head)
        self.assertEqual(parsed.message, b"base\n")

    def test_raw_commit_reader_rejects_malformed_structural_headers(self) -> None:
        self.git("commit", "--allow-empty", "-qm", "second")
        head = self.git("rev-parse", "HEAD").stdout.decode("ascii").strip()
        raw = self.git("cat-file", "commit", head).stdout
        header, message = raw.split(b"\n\n", 1)
        lines = header.splitlines()
        tree = next(line for line in lines if line.startswith(b"tree "))
        parent = next(line for line in lines if line.startswith(b"parent "))
        author = next(line for line in lines if line.startswith(b"author "))
        committer = next(line for line in lines if line.startswith(b"committer "))
        malformed = {
            "missing-separator": header,
            "missing-tree": b"\n".join((parent, author, committer)) + b"\n\n" + message,
            "duplicate-tree": b"\n".join((tree, tree, parent, author, committer)) + b"\n\n" + message,
            "malformed-tree": b"\n".join((b"tree xyz", parent, author, committer)) + b"\n\n" + message,
            "malformed-parent": b"\n".join((tree, b"parent xyz", author, committer)) + b"\n\n" + message,
            "illegal-header": b"\n".join((tree, parent, b"illegal", author, committer)) + b"\n\n" + message,
            "orphan-continuation": b"\n".join((b" continuation", tree, parent, author, committer)) + b"\n\n" + message,
            "tree-continuation": b"\n".join((tree, b" continuation", parent, author, committer)) + b"\n\n" + message,
            "nul-header": b"\n".join((tree, parent, b"x bad\x00value", author, committer)) + b"\n\n" + message,
            "cr-header": b"\n".join((tree, parent, b"x bad\rvalue", author, committer)) + b"\n\n" + message,
            "non-ascii-key": b"\n".join((tree, parent, b"x-\xff value", author, committer)) + b"\n\n" + message,
            "missing-author": b"\n".join((tree, parent, committer)) + b"\n\n" + message,
            "missing-committer": b"\n".join((tree, parent, author)) + b"\n\n" + message,
        }
        context = CANDIDATE.discover_context(self.root)

        for label, candidate_raw in malformed.items():
            written = subprocess.run(
                [
                    "git",
                    "hash-object",
                    "--literally",
                    "-t",
                    "commit",
                    "-w",
                    "--stdin",
                ],
                cwd=self.root,
                input=candidate_raw,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            ).stdout.decode("ascii").strip()
            with self.subTest(label=label):
                with self.assertRaisesRegex(
                    CANDIDATE.CandidateError, "produced commit"
                ):
                    CANDIDATE.read_commit_object(context, written)

    def test_raw_commit_reader_enforces_cap_and_raw_object_identity(self) -> None:
        context = CANDIDATE.discover_context(self.root)
        head = self.git("rev-parse", "HEAD").stdout.decode("ascii").strip()
        raw = self.git("cat-file", "commit", head).stdout

        with mock.patch.object(CANDIDATE, "COMMIT_OBJECT_MAX_BYTES", len(raw) - 1):
            with self.assertRaisesRegex(CANDIDATE.CandidateError, "byte ceiling"):
                CANDIDATE.read_commit_object(context, head)

        changed = raw.replace(b"base\n", b"mutant\n")
        with mock.patch.dict(
            CANDIDATE.CANDIDATE_CONTROLS,
            {"raw-produced-object-reading": lambda _context, _sha: changed},
        ):
            with self.assertRaisesRegex(CANDIDATE.CandidateError, "identity"):
                CANDIDATE.read_commit_object(context, head)

    def test_literal_tree_lookup_handles_pathspec_magic_filename(self) -> None:
        name = "literal[abc]*?.txt"
        (self.root / name).write_text("literal\n", encoding="utf-8")
        self.git("add", "--", name)
        snapshot = self.snapshot()
        context = CANDIDATE.discover_context(self.root)

        entry = CANDIDATE.tree_entry(context, snapshot.tree_oid, name)

        self.assertIsNotNone(entry)
        self.assertEqual(entry.path, name)
        self.assertEqual(CANDIDATE.tree_blob(context, snapshot.tree_oid, name), b"literal\n")

    def test_bounded_runner_kills_descendants_that_retain_output_pipes(self) -> None:
        started = time.monotonic()
        with self.assertRaisesRegex(CANDIDATE.CandidateError, "timed out"):
            CANDIDATE._run_bounded(
                [sys.executable, "-c", "import subprocess; subprocess.Popen(['sleep', '30'])"],
                cwd=self.root,
                env=os.environ.copy(),
                stdout_limit=32,
                timeout=0.1,
            )
        self.assertLess(time.monotonic() - started, 3.0)

    def test_bounded_runner_refuses_the_first_byte_beyond_ceiling(self) -> None:
        with self.assertRaisesRegex(CANDIDATE.CandidateError, "stdout exceeded"):
            CANDIDATE._run_bounded(
                [sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'x' * 33)"],
                cwd=self.root,
                env=os.environ.copy(),
                stdout_limit=32,
            )

    def test_tree_enumeration_rejects_empty_nul_records(self) -> None:
        context = CANDIDATE.discover_context(self.root)
        head_tree = self.git("rev-parse", "HEAD^{tree}").stdout.decode().strip()
        malformed = mock.Mock(return_value=mock.Mock(stdout=b"tracked.txt\0\0"))

        with mock.patch.object(CANDIDATE, "_git", malformed):
            with self.assertRaisesRegex(CANDIDATE.CandidateError, "malformed NUL"):
                CANDIDATE._enumerate_paths(context, head_tree, head_tree)

    def test_unmerged_index_fails_before_partial_snapshot(self) -> None:
        blob = self.git("hash-object", "-w", "tracked.txt").stdout.decode().strip()
        index_info = (
            f"100644 {blob} 1\ttracked.txt\n"
            f"100644 {blob} 2\ttracked.txt\n"
            f"100644 {blob} 3\ttracked.txt\n"
        ).encode()
        subprocess.run(
            ["git", "update-index", "--index-info"],
            cwd=self.root,
            input=index_info,
            check=True,
        )

        with self.assertRaisesRegex(CANDIDATE.CandidateError, "write-tree"):
            self.snapshot()

    def test_snapshot_never_changes_real_index_bytes(self) -> None:
        (self.root / "tracked.txt").write_text("candidate\n", encoding="utf-8")
        self.git("add", "tracked.txt")
        context = CANDIDATE.discover_context(self.root)
        before = context.index_file.read_bytes()

        snapshot = CANDIDATE.snapshot(
            context, computed_at="2026-09-07T12:00:00Z"
        )

        self.assertEqual(context.index_file.read_bytes(), before)
        self.assertEqual(snapshot.paths, ("tracked.txt",))

    def test_explicit_alternate_index_is_pinned_without_touching_main_index(self) -> None:
        main_context = CANDIDATE.discover_context(self.root)
        main_before = main_context.index_file.read_bytes()
        alternate = self.root / "forge-alternate.index"
        environment = os.environ.copy()
        environment["GIT_INDEX_FILE"] = str(alternate)
        self.git("read-tree", "HEAD", env=environment)
        (self.root / "tracked.txt").write_text("alternate candidate\n", encoding="utf-8")
        self.git("add", "tracked.txt", env=environment)

        alternate_context = CANDIDATE.discover_context(
            self.root, environment=environment
        )
        snapshot = CANDIDATE.snapshot(
            alternate_context, computed_at="2026-09-07T12:00:00Z"
        )

        self.assertEqual(alternate_context.index_file, alternate)
        self.assertEqual(snapshot.paths, ("tracked.txt",))
        self.assertEqual(main_context.index_file.read_bytes(), main_before)
        self.assertEqual(CANDIDATE.index_paths(main_context), ())

    def test_intent_to_add_is_not_mistaken_for_committable_tree_content(self) -> None:
        (self.root / "intent.txt").write_text("working bytes\n", encoding="utf-8")
        self.git("add", "--intent-to-add", "intent.txt")

        snapshot = self.snapshot()

        self.assertEqual(snapshot.paths, ())
        self.assertEqual(snapshot.review_diff, b"")

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink support is required")
    def test_tree_semantics_include_modes_symlinks_binary_empty_and_hostile_paths(self) -> None:
        (self.root / "gone.txt").write_text("remove me\n", encoding="utf-8")
        (self.root / "rename-old.txt").write_text("rename bytes\n", encoding="utf-8")
        self.git("add", "gone.txt", "rename-old.txt")
        self.git("commit", "-qm", "add deletion fixture")

        (self.root / "tracked.txt").write_text("mode only base\n", encoding="utf-8")
        self.git("add", "tracked.txt")
        self.git("commit", "-qm", "mode fixture")
        (self.root / "tracked.txt").chmod(0o755)
        (self.root / "gone.txt").unlink()
        (self.root / "rename-old.txt").rename(self.root / "rename-new.txt")
        (self.root / "empty.txt").write_bytes(b"")
        (self.root / "binary.bin").write_bytes(b"\x00\xff\x01candidate\n")
        os.symlink("tracked.txt", self.root / "linked")
        hostile = "space tab\tline\n.txt"
        (self.root / hostile).write_text("hostile\n", encoding="utf-8")
        self.git("add", "-A")

        snapshot = self.snapshot()

        expected = tuple(
            sorted(
                (
                    "binary.bin",
                    "empty.txt",
                    "gone.txt",
                    "linked",
                    "rename-new.txt",
                    "rename-old.txt",
                    hostile,
                    "tracked.txt",
                ),
                key=lambda value: value.encode("utf-8"),
            )
        )
        self.assertEqual(snapshot.paths, expected)
        self.assertIn(b"old mode 100644", snapshot.review_diff)
        self.assertIn(b"new mode 100755", snapshot.review_diff)
        self.assertIn(b"GIT binary patch", snapshot.review_diff)
        self.assertIn(b"tracked.txt", snapshot.review_diff)

    def test_linked_worktree_uses_its_own_pinned_index(self) -> None:
        with tempfile.TemporaryDirectory() as outer:
            linked = Path(outer) / "linked"
            self.git("worktree", "add", "-q", "-b", "candidate-linked", str(linked))
            (linked / "tracked.txt").write_text("linked candidate\n", encoding="utf-8")
            subprocess.run(["git", "add", "tracked.txt"], cwd=linked, check=True)

            context = CANDIDATE.discover_context(linked)
            snapshot = CANDIDATE.snapshot(
                context, computed_at="2026-09-07T12:00:00Z"
            )

            self.assertEqual(context.worktree_root, linked.resolve())
            self.assertNotEqual(context.index_file, CANDIDATE.discover_context(self.root).index_file)
            self.assertEqual(snapshot.paths, ("tracked.txt",))
            self.assertEqual(CANDIDATE.index_paths(CANDIDATE.discover_context(self.root)), ())

    def test_non_ascii_worktree_path_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as outer:
            root = Path(outer) / "répository"
            root.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Forge"], cwd=root, check=True)
            subprocess.run(
                ["git", "config", "user.email", "forge@example.invalid"],
                cwd=root,
                check=True,
            )
            (root / "value.txt").write_text("base\n", encoding="utf-8")
            subprocess.run(["git", "add", "value.txt"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "base"], cwd=root, check=True)
            (root / "value.txt").write_text("candidate\n", encoding="utf-8")
            subprocess.run(["git", "add", "value.txt"], cwd=root, check=True)

            snapshot = CANDIDATE.snapshot(
                CANDIDATE.discover_context(root),
                computed_at="2026-09-07T12:00:00Z",
            )

        self.assertEqual(snapshot.paths, ("value.txt",))

    def test_non_utf8_path_is_refused_without_replacement_decode(self) -> None:
        raw_root = os.fsencode(self.root)
        descriptor = os.open(raw_root + b"/bad-\xff.txt", os.O_WRONLY | os.O_CREAT, 0o600)
        os.write(descriptor, b"bad\n")
        os.close(descriptor)
        subprocess.run(
            [b"git", b"add", b"--", b"bad-\xff.txt"],
            cwd=raw_root,
            check=True,
        )

        with self.assertRaisesRegex(CANDIDATE.CandidateError, "not valid UTF-8"):
            self.snapshot()

    def test_candidate_control_registry_entries_are_independently_load_bearing(self) -> None:
        (self.root / "tracked.txt").write_text("candidate\n", encoding="utf-8")
        self.git("add", "tracked.txt")
        context = CANDIDATE.discover_context(self.root)
        baseline = CANDIDATE.snapshot(context, computed_at="2026-09-07T12:00:00Z")
        self.assertEqual(
            set(CANDIDATE.CANDIDATE_CONTROLS),
            {
                "pinned-index-tree",
                "config-proof-tree-enumeration",
                "deterministic-review-patch",
                "raw-produced-object-reading",
            },
        )
        for name in (
            "pinned-index-tree",
            "config-proof-tree-enumeration",
            "deterministic-review-patch",
        ):
            with self.subTest(name=name), mock.patch.dict(
                CANDIDATE.CANDIDATE_CONTROLS,
                {name: mock.Mock(side_effect=CANDIDATE.CandidateError(name))},
            ):
                with self.assertRaisesRegex(CANDIDATE.CandidateError, name):
                    CANDIDATE.snapshot(
                        context, computed_at="2026-09-07T12:00:00Z"
                    )
        snapshot_mutants = {
            "pinned-index-tree": lambda _context, _format: baseline.base_tree_oid,
            "config-proof-tree-enumeration": lambda _context, _base, _tree: ((), ()),
            "deterministic-review-patch": lambda _context, _base, _tree: b"",
        }
        for name, mutant in snapshot_mutants.items():
            with self.subTest(positive_control=name), mock.patch.dict(
                CANDIDATE.CANDIDATE_CONTROLS, {name: mutant}
            ):
                with self.assertRaises(AssertionError):
                    mutated = CANDIDATE.snapshot(
                        context, computed_at="2026-09-07T12:00:00Z"
                    )
                    self.assertEqual(mutated.authorization_id, baseline.authorization_id)
                    self.assertEqual(mutated.paths, baseline.paths)
                    self.assertEqual(mutated.review_diff, baseline.review_diff)
        head = self.git("rev-parse", "HEAD").stdout.decode().strip()
        self.assertEqual(CANDIDATE.read_commit_object(context, head).sha, head)
        with mock.patch.dict(
            CANDIDATE.CANDIDATE_CONTROLS,
            {
                "raw-produced-object-reading": mock.Mock(
                    side_effect=CANDIDATE.CandidateError("raw-produced-object-reading")
                )
            },
        ):
            with self.assertRaisesRegex(
                CANDIDATE.CandidateError, "raw-produced-object-reading"
            ):
                CANDIDATE.read_commit_object(context, head)
        original_reader = CANDIDATE.CANDIDATE_CONTROLS[
            "raw-produced-object-reading"
        ]
        old_raw = original_reader(context, head)
        self.git("commit", "-qm", "candidate commit")
        produced = self.git("rev-parse", "HEAD").stdout.decode().strip()
        with mock.patch.dict(
            CANDIDATE.CANDIDATE_CONTROLS,
            {"raw-produced-object-reading": lambda _context, _sha: old_raw},
        ):
            with self.assertRaisesRegex(CANDIDATE.CandidateError, "identity"):
                CANDIDATE.read_commit_object(context, produced)
        self.assertTrue(baseline.review_diff)

    def test_marker_grammar_is_exact_and_legacy_never_parses(self) -> None:
        (self.root / "tracked.txt").write_text("candidate\n", encoding="utf-8")
        self.git("add", "tracked.txt")
        observation = CANDIDATE.observe_index(CANDIDATE.discover_context(self.root))
        now = dt.datetime(2026, 9, 7, 12, 0, tzinfo=dt.timezone.utc)
        forms = (
            CANDIDATE.render_marker(observation, "2026-09-07T12:00:00Z"),
            CANDIDATE.render_marker(
                observation, "2026-09-07T12:00:00Z", skip=True
            ),
            CANDIDATE.render_marker(
                observation,
                "2026-09-07T12:00:00Z",
                fast_policy=self.git("rev-parse", "HEAD").stdout.decode().strip(),
            ),
        )
        self.assertEqual([raw.count(b"\n") for raw in forms], [4, 5, 6])
        for raw in forms:
            parsed, failure = CANDIDATE.parse_marker(
                raw,
                filename=observation.authorization_id,
                observation=observation,
                now=now,
            )
            self.assertIsNone(failure)
            self.assertEqual(parsed.authorization_id, observation.authorization_id)
        legacy = f"{observation.authorization_id}\n2026-09-07T12:00:00Z\n".encode()
        self.assertEqual(
            CANDIDATE.parse_marker(
                legacy,
                filename=observation.authorization_id,
                observation=observation,
                now=now,
            )[1],
            "marker malformed",
        )
        self.assertIsNotNone(CANDIDATE.marker_timestamp_for_cleanup(legacy))


if __name__ == "__main__":
    unittest.main()
