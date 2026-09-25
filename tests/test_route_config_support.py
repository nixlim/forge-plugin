from __future__ import annotations

import io
import os
import re
import shlex
import subprocess
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORGE_SCRIPTS = ROOT / "scripts/forge"
if str(FORGE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(FORGE_SCRIPTS))

import route_config  # noqa: E402
import route_config_git  # noqa: E402
import route_config_probe  # noqa: E402

__all__ = (
    "ROOT",
    "RouteConfigSupport",
    "codex_toml",
    "route_config",
    "route_config_git",
    "route_config_probe",
    "route_text",
)


def route_text(
    role: str = "implementer",
    provider: str = "codex",
    model: str = "gpt-5.6-sol",
    effort: str = "ultra",
) -> bytes:
    return (
        'schema = "forge-routes/1"\n'
        f"[{role}]\n"
        f'provider = "{provider}"\n'
        f'model = "{model}"\n'
        f'effort = "{effort}"\n'
    ).encode()


def codex_toml(model: str, effort: str) -> str:
    return f'model = "{model}"\nmodel_reasoning_effort = "{effort}"\n'


class RouteConfigSupport:
    def setUp(self) -> None:
        super().setUp()
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.scratch = Path(self.temporary.name)
        self.repo = self.make_repo("repo")

    def git(
        self, repo: Path, *arguments: str, check: bool = True
    ) -> subprocess.CompletedProcess[bytes]:
        environment = dict(os.environ)
        environment.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull})
        return subprocess.run(
            ["git", "-C", str(repo), *arguments],
            env=environment,
            capture_output=True,
            check=check,
        )

    def make_repo(self, name: str) -> Path:
        repo = self.scratch / name
        repo.mkdir()
        self.git(repo, "init", "-q")
        self.git(repo, "config", "user.name", "Forge Tests")
        self.git(repo, "config", "user.email", "forge-tests@example.invalid")
        (repo / "README.md").write_text("fixture\n", encoding="utf-8")
        self.git(repo, "add", "README.md")
        self.git(repo, "commit", "-q", "-m", "fixture")
        return repo

    def head(self, repo: Path | None = None) -> str:
        result = self.git(repo or self.repo, "rev-parse", "HEAD")
        return result.stdout.decode().strip()

    def commit_paths(self, paths: dict[str, str], message: str = "routes") -> str:
        for relative, content in paths.items():
            target = self.repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        self.git(self.repo, "add", *paths)
        self.git(self.repo, "commit", "-q", "-m", message)
        return self.head()

    def exclude_path(self, repo: Path | None = None) -> Path:
        return (repo or self.repo) / ".git/info/exclude"

    def set_ignored(self, enabled: bool, repo: Path | None = None) -> None:
        exclude = self.exclude_path(repo)
        data = exclude.read_bytes() if exclude.exists() else b""
        lines = [line for line in data.split(b"\n") if line != route_config.EXCLUDE_LINE]
        data = b"\n".join(lines)
        if enabled:
            data += (b"" if not data or data.endswith(b"\n") else b"\n")
            data += route_config.EXCLUDE_LINE + b"\n"
        exclude.parent.mkdir(parents=True, exist_ok=True)
        exclude.write_bytes(data)

    def write_routes(
        self,
        data: bytes,
        *,
        mode: int = 0o600,
        ignored: bool = True,
        repo: Path | None = None,
    ) -> Path:
        target_repo = repo or self.repo
        self.set_ignored(ignored, target_repo)
        path = target_repo / ".forge/local/routes.toml"
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_file():
            path.chmod(0o600)
        path.write_bytes(data)
        path.chmod(mode)
        return path

    def load(self, repo: Path | None = None) -> route_config.RouteResolution:
        target = repo or self.repo
        return route_config.load(target, head=self.head(target))

    def assert_route_refusal(self, cause: str, repo: Path | None = None) -> None:
        expected = f"forge: routes file refused — {cause}"
        with self.assertRaisesRegex(route_config.RouteRefusal, f"^{re.escape(expected)}$"):
            self.load(repo)

    def invoke(self, *arguments: str) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = route_config.main(list(arguments))
        return status, stdout.getvalue(), stderr.getvalue()

    def fake_executable(self, name: str, body: str) -> Path:
        directory = self.scratch / "bin"
        directory.mkdir(exist_ok=True)
        path = directory / name
        path.write_text("#!/bin/sh\nset -eu\n" + body, encoding="utf-8")
        path.chmod(0o755)
        return path

    def shell_path(self, path: Path) -> str:
        return shlex.quote(str(path))

    def probe_environment(self) -> dict[str, str]:
        home = self.scratch / "home"
        home.mkdir(exist_ok=True)
        return {
            "HOME": str(home),
            "PATH": f"{self.scratch / 'bin'}:/usr/bin:/bin",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "USER": "forge-test",
            "TMPDIR": str(self.scratch),
            "TERM": "dumb",
            "CODEX_HOME": str(self.scratch / "codex-home"),
            "ANTHROPIC_BASE_URL": "https://api.example.invalid",
            "ANTHROPIC_AUTH_TOKEN": "token",
            "ANTHROPIC_API_KEY": "secret",
            "CLAUDE_CODE_USE_BEDROCK": "1",
            "CLAUDE_CODE_USE_VERTEX": "1",
            "AWS_REGION": "test-region",
            "GOOGLE_APPLICATION_CREDENTIALS": "credential-path",
            "CLOUD_ML_REGION": "cloud-region",
            "FORGE_SESSION_PID": "forbidden",
            "CLAUDE_PID": "forbidden",
            "CLAUDE_CODE_SESSION_ID": "forbidden",
            "ANTHROPIC_MODEL": "forbidden",
            "ANTHROPIC_DEFAULT_HAIKU_MODEL": "forbidden",
            "CODEX_UNSAFE": "forbidden",
        }
