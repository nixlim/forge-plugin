from __future__ import annotations

import re
import unittest
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CI_PATH = ROOT / ".github/workflows/forge-ci.yml"
DRIFT_PATH = ROOT / ".github/workflows/forge-drift.yml"
CHECKOUT_SHA = "11d5960a326750d5838078e36cf38b85af677262"
PYTHON_SHA = "a26af69be951a213d495a4c3e4e4022e16d87065"
UPLOAD_SHA = "ea165f8d65b6e75b540449e92b4886f43607fa02"
CLAUDE_PACKAGE = "@anthropic-ai/claude-code@2.1.283"
CODEX_PACKAGE = "@openai/codex@0.155.1"
STEP_ITEM = re.compile(r"^(?P<indent> *)-(?:\s+|$)")
FIELD = r"^\s*(?:-\s+)?{name}:\s*(?P<value>.*?)\s*$"
SHELL_WORD = r'''(?:"[^"\n]*"|'[^'\n]*'|[^\s#]+)'''


@dataclass(frozen=True)
class WorkflowStep:
    start: int
    end: int
    body: str

    def field(self, name: str) -> str | None:
        pattern = re.compile(FIELD.format(name=re.escape(name)), re.MULTILINE)
        match = pattern.search(self.body)
        return match.group("value") if match else None


