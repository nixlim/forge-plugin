"""Shared fake-provider support for the headless review lane tests.

The fakes deliberately select their behaviour through their executable bytes, not
through an environment variable: the review lane's provider allowlist must not be
widened merely to make tests convenient.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import sys
import tempfile
import textwrap
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from tests._cli_loader import package_module

ROOT = Path(__file__).resolve().parents[1]
ENGINE = package_module("engine")

_CANDIDATE = "1" * 64
_PACKAGE = "2" * 64


def review_prompt(
    candidate: str = _CANDIDATE,
    package: str = _PACKAGE,
) -> bytes:
    """Return the smallest prompt that still exercises verdict binding."""

    return (
        "Review this candidate.\n"
        f"candidate: {candidate}\n"
        f"package: {package}\n"
    ).encode()


def verdict_for_prompt(prompt: str, verdict: str = "PASS") -> str:
    """Build a bound verdict from the two digest lines in ``prompt``."""

    candidate = _digest_line(prompt, "candidate")
    package = _digest_line(prompt, "package")
    finding = "finding: MAJOR fake provider block\n" if verdict == "BLOCK" else ""
    return (
        f"VERDICT: {verdict}\n"
        f"candidate: {candidate}\n"
        f"package: {package}\n"
        f"{finding}"
    )


def _digest_line(prompt: str, name: str) -> str:
    prefix = f"{name}: "
    matches = [line[len(prefix) :] for line in prompt.splitlines() if line.startswith(prefix)]
    lengths = {40, 64} if name == "candidate" else {64}
    if (
        not matches
        or any(len(value) not in lengths for value in matches)
        or len(set(matches)) != 1
    ):
        raise ValueError(f"fake provider needs one {name} digest")
    return matches[0]


def _fake_source(
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
        provider = CONFIG["provider"]
        mode = CONFIG["mode"]
        logs = Path(CONFIG["log_dir"])
        logs.mkdir(parents=True, exist_ok=True)

        if sys.argv[1:] == ["--version"]:
            (logs / f"{{provider}}.version-argv.json").write_text(
                json.dumps(sys.argv[1:]), encoding="utf-8"
            )
            (logs / f"{{provider}}.version-environment.json").write_text(
                json.dumps(dict(os.environ), sort_keys=True), encoding="utf-8"
            )
            if mode == "version-nonzero":
                print("version probe failed", file=sys.stderr)
                raise SystemExit(9)
            if mode == "version-unparseable":
                print("unknown provider build")
                raise SystemExit(0)
            if mode == "version-hang":
                while True:
                    time.sleep(1)
            if mode == "version-oversize":
                print("x" * 5000)
                raise SystemExit(0)
            if mode == "version-oversize-stderr":
                print("x" * 5000, file=sys.stderr)
                raise SystemExit(0)
            print(CONFIG["version"])
            raise SystemExit(0)

        prompt = sys.stdin.read()
        (logs / f"{{provider}}.argv.json").write_text(
            json.dumps(sys.argv[1:]), encoding="utf-8"
        )
        (logs / f"{{provider}}.prompt").write_text(prompt, encoding="utf-8")
        (logs / f"{{provider}}.environment.json").write_text(
            json.dumps(dict(os.environ), sort_keys=True), encoding="utf-8"
        )

        def digest_line(name):
            prefix = name + ": "
            values = [line[len(prefix):] for line in prompt.splitlines()
                      if line.startswith(prefix)]
            lengths = {{40, 64}} if name == "candidate" else {{64}}
            if (not values or any(len(value) not in lengths for value in values)
                    or len(set(values)) != 1):
                raise SystemExit(8)
            return values[0]

        candidate = digest_line("candidate")
        package = digest_line("package")
        verdict = "BLOCK" if mode == "block" else "PASS"
        finding = "finding: MAJOR fake provider block\\n" if verdict == "BLOCK" else ""
        result = (f"VERDICT: {{verdict}}\\n"
                  f"candidate: {{candidate}}\\n"
                  f"package: {{package}}\\n" + finding)

        if mode == "bad-line":
            print("this is not json", flush=True)
            raise SystemExit(0)
        if provider == "claude":
            if mode == "missing-init":
                raise SystemExit(0)
            if mode == "result-first":
                print(json.dumps({{"type": "result", "is_error": False,
                                  "result": result}}), flush=True)
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
            init = {{"type": "system", "subtype": "init", "model": "claude-init",
                    "agents": ["fixture"], "permissionMode": permission_mode,
                    "tools": tools}}
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

        if mode in {{"fork-sleeper", "drop-descriptors"}}:
            child = subprocess.Popen(
                [sys.executable, "-c", "import time; time.sleep(300)"],
                close_fds=(mode == "drop-descriptors"),
            )
            (logs / f"{{provider}}.grandchild-pid").write_text(
                str(child.pid), encoding="ascii"
            )
        if mode == "hang":
            while True:
                time.sleep(1)
        if mode == "nonzero":
            print("fake provider failed", file=sys.stderr)
            raise SystemExit(9)

        if provider == "codex":
            if mode == "auth":
                print(json.dumps({{"type": "error", "message": "401 Unauthorized"}}))
                raise SystemExit(1)
            if mode not in {{"no-verdict", "empty-verdict"}}:
                output = Path(sys.argv[sys.argv.index("--output-last-message") + 1])
                temporary = output.with_name(output.name + ".fake-tmp")
                temporary.write_text("" if mode == "empty-verdict" else result,
                                     encoding="utf-8")
                os.replace(temporary, output)
            print(json.dumps({{"type": "turn.completed"}}), flush=True)
            raise SystemExit(0)

        print(json.dumps({{"type": "assistant",
                           "message": {{"model": "claude-message"}}}}), flush=True)
        if mode == "auth":
            event = {{"type": "result", "subtype": "success", "is_error": True,
                     "result": "Not logged in - run /login"}}
        elif mode == "error-result":
            event = {{"type": "result", "subtype": "success", "is_error": True,
                     "result": result}}
        elif mode == "model-usage":
            event = {{"type": "result", "is_error": False, "result": result,
                     "modelUsage": {{"claude-usage": {{"inputTokens": 1}}}}}}
        else:
            event = {{"type": "result", "subtype": "error" if mode == "pass" else "success",
                     "is_error": False, "result": result}}
        print(json.dumps(event), flush=True)
        """
    )


