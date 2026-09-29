"""Phase-0 initialization and local route setup contract tests."""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

from tests.test_route_config_support import ROOT, RouteConfigSupport

SKILL_PATH = ROOT / "skills/init/SKILL.md"
SEED_PATH = ROOT / "system/local/routes.toml.seed"
REINIT_DIAGNOSTIC = "forge: route init refused — routes file already exists\n"
UNBORN_DIAGNOSTIC = (
    "forge: init stopped — the current branch has no commit yet; make a first commit, "
    "then re-run /forge:init\n"
)
STEP5_COMMANDS = (
    "git -C \"$REPO_ROOT\" rev-parse --verify --quiet 'HEAD^{commit}' >/dev/null || "
    "{ echo \"forge: init stopped — the current branch has no commit yet; make a first "
    "commit, then re-run /forge:init\" >&2; exit 1; }",
    'python3 "${CLAUDE_PLUGIN_ROOT}/scripts/forge/route_config.py" init '
    '--repo "$REPO_ROOT"',
    'python3 "${CLAUDE_PLUGIN_ROOT}/scripts/forge/route_floor.py" '
    '--repo "$REPO_ROOT"',
    'python3 "${CLAUDE_PLUGIN_ROOT}/scripts/forge/route_config.py" probe '
    '--repo "$REPO_ROOT"',
)
def _step5_text() -> str:
    skill = SKILL_PATH.read_text(encoding="utf-8")
    return skill.split("5. From the repository root", 1)[1].split(
        "\n6. Immediately before Phase 1", 1
    )[0]


def _step5_commands() -> tuple[str, ...]:
    match = re.search(r"```bash\n(?P<body>.*?)\n   ```", _step5_text(), re.DOTALL)
    if match is None:
        raise AssertionError("Phase 0 step 5 bash block is missing")
    return tuple(line.removeprefix("   ") for line in match.group("body").splitlines())


