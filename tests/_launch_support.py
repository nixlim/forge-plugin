"""Shared fixtures for the typed implementer and plan launch lane."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import signal
import subprocess
import sys
import textwrap
import time
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock

from tests._cli_loader import load_cli, package_module, patch_engine
from tests._review_lane_support import install_fake_provider
from tests._revision9_coord_constants import key
from tests._revision9_coord_support import Revision9BuilderBatchSupport

ROOT = Path(__file__).resolve().parents[1]
STRIPPED_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
CLI = load_cli("forge_launch_support_cli")
ENGINE = package_module("engine")
LAUNCH_LANE = importlib.import_module("forge_cli.engine._launch_lane")
VERBS_LAUNCH = importlib.import_module("forge_cli.engine._verbs_launch")
VERBS_LAUNCH_COLLECT = importlib.import_module(
    "forge_cli.engine._verbs_launch_collect"
)
REVIEW_ATTEMPT = importlib.import_module("forge_cli.engine._review_attempt")
ROUTE_CONFIG = importlib.import_module("route_config")
RUNTIME = package_module("runtime")


def _launch_fake_source(
    provider: str,
    mode: str,
    version: str,
    log_dir: Path,
) -> str:
    config = repr(
        {
            "provider": provider,
            "mode": mode,
            "version": version,
            "log_dir": str(log_dir),
        }
    )
    return textwrap.dedent(
        f"""\
        #!{sys.executable}
        import json
        import os
        from pathlib import Path
        import subprocess
        import sys
        import time

        CONFIG = {config}
        provider, mode = CONFIG["provider"], CONFIG["mode"]
        logs = Path(CONFIG["log_dir"])
        logs.mkdir(parents=True, exist_ok=True)

        if sys.argv[1:] == ["--version"]:
            (logs / f"{{provider}}.version-argv.json").write_text(
                json.dumps(sys.argv[1:]), encoding="utf-8"
            )
            print(CONFIG["version"])
            raise SystemExit(0)

        prompt = sys.stdin.read()
        (logs / f"{{provider}}.argv.json").write_text(
            json.dumps(sys.argv[1:]), encoding="utf-8"
        )
        (logs / f"{{provider}}.prompt").write_text(prompt, encoding="utf-8")
        (logs / f"{{provider}}.cwd").write_text(os.getcwd(), encoding="utf-8")
        (logs / f"{{provider}}.environment.json").write_text(
            json.dumps(dict(os.environ), sort_keys=True), encoding="utf-8"
        )
        handoff = "fixture launch handoff\\n"
        if mode == "oversize-handoff":
            handoff = "x" * 65537
        elif mode == "redaction-handoff":
            handoff = (
                "agents/review-final.md\\n"
                f"user={{os.environ['USER']}}\\n"
                f"home={{os.environ['HOME']}}\\n"
                f"planted={{os.environ['ANTHROPIC_API_KEY']}}\\n"
            )
        if mode == "bad-line":
            print("not json", flush=True)
            raise SystemExit(0)
        if provider == "claude":
            if mode == "missing-init":
                raise SystemExit(0)
            if mode == "result-first":
                print(json.dumps({{"type": "result", "is_error": False,
                                  "result": handoff}}), flush=True)
                raise SystemExit(0)
            permission_modes = [
                sys.argv[index + 1]
                for index, argument in enumerate(sys.argv[:-1])
                if argument == "--permission-mode"
                and sys.argv[index + 1]
                and not sys.argv[index + 1].startswith("-")
            ]
            permission_mode = "bypassPermissions" \
                if "--dangerously-skip-permissions" in sys.argv else "default"
            if permission_mode == "default" and permission_modes:
                position = -1 if mode == "permission-mode-last" else 0
                permission_mode = permission_modes[position]
            tools = sys.argv[sys.argv.index("--tools") + 1].split(",")
            init = {{"type": "system", "subtype": "init", "model": "claude-fixture",
                    "permissionMode": permission_mode, "tools": tools}}
            if mode == "wrong-mode":
                init["permissionMode"] = (
                    "default" if permission_mode != "default" else "bypassPermissions"
                )
            elif mode == "missing-mode":
                del init["permissionMode"]
            elif mode == "missing-tool":
                init["tools"] = tools[:-1]
            elif mode == "extra-tool":
                init["tools"] = tools + ["UnexpectedTool"]
            elif mode == "duplicate-tool":
                init["tools"] = tools + tools[:1]
            elif mode == "reordered-tools":
                init["tools"] = list(reversed(tools))
            print(json.dumps(init), flush=True)
        if mode == "fork-sleeper":
            child = subprocess.Popen(
                [sys.executable, "-c", "import time; time.sleep(300)"]
            )
            (logs / f"{{provider}}.grandchild-pid").write_text(
                str(child.pid), encoding="ascii"
            )
        if mode in {{"hang", "fork-sleeper"}}:
            while True:
                time.sleep(1)
        if mode == "nonzero":
            print("fake launch provider failed", file=sys.stderr)
            raise SystemExit(9)

        if provider == "codex":
            if mode == "auth":
                print(json.dumps({{"type": "error", "message": "401 Unauthorized"}}))
                raise SystemExit(1)
            if mode not in {{"missing-handoff", "empty-handoff"}}:
                output = Path(sys.argv[sys.argv.index("--output-last-message") + 1])
                output.write_text(handoff, encoding="utf-8")
            elif mode == "empty-handoff":
                output = Path(sys.argv[sys.argv.index("--output-last-message") + 1])
                output.write_text("", encoding="utf-8")
            print(json.dumps({{"type": "turn.completed"}}), flush=True)
            raise SystemExit(0)

        if mode == "auth":
            result = {{"type": "result", "subtype": "success", "is_error": True,
                      "result": "Not logged in - run /login"}}
        elif mode == "error-result":
            result = {{"type": "result", "subtype": "success", "is_error": True,
                      "result": handoff}}
        elif mode == "missing-handoff":
            result = {{"type": "assistant", "message": {{"model": "claude-fixture"}}}}
        else:
            result = {{"type": "result", "subtype": "success", "is_error": False,
                      "result": "" if mode == "empty-handoff" else handoff}}
        print(json.dumps(result), flush=True)
        """
    )


def install_launch_provider(
    directory: Path,
    provider: str,
    *,
    mode: str = "pass",
    version: str | None = None,
    log_dir: Path | None = None,
    executable_name: str | None = None,
) -> Path:
    """Install a provider fake that emits a launch handoff, not a review verdict."""

    if provider not in {"codex", "claude"}:
        raise ValueError(f"unsupported fake provider: {provider}")
    versions = {"codex": "codex-cli 0.155.0", "claude": "2.1.283 (Claude Code)"}
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (executable_name or provider)
    path.write_text(
        _launch_fake_source(
            provider, mode, version or versions[provider], log_dir or directory
        ),
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


class LaunchLaneSupport(Revision9BuilderBatchSupport):
    """Fixture repository, explicit providers, and direct typed-verb helpers."""

    run_id = "run-20260928-launch-test"
    task_id = "task-01"

    def setUp(self) -> None:
        super().setUp()
        self.scratch = Path(self.temporary.name).resolve(strict=True)
        self.bin_dir = self.scratch / "bin"
        self.logs = self.scratch / "logs"
        self.home = self.scratch / "home"
        self.brief = self.scratch / "brief.md"
        self.linked_worktree = self.scratch / "linked-worktree"
        for directory in (self.bin_dir, self.logs, self.home):
            directory.mkdir(parents=True, exist_ok=True)
        self.brief.write_text("fixture task assignment\n", encoding="utf-8")
        self.brief.chmod(0o600)
        self._install_committed_launch_inputs()
        subprocess.run(
            ["git", "-C", str(self.repo), "worktree", "add", "--quiet", "--detach",
             str(self.linked_worktree), self.head],
            check=True,
        )
        self._routes: dict[str, tuple[str, str, str]] = {}
        codex = self.install_provider("codex")
        claude = self.install_provider("claude")
        self.env = self.environment(FORGE_SESSION_PID=str(os.getpid()))
        environment_patch = mock.patch.dict(os.environ, self.env, clear=True)
        environment_patch.start()
        self.addCleanup(environment_patch.stop)
        self.enterContext(patch_engine("CODEX_EXECUTABLE", str(codex)))
        self.enterContext(patch_engine("CLAUDE_EXECUTABLE", str(claude)))
        plugin_patch = mock.patch.object(RUNTIME, "PLUGIN_ROOT", ROOT)
        plugin_patch.start()
        self.addCleanup(plugin_patch.stop)

    def _install_committed_launch_inputs(self) -> None:
        inputs = {
            ".forge-manifest": "init_completed: true\n",
            "forge-project.md": (ROOT / "forge-project.md").read_text(encoding="utf-8"),
            "src/example.py": "VALUE = 1\n",
        }
        for relative, content in inputs.items():
            target = self.repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        subprocess.run(
            ["git", "-C", str(self.repo), "add", *inputs], check=True
        )
        subprocess.run(
            [
                "git", "-C", str(self.repo), "-c", "user.name=Forge Tests",
                "-c", "user.email=forge-tests@example.invalid",
                "-c", "commit.gpgsign=false", "commit", "--quiet",
                "-m", "launch fixture inputs",
            ],
            check=True,
        )
        self.head = subprocess.run(
            ["git", "-C", str(self.repo), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def environment(self, **updates: str) -> dict[str, str]:
        environment = {
            "HOME": str(self.home),
            "PATH": STRIPPED_PATH,
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "USER": "forge-test-user",
            "TMPDIR": str(self.scratch),
            "TERM": "dumb-terminal",
            "CODEX_HOME": str(self.scratch / "codex-home"),
            "ANTHROPIC_API_KEY": "anthropic-fixture-key",
            "CLAUDE_PLUGIN_ROOT": str(ROOT),
        }
        environment.update(updates)
        return environment

    def install_provider(
        self,
        provider: str,
        *,
        mode: str = "pass",
        version: str | None = None,
        executable_name: str | None = None,
    ) -> Path:
        return install_launch_provider(
            self.bin_dir,
            provider,
            mode=mode,
            version=version,
            log_dir=self.logs,
            executable_name=executable_name,
        )

    def install_mode_provider(self, provider: str, mode: str) -> Path:
        return self.install_provider(
            provider, mode=mode, executable_name=f"{provider}-{mode}"
        )

    def install_review_provider(self, provider: str, *, mode: str = "pass") -> Path:
        """Expose E's verdict-producing fake for tests that need it explicitly."""

        return install_fake_provider(
            self.bin_dir, provider, mode=mode, log_dir=self.logs,
            executable_name=f"{provider}-review-{mode}",
        )

    def configure_route(
        self,
        role: str,
        provider: str,
        *,
        model: str | None = None,
        effort: str | None = None,
    ) -> None:
        defaults = {
            "codex": ("gpt-5.6-sol", "high"),
            "claude": ("claude-fixture", "high"),
        }
        default_model, default_effort = defaults[provider]
        self._routes[role] = (
            provider, model or default_model, effort or default_effort
        )
        local = self.repo / ".forge/local/routes.toml"
        local.parent.mkdir(parents=True, exist_ok=True)
        lines = ['schema = "forge-routes/1"']
        for route_role in ROUTE_CONFIG.ROLES:
            if route_role not in self._routes:
                continue
            route_provider, route_model, route_effort = self._routes[route_role]
            lines.extend(
                (
                    "",
                    f"[{route_role}]",
                    f'provider = "{route_provider}"',
                    f'model = "{route_model}"',
                    f'effort = "{route_effort}"',
                )
            )
        local.write_text("\n".join(lines) + "\n", encoding="utf-8")
        local.chmod(0o600)
        exclude = self.repo / ".git/info/exclude"
        data = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
        if "/.forge/local/\n" not in data:
            exclude.write_text(data + "/.forge/local/\n", encoding="utf-8")

    def route(self, provider: str, role: str) -> Any:
        self.configure_route(role, provider)
        return ROUTE_CONFIG.resolve(self.linked_worktree, role, self.head)

    def open_run_and_task(self, run_id: str | None = None) -> tuple[Any, Any]:
        selected = run_id or self.run_id
        _batch, builders, _journal = RUNTIME._coordination_modules()
        with self.api_environment():
            opened = builders.run_open(
                self.repo, selected, idempotency_key=key(f"{selected}-open"),
                goal="Exercise typed launch", scope=[f"scopes/{selected}/**"],
                plugin_ref="forge-test-typed-launch",
            )
            task = builders.task_start(
                self.repo, selected, idempotency_key=key(f"{selected}-task"),
                task=self.task_id, goal="Exercise typed launch",
                acceptance=["The focused behavior passes"],
                files=[f"scopes/{selected}/example.py"],
            )
        return opened, task

    def ready_engine(
        self, run_id: str | None = None, *, open_task: bool = True
    ) -> Any:
        selected = run_id or self.run_id
        if open_task and not self.run_dir(self.repo, selected).exists():
            self.open_run_and_task(selected)
        repository = CLI.Repository(self.repo)
        context = CLI.CommandContext(
            repository,
            CLI.ChainStore(repository.common_root()),
            CLI.CLIOptions(repo=str(self.repo), run_id=selected),
        )
        return CLI.Engine(context)

    def records(self, run_id: str | None = None) -> list[dict[str, object]]:
        selected = run_id or self.run_id
        _batch, _builders, journal = RUNTIME._coordination_modules()
        return list(journal._scan_run(self.run_dir(self.repo, selected)).records)

    def execution_records(
        self, run_id: str | None = None
    ) -> list[dict[str, object]]:
        return [record for record in self.records(run_id) if record.get("type") == "execution"]

    def attempt_dir(self, record: Mapping[str, object] | None = None) -> Path:
        selected = record or self.execution_records()[-1]
        return self.run_dir(self.repo, self.run_id) / str(selected["agent"]) / str(
            selected["execution"]
        )

    def paths(
        self, record: Mapping[str, object] | None = None
    ) -> Any:
        selected = record or self.execution_records()[-1]
        return LAUNCH_LANE.LaunchPaths(
            self.run_dir(self.repo, self.run_id),
            str(selected["agent"]),
            str(selected["execution"]),
        )

    def marker(self, record: Mapping[str, object] | None = None) -> dict[str, Any]:
        selected = record or self.execution_records()[-1]
        return LAUNCH_LANE.read_marker(self.attempt_dir(selected) / "launch.json")

    def live_identity(
        self, record: Mapping[str, object] | None = None,
        wrapper_pid: int = 77, reviewer_pid: int | None = 88,
        *, attempt: str | None = None,
        starttimes: tuple[int, int] | None = None,
    ) -> dict[str, object]:
        wrapper_start, reviewer_start = starttimes or (
            wrapper_pid,
            reviewer_pid or wrapper_pid,
        )
        wrapper_birth = {
            "kind": "linux-proc", "boot_id": "fixture", "starttime": wrapper_start,
        }
        reviewer_birth = None if reviewer_pid is None else {
            "kind": "linux-proc", "boot_id": "fixture", "starttime": reviewer_start,
        }
        return {
            "schema": REVIEW_ATTEMPT.IDENTITY_SCHEMA,
            "attempt": attempt or self.marker(record)["attempt"],
            "wrapper_pid": wrapper_pid, "pgid": wrapper_pid,
            "wrapper_birth": wrapper_birth, "reviewer_pid": reviewer_pid,
            "reviewer_birth": reviewer_birth,
            "started_at": "2026-09-28T12:00:00Z",
        }

    def write_identity(
        self, identity: Mapping[str, object], record: Mapping[str, object] | None = None,
    ) -> Path:
        directory = self.attempt_dir(record)
        LAUNCH_LANE.write_owner_file(
            directory, REVIEW_ATTEMPT.IDENTITY_NAME,
            ENGINE.chain_core.canonical_bytes(dict(identity)) + b"\n",
        )
        return directory / REVIEW_ATTEMPT.IDENTITY_NAME

    def write_private_json(self, path: Path, value: Mapping[str, object]) -> bytes:
        raw = ENGINE.chain_core.canonical_bytes(dict(value)) + b"\n"
        LAUNCH_LANE.replace_owner_file(path.parent, path.name, raw)
        return raw

    def wrapper_config(
        self, record: Mapping[str, object] | None = None
    ) -> dict[str, object]:
        selected = record or self.execution_records()[-1]
        marker = self.marker(selected)
        paths = self.paths(selected)
        argv = LAUNCH_LANE.marker_argv(marker, paths)
        return LAUNCH_LANE.wrapper_config(marker, argv)

    def launch_direct(
        self,
        *,
        role: str = "implementer",
        provider: str | None = None,
        engine: Any | None = None,
        worktree: Path | None = None,
        brief: Path | None = None,
    ) -> Any:
        if provider is not None:
            self.configure_route(role, provider)
        selected_engine = engine or self.ready_engine()
        selected_worktree = worktree or self.linked_worktree
        return VERBS_LAUNCH.launch(
            selected_engine,
            role=role,
            task=self.task_id,
            worktree=str(selected_worktree),
            brief=str(brief or self.brief),
        )

    def seed_launch(
        self,
        *,
        role: str = "implementer",
        provider: str | None = None,
        engine: Any | None = None,
        worktree: Path | None = None,
        brief: Path | None = None,
    ) -> Any:
        """Create the owner record and marker without starting a live wrapper."""

        self.spawn_calls: list[tuple[tuple[str, ...], dict[str, object]]] = []

        def capture(
            launcher_argv: tuple[str, ...], **kwargs: object
        ) -> SimpleNamespace:
            self.spawn_calls.append((tuple(launcher_argv), dict(kwargs)))
            return SimpleNamespace(pid=424_242)

        with patch_engine("spawn_wrapper", side_effect=capture):
            return self.launch_direct(
                role=role,
                provider=provider,
                engine=engine,
                worktree=worktree,
                brief=brief,
            )

    def _captured_wrapper_config(self) -> dict[str, object]:
        return decode_launcher(self.spawn_calls[-1][0])

    def _assert_no_attempt(self) -> None:
        self.assertFalse(self.execution_records())
        run_dir = self.run_dir(self.repo, self.run_id)
        self.assertFalse(
            any(path.name.startswith(("codex-", "claude-")) for path in run_dir.iterdir())
        )


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def decode_launcher(launcher_argv: tuple[str, ...]) -> dict[str, object]:
    value = json.loads(launcher_argv[-1])
    if not isinstance(value, dict):
        raise AssertionError("wrapper launcher config was not an object")
    return value


def wait_path(path: Path, timeout: float = 10.0) -> Path:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return path
        time.sleep(0.02)
    raise AssertionError(f"path did not appear within {timeout:g}s: {path}")


def wait_process_gone(pid: int, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        process = subprocess.run(
            ["ps", "-o", "stat=", "-p", str(pid)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
        if process.returncode or process.stdout.lstrip().startswith("Z"):
            return
        time.sleep(0.02)
    raise AssertionError(f"process {pid} survived for {timeout:g}s")


def kill_group(pgid: int) -> None:
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        pass


__all__ = (
    "CLI",
    "ENGINE",
    "LAUNCH_LANE",
    "ROOT",
    "STRIPPED_PATH",
    "LaunchLaneSupport",
    "VERBS_LAUNCH",
    "VERBS_LAUNCH_COLLECT",
    "decode_launcher",
    "digest",
    "install_launch_provider",
    "kill_group",
    "wait_path",
    "wait_process_gone",
)
