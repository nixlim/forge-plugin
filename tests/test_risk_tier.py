from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLASSIFIER = ROOT / "scripts/forge/risk_tier.py"
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
| fast | docs/**, .forge/history/**, @formatting-only |
| standard | src/** |
| hard | security/** |"""
    return f"""<!-- FORGE:REGION file-categories BEGIN -->
| category | file patterns |
|---|---|
        {chr(10).join(f'| {category} | {patterns} |' for category, patterns in (category_rows or (("python", "*.py, src/**, pyproject.toml"), ("docs", "*.md, docs/**"), ("yaml", "*.yml, *.yaml, pnpm-lock.yaml"), ("bash", "*.sh"), ("control", "forge-project.md, .forge-manifest, .github/workflows/**"))))}
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
        self.tempdir = tempfile.TemporaryDirectory()
        self.repo = Path(self.tempdir.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Forge Test")
        self.git("config", "user.email", "forge@example.test")
        self.commit_policy(policy())

    def tearDown(self) -> None:
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
        declared: str | None = None,
        require: str | None = None,
        sha: str | None = None,
    ) -> tuple[subprocess.CompletedProcess[str], dict[str, object] | None]:
        command = [
            "python3", str(CLASSIFIER), "--repo", str(self.repo), "--policy-sha",
            sha or self.git("rev-parse", "HEAD"), "--staged",
        ]
        if declared:
            command.extend(("--declared-tier", declared))
        if require:
            command.extend(("--require-effective", require))
        result = subprocess.run(command, cwd=self.repo, capture_output=True, text=True)
        return result, json.loads(result.stdout) if result.stdout else None

    def classify_range(
        self, base: str, head: str, *, declared: str = "standard"
    ) -> tuple[subprocess.CompletedProcess[str], dict[str, object] | None]:
        result = subprocess.run(
            [
                "python3", str(CLASSIFIER), "--repo", str(self.repo),
                "--policy-sha", head, "--declared-tier", declared,
                "--range", f"{base}...{head}",
            ],
            cwd=self.repo,
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
