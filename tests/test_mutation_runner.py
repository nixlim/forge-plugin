from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "forge" / "run-scoped-mutation.py"


def policy_with_mutation(
    mutation_body: str,
    *,
    category_rows: tuple[str, ...] = ("| `python` | `*.py`, `pyproject.toml` |",),
) -> str:
    return f"""# Forge Project

<!-- FORGE:REGION file-categories BEGIN -->
| Category | File patterns |
|---|---|
{chr(10).join(category_rows)}
<!-- FORGE:REGION file-categories END -->

<!-- FORGE:REGION mutation-testing BEGIN -->
{mutation_body}
<!-- FORGE:REGION mutation-testing END -->
"""


def mutation_table(*rows: str, legacy_header: bool = False) -> str:
    header = (
        "| category | command | changed-files form |"
        if legacy_header
        else "| category | command | changed-files form | timeout |"
    )
    separator = "|---|---|---|" if legacy_header else "|---|---|---|---|"
    return "\n".join((header, separator, *rows))


class MutationRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.repo = Path(self.temporary_directory.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Forge Tests")
        self.git("config", "user.email", "forge-tests@example.invalid")
        self.git("config", "commit.gpgsign", "false")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def git(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *arguments],
            cwd=self.repo,
            check=True,
            capture_output=True,
            text=True,
        )

    def write(self, relative_path: str, contents: str) -> None:
        path = self.repo / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")

    def commit(self, message: str) -> str:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD").stdout.strip()

    def establish_candidate(
        self,
        mutation_body: str,
        *,
        category_rows: tuple[str, ...] = ("| `python` | `*.py`, `pyproject.toml` |",),
        initial_files: dict[str, str] | None = None,
        candidate_files: dict[str, str | None] | None = None,
    ) -> tuple[str, str]:
        self.write(
            "forge-project.md",
            policy_with_mutation(mutation_body, category_rows=category_rows),
        )
        for path, contents in (initial_files or {}).items():
            self.write(path, contents)
        base = self.commit("base policy")
        for path, contents in (candidate_files or {}).items():
            if contents is None:
                (self.repo / path).unlink()
            else:
                self.write(path, contents)
        head = self.commit("candidate")
        return base, head

    def invoke(
        self,
        base: str,
        head: str,
        *,
        environment: dict[str, str] | None = None,
        journal: Path | None = None,
        task: str = "task-04",
        timeout: float = 8,
    ) -> subprocess.CompletedProcess[str]:
        arguments = [
            "python3",
            str(RUNNER),
            "--base",
            base,
            "--head",
            head,
        ]
        if journal is not None:
            arguments.extend(("--journal", str(journal), "--task", task))
        return subprocess.run(
            arguments,
            cwd=self.repo,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
            env=environment,
        )

    def invoke_outside_repo(self) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as directory:
            return subprocess.run(
                [
                    "python3",
                    str(RUNNER),
                    "--base",
                    "0" * 40,
                    "--head",
                    "1" * 40,
                ],
                cwd=directory,
                capture_output=True,
                text=True,
                check=False,
            )

    def evidence(self, result: subprocess.CompletedProcess[str]) -> list[dict[str, object]]:
        return [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")]

    def test_scope_truth_table_passes_only_touched_tests_and_added_sources(self) -> None:
        argument_log = self.repo / "mutation-argv.json"
        changed_form = (
            "python3 -c 'import json,os,sys; "
            'open(os.environ["FORGE_ARG_LOG"],"w").write(json.dumps(sys.argv[1:]))\' "$@"'
        )
        base, head = self.establish_candidate(
            mutation_table(
                f"| python | mutmut run | {changed_form} | 9 |",
            ),
            initial_files={
                "src/modified.py": "old = 1\n",
                "src/deleted.py": "gone = True\n",
                "tests/test_modified.py": "def test_old():\n    assert True\n",
                "tests/test_deleted.py": "def test_gone():\n    assert True\n",
            },
            candidate_files={
                "src/modified.py": "new = 2\n",
                "src/deleted.py": None,
                "src/added.py": "added = True\n",
                "src/weird $(touch injected).py": "literal = True\n",
                "tests/test_modified.py": "def test_new():\n    assert 1 == 1\n",
                "tests/test_deleted.py": None,
                "tests/helper.py": "TEST_VALUE = 1\n",
            },
        )
        environment = {**os.environ, "FORGE_ARG_LOG": str(argument_log)}

        result = self.invoke(base, head, environment=environment)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        arguments = json.loads(argument_log.read_text(encoding="utf-8"))
        self.assertNotIn("tests/test_deleted.py", arguments)
        self.assertEqual(
            set(arguments),
            {
                "src/added.py",
                "src/weird $(touch injected).py",
                "tests/test_modified.py",
                "tests/helper.py",
            },
        )
        self.assertFalse((self.repo / "injected").exists())
        evidence = self.evidence(result)
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["criterion"], "mutation: python")
        self.assertEqual(evidence[0]["result"], "passed")
        self.assertEqual(evidence[0]["check"], changed_form)
        self.assertIn(
            "tool=mutmut run; scope=python; outcome=completed;", evidence[0]["observation"]
        )
        self.assertIn("timeout=9s", evidence[0]["observation"])
        self.assertNotIn("src/modified.py", evidence[0]["observation"])
        self.assertNotIn("src/deleted.py", evidence[0]["observation"])

    def test_deleted_test_alone_emits_no_live_scope_without_executing(self) -> None:
        marker = self.repo / "deleted-test-must-not-run"
        changed_form = "touch deleted-test-must-not-run"
        base, head = self.establish_candidate(
            mutation_table(f"| python | mutmut run | {changed_form} | 7 |"),
            initial_files={"tests/test_deleted.py": "def test_value():\n    assert True\n"},
            candidate_files={"tests/test_deleted.py": None},
        )
        journal = self.repo / "journal.jsonl"

        result = self.invoke(base, head, journal=journal)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertFalse(marker.exists())
        evidence = self.evidence(result)
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["criterion"], "mutation: python")
        self.assertEqual(evidence[0]["result"], "skipped")
        self.assertEqual(evidence[0]["check"], changed_form)
        self.assertEqual(
            evidence[0]["observation"],
            "tool=mutmut run; scope=python; outcome=no-live-scope; " "scoped_files=[]; timeout=7s",
        )
        verification = json.loads(journal.read_text(encoding="utf-8"))
        self.assertEqual(verification["criterion"], "mutation: python")
        self.assertEqual(verification["result"], "skipped")
        self.assertEqual(verification["check"], changed_form)
        self.assertEqual(verification["observation"], evidence[0]["observation"])

    def test_renamed_test_is_touched_but_renamed_source_is_not_added(self) -> None:
        argument_log = self.repo / "renamed-argv.json"
        changed_form = (
            "python3 -c 'import json,os,sys; "
            'open(os.environ["FORGE_ARG_LOG"],"w").write(json.dumps(sys.argv[1:]))\' "$@"'
        )
        self.write(
            "forge-project.md",
            policy_with_mutation(mutation_table(f"| python | mutmut run | {changed_form} | 5 |")),
        )
        self.write("tests/test_old.py", "def test_value():\n    assert True\n")
        self.write("src/old.py", "value = 1\n")
        base = self.commit("base policy")
        self.git("mv", "tests/test_old.py", "tests/test_new.py")
        self.git("mv", "src/old.py", "src/new.py")
        head = self.commit("rename files")

        result = self.invoke(
            base,
            head,
            environment={**os.environ, "FORGE_ARG_LOG": str(argument_log)},
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            json.loads(argument_log.read_text(encoding="utf-8")),
            ["tests/test_new.py"],
        )
        self.assertNotIn("src/new.py", self.evidence(result)[0]["observation"])

    def test_process_argv_contains_unchanged_cell_forge_and_literal_paths(self) -> None:
        changed_form = r'printf "%s\n" "$@" \| sed -n "p"'
        literal_path = "src/a $(touch injected).py"
        base, head = self.establish_candidate(
            mutation_table(f"| python | mutmut run | {changed_form} | 5 |"),
            candidate_files={literal_path: "value = 1\n"},
        )
        fake_bin = self.repo / "fake-bin"
        fake_bin.mkdir()
        argument_log = self.repo / "bash-arguments.json"
        wrapper = fake_bin / "bash"
        wrapper.write_text(
            "#!/bin/sh\n"
            "python3 -c 'import json,os,sys; "
            'open(os.environ["FORGE_ARG_LOG"],"w").write(json.dumps(sys.argv[1:]))\' '
            '"$@"\n',
            encoding="utf-8",
        )
        wrapper.chmod(0o755)
        environment = {
            **os.environ,
            "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
            "FORGE_ARG_LOG": str(argument_log),
        }

        result = self.invoke(base, head, environment=environment)

        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            json.loads(argument_log.read_text(encoding="utf-8")),
            ["-c", changed_form.replace(r"\|", "|"), "forge", literal_path],
        )
        self.assertFalse((self.repo / "injected").exists())

    def test_modified_source_without_a_test_change_does_not_execute(self) -> None:
        base, head = self.establish_candidate(
            mutation_table("| python | mutmut run | touch must-not-run | 5 |"),
            initial_files={"src/only.py": "old = 1\n"},
            candidate_files={"src/only.py": "new = 2\n"},
        )

        result = self.invoke(base, head)

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")
        self.assertFalse((self.repo / "must-not-run").exists())
        evidence = self.evidence(result)
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["criterion"], "mutation: policy")
        self.assertEqual(evidence[0]["result"], "skipped")
        self.assertEqual(evidence[0]["check"], "derive fixed candidate mutation scope")
        self.assertEqual(
            evidence[0]["observation"],
            "tool=mutation-testing policy; scope=policy; outcome=not-applicable; "
            'categories_evaluated=["python"]',
        )

    def test_dot_directory_patterns_keep_their_leading_dot(self) -> None:
        import runpy

        path_matches = runpy.run_path(str(RUNNER))["path_matches"]

        self.assertTrue(path_matches(".github/workflows/test_ci.yml", ".github/workflows/*.yml"))
        self.assertTrue(path_matches("./.github/workflows/test_ci.yml", ".github/workflows/*.yml"))
        self.assertFalse(path_matches("github/workflows/test_ci.yml", ".github/workflows/*.yml"))

    def test_added_source_classification_excludes_python_test_files(self) -> None:
        import runpy

        runner = runpy.run_path(str(RUNNER))
        change = runner["Change"]("A", "checks/test_helper.py")
        seeds = runner["parse_stack_seeds"](
            (ROOT / "system/seeds/validation-snippets/stacks.md").read_text(encoding="utf-8")
        )

        self.assertTrue(runner["is_test_path"](change.path, "python", seeds))
        self.assertFalse(runner["is_source_addition"](change, "python", seeds))
        self.assertNotIn("SOURCE_EXCLUSIONS_BY_CATEGORY", runner)

    def test_seed_test_pattern_takes_precedence_over_source_addition(self) -> None:
        base, head = self.establish_candidate(
            mutation_table("| python | mutmut run | true | 5 |"),
            candidate_files={"checks/test_helper.py": "def test_value():\n    assert True\n"},
        )

        result = self.invoke(base, head)

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")
        evidence = self.evidence(result)
        self.assertEqual(evidence[0]["criterion"], "mutation: python")
        self.assertIn('scoped_files=["checks/test_helper.py"]', evidence[0]["observation"])

    def test_unknown_category_uses_added_nonmanifest_path_as_source(self) -> None:
        base, head = self.establish_candidate(
            mutation_table("| custom | custom-mutator | printf '%s\\n' \"$@\" | 5 |"),
            category_rows=("| `custom` | `*.rb`, `Gemfile` |",),
            candidate_files={"lib/new.rb": "VALUE = 1\n", "Gemfile": "source 'x'\n"},
        )

        result = self.invoke(base, head)

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")
        evidence = self.evidence(result)
        self.assertEqual(evidence[0]["criterion"], "mutation: custom")
        self.assertIn('scoped_files=["lib/new.rb"]', evidence[0]["observation"])
        self.assertNotIn("Gemfile", evidence[0]["observation"])

    def test_committed_category_is_authoritative_for_unlisted_source_extension(self) -> None:
        base, head = self.establish_candidate(
            mutation_table("| scala | stryker4s run | true | 5 |"),
            category_rows=("| `scala` | `*.scala`, `build.sbt` |",),
            candidate_files={"src/main/App.scala": "object App {}\n"},
        )

        result = self.invoke(base, head)

        self.assertEqual(result.returncode, 0)
        evidence = self.evidence(result)
        self.assertEqual(evidence[0]["criterion"], "mutation: scala")
        self.assertIn('scoped_files=["src/main/App.scala"]', evidence[0]["observation"])

    def test_committed_patterns_can_extend_known_category_source_extensions(self) -> None:
        base, head = self.establish_candidate(
            mutation_table(
                "| npm | stryker run | true | 5 |",
                "| python | mutmut run | true | 5 |",
            ),
            category_rows=(
                "| `npm` | `*.mjs`, `*.vue`, `package.json` |",
                "| `python` | `*.pyx`, `pyproject.toml` |",
            ),
            candidate_files={
                "src/module.mjs": "export const value = 1;\n",
                "src/View.vue": "<template />\n",
                "src/extension.pyx": "value = 1\n",
            },
        )

        result = self.invoke(base, head)

        self.assertEqual(result.returncode, 0)
        evidence = self.evidence(result)
        self.assertEqual(
            [item["criterion"] for item in evidence], ["mutation: npm", "mutation: python"]
        )
        self.assertIn(
            'scoped_files=["src/View.vue","src/module.mjs"]',
            evidence[0]["observation"],
        )
        self.assertIn('scoped_files=["src/extension.pyx"]', evidence[1]["observation"])

    def test_merge_scope_never_executes_the_full_suite_command(self) -> None:
        base, head = self.establish_candidate(
            mutation_table(
                "| python | touch full-suite-must-not-run | true | 5 |",
            ),
            candidate_files={"src/new.py": "value = 1\n"},
        )

        result = self.invoke(base, head)

        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.evidence(result)[0]["result"], "passed")
        self.assertFalse((self.repo / "full-suite-must-not-run").exists())

    def test_applicable_declared_absence_is_journaled_as_ordinary_verification(self) -> None:
        journal = self.repo / "journal.jsonl"
        base, head = self.establish_candidate(
            "No mutation tool available for go — assertion-quality fallback only.",
            category_rows=("| `go` | `*.go`, `go.mod` |",),
            candidate_files={"pkg/new.go": "package pkg\n"},
        )

        result = self.invoke(base, head, journal=journal)

        self.assertEqual(result.returncode, 0)
        evidence = self.evidence(result)
        self.assertEqual(evidence[0]["criterion"], "mutation: go")
        self.assertEqual(evidence[0]["result"], "skipped")
        verification = json.loads(journal.read_text(encoding="utf-8"))
        self.assertEqual(verification["type"], "verification")
        self.assertEqual(verification["criterion"], "mutation: go")
        self.assertEqual(verification["result"], "skipped")
        self.assertEqual(
            verification["check"],
            "No mutation tool available for go — assertion-quality fallback only.",
        )
        self.assertIn("tool=none; scope=go; outcome=declared-absence", verification["observation"])
        self.assertIn('scoped_files=["pkg/new.go"]', verification["observation"])
        self.assertIn("timeout=not-applicable", verification["observation"])

    def test_declared_absence_with_missing_category_still_emits_and_journals_notice(self) -> None:
        journal = self.repo / "journal.jsonl"
        base, head = self.establish_candidate(
            "No mutation tool available for go — assertion-quality fallback only.",
            candidate_files={"README.md": "candidate\n"},
        )

        result = self.invoke(base, head, journal=journal)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        evidence = self.evidence(result)
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["criterion"], "mutation: go")
        self.assertEqual(evidence[0]["result"], "skipped")
        self.assertEqual(
            evidence[0]["check"],
            "No mutation tool available for go — assertion-quality fallback only.",
        )
        self.assertEqual(
            evidence[0]["observation"],
            "tool=none; scope=go; outcome=declared-absence; "
            "scoped_files=[]; timeout=not-applicable",
        )
        verification = json.loads(journal.read_text(encoding="utf-8"))
        self.assertEqual(verification["criterion"], evidence[0]["criterion"])
        self.assertEqual(verification["result"], evidence[0]["result"])
        self.assertEqual(verification["check"], evidence[0]["check"])
        self.assertEqual(verification["observation"], evidence[0]["observation"])

    def test_executable_row_and_mapped_declared_absence_are_malformed(self) -> None:
        marker = self.repo / "contradictory-row-must-not-run"
        body = "\n".join(
            (
                mutation_table(
                    "| java | pitest | touch contradictory-row-must-not-run | 5 |"
                ),
                "No mutation tool available for java-maven — assertion-quality fallback only.",
            )
        )
        base, head = self.establish_candidate(
            body,
            category_rows=("| `java` | `*.java`, `pom.xml` |",),
            candidate_files={"src/New.java": "class New {}\n"},
        )

        result = self.invoke(base, head)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout.splitlines()[0], "forge: executable policy row malformed")
        evidence = self.evidence(result)
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["criterion"], "mutation: policy")
        self.assertEqual(evidence[0]["result"], "skipped")
        self.assertEqual(evidence[0]["check"], "git show HEAD:forge-project.md (mutation-testing)")
        self.assertEqual(evidence[0]["diagnostic"], "forge: executable policy row malformed")
        self.assertEqual(
            evidence[0]["observation"],
            "tool=mutation-testing policy; scope=policy; outcome=malformed-skip; "
            "scoped_files=[]; timeout=not-applicable; "
            "diagnostic=forge: executable policy row malformed",
        )
        self.assertFalse(marker.exists())

    def test_nul_in_executable_cell_makes_the_whole_policy_malformed(self) -> None:
        import runpy

        parse_region = runpy.run_path(str(RUNNER))["parse_mutation_region"]
        nul_cell = "printf 'bad" + "\x00" + "cell'"
        policy = policy_with_mutation(mutation_table(f"| python | mutmut run | {nul_cell} | 5 |"))

        with self.assertRaisesRegex(RuntimeError, "forge: executable policy row malformed"):
            parse_region(policy)

    def test_missing_required_cells_and_extra_cells_remain_malformed(self) -> None:
        import runpy

        parse_region = runpy.run_path(str(RUNNER))["parse_mutation_region"]
        malformed_rows = (
            "|  | mutmut run | true | 5 |",
            "| python |  | true | 5 |",
            "| python | mutmut run |  | 5 |",
            "| python | mutmut run | true | 5 | extra |",
        )

        for row in malformed_rows:
            with self.subTest(row=row):
                with self.assertRaisesRegex(
                    RuntimeError, "^forge: executable policy row malformed$"
                ):
                    parse_region(policy_with_mutation(mutation_table(row)))

    def test_absence_sentence_closes_the_single_executable_table(self) -> None:
        import runpy

        parse_region = runpy.run_path(str(RUNNER))["parse_mutation_region"]
        body = "\n".join(
            (
                mutation_table("| python | mutmut run | true | 5 |"),
                "No mutation tool available for go — assertion-quality fallback only.",
                "| npm | stryker run | touch must-not-run | 5 |",
            )
        )

        with self.assertRaisesRegex(RuntimeError, "forge: executable policy row malformed"):
            parse_region(policy_with_mutation(body))

    def test_legacy_header_rejects_a_four_cell_row_without_executing(self) -> None:
        body = "\n".join(
            (
                "| category | command | changed-files form |",
                "|---|---|---|",
                "| python | full mutation | touch mixed-width-must-not-run | 5 |",
            )
        )
        base, head = self.establish_candidate(
            body,
            candidate_files={"src/new.py": "value = 1\n"},
        )

        result = self.invoke(base, head)

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.splitlines()[0], "forge: executable policy row malformed")
        self.assertEqual(self.evidence(result)[0]["result"], "skipped")
        self.assertFalse((self.repo / "mixed-width-must-not-run").exists())

    def test_modern_missing_timeout_cell_defaults_to_600_seconds(self) -> None:
        import runpy

        runner = runpy.run_path(str(RUNNER))
        body = mutation_table("| python | mutmut run | touch missing-timeout-defaulted |")
        parsed_rows, _ = runner["parse_mutation_region"](policy_with_mutation(body))
        self.assertEqual(parsed_rows[0].timeout, 600)
        marker = self.repo / "missing-timeout-defaulted"
        base, head = self.establish_candidate(
            body,
            candidate_files={"src/new.py": "value = 1\n"},
        )

        result = self.invoke(base, head)

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")
        evidence = self.evidence(result)
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["criterion"], "mutation: python")
        self.assertEqual(evidence[0]["result"], "passed")
        self.assertEqual(evidence[0]["check"], "touch missing-timeout-defaulted")
        self.assertEqual(
            evidence[0]["observation"],
            "tool=mutmut run; scope=python; outcome=completed; exit_code=0; "
            'timeout=600s; scoped_files=["src/new.py"]; output=',
        )
        self.assertTrue(marker.exists())

    def test_modified_rust_source_alone_does_not_trigger_as_a_test(self) -> None:
        base, head = self.establish_candidate(
            mutation_table("| rust | cargo mutants | touch must-not-run | 5 |"),
            category_rows=("| `rust` | `*.rs`, `Cargo.toml`, `Cargo.lock` |",),
            initial_files={"src/lib.rs": "pub fn old() {}\n"},
            candidate_files={"src/lib.rs": "pub fn new() {}\n"},
        )

        result = self.invoke(base, head)

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")
        self.assertFalse((self.repo / "must-not-run").exists())
        evidence = self.evidence(result)
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["criterion"], "mutation: policy")
        self.assertEqual(evidence[0]["result"], "skipped")
        self.assertEqual(evidence[0]["check"], "derive fixed candidate mutation scope")
        self.assertEqual(
            evidence[0]["observation"],
            "tool=mutation-testing policy; scope=policy; outcome=not-applicable; "
            'categories_evaluated=["rust"]',
        )

    def test_each_applicable_category_gets_only_its_own_scope(self) -> None:
        changed_form = (
            'python3 -c \'import json,os,sys; p=os.environ["FORGE_MULTI_LOG"]; '
            'open(p,"a").write(json.dumps(sys.argv[1:])+"\\n")\' "$@"'
        )
        base, head = self.establish_candidate(
            mutation_table(
                f"| python | mutmut run | {changed_form} | 5 |",
                f"| npm | stryker run | {changed_form} | 5 |",
            ),
            category_rows=(
                "| `python` | `*.py`, `pyproject.toml` |",
                "| `npm` | `*.js`, `package.json` |",
            ),
            candidate_files={
                "src/new.py": "python = True\n",
                "src/new.js": "const node = true;\n",
            },
        )
        log = self.repo / "multi-log"
        result = self.invoke(base, head, environment={**os.environ, "FORGE_MULTI_LOG": str(log)})

        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()],
            [["src/new.py"], ["src/new.js"]],
        )
        self.assertEqual(
            [(item["criterion"], item["result"]) for item in self.evidence(result)],
            [("mutation: python", "passed"), ("mutation: npm", "passed")],
        )

    def test_nonzero_result_is_journaled_but_runner_remains_advisory(self) -> None:
        changed_form = 'printf "survivors: 2\\n"; exit 7'
        base, head = self.establish_candidate(
            mutation_table(f"| python | mutmut run | {changed_form} | 12 |"),
            candidate_files={"src/new.py": "value = 1\n"},
        )
        journal = self.repo / "journal.jsonl"
        journal.write_text(
            json.dumps({"type": "task", "id": "task-04", "status": "complete"}) + "\n",
            encoding="utf-8",
        )

        result = self.invoke(base, head, journal=journal)

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")
        records = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
        verification = records[-1]
        self.assertEqual(verification["type"], "verification")
        self.assertEqual(verification["task"], "task-04")
        self.assertEqual(verification["criterion"], "mutation: python")
        self.assertFalse(verification["criterion"].startswith("gate-"))
        self.assertEqual(verification["method"], "command")
        self.assertEqual(verification["check"], changed_form)
        self.assertEqual(verification["result"], "failed")
        self.assertEqual(
            verification["observation"],
            "tool=mutmut run; scope=python; outcome=completed; exit_code=7; "
            'timeout=12s; scoped_files=["src/new.py"]; output=survivors: 2',
        )

    def test_journal_write_failure_keeps_all_rows_as_evidence_only(self) -> None:
        base, head = self.establish_candidate(
            mutation_table(
                "| python | mutmut run | true | 5 |",
                "| npm | stryker run | true | 7 |",
            ),
            category_rows=(
                "| `python` | `*.py` |",
                "| `npm` | `*.js` |",
            ),
            candidate_files={
                "src/new.py": "value = 1\n",
                "src/new.js": "const value = 1;\n",
            },
        )
        journal = self.repo / "unwritable-journal"
        journal.mkdir()

        result = self.invoke(base, head, journal=journal)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertNotIn("Traceback", result.stdout)
        self.assertEqual(
            self.evidence(result),
            [
                {
                    "type": "mutation_evidence",
                    "criterion": "mutation: python",
                    "result": "passed",
                    "check": "true",
                    "observation": (
                        "tool=mutmut run; scope=python; outcome=completed; exit_code=0; "
                        'timeout=5s; scoped_files=["src/new.py"]; output='
                    ),
                },
                {
                    "type": "mutation_evidence",
                    "criterion": "mutation: npm",
                    "result": "passed",
                    "check": "true",
                    "observation": (
                        "tool=stryker run; scope=npm; outcome=completed; exit_code=0; "
                        'timeout=7s; scoped_files=["src/new.js"]; output='
                    ),
                },
            ],
        )
        self.assertTrue(journal.is_dir())

    def test_launch_failure_is_inconclusive_and_runner_remains_advisory(self) -> None:
        base, head = self.establish_candidate(
            mutation_table("| python | mutmut run | true | 5 |"),
            candidate_files={"src/new.py": "value = 1\n"},
        )
        fake_bin = self.repo / "fake-path"
        fake_bin.mkdir()
        for executable in ("git", "python3"):
            source = shutil.which(executable)
            self.assertIsNotNone(source)
            os.symlink(source, fake_bin / executable)
        journal = self.repo / "journal.jsonl"

        result = self.invoke(
            base,
            head,
            environment={**os.environ, "PATH": str(fake_bin)},
            journal=journal,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        evidence = self.evidence(result)
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["criterion"], "mutation: python")
        self.assertEqual(evidence[0]["result"], "inconclusive")
        self.assertEqual(evidence[0]["check"], "true")
        self.assertEqual(
            evidence[0]["observation"],
            "tool=mutmut run; scope=python; outcome=launch-failed; exit_code=none; "
            'timeout=5s; scoped_files=["src/new.py"]; '
            "output=[Errno 2] No such file or directory: 'bash'",
        )
        verification = json.loads(journal.read_text(encoding="utf-8"))
        self.assertEqual(verification["result"], "inconclusive")
        self.assertEqual(verification["observation"], evidence[0]["observation"])

    def test_timeout_is_advisory_and_kills_the_complete_process_group(self) -> None:
        process_group_file = self.repo / "mutation-pgid"
        changed_form = (
            'python3 -c \'import os; open(os.environ["FORGE_PGID"], "w").write('
            "str(os.getpgrp()))'; sleep 30 & wait"
        )
        base, head = self.establish_candidate(
            mutation_table(f"| python | mutmut run | {changed_form} | 01 |"),
            candidate_files={"src/new.py": "value = 1\n"},
        )
        journal = self.repo / "journal.jsonl"

        started = time.monotonic()
        result = self.invoke(
            base,
            head,
            environment={**os.environ, "FORGE_PGID": str(process_group_file)},
            journal=journal,
        )
        elapsed = time.monotonic() - started

        # Keep this comfortably below the 30-second child while allowing for
        # temporary Git/process startup contention in the complete test suite.
        self.assertLess(elapsed, 8.0)
        self.assertEqual(result.returncode, 0)
        evidence = self.evidence(result)
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["result"], "inconclusive")
        self.assertIn("outcome=timed-out", evidence[0]["observation"])
        self.assertIn("timeout=1s", evidence[0]["observation"])
        verification = json.loads(journal.read_text(encoding="utf-8"))
        self.assertEqual(verification["criterion"], "mutation: python")
        self.assertFalse(verification["criterion"].startswith("gate-"))
        self.assertEqual(verification["check"], changed_form)
        self.assertEqual(verification["result"], "inconclusive")
        self.assertEqual(
            verification["observation"],
            "tool=mutmut run; scope=python; outcome=timed-out; exit_code=none; "
            'timeout=1s; scoped_files=["src/new.py"]; output=',
        )
        process_group = int(process_group_file.read_text(encoding="utf-8"))
        self.assertNotEqual(process_group, os.getpgrp())
        deadline = time.monotonic() + 1
        while True:
            try:
                os.killpg(process_group, 0)
            except ProcessLookupError:
                break
            if time.monotonic() >= deadline:
                self.fail(f"mutation process group {process_group} survived timeout")
            time.sleep(0.02)

    def test_normal_completion_kills_background_descendants_before_group_anchor_reap(self) -> None:
        process_group_file = self.repo / "completed-mutation-pgid"
        changed_form = (
            'python3 -c \'import os; open(os.environ["FORGE_PGID"], "w").write('
            "str(os.getpgrp()))'; sleep 30 &"
        )
        base, head = self.establish_candidate(
            mutation_table(f"| python | mutmut run | {changed_form} | 5 |"),
            candidate_files={"src/new.py": "value = 1\n"},
        )

        started = time.monotonic()
        result = self.invoke(
            base,
            head,
            environment={**os.environ, "FORGE_PGID": str(process_group_file)},
        )
        elapsed = time.monotonic() - started

        self.assertLess(elapsed, 4.0)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        evidence = self.evidence(result)
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["result"], "passed")
        self.assertEqual(
            evidence[0]["observation"],
            "tool=mutmut run; scope=python; outcome=completed; exit_code=0; "
            'timeout=5s; scoped_files=["src/new.py"]; output=',
        )
        process_group = int(process_group_file.read_text(encoding="utf-8"))
        self.assertNotEqual(process_group, os.getpgrp())
        deadline = time.monotonic() + 1
        while True:
            try:
                os.killpg(process_group, 0)
            except ProcessLookupError:
                break
            if time.monotonic() >= deadline:
                self.fail(f"mutation process group {process_group} survived normal completion")
            time.sleep(0.02)

    def test_legacy_missing_timeout_defaults_to_600_seconds(self) -> None:
        import runpy

        runner = runpy.run_path(str(RUNNER))
        parsed_rows, _ = runner["parse_mutation_region"](
            policy_with_mutation(
                mutation_table(
                    "| python | mutmut run | true |",
                    legacy_header=True,
                )
            )
        )
        self.assertEqual(parsed_rows[0].timeout, 600)
        base, head = self.establish_candidate(
            mutation_table(
                "| python | mutmut run | true |",
                legacy_header=True,
            ),
            candidate_files={"src/new.py": "value = 1\n"},
        )

        result = self.invoke(base, head)

        self.assertEqual(result.returncode, 0)
        evidence = self.evidence(result)
        self.assertEqual(evidence[0]["result"], "passed")
        self.assertIn("timeout=600s", evidence[0]["observation"])

    def test_modern_empty_timeout_cell_defaults_to_600_seconds(self) -> None:
        import runpy

        runner = runpy.run_path(str(RUNNER))
        body = mutation_table("| python | mutmut run | touch empty-timeout-defaulted |  |")
        parsed_rows, _ = runner["parse_mutation_region"](policy_with_mutation(body))
        self.assertEqual(parsed_rows[0].timeout, 600)
        marker = self.repo / "empty-timeout-defaulted"
        base, head = self.establish_candidate(
            body,
            candidate_files={"src/new.py": "value = 1\n"},
        )

        result = self.invoke(base, head)

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")
        evidence = self.evidence(result)
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["criterion"], "mutation: python")
        self.assertEqual(evidence[0]["result"], "passed")
        self.assertEqual(evidence[0]["check"], "touch empty-timeout-defaulted")
        self.assertEqual(
            evidence[0]["observation"],
            "tool=mutmut run; scope=python; outcome=completed; exit_code=0; "
            'timeout=600s; scoped_files=["src/new.py"]; output=',
        )
        self.assertTrue(marker.exists())

    def test_empty_timeout_row_preserves_other_rows_evidence(self) -> None:
        base, head = self.establish_candidate(
            mutation_table(
                "| python | mutmut run | true |  |",
                "| npm | stryker run | true | 7 |",
            ),
            category_rows=(
                "| `python` | `*.py` |",
                "| `npm` | `*.js` |",
            ),
            candidate_files={
                "src/new.py": "value = 1\n",
                "src/new.js": "const value = 1;\n",
            },
        )

        result = self.invoke(base, head)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(
            self.evidence(result),
            [
                {
                    "type": "mutation_evidence",
                    "criterion": "mutation: python",
                    "result": "passed",
                    "check": "true",
                    "observation": (
                        "tool=mutmut run; scope=python; outcome=completed; exit_code=0; "
                        'timeout=600s; scoped_files=["src/new.py"]; output='
                    ),
                },
                {
                    "type": "mutation_evidence",
                    "criterion": "mutation: npm",
                    "result": "passed",
                    "check": "true",
                    "observation": (
                        "tool=stryker run; scope=npm; outcome=completed; exit_code=0; "
                        'timeout=7s; scoped_files=["src/new.js"]; output='
                    ),
                },
            ],
        )

    def test_malformed_row_prints_exact_diagnostic_skips_all_rows_and_journals_skip(self) -> None:
        base, head = self.establish_candidate(
            mutation_table(
                "| python | mutmut run | touch must-not-run | 5 |",
                "| npm | stryker run | touch must-not-run-either | 10m |",
            ),
            category_rows=(
                "| `python` | `*.py` |",
                "| `npm` | `*.js` |",
            ),
            candidate_files={"src/new.py": "value = 1\n"},
        )
        journal = self.repo / "journal.jsonl"
        journal.touch()

        result = self.invoke(base, head, journal=journal)

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.splitlines()[0], "forge: executable policy row malformed")
        self.assertEqual(result.stderr, "")
        evidence = self.evidence(result)
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["diagnostic"], "forge: executable policy row malformed")
        self.assertFalse((self.repo / "must-not-run").exists())
        self.assertFalse((self.repo / "must-not-run-either").exists())
        verification = json.loads(journal.read_text(encoding="utf-8"))
        self.assertEqual(verification["type"], "verification")
        self.assertEqual(verification["criterion"], "mutation: policy")
        self.assertEqual(verification["result"], "skipped")
        self.assertEqual(verification["method"], "inspection")
        self.assertEqual(
            verification["observation"],
            "tool=mutation-testing policy; scope=policy; outcome=malformed-skip; "
            "scoped_files=[]; timeout=not-applicable; "
            "diagnostic=forge: executable policy row malformed",
        )

    def test_every_invalid_timeout_form_is_advisory_and_executes_no_row(self) -> None:
        for index, timeout in enumerate(("0", "-1", "abc", "10m", "１２")):
            with self.subTest(timeout=timeout):
                marker = f"must-not-run-{index}"
                base, head = self.establish_candidate(
                    mutation_table(f"| python | mutmut run | touch {marker} | {timeout} |"),
                    candidate_files={f"src/new-{index}.py": "value = 1\n"},
                )

                result = self.invoke(base, head)

                self.assertEqual(result.returncode, 0)
                self.assertEqual(
                    result.stdout.splitlines()[0],
                    "forge: executable policy row malformed",
                )
                self.assertEqual(result.stderr, "")
                self.assertEqual(self.evidence(result)[0]["result"], "skipped")
                self.assertFalse((self.repo / marker).exists())

    def test_policy_is_read_from_committed_head_not_working_tree(self) -> None:
        base, head = self.establish_candidate(
            mutation_table("| python | committed tool | touch committed-policy | 5 |"),
            candidate_files={"src/new.py": "value = 1\n"},
        )
        self.write(
            "forge-project.md",
            policy_with_mutation(
                mutation_table("| python | working tool | touch working-policy | 5 |")
            ),
        )

        result = self.invoke(base, head)

        self.assertEqual(result.returncode, 0)
        self.assertTrue((self.repo / "committed-policy").exists())
        self.assertFalse((self.repo / "working-policy").exists())
        evidence = self.evidence(result)
        self.assertEqual(evidence[0]["observation"].split(";", 1)[0], "tool=committed tool")

    def test_policy_absent_at_head_is_unavailable_not_malformed(self) -> None:
        self.write("README.md", "base\n")
        base = self.commit("base without policy")
        self.write("README.md", "candidate\n")
        head = self.commit("candidate without policy")

        result = self.invoke(base, head)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertNotIn("forge: executable policy row malformed", result.stdout)
        evidence = self.evidence(result)
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["criterion"], "mutation: policy")
        self.assertEqual(evidence[0]["result"], "inconclusive")
        self.assertEqual(evidence[0]["check"], "derive fixed candidate mutation scope")
        self.assertEqual(
            evidence[0]["observation"],
            "tool=mutation-testing policy; scope=policy; outcome=unavailable; "
            "diagnostic=forge: mutation policy absent at HEAD",
        )

    def test_outside_git_repo_emits_structured_unavailable_evidence(self) -> None:
        result = self.invoke_outside_repo()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(len(result.stdout.splitlines()), 1)
        self.assertEqual(
            json.loads(result.stdout),
            {
                "type": "mutation_evidence",
                "criterion": "mutation: policy",
                "result": "inconclusive",
                "check": "derive fixed candidate mutation scope",
                "observation": (
                    "tool=mutation-testing policy; scope=policy; outcome=unavailable; "
                    "diagnostic=forge: scoped mutation unavailable"
                ),
            },
        )

    def test_output_limit_breach_keeps_full_evidence_but_caps_journal_observation(self) -> None:
        changed_form = "python3 -c 'import sys; sys.stdout.write(\"x\" * 70000)'"
        base, head = self.establish_candidate(
            mutation_table(f"| python | mutmut run | {changed_form} | 5 |"),
            candidate_files={"src/new.py": "value = 1\n"},
        )
        journal = self.repo / "journal.jsonl"

        result = self.invoke(base, head, journal=journal)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        evidence = self.evidence(result)
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["result"], "inconclusive")
        self.assertIn("outcome=output-limit-exceeded", evidence[0]["observation"])
        observation = evidence[0]["observation"]
        self.assertEqual(len(observation.rsplit("output=", 1)[1].encode("utf-8")), 65_536)
        self.assertGreater(len(observation), 65_536)
        marker = "... [truncated for journal; full observation retained in mutation evidence]"
        verification = json.loads(journal.read_text(encoding="utf-8"))
        self.assertEqual(verification["criterion"], "mutation: python")
        self.assertEqual(verification["result"], "inconclusive")
        self.assertEqual(len(verification["observation"]), 2_000)
        self.assertTrue(verification["observation"].endswith(marker))
        self.assertEqual(
            verification["observation"][: 2_000 - len(marker)],
            observation[: 2_000 - len(marker)],
        )


if __name__ == "__main__":
    unittest.main()
