#!/usr/bin/env python3
"""Bounded, fail-loud diagnostics for Forge's GitHub Actions jobs."""
from __future__ import annotations

import argparse
import os
import re
import resource
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

PROVIDERS = ("claude", "codex")
PROBE_TIMEOUT_SECONDS = 10
PROBE_OUTPUT_BYTES = 16 * 1024
FINGERPRINT_OUTPUT_BYTES = 64 * 1024
FINGERPRINT_FIELD_BYTES = 2 * 1024
FINGERPRINT_TEMPLATE_BYTES = 12 * 1024
AUDIT_LOG_BYTES = 4 * 1024
RERUN_LOG_BYTES = 4 * 1024
RERUN_INPUT_BYTES = 1024 * 1024
RERUN_MODULE_LIMIT = 3
RERUN_MODULE_TIMEOUT = 900.0
RERUN_TOTAL_TIMEOUT = 1500.0
RERUN_EXIT_CODE = 1
SNAPSHOT_PROCESS_LIMIT = 200
SNAPSHOT_ENTRY_LIMIT = 100_000
SNAPSHOT_WALK_TIMEOUT = 30.0
SNAPSHOT_LINE_CHARS = 2048
UNAVAILABLE = "unavailable"
CPU_PRESSURE_PATH = Path("/proc/pressure/cpu")

FAILURE_LINE = re.compile(
    r"^(?:forge: drift [^|\r\n]+ \| )?"
    r"gate-1 (?P<name>test_[A-Za-z0-9_]+): exit -?\d+ ran -?\d+ "
    r"in (?:[0-9.]+|\?)s FAILED$"
)
UNITTEST_SUMMARY = re.compile(rb"^Ran \d+ tests? in [0-9.]+s$", re.MULTILINE)
PROCESS_NAME = re.compile(
    r"(?:^|[^A-Za-z0-9_])"
    r"(?:git|python\d*|bash|sh|node|claude|codex)"
    r"(?:$|[^A-Za-z0-9_])"
)


@dataclass(frozen=True)
class RerunConfig:
    root: Path
    out_dir: Path
    module_timeout: float
    total_timeout: float


@dataclass(frozen=True)
class RerunResult:
    name: str
    label: str
    returncode: int | None
    log_path: Path
    detail: str


@dataclass(frozen=True)
class WalkResult:
    entries: int
    size: int
    state: str


def _sanitize(value: str) -> str:
    return "".join(
        "?" if ord(character) < 32 and character != "\t" else character
        for character in value
    )


def _sanitized_lines(value: str) -> list[str]:
    cleaned = "".join(
        character if character in {"\n", "\t"} or ord(character) >= 32 else "?"
        for character in value
    )
    return cleaned.split("\n")


def _bounded_text(raw: bytes, limit: int) -> str:
    return raw[:limit].decode("utf-8", errors="replace")


def _bounded_line(value: str, limit: int = FINGERPRINT_FIELD_BYTES) -> str:
    safe = _sanitize(value)
    return safe.encode("utf-8")[:limit].decode("utf-8", errors="ignore")


