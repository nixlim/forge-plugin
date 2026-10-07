from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests._cli_loader import load_script, package_module


ROOT = Path(__file__).resolve().parents[1]
CLASSIFIER = ROOT / "scripts/forge/risk_tier.py"
package_module("candidate")
RISK_TIER = load_script("forge_risk_tier_tests", CLASSIFIER)
DEPENDENCIES = """package.json
package-lock.json
yarn.lock
pnpm-lock.yaml
requirements*.txt
pyproject.toml
poetry.lock
uv.lock
Cargo.toml
Cargo.lock
go.mod
go.sum
Gemfile
Gemfile.lock
pom.xml
build.gradle*
composer.json
composer.lock"""


def policy(
    *,
    tiers: str | None = None,
    triggers: str = "No trigger paths configured.",
    category_rows: tuple[tuple[str, str], ...] | None = None,
    fast_patterns: str | None = None,
) -> str:
    if fast_patterns is not None:
        tiers = f"""| tier | path patterns |
|---|---|
| fast | {fast_patterns} |
| standard | src/** |
| hard | security/** |"""
    tiers = tiers or """| tier | path patterns |
|---|---|
| fast | docs/**, .forge/history/**, .forge/evals/candidates/**, @formatting-only |
| standard | src/** |
| hard | security/** |"""
    return f"""<!-- FORGE:REGION file-categories BEGIN -->
| category | file patterns |
|---|---|
        {chr(10).join(f'| {category} | {patterns} |' for category, patterns in (category_rows or (("python", "*.py, src/**, pyproject.toml"), ("docs", "*.md, docs/**, .forge/evals/candidates/**"), ("yaml", "*.yml, *.yaml, pnpm-lock.yaml"), ("bash", "*.sh"), ("control", "forge-project.md, .forge-manifest, .forge/evals/tasks/**, .github/workflows/**"))))}
<!-- FORGE:REGION file-categories END -->
<!-- FORGE:REGION risk-tiers BEGIN -->
{tiers}

| formatting-only category |
|---|
| docs |
| python |
| yaml |

<!-- FORGE:DEPENDENCY-MANIFEST-PATHS BEGIN -->
{DEPENDENCIES}
<!-- FORGE:DEPENDENCY-MANIFEST-PATHS END -->
<!-- FORGE:REGION risk-tiers END -->
<!-- FORGE:REGION trigger-paths BEGIN -->
{triggers}
<!-- FORGE:REGION trigger-paths END -->
"""


