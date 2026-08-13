from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMIT_GUARD = ROOT / "scripts" / "forge" / "commit-guard.sh"
MARKER_REASON = "forge: commit not authorized — run /forge:commit"
DEPENDENCY_PATHS = (
    "package.json",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "requirements*.txt",
    "pyproject.toml",
    "poetry.lock",
    "uv.lock",
    "Cargo.toml",
    "Cargo.lock",
    "go.mod",
    "go.sum",
    "Gemfile",
    "Gemfile.lock",
    "pom.xml",
    "build.gradle*",
    "composer.json",
    "composer.lock",
)


class CommitGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="forge-commit-guard-")
        self.addCleanup(self.temp_dir.cleanup)
        self.scratch = Path(self.temp_dir.name)
        self.repo = self.scratch / "main checkout"
        self.init_repo(self.repo)

    def init_repo(self, path: Path) -> None:
        subprocess.run(
            ["git", "init", "--quiet", str(path)],
            check=True,
            capture_output=True,
            text=True,
        )
        self.git("config", "user.name", "Forge Tests", cwd=path)
        self.git("config", "user.email", "forge-tests@example.invalid", cwd=path)
        self.git("symbolic-ref", "HEAD", "refs/heads/main", cwd=path)
        empty_tree = self.git("mktree", cwd=path, input_text="").stdout.strip()
        initial_commit = self.git(
            "commit-tree", empty_tree, cwd=path, input_text="scratch repository\n"
        ).stdout.strip()
        self.git("update-ref", "refs/heads/main", initial_commit, cwd=path)

    def git(
        self,
        *arguments: str,
        cwd: Path | None = None,
        input_text: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *arguments],
            cwd=cwd or self.repo,
            input=input_text,
            check=True,
            capture_output=True,
            text=True,
        )

    def invoke(
        self,
        command: str,
        *,
        cwd: Path | None = None,
        tool_name: str = "Bash",
        environment: dict[str, str] | None = None,
        guard: Path = COMMIT_GUARD,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(guard)],
            cwd=cwd or self.repo,
            input=json.dumps(
                {"tool_name": tool_name, "tool_input": {"command": command}}
            ),
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )

    def mutant_guard(self, name: str, needle: str, replacement: str) -> Path:
        mutant_root = self.scratch / name
        shutil.copytree(ROOT / "scripts" / "forge", mutant_root / "scripts" / "forge")
        guard = mutant_root / "scripts" / "forge" / "commit-guard.sh"
        source = guard.read_text(encoding="utf-8")
        self.assertEqual(source.count(needle), 1, needle)
        guard.write_text(source.replace(needle, replacement), encoding="utf-8")
        return guard

    def assert_allowed(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")

    def assert_denied(
        self,
        result: subprocess.CompletedProcess[str],
        reason: str,
    ) -> None:
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        expected = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }
        self.assertEqual(result.stdout, json.dumps(expected, ensure_ascii=False) + "\n")
        self.assertEqual(json.loads(result.stdout), expected)

    def track_manifest(self, *, cwd: Path | None = None) -> None:
        repo = cwd or self.repo
        (repo / ".forge-manifest").write_text(
            "forge_version: 1\nplugin_ref: test-plugin\ninit_completed: true\n",
            encoding="utf-8",
        )
        self.git("add", ".forge-manifest", cwd=repo)
        tree = self.git("write-tree", cwd=repo).stdout.strip()
        parent = self.git("rev-parse", "HEAD", cwd=repo).stdout.strip()
        commit = self.git(
            "commit-tree",
            tree,
            "-p",
            parent,
            cwd=repo,
            input_text="track forge manifest\n",
        ).stdout.strip()
        self.git("update-ref", "HEAD", commit, cwd=repo)

    def policy_text(
        self,
        *,
        fast_patterns: str = "docs/**, .forge/history/**, @formatting-only",
        triggers: str = "No trigger paths configured.",
    ) -> str:
        dependencies = "\n".join(DEPENDENCY_PATHS)
        return f"""# Forge policy
<!-- FORGE:REGION file-categories BEGIN -->
| Category | File patterns |
|---|---|
| `docs` | `*.md`, `docs/**` |
| `python` | `*.py`, `pyproject.toml` |
| `control` | `forge-project.md`, `.forge-manifest`, `.codex/**`, `.forge/evals/**`, `AGENTS.md`, `CLAUDE.md`, `.claude/settings*.json`, `.github/workflows/**` |
<!-- FORGE:REGION file-categories END -->
<!-- FORGE:REGION risk-tiers BEGIN -->
| tier | path patterns |
|---|---|
| fast | {fast_patterns} |
| standard | src/** |
| hard | forge-project.md |

| formatting-only category |
|---|
| docs |
<!-- FORGE:DEPENDENCY-MANIFEST-PATHS BEGIN -->
{dependencies}
<!-- FORGE:DEPENDENCY-MANIFEST-PATHS END -->
<!-- FORGE:REGION risk-tiers END -->
<!-- FORGE:REGION trigger-paths BEGIN -->
{triggers}
<!-- FORGE:REGION trigger-paths END -->
"""

    def commit_policy(
        self,
        *,
        fast_patterns: str = "docs/**, .forge/history/**, @formatting-only",
        triggers: str = "No trigger paths configured.",
        cwd: Path | None = None,
    ) -> str:
        repo = cwd or self.repo
        (repo / "forge-project.md").write_text(
            self.policy_text(fast_patterns=fast_patterns, triggers=triggers),
            encoding="utf-8",
        )
        (repo / ".forge-manifest").write_text(
            "forge_version: 1\nplugin_ref: test-plugin\ninit_completed: true\n",
            encoding="utf-8",
        )
        self.git("add", "forge-project.md", ".forge-manifest", cwd=repo)
        tree = self.git("write-tree", cwd=repo).stdout.strip()
        parent = self.git("rev-parse", "HEAD", cwd=repo).stdout.strip()
        commit = self.git(
            "commit-tree",
            tree,
            "-p",
            parent,
            cwd=repo,
            input_text="commit tier policy\n",
        ).stdout.strip()
        self.git("update-ref", "HEAD", commit, cwd=repo)
        return commit

    def stage_change(self, *, cwd: Path | None = None, name: str = "change.txt") -> None:
        repo = cwd or self.repo
        target = repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("reviewed change\n", encoding="utf-8")
        self.git("add", name, cwd=repo)

    def staged_hash(self, *, cwd: Path | None = None) -> str:
        result = subprocess.run(
            ["git", "diff", "--cached"],
            cwd=cwd or self.repo,
            check=True,
            capture_output=True,
        )
        return hashlib.sha256(result.stdout).hexdigest()

    def write_marker(
        self,
        *,
        cwd: Path | None = None,
        marker_root: Path | None = None,
        digest: str | None = None,
        timestamp: str | None = None,
        third_line: str | None = None,
        fourth_line: str | None = None,
    ) -> Path:
        root = marker_root or self.repo
        marker = root / ".forge" / "tmp" / "commit-authorized"
        marker.parent.mkdir(parents=True, exist_ok=True)
        reviewed_at = timestamp or datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        lines = [digest or self.staged_hash(cwd=cwd), reviewed_at]
        if third_line is not None:
            lines.append(third_line)
        if fourth_line is not None:
            lines.append(fourth_line)
        marker.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return marker

    def test_non_bash_and_irrelevant_bash_allow_silently(self) -> None:
        self.assert_allowed(self.invoke("git commit -m nope", tool_name="Read"))
        self.assert_allowed(self.invoke("printf '%s\\n' 'git commit'"))
        self.assert_allowed(self.invoke("bash -c 'git commit'"))

    def test_missing_stale_hash_mismatch_and_malformed_markers_are_denied(self) -> None:
        (self.repo / ".forge-manifest").write_text(
            "forge_version: 1\n", encoding="utf-8"
        )
        self.stage_change()
        marker = self.repo / ".forge" / "tmp" / "commit-authorized"
        stale_timestamp = (datetime.now(timezone.utc) - timedelta(minutes=31)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )

        cases: list[tuple[str, str | None]] = [
            ("missing", None),
            ("malformed", "not-a-marker\n"),
            (
                "stale",
                f"{self.staged_hash()}\n{stale_timestamp}\n",
            ),
            (
                "hash mismatch",
                f"{'0' * 64}\n{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}\n",
            ),
        ]
        for failure, contents in cases:
            with self.subTest(failure=failure):
                if contents is None:
                    marker.unlink(missing_ok=True)
                else:
                    marker.parent.mkdir(parents=True, exist_ok=True)
                    marker.write_text(contents, encoding="utf-8")
                self.assert_denied(
                    self.invoke("git commit -m guarded"),
                    f"{MARKER_REASON} (marker {failure})",
                )

        audit = self.repo / ".forge" / "tmp" / "halt-audit.log"
        self.assertEqual(stat.S_IMODE(audit.stat().st_mode), 0o600)
        self.assertEqual(len(audit.read_text(encoding="utf-8").splitlines()), 4)

    def test_only_exact_two_and_three_line_legacy_marker_shapes_are_accepted(self) -> None:
        (self.repo / ".forge-manifest").write_text("forge_version: 1\n")
        self.stage_change()

        self.write_marker()
        self.assert_allowed(self.invoke("git commit -m reviewed"))

        self.write_marker(third_line="skip: user-directed")
        self.assert_allowed(self.invoke("git commit -m user-directed"))

        for contents in (
            f"{self.staged_hash()}\n",
            f"{self.staged_hash()}\n2026-08-08T00:00:00Z\nunexpected\n",
            f"{self.staged_hash()}\n2026-08-08T00:00:00Z\nskip: user-directed\nextra\n",
            f"{'A' * 64}\n2026-08-08T00:00:00Z\n",
            f"{self.staged_hash()}\nnot-a-timestamp\n",
        ):
            with self.subTest(contents=contents):
                marker = self.repo / ".forge" / "tmp" / "commit-authorized"
                marker.write_text(contents, encoding="utf-8")
                self.assert_denied(
                    self.invoke("git commit"),
                    f"{MARKER_REASON} (marker malformed)",
                )

    def test_fast_marker_is_admitted_only_for_independently_eligible_diff(self) -> None:
        policy_sha = self.commit_policy()
        self.stage_change(name="docs/guide.md")
        self.write_marker(
            third_line="tier: fast",
            fourth_line=f"policy: {policy_sha}",
        )

        self.assert_allowed(self.invoke("git commit"))

    def test_fast_marker_permutations_and_malformed_annotations_are_denied(self) -> None:
        policy_sha = self.commit_policy()
        self.stage_change(name="docs/guide.md")
        digest = self.staged_hash()
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        malformed = (
            f"{digest}\n{timestamp}\npolicy: {policy_sha}\ntier: fast\n",
            f"{digest}\n{timestamp}\ntier: fast\npolicy: {policy_sha[:12]}\n",
            f"{digest}\n{timestamp}\ntier: fast\npolicy:{policy_sha}\n",
            f"{digest}\n{timestamp}\nskip: user-directed\ntier: fast\n",
            f"{digest}\n{timestamp}\ntier: fast\npolicy: {policy_sha}\nextra\n",
        )
        marker = self.repo / ".forge/tmp/commit-authorized"
        marker.parent.mkdir(parents=True, exist_ok=True)
        for contents in malformed:
            with self.subTest(contents=contents):
                marker.write_text(contents, encoding="utf-8")
                self.assert_denied(
                    self.invoke("git commit"),
                    f"{MARKER_REASON} (marker malformed)",
                )

    def test_fast_marker_policy_region_drift_is_denied_exactly(self) -> None:
        policy_sha = self.commit_policy()
        (self.repo / "forge-project.md").write_text(
            self.policy_text(fast_patterns="docs/private/**"), encoding="utf-8"
        )
        self.git("add", "forge-project.md")
        tree = self.git("write-tree").stdout.strip()
        descendant = self.git(
            "commit-tree",
            tree,
            "-p",
            policy_sha,
            input_text="narrow policy\n",
        ).stdout.strip()
        self.git("update-ref", "HEAD", descendant)
        self.stage_change(name="docs/guide.md")
        self.write_marker(
            third_line="tier: fast",
            fourth_line=f"policy: {policy_sha}",
        )

        self.assert_denied(
            self.invoke("git commit"),
            f"{MARKER_REASON} (fast-path policy drift)",
        )

    def test_each_complete_policy_region_is_independently_continuity_checked(self) -> None:
        mutations = (
            ("risk-tiers", {"fast_patterns": "docs/private/**"}),
            ("trigger-paths", {"triggers": "| src/** | security |"}),
            ("file-categories", {}),
        )
        for region, changes in mutations:
            with self.subTest(region=region):
                repo = self.scratch / f"{region} checkout"
                self.init_repo(repo)
                policy_sha = self.commit_policy(cwd=repo)
                updated = self.policy_text(**changes)
                if region == "file-categories":
                    updated = updated.replace(
                        "| `docs` | `*.md`, `docs/**` |",
                        "| `docs` | `*.md`, `docs/**`, `guides/**` |",
                    )
                (repo / "forge-project.md").write_text(updated, encoding="utf-8")
                self.git("add", "forge-project.md", cwd=repo)
                tree = self.git("write-tree", cwd=repo).stdout.strip()
                descendant = self.git(
                    "commit-tree",
                    tree,
                    "-p",
                    policy_sha,
                    cwd=repo,
                    input_text=f"change {region}\n",
                ).stdout.strip()
                self.git("update-ref", "HEAD", descendant, cwd=repo)
                self.stage_change(cwd=repo, name="docs/guide.md")
                self.write_marker(
                    cwd=repo,
                    marker_root=repo,
                    third_line="tier: fast",
                    fourth_line=f"policy: {policy_sha}",
                )

                self.assert_denied(
                    self.invoke("git commit", cwd=repo),
                    f"{MARKER_REASON} (fast-path policy drift)",
                )

    def test_fast_marker_nonancestor_policy_is_denied_exactly(self) -> None:
        head_policy = self.commit_policy()
        tree = self.git("rev-parse", f"{head_policy}^{{tree}}").stdout.strip()
        unrelated = self.git(
            "commit-tree", tree, input_text="unrelated policy commit\n"
        ).stdout.strip()
        self.stage_change(name="docs/guide.md")
        self.write_marker(
            third_line="tier: fast",
            fourth_line=f"policy: {unrelated}",
        )

        self.assert_denied(
            self.invoke("git commit"),
            f"{MARKER_REASON} (fast-path policy drift)",
        )

    def test_fast_marker_standard_diff_is_promoted_and_denied_exactly(self) -> None:
        policy_sha = self.commit_policy()
        self.stage_change(name="src/service.py")
        self.write_marker(
            third_line="tier: fast",
            fourth_line=f"policy: {policy_sha}",
        )

        self.assert_denied(
            self.invoke("git commit"),
            f"{MARKER_REASON} (fast-path eligibility drift)",
        )

        events = self.repo / ".forge/tmp/decisions/events.jsonl"
        emitted = [json.loads(line) for line in events.read_text().splitlines()]
        self.assertEqual(len(emitted), 1)
        self.assertEqual(emitted[0]["event"], "fast_denied_eligibility")
        self.assertEqual(emitted[0]["candidate"], self.staged_hash())
        self.assertEqual(emitted[0]["policy_sha"], policy_sha)
        self.assertEqual(emitted[0]["reason"], "fast-path-eligibility-drift")
        self.assertFalse(any(item["event"] == "guard_deny" for item in emitted))

    def test_fast_classification_never_reads_working_tree_policy(self) -> None:
        policy_sha = self.commit_policy()
        self.stage_change(name="src/service.py")
        (self.repo / "forge-project.md").write_text(
            self.policy_text(fast_patterns="**"), encoding="utf-8"
        )
        self.write_marker(
            third_line="tier: fast",
            fourth_line=f"policy: {policy_sha}",
        )

        self.assert_denied(
            self.invoke("git commit"),
            f"{MARKER_REASON} (fast-path eligibility drift)",
        )

    def test_future_marker_timestamp_allows_only_clock_skew(self) -> None:
        (self.repo / ".forge-manifest").write_text("forge_version: 1\n")
        self.stage_change()

        one_hour_ahead = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        self.write_marker(timestamp=one_hour_ahead)
        self.assert_denied(
            self.invoke("git commit"),
            f"{MARKER_REASON} (marker malformed)",
        )

        one_minute_ahead = (datetime.now(timezone.utc) + timedelta(seconds=60)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        self.write_marker(timestamp=one_minute_ahead)
        self.assert_allowed(self.invoke("git commit"))

    def test_malformed_working_tree_manifest_requires_marker(self) -> None:
        (self.repo / ".forge-manifest").write_text(
            "forge_version: 1\n"
            "not_plugin_ref: decoy\n"
            "not_upstream_commit: decoy\n"
            "note: region: gates (forge-project.md)\n",
            encoding="utf-8",
        )
        self.stage_change()

        self.assert_denied(
            self.invoke("git commit"),
            f"{MARKER_REASON} (marker missing)",
        )

    def test_upstream_schema_working_tree_manifest_leaves_only_halt_check(self) -> None:
        upstream_manifests = (
            "forge_version: 1\nupstream_commit: abc123\n",
            "forge_version: 1\nupstream_commit:\n",
            "forge_version: 1\nregion: gates (.opencode/rules/gates.md)\n",
        )

        for index, contents in enumerate(upstream_manifests):
            with self.subTest(contents=contents):
                repo = self.scratch / f"upstream manifest {index}"
                self.init_repo(repo)
                (repo / ".forge-manifest").write_text(contents, encoding="utf-8")
                self.git("add", ".forge-manifest", cwd=repo)
                tree = self.git("write-tree", cwd=repo).stdout.strip()
                parent = self.git("rev-parse", "HEAD", cwd=repo).stdout.strip()
                commit = self.git(
                    "commit-tree",
                    tree,
                    "-p",
                    parent,
                    cwd=repo,
                    input_text="track upstream manifest\n",
                ).stdout.strip()
                self.git("update-ref", "HEAD", commit, cwd=repo)
                self.stage_change(cwd=repo)
                self.assert_allowed(self.invoke("git commit", cwd=repo))

                (repo / "AGENT_HALT_commit").write_text(
                    "operator pause\n", encoding="utf-8"
                )
                self.assert_denied(
                    self.invoke("git commit", cwd=repo),
                    "forge: operator halt engaged (AGENT_HALT_commit)",
                )

    def test_head_plugin_ref_match_is_anchored_not_a_bare_substring(self) -> None:
        (self.repo / ".forge-manifest").write_text(
            "forge_version: 1\nnot_plugin_ref: decoy\n", encoding="utf-8"
        )
        self.git("add", ".forge-manifest")
        tree = self.git("write-tree").stdout.strip()
        parent = self.git("rev-parse", "HEAD").stdout.strip()
        commit = self.git(
            "commit-tree",
            tree,
            "-p",
            parent,
            input_text="track non-plugin manifest\n",
        ).stdout.strip()
        self.git("update-ref", "HEAD", commit)
        (self.repo / ".forge-manifest").unlink()
        self.stage_change()

        self.assert_allowed(self.invoke("git commit"))

    def test_bootstrap_manifest_with_plugin_ref_stripped_still_requires_marker(self) -> None:
        (self.repo / ".forge-manifest").write_text(
            "forge_version: 1\n"
            "installed: 2026-08-12\n"
            "project_name: bootstrap-fixture\n"
            "default_branch: main\n"
            "init_completed: false\n",
            encoding="utf-8",
        )
        self.stage_change()

        self.assert_denied(
            self.invoke("git commit"),
            f"{MARKER_REASON} (marker missing)",
        )

    def test_any_working_tree_manifest_entry_requires_marker(self) -> None:
        manifest = self.repo / ".forge-manifest"
        self.stage_change()

        manifest.mkdir()
        self.assert_denied(
            self.invoke("git commit"),
            f"{MARKER_REASON} (marker missing)",
        )
        manifest.rmdir()

        manifest.symlink_to("missing-manifest-target")
        self.assert_denied(
            self.invoke("git commit"),
            f"{MARKER_REASON} (marker missing)",
        )

    def test_head_plugin_manifest_still_requires_marker_when_staged_for_deletion(self) -> None:
        self.track_manifest()
        (self.repo / ".forge-manifest").unlink()
        self.git("add", "-u", ".forge-manifest")

        self.assert_denied(
            self.invoke("git commit"),
            f"{MARKER_REASON} (marker missing)",
        )

    def test_head_plugin_manifest_still_requires_marker_when_deleted_unstaged(self) -> None:
        self.track_manifest()
        (self.repo / ".forge-manifest").unlink()

        self.assert_denied(
            self.invoke("git commit"),
            f"{MARKER_REASON} (marker missing)",
        )

    def test_manifest_schema_predicate_mutants_are_killed(self) -> None:
        disabled = self.mutant_guard(
            "manifest-predicate-disabled",
            "def manifest_requires_marker(context: RepoContext) -> bool:\n    try:\n",
            "def manifest_requires_marker(context: RepoContext) -> bool:\n"
            "    return False  # CONTROL DISABLED\n"
            "    try:\n",
        )
        (self.repo / ".forge-manifest").write_text(
            "forge_version: 1\ninstalled: now\ninit_completed: false\n",
            encoding="utf-8",
        )
        self.stage_change()

        # The intact bootstrap/malformed-manifest tests expect denial. With the
        # predicate removed, that same positive assertion fails because the
        # commit is allowed.
        self.assert_allowed(self.invoke("git commit", guard=disabled))

        upstream_disabled = self.mutant_guard(
            "upstream-schema-disabled",
            "    return not is_upstream\n",
            "    return True  # CONTROL DISABLED: upstream schema recognition\n",
        )
        (self.repo / ".forge-manifest").write_text(
            "forge_version: 1\nupstream_commit: abc123\n", encoding="utf-8"
        )

        # The intact upstream-schema test expects pass-through. Removing schema
        # recognition makes its assertion fail by arming the marker requirement.
        self.assert_denied(
            self.invoke("git commit", guard=upstream_disabled),
            f"{MARKER_REASON} (marker missing)",
        )

        substring = self.mutant_guard(
            "head-plugin-ref-substring",
            'HEAD_PLUGIN_REF_LINE = re.compile(br"^plugin_ref: ", re.MULTILINE)',
            'HEAD_PLUGIN_REF_LINE = re.compile(br"plugin_ref: ", re.MULTILINE)',
        )
        (self.repo / ".forge-manifest").write_text(
            "forge_version: 1\nnot_plugin_ref: decoy\n", encoding="utf-8"
        )
        self.git("add", ".forge-manifest")
        tree = self.git("write-tree").stdout.strip()
        parent = self.git("rev-parse", "HEAD").stdout.strip()
        commit = self.git(
            "commit-tree",
            tree,
            "-p",
            parent,
            input_text="track non-plugin manifest\n",
        ).stdout.strip()
        self.git("update-ref", "HEAD", commit)
        (self.repo / ".forge-manifest").unlink()

        # The anchored-match test expects pass-through; a bare-substring mutant
        # instead arms on not_plugin_ref and is therefore observably killed.
        self.assert_denied(
            self.invoke("git commit", guard=substring),
            f"{MARKER_REASON} (marker missing)",
        )

    def test_non_forge_repo_commit_and_push_pass_through(self) -> None:
        self.stage_change()

        self.assert_allowed(self.invoke("git commit -m ordinary"))
        self.assert_allowed(self.invoke("git push origin HEAD"))

    def test_authorized_candidate_rejects_index_mutation_and_commit_selection_forms(self) -> None:
        self.track_manifest()
        self.stage_change(name="docs/guide.md")
        self.write_marker()
        unsafe = (
            "git add src/evil.py && git commit",
            "git commit -a",
            "git commit --all",
            "git commit --include src/evil.py",
            "git commit --only src/evil.py",
            "git commit src/evil.py",
            "git commit --patch",
            "git commit --interactive",
            "git commit --pathspec-from-file=paths.txt",
            "git commit -amessage",
            "git commit -C HEAD",
            "git commit --reuse-message HEAD",
            "git commit --reuse-message=HEAD",
            "git commit -c HEAD",
            "git commit --reedit-message HEAD",
            "git commit --reedit-message=HEAD",
            "git commit -F message.txt",
            "git commit --file message.txt",
            "git commit --file=message.txt",
            "git add src/evil.py & git commit",
            'git commit -m "$(git add src/evil.py)"',
            'git commit -m "<(git add src/evil.py)"',
        )
        for command in unsafe:
            with self.subTest(command=command):
                self.assert_denied(
                    self.invoke(command),
                    f"{MARKER_REASON} (marker hash mismatch)",
                )

    def test_authorized_candidate_accepts_value_less_benign_commit_flags(self) -> None:
        self.track_manifest()
        self.stage_change(name="docs/guide.md")
        self.write_marker()
        benign = (
            "git commit -q -m x",
            "git commit --quiet -m x",
            "git commit -v -m x",
            "git commit --verbose -m x",
            "git commit -n -m x",
            "git commit --no-verify -m x",
            "git commit -s -m x",
            "git commit --signoff -m x",
            "git commit --no-edit",
        )
        for command in benign:
            with self.subTest(command=command):
                self.assert_allowed(self.invoke(command))

    def test_signing_flags_do_not_swallow_unsafe_commit_options(self) -> None:
        self.track_manifest()
        self.stage_change(name="docs/guide.md")
        self.write_marker()
        bypasses = (
            "git commit -S --amend -m x",
            "git commit -S -a -m x",
            "git commit --gpg-sign --amend -m x",
            "git commit -m x -S --amend",
            "git commit -S- --amend -m x",
        )
        for command in bypasses:
            with self.subTest(command=command):
                self.assert_denied(
                    self.invoke(command),
                    f"{MARKER_REASON} (marker hash mismatch)",
                )

    def test_attached_signing_keys_preserve_clean_commit_candidate(self) -> None:
        self.track_manifest()
        self.stage_change(name="docs/guide.md")
        self.write_marker()
        for command in (
            "git commit -S0123456789ABCDEF -m x",
            "git commit --gpg-sign=0123456789ABCDEF -m x",
        ):
            with self.subTest(command=command):
                self.assert_allowed(self.invoke(command))

    def test_all_required_command_forms_are_detected(self) -> None:
        (self.repo / ".forge-manifest").write_text("forge_version: 1\n")
        self.stage_change()
        self.assert_allowed(self.invoke("env git status"))
        git_path = "/usr/bin/git" if Path("/usr/bin/git").is_file() else "git"
        cases = [
            (f"git -C {shlex_quote(self.repo)} commit", self.scratch),
            (f"{git_path} commit", self.repo),
            ("env A=b git commit", self.repo),
            ("env -i PATH=/usr/bin git commit -m x", self.repo),
            ("env -u FOO A=b git commit", self.repo),
            ("env env git commit", self.repo),
            ("env -0 -v -uFOO -C . -P /usr/bin A=b git commit", self.repo),
            ("env -S 'A=b -- git commit'", self.repo),
            (
                "env --ignore-environment --unset=FOO --chdir=. "
                "--null --block-signal PIPE "
                "--default-signal PIPE --ignore-signal INT "
                "--list-signal-handlers --debug --split-string='git commit'",
                self.repo,
            ),
            ("FOO=bar git commit", self.repo),
            (">/dev/null git commit", self.repo),
            ("> /dev/null git commit", self.repo),
            ("git 2>/dev/null commit", self.repo),
            (f"cd {shlex_quote(self.repo)} && git commit", self.scratch),
            ("printf before\ngit commit", self.repo),
            ("printf before | git commit", self.repo),
            ("true ; git commit", self.repo),
            ("false || git commit", self.repo),
            (
                "git -c core.pager=cat --git-dir=.git --work-tree=. --no-pager commit",
                self.repo,
            ),
            ("git --no-advice commit", self.repo),
        ]
        for command, cwd in cases:
            with self.subTest(command=command):
                self.assert_denied(
                    self.invoke(command, cwd=cwd),
                    f"{MARKER_REASON} (marker missing)",
                )

        tilde_environment = os.environ.copy()
        tilde_environment["HOME"] = str(self.scratch)
        self.assert_denied(
            self.invoke(
                "git -C ~/main\\ checkout commit",
                cwd=self.scratch,
                environment=tilde_environment,
            ),
            f"{MARKER_REASON} (marker missing)",
        )

        variable_environment = os.environ.copy()
        variable_environment["REPO"] = str(self.repo)
        for command, cwd in (
            ('git -C "$REPO" commit', self.scratch),
            ('cd "$REPO" && git commit', self.scratch),
            ('git -C "$PWD" commit', self.repo),
        ):
            with self.subTest(command=command):
                self.assert_denied(
                    self.invoke(command, cwd=cwd, environment=variable_environment),
                    f"{MARKER_REASON} (marker missing)",
                )

    def test_env_split_string_and_chdir_use_the_effective_git_context(self) -> None:
        (self.repo / ".forge-manifest").write_text("forge_version: 1\n")
        self.stage_change()
        git_path = "/usr/bin/git" if Path("/usr/bin/git").is_file() else "git"

        for command in (
            "env -S 'git commit -m x'",
            "env -S 'env git commit -m x'",
            f"env -S 'A=b {git_path} commit -m x'",
        ):
            with self.subTest(command=command):
                self.assert_denied(
                    self.invoke(command),
                    f"{MARKER_REASON} (marker missing)",
                )
        self.assert_allowed(self.invoke("env -S 'git status'"))
        self.assert_allowed(self.invoke("env --split-string 'git status'"))

        for command in (
            "env --split-string 'git commit -m x'",
            "env --unset FOO git commit",
        ):
            with self.subTest(command=command):
                self.assert_denied(
                    self.invoke(command),
                    f"{MARKER_REASON} (marker missing)",
                )

        for command in (
            f"env -C {shlex_quote(self.repo)} git commit",
            f"env -C {shlex_quote(self.repo)} git -C . commit",
            f"env --chdir {shlex_quote(self.repo)} git commit",
        ):
            with self.subTest(command=command):
                self.assert_denied(
                    self.invoke(command, cwd=self.scratch),
                    f"{MARKER_REASON} (marker missing)",
                )

    def test_halt_precedes_marker_check_and_blocks_push_in_any_repo(self) -> None:
        (self.repo / ".forge-manifest").write_text("forge_version: 1\n")
        (self.repo / "AGENT_HALT_commit").write_text("operator pause\n")

        for command in ("git commit", "git push origin HEAD"):
            with self.subTest(command=command):
                self.assert_denied(
                    self.invoke(command),
                    "forge: operator halt engaged (AGENT_HALT_commit)",
                )
        halt_audit = self.repo / ".forge" / "tmp" / "halt-audit.log"
        self.assertEqual(stat.S_IMODE(halt_audit.stat().st_mode), 0o600)

        other = self.scratch / "ordinary repo"
        self.init_repo(other)
        (other / "AGENT_HALT").write_text("global pause\n")
        self.assert_denied(
            self.invoke(f"git -C {shlex_quote(other)} push", cwd=self.scratch),
            "forge: operator halt engaged (AGENT_HALT)",
        )

        bare_parent = self.scratch / "bare parent"
        bare_parent.mkdir()
        bare_repo = bare_parent / "origin.git"
        subprocess.run(
            ["git", "init", "--bare", "--quiet", str(bare_repo)],
            check=True,
            capture_output=True,
            text=True,
        )
        (bare_parent / "AGENT_HALT").write_text("bare pause\n", encoding="utf-8")
        self.assert_denied(
            self.invoke(f"git -C {shlex_quote(bare_repo)} push", cwd=self.scratch),
            "forge: operator halt engaged (AGENT_HALT)",
        )

    def test_halt_denial_emits_exactly_one_operator_halt_guard_event(self) -> None:
        self.stage_change(name="halted.txt")
        expected_candidate = self.staged_hash()
        expected_policy = self.git("rev-parse", "HEAD").stdout.strip()
        (self.repo / "AGENT_HALT").write_text("operator pause\n", encoding="utf-8")

        self.assert_denied(
            self.invoke("git push origin HEAD"),
            "forge: operator halt engaged (AGENT_HALT)",
        )

        events = self.repo / ".forge/tmp/decisions/events.jsonl"
        emitted = [json.loads(line) for line in events.read_text().splitlines()]
        guard_denials = [item for item in emitted if item["event"] == "guard_deny"]
        self.assertEqual(len(guard_denials), 1)
        self.assertEqual(guard_denials[0]["candidate"], expected_candidate)
        self.assertEqual(guard_denials[0]["policy_sha"], expected_policy)
        self.assertEqual(guard_denials[0]["reason"], "operator-halt")
        self.assertEqual(guard_denials[0]["surface"], "commit-guard")

    def test_non_utf8_halt_contents_still_emit_a_deny(self) -> None:
        (self.repo / "AGENT_HALT").write_bytes(b"operator pause: \xff\n")
        self.assert_denied(
            self.invoke("git push origin HEAD"),
            "forge: operator halt engaged (AGENT_HALT)",
        )

    def test_block_audit_is_mode_600_truncated_and_redacts_secrets(self) -> None:
        (self.repo / "AGENT_HALT").write_text("pause\n")
        command = (
            "git push DB_PASSWORD=hunter2 OPENAI_API_KEY=api-secret-value "
            "BEARER_TOKEN=supersecretvalue bearer=othersecret "
            '"Authorization: Bearer bearer-secret-value" sk-supersecrettoken '
            "-----BEGIN PRIVATE KEY-----\nprivate-key-bytes\n"
            "-----END PRIVATE KEY----- "
            + "x" * 400
        )

        self.assert_denied(
            self.invoke(command),
            "forge: operator halt engaged (AGENT_HALT)",
        )

        audit = self.repo / ".forge" / "tmp" / "halt-audit.log"
        self.assertEqual(stat.S_IMODE(audit.stat().st_mode), 0o600)
        contents = audit.read_text(encoding="utf-8")
        for secret in (
            "hunter2",
            "api-secret-value",
            "supersecretvalue",
            "othersecret",
            "bearer-secret-value",
            "sk-supersecrettoken",
            "private-key-bytes",
        ):
            self.assertNotIn(secret, contents)
        guard_line = next(
            line for line in contents.splitlines()
            if "executable=git deny=operator-halt" in line
        )
        self.assertIn("executable=git deny=operator-halt", guard_line)
        self.assertIn("[REDACTED]", guard_line)
        self.assertIn("[REDACTED PEM BLOCK]", guard_line)
        excerpt = guard_line.split(" excerpt=", 1)[1]
        self.assertLessEqual(len(excerpt), 200)

    def test_linked_worktree_uses_main_checkout_marker_and_audit_root(self) -> None:
        self.track_manifest()
        linked = self.scratch / "linked worktree"
        self.git("worktree", "add", "--quiet", "-b", "linked", str(linked))
        self.stage_change(cwd=linked, name="linked.txt")

        main_marker = self.write_marker(cwd=linked, marker_root=self.repo)
        self.assert_allowed(self.invoke("git commit", cwd=linked))

        main_marker.unlink()
        self.write_marker(cwd=linked, marker_root=linked)
        self.assert_denied(
            self.invoke("git commit", cwd=linked),
            f"{MARKER_REASON} (marker missing)",
        )
        self.assertTrue((self.repo / ".forge/tmp/halt-audit.log").is_file())
        self.assertFalse((linked / ".forge/tmp/halt-audit.log").exists())

    def test_linked_worktree_fast_marker_reclassifies_linked_index(self) -> None:
        policy_sha = self.commit_policy()
        linked = self.scratch / "linked fast worktree"
        self.git("worktree", "add", "--quiet", "-b", "linked-fast", str(linked))
        self.stage_change(cwd=linked, name="docs/guide.md")
        self.write_marker(
            cwd=linked,
            marker_root=self.repo,
            third_line="tier: fast",
            fourth_line=f"policy: {policy_sha}",
        )

        self.assert_allowed(self.invoke("git commit", cwd=linked))

    def test_linked_fast_classifier_does_not_forward_ambient_repository_globals(self) -> None:
        policy_sha = self.commit_policy()
        linked = self.scratch / "linked ambient worktree"
        self.git("worktree", "add", "--quiet", "-b", "linked-ambient", str(linked))
        self.stage_change(cwd=linked, name="docs/guide.md")
        self.write_marker(
            cwd=linked,
            marker_root=self.repo,
            third_line="tier: fast",
            fourth_line=f"policy: {policy_sha}",
        )
        invocation_cwd = linked / "nested"
        invocation_cwd.mkdir()
        linked_git_dir = Path(
            self.git("rev-parse", "--absolute-git-dir", cwd=linked).stdout.strip()
        )
        environment = os.environ.copy()
        environment["GIT_DIR"] = os.path.relpath(
            linked_git_dir, invocation_cwd.resolve()
        )
        environment["GIT_WORK_TREE"] = os.path.relpath(
            linked.resolve(), invocation_cwd.resolve()
        )

        self.assert_allowed(
            self.invoke("git commit", cwd=invocation_cwd, environment=environment)
        )

    def test_ambient_main_git_dir_cannot_authorize_linked_hard_index_as_fast(self) -> None:
        policy_sha = self.commit_policy()
        linked = self.scratch / "linked split worktree"
        self.git("worktree", "add", "--quiet", "-b", "linked-split", str(linked))
        self.stage_change(cwd=linked, name="docs/guide.md")
        (self.repo / "forge-project.md").write_text(
            self.policy_text() + "\nambient hard change\n",
            encoding="utf-8",
        )
        self.git("add", "forge-project.md", cwd=self.repo)
        self.write_marker(
            cwd=self.repo,
            marker_root=self.repo,
            third_line="tier: fast",
            fourth_line=f"policy: {policy_sha}",
        )
        environment = os.environ.copy()
        environment["GIT_DIR"] = str(self.repo / ".git")

        self.assert_denied(
            self.invoke("git commit", cwd=linked, environment=environment),
            f"{MARKER_REASON} (fast-path eligibility drift)",
        )

    def test_fast_marker_preserves_inherited_alternate_index(self) -> None:
        policy_sha = self.commit_policy()
        alternate_index = self.scratch / "alternate.index"
        environment = os.environ.copy()
        environment["GIT_INDEX_FILE"] = str(alternate_index)
        subprocess.run(
            ["git", "read-tree", "HEAD"],
            cwd=self.repo,
            env=environment,
            check=True,
            capture_output=True,
        )
        alternate_doc = self.repo / "docs" / "alternate.md"
        alternate_doc.parent.mkdir(parents=True)
        alternate_doc.write_text("alternate index\n", encoding="utf-8")
        subprocess.run(
            ["git", "add", "docs/alternate.md"],
            cwd=self.repo,
            env=environment,
            check=True,
            capture_output=True,
        )
        alternate_diff = subprocess.run(
            ["git", "diff", "--cached"],
            cwd=self.repo,
            env=environment,
            check=True,
            capture_output=True,
        ).stdout
        self.write_marker(
            digest=hashlib.sha256(alternate_diff).hexdigest(),
            third_line="tier: fast",
            fourth_line=f"policy: {policy_sha}",
        )

        self.assert_allowed(self.invoke("git commit", environment=environment))

    def test_legacy_git_path_fallback_preserves_relative_alternate_index(self) -> None:
        policy_sha = self.commit_policy()
        nested = self.repo / "nested" / "deeper"
        nested.mkdir(parents=True)
        environment = os.environ.copy()
        environment["GIT_INDEX_FILE"] = "alternate.index"
        subprocess.run(
            ["git", "read-tree", "HEAD"],
            cwd=self.repo,
            env=environment,
            check=True,
            capture_output=True,
        )
        alternate_doc = self.repo / "docs" / "legacy-alternate.md"
        alternate_doc.parent.mkdir(parents=True)
        alternate_doc.write_text("legacy alternate index\n", encoding="utf-8")
        subprocess.run(
            ["git", "add", "docs/legacy-alternate.md"],
            cwd=self.repo,
            env=environment,
            check=True,
            capture_output=True,
        )
        alternate_diff = subprocess.run(
            ["git", "diff", "--cached"],
            cwd=self.repo,
            env=environment,
            check=True,
            capture_output=True,
        ).stdout
        self.write_marker(
            digest=hashlib.sha256(alternate_diff).hexdigest(),
            third_line="tier: fast",
            fourth_line=f"policy: {policy_sha}",
        )

        real_git = shutil.which("git")
        self.assertIsNotNone(real_git)
        fake_bin = self.scratch / "legacy git bin"
        fake_bin.mkdir()
        git_wrapper = fake_bin / "git"
        git_wrapper.write_text(
            "#!/usr/bin/env bash\n"
            'if [[ "$1" == "rev-parse" && "$2" == "--path-format=absolute" ]]; then\n'
            "  exit 129\n"
            "fi\n"
            f"exec {shlex_quote(Path(real_git or ''))} \"$@\"\n",
            encoding="utf-8",
        )
        git_wrapper.chmod(0o755)
        environment["PATH"] = f"{fake_bin}{os.pathsep}{environment.get('PATH', '')}"

        self.assert_allowed(
            self.invoke("git commit", cwd=nested, environment=environment)
        )

    def test_explicit_external_git_dir_and_work_tree_keep_repository_context(self) -> None:
        external_git_dir = self.scratch / "external admin.git"
        (self.repo / ".git").rename(external_git_dir)
        (self.repo / ".forge-manifest").write_text("forge_version: 1\n")
        command = (
            f"git --git-dir={shlex_quote(external_git_dir)} "
            f"--work-tree={shlex_quote(self.repo)} commit"
        )

        self.assert_denied(
            self.invoke(command, cwd=self.scratch),
            f"{MARKER_REASON} (marker missing)",
        )
        audit = self.scratch / ".forge/tmp/halt-audit.log"
        self.assertTrue(audit.is_file())
        self.assertEqual(stat.S_IMODE(audit.stat().st_mode), 0o600)

        (self.scratch / "AGENT_HALT").write_text("pause\n")
        push_command = command.rsplit(" ", 1)[0] + " push"
        self.assert_denied(
            self.invoke(push_command, cwd=self.scratch),
            "forge: operator halt engaged (AGENT_HALT)",
        )

    def test_fast_classifier_uses_explicit_git_dir_and_work_tree_identity(self) -> None:
        policy_sha = self.commit_policy()
        self.stage_change(name="docs/guide.md")
        self.write_marker(
            cwd=self.repo,
            marker_root=self.scratch,
            third_line="tier: fast",
            fourth_line=f"policy: {policy_sha}",
        )
        external_git_dir = self.scratch / "external fast admin.git"
        (self.repo / ".git").rename(external_git_dir)
        command = (
            f"git --git-dir={shlex_quote(external_git_dir)} "
            f"--work-tree={shlex_quote(self.repo)} commit"
        )

        self.assert_allowed(self.invoke(command, cwd=self.scratch))


def shlex_quote(value: Path) -> str:
    import shlex

    return shlex.quote(str(value))


if __name__ == "__main__":
    unittest.main()