def _run_probe(arguments: Sequence[str]) -> str:
    try:
        result = subprocess.run(
            list(arguments),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=PROBE_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return UNAVAILABLE
    if result.returncode != 0:
        return UNAVAILABLE
    output = _bounded_text(result.stdout, PROBE_OUTPUT_BYTES).strip()
    return _sanitize(output.replace("\r", " ").replace("\n", ",")) or UNAVAILABLE


def _read_umask() -> str:
    current = os.umask(0)
    try:
        return f"{current:04o}"
    finally:
        os.umask(current)


def _disk_usage(path: Path) -> str:
    try:
        usage = shutil.disk_usage(path)
    except OSError:
        return UNAVAILABLE
    return f"total={usage.total} used={usage.used} free={usage.free}"


def _which(name: str) -> str | None:
    try:
        return shutil.which(name)
    except OSError:
        return None


def _read_pressure(path: Path | None = None) -> str:
    source = path or CPU_PRESSURE_PATH
    try:
        payload = source.read_bytes()[:PROBE_OUTPUT_BYTES]
    except OSError:
        return UNAVAILABLE
    text = payload.decode("utf-8", errors="replace").strip()
    return _sanitize(text.replace("\r", " ").replace("\n", " | ")) or UNAVAILABLE


def _template_directory() -> Path | None:
    configured = _run_probe(("git", "config", "--get", "init.templateDir"))
    if configured != UNAVAILABLE:
        return Path(configured).expanduser()
    executable_path = _run_probe(("git", "--exec-path"))
    if executable_path == UNAVAILABLE:
        return None
    return Path(executable_path) / ".." / ".." / "share" / "git-core" / "templates"


def _template_modes(directory: Path | None) -> list[str]:
    if directory is None:
        return [UNAVAILABLE]
    try:
        root = directory.resolve(strict=True)
    except OSError:
        return [UNAVAILABLE]
    modes: list[str] = []
    deadline = time.monotonic() + PROBE_TIMEOUT_SECONDS
    try:
        for current, directories, files in os.walk(root, followlinks=False):
            if time.monotonic() >= deadline:
                modes.append("truncated")
                return modes
            directories.sort()
            files.sort()
            for filename in files:
                if time.monotonic() >= deadline or len(modes) >= 256:
                    modes.append("truncated")
                    return modes
                path = Path(current, filename)
                mode = stat.S_IMODE(path.stat(follow_symlinks=False).st_mode)
                modes.append(f"{path.relative_to(root)}={mode:04o}")
    except OSError:
        return modes or [UNAVAILABLE]
    return modes or [UNAVAILABLE]


def _rlimit_nofile() -> str:
    try:
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    except (OSError, ValueError):
        return UNAVAILABLE
    return f"soft={soft} hard={hard}"


def _inside_directory(path: Path, directory: Path) -> bool:
    try:
        resolved_directory = directory.resolve(strict=True)
        resolved_path = path.resolve(strict=True)
        resolved_path.relative_to(resolved_directory)
        return resolved_path.is_file()
    except (OSError, RuntimeError, ValueError):
        return False


def verify_stubs(stub_directory: Path) -> bool:
    for provider in PROVIDERS:
        resolved = _which(provider)
        if resolved is None or not _inside_directory(Path(resolved), stub_directory):
            return False
    return True


def _fingerprint_lines(expect_stubs: Path | None) -> tuple[list[str], bool]:
    runner_temp = os.environ.get("RUNNER_TEMP")
    cpu_count = os.cpu_count()
    template_directory = _template_directory()
    template_modes = _template_modes(template_directory)
    lines = [
        f"cpu.count={cpu_count if cpu_count is not None else UNAVAILABLE}",
        f"umask={_read_umask()}",
        f"git.version={_run_probe(('git', '--version'))}",
        f"git.template-dir={template_directory if template_directory is not None else UNAVAILABLE}",
    ]
    lines.extend(
        (
            f"python.version={_sanitize(sys.version.replace(chr(10), ' '))}",
            f"python.executable={sys.executable or UNAVAILABLE}",
            f"which.python3={_which('python3') or UNAVAILABLE}",
            f"which.claude={_which('claude') or UNAVAILABLE}",
            f"which.codex={_which('codex') or UNAVAILABLE}",
            f"disk./tmp={_disk_usage(Path('/tmp'))}",
            f"disk./dev/shm={_disk_usage(Path('/dev/shm'))}",
            f"disk.RUNNER_TEMP={_disk_usage(Path(runner_temp)) if runner_temp else UNAVAILABLE}",
            f"proc.pressure.cpu={_read_pressure()}",
            f"env.LANG={_sanitize(os.environ.get('LANG', UNAVAILABLE))}",
            f"env.LC_ALL={_sanitize(os.environ.get('LC_ALL', UNAVAILABLE))}",
            f"env.TMPDIR={_sanitize(os.environ.get('TMPDIR', UNAVAILABLE))}",
            f"env.CLAUDE_PLUGIN_ROOT.set={'yes' if 'CLAUDE_PLUGIN_ROOT' in os.environ else 'no'}",
            f"rlimit.nofile={_rlimit_nofile()}",
            "git.global-config-names="
            + _run_probe(("git", "config", "--global", "--name-only", "--list")),
        )
    )
    verified = expect_stubs is None or verify_stubs(expect_stubs)
    if expect_stubs is not None:
        lines.append(f"provider-stubs={'verified' if verified else 'FAILED'}")
    template_bytes = 0
    for mode in template_modes:
        line = _bounded_line(f"git.template-mode={mode}")
        size = len(line.encode("utf-8")) + 1
        if template_bytes + size > FINGERPRINT_TEMPLATE_BYTES:
            lines.append("git.template-mode=truncated")
            break
        lines.append(line)
        template_bytes += size
    return lines, verified


def fingerprint(out_path: Path, expect_stubs: Path | None = None) -> int:
    lines, verified = _fingerprint_lines(expect_stubs)
    safe_lines = [_bounded_line(line) for line in lines]
    text = "\n".join(safe_lines) + "\n"
    if len(text.encode("utf-8")) > FINGERPRINT_OUTPUT_BYTES:
        text = "forge-ci: fingerprint unavailable: output limit exceeded\n"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    return 0 if verified else 1


def _stub_script(provider: str, log_path: Path) -> str:
    quoted_log = shlex.quote(str(log_path))
    return (
        "#!/bin/sh\n"
        f"log={quoted_log}\n"
        "name=${0##*/}\n"
        "{\n"
        "  printf '%s' \"$name\"\n"
        "  for argument do\n"
        "    sanitized=$(printf '%s' \"$argument\" | "
        "LC_ALL=C tr '\\000-\\010\\012-\\037' '?')\n"
        "    printf ' %s' \"$sanitized\"\n"
        "  done\n"
        "  printf '\\n'\n"
        "} >> \"$log\"\n"
        f"printf '%s\\n' 'forge-ci: provider stub {provider} invoked; "
        "tests must not launch a real provider' >&2\n"
        "exit 97\n"
    )


def install_stubs(stub_directory: Path, log_path: Path) -> int:
    stub_directory.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.touch(exist_ok=True)
    resolved_log = log_path.resolve()
    for provider in PROVIDERS:
        stub_path = stub_directory / provider
        stub_path.write_text(_stub_script(provider, resolved_log), encoding="utf-8")
        stub_path.chmod(0o755)
    return 0


def _tail_bytes(path: Path, limit: int) -> bytes:
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - limit))
            return handle.read(limit)
    except OSError:
        return b""


