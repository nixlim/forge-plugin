from __future__ import annotations

import argparse
import io
import json
import os
import re
import stat
import subprocess
import sys
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

import tomllib

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = Path("forge-project.md")
SPEC_PATH = Path("docs/specs/forge-plugin-spec.md")
IMPLEMENTER_PATH = Path("system/codex/agents/implementer.toml")
REVIEWER_PATH = Path("system/codex/agents/review-cheap.toml")
FINAL_REVIEWER_PATH = Path("agents/review-final.md")
ROLE_PATHS = {
    "implementation": IMPLEMENTER_PATH,
    "review": REVIEWER_PATH,
}


class ConformanceError(RuntimeError):
    pass


def git(repo: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *arguments], cwd=repo, check=False, capture_output=True
    )


def committed_text(repo: Path, revision: str, path: Path) -> str:
    result = git(repo, "show", f"{revision}:{path.as_posix()}")
    if result.returncode != 0:
        raise ConformanceError(
            f"{revision}:{path.as_posix()} is unavailable"
        )
    try:
        return result.stdout.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ConformanceError(
            f"{revision}:{path.as_posix()} is not UTF-8"
        ) from exc


def parse_toml_route(text: str, source: str) -> tuple[str, str, str]:
    try:
        values = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConformanceError(f"{source} is malformed TOML") from exc
    route = (
        values.get("model"),
        values.get("model_reasoning_effort"),
        values.get("sandbox_mode"),
    )
    if not all(isinstance(value, str) and value for value in route):
        raise ConformanceError(f"{source} lacks a complete route")
    return route  # type: ignore[return-value]


def requirement(text: str, requirement_id: str) -> str:
    matches = re.findall(
        rf"(?m)^- \*\*{re.escape(requirement_id)}\*\* .*?$", text
    )
    if len(matches) != 1:
        raise ConformanceError(f"spec must contain exactly one {requirement_id}")
    return matches[0]


def spec_codex_routes(spec: str) -> dict[str, tuple[str, str, str]]:
    line = requirement(spec, "FR-030")
    routes: dict[str, tuple[str, str, str]] = {}
    for role, label in (
        ("implementation", "implementer"),
        ("review", "first-pass reviewer"),
    ):
        match = re.search(
            rf"{re.escape(label)} \(`role: \"{role}\"`, model `([^`]+)`, "
            rf"effort `([^`]+)`, sandbox `([^`]+)`\)",
            line,
        )
        if match is None:
            raise ConformanceError(f"FR-030 lacks the {role} route")
        routes[role] = match.groups()
    return routes


def frontmatter_route(text: str, source: str) -> tuple[str, str]:
    if not text.startswith("---\n"):
        raise ConformanceError(f"{source} lacks frontmatter")
    parts = text.split("---\n", 2)
    if len(parts) != 3:
        raise ConformanceError(f"{source} has malformed frontmatter")
    values: dict[str, str] = {}
    for line in parts[1].splitlines():
        if ": " in line:
            key, value = line.split(": ", 1)
            values[key] = value
    try:
        return values["model"], values["effort"]
    except KeyError as exc:
        raise ConformanceError(f"{source} lacks model or effort") from exc


def spec_final_route(spec: str) -> tuple[str, str]:
    line = requirement(spec, "FR-111")
    match = re.search(r"`model: ([^`]+)`, `effort: ([^`]+)`", line)
    if match is None:
        raise ConformanceError("FR-111 lacks the final-review route")
    return match.groups()


def surface_inventory(spec: str) -> set[str]:
    try:
        section = spec.split("## 5. Surface / API Inventory\n", 1)[1].split(
            "\n## 6. ", 1
        )[0]
    except IndexError as exc:
        raise ConformanceError("spec section 5 is unavailable") from exc
    inventory_lines = [
        line
        for line in section.splitlines()
        if line.endswith(" — executable governance script surfaces")
    ]
    if len(inventory_lines) != 1:
        raise ConformanceError(
            "spec section 5 executable script inventory is unavailable"
        )
    inventory_line = inventory_lines[0]
    inventory = set(
        re.findall(r"scripts/forge/[A-Za-z0-9_./-]+\.(?:py|sh)", inventory_line)
    )
    for members in re.findall(r"scripts/forge/\{([^}]+)\}", inventory_line):
        for member in members.split(","):
            if re.fullmatch(r"[A-Za-z0-9_./-]+\.(?:py|sh)", member):
                inventory.add(f"scripts/forge/{member}")
    if not inventory:
        raise ConformanceError(
            "spec section 5 executable script inventory is unavailable"
        )
    return inventory