def _require(condition: object, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _steps(text: str) -> list[WorkflowStep]:
    lines = text.splitlines(keepends=True)
    headers = [index for index, line in enumerate(lines) if line.strip() == "steps:"]
    _require(len(headers) == 1, "workflow must have exactly one steps list")
    header = headers[0]
    header_indent = len(lines[header]) - len(lines[header].lstrip(" "))
    starts = []
    for index in range(header + 1, len(lines)):
        match = STEP_ITEM.match(lines[index])
        if match and len(match.group("indent")) == header_indent + 2:
            starts.append(index)
    _require(starts, "workflow must have steps")
    ends = [*starts[1:], len(lines)]
    return [
        WorkflowStep(start, end, "".join(lines[start:end]))
        for start, end in zip(starts, ends, strict=True)
    ]


def _find_step(steps: list[WorkflowStep], needle: str) -> tuple[int, WorkflowStep]:
    matches = [(index, step) for index, step in enumerate(steps) if needle in step.body]
    _require(len(matches) == 1, f"expected one workflow step containing {needle!r}")
    return matches[0]


def _on_keys(text: str) -> set[str]:
    lines = text.splitlines()
    starts = [index for index, line in enumerate(lines) if line == "on:"]
    _require(len(starts) == 1, "workflow must have one top-level on mapping")
    keys = set()
    for line in lines[starts[0] + 1 :]:
        if line and not line.startswith(" "):
            break
        match = re.match(r"^  ([A-Za-z_][A-Za-z0-9_-]*):", line)
        if match:
            keys.add(match.group(1))
    return keys


def _job_keys(text: str) -> set[str]:
    lines = text.splitlines()
    starts = [index for index, line in enumerate(lines) if line == "jobs:"]
    _require(len(starts) == 1, "workflow must have one top-level jobs mapping")
    keys = set()
    for line in lines[starts[0] + 1 :]:
        if line and not line.startswith(" "):
            break
        match = re.match(r"^  ([A-Za-z_][A-Za-z0-9_-]*):", line)
        if match:
            keys.add(match.group(1))
    return keys


def _job_block(text: str, name: str) -> str:
    lines = text.splitlines(keepends=True)
    starts = [index for index, line in enumerate(lines) if line.rstrip() == f"  {name}:"]
    _require(len(starts) == 1, f"workflow must have one {name!r} job")
    start = starts[0]
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if re.match(r"^  [A-Za-z_][A-Za-z0-9_-]*:", lines[index]):
            end = index
            break
        if lines[index].strip() and not lines[index].startswith(" "):
            end = index
            break
    return "".join(lines[start:end])


def _replace_in_step(text: str, needle: str, old: str, new: str) -> str:
    steps = _steps(text)
    _index, step = _find_step(steps, needle)
    _require(old in step.body, f"step containing {needle!r} lacks mutation target {old!r}")
    changed = step.body.replace(old, new, 1)
    lines = text.splitlines(keepends=True)
    return "".join([*lines[: step.start], changed, *lines[step.end :]])


def _move_step_after(text: str, moving_needle: str, target_needle: str) -> str:
    steps = _steps(text)
    moving_index, _moving = _find_step(steps, moving_needle)
    target_index, _target = _find_step(steps, target_needle)
    lines = text.splitlines(keepends=True)
    blocks = [lines[step.start : step.end] for step in steps]
    moving_block = blocks.pop(moving_index)
    if moving_index < target_index:
        target_index -= 1
    blocks.insert(target_index + 1, moving_block)
    return "".join(
        [*lines[: steps[0].start], *(line for block in blocks for line in block)]
    )


def _check_ci_surface(text: str) -> None:
    _require("scripts/forge/drift-check.sh" not in text, "forge-ci still runs drift")
    _require("name: drift-summary" not in text, "forge-ci still uploads drift summary")
    _require(
        "name: forge gates (tests, conformance, evals)" in text,
        "forge-ci job name still advertises drift",
    )
    _require(
        _on_keys(text) == {"push", "pull_request", "schedule", "workflow_dispatch"},
        "forge-ci triggers changed unexpectedly",
    )


def _check_drift_envelope(text: str) -> None:
    _require(
        _on_keys(text) == {"schedule", "workflow_dispatch"},
        "drift workflow must be scheduled and manually dispatchable only",
    )
    _require('cron: "23 5 * * 1"' in text, "weekly drift cron changed")
    _require("permissions:\n  contents: read\n" in text, "drift permissions are not read-only")
    _require(_job_keys(text) == {"drift"}, "drift workflow must have exactly one job")
    job = _job_block(text, "drift")
    _require(not re.search(r"^    uses:", job, re.MULTILINE), "drift job may not be reusable")
    _require(job.count("\n    runs-on:") == 1, "drift job must run on one runner")
    _require("timeout-minutes: 60" in job, "drift job timeout changed")
    steps = _steps(text)
    _require(
        steps[0].field("uses") == f"actions/checkout@{CHECKOUT_SHA} # v4",
        "checkout is not the first pinned step",
    )
    _require("fetch-depth: 0" in steps[0].body, "drift checkout is shallow")
    _require("persist-credentials: false" in steps[0].body, "checkout persists credentials")
    _require(
        steps[1].field("uses") == f"actions/setup-python@{PYTHON_SHA} # v5",
        "setup-python is not the second pinned step",
    )
    _require('python-version: "3.13"' in steps[1].body, "drift Python version changed")
    _require("actions/setup-node@" not in text, "drift does not need Node")
    _require("mypy" not in text, "drift does not install mypy")


def _check_drift_command(text: str) -> None:
    _index, step = _find_step(_steps(text), "scripts/forge/drift-check.sh")
    body = step.body
    _require(body.count("scripts/forge/drift-check.sh") == 1, "drift command is not singular")
    _require(
        re.search(r'\|\s*tee\s+"\$RUNNER_TEMP/[^"\n]+"', body),
        "drift stdout is not tee'd under RUNNER_TEMP",
    )
    _require("2>&1" not in body, "drift stderr is merged into summary stdout")
    _require('2>"$stderr_path"' in body, "drift stderr is not captured separately")
    _require('cat "$stderr_path" >&2' in body, "drift stderr is not replayed to stderr")
    _require(
        'stderr_path="$RUNNER_TEMP/forge-diagnostics/drift-stderr.txt"' in body,
        "drift stderr path is outside diagnostics",
    )
    _require(
        'if [ "$status" -eq 2 ]; then exit 2; fi' in body,
        "drift step no longer fails only on exit 2",
    )
    _require(
        "CLAUDE_PLUGIN_ROOT: ${{ github.workspace }}" in body,
        "drift step lost its plugin-root environment",
    )


def _check_no_continue_on_error(ci_text: str, drift_text: str) -> None:
    _require("continue-on-error" not in ci_text, "forge-ci weakens a failing step")
    _require("continue-on-error" not in drift_text, "forge-drift weakens a failing step")


def _check_reruns(ci_text: str, drift_text: str) -> None:
    ci_steps = _steps(ci_text)
    gate_index, _gate = _find_step(ci_steps, "parse_policy(head, raw).gate1")
    ci_rerun_index, ci_rerun = _find_step(ci_steps, "ci_diagnostics.py rerun")
    _require(ci_rerun.field("if") == "failure()", "Gate 1 rerun is not failure-only")
    _require(ci_rerun_index == gate_index + 1, "Gate 1 rerun is not directly after Gate 1")
    _require(
        '"$RUNNER_TEMP/forge-diagnostics/gate1-output.txt"' in ci_rerun.body,
        "Gate 1 rerun does not consume captured output",
    )

    drift_steps = _steps(drift_text)
    drift_index, _drift = _find_step(drift_steps, "scripts/forge/drift-check.sh")
    post_index, post = _find_step(drift_steps, "snapshot post-drift")
    drift_rerun_index, drift_rerun = _find_step(drift_steps, "ci_diagnostics.py rerun")
    _require(post.field("if") == "always()", "post-drift snapshot is not unconditional")
    _require(post_index == drift_index + 1, "post-drift snapshot moved away from drift")
    _require(
        drift_rerun_index == post_index + 1,
        "only the mandated post-drift snapshot may precede the drift rerun",
    )
    _require(drift_rerun.field("if") == "failure()", "drift rerun is not failure-only")
    _require(
        '"$RUNNER_TEMP/forge-diagnostics/drift-stderr.txt"' in drift_rerun.body,
        "drift rerun does not consume captured stderr",
    )


def _check_provider_install(ci_text: str, drift_text: str) -> None:
    _require("npm install -g" not in ci_text, "provider CLIs are installed globally")
    _require("npm install -g" not in drift_text, "provider CLIs are installed globally")
    _require(ci_text.count(CLAUDE_PACKAGE) == 1, "Claude package pin is not exact")
    _require(ci_text.count(CODEX_PACKAGE) == 1, "Codex package pin is not exact")
    ci_steps = _steps(ci_text)
    version_index, version = _find_step(ci_steps, CLAUDE_PACKAGE)
    stub_index, stub = _find_step(ci_steps, "ci_diagnostics.py install-stubs")
    _require('--prefix "$RUNNER_TEMP/provider-cli"' in version.body, "CLI install is not isolated")
    _require("node_modules/.bin/claude\" --version" in version.body, "Claude pin not verified")
    _require("node_modules/.bin/codex\" --version" in version.body, "Codex pin not verified")
    _require(version_index < stub_index, "CI stubs must follow the real provider version check")
    for needle in (
        "parse_policy(head, raw).gate1",
        "ci_diagnostics.py rerun",
        "parse_policy(head, raw).stack_commands",
        "STRICT=1 bash scripts/forge/run-evals.sh",
    ):
        test_index, _test = _find_step(ci_steps, needle)
        _require(stub_index < test_index, f"CI stubs do not cover {needle}")
    _require("$GITHUB_PATH" in stub.body, "provider stubs are not added to PATH")

    drift_steps = _steps(drift_text)
    drift_stub_index, _stub = _find_step(drift_steps, "ci_diagnostics.py install-stubs")
    for needle in ("scripts/forge/drift-check.sh", "ci_diagnostics.py rerun"):
        test_index, _test = _find_step(drift_steps, needle)
        _require(drift_stub_index < test_index, f"drift stubs do not cover {needle}")
    _require(CLAUDE_PACKAGE not in drift_text, "drift unexpectedly installs a real provider")
    _require(CODEX_PACKAGE not in drift_text, "drift unexpectedly installs a real provider")


def _check_audit(workflow: str, test_needles: tuple[str, ...]) -> None:
    steps = _steps(workflow)
    audit_index, audit = _find_step(steps, "ci_diagnostics.py stub-audit")
    _require(audit.field("if") == "always()", "stub audit is not unconditional")
    for needle in test_needles:
        test_index, _step = _find_step(steps, needle)
        _require(audit_index > test_index, f"stub audit runs before {needle}")
    later_steps_are_uploads = all(
        f"actions/upload-artifact@{UPLOAD_SHA}" in step.body
        for step in steps[audit_index + 1 :]
    )
    _require(
        later_steps_are_uploads,
        "stub audit is not the last gating step",
    )
    _require(
        '"$RUNNER_TEMP/provider-stubs"' in audit.body
        and '"$RUNNER_TEMP/forge-diagnostics/provider-launches.log"' in audit.body,
        "stub audit does not inspect the installed stubs and launch log",
    )


def _check_audits(ci_text: str, drift_text: str) -> None:
    _check_audit(
        ci_text,
        (
            "parse_policy(head, raw).gate1",
            "ci_diagnostics.py rerun",
            "parse_policy(head, raw).stack_commands",
            "STRICT=1 bash scripts/forge/run-evals.sh",
        ),
    )
    _check_audit(drift_text, ("scripts/forge/drift-check.sh", "ci_diagnostics.py rerun"))


def _check_fingerprints(ci_text: str, drift_text: str) -> None:
    for label, text, gate_needle in (
        ("ci", ci_text, "parse_policy(head, raw).gate1"),
        ("drift", drift_text, "scripts/forge/drift-check.sh"),
    ):
        steps = _steps(text)
        stub_index, _stub = _find_step(steps, "ci_diagnostics.py install-stubs")
        fingerprint_index, fingerprint = _find_step(steps, "ci_diagnostics.py fingerprint")
        gate_index, _gate = _find_step(steps, gate_needle)
        _require(stub_index < fingerprint_index < gate_index, f"{label} fingerprint is misplaced")
        _require(
            '--expect-stubs "$RUNNER_TEMP/provider-stubs"' in fingerprint.body,
            f"{label} fingerprint does not fail closed on stub resolution",
        )
        _require(
            '--out "$RUNNER_TEMP/forge-diagnostics/environment-fingerprint.txt"'
            in fingerprint.body,
            f"{label} fingerprint output is not diagnostic-scoped",
        )


def _check_snapshots(ci_text: str, drift_text: str) -> None:
    ci_steps = _steps(ci_text)
    positions = {}
    labels = ("pre-gate1", "post-gate1", "post-stack", "post-evals")
    for label in labels:
        index, step = _find_step(ci_steps, f"snapshot {label}")
        positions[label] = index
        _require(
            '--out-dir "$RUNNER_TEMP/forge-diagnostics"' in step.body,
            f"snapshot {label} escapes diagnostics",
        )
        if label.startswith("post-"):
            _require(step.field("if") == "always()", f"snapshot {label} is not unconditional")
    gate_index, _gate = _find_step(ci_steps, "parse_policy(head, raw).gate1")
    rerun_index, _rerun = _find_step(ci_steps, "ci_diagnostics.py rerun")
    stack_index, _stack = _find_step(ci_steps, "parse_policy(head, raw).stack_commands")
    eval_index, _eval = _find_step(ci_steps, "STRICT=1 bash scripts/forge/run-evals.sh")
    _require(positions["pre-gate1"] + 1 == gate_index, "pre-gate1 does not precede Gate 1")
    _require(gate_index + 1 == rerun_index, "Gate 1 rerun moved from its boundary")
    _require(rerun_index + 1 == positions["post-gate1"], "post-gate1 is misplaced")
    _require(positions["post-gate1"] + 1 == stack_index, "stack is not after post-gate1")
    _require(stack_index + 1 == positions["post-stack"], "post-stack is misplaced")
    _require(positions["post-stack"] + 1 == eval_index, "STRICT evals are misplaced")
    _require(eval_index + 1 == positions["post-evals"], "post-evals is misplaced")

    drift_steps = _steps(drift_text)
    pre_index, _pre = _find_step(drift_steps, "snapshot pre-drift")
    drift_index, _drift = _find_step(drift_steps, "scripts/forge/drift-check.sh")
    post_index, post = _find_step(drift_steps, "snapshot post-drift")
    _require(pre_index < drift_index < post_index, "drift snapshots do not bracket drift")
    _require(post.field("if") == "always()", "post-drift snapshot is not unconditional")


def _check_gate1_capture(text: str) -> None:
    steps = _steps(text)
    _index, gate = _find_step(steps, "parse_policy(head, raw).gate1")
    output_path = 'Path(os.environ["RUNNER_TEMP"]) / "forge-diagnostics/gate1-output.txt"'
    _require(output_path in gate.body, "Gate 1 output is not written under RUNNER_TEMP")
    _require(".write_bytes(result.output)" in gate.body, "Gate 1 result output is not captured")
    _require("except OSError as exc:" in gate.body, "Gate 1 diagnostic write is not guarded")
    _require(
        gate.body.index(".write_bytes(result.output)") < gate.body.index("if result.timed_out:"),
        "Gate 1 output is captured after verdict logic",
    )


def _check_upload(
    text: str,
    artifact_name: str,
    artifact_path: str,
    *,
    retention: bool,
) -> None:
    _index, step = _find_step(_steps(text), f"name: {artifact_name}")
    _require(step.field("if") == "always()", f"{artifact_name} upload is not unconditional")
    _require(
        f"actions/upload-artifact@{UPLOAD_SHA}" in step.body,
        f"{artifact_name} upload action is not pinned",
    )
    _require(f"path: {artifact_path}" in step.body, f"{artifact_name} path is wrong")
    _require(
        "if-no-files-found: ignore" in step.body,
        f"{artifact_name} missing-file policy changed",
    )
    if retention:
        _require("retention-days: 14" in step.body, f"{artifact_name} retention changed")


def _check_uploads(ci_text: str, drift_text: str) -> None:
    _check_upload(
        ci_text,
        "forge-diagnostics",
        "${{ runner.temp }}/forge-diagnostics",
        retention=True,
    )
    _check_upload(
        drift_text,
        "drift-summary",
        "${{ runner.temp }}/drift-summary.json",
        retention=False,
    )
    _check_upload(
        drift_text,
        "drift-diagnostics",
        "${{ runner.temp }}/forge-diagnostics",
        retention=True,
    )


def _runner_temp_argument(raw: str) -> bool:
    if raw.startswith("'"):
        value = raw[1:-1]
        if value.startswith("$RUNNER_TEMP/"):
            return False
    elif raw.startswith('"'):
        value = raw[1:-1]
    else:
        value = raw
    prefixes = ("$RUNNER_TEMP/", "${{ runner.temp }}/")
    return any(
        value.startswith(prefix) and ".." not in value[len(prefix) :].split("/")
        for prefix in prefixes
    )


def _diagnostic_option_arguments(text: str) -> list[str]:
    pattern = re.compile(rf"--out(?:-dir)?(?:=|\s+)(?P<argument>{SHELL_WORD})")
    return [match.group("argument") for match in pattern.finditer(text)]


def _provider_log_arguments(text: str) -> list[str]:
    pattern = re.compile(
        rf"ci_diagnostics\.py\s+(?:install-stubs|stub-audit)\s+"
        rf"{SHELL_WORD}\s+(?P<argument>{SHELL_WORD})"
    )
    return [match.group("argument") for match in pattern.finditer(text)]


def _check_drift_temp_confinement(text: str) -> None:
    arguments = _diagnostic_option_arguments(text)
    _require(len(arguments) == 4, "drift diagnostic output arguments changed")
    _require(
        all(_runner_temp_argument(argument) for argument in arguments),
        "a drift diagnostic output argument escapes RUNNER_TEMP",
    )
    log_arguments = _provider_log_arguments(text)
    _require(
        len(log_arguments) == 2,
        "install and audit must each bind the provider launch log",
    )
    _require(
        all(_runner_temp_argument(argument) for argument in log_arguments),
        "a provider launch log argument escapes RUNNER_TEMP",
    )
    _require(
        'tee "$RUNNER_TEMP/drift-summary.json"' in text,
        "drift summary escapes RUNNER_TEMP",
    )
    _require(
        'stderr_path="$RUNNER_TEMP/forge-diagnostics/drift-stderr.txt"' in text,
        "drift stderr escapes RUNNER_TEMP",
    )


class CiWorkflowShapeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ci_text = CI_PATH.read_text(encoding="utf-8")
        cls.drift_text = DRIFT_PATH.read_text(encoding="utf-8")

    def _assert_rejected(self, checker: Callable[[str], None], mutant: str) -> None:
        with self.assertRaises(AssertionError):
            checker(mutant)

    def _assert_pair_rejected(
        self,
        checker: Callable[[str, str], None],
        ci_text: str,
        drift_text: str,
    ) -> None:
        with self.assertRaises(AssertionError):
            checker(ci_text, drift_text)

    def test_ci_surface_has_no_drift_and_keeps_expected_triggers(self) -> None:
        _check_ci_surface(self.ci_text)
        old_drift = (
            "\n      - name: Drift check\n"
            "        run: bash scripts/forge/drift-check.sh\n"
            "      - name: Upload drift summary\n"
            "        with:\n"
            "          name: drift-summary\n"
        )
        mutants = (
            self.ci_text + old_drift,
            self.ci_text.replace("  workflow_dispatch:\n", "", 1),
            self.ci_text.replace("  push:\n    branches: [main]\n", "", 1),
            self.ci_text.replace('  schedule:\n    - cron: "23 5 * * 1"\n', "", 1),
            self.ci_text.replace(
                "forge gates (tests, conformance, evals)",
                "forge gates (tests, conformance, evals, drift)",
                1,
            ),
        )
        for mutant in mutants:
            with self.subTest(mutant=mutants.index(mutant)):
                self._assert_rejected(_check_ci_surface, mutant)

    def test_drift_envelope_is_narrow_and_pinned(self) -> None:
        _check_drift_envelope(self.drift_text)
        mutants = (
            self.drift_text.replace("on:\n", "on:\n  push:\n", 1),
            self.drift_text.replace("on:\n", "on:\n  pull_request:\n", 1),
            self.drift_text.replace('cron: "23 5 * * 1"', 'cron: "24 5 * * 1"', 1),
            self.drift_text.replace("contents: read", "contents: write", 1),
            self.drift_text + "\n  reusable:\n    uses: owner/repo/.github/workflows/x.yml@main\n",
            self.drift_text.replace(
                "    runs-on: ubuntu-latest",
                "    uses: owner/repo/.github/workflows/x.yml@main",
                1,
            ),
            self.drift_text.replace(
                "    runs-on: ubuntu-latest",
                "    runs-on: ubuntu-latest\n    runs-on: macos-latest",
                1,
            ),
            self.drift_text.replace("timeout-minutes: 60", "timeout-minutes: 61", 1),
            _move_step_after(
                self.drift_text,
                f"actions/checkout@{CHECKOUT_SHA}",
                f"actions/setup-python@{PYTHON_SHA}",
            ),
            self.drift_text.replace("fetch-depth: 0", "fetch-depth: 1", 1),
            self.drift_text.replace("persist-credentials: false", "persist-credentials: true", 1),
            self.drift_text.replace(CHECKOUT_SHA, "0" * 40, 1),
            self.drift_text.replace(PYTHON_SHA, "1" * 40, 1),
            self.drift_text.replace('python-version: "3.13"', 'python-version: "3.12"', 1),
            self.drift_text.replace(
                '          python-version: "3.13"',
                '          python-version: "3.13"\n\n      - uses: actions/setup-node@bad',
                1,
            ),
            self.drift_text + "\n# install mypy\n",
        )
        for index, mutant in enumerate(mutants):
            with self.subTest(mutant=index):
                self._assert_rejected(_check_drift_envelope, mutant)

    def test_drift_command_preserves_stream_and_exit_semantics(self) -> None:
        _check_drift_command(self.drift_text)
        mutants = (
            self.drift_text.replace(
                'tee "$RUNNER_TEMP/drift-summary.json"',
                'tee "drift-summary.json"',
                1,
            ),
            self.drift_text.replace(
                "bash scripts/forge/drift-check.sh",
                "bash scripts/forge/drift-check.sh 2>&1",
                1,
            ),
            self.drift_text.replace(
                "bash scripts/forge/drift-check.sh",
                "bash scripts/forge/drift-check.sh && bash scripts/forge/drift-check.sh",
                1,
            ),
            self.drift_text.replace('2>"$stderr_path"', '2>"other-stderr.txt"', 1),
            self.drift_text.replace('cat "$stderr_path" >&2\n', "", 1),
            self.drift_text.replace(
                'stderr_path="$RUNNER_TEMP/forge-diagnostics/drift-stderr.txt"',
                'stderr_path="drift-stderr.txt"',
                1,
            ),
            self.drift_text.replace('if [ "$status" -eq 2 ]', 'if [ "$status" -ne 0 ]', 1),
            self.drift_text.replace(
                "          CLAUDE_PLUGIN_ROOT: ${{ github.workspace }}\n",
                "",
                1,
            ),
        )
        for index, mutant in enumerate(mutants):
            with self.subTest(mutant=index):
                self._assert_rejected(_check_drift_command, mutant)

    def test_no_step_can_continue_on_error(self) -> None:
        _check_no_continue_on_error(self.ci_text, self.drift_text)
        ci_mutant = _replace_in_step(
            self.ci_text,
            "parse_policy(head, raw).gate1",
            "        run: |\n",
            "        continue-on-error: true\n        run: |\n",
        )
        self._assert_pair_rejected(
            _check_no_continue_on_error,
            ci_mutant,
            self.drift_text,
        )
        drift_mutant = _replace_in_step(
            self.drift_text,
            "scripts/forge/drift-check.sh",
            "        run: |\n",
            "        continue-on-error: true\n        run: |\n",
        )
        self._assert_pair_rejected(
            _check_no_continue_on_error,
            self.ci_text,
            drift_mutant,
        )

    def test_failure_reruns_have_fail_closed_conditions_and_order(self) -> None:
        _check_reruns(self.ci_text, self.drift_text)
        ci_mutant = _replace_in_step(
            self.ci_text,
            "ci_diagnostics.py rerun",
            "if: failure()",
            "if: always()",
        )
        drift_mutant = _replace_in_step(
            self.drift_text,
            "ci_diagnostics.py rerun",
            "if: failure()",
            "if: always()",
        )
        self._assert_pair_rejected(_check_reruns, ci_mutant, self.drift_text)
        self._assert_pair_rejected(_check_reruns, self.ci_text, drift_mutant)
        ci_order_mutant = _move_step_after(
            self.ci_text,
            "ci_diagnostics.py rerun",
            "snapshot post-gate1",
        )
        drift_order_mutant = _move_step_after(
            self.drift_text,
            "ci_diagnostics.py rerun",
            "ci_diagnostics.py stub-audit",
        )
        self._assert_pair_rejected(_check_reruns, ci_order_mutant, self.drift_text)
        self._assert_pair_rejected(_check_reruns, self.ci_text, drift_order_mutant)
        bad_input = _replace_in_step(
            self.ci_text,
            "ci_diagnostics.py rerun",
            "gate1-output.txt",
            "other-output.txt",
        )
        self._assert_pair_rejected(_check_reruns, bad_input, self.drift_text)
        bad_drift_input = _replace_in_step(
            self.drift_text,
            "ci_diagnostics.py rerun",
            "drift-stderr.txt",
            "other-stderr.txt",
        )
        self._assert_pair_rejected(_check_reruns, self.ci_text, bad_drift_input)

    def test_provider_install_isolated_and_stubs_precede_gates(self) -> None:
        _check_provider_install(self.ci_text, self.drift_text)
        ci_mutants = (
            self.ci_text.replace("npm install --prefix", "npm install -g --prefix", 1),
            self.ci_text.replace(CLAUDE_PACKAGE, "@anthropic-ai/claude-code@latest", 1),
            self.ci_text.replace(CODEX_PACKAGE, "@openai/codex@latest", 1),
            self.ci_text.replace(
                '--prefix "$RUNNER_TEMP/provider-cli"',
                '--prefix "provider-cli"',
                1,
            ),
            self.ci_text.replace(
                '"$RUNNER_TEMP/provider-cli/node_modules/.bin/claude" --version\n',
                "",
                1,
            ),
            self.ci_text.replace(
                '"$RUNNER_TEMP/provider-cli/node_modules/.bin/codex" --version\n',
                "",
                1,
            ),
            _move_step_after(
                self.ci_text,
                "ci_diagnostics.py install-stubs",
                "STRICT=1 bash scripts/forge/run-evals.sh",
            ),
            self.ci_text.replace(
                '          echo "$RUNNER_TEMP/provider-stubs" >> "$GITHUB_PATH"\n',
                "",
                1,
            ),
        )
        for index, mutant in enumerate(ci_mutants):
            with self.subTest(mutant=index):
                self._assert_pair_rejected(
                    _check_provider_install,
                    mutant,
                    self.drift_text,
                )
        drift_order_mutant = _move_step_after(
            self.drift_text,
            "ci_diagnostics.py install-stubs",
            "scripts/forge/drift-check.sh",
        )
        self._assert_pair_rejected(
            _check_provider_install,
            self.ci_text,
            drift_order_mutant,
        )
        real_provider_mutant = self.drift_text + f"\n# {CLAUDE_PACKAGE}\n"
        self._assert_pair_rejected(
            _check_provider_install,
            self.ci_text,
            real_provider_mutant,
        )
        global_install_mutant = self.drift_text + "\n# npm install -g provider\n"
        self._assert_pair_rejected(
            _check_provider_install,
            self.ci_text,
            global_install_mutant,
        )

    def test_stub_audits_are_last_gating_steps(self) -> None:
        _check_audits(self.ci_text, self.drift_text)
        ci_mutant = _replace_in_step(
            self.ci_text,
            "ci_diagnostics.py stub-audit",
            "if: always()",
            "if: success()",
        )
        drift_mutant = _replace_in_step(
            self.drift_text,
            "ci_diagnostics.py stub-audit",
            "if: always()",
            "if: success()",
        )
        self._assert_pair_rejected(_check_audits, ci_mutant, self.drift_text)
        self._assert_pair_rejected(_check_audits, self.ci_text, drift_mutant)
        ci_order_mutant = _move_step_after(
            self.ci_text,
            "STRICT=1 bash scripts/forge/run-evals.sh",
            "ci_diagnostics.py stub-audit",
        )
        drift_order_mutant = _move_step_after(
            self.drift_text,
            "ci_diagnostics.py rerun",
            "ci_diagnostics.py stub-audit",
        )
        self._assert_pair_rejected(_check_audits, ci_order_mutant, self.drift_text)
        self._assert_pair_rejected(_check_audits, self.ci_text, drift_order_mutant)
        bad_log = _replace_in_step(
            self.ci_text,
            "ci_diagnostics.py stub-audit",
            "provider-launches.log",
            "other.log",
        )
        self._assert_pair_rejected(_check_audits, bad_log, self.drift_text)

    def test_fingerprints_verify_stub_resolution_before_gates(self) -> None:
        _check_fingerprints(self.ci_text, self.drift_text)
        expect_mutant = self.ci_text.replace(
            '--expect-stubs "$RUNNER_TEMP/provider-stubs"',
            "",
            1,
        )
        output_mutant = self.drift_text.replace(
            '--out "$RUNNER_TEMP/forge-diagnostics/environment-fingerprint.txt"',
            '--out "$RUNNER_TEMP/fingerprint.txt"',
            1,
        )
        order_mutant = _move_step_after(
            self.ci_text,
            "ci_diagnostics.py fingerprint",
            "parse_policy(head, raw).gate1",
        )
        self._assert_pair_rejected(_check_fingerprints, expect_mutant, self.drift_text)
        self._assert_pair_rejected(_check_fingerprints, self.ci_text, output_mutant)
        self._assert_pair_rejected(_check_fingerprints, order_mutant, self.drift_text)

    def test_snapshots_bracket_gate_boundaries(self) -> None:
        _check_snapshots(self.ci_text, self.drift_text)
        ci_mutant = _replace_in_step(
            self.ci_text,
            "snapshot post-stack",
            "if: always()",
            "if: success()",
        )
        drift_mutant = _replace_in_step(
            self.drift_text,
            "snapshot post-drift",
            "if: always()",
            "if: success()",
        )
        self._assert_pair_rejected(_check_snapshots, ci_mutant, self.drift_text)
        self._assert_pair_rejected(_check_snapshots, self.ci_text, drift_mutant)
        for label in ("post-gate1", "post-evals"):
            condition_mutant = _replace_in_step(
                self.ci_text,
                f"snapshot {label}",
                "if: always()",
                "if: success()",
            )
            self._assert_pair_rejected(
                _check_snapshots,
                condition_mutant,
                self.drift_text,
            )
        ci_order_mutants = (
            _move_step_after(
                self.ci_text,
                "snapshot pre-gate1",
                "parse_policy(head, raw).gate1",
            ),
            _move_step_after(
                self.ci_text,
                "snapshot post-gate1",
                "parse_policy(head, raw).stack_commands",
            ),
            _move_step_after(
                self.ci_text,
                "snapshot post-stack",
                "STRICT=1 bash scripts/forge/run-evals.sh",
            ),
            _move_step_after(
                self.ci_text,
                "snapshot post-evals",
                "ci_diagnostics.py stub-audit",
            ),
        )
        for index, order_mutant in enumerate(ci_order_mutants):
            with self.subTest(order_mutant=index):
                self._assert_pair_rejected(
                    _check_snapshots,
                    order_mutant,
                    self.drift_text,
                )
        output_mutant = _replace_in_step(
            self.ci_text,
            "snapshot pre-gate1",
            '"$RUNNER_TEMP/forge-diagnostics"',
            '"$RUNNER_TEMP/other"',
        )
        self._assert_pair_rejected(_check_snapshots, output_mutant, self.drift_text)
        drift_order_mutant = _move_step_after(
            self.drift_text,
            "snapshot pre-drift",
            "scripts/forge/drift-check.sh",
        )
        self._assert_pair_rejected(_check_snapshots, self.ci_text, drift_order_mutant)

    def test_gate1_output_is_captured_before_verdict(self) -> None:
        _check_gate1_capture(self.ci_text)
        mutant = self.ci_text.replace(
            ".write_bytes(result.output)",
            '.write_bytes(b"")',
            1,
        )
        self._assert_rejected(_check_gate1_capture, mutant)
        path_mutant = self.ci_text.replace(
            '"forge-diagnostics/gate1-output.txt"',
            '"gate1-output.txt"',
            1,
        )
        guard_mutant = self.ci_text.replace("except OSError as exc:", "except ValueError:", 1)
        late_mutant = self.ci_text.replace(
            "          if result.timed_out:\n",
            "          if result.timed_out:\n"
            "              pass\n"
            "          # .write_bytes(result.output)\n",
            1,
        ).replace(".write_bytes(result.output)", '.write_bytes(b"")', 1)
        self._assert_rejected(_check_gate1_capture, path_mutant)
        self._assert_rejected(_check_gate1_capture, guard_mutant)
        self._assert_rejected(_check_gate1_capture, late_mutant)

    def test_diagnostics_uploads_are_unconditional_and_pinned(self) -> None:
        _check_uploads(self.ci_text, self.drift_text)
        ci_mutants = (
            _replace_in_step(
                self.ci_text,
                "name: forge-diagnostics",
                "if: always()",
                "if: success()",
            ),
            _replace_in_step(
                self.ci_text,
                "name: forge-diagnostics",
                f"actions/upload-artifact@{UPLOAD_SHA}",
                "actions/upload-artifact@v4",
            ),
            _replace_in_step(
                self.ci_text,
                "name: forge-diagnostics",
                "path: ${{ runner.temp }}/forge-diagnostics",
                "path: forge-diagnostics",
            ),
            _replace_in_step(
                self.ci_text,
                "name: forge-diagnostics",
                "if-no-files-found: ignore",
                "if-no-files-found: warn",
            ),
            _replace_in_step(
                self.ci_text,
                "name: forge-diagnostics",
                "retention-days: 14",
                "retention-days: 1",
            ),
        )
        for index, ci_mutant in enumerate(ci_mutants):
            with self.subTest(ci_upload_mutant=index):
                self._assert_pair_rejected(_check_uploads, ci_mutant, self.drift_text)

        drift_mutants = []
        for artifact_name, artifact_path, retention in (
            ("drift-summary", "${{ runner.temp }}/drift-summary.json", False),
            ("drift-diagnostics", "${{ runner.temp }}/forge-diagnostics", True),
        ):
            drift_mutants.extend(
                (
                    _replace_in_step(
                        self.drift_text,
                        f"name: {artifact_name}",
                        "if: always()",
                        "if: success()",
                    ),
                    _replace_in_step(
                        self.drift_text,
                        f"name: {artifact_name}",
                        f"actions/upload-artifact@{UPLOAD_SHA}",
                        "actions/upload-artifact@v4",
                    ),
                    _replace_in_step(
                        self.drift_text,
                        f"name: {artifact_name}",
                        f"path: {artifact_path}",
                        "path: artifact-outside-runner-temp",
                    ),
                    _replace_in_step(
                        self.drift_text,
                        f"name: {artifact_name}",
                        "if-no-files-found: ignore",
                        "if-no-files-found: warn",
                    ),
                )
            )
            if retention:
                drift_mutants.append(
                    _replace_in_step(
                        self.drift_text,
                        f"name: {artifact_name}",
                        "retention-days: 14",
                        "retention-days: 1",
                    )
                )
        for index, drift_mutant in enumerate(drift_mutants):
            with self.subTest(drift_upload_mutant=index):
                self._assert_pair_rejected(_check_uploads, self.ci_text, drift_mutant)

    def test_drift_diagnostic_outputs_are_runner_temp_confined(self) -> None:
        _check_drift_temp_confinement(self.drift_text)
        mutants = (
            self.drift_text.replace(
                '--out-dir "$RUNNER_TEMP/forge-diagnostics"',
                '--out-dir "forge-diagnostics"',
                1,
            ),
            self.drift_text.replace(
                '--out "$RUNNER_TEMP/forge-diagnostics/environment-fingerprint.txt"',
                "--out 'fingerprint.txt'",
                1,
            ),
            self.drift_text.replace(
                '--out-dir "$RUNNER_TEMP/forge-diagnostics"',
                "--out-dir diagnostics",
                1,
            ),
            self.drift_text.replace(
                '"$RUNNER_TEMP/forge-diagnostics/provider-launches.log"',
                "'provider-launches.log'",
                1,
            ),
            self.drift_text.replace(
                '"$RUNNER_TEMP/forge-diagnostics/provider-launches.log"',
                "provider-launches.log",
                1,
            ),
        )
        for index, mutant in enumerate(mutants):
            with self.subTest(confinement_mutant=index):
                self._assert_rejected(_check_drift_temp_confinement, mutant)


if __name__ == "__main__":
    unittest.main()