def _emit_prefixed_tail(
    path: Path,
    prefix: str,
    limit: int,
    stream: object | None = None,
) -> None:
    target = sys.stdout if stream is None else stream
    payload = _tail_bytes(path, limit).decode("utf-8", errors="replace")
    for line in _sanitized_lines(payload):
        if line:
            print(prefix + line, file=target)


def stub_audit(stub_directory: Path, log_path: Path) -> int:
    problems = []
    if not stub_directory.is_dir():
        problems.append("stub directory missing")
    for provider in PROVIDERS:
        if not (stub_directory / provider).is_file():
            problems.append(f"{provider} stub missing")
    try:
        nonempty_log = log_path.exists() and log_path.stat().st_size > 0
    except OSError:
        nonempty_log = True
    if nonempty_log:
        problems.append("provider launch log is non-empty")
    if not problems:
        return 0
    for problem in problems:
        print(f"forge-ci: provider audit failed: {problem}", file=sys.stderr)
    if nonempty_log:
        _emit_prefixed_tail(
            log_path,
            "forge-ci: provider audit | ",
            AUDIT_LOG_BYTES,
            sys.stderr,
        )
    return 1


def _read_rerun_input(path: Path) -> str:
    try:
        with path.open("rb") as handle:
            return handle.read(RERUN_INPUT_BYTES).decode("utf-8", errors="replace")
    except OSError:
        return ""


def _regular_test_module(root: Path, name: str) -> bool:
    path = root / "tests" / f"{name}.py"
    try:
        mode = path.stat(follow_symlinks=False).st_mode
        path.resolve(strict=True).relative_to(root.resolve(strict=True))
    except (OSError, ValueError):
        return False
    return stat.S_ISREG(mode)


def attributable_modules(output_path: Path, root: Path) -> list[str]:
    selected: list[str] = []
    for line in _read_rerun_input(output_path).splitlines():
        match = FAILURE_LINE.fullmatch(line)
        if match is None:
            continue
        name = match.group("name")
        if name not in selected and _regular_test_module(root, name):
            selected.append(name)
        if len(selected) == RERUN_MODULE_LIMIT:
            break
    return selected