def executable_scripts(repo: Path) -> set[str]:
    scripts_root = repo / "scripts/forge"
    scripts: set[str] = set()

    def fail_walk(error: OSError) -> None:
        raise error

    try:
        if not stat.S_ISDIR(scripts_root.stat(follow_symlinks=False).st_mode):
            raise ConformanceError("worktree executable inventory is unavailable")
        for directory, _directories, filenames in os.walk(
            scripts_root, onerror=fail_walk, followlinks=False
        ):
            for filename in filenames:
                path = Path(directory, filename)
                mode = path.stat(follow_symlinks=False).st_mode
                if stat.S_ISREG(mode) and mode & 0o111:
                    scripts.add(path.relative_to(repo).as_posix())
    except OSError as exc:
        raise ConformanceError("worktree executable inventory is unavailable") from exc
    return scripts


def file_categories(policy: str) -> dict[str, tuple[str, ...]]:
    try:
        body = policy.split(
            "<!-- FORGE:REGION file-categories BEGIN -->\n", 1
        )[1].split("\n<!-- FORGE:REGION file-categories END -->", 1)[0]
    except IndexError as exc:
        raise ConformanceError("file-categories region is unavailable") from exc
    categories: dict[str, tuple[str, ...]] = {}
    for line in body.splitlines():
        match = re.fullmatch(r"\| `([^`]+)` \| (.+) \|", line)
        if match is None:
            continue
        category, cell = match.groups()
        patterns = tuple(re.findall(r"`([^`]+)`", cell))
        if not patterns or category in categories:
            raise ConformanceError("file-categories region is malformed")
        categories[category] = patterns
    if not categories:
        raise ConformanceError("file-categories region is malformed")
    return categories


def repository_paths(repo: Path, patterns: tuple[str, ...] = ()) -> set[str]:
    arguments = ["ls-files", "-z", "--cached", "--others", "--exclude-standard"]
    if patterns:
        arguments.extend(("--", *patterns))
    result = git(repo, *arguments)
    if result.returncode != 0:
        raise ConformanceError("git repository path inventory is unavailable")
    return {
        item.decode("utf-8", "surrogateescape")
        for item in result.stdout.split(b"\0")
        if item
    }


def assert_dogfood_file_categories(
    test_case: unittest.TestCase, policy: str, repo: Path
) -> None:
    categories = file_categories(policy)
    test_case.assertTrue(
        {".gitignore", "*.yml", "*.yaml", "*.json"}.issubset(
            categories["config"]
        )
    )

    paths = repository_paths(repo)
    matched = repository_paths(
        repo,
        tuple(pattern for patterns in categories.values() for pattern in patterns),
    )
    test_case.assertIn("UPSTREAM", paths)
    test_case.assertEqual(paths - matched, set())


def assert_dogfood_conformance_invariants(
    test_case: unittest.TestCase, policy: str
) -> None:
    try:
        body = policy.split(
            "<!-- FORGE:REGION invariants BEGIN -->\n", 1
        )[1].split("\n<!-- FORGE:REGION invariants END -->", 1)[0]
    except IndexError as exc:
        raise AssertionError("dogfood invariants region is unavailable") from exc
    expected = (
        "| Forge repository routing and executable inventory conform | "
        "python3 -m unittest tests.test_repo_conformance | {} |"
    )

    test_case.assertEqual(body.count(expected.format("commit")), 1)
    test_case.assertEqual(body.count(expected.format("merge")), 1)


def assert_dogfood_initialized_regions(
    test_case: unittest.TestCase, policy: str
) -> None:
    expected = (
        "project-overview",
        "file-categories",
        "stack-validations",
        "gate1-test-command",
        "changelog-policy",
        "review-prompt-project-focus",
        "project-triggers",
        "completeness-project-items",
        "agent-project-context",
        "mutation-testing",
        "invariants",
        "risk-tiers",
        "drift-config",
        "trigger-paths",
    )
    begins = re.findall(r"<!-- FORGE:REGION ([a-z0-9-]+) BEGIN -->", policy)

    test_case.assertEqual(tuple(begins), expected)
    test_case.assertNotIn("forge-init:", policy)

    for heading in (
        "## DVRR Spine",
        "### Operating Model",
        "### Instruction Priority",
        "### Git Policy",
        "### Untrusted Input",
        "### Risk and Authority Classes",
        "## Plugin Skills",
    ):
        with test_case.subTest(heading=heading):
            test_case.assertEqual(policy.count(heading), 1)
    for skill in (
        "init",
        "learn",
        "workflow",
        "orchestrate",
        "commit",
        "worktree-merge",
        "report",
        "drift",
    ):
        with test_case.subTest(skill=skill):
            test_case.assertIn(
                f"${{CLAUDE_PLUGIN_ROOT}}/skills/{skill}/SKILL.md", policy
            )


