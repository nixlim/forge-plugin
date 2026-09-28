"""Deleted touched test paths are skipped inputs, never sensor failures (GH#33).

A touched test path absent from the candidate prints one visible note and is not
assessed; a present input the sensor cannot read, and every absent label that is
not shaped like a git-derived deletion, still exits 2 with the exact FR-144
diagnostic and an empty stdout. Each changed control has a disable leg: a copy of
the sensor with that control removed in memory flips the outcome.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SENSOR = ROOT / "scripts/forge/check-test-quality.py"
FAILURE = "forge: test-quality check failed to execute\n"
SEED = "## go\nTest file patterns: `*_test.go`\nAssertion heuristic: literal: `t.Error`\n"
IS_ROOT = hasattr(os, "geteuid") and os.geteuid() == 0
# Strict UTF-8 child stdout keeps the non-UTF-8 disable leg locale-independent:
# under C.UTF-8 (the CI runner) or UTF-8 mode stdout defaults to surrogateescape.
STRICT_STDIO = {**os.environ, "PYTHONIOENCODING": "utf-8:strict"}

SKIP_ACTION = """                    output.append(DELETED_TEMPLATE.format(path=path_label))
                    continue
"""
LABEL_GUARD = 'path_label.isprintable() and not path_label.startswith(("-", "/"))'
PRINTABLE_GUARD = "path_label.isprintable() and "
SHAPE_GUARD = ' and not path_label.startswith(("-", "/"))'
ABSENCE_ERRORS = "except (FileNotFoundError, NotADirectoryError):"
DELETED_PROSE = "forge: deleted test path skipped: <path>"
NO_EVENT_PROSE = "emits no `assertion_*` event"


def normalize(text: str) -> str:
    return " ".join(text.split())


def extracted_deleted_template(source: str) -> str:
    match = re.search(r'^DELETED_TEMPLATE = "([^"]+)"$', source, flags=re.MULTILINE)
    if match is None:
        raise AssertionError("deleted-path template is missing")
    return match.group(1)


def assert_deleted_path_prose(
    commit: str, merge: str, sensor_source: str, *, template: str | None = None
) -> None:
    anchor = 'check-test-quality.py" -- <touched-test-path>...'
    end = "After preserving the sensor's primary result"
    sections = (
        normalize(commit).split(anchor, 1)[1].split(end, 1)[0],
        normalize(merge).split(anchor, 1)[1].split(end, 1)[0],
    )
    for section in sections:
        if section.count(f"`{DELETED_PROSE}`") != 1:
            raise AssertionError("deleted-path note must appear once in the sensor section")
        if section.count(NO_EVENT_PROSE) != 1:
            raise AssertionError("deleted-path note must suppress assertion events exactly once")
    actual_template = (
        template if template is not None else extracted_deleted_template(sensor_source)
    )
    if actual_template.format(path="<path>") != DELETED_PROSE:
        raise AssertionError("sensor and skill deletion notes differ")


def note(label: str) -> str:
    return f"forge: deleted test path skipped: {label}\n"


class DeletedTestPathTests(unittest.TestCase):
    def setUp(self) -> None:
        temp_dir = tempfile.TemporaryDirectory(prefix="forge-test-quality-deleted-")
        self.addCleanup(temp_dir.cleanup)
        self.scratch = Path(temp_dir.name)
        self.seed = self.scratch / "stacks.md"
        self.seed.write_text(SEED, encoding="utf-8")
        (self.scratch / "tests").mkdir()

    def write(self, relative_path: str, contents: str | bytes) -> str:
        path = self.scratch / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(contents, bytes):
            path.write_bytes(contents)
        else:
            path.write_text(contents, encoding="utf-8")
        return relative_path

    def mutant(self, needle: str, replacement: str) -> Path:
        source = SENSOR.read_text(encoding="utf-8")
        self.assertEqual(source.count(needle), 1, needle)
        mutant = self.scratch / "check-test-quality-disabled.py"
        mutant.write_text(source.replace(needle, replacement), encoding="utf-8")
        return mutant

    def run_sensor(
        self, *labels: str, sensor: Path = SENSOR, seed: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(sensor), "--stacks-file", str(seed or self.seed), "--", *labels],
            cwd=self.scratch,
            check=False,
            capture_output=True,
            text=True,
            env=STRICT_STDIO,
        )

    def assert_fails_closed(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual((result.returncode, result.stdout, result.stderr), (2, "", FAILURE))

    def test_deleted_path_is_a_visible_skip_not_a_failure(self) -> None:
        for label in ("tests/test_gone.py", "gone_test.go"):
            with self.subTest(label=label):
                result = self.run_sensor(label)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(result.stdout, note(label))
                self.assertEqual(result.stderr, "")

        disabled_sensor = self.mutant(SKIP_ACTION, "                    pass\n")
        self.assert_fails_closed(self.run_sensor("tests/test_gone.py", sensor=disabled_sensor))

    def test_note_is_not_parsed_as_an_assertion_disposition(self) -> None:
        # The commit engine (forge_cli/engine/_verbs_gate.py) maps sensor lines to
        # decision events by these markers; a deletion is not a quality finding.
        line = note("tests/test_gone.py")
        self.assertFalse(line.startswith("forge: assertion-free test detected:"))
        self.assertFalse(line.startswith("forge: assertion waiver:"))
        self.assertNotIn("advisory only", line)

    def test_deleted_paths_never_mask_present_findings(self) -> None:
        blocking = self.write("tests/test_bad.py", "def test_bad():\n    value = 1\n")
        clean = self.write("tests/test_ok.py", "def test_ok():\n    assert True\n")

        result = self.run_sensor("tests/test_gone.py", blocking, "gone_test.go", clean)

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(
            result.stdout,
            note("tests/test_gone.py")
            + note("gone_test.go")
            + f"forge: assertion-free test detected: {blocking}:1:test_bad\n",
        )
        self.assertEqual(result.stderr, "")

    def test_duplicate_deleted_label_is_noted_once(self) -> None:
        result = self.run_sensor("tests/test_gone.py", "tests/test_gone.py")
        self.assertEqual((result.returncode, result.stdout), (0, note("tests/test_gone.py")))

        disabled = self.run_sensor(
            "tests/test_gone.py",
            "tests/test_gone.py",
            sensor=self.mutant("dict.fromkeys(path_labels)", "path_labels"),
        )
        self.assertEqual(disabled.stdout, note("tests/test_gone.py") * 2)

    def test_directory_replaced_by_file_counts_as_deletion(self) -> None:
        self.write("tests/test_unit.py", "def test_unit():\n    assert True\n")
        label = "tests/test_unit.py/test_child.py"

        result = self.run_sensor(label)
        self.assertEqual((result.returncode, result.stdout), (0, note(label)))

        disabled = self.run_sensor(
            label, sensor=self.mutant(ABSENCE_ERRORS, "except FileNotFoundError:")
        )
        self.assert_fails_closed(disabled)

    def test_non_deletion_shaped_absent_labels_fail_closed(self) -> None:
        self.write("tests/test_ok.py", "def test_ok():\n    assert True\n")
        joined = "tests/test_ok.py\ntests/test_gone.py"  # zsh unsplit list (GH#18)
        # Disabled, each label is skipped (exit 0) except the non-UTF-8 one, whose
        # unguarded note cannot be encoded on strict stdout (traceback, exit 1).
        cases = (
            (PRINTABLE_GUARD, joined, 0),
            (PRINTABLE_GUARD, "tests/test\tgone.py", 0),
            (PRINTABLE_GUARD, "tests/test_\udce9.py", 1),
            (SHAPE_GUARD, "--stack", 0),
            (SHAPE_GUARD, str(self.scratch / "tests/test_gone.py"), 0),
        )
        for guard, label, disabled_exit in cases:
            with self.subTest(guard=guard, label=label):
                self.assert_fails_closed(self.run_sensor(label))
                disabled = self.run_sensor(label, sensor=self.mutant(guard, ""))
                self.assertEqual(disabled.returncode, disabled_exit, disabled.stderr)
                if disabled_exit == 0:
                    self.assertIn("forge: deleted test path skipped: ", disabled.stdout)
                else:
                    self.assertIn("UnicodeEncodeError", disabled.stderr)
        self.assertIn(LABEL_GUARD, SENSOR.read_text(encoding="utf-8"))

    def test_present_non_files_fail_closed(self) -> None:
        (self.scratch / "tests/test_dangling.py").symlink_to("nowhere.py")
        (self.scratch / "tests/loop_a").symlink_to("loop_b")
        (self.scratch / "tests/loop_b").symlink_to("loop_a")

        dangling = self.run_sensor("tests/test_dangling.py")
        self.assert_fails_closed(dangling)
        followed = self.run_sensor(
            "tests/test_dangling.py", sensor=self.mutant("path.lstat()", "path.stat()")
        )
        self.assertEqual(
            (followed.returncode, followed.stdout), (0, note("tests/test_dangling.py"))
        )

        looped = "tests/loop_a/test_x.py"
        self.assert_fails_closed(self.run_sensor(looped))
        widened = self.run_sensor(looped, sensor=self.mutant(ABSENCE_ERRORS, "except OSError:"))
        self.assertEqual((widened.returncode, widened.stdout), (0, note(looped)))

        self.assert_fails_closed(self.run_sensor("tests"))

    @unittest.skipIf(IS_ROOT, "root bypasses permission bits")
    def test_unreadable_present_inputs_fail_closed(self) -> None:
        # On Python 3.13 an unsearchable parent raises in Path.is_file() itself
        # (EACCES is not an ignored errno); where is_file() swallows it, the lstat in
        # the absence branch raises it instead. Either way these legs stay exit 2.
        unreadable = self.write("tests/test_locked.py", "def test_locked():\n    assert True\n")
        self.write("locked/test_inner.py", "def test_inner():\n    assert True\n")
        os.chmod(self.scratch / unreadable, 0)
        os.chmod(self.scratch / "locked", 0)
        self.addCleanup(os.chmod, self.scratch / "locked", 0o755)
        self.addCleanup(os.chmod, self.scratch / unreadable, 0o644)

        for labels in (
            (unreadable,),
            ("tests/test_gone.py", unreadable),
            ("locked/test_inner.py",),
            ("locked/test_missing.py",),
        ):
            with self.subTest(labels=labels):
                self.assert_fails_closed(self.run_sensor(*labels))

    def test_undecodable_present_file_and_broken_seed_still_fail_closed(self) -> None:
        undecodable = self.write("tests/broken_test.go", b"func TestX(t *T) { \xff }\n")

        self.assert_fails_closed(self.run_sensor("tests/test_gone.py", undecodable))
        self.assert_fails_closed(
            self.run_sensor("tests/test_gone.py", seed=self.scratch / "missing-stacks.md")
        )

    def test_skipped_deletion_prose_matches_sensor_without_events(self) -> None:
        commit = (ROOT / "skills/commit/SKILL.md").read_text(encoding="utf-8")
        merge = (ROOT / "skills/worktree-merge/SKILL.md").read_text(encoding="utf-8")
        sensor_source = SENSOR.read_text(encoding="utf-8")
        assert_deleted_path_prose(commit, merge, sensor_source)

        for label, original in (("commit", commit), ("merge", merge)):
            prose = normalize(original)
            for control in (f"`{DELETED_PROSE}`", NO_EVENT_PROSE):
                with self.subTest(skill=label, disabled=control):
                    self.assertEqual(prose.count(control), 1)
                    mutant = prose.replace(control, "DISABLED_CONTROL", 1)
                    args = (mutant, merge) if label == "commit" else (commit, mutant)
                    with self.assertRaises(AssertionError):
                        assert_deleted_path_prose(*args, sensor_source)

        template = extracted_deleted_template(sensor_source)
        with self.subTest(disabled="sensor template"), self.assertRaises(AssertionError):
            assert_deleted_path_prose(
                commit,
                merge,
                sensor_source,
                template=template.replace("deleted", "disabled", 1),
            )


if __name__ == "__main__":
    unittest.main()
