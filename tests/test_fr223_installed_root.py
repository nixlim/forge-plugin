from __future__ import annotations

import hashlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest import mock

from tests._cli_loader import load_script
from tests._git_env import init_quiet_repository

ROOT = Path(__file__).resolve().parents[1]
VERIFY_PATH = Path("scripts/forge/fr223_verify.py")
EVALUATOR_PATH = Path("scripts/forge/fr223_eval.py")
MANIFEST_PATH = Path(".forge/evals/tasks/fr223-phase0-v1.manifest.json")
EVIDENCE_PATH = Path(".forge/evals/tasks/fr223-bang-bypass-v1.evidence.json")
SPEC_PATH = Path("docs/specs/forge-plugin-spec.md")
REASON_CORPUS_PATH = Path("system/fr223/reason-codes-v1.json")
MANIFEST = json.loads((ROOT / MANIFEST_PATH).read_text(encoding="utf-8"))
ARTIFACT_PATHS = tuple(Path(entry["path"]) for entry in MANIFEST["artifacts"])
EXPECTED_LEGS = frozenset(
    {
        "root-mode",
        "regular-files",
        "manifest-digest",
        "evaluator-digest",
        "spec-utf8",
        "spec-manifest-pin",
        "evaluator-seam",
    }
)

VERIFY = load_script("forge_fr223_installed_root_tests", ROOT / VERIFY_PATH)


def git_index_mode(relative: Path) -> str:
    """Return the real or isolated-overlay index mode for ``relative``."""

    environment = VERIFY._git_environment()

    def indexed(env: dict[str, str]) -> bytes:
        return subprocess.run(
            ["git", "ls-files", "-s", "--", relative.as_posix()],
            cwd=ROOT,
            check=True,
            capture_output=True,
            env=env,
        ).stdout

    output = indexed(environment)
    if not output:
        with tempfile.TemporaryDirectory(prefix="forge-fr223-index-") as temporary:
            objects_text = subprocess.run(
                ["git", "rev-parse", "--git-path", "objects"],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
                env=environment,
            ).stdout.strip()
            objects = Path(objects_text)
            if not objects.is_absolute():
                objects = (ROOT / objects).resolve()
            scratch_objects = Path(temporary) / "objects"
            scratch_objects.mkdir()
            isolated = dict(environment)
            isolated["GIT_INDEX_FILE"] = str(Path(temporary) / "index")
            isolated["GIT_OBJECT_DIRECTORY"] = str(scratch_objects)
            isolated["GIT_ALTERNATE_OBJECT_DIRECTORIES"] = str(objects)
            subprocess.run(
                ["git", "read-tree", "HEAD"],
                cwd=ROOT,
                check=True,
                capture_output=True,
                env=isolated,
            )
            subprocess.run(
                ["git", "add", "--", relative.as_posix()],
                cwd=ROOT,
                check=True,
                capture_output=True,
                env=isolated,
            )
            output = indexed(isolated)
    fields = output.split()
    if len(fields) != 4 or fields[2] != b"0" or fields[3] != relative.as_posix().encode():
        raise AssertionError(f"unexpected git index entry for {relative}: {output!r}")
    return fields[0].decode("ascii")


def seed_installed_root(plugin_root: Path) -> None:
    """Copy exactly the shipped inputs needed by an installed-root verification."""

    paths = (*ARTIFACT_PATHS, MANIFEST_PATH, SPEC_PATH, VERIFY_PATH)
    for relative in paths:
        target = plugin_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)


def run_script(script: Path, plugin_root: Path) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [
            sys.executable,
            str(script),
            "verify",
            "--root",
            str(plugin_root),
        ],
        cwd=plugin_root,
        check=False,
        capture_output=True,
    )