def _write_log_message(log_path: Path, message: str) -> None:
    try:
        log_path.write_text(message + "\n", encoding="utf-8")
    except OSError:
        return


def _kill_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=10)
    except (subprocess.TimeoutExpired, OSError):
        pass


def _completed_result(name: str, log_path: Path, returncode: int) -> RerunResult:
    if returncode != 0:
        return RerunResult(name, "REPRODUCIBLE", returncode, log_path, "completed")
    summary = UNITTEST_SUMMARY.search(_tail_bytes(log_path, 64 * 1024))
    if summary is not None:
        return RerunResult(name, "FLAKE-SUSPECT", returncode, log_path, "completed")
    return RerunResult(name, "INCONCLUSIVE", returncode, log_path, "missing unittest summary")


def _run_module(name: str, config: RerunConfig, deadline: float) -> RerunResult:
    log_path = config.out_dir / f"rerun-{name}.log"
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        _write_log_message(log_path, "forge-ci: total rerun deadline exhausted before launch")
        return RerunResult(name, "INCONCLUSIVE", None, log_path, "deadline exhausted")
    environment = dict(os.environ, FORGE_GATE1_NESTED="1")
    try:
        with log_path.open("wb") as output:
            process = subprocess.Popen(
                [sys.executable, "-m", "unittest", "-v", f"tests.{name}"],
                cwd=config.root,
                env=environment,
                stdout=output,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            try:
                returncode = process.wait(timeout=min(config.module_timeout, remaining))
            except subprocess.TimeoutExpired:
                _kill_process_group(process)
                return RerunResult(name, "INCONCLUSIVE", None, log_path, "timeout")
    except OSError as error:
        _write_log_message(log_path, f"forge-ci: rerun launch failed: {error}")
        return RerunResult(name, "INCONCLUSIVE", None, log_path, "launch error")
    return _completed_result(name, log_path, returncode)


def _result_line(result: RerunResult) -> str:
    exit_value = str(result.returncode) if result.returncode is not None else "none"
    return (
        f"forge-ci: rerun {result.name}: {result.label} "
        f"exit={exit_value} detail={result.detail}"
    )


def rerun(
    output_path: Path,
    out_dir: Path,
    root: Path,
    module_timeout: float | None = None,
    total_timeout: float | None = None,
) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    effective_module_timeout = module_timeout or RERUN_MODULE_TIMEOUT
    effective_total_timeout = total_timeout or RERUN_TOTAL_TIMEOUT
    config = RerunConfig(
        root.resolve(),
        out_dir,
        effective_module_timeout,
        effective_total_timeout,
    )
    modules = attributable_modules(output_path, config.root)
    summary_lines: list[str] = []
    if not modules:
        message = "forge-ci: rerun: no attributable gate-1 module line"
        print(message)
        summary_lines.append(message)
    else:
        deadline = time.monotonic() + config.total_timeout
        for name in modules:
            result = _run_module(name, config, deadline)
            line = _result_line(result)
            print(line)
            summary_lines.append(line)
            _emit_prefixed_tail(result.log_path, f"forge-ci: rerun {name} | ", RERUN_LOG_BYTES)
    try:
        (out_dir / "rerun-summary.txt").write_text(
            "\n".join(summary_lines) + "\n",
            encoding="utf-8",
        )
    except OSError as error:
        print(f"forge-ci: rerun summary unavailable: {_sanitize(str(error))}")
    return RERUN_EXIT_CODE


def _filtered_processes() -> list[str]:
    try:
        result = subprocess.run(
            ["ps", "-eo", "pid,ppid,pgid,etime,args"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=PROBE_TIMEOUT_SECONDS,
            check=False,
            text=True,
        )
    except (OSError, subprocess.TimeoutExpired):
        return [UNAVAILABLE]
    if result.returncode != 0:
        return [UNAVAILABLE]
    selected = []
    for line in result.stdout.splitlines()[1:]:
        fields = line.split(None, 4)
        if not fields or fields[0] == str(os.getpid()) or not PROCESS_NAME.search(line):
            continue
        selected.append(_sanitize(line)[:SNAPSHOT_LINE_CHARS])
        if len(selected) == SNAPSHOT_PROCESS_LIMIT:
            break
    return selected or ["none"]


def _walk_entry_size(child: os.DirEntry[str], pending: list[Path]) -> int:
    try:
        metadata = child.stat(follow_symlinks=False)
    except OSError:
        return 0
    if stat.S_ISDIR(metadata.st_mode):
        pending.append(Path(child.path))
    return metadata.st_size


def _walk_usage(root: Path) -> WalkResult:
    if not root.is_dir():
        return WalkResult(0, 0, UNAVAILABLE)
    deadline = time.monotonic() + SNAPSHOT_WALK_TIMEOUT
    entries = 0
    size = 0
    pending = [root]
    while pending:
        if time.monotonic() >= deadline:
            return WalkResult(entries, size, "timeout")
        current = pending.pop()
        try:
            children = os.scandir(current)
        except OSError:
            continue
        with children:
            for child in children:
                if time.monotonic() >= deadline:
                    return WalkResult(entries, size, "timeout")
                entries += 1
                size += _walk_entry_size(child, pending)
                if entries >= SNAPSHOT_ENTRY_LIMIT:
                    return WalkResult(entries, size, "entry-cap")
    return WalkResult(entries, size, "complete")


def _safe_snapshot_label(label: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", label)
    if safe in {"", ".", ".."}:
        return "snapshot"
    return safe[:100]


def snapshot(label: str, out_dir: Path) -> int:
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        runner_temp = os.environ.get("RUNNER_TEMP")
        roots = [("/tmp", Path("/tmp"))]
        if runner_temp:
            roots.append(("RUNNER_TEMP", Path(runner_temp)))
        lines = ["processes:"]
        lines.extend(f"process | {line}" for line in _filtered_processes())
        for name, path in roots:
            usage = _walk_usage(path)
            lines.append(
                f"walk.{name}=entries={usage.entries} size={usage.size} state={usage.state}"
            )
        if not runner_temp:
            lines.append(f"walk.RUNNER_TEMP={UNAVAILABLE}")
        target = out_dir / f"snapshot-{_safe_snapshot_label(label)}.txt"
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception as error:
        print(f"forge-ci: snapshot unavailable: {_sanitize(str(error))}", file=sys.stderr)
    return 0


def _positive_timeout(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("timeout must be positive")
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    fingerprint_parser = commands.add_parser("fingerprint")
    fingerprint_parser.add_argument("--out", required=True, type=Path)
    fingerprint_parser.add_argument("--expect-stubs", type=Path)
    install_parser = commands.add_parser("install-stubs")
    install_parser.add_argument("stub_directory", type=Path)
    install_parser.add_argument("log_path", type=Path)
    audit_parser = commands.add_parser("stub-audit")
    audit_parser.add_argument("stub_directory", type=Path)
    audit_parser.add_argument("log_path", type=Path)
    rerun_parser = commands.add_parser("rerun")
    rerun_parser.add_argument("output_path", type=Path)
    rerun_parser.add_argument("--out-dir", required=True, type=Path)
    rerun_parser.add_argument("--root", default=Path.cwd(), type=Path)
    rerun_parser.add_argument(
        "--module-timeout",
        default=RERUN_MODULE_TIMEOUT,
        type=_positive_timeout,
    )
    rerun_parser.add_argument(
        "--total-timeout",
        default=RERUN_TOTAL_TIMEOUT,
        type=_positive_timeout,
    )
    snapshot_parser = commands.add_parser("snapshot")
    snapshot_parser.add_argument("label")
    snapshot_parser.add_argument("--out-dir", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    if arguments.command == "fingerprint":
        return fingerprint(arguments.out, arguments.expect_stubs)
    if arguments.command == "install-stubs":
        return install_stubs(arguments.stub_directory, arguments.log_path)
    if arguments.command == "stub-audit":
        return stub_audit(arguments.stub_directory, arguments.log_path)
    if arguments.command == "rerun":
        return rerun(
            arguments.output_path,
            arguments.out_dir,
            arguments.root,
            arguments.module_timeout,
            arguments.total_timeout,
        )
    return snapshot(arguments.label, arguments.out_dir)


if __name__ == "__main__":
    raise SystemExit(main())