def check_current(repo: Path) -> list[str]:
    issues: list[str] = []
    try:
        spec = (repo / SPEC_PATH).read_text(encoding="utf-8")
        pinned = spec_codex_routes(spec)
        for role, path in ROLE_PATHS.items():
            actual = parse_toml_route(
                (repo / path).read_text(encoding="utf-8"), path.as_posix()
            )
            if actual != pinned[role]:
                issues.append(
                    f"{path}: route {actual!r} does not match FR-030 {pinned[role]!r}"
                )
        actual_final = frontmatter_route(
            (repo / FINAL_REVIEWER_PATH).read_text(encoding="utf-8"),
            FINAL_REVIEWER_PATH.as_posix(),
        )
        pinned_final = spec_final_route(spec)
        if actual_final != pinned_final:
            issues.append(
                f"{FINAL_REVIEWER_PATH}: route {actual_final!r} does not match "
                f"FR-111 {pinned_final!r}"
            )
        executable = executable_scripts(repo)
        inventory = surface_inventory(spec)
        missing = sorted(executable - inventory)
        if missing:
            issues.append(
                "spec section 5 omits executable scripts: " + ", ".join(missing)
            )
        non_executable = []
        for path_label in sorted(inventory - executable):
            try:
                mode = (repo / path_label).stat(follow_symlinks=False).st_mode
            except FileNotFoundError:
                # Absence is the third drift direction. It cannot be judged from
                # a synthetic fixture, which carries a deliberate subset of the
                # inventory, so it is asserted against the real repository by
                # test_every_inventoried_script_exists.
                continue
            if not stat.S_ISREG(mode) or not mode & 0o111:
                non_executable.append(path_label)
        if non_executable:
            issues.append(
                "spec section 5 lists non-executable scripts: "
                + ", ".join(non_executable)
            )
    except (ConformanceError, OSError, UnicodeError) as exc:
        issues.append(str(exc))
    return issues


def check_run(repo: Path, run_dir: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    findings: list[str] = []
    journal = run_dir / "journal.jsonl"
    try:
        lines = journal.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        return [f"could not read {journal}: {exc}"], []
    for line_number, line in enumerate(lines, 1):
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"journal line {line_number}: invalid JSON: {exc.msg}")
            continue
        if not isinstance(record, dict) or record.get("type") != "execution":
            continue
        # CONTROL historical-routing-fields-fatal BEGIN
        invalid_fields = [
            field
            for field in ("agent", "model", "effort")
            if not isinstance(record.get(field), str) or not record[field].strip()
        ]
        if invalid_fields:
            errors.append(
                f"journal line {line_number}: execution lacks non-empty string "
                + ", ".join(invalid_fields)
            )
            continue
        # CONTROL historical-routing-fields-fatal END
        head = record.get("head")
        if not isinstance(head, str) or not re.fullmatch(r"[0-9a-f]{7,64}", head):
            errors.append(f"journal line {line_number}: execution lacks a valid head")
            continue
        provider = record.get("provider")
        role = record.get("role")
        if provider == "codex":
            if role not in ROLE_PATHS:
                errors.append(
                    f"journal line {line_number}: unknown Codex execution role {role!r}"
                )
                continue
            authority_path = ROLE_PATHS[role]
            try:
                authority = parse_toml_route(
                    committed_text(repo, head, authority_path),
                    f"{head}:{authority_path}",
                )[:2]
            except ConformanceError as exc:
                errors.append(f"journal line {line_number}: {exc}")
                continue
        elif provider == "claude":
            if role != "review":
                errors.append(
                    f"journal line {line_number}: unknown Claude execution role {role!r}"
                )
                continue
            authority_path = FINAL_REVIEWER_PATH
            try:
                authority = frontmatter_route(
                    committed_text(repo, head, authority_path),
                    f"{head}:{authority_path}",
                )
            except ConformanceError as exc:
                errors.append(f"journal line {line_number}: {exc}")
                continue
        else:
            errors.append(
                f"journal line {line_number}: execution has unsupported provider "
                f"{provider!r}"
            )
            continue
        recorded = record.get("model"), record.get("effort")
        # CONTROL historical-routing-finding BEGIN
        if recorded != authority:
            findings.append(
                f"journal line {line_number}: agent {record.get('agent')!r} recorded "
                f"model/effort {recorded!r}; expected model/effort {authority!r} "
                f"from {head}:{authority_path}"
            )
        # CONTROL historical-routing-finding END
    return errors, findings