class RiskTierTests(unittest.TestCase):
    def setUp(self) -> None:
        RISK_TIER._GIT_CONTEXT = None
        RISK_TIER._TREE_SOURCE = None
        self.tempdir = tempfile.TemporaryDirectory()
        self.repo = Path(self.tempdir.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Forge Test")
        self.git("config", "user.email", "forge@example.test")
        self.commit_policy(policy())

    def tearDown(self) -> None:
        RISK_TIER._GIT_CONTEXT = None
        RISK_TIER._TREE_SOURCE = None
        self.tempdir.cleanup()

    def git(self, *args: str) -> str:
        return subprocess.run(
            ["git", "-c", "commit.gpgsign=false", *args],
            cwd=self.repo, check=True, capture_output=True, text=True, timeout=15,
        ).stdout.strip()

    def commit_policy(
        self,
        contents: str | None = None,
        **policy_options: object,
    ) -> str:
        contents = contents if contents is not None else policy(**policy_options)
        (self.repo / "forge-project.md").write_text(contents, encoding="utf-8")
        (self.repo / ".forge-manifest").write_text("forge_version: 1\n", encoding="utf-8")
        self.git("add", "forge-project.md", ".forge-manifest")
        self.git("commit", "-qm", "policy")
        return self.git("rev-parse", "HEAD")

    def stage(self, path: str, contents: bytes) -> None:
        target = self.repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(contents)
        self.git("add", path)

    def commit_file(self, path: str, contents: bytes) -> None:
        self.stage(path, contents)
        self.git("commit", "-qm", f"add {path}")

    def classify(
        self,
        *,
        classifier: Path = CLASSIFIER,
        declared: str | None = None,
        require: str | None = None,
        sha: str | None = None,
        environment: dict[str, str] | None = None,
    ) -> tuple[subprocess.CompletedProcess[str], dict[str, object] | None]:
        command = [
            "python3", str(classifier), "--repo", str(self.repo), "--policy-sha",
            sha or self.git("rev-parse", "HEAD"), "--staged",
        ]
        if declared:
            command.extend(("--declared-tier", declared))
        if require:
            command.extend(("--require-effective", require))
        invocation_environment = os.environ.copy()
        invocation_environment["PYTHONPATH"] = os.pathsep.join(
            filter(
                None,
                (
                    str(ROOT / "scripts" / "forge"),
                    invocation_environment.get("PYTHONPATH", ""),
                ),
            )
        )
        if environment is not None:
            invocation_environment.update(environment)
        result = subprocess.run(
            command,
            cwd=self.repo,
            env=invocation_environment,
            capture_output=True,
            text=True,
        )
        return result, json.loads(result.stdout) if result.stdout else None

    def classify_range(
        self,
        base: str,
        head: str,
        *,
        declared: str = "standard",
        environment: dict[str, str] | None = None,
    ) -> tuple[subprocess.CompletedProcess[str], dict[str, object] | None]:
        invocation_environment = os.environ.copy()
        if environment is not None:
            invocation_environment.update(environment)
        result = subprocess.run(
            [
                "python3", str(CLASSIFIER), "--repo", str(self.repo),
                "--policy-sha", head, "--declared-tier", declared,
                "--range", f"{base}...{head}",
            ],
            cwd=self.repo,
            env=invocation_environment,
            capture_output=True,
            text=True,
        )
        return result, json.loads(result.stdout) if result.stdout else None

    def test_merge_range_cli_classifies_exact_committed_candidate(self) -> None:
        base = self.git("rev-parse", "HEAD")
        self.commit_file("docs/guide.md", b"guide\n")
        head = self.git("rev-parse", "HEAD")

        result, evidence = self.classify_range(base, head, declared="fast")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(evidence["policy_sha"], head)
        self.assertEqual(evidence["derived_tier"], "fast")
        self.assertEqual(evidence["effective_tier"], "fast")
        self.assertEqual([item["path"] for item in evidence["paths"]], ["docs/guide.md"])

    def test_committed_policy_lookup_ignores_replace_refs(self) -> None:
        policy_sha = self.git("rev-parse", "HEAD")
        replacement = self.commit_policy(
            policy(tiers="""| tier | path patterns |
|---|---|
| fast | misc/** |
| hard | docs/** |""")
        )
        self.git("reset", "--hard", "-q", policy_sha)
        self.git("replace", policy_sha, replacement)
        self.stage("docs/guide.md", b"guide\n")

        result, evidence = self.classify(sha=policy_sha, declared="fast")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(evidence["policy_sha"], policy_sha)
        self.assertEqual(evidence["derived_tier"], "fast")

    def test_supplied_candidate_base_must_match_live_head(self) -> None:
        policy_sha = self.git("rev-parse", "HEAD")
        base_tree = self.git("rev-parse", f"{policy_sha}^{{tree}}")
        unrelated_base = self.git("commit-tree", base_tree, "-m", "unrelated base")
        self.stage("docs/guide.md", b"guide\n")
        object_format = self.git("rev-parse", "--show-object-format")
        candidate_tree = self.git("write-tree")
        authorization_id = RISK_TIER.candidate_module.authorization_id(
            object_format, candidate_tree
        )
        candidate_environment = {
            "FORGE_CANDIDATE_SCHEMA": RISK_TIER.candidate_module.CANDIDATE_SCHEMA,
            "FORGE_CANDIDATE_AUTHORIZATION_ID": authorization_id,
            "FORGE_CANDIDATE_OBJECT_FORMAT": object_format,
            "FORGE_CANDIDATE_TREE_OID": candidate_tree,
            "FORGE_CANDIDATE_BASE_COMMIT_OID": unrelated_base,
        }

        result, evidence = self.classify(
            sha=policy_sha,
            declared="fast",
            environment=candidate_environment,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIsNone(evidence)
        self.assertIn("live index tree differs from supplied candidate", result.stderr)

        def assert_mismatched_base_is_refused() -> None:
            RISK_TIER._GIT_CONTEXT = None
            RISK_TIER._TREE_SOURCE = None
            with mock.patch.dict(os.environ, candidate_environment, clear=False):
                with self.assertRaisesRegex(
                    RISK_TIER.PolicyError,
                    "live index tree differs from supplied candidate",
                ):
                    RISK_TIER.staged_tree_source(self.repo)

        assert_mismatched_base_is_refused()
        with mock.patch.object(
            RISK_TIER, "supplied_candidate_matches", return_value=True
        ), self.assertRaises(AssertionError):
            assert_mismatched_base_is_refused()

    def test_range_pathspec_globals_and_injected_config_are_ignored(self) -> None:
        base = self.commit_policy(
            policy(tiers="""| tier | path patterns |
|---|---|
| fast | docs/** |
| hard | DOCS/** |""")
        )
        self.commit_file("docs/guide.md", b"guide\n")
        head = self.git("rev-parse", "HEAD")
        hostile_environment = {
            "GIT_LITERAL_PATHSPECS": "1",
            "GIT_GLOB_PATHSPECS": "1",
            "GIT_NOGLOB_PATHSPECS": "1",
            "GIT_ICASE_PATHSPECS": "1",
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "diff.ignoreSubmodules",
            "GIT_CONFIG_VALUE_0": "all",
        }

        result, evidence = self.classify_range(
            base,
            head,
            declared="fast",
            environment=hostile_environment,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(evidence["derived_tier"], "fast")
        self.assertEqual([item["path"] for item in evidence["paths"]], ["docs/guide.md"])

    def test_range_gitlink_ignores_submodule_suppression_config(self) -> None:
        policy_sha = self.commit_policy(fast_patterns="vendor")
        seed_tree = self.git("rev-parse", f"{policy_sha}^{{tree}}")
        first_gitlink = self.git("commit-tree", seed_tree, "-m", "first gitlink")
        second_gitlink = self.git(
            "commit-tree",
            seed_tree,
            "-p",
            first_gitlink,
            "-m",
            "second gitlink",
        )
        self.git(
            "update-index",
            "--add",
            "--cacheinfo",
            f"160000,{first_gitlink},vendor",
        )
        base_tree = self.git("write-tree")
        base = self.git("commit-tree", base_tree, "-p", policy_sha, "-m", "gitlink base")
        self.git("update-ref", "HEAD", base)
        self.git("config", "diff.ignoreSubmodules", "all")
        self.git("config", "submodule.vendor.ignore", "all")
        self.git(
            "update-index",
            "--cacheinfo",
            f"160000,{second_gitlink},vendor",
        )
        head_tree = self.git("write-tree")
        head = self.git("commit-tree", head_tree, "-p", base, "-m", "gitlink changed")
        self.git("update-ref", "HEAD", head)

        result, evidence = self.classify_range(base, head, declared="fast")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(evidence["derived_tier"], "fast")
        self.assertEqual([item["path"] for item in evidence["paths"]], ["vendor"])

    def test_malformed_name_status_output_fails_closed(self) -> None:
        source = RISK_TIER.TreeSource(
            context=mock.sentinel.context,
            base_tree_oid="a" * 40,
            candidate_tree_oid="b" * 40,
        )
        malformed = (
            b"Q\0docs/guide.md\0",
            b"M100\0docs/guide.md\0",
            b"U\0docs/guide.md\0",
            b"X\0docs/guide.md\0",
            b"B\0docs/guide.md\0",
            b"R1\0old.md\0new.md\0",
            b"C01\0old.md\0new.md\0",
            b"R101\0old.md\0new.md\0",
            b"R100\0old.md\0",
            b"M\0docs/guide.md",
            b"M\0docs/guide.md\0\0",
            b"M\0docs/guide.md\0A\0docs/guide.md\0",
            b"M\0bad-\xff.md\0",
        )
        for raw in malformed:
            with self.subTest(raw=raw), mock.patch.object(
                RISK_TIER, "diff_tree_source", return_value=source
            ), mock.patch.object(
                RISK_TIER.candidate_module,
                "name_status_tree_pair",
                return_value=raw,
            ), self.assertRaisesRegex(RISK_TIER.PolicyError, "malformed Git diff status"):
                RISK_TIER.diff_entries(self.repo, staged=False, range_spec="unused")

        def assert_unknown_status_is_refused() -> None:
            with mock.patch.object(
                RISK_TIER, "diff_tree_source", return_value=source
            ), mock.patch.object(
                RISK_TIER.candidate_module,
                "name_status_tree_pair",
                return_value=b"Q\0docs/guide.md\0",
            ), self.assertRaisesRegex(
                RISK_TIER.PolicyError, "malformed Git diff status"
            ):
                RISK_TIER.diff_entries(self.repo, staged=False, range_spec="unused")

        assert_unknown_status_is_refused()
        with mock.patch.object(
            RISK_TIER, "valid_tree_diff_status", return_value=True
        ), self.assertRaises(AssertionError):
            assert_unknown_status_is_refused()

    def test_sha256_git_repository_uses_full_policy_object_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            initialized = subprocess.run(
                ["git", "init", "-q", "--object-format=sha256", str(repo)],
                capture_output=True,
                text=True,
            )
            if initialized.returncode != 0:
                self.skipTest("installed Git does not support SHA-256 repositories")
            for key, value in (("user.name", "Forge Test"), ("user.email", "forge@example.test")):
                subprocess.run(["git", "config", key, value], cwd=repo, check=True)
            (repo / "forge-project.md").write_text(policy(), encoding="utf-8")
            (repo / ".forge-manifest").write_text("forge_version: 1\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", "forge-project.md", ".forge-manifest"], cwd=repo, check=True
            )
            subprocess.run(
                ["git", "-c", "commit.gpgsign=false", "commit", "-qm", "policy"],
                cwd=repo, check=True, timeout=15,
            )
            sha = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=repo, check=True,
                capture_output=True, text=True,
            ).stdout.strip()
            self.assertEqual(len(sha), 64)
            target = repo / "docs/guide.md"
            target.parent.mkdir(parents=True)
            target.write_text("guide\n", encoding="utf-8")
            subprocess.run(["git", "add", "docs/guide.md"], cwd=repo, check=True)

            result = subprocess.run(
                [
                    "python3", str(CLASSIFIER), "--repo", str(repo),
                    "--policy-sha", sha, "--staged", "--declared-tier", "fast",
                    "--require-effective", "fast",
                ],
                cwd=repo,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["policy_sha"], sha)

    def test_docs_fast_and_declared_hard_never_demotes(self) -> None:
        self.stage("docs/guide.md", b"guide\n")
        result, evidence = self.classify(declared="fast", require="fast")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(evidence["derived_tier"], "fast")
        self.assertEqual(evidence["effective_tier"], "fast")

        result, evidence = self.classify(declared="hard")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(evidence["derived_tier"], "fast")
        self.assertEqual(evidence["effective_tier"], "hard")

    def test_highest_match_wins_and_unmatched_defaults_standard(self) -> None:
        sha = self.commit_policy(policy(tiers="""| tier | path patterns |
|---|---|
| fast | docs/** |
| hard | docs/private/** |"""))
        self.stage("docs/private/secret.md", b"secret\n")
        result, evidence = self.classify(sha=sha)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(evidence["derived_tier"], "hard")

        self.git("reset", "--hard", "-q", sha)
        self.stage("misc/value.txt", b"value\n")
        result, evidence = self.classify(sha=sha)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(evidence["derived_tier"], "standard")

    def test_control_trigger_and_dependency_floors(self) -> None:
        cases = (
            ("AGENTS.md", "hard"),
            ("src/critical.py", "hard"),
            ("package.json", "standard"),
        )
        trigger_sha = self.commit_policy(policy(triggers="""| Path pattern |
|---|
| src/critical.py |"""))
        for path, expected in cases:
            with self.subTest(path=path):
                self.git("reset", "--hard", "-q", trigger_sha)
                self.stage(path, b"changed\n")
                result, evidence = self.classify(sha=trigger_sha)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(evidence["derived_tier"], expected)

    def test_git_pathspec_directory_prefix_and_immutable_dependency_block(self) -> None:
        narrowed = policy(
            tiers="""| tier | path patterns |
|---|---|
| fast | security/**, package-lock.json |
| standard | src/** |
| hard | forge-project.md |""",
            triggers="""| Path pattern |
|---|
| security |""",
        ).replace("package-lock.json\n", "")
        sha = self.commit_policy(narrowed)
        self.stage("security/nested/file.txt", b"sensitive\n")
        self.stage("package-lock.json", b"{}\n")
        _result, evidence = self.classify(sha=sha, declared="fast")
        by_path = {item["path"]: item for item in evidence["paths"]}
        self.assertEqual(by_path["security/nested/file.txt"]["path_tier"], "hard")
        self.assertEqual(by_path["package-lock.json"]["path_tier"], "standard")
        self.assertTrue(evidence["policy_malformed"])

        whitespace_changed = policy().replace("package.json\n", " package.json\n", 1)
        whitespace_sha = self.commit_policy(whitespace_changed)
        self.stage("docs/verbatim.md", b"docs\n")
        _result, whitespace_evidence = self.classify(sha=whitespace_sha)
        self.assertTrue(whitespace_evidence["policy_malformed"])
        self.assertEqual(whitespace_evidence["derived_tier"], "standard")

    def test_malformed_nonempty_trigger_makes_entire_diff_hard(self) -> None:
        sha = self.commit_policy(policy(triggers="not a table row"))
        self.stage("docs/guide.md", b"guide\n")
        result, evidence = self.classify(sha=sha)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(evidence["trigger_malformed"])

    def test_malformed_trigger_empty_diff_preserves_hard_floor(self) -> None:
        sha = self.commit_policy(policy(triggers="not a table row"))

        result, evidence = self.classify(sha=sha, require="hard")

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")
        self.assertEqual(evidence["paths"], [])
        self.assertTrue(evidence["trigger_malformed"])
        self.assertEqual(evidence["derived_tier"], "hard")
        self.assertEqual(evidence["effective_tier"], "hard")

    def test_unknown_detected_stack_manifest_is_never_fast(self) -> None:
        policy_sha = self.commit_policy(
            category_rows=(
                ("docs", "*.md, docs/**"),
                ("control", "forge-project.md"),
                ("custom-stack", "custom/**/*.custom"),
            ),
            fast_patterns="custom/**/*.custom",
        )
        self.stage("custom/probe.custom", b"version=1\n")
        _result, evidence = self.classify(sha=policy_sha)
        self.assertEqual(evidence["derived_tier"], "standard")
        self.assertTrue(evidence["dependency_decision"][0]["unknown_manifest"])

    def test_history_archive_is_docs_and_fast(self) -> None:
        policy_sha = self.commit_policy(
            category_rows=(
                ("docs", "*.md, docs/**, .forge/history/**"),
                ("control", "forge-project.md"),
            )
        )
        self.stage(".forge/history/runs/run-001.md", b"archive\n")

        result, evidence = self.classify(sha=policy_sha)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(evidence["derived_tier"], "fast")
        self.assertEqual(evidence["paths"][0]["categories"], ["docs"])

    def test_eval_tasks_are_control_but_candidates_are_advisory_fast(self) -> None:
        policy_sha = self.commit_policy(
            category_rows=(
                (
                    "docs",
                    "*.md, docs/**, .forge/history/**, .forge/evals/candidates/**",
                ),
                ("control", "forge-project.md, .forge/evals/**"),
            ),
            fast_patterns=(
                "docs/**, .forge/history/**, .forge/evals/candidates/**, "
                "@formatting-only"
            ),
        )
        self.stage(".forge/evals/tasks/task-fixture.md", b"task\n")
        self.stage(".forge/evals/tasks/task-fixture.result", b"PASS\n")

        result, evidence = self.classify(sha=policy_sha)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(evidence["derived_tier"], "hard")
        for item in evidence["paths"]:
            self.assertEqual(item["path_tier"], "hard")
            self.assertTrue(item["control_floor"])
            self.assertIn("control", item["categories"])

        self.git("reset", "--hard", "-q", policy_sha)
        candidate_path = ".forge/evals/candidates/proposed-fixture.md"
        self.stage(candidate_path, b"candidate\n")

        def assert_advisory(candidate_evidence: dict[str, object]) -> None:
            self.assertEqual(candidate_evidence["derived_tier"], "fast")
            self.assertEqual(candidate_evidence["effective_tier"], "fast")
            self.assertEqual(len(candidate_evidence["paths"]), 1)
            item = candidate_evidence["paths"][0]
            self.assertEqual(item["path"], candidate_path)
            self.assertEqual(item["categories"], ["docs"])
            self.assertEqual(item["path_tier"], "fast")
            self.assertFalse(item["control_floor"])

        result, evidence = self.classify(sha=policy_sha)
        self.assertEqual(result.returncode, 0, result.stderr)
        assert_advisory(evidence)

        source = CLASSIFIER.read_text(encoding="utf-8")
        control = "        eval_candidate = path in pattern_matches[EVAL_CANDIDATES]\n"
        self.assertEqual(source.count(control), 1)
        mutant = self.repo / "risk-tier-disabled-candidate-carveout.py"
        mutant.write_text(
            source.replace(control, "        eval_candidate = False\n"),
            encoding="utf-8",
        )

        mutant_result, mutant_evidence = self.classify(
            classifier=mutant,
            sha=policy_sha,
        )

        self.assertEqual(mutant_result.returncode, 0, mutant_result.stderr)
        with self.assertRaises(AssertionError):
            assert_advisory(mutant_evidence)

    def test_scripts_floor_is_hard_without_control_and_is_not_fast_eligible(self) -> None:
        sha = self.git("rev-parse", "HEAD")
        self.stage("scripts/tool.py", b"VALUE = 1\n")
        result, evidence = self.classify(sha=sha)
        self.assertEqual(result.returncode, 0, result.stderr)
        assert evidence is not None
        row = evidence["paths"][0]
        self.assertEqual(evidence["effective_tier"], "hard")
        self.assertFalse(row["control_floor"])
        self.assertTrue(row["review_final_floor"])
        self.assertTrue(row["strict_floor"])
        self.assertEqual(row["floor_matches"], [
            {"source": "builtin", "pattern": "scripts/**"},
        ])
        self.assertEqual(evidence["floor_matches"], [
            {"path": "scripts/tool.py", "source": "builtin", "pattern": "scripts/**"},
        ])
        denied, _payload = self.classify(sha=sha, require="fast")
        self.assertNotEqual(denied.returncode, 0)

        parsed = RISK_TIER.parse_policy(policy(), sha)
        entries = RISK_TIER.diff_entries(self.repo, staged=True, range_spec=None)
        with mock.patch.object(
            RISK_TIER, "BUILTIN_REVIEW_FINAL_FLOOR",
            tuple(pattern for pattern in RISK_TIER.BUILTIN_REVIEW_FINAL_FLOOR
                  if pattern != "scripts/**"),
        ):
            mutant = RISK_TIER.classify(
                self.repo, parsed, entries, staged=True, range_spec=None,
                declared_tier=None,
            )
        self.assertEqual(mutant["derived_tier"], "standard")
        self.assertFalse(mutant["paths"][0]["review_final_floor"])

    def test_route_config_is_builtin_control(self) -> None:
        self.stage("scripts/forge/route_config.py", b"ROUTES = {}\n")
        result, evidence = self.classify()
        self.assertEqual(result.returncode, 0, result.stderr)
        assert evidence is not None
        row = evidence["paths"][0]
        self.assertTrue(row["control_floor"])
        self.assertIn("control", row["categories"])
        self.assertIn(
            {"source": "builtin", "pattern": "scripts/forge/route_config.py"},
            row["floor_matches"],
        )

    def test_every_builtin_control_path_survives_project_omission(self) -> None:
        representatives = {
            "forge-project.md": "forge-project.md",
            ".forge-manifest": ".forge-manifest",
            "rules/**": "rules/review.md",
            "agents/**": "agents/reviewer.md",
            "system/**": "system/template.txt",
            "hooks/**": "hooks/guard.sh",
            "skills/**": "skills/commit/SKILL.md",
            ".claude-plugin/**": ".claude-plugin/plugin.json",
            ".codex/**": ".codex/config.toml",
            ".claude/settings*.json": ".claude/settings.local.json",
            ".github/workflows/**": ".github/workflows/check.yml",
            "AGENTS.md": "AGENTS.md",
            "CLAUDE.md": "CLAUDE.md",
            "docs/specs/**": "docs/specs/rules.md",
            ".forge/evals/tasks/**": ".forge/evals/tasks/check.json",
            ".refactor/type-baseline.json": ".refactor/type-baseline.json",
            "scripts/forge/route_config.py": "scripts/forge/route_config.py",
        }
        self.assertEqual(set(representatives), set(RISK_TIER.BUILTIN_CONTROL))
        sha = self.commit_policy(category_rows=(("control", "custom/only/**"),))
        for path in representatives.values():
            self.stage(path, b"changed\n")

        result, evidence = self.classify(sha=sha)
        self.assertEqual(result.returncode, 0, result.stderr)
        assert evidence is not None
        rows = {row["path"]: row for row in evidence["paths"]}
        for pattern, path in representatives.items():
            with self.subTest(pattern=pattern):
                self.assertTrue(rows[path]["control_floor"])
                self.assertTrue(rows[path]["review_final_floor"])
                self.assertIn("control", rows[path]["categories"])
                self.assertIn(
                    {"source": "builtin", "pattern": pattern},
                    rows[path]["floor_matches"],
                )

    def test_project_control_extension_has_floor_evidence(self) -> None:
        sha = self.commit_policy(category_rows=(
            ("docs", "*.md"),
            ("control", "forge-project.md, custom/policy.txt"),
        ))
        self.stage("custom/policy.txt", b"policy\n")
        result, evidence = self.classify(sha=sha)
        self.assertEqual(result.returncode, 0, result.stderr)
        assert evidence is not None
        row = evidence["paths"][0]
        self.assertTrue(row["control_floor"])
        self.assertEqual(row["floor_matches"], [
            {"source": "project-control", "pattern": "custom/policy.txt"},
        ])
        self.assertEqual(row["path_tier"], "hard")

    def test_consumer_scripts_control_extension_remains_authoritative(self) -> None:
        sha = self.commit_policy(category_rows=(
            ("python", "*.py"),
            ("control", "forge-project.md, scripts/**"),
        ))
        self.stage("scripts/ordinary.py", b"ordinary\n")
        result, evidence = self.classify(sha=sha)
        self.assertEqual(result.returncode, 0, result.stderr)
        assert evidence is not None
        row = evidence["paths"][0]
        self.assertTrue(row["control_floor"])
        self.assertIn(
            {"source": "project-control", "pattern": "scripts/**"},
            row["floor_matches"],
        )

    def test_fixture_floor_is_hard_without_control_in_dogfood_policy(self) -> None:
        sha = self.commit_policy((ROOT / "forge-project.md").read_text())
        self.stage("tests/fixtures/new.rules", b"allow\n")
        result, evidence = self.classify(sha=sha)
        self.assertEqual(result.returncode, 0, result.stderr)
        assert evidence is not None
        row = evidence["paths"][0]
        self.assertEqual(row["categories"], ["config"])
        self.assertFalse(row["control_floor"])
        self.assertTrue(row["strict_floor"])
        self.assertEqual(row["path_tier"], "hard")

    def test_project_trigger_and_hard_extensions_do_not_require_strict(self) -> None:
        sha = self.commit_policy(
            triggers="| path pattern |\n|---|\n| review/trigger.md |",
            tiers="| tier | path patterns |\n|---|---|\n| fast | docs/** |\n"
                  "| hard | review/hard.md |",
        )
        self.stage("review/trigger.md", b"trigger\n")
        self.stage("review/hard.md", b"hard\n")
        result, evidence = self.classify(sha=sha)
        self.assertEqual(result.returncode, 0, result.stderr)
        assert evidence is not None
        self.assertEqual(evidence["derived_tier"], "hard")
        rows = {row["path"]: row for row in evidence["paths"]}
        self.assertEqual(rows["review/trigger.md"]["floor_matches"], [
            {"source": "project-trigger", "pattern": "review/trigger.md"},
        ])
        self.assertEqual(rows["review/hard.md"]["floor_matches"], [
            {"source": "project-hard", "pattern": "review/hard.md"},
        ])
        self.assertFalse(rows["review/trigger.md"]["strict_floor"])
        self.assertFalse(rows["review/hard.md"]["strict_floor"])

    def test_project_fast_row_cannot_narrow_builtin_floor(self) -> None:
        sha = self.commit_policy(fast_patterns="scripts/**")
        self.stage("scripts/ordinary.py", b"ordinary\n")
        denied, evidence = self.classify(sha=sha, require="fast")
        self.assertNotEqual(denied.returncode, 0)
        assert evidence is not None
        self.assertEqual(evidence["effective_tier"], "hard")
        self.assertEqual(evidence["paths"][0]["matched_rows"], [
            {"tier": "fast", "pattern": "scripts/**"},
        ])

    def test_project_control_negation_is_refused(self) -> None:
        bad_row = "| control | forge-project.md, :!scripts/** |"
        original = policy(category_rows=(("control", "forge-project.md, :!scripts/**"),))
        self.assert_invalid_control_policy(original, bad_row)

    def assert_invalid_control_policy(self, corrupted: str, bad_row: str) -> None:
        sha = self.commit_policy(corrupted)
        self.stage("docs/guide.md", b"guide\n")
        result, evidence = self.classify(sha=sha)
        self.assertEqual(result.returncode, 2)
        self.assertIsNone(evidence)
        self.assertRegex(
            result.stderr,
            r"^forge: risk-tier classification failed: invalid path pattern "
            r"in file-categories row [0-9]+\n$",
        )
        self.assertNotIn(bad_row.strip(), result.stderr)
        self.stage("forge-project.md", policy().encode())
        repaired, evidence = self.classify(sha=sha)
        self.assertEqual(repaired.returncode, 2)
        self.assertIsNone(evidence)
        self.assertEqual(repaired.stderr, result.stderr)

    def test_earlier_malformed_row_cannot_hide_control_extension(self) -> None:
        source = policy()
        row = "| docs | *.md, docs/**, .forge/evals/candidates/** |"
        control = "| control | forge-project.md, .forge-manifest, .forge/evals/tasks/**, .github/workflows/** |"
        self.assert_invalid_control_policy(source.replace(row, row[:-1]), control)

    def test_comment_before_control_extension_is_refused(self) -> None:
        source = policy()
        control = "| control | forge-project.md, .forge-manifest, .forge/evals/tasks/**, .github/workflows/** |"
        self.assert_invalid_control_policy(source.replace(control, "<!-- boundary -->\n" + control), control)

    def test_blank_line_before_control_extension_is_refused(self) -> None:
        source = policy()
        control = "| control | forge-project.md, .forge-manifest, .forge/evals/tasks/**, .github/workflows/** |"
        self.assert_invalid_control_policy(source.replace(control, "\n" + control), control)

    def test_duplicate_category_header_is_refused(self) -> None:
        source = policy()
        header = "| category | file patterns |"
        control = "| control | forge-project.md, .forge-manifest, .forge/evals/tasks/**, .github/workflows/** |"
        self.assert_invalid_control_policy(source.replace(control, header + "\n" + control), header)

    def test_malformed_control_rows_are_refused_before_silent_drop(self) -> None:
        original = "| control | forge-project.md, .forge-manifest, .forge/evals/tasks/**, .github/workflows/** |"
        for malformed in (
            "| control |", "| control | |", "| control | rules/** | extra |",
            "| control | rules/**", "control | rules/** |",
        ):
            with self.subTest(malformed=malformed):
                corrupted = policy().replace(original, malformed)
                self.assertNotEqual(corrupted, policy())
                with self.assertRaisesRegex(RISK_TIER.PolicyError, "invalid path pattern"):
                    RISK_TIER.parse_policy(corrupted, "a" * 40)

    def test_unknown_stack_promotes_the_entire_docs_only_diff(self) -> None:
        policy_sha = self.commit_policy(
            category_rows=(
                ("docs", "*.md, docs/**"),
                ("elixir", "lib/**/*.ex, lib/**/*.exs"),
                ("control", "forge-project.md"),
            )
        )
        self.stage("docs/guide.md", b"guide\n")

        result, evidence = self.classify(sha=policy_sha)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(evidence["derived_tier"], "standard")
        self.assertEqual(evidence["paths"][0]["path_tier"], "fast")
        self.assertTrue(evidence["dependency_decision"][0]["unknown_manifest"])

    def test_category_name_does_not_control_manifest_membership(self) -> None:
        known_sha = self.commit_policy(
            category_rows=(
                ("docs", "*.md, docs/**"),
                ("py", "*.py, pyproject.toml"),
                ("control", "forge-project.md"),
            )
        )
        self.stage("docs/guide.md", b"guide\n")
        result, evidence = self.classify(sha=known_sha)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(evidence["derived_tier"], "fast")
        self.assertFalse(evidence["dependency_decision"][0]["unknown_manifest"])

        self.git("reset", "--hard", "-q", known_sha)
        unknown_sha = self.commit_policy(
            category_rows=(
                ("docs", "*.md, docs/**"),
                ("python", "*.py"),
                ("control", "forge-project.md"),
            )
        )
        self.stage("docs/guide.md", b"guide\n")
        result, evidence = self.classify(sha=unknown_sha)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(evidence["derived_tier"], "standard")
        self.assertTrue(evidence["dependency_decision"][0]["unknown_manifest"])

    def test_formatting_only_rejects_modified_symlink(self) -> None:
        target = self.repo / "notes.md"
        target.symlink_to("target ")
        self.git("add", "notes.md")
        self.git("commit", "-qm", "add symlink")
        target.unlink()
        target.symlink_to("target")
        self.git("add", "notes.md")
        policy_sha = self.git("rev-parse", "HEAD")
        _result, evidence = self.classify(sha=policy_sha, declared="fast")
        self.assertEqual(evidence["derived_tier"], "standard")
        self.assertEqual(
            evidence["formatting_decisions"][0]["reason"], "non-regular-file"
        )

    def test_formatting_only_trailing_space_and_line_endings_qualify(self) -> None:
        self.commit_file("notes.md", b"one  \r\ntwo\r\n")
        policy_sha = self.git("rev-parse", "HEAD")
        self.stage("notes.md", b"one\ntwo  \n")
        result, evidence = self.classify(sha=policy_sha, declared="fast")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(evidence["derived_tier"], "fast")
        self.assertTrue(evidence["formatting_decisions"][0]["eligible"])

    def test_formatting_only_rejects_mode_only_change(self) -> None:
        self.commit_file("notes.md", b"unchanged\n")
        policy_sha = self.git("rev-parse", "HEAD")
        (self.repo / "notes.md").chmod(0o755)
        self.git("add", "notes.md")

        result, evidence = self.classify(sha=policy_sha, declared="fast")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(evidence["derived_tier"], "standard")
        self.assertEqual(
            evidence["formatting_decisions"],
            [{"path": "notes.md", "eligible": False, "reason": "file-mode-changed"}],
        )

        def assert_mode_change_is_rejected() -> None:
            eligible, reason = RISK_TIER.formatting_only(
                self.repo,
                RISK_TIER.DiffEntry("M", "notes.md"),
                ["docs"],
                frozenset({"docs"}),
                staged=True,
                range_spec=None,
            )
            self.assertFalse(eligible)
            self.assertEqual(reason, "file-mode-changed")

        assert_mode_change_is_rejected()
        with mock.patch.object(
            RISK_TIER, "file_modes_match", return_value=True
        ), self.assertRaises(AssertionError):
            assert_mode_change_is_rejected()

    def test_formatting_only_rejects_python_yaml_leading_interior_and_add(self) -> None:
        fixtures = (
            ("script.py", b"  value\n", b"value\n"),
            ("config.yaml", b"  key: value\n", b"key: value\n"),
            ("notes.md", b"a b\n", b"a  b\n"),
        )
        for path, before, after in fixtures:
            with self.subTest(path=path):
                self.git("reset", "--hard", "-q")
                self.commit_file(path, before)
                policy_sha = self.git("rev-parse", "HEAD")
                self.stage(path, after)
                result, evidence = self.classify(sha=policy_sha)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(evidence["derived_tier"], "standard")
                self.assertFalse(evidence["formatting_decisions"][0]["eligible"])
                expected_reason = (
                    "excluded-category" if path.endswith((".py", ".yaml"))
                    else "semantic-bytes"
                )
                self.assertEqual(
                    evidence["formatting_decisions"][0]["reason"], expected_reason
                )

        self.git("reset", "--hard", "-q")
        self.stage("new-note.md", b"new  \n")
        result, evidence = self.classify()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(evidence["derived_tier"], "standard")
        self.assertFalse(evidence["formatting_decisions"][0]["eligible"])
        added_decision = next(
            item for item in evidence["formatting_decisions"] if item["path"] == "new-note.md"
        )
        self.assertFalse(added_decision["eligible"])
        self.assertEqual(added_decision["reason"], "status-A")

    def test_formatting_exclusion_floor_rejects_trailing_whitespace(self) -> None:
        cases = (
            ("python", "probe.py"),
            ("yaml", "probe.yaml"),
            ("make", "Makefile"),
            ("shell", "probe.shell"),
            ("bash", "probe.sh"),
            ("haskell", "probe.hs"),
            ("nim", "probe.nim"),
        )
        for category, path in cases:
            with self.subTest(category=category):
                self.git("reset", "--hard", "-q")
                policy_sha = self.commit_policy(
                    policy(
                        category_rows=(
                            (category, path),
                            ("docs", "*.md, docs/**"),
                            ("control", "forge-project.md"),
                        )
                    ).replace("| python |\n| yaml |", f"| python |\n| yaml |\n| {category} |")
                )
                self.commit_file(path, b"value\n")
                policy_sha = self.git("rev-parse", "HEAD")
                self.stage(path, b"value  \n")

                result, evidence = self.classify(sha=policy_sha)

                self.assertEqual(result.returncode, 0, result.stderr)
                decision = evidence["formatting_decisions"][0]
                self.assertFalse(decision["eligible"])
                self.assertEqual(decision["reason"], "excluded-category")

    def test_range_rejects_non_full_three_dot_commit_ids(self) -> None:
        sha = self.git("rev-parse", "HEAD")
        for range_spec in (f"{sha}..{sha}", "--cached", f"HEAD...{sha}"):
            with self.subTest(range_spec=range_spec):
                range_argument = (
                    f"--range={range_spec}" if range_spec.startswith("-") else range_spec
                )
                result = subprocess.run(
                    [
                        "python3", str(CLASSIFIER), "--repo", str(self.repo),
                        "--policy-sha", sha,
                        *(
                            (range_argument,)
                            if range_argument.startswith("--range=")
                            else ("--range", range_argument)
                        ),
                    ],
                    cwd=self.repo, capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 2)
                self.assertIn("--range must be two full lowercase hexadecimal", result.stderr)

    def test_committed_policy_isolation_and_require_effective(self) -> None:
        policy_sha = self.git("rev-parse", "HEAD")
        (self.repo / "forge-project.md").write_text(
            policy(tiers="""| tier | path patterns |
|---|---|
| fast | src/** |"""),
            encoding="utf-8",
        )
        self.stage("src/service.py", b"service\n")
        result, evidence = self.classify(sha=policy_sha, declared="fast", require="fast")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(evidence["effective_tier"], "standard")


if __name__ == "__main__":
    unittest.main()