def initialize_repository(repository: Path, *tracked: Path) -> None:
    environment = VERIFY._git_environment()
    initialized = init_quiet_repository(
        repository,
        "-q",
        environment=environment,
    )
    if initialized.returncode != 0:
        raise AssertionError(initialized.stderr)
    commands = (
        ("git", "add", "--", *(path.as_posix() for path in tracked)),
        (
            "git",
            "-c",
            "user.name=Forge Tests",
            "-c",
            "user.email=forge-tests@example.invalid",
            "commit",
            "-qm",
            "authority",
        ),
    )
    for command in commands:
        completed = subprocess.run(
            command,
            cwd=repository,
            check=False,
            capture_output=True,
            env=environment,
        )
        if completed.returncode != 0:
            raise AssertionError(completed.stderr.decode("utf-8", errors="replace"))


class InstalledRootVerificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="forge-fr223-installed-")
        self.addCleanup(self.temporary.cleanup)
        self.plugin_root = Path(self.temporary.name) / "plugin"
        self.plugin_root.mkdir()
        seed_installed_root(self.plugin_root)
        self.addCleanup(sys.modules.pop, VERIFY.EVALUATOR_MODULE, None)

    def _run_main(
        self,
        *disabled_legs: str,
    ) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        enabled = VERIFY.VERIFICATION_LEGS.difference(disabled_legs)
        with (
            mock.patch.object(VERIFY, "VERIFICATION_LEGS", frozenset(enabled)),
            mock.patch.multiple(sys, stdout=stdout, stderr=stderr),
        ):
            returncode = VERIFY.main(
                ("verify", "--root", str(self.plugin_root))
            )
        return returncode, stdout.getvalue(), stderr.getvalue()

    def _assert_passed(self, result: tuple[int, str, str]) -> None:
        returncode, stdout, stderr = result
        self.assertEqual(returncode, 0, stdout + stderr)
        self.assertIn("PASS FR-223 phase-0 package integrity", stdout)
        self.assertIn("PENDING FR-223(a)", stdout)
        self.assertNotIn("internal failure", stderr.lower())

    def _assert_refused(
        self,
        result: tuple[int, str, str],
        diagnostic: str,
    ) -> None:
        returncode, stdout, stderr = result
        self.assertEqual(returncode, 2, stdout + stderr)
        self.assertIn("forge: FR-223 verifier internal failure:", stderr)
        self.assertIn(diagnostic, stderr)

    def _assert_evaluator_refused(
        self,
        result: tuple[int, str, str],
        diagnostic: str,
    ) -> None:
        returncode, stdout, stderr = result
        self.assertEqual(returncode, 2, stdout + stderr)
        self.assertIn("forge: FR-223 evaluator internal failure:", stderr)
        self.assertIn(diagnostic, stderr)

    def _assert_seam_mutant_refused(
        self,
        module: ModuleType,
        diagnostic: str = "has no committed-spec seam",
    ) -> None:
        with mock.patch.object(VERIFY, "_load_evaluator", return_value=module):
            refused = self._run_main()
            bypassed = self._run_main("evaluator-seam")
        self._assert_refused(refused, diagnostic)
        returncode, stdout, stderr = bypassed
        self.assertEqual(returncode, 0, stdout + stderr)

    def test_fixture_and_declared_verification_legs_are_exact(self) -> None:
        self.assertIsInstance(VERIFY.VERIFICATION_LEGS, frozenset)
        self.assertEqual(VERIFY.VERIFICATION_LEGS, EXPECTED_LEGS)
        self.assertEqual(len(ARTIFACT_PATHS), 12)
        for relative in (*ARTIFACT_PATHS, MANIFEST_PATH, SPEC_PATH, VERIFY_PATH):
            with self.subTest(path=relative):
                self.assertTrue((self.plugin_root / relative).is_file())
        self.assertFalse((self.plugin_root / EVIDENCE_PATH).exists())
        self.assertEqual((ROOT / VERIFY_PATH).stat().st_mode & 0o111, 0)
        self.assertEqual((self.plugin_root / VERIFY_PATH).stat().st_mode & 0o111, 0)
        self.assertEqual(git_index_mode(VERIFY_PATH), "100644")

    def test_non_git_installed_root_passes_where_frozen_evaluator_fails(self) -> None:
        direct = run_script(self.plugin_root / EVALUATOR_PATH, self.plugin_root)
        wrapped = run_script(self.plugin_root / VERIFY_PATH, self.plugin_root)

        self.assertEqual(direct.returncode, 2, direct.stdout + direct.stderr)
        self.assertIn(b"cannot read committed HEAD spec", direct.stderr)
        self.assertEqual(wrapped.returncode, 0, wrapped.stdout + wrapped.stderr)
        self.assertIn(b"PASS FR-223 phase-0 package integrity", wrapped.stdout)
        self.assertIn(b"PENDING FR-223(a)", wrapped.stdout)
        self.assertNotIn(b"internal failure", wrapped.stderr.lower())

    def test_manifest_digest_rejects_harmless_byte_tamper(self) -> None:
        manifest = self.plugin_root / MANIFEST_PATH
        manifest.write_bytes(manifest.read_bytes() + b" ")

        self._assert_refused(self._run_main(), "does not match its DM-016 digest")
        self._assert_passed(self._run_main("manifest-digest"))

    def test_manifest_digest_rejects_consistently_reminted_package(self) -> None:
        corpus = self.plugin_root / REASON_CORPUS_PATH
        corpus.write_bytes(corpus.read_bytes() + b" ")
        manifest_path = self.plugin_root / MANIFEST_PATH
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        matching = [
            entry
            for entry in payload["artifacts"]
            if entry["path"] == REASON_CORPUS_PATH.as_posix()
        ]
        self.assertEqual(len(matching), 1)
        matching[0]["sha256"] = hashlib.sha256(corpus.read_bytes()).hexdigest()
        manifest_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        self._assert_refused(self._run_main(), "does not match its DM-016 digest")
        self._assert_passed(self._run_main("manifest-digest"))

    def test_frozen_evaluator_rejects_corpus_only_tamper(self) -> None:
        corpus = self.plugin_root / REASON_CORPUS_PATH
        corpus.write_bytes(corpus.read_bytes() + b" ")

        returncode, stdout, stderr = self._run_main()

        self.assertEqual(returncode, 1, stdout + stderr)
        self.assertIn("stale sha256 for system/fr223/reason-codes-v1.json", stdout)
        self.assertIn("FAIL FR-223 phase-0 package", stdout)
        self.assertNotIn("verifier internal failure", stderr.lower())

    def test_evaluator_digest_prevents_tampered_source_execution(self) -> None:
        evaluator = self.plugin_root / EVALUATOR_PATH
        original = evaluator.read_bytes()
        trusted_copy = self.plugin_root / "trusted-fr223-eval.py"
        trusted_copy.write_bytes(original)
        marker = self.plugin_root / "tampered-evaluator-executed"
        payload = (
            f"\nPath({str(marker)!r}).write_text('executed', encoding='utf-8')\n"
            f"Path(__file__).write_bytes(Path({str(trusted_copy)!r}).read_bytes())\n"
        ).encode()
        evaluator.write_bytes(original + payload)

        self._assert_refused(
            self._run_main(),
            "evaluator does not match its manifest digest",
        )
        self.assertFalse(marker.exists())
        self.assertNotEqual(evaluator.read_bytes(), original)

        self._assert_passed(self._run_main("evaluator-digest"))
        self.assertEqual(marker.read_text(encoding="utf-8"), "executed")
        self.assertEqual(evaluator.read_bytes(), original)

    def test_spec_manifest_pin_is_load_bearing(self) -> None:
        specification = self.plugin_root / SPEC_PATH
        lines = specification.read_text(encoding="utf-8").splitlines(keepends=True)
        pin = VERIFY.PINNED_MANIFEST_LINE
        matches = [line for line in lines if line.rstrip("\r\n") == pin]
        self.assertEqual(matches, [pin + "\n"])
        specification.write_text(
            "".join(line for line in lines if line.rstrip("\r\n") != pin),
            encoding="utf-8",
        )

        self._assert_evaluator_refused(
            self._run_main(),
            "lacks the DM-016 manifest digest line",
        )
        self._assert_passed(self._run_main("spec-manifest-pin"))

    def test_frozen_evaluator_rejects_corpus_relevant_spec_tamper(self) -> None:
        specification = self.plugin_root / SPEC_PATH
        source = specification.read_text(encoding="utf-8")
        authority = (
            "`approval-required` (control-class chain not yet operator-approved)"
        )
        tampered = (
            "`approval-required` (control-class chain is unexpectedly "
            "operator-approved)"
        )
        self.assertEqual(source.count(authority), 1)
        specification.write_text(source.replace(authority, tampered), encoding="utf-8")

        returncode, stdout, stderr = self._run_main()

        self.assertEqual(returncode, 1, stdout + stderr)
        self.assertIn(
            "entries do not exactly match committed FR-220",
            stdout,
        )
        self.assertIn("FAIL FR-223 phase-0 package", stdout)
        self.assertNotIn("verifier internal failure", stderr.lower())

    def test_regular_file_check_rejects_symlinked_specification(self) -> None:
        specification = self.plugin_root / SPEC_PATH
        target = self.plugin_root / "trusted-specification.md"
        target.write_bytes(specification.read_bytes())
        specification.unlink()
        specification.symlink_to(target)

        self._assert_evaluator_refused(
            self._run_main(),
            "specification is not a regular non-symlink file",
        )
        self._assert_passed(self._run_main("regular-files"))

    def test_strict_utf8_check_rejects_invalid_specification(self) -> None:
        specification = self.plugin_root / SPEC_PATH
        specification.write_bytes(specification.read_bytes() + b"\xff")

        self._assert_evaluator_refused(
            self._run_main(),
            "specification is not UTF-8",
        )
        self._assert_passed(self._run_main("spec-utf8"))

    def test_real_evaluator_uses_the_exact_supplied_bytes_and_active_seam(self) -> None:
        evaluator_path = self.plugin_root / EVALUATOR_PATH
        trusted_source = evaluator_path.read_bytes()
        evaluator_path.write_text(
            "raise RuntimeError('hostile on-disk replacement')\n",
            encoding="utf-8",
        )

        module = VERIFY._load_evaluator(evaluator_path, trusted_source)
        VERIFY._replace_committed_spec(module)

        self.assertTrue(callable(module.main))
        self.assertEqual(module.main.__code__.co_filename, str(evaluator_path))
        self.assertIs(
            module._package_issues.__globals__["_committed_spec"],
            module._committed_spec,
        )
        self.assertIn("_committed_spec", module._package_issues.__code__.co_names)
        self.assertIn("_package_issues", module._verify.__code__.co_names)
        self.assertEqual(
            module._committed_spec(self.plugin_root),
            (self.plugin_root / SPEC_PATH).read_text(encoding="utf-8"),
        )

    def test_evaluator_seam_identity_check_is_load_bearing(self) -> None:
        module = ModuleType("forge_fr223_foreign_seam")
        foreign_globals: dict[str, object] = {"_committed_spec": object()}
        exec(
            compile(
                "def foreign_package_issues(_root):\n"
                "    return [] if _committed_spec else []\n",
                "<foreign-fr223-seam>",
                "exec",
            ),
            foreign_globals,
        )

        def original_committed_spec(_root: Path) -> str:
            return "unused"

        module._committed_spec = original_committed_spec
        module._package_issues = foreign_globals["foreign_package_issues"]
        exec(
            compile(
                "def _verify(root):\n"
                "    return 1 if _package_issues(root) else 0\n",
                "<foreign-fr223-verify>",
                "exec",
            ),
            module.__dict__,
        )

        def fake_main(_argv: list[str]) -> int:
            return 0

        module.main = fake_main
        self._assert_seam_mutant_refused(
            module,
            "committed-spec seam is not active",
        )

    def test_evaluator_seam_rejects_direct_spec_reader(self) -> None:
        module = ModuleType("forge_fr223_direct_spec_reader")
        exec(
            compile(
                "def _committed_spec(_root):\n"
                "    return 'unused'\n"
                "def _package_issues(root):\n"
                f"    (root / {SPEC_PATH.as_posix()!r}).read_text(encoding='utf-8')\n"
                "    return []\n"
                "def _verify(root):\n"
                "    return 1 if _package_issues(root) else 0\n"
                "def main(_argv):\n"
                "    return 0\n",
                "<direct-fr223-spec-reader>",
                "exec",
            ),
            module.__dict__,
        )

        self._assert_seam_mutant_refused(module)

    def test_evaluator_seam_rejects_missing_committed_spec(self) -> None:
        module = ModuleType("forge_fr223_missing_committed_spec")
        exec(
            compile(
                "def _package_issues(root):\n"
                "    return [] if _committed_spec(root) else []\n"
                "def _verify(root):\n"
                "    return 1 if _package_issues(root) else 0\n"
                "def main(_argv):\n"
                "    return 0\n",
                "<missing-fr223-committed-spec>",
                "exec",
            ),
            module.__dict__,
        )

        self._assert_seam_mutant_refused(module)

    def test_evaluator_seam_rejects_bypassed_package_issues(self) -> None:
        module = ModuleType("forge_fr223_bypassed_package_issues")
        exec(
            compile(
                "def _committed_spec(_root):\n"
                "    return 'unused'\n"
                "def _package_issues(root):\n"
                "    return [] if _committed_spec(root) else []\n"
                "def _verify(_root):\n"
                "    return 0\n"
                "def main(_argv):\n"
                "    return 0\n",
                "<bypassed-fr223-package-issues>",
                "exec",
            ),
            module.__dict__,
        )

        self._assert_seam_mutant_refused(module)

    def test_broken_git_entry_refuses_and_root_mode_check_is_load_bearing(self) -> None:
        git_entry = self.plugin_root / ".git"
        git_entry.symlink_to(self.plugin_root / "missing-git-directory")
        self.assertTrue(git_entry.is_symlink())
        self.assertFalse(git_entry.exists())

        self._assert_refused(self._run_main(), "has an unusable .git entry")
        self._assert_passed(self._run_main("root-mode"))

    def test_nested_git_root_refuses_and_old_evaluator_would_use_outer_head(
        self,
    ) -> None:
        outer = Path(self.temporary.name)
        outer_specification = outer / SPEC_PATH
        outer_specification.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / SPEC_PATH, outer_specification)
        initialize_repository(outer, SPEC_PATH)

        direct = run_script(self.plugin_root / EVALUATOR_PATH, self.plugin_root)
        wrapped = run_script(self.plugin_root / VERIFY_PATH, self.plugin_root)

        self.assertEqual(direct.returncode, 0, direct.stdout + direct.stderr)
        self.assertIn(b"PASS FR-223 phase-0 package integrity", direct.stdout)
        self.assertEqual(wrapped.returncode, 2, wrapped.stdout + wrapped.stderr)
        self.assertIn(b"plugin root is nested in git work tree", wrapped.stderr)
        self._assert_passed(self._run_main("root-mode"))

    def test_git_top_level_is_byte_for_byte_the_historical_path(self) -> None:
        initialize_repository(self.plugin_root, SPEC_PATH)
        (self.plugin_root / SPEC_PATH).write_text(
            "uncommitted working specification must never be authority\n",
            encoding="utf-8",
        )

        direct = run_script(self.plugin_root / EVALUATOR_PATH, self.plugin_root)
        wrapped = run_script(self.plugin_root / VERIFY_PATH, self.plugin_root)

        self.assertEqual(direct.returncode, 0, direct.stdout + direct.stderr)
        self.assertEqual(
            (wrapped.returncode, wrapped.stdout, wrapped.stderr),
            (direct.returncode, direct.stdout, direct.stderr),
        )


if __name__ == "__main__":
    unittest.main()