def report(errors: list[str], findings: list[str]) -> int:
    print("## Historical Routing Findings")
    print()
    if findings:
        for finding in findings:
            print(f"- {finding}")
    else:
        print("None recorded")
    for error in errors:
        print(f"forge repo conformance: {error}", file=sys.stderr)
    # CONTROL current-routing-fatal BEGIN
    return 1 if errors else 0
    # CONTROL current-routing-fatal END


class RepoConformanceTests(unittest.TestCase):
    def test_every_inventoried_script_exists(self) -> None:
        """Third drift direction: a script listed in spec section 5 but deleted."""
        spec = (ROOT / SPEC_PATH).read_text(encoding="utf-8")
        missing = sorted(
            path_label
            for path_label in surface_inventory(spec)
            if not (ROOT / path_label).exists()
        )
        self.assertEqual(
            missing, [], f"spec section 5 lists absent scripts: {missing}"
        )

    maxDiff = None

    def setUp(self) -> None:
        self.addCleanup(self._cleanup)
        self._temporary_directories: list[object] = []

    def _cleanup(self) -> None:
        for temporary in self._temporary_directories:
            temporary.cleanup()  # type: ignore[attr-defined]

    def fixture_repo(self) -> Path:
        import tempfile

        temporary = tempfile.TemporaryDirectory()
        self._temporary_directories.append(temporary)
        repo = Path(temporary.name)
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(
            ["git", "config", "user.name", "Forge Tests"], cwd=repo, check=True
        )
        subprocess.run(
            ["git", "config", "user.email", "forge-tests@example.invalid"],
            cwd=repo,
            check=True,
        )
        for source in (*ROLE_PATHS.values(), FINAL_REVIEWER_PATH, SPEC_PATH):
            target = repo / source
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / source).read_bytes())
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "routing"], cwd=repo, check=True)
        (repo / "scripts/forge").mkdir(parents=True)
        return repo

    def invoke_main(self, repo: Path, *arguments: str) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch.object(sys.modules[__name__], "ROOT", repo),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            return_code = main(list(arguments))
        return return_code, stdout.getvalue(), stderr.getvalue()

    def test_current_repository_matches_spec_routes_and_script_inventory(self) -> None:
        self.assertEqual(check_current(ROOT), [])

    def test_executable_inventory_includes_untracked_worktree_file(self) -> None:
        repo = self.fixture_repo()
        script = repo / "scripts/forge/untracked-tool.py"
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
        script.chmod(0o755)

        self.assertEqual(
            executable_scripts(repo), {"scripts/forge/untracked-tool.py"}
        )

    def test_executable_inventory_preserves_nested_path_identity(self) -> None:
        repo = self.fixture_repo()
        script = repo / "scripts/forge/nested/archive-run.py"
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
        script.chmod(0o755)

        self.assertEqual(
            executable_scripts(repo), {"scripts/forge/nested/archive-run.py"}
        )
        issues = check_current(repo)
        self.assertTrue(
            any("scripts/forge/nested/archive-run.py" in issue for issue in issues),
            issues,
        )

    def test_executable_inventory_uses_unstaged_worktree_mode(self) -> None:
        repo = self.fixture_repo()
        script = repo / "scripts/forge/tracked-tool.py"
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
        script.chmod(0o644)
        subprocess.run(["git", "add", str(script)], cwd=repo, check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "non-executable script"],
            cwd=repo,
            check=True,
        )
        script.chmod(0o755)

        indexed = git(repo, "ls-files", "-s", "--", str(script.relative_to(repo)))
        self.assertTrue(indexed.stdout.startswith(b"100644 "), indexed.stdout)
        self.assertEqual(
            executable_scripts(repo), {"scripts/forge/tracked-tool.py"}
        )

        subprocess.run(["git", "add", str(script)], cwd=repo, check=True)
        script.chmod(0o644)
        indexed = git(repo, "ls-files", "-s", "--", str(script.relative_to(repo)))
        self.assertTrue(indexed.stdout.startswith(b"100755 "), indexed.stdout)
        self.assertEqual(executable_scripts(repo), set())

    def test_current_check_catches_interpreter_helper_made_executable(self) -> None:
        repo = self.fixture_repo()
        script = repo / "scripts/forge/run-scoped-mutation.py"
        script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
        script.chmod(0o755)

        issues = check_current(repo)

        self.assertTrue(
            any(
                issue
                == "spec section 5 omits executable scripts: "
                "scripts/forge/run-scoped-mutation.py"
                for issue in issues
            ),
            issues,
        )

    def test_current_check_catches_inventory_script_made_non_executable(self) -> None:
        repo = self.fixture_repo()
        script = repo / "scripts/forge/check-halt.sh"
        script.write_text("#!/bin/sh\n", encoding="utf-8")
        script.chmod(0o644)

        issues = check_current(repo)

        self.assertTrue(
            any(
                issue
                == "spec section 5 lists non-executable scripts: "
                "scripts/forge/check-halt.sh"
                for issue in issues
            ),
            issues,
        )

    def test_current_check_catches_inventory_script_replaced_by_symlink(self) -> None:
        repo = self.fixture_repo()
        script = repo / "scripts/forge/check-halt.sh"
        script.symlink_to("missing-check-halt.sh")

        issues = check_current(repo)

        self.assertTrue(
            any(
                issue
                == "spec section 5 lists non-executable scripts: "
                "scripts/forge/check-halt.sh"
                for issue in issues
            ),
            issues,
        )

    def test_dogfood_file_categories_preserve_generics_and_cover_repository(
        self,
    ) -> None:
        policy = (ROOT / POLICY_PATH).read_text(encoding="utf-8")
        assert_dogfood_file_categories(self, policy, ROOT)

    def test_dogfood_policy_runs_conformance_at_commit_step_2_and_merge_gate_2(
        self,
    ) -> None:
        policy = (ROOT / POLICY_PATH).read_text(encoding="utf-8")
        assert_dogfood_conformance_invariants(self, policy)

    def test_dogfood_policy_has_all_initialized_regions_in_authoritative_order(
        self,
    ) -> None:
        policy = (ROOT / POLICY_PATH).read_text(encoding="utf-8")
        assert_dogfood_initialized_regions(self, policy)

    def test_dogfood_policy_controls_are_observed_by_mutation(self) -> None:
        policy = (ROOT / POLICY_PATH).read_text(encoding="utf-8")
        mutations = (
            (
                "file-category coverage",
                "`*.md`, `*.txt`, `UPSTREAM`, `docs/**`, `.forge/history/**`",
                "`*.md`, `*.txt`, `UPSTREAM-DISABLED`, `docs/**`, `.forge/history/**`",
                lambda mutant: assert_dogfood_file_categories(self, mutant, ROOT),
            ),
            (
                "commit conformance invariant",
                "| Forge repository routing and executable inventory conform | "
                "python3 -m unittest tests.test_repo_conformance | commit |",
                "| Forge repository routing and executable inventory conform | "
                "true # conformance disabled | commit |",
                lambda mutant: assert_dogfood_conformance_invariants(self, mutant),
            ),
            (
                "merge conformance invariant",
                "| Forge repository routing and executable inventory conform | "
                "python3 -m unittest tests.test_repo_conformance | merge |",
                "| Forge repository routing and executable inventory conform | "
                "true # conformance disabled | merge |",
                lambda mutant: assert_dogfood_conformance_invariants(self, mutant),
            ),
            (
                "initialized region inventory",
                "<!-- FORGE:REGION invariants BEGIN -->",
                "<!-- CONTROL DISABLED: invariants -->",
                lambda mutant: assert_dogfood_initialized_regions(self, mutant),
            ),
        )

        for control, needle, replacement, sensor in mutations:
            with self.subTest(control=control):
                self.assertEqual(policy.count(needle), 1)
                mutant = policy.replace(needle, replacement, 1)
                with self.assertRaises(AssertionError):
                    sensor(mutant)

    def test_current_check_catches_agent_and_inventory_drift(self) -> None:
        repo = self.fixture_repo()
        spec_path = repo / SPEC_PATH
        spec = spec_path.read_text(encoding="utf-8")
        broken = spec.replace(
            "gpt-5.6-sol`, effort `high`, sandbox `read-only`",
            "gpt-5.6-terra`, effort `medium`, sandbox `read-only`",
            1,
        )
        self.assertNotEqual(spec, broken)
        spec_path.write_text(broken, encoding="utf-8")
        issues = check_current(repo)
        self.assertTrue(
            any("review-cheap.toml" in issue for issue in issues), issues
        )

        spec_path.write_text(spec, encoding="utf-8")
        script = repo / "scripts/forge/archive-run.py"
        script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
        script.chmod(0o755)
        self.assertEqual(check_current(repo), [])

        missing = spec.replace(",archive-run.py", "", 1)
        self.assertNotEqual(spec, missing)
        spec_path.write_text(missing, encoding="utf-8")
        issues = check_current(repo)
        self.assertTrue(
            any("scripts/forge/archive-run.py" in issue for issue in issues), issues
        )

    def test_current_route_mismatch_refuses_at_cli_boundary(self) -> None:
        repo = self.fixture_repo()
        route = repo / REVIEWER_PATH
        original = route.read_text(encoding="utf-8")
        mismatched = original.replace(
            'model_reasoning_effort = "high"',
            'model_reasoning_effort = "medium"',
            1,
        )
        self.assertNotEqual(original, mismatched)
        route.write_text(mismatched, encoding="utf-8")

        return_code, stdout, stderr = self.invoke_main(repo)

        self.assertEqual(return_code, 1)
        self.assertEqual(
            stdout,
            "## Historical Routing Findings\n\nNone recorded\n",
        )
        self.assertIn("forge repo conformance: ", stderr)
        self.assertIn("system/codex/agents/review-cheap.toml", stderr)
        self.assertIn("does not match FR-030", stderr)

    def test_historical_route_mismatches_are_all_reported_and_nonfatal(self) -> None:
        repo = self.fixture_repo()
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, check=True, text=True, capture_output=True
        ).stdout.strip()
        run_dir = repo / "run"
        run_dir.mkdir()
        (run_dir / "journal.jsonl").write_text(
            "\n".join(
                json.dumps(record)
                for record in (
                    {"type": "run_started"},
                    {
                        "type": "execution",
                        "agent": "codex-review-01",
                        "provider": "codex",
                        "event_source": "exec",
                        "role": "review",
                        "head": head,
                        "model": "gpt-5.6-terra",
                        "effort": "medium",
                    },
                    {"type": "decision", "id": "decision-between-routes"},
                    {
                        "type": "execution",
                        "agent": "claude-review-final",
                        "provider": "claude",
                        "event_source": "claude",
                        "role": "review",
                        "head": head,
                        "model": "fable",
                        "effort": "medium",
                    },
                )
            )
            + "\n",
            encoding="utf-8",
        )
        expected = [
            (
                "journal line 2: agent 'codex-review-01' recorded model/effort "
                "('gpt-5.6-terra', 'medium'); expected model/effort "
                f"('gpt-5.6-sol', 'high') from {head}:{REVIEWER_PATH}"
            ),
            (
                "journal line 4: agent 'claude-review-final' recorded model/effort "
                "('fable', 'medium'); expected model/effort ('fable', 'high') "
                f"from {head}:{FINAL_REVIEWER_PATH}"
            ),
        ]

        errors, findings = check_run(repo, run_dir)

        self.assertEqual(errors, [])
        self.assertEqual(findings, expected)

        return_code, stdout, stderr = self.invoke_main(
            repo, "--run-dir", str(run_dir)
        )
        self.assertEqual(return_code, 0)
        self.assertEqual(
            stdout,
            "## Historical Routing Findings\n\n"
            + "".join(f"- {finding}\n" for finding in expected),
        )
        self.assertEqual(stderr, "")

    def test_malformed_historical_route_fields_refuse_without_findings(self) -> None:
        repo = self.fixture_repo()
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo,
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()
        run_dir = repo / "run"
        run_dir.mkdir()
        base = {
            "type": "execution",
            "agent": "codex-review-01",
            "provider": "codex",
            "event_source": "exec",
            "role": "review",
            "head": head,
            "model": "gpt-5.6-sol",
            "effort": "high",
        }
        records = []
        for field, value in (
            ("agent", None),
            ("model", 17),
            ("effort", "   "),
        ):
            record = dict(base)
            record[field] = value
            records.append(record)
        (run_dir / "journal.jsonl").write_text(
            "".join(json.dumps(record) + "\n" for record in records),
            encoding="utf-8",
        )

        errors, findings = check_run(repo, run_dir)

        self.assertEqual(findings, [])
        self.assertEqual(
            errors,
            [
                "journal line 1: execution lacks non-empty string agent",
                "journal line 2: execution lacks non-empty string model",
                "journal line 3: execution lacks non-empty string effort",
            ],
        )
        return_code, stdout, stderr = self.invoke_main(
            repo, "--run-dir", str(run_dir)
        )
        self.assertEqual(return_code, 1)
        self.assertEqual(
            stdout,
            "## Historical Routing Findings\n\nNone recorded\n",
        )
        for error in errors:
            self.assertIn(f"forge repo conformance: {error}\n", stderr)

    def test_routing_controls_are_observed_by_mutation(self) -> None:
        source = Path(__file__).read_text(encoding="utf-8")
        controls = {
            "current-routing-fatal": (
                "    return 1 if errors else 0\n",
                "    return 0\n",
                "test_current_route_mismatch_refuses_at_cli_boundary",
            ),
            "historical-routing-finding": (
                "        if recorded != authority:\n"
                "            findings.append(\n"
                "                f\"journal line {line_number}: agent "
                "{record.get('agent')!r} recorded \"\n"
                "                f\"model/effort {recorded!r}; expected "
                "model/effort {authority!r} \"\n"
                "                f\"from {head}:{authority_path}\"\n"
                "            )\n",
                "        if recorded != authority:\n"
                "            pass\n",
                "test_historical_route_mismatches_are_all_reported_and_nonfatal",
            ),
            "historical-routing-fields-fatal": (
                "        invalid_fields = [\n"
                "            field\n"
                "            for field in (\"agent\", \"model\", \"effort\")\n"
                "            if not isinstance(record.get(field), str) or not "
                "record[field].strip()\n"
                "        ]\n"
                "        if invalid_fields:\n"
                "            errors.append(\n"
                "                f\"journal line {line_number}: execution lacks "
                "non-empty string \"\n"
                "                + \", \".join(invalid_fields)\n"
                "            )\n"
                "            continue\n",
                "        invalid_fields = []\n",
                "test_malformed_historical_route_fields_refuse_without_findings",
            ),
        }
        for index, (control, (needle, replacement, test_name)) in enumerate(
            controls.items()
        ):
            with self.subTest(control=control):
                self.assertEqual(source.count(needle), 1)
                module_name = f"repo_conformance_mutant_{index}"
                module = types.ModuleType(module_name)
                module.__file__ = __file__
                sys.modules[module_name] = module
                try:
                    exec(
                        compile(source.replace(needle, replacement), __file__, "exec"),
                        module.__dict__,
                    )
                    suite = unittest.TestSuite(
                        [module.RepoConformanceTests(test_name)]
                    )
                    result = unittest.TestResult()
                    suite.run(result)
                finally:
                    del sys.modules[module_name]
                self.assertEqual(result.errors, [], (control, result.errors))
                self.assertTrue(result.failures, (control, result.failures))

    def test_historical_audit_uses_route_committed_at_execution_head(self) -> None:
        repo = self.fixture_repo()
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, check=True, text=True, capture_output=True
        ).stdout.strip()
        run_dir = repo / "run"
        run_dir.mkdir()
        (run_dir / "journal.jsonl").write_text(
            json.dumps(
                {
                    "type": "execution",
                    "agent": "codex-review-01",
                    "provider": "codex",
                    "event_source": "exec",
                    "role": "review",
                    "head": head,
                    "model": "gpt-5.6-sol",
                    "effort": "medium",
                }
            )
            + "\n",
            encoding="utf-8",
        )

        errors, findings = check_run(repo, run_dir)

        self.assertEqual(errors, [])
        self.assertEqual(len(findings), 1)
        self.assertIn("journal line 1", findings[0])
        self.assertIn("agent 'codex-review-01'", findings[0])
        self.assertIn("recorded model/effort ('gpt-5.6-sol', 'medium')", findings[0])
        self.assertIn("expected model/effort ('gpt-5.6-sol', 'high')", findings[0])
        self.assertIn(f"{head}:{REVIEWER_PATH}", findings[0])

    def test_historical_audit_fails_closed_when_authority_is_unavailable(self) -> None:
        repo = self.fixture_repo()
        subprocess.run(
            ["git", "rm", "-q", str(REVIEWER_PATH)], cwd=repo, check=True
        )
        subprocess.run(
            ["git", "commit", "-q", "-m", "remove authority"], cwd=repo, check=True
        )
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, check=True, text=True, capture_output=True
        ).stdout.strip()
        run_dir = repo / "run"
        run_dir.mkdir()
        (run_dir / "journal.jsonl").write_text(
            json.dumps(
                {
                    "type": "execution",
                    "agent": "codex-review-01",
                    "provider": "codex",
                    "event_source": "exec",
                    "role": "review",
                    "head": head,
                    "model": "gpt-5.6-sol",
                    "effort": "high",
                }
            )
            + "\n",
            encoding="utf-8",
        )

        errors, findings = check_run(repo, run_dir)

        self.assertEqual(findings, [])
        self.assertEqual(len(errors), 1)
        self.assertIn("is unavailable", errors[0])

    def test_historical_audit_ignores_later_authority_changes(self) -> None:
        repo = self.fixture_repo()
        old_head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, check=True, text=True, capture_output=True
        ).stdout.strip()
        route = repo / REVIEWER_PATH
        route.write_text(
            route.read_text(encoding="utf-8").replace(
                'model_reasoning_effort = "high"',
                'model_reasoning_effort = "medium"',
            ),
            encoding="utf-8",
        )
        subprocess.run(["git", "add", str(REVIEWER_PATH)], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "new routing"], cwd=repo, check=True)
        run_dir = repo / "run"
        run_dir.mkdir()
        (run_dir / "journal.jsonl").write_text(
            json.dumps(
                {
                    "type": "execution",
                    "agent": "codex-review-01",
                    "provider": "codex",
                    "event_source": "exec",
                    "role": "review",
                    "head": old_head,
                    "model": "gpt-5.6-sol",
                    "effort": "high",
                }
            )
            + "\n",
            encoding="utf-8",
        )

        self.assertEqual(check_run(repo, run_dir), ([], []))

    def test_historical_audit_uses_final_agent_at_claude_execution_head(
        self,
    ) -> None:
        repo = self.fixture_repo()
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, check=True, text=True, capture_output=True
        ).stdout.strip()
        run_dir = repo / "run"
        run_dir.mkdir()
        (run_dir / "journal.jsonl").write_text(
            json.dumps(
                {
                    "type": "execution",
                    "agent": "claude-review-final",
                    "provider": "claude",
                    "event_source": "claude",
                    "role": "review",
                    "head": head,
                    "model": "fable",
                    "effort": "high",
                }
            )
            + "\n",
            encoding="utf-8",
        )

        self.assertEqual(check_run(repo, run_dir), ([], []))

        journal = run_dir / "journal.jsonl"
        journal.write_text(
            journal.read_text(encoding="utf-8").replace(
                '"model": "fable"', '"model": "opus"'
            ),
            encoding="utf-8",
        )
        errors, findings = check_run(repo, run_dir)

        self.assertEqual(errors, [])
        self.assertEqual(len(findings), 1)
        self.assertIn("agent 'claude-review-final'", findings[0])
        self.assertIn("recorded model/effort ('opus', 'high')", findings[0])
        self.assertIn("expected model/effort ('fable', 'high')", findings[0])
        self.assertIn(f"{head}:{FINAL_REVIEWER_PATH}", findings[0])

    def test_historical_audit_fails_closed_for_unclassified_provider(self) -> None:
        repo = self.fixture_repo()
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, check=True, text=True, capture_output=True
        ).stdout.strip()
        run_dir = repo / "run"
        run_dir.mkdir()
        (run_dir / "journal.jsonl").write_text(
            json.dumps(
                {
                    "type": "execution",
                    "agent": "mystery-review",
                    "role": "review",
                    "head": head,
                    "model": "gpt-5.6-sol",
                    "effort": "high",
                }
            )
            + "\n",
            encoding="utf-8",
        )

        errors, findings = check_run(repo, run_dir)

        self.assertEqual(findings, [])
        self.assertEqual(len(errors), 1)
        self.assertIn("unsupported provider None", errors[0])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check forge-plugin repository conformance.")
    parser.add_argument("--run-dir", type=Path)
    args = parser.parse_args(argv)
    errors = check_current(ROOT)
    findings: list[str] = []
    if args.run_dir is not None:
        run_errors, findings = check_run(ROOT, args.run_dir)
        errors.extend(run_errors)
    return report(errors, findings)


if __name__ == "__main__":
    raise SystemExit(main())