def install_fake_provider(
    directory: Path,
    provider: str,
    *,
    mode: str = "pass",
    version: str | None = None,
    log_dir: Path | None = None,
    executable_name: str | None = None,
) -> Path:
    """Install a mode-specific ``codex`` or ``claude`` executable."""

    if provider not in {"codex", "claude"}:
        raise ValueError(f"unsupported fake provider: {provider}")
    versions = {"codex": "codex-cli 0.155.0", "claude": "2.1.283 (Claude Code)"}
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (executable_name or provider)
    path.write_text(
        _fake_source(provider, mode, version or versions[provider], log_dir or directory),
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def wait_for_completion(
    completion: Path,
    *,
    collect: Callable[[], Any] | None = None,
    timeout: float = 10.0,
) -> Any:
    """Poll a bounded asynchronous attempt, optionally invoking collect each turn."""

    deadline = time.monotonic() + timeout
    observed = None
    while time.monotonic() < deadline:
        if completion.exists():
            return observed if collect is not None else json.loads(completion.read_text())
        if collect is not None:
            observed = collect()
        time.sleep(0.02)
    raise AssertionError(f"review completion was not published within {timeout:g}s")


class ReviewLaneSupport:
    """Mixin providing isolated provider binaries, paths, and environment."""

    def setUp(self) -> None:
        super().setUp()
        self._review_temporary = tempfile.TemporaryDirectory(prefix="forge-review-lane-")
        self.addCleanup(self._review_temporary.cleanup)
        self.scratch = Path(self._review_temporary.name)
        self.bin_dir = self.scratch / "bin"
        self.logs = self.scratch / "logs"
        self.worktree = self.scratch / "worktree"
        self.plugin_root = self.scratch / "plugin"
        self.attempt_dir = self.scratch / "attempt-0123456789abcdef"
        for path in (self.bin_dir, self.logs, self.worktree, self.plugin_root, self.attempt_dir):
            path.mkdir(parents=True)

    def install_provider(
        self,
        provider: str,
        *,
        mode: str = "pass",
        version: str | None = None,
        executable_name: str | None = None,
    ) -> Path:
        return install_fake_provider(
            self.bin_dir,
            provider,
            mode=mode,
            version=version,
            log_dir=self.logs,
            executable_name=executable_name,
        )

    def install_mode_provider(self, provider: str, mode: str) -> Path:
        """Install a mode-specific fake without replacing the default provider."""

        return self.install_provider(
            provider,
            mode=mode,
            executable_name=f"{provider}-{mode}",
        )

    def environment(self, **updates: str) -> dict[str, str]:
        home = self.scratch / "home"
        home.mkdir(exist_ok=True)
        environment = {
            "HOME": str(home),
            "PATH": os.pathsep.join((str(self.bin_dir), "/usr/bin", "/bin")),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "USER": "forge-test-user",
            "TMPDIR": str(self.scratch),
            "TERM": "dumb-terminal",
            "CODEX_HOME": str(self.scratch / "codex-home"),
            "ANTHROPIC_API_KEY": "anthropic-secret",
            "ANTHROPIC_AUTH_TOKEN": "anthropic-token",
            "AWS_REGION": "test-region",
            "CLAUDE_CODE_USE_BEDROCK": "1",
            "CLAUDE_CODE_USE_VERTEX": "1",
            "FORGE_TEST_FORBIDDEN": "must-not-pass",
        }
        environment.update(updates)
        return environment

    def paths(self) -> Any:
        """Construct ``ReviewPaths`` while tolerating harmless field renames in flight."""

        attempt = self.attempt_dir
        role_body = b"fixture review-final body\n"
        values: Mapping[str, object] = {
            "chain_id": "c-fixture-review-lane",
            "attempt": attempt.name,
            "attempt_relative": f"review/iteration-01/{attempt.name}",
            "worktree": self.worktree,
            "plugin_root": self.plugin_root,
            "attempt_dir": attempt,
            "package_path": attempt / "package.txt",
            "prompt_path": attempt / "prompt.txt",
            "events_path": attempt / "events.jsonl",
            "stderr_path": attempt / "stderr.log",
            "identity_path": attempt / "identity.json",
            "completion_path": attempt / "completion.json",
            "verdict_path": attempt / "verdict.txt",
            "staging_path": attempt / "verdict.staging",
            "codex_staging_path": attempt / "verdict.staging",
            "role_body_path": attempt / "review-final-body.md",
            "review_final_body_path": attempt / "review-final-body.md",
            "role_body": role_body,
            "role_body_digest": hashlib.sha256(role_body).hexdigest(),
        }
        parameters = inspect.signature(ENGINE.ReviewPaths).parameters
        return ENGINE.ReviewPaths(**{name: values[name] for name in parameters})


__all__ = (
    "ENGINE",
    "ROOT",
    "ReviewLaneSupport",
    "install_fake_provider",
    "review_prompt",
    "verdict_for_prompt",
    "wait_for_completion",
)