class LaunchInitStepTests(RouteConfigSupport, unittest.TestCase):
    def _environment(self, repo: Path, plugin_root: Path = ROOT) -> dict[str, str]:
        python_dir = Path(sys.executable).parent
        return {
            "CLAUDE_PLUGIN_ROOT": str(plugin_root),
            "CODEX_HOME": str(self.scratch / "codex-home"),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "HOME": str(self.scratch / "home"),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PATH": f"{self.scratch / 'bin'}:{python_dir}:/usr/bin:/bin",
            "REPO_ROOT": str(repo),
            "TERM": "dumb",
            "TMPDIR": str(self.scratch),
            "USER": "forge-test",
        }

    def _run_step5(
        self,
        repo: Path,
        *,
        plugin_root: Path = ROOT,
        umask: int = 0o022,
    ) -> list[subprocess.CompletedProcess[str]]:
        results: list[subprocess.CompletedProcess[str]] = []
        environment = self._environment(repo, plugin_root)
        for index, command in enumerate(_step5_commands()):
            result = subprocess.run(
                ["/bin/sh", "-c", f"umask {umask:o}\n{command}"],
                cwd=repo,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            results.append(result)
            expected_reinit = (
                index == 1
                and result.returncode == 1
                and result.stdout == ""
                and result.stderr == REINIT_DIAGNOSTIC
            )
            if result.returncode != 0 and not expected_reinit:
                break
        return results

    def _install_provider(
        self,
        provider: str,
        *,
        version: str,
        mode: str = "pass",
    ) -> Path:
        directory = self.scratch / "bin"
        directory.mkdir(exist_ok=True)
        logs = self.scratch / "provider-logs"
        logs.mkdir(exist_ok=True)
        config = repr(
            {
                "provider": provider,
                "version": version,
                "mode": mode,
                "log": str(logs / f"{provider}.jsonl"),
            }
        )
        source = textwrap.dedent(
            f"""\
            #!{sys.executable}
            import json
            from pathlib import Path
            import sys

            CONFIG = {config}
            with Path(CONFIG["log"]).open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(sys.argv[1:]) + "\\n")
            if sys.argv[1:] == ["--version"]:
                print(CONFIG["version"])
                raise SystemExit(0)
            prompt = sys.stdin.read()
            if CONFIG["provider"] == "codex":
                if CONFIG["mode"] == "auth":
                    print(json.dumps({{"type": "error", "message": "401 Unauthorized"}}))
                    raise SystemExit(1)
                capture = Path(sys.argv[sys.argv.index("--output-last-message") + 1])
                capture.write_text("probe ok\\n", encoding="utf-8")
                print(json.dumps({{"type": "turn.completed"}}))
                raise SystemExit(0)
            print(json.dumps({{"type": "system", "subtype": "init",
                              "model": "fake-claude"}}))
            print(json.dumps({{"type": "result", "subtype": "success",
                              "is_error": False, "result": "probe ok",
                              "permission_denials": []}}))
            """
        )
        executable = directory / provider
        executable.write_text(source, encoding="utf-8")
        executable.chmod(0o755)
        return executable

    def _install_passing_providers(self) -> None:
        self._install_provider("codex", version="codex-cli 0.155.0")
        self._install_provider("claude", version="2.1.283 (Claude Code)")

    def _provider_calls(self, provider: str) -> list[list[str]]:
        path = self.scratch / "provider-logs" / f"{provider}.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines()]

    def _assert_fresh_state(self, repo: Path) -> None:
        routes = repo / ".forge/local/routes.toml"
        self.assertEqual(routes.read_bytes(), SEED_PATH.read_bytes())
        self.assertEqual(stat.S_IMODE(routes.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(routes.parent.stat().st_mode), 0o700)
        exclude = repo / ".git/info/exclude"
        self.assertEqual(exclude.read_bytes().count(b"/.forge/local/\n"), 1)
        probe_root = repo / ".forge/tmp/route-probe"
        self.assertTrue(probe_root.is_dir())
        self.assertEqual(list(probe_root.iterdir()), [])

    def test_step5_text_and_local_state_contract_are_pinned(self) -> None:
        self.assertEqual(_step5_commands(), STEP5_COMMANDS)
        text = _step5_text()
        for literal in (
            UNBORN_DIAGNOSTIC.rstrip("\n"),
            REINIT_DIAGNOSTIC.rstrip("\n"),
            "<common-root>/.forge/local/routes.toml` (0600 in a 0700 directory)",
            "one\n   `/.forge/local/` line in the common checkout's `info/exclude`",
            "<common-root>/.forge/tmp/route-probe/",
            "any failure here leaves `.forge-manifest` unchanged",
        ):
            self.assertIn(literal, text)
        skill = SKILL_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "Only after every preceding confirmation and both the route floor and route probe "
            "checks have\n   passed",
            skill,
        )
        self.assertIn(
            "Phase 0 step 5 requires\n   the branch's first commit, so an unborn branch "
            "never reaches candidate materialization.",
            skill,
        )

    def test_fresh_step5_writes_local_state_and_runs_floor_then_probe(self) -> None:
        self._install_passing_providers()
        results = self._run_step5(self.repo)
        self.assertEqual([result.returncode for result in results], [0, 0, 0, 0])
        self._assert_fresh_state(self.repo)
        for provider in ("codex", "claude"):
            calls = self._provider_calls(provider)
            self.assertEqual(calls[0], ["--version"])
            self.assertTrue(any(call != ["--version"] for call in calls))

    def test_reinit_accepts_only_the_already_exists_refusal_and_probes(self) -> None:
        self._install_passing_providers()
        self.assertEqual(self._run_step5(self.repo)[-1].returncode, 0)
        routes = self.repo / ".forge/local/routes.toml"
        original = routes.read_bytes()
        second = self._run_step5(self.repo)
        self.assertEqual(len(second), 4)
        self.assertEqual(second[1].returncode, 1)
        self.assertEqual(second[1].stderr, REINIT_DIAGNOSTIC)
        self.assertEqual(second[-1].returncode, 0)
        self.assertEqual(routes.read_bytes(), original)
        self.assertEqual(
            (self.repo / ".git/info/exclude").read_bytes().count(b"/.forge/local/\n"),
            1,
        )
        for provider in ("codex", "claude"):
            self.assertGreaterEqual(self._provider_calls(provider).count(["--version"]), 2)

    def test_probe_failure_stops_with_the_provider_diagnostic(self) -> None:
        self._install_provider("codex", version="codex-cli 0.155.0", mode="auth")
        self._install_provider("claude", version="2.1.283 (Claude Code)")
        manifest = self.repo / ".forge-manifest"
        manifest.write_bytes(b"init_completed: true\n")
        results = self._run_step5(self.repo)
        self.assertEqual([result.returncode for result in results], [0, 0, 0, 1])
        diagnostic = (
            "forge: codex launch refused — codex CLI is not logged in; "
            "run codex login manually and retry\n"
        )
        self.assertEqual(results[-1].stderr, diagnostic * 2)
        self.assertEqual(manifest.read_bytes(), b"init_completed: true\n")

    def test_unexpected_init_refusal_stops_before_floor(self) -> None:
        fake_root = self.scratch / "failing-plugin"
        scripts = fake_root / "scripts/forge"
        scripts.mkdir(parents=True)
        (scripts / "route_config.py").write_text(
            "import sys\n"
            "print('forge: route init refused — unreadable', file=sys.stderr)\n"
            "raise SystemExit(1)\n",
            encoding="utf-8",
        )
        sentinel = self.scratch / "floor-ran"
        (scripts / "route_floor.py").write_text(
            f"from pathlib import Path\nPath({str(sentinel)!r}).touch()\n",
            encoding="utf-8",
        )
        manifest = self.repo / ".forge-manifest"
        manifest.write_bytes(b"init_completed: true\n")
        results = self._run_step5(self.repo, plugin_root=fake_root)
        self.assertEqual([result.returncode for result in results], [0, 1])
        self.assertEqual(results[-1].stderr, "forge: route init refused — unreadable\n")
        self.assertFalse(sentinel.exists())
        self.assertEqual(manifest.read_bytes(), b"init_completed: true\n")

    def test_below_floor_stops_before_any_provider_probe(self) -> None:
        self._install_provider("codex", version="codex-cli 0.154.9")
        self._install_provider("claude", version="2.1.283 (Claude Code)")
        results = self._run_step5(self.repo)
        self.assertEqual([result.returncode for result in results], [0, 0, 1])
        self.assertEqual(
            results[-1].stderr,
            "forge: route floor refused — codex version 0.154.9 is below required "
            "0.155.0\n",
        )
        self.assertEqual(self._provider_calls("codex"), [["--version"]])
        self.assertFalse(any(call != ["--version"] for call in self._provider_calls("claude")))

    def test_unborn_head_stops_before_route_commands_without_local_writes(self) -> None:
        repo = self.scratch / "unborn"
        repo.mkdir()
        self.git(repo, "init", "-q")
        exclude = repo / ".git/info/exclude"
        before = exclude.read_bytes()
        fake_root = self.scratch / "must-not-run"
        scripts = fake_root / "scripts/forge"
        scripts.mkdir(parents=True)
        sentinel = self.scratch / "route-command-ran"
        for name in ("route_config.py", "route_floor.py"):
            path = scripts / name
            path.write_text(
                f"from pathlib import Path\nPath({str(sentinel)!r}).touch()\n",
                encoding="utf-8",
            )
        results = self._run_step5(repo, plugin_root=fake_root)
        self.assertEqual(len(results), 1)
        self.assertEqual((results[0].returncode, results[0].stdout), (1, ""))
        self.assertEqual(results[0].stderr, UNBORN_DIAGNOSTIC)
        self.assertFalse(sentinel.exists())
        self.assertFalse((repo / ".forge").exists())
        self.assertEqual(exclude.read_bytes(), before)
        self.assertNotIn(b"/.forge/local/", exclude.read_bytes().splitlines())

    def test_seed_header_manual_command_works_without_forge_project(self) -> None:
        repo = self.make_repo("manual")
        self.assertFalse((repo / "forge-project.md").exists())
        lines = SEED_PATH.read_text(encoding="utf-8").splitlines()
        command = next(line.removeprefix("# ") for line in lines if "<plugin-root>" in line)
        self.assertEqual(
            command,
            "python3 <plugin-root>/scripts/forge/route_config.py init --repo "
            "<absolute repo path>",
        )
        command = command.replace("<plugin-root>", str(ROOT)).replace(
            "<absolute repo path>", f'"{repo}"'
        )
        result = subprocess.run(
            ["/bin/sh", "-c", f"umask 022\n{command}"],
            cwd=repo,
            env=self._environment(repo),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        self._assert_fresh_seed_only(repo)

    def _assert_fresh_seed_only(self, repo: Path) -> None:
        routes = repo / ".forge/local/routes.toml"
        self.assertEqual(routes.read_bytes(), SEED_PATH.read_bytes())
        self.assertEqual(stat.S_IMODE(routes.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(routes.parent.stat().st_mode), 0o700)
        self.assertEqual(
            (repo / ".git/info/exclude").read_bytes().count(b"/.forge/local/\n"),
            1,
        )

    def test_step5_under_umask_002_after_ap0g_lands(self) -> None:
        self._install_passing_providers()
        results = self._run_step5(self.repo, umask=0o002)
        self.assertEqual([result.returncode for result in results], [0, 0, 0, 0])
        self._assert_fresh_state(self.repo)


if __name__ == "__main__":
    unittest.main()
