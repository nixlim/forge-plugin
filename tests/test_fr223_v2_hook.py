"""DM-016 additive v2 corpora and FR-239 commit-guard behavior."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import ModuleType
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = Path("docs/specs/forge-plugin-spec.md")
GUARD = ROOT / "scripts/forge/commit-guard.sh"
V1_REASON = ROOT / "system/fr223/reason-codes-v1.json"
V2_REASON = ROOT / "system/fr223/reason-codes-v2.json"
V1_HOOK = ROOT / "system/fr223/hook-argv-cases-v1.json"
V2_HOOK = ROOT / "system/fr223/hook-argv-cases-v2.json"
V1_REASON_SHA256 = "3646227d8437789e0407117dc09e00d6116edccb63e89354c746d4b9059c264b"
V1_HOOK_SHA256 = "1850257d7899a4c7199e9bcbe12ffd39b0905bb44e49d16348c10e438ea05db7"
V1_MANIFEST_SHA256 = "7741b877b1ed45047d680a077c5303b2314cd1f3ef0339821bd7105ac9acd5c9"
V1_MANIFEST = ROOT / ".forge/evals/tasks/fr223-phase0-v1.manifest.json"
ACTIVATION_CONTEXTS = {
    "non-forge",
    "upstream",
    "plugin-mode-missing",
    "legacy-v1",
    "forge-verbs-v1",
    "invalid",
}
EXPECTATIONS = {
    "allow",
    "no-match",
    "deny-merge-approve",
    "deny-invalid-mode",
    "deny-raw-commit",
    "deny-raw-push",
}
DENIALS = {
    "deny-merge-approve": (
        "forge: operator verb denied — present the candidate and ask the operator "
        "to run this via ! (merge approve)"
    ),
    "deny-raw-commit": (
        "forge: raw git commit denied — use Forge CLI commit finalize"
    ),
    "deny-raw-push": (
        "forge: raw git push denied — use Forge CLI merge finalize or Forge CLI push"
    ),
    "deny-invalid-mode": (
        "forge: history mutation mode invalid — repair committed .forge-manifest "
        "through Forge CLI"
    ),
}
LEGACY_OPERATOR_DENIALS = {
    "deny-approve": (
        "forge: operator verb denied — present the candidate and ask the operator "
        "to run this via ! (commit approve)"
    ),
    "deny-skip": (
        "forge: operator verb denied — present the candidate and ask the operator "
        "to run this via ! (commit skip)"
    ),
}
FAILSAFE_DENIALS = {
    "nesting": (
        "forge: commit guard input bound exceeded — command nesting reached the "
        "64-level bound and was not classified; split the command"
    ),
    "time": (
        "forge: commit guard time budget exceeded — command was not classified "
        "within 10s; split the command"
    ),
    "internal": (
        "forge: commit guard internal failure — command was not classified "
        "({failure}); split the command"
    ),
}
FAILSAFE_REASON_CODES = {
    "nesting": "guard-input-bound",
    "time": "guard-time-budget",
    "internal": "guard-internal-failure",
}
EXPECTED_IDS = (
    "activation-enabled-raw-commit-worktree-legacy",
    "activation-enabled-raw-push-worktree-missing",
    "activation-invalid-raw-commit",
    "activation-invalid-raw-push",
    "activation-legacy-raw-push-worktree-invalid",
    "activation-missing-raw-push-worktree-enabled",
    "activation-non-forge-raw-commit",
    "activation-upstream-raw-push",
    "allow-enabled-commit-finalize",
    "allow-enabled-merge-finalize",
    "allow-enabled-push",
    "allow-quoted-raw-text",
    "compound-merge-finalize-then-raw-commit",
    "compound-push-then-raw-push",
    "deny-merge-approve-global-after-last",
    "deny-merge-approve-global-before-first",
    "deny-merge-approve-global-between-middle",
    "no-match-merge-approved",
)
EXPECTED_PARTITION = {
    "allow": 8,
    "no-match": 1,
    "deny-merge-approve": 3,
    "deny-invalid-mode": 2,
    "deny-raw-commit": 2,
    "deny-raw-push": 2,
}


def read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AssertionError(f"{path} root is not an object")
    return payload


def committed_spec() -> str:
    result = subprocess.run(
        ["git", "show", f"HEAD:{SPEC_PATH.as_posix()}"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return result.stdout


def v2_reason_rows(spec: str) -> list[dict[str, object]]:
    start = "### `cli.py` — Forge CLI v2 output envelope and closed reason enum"
    end = "Hook audit labels"
    section = spec.split(start, 1)[1].split(end, 1)[0]
    return [
        {"code": code, "exit_class": int(exit_class), "precondition": precondition}
        for code, exit_class, precondition in re.findall(
            r"(?m)^\| `([a-z][a-z0-9-]*)` \| ([012]) \| (.*?) \|$",
            section,
        )
    ]


def load_guard_module(test: unittest.TestCase, name: str) -> ModuleType:
    source = GUARD.read_text(encoding="utf-8")
    embedded = source.split("<<'PY' || true\n", 1)[1].split("\nPY\n", 1)[0]
    definitions = embedded.split("\ntry:\n    raise SystemExit(main())", 1)[0]
    test.addCleanup(sys.modules.pop, name, None)
    module = ModuleType(name)
    module.__file__ = str(GUARD)
    sys.modules[name] = module
    exec(compile(definitions, str(GUARD), "exec"), module.__dict__)
    return module


def denial(reason: str) -> dict[str, object]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def manifest_bytes(context: str) -> bytes | None:
    if context == "non-forge":
        return None
    if context == "upstream":
        return b"upstream_commit: upstream-test\nregion: project (upstream)\n"
    lines = [
        "forge_version: 1",
        "plugin_ref: test-plugin",
        "installed: 2026-08-29",
        "project_name: hook-test",
        "default_branch: main",
        "init_completed: true",
    ]
    if context == "legacy-v1":
        lines.append("history_mutation_mode: legacy-v1")
    elif context == "forge-verbs-v1":
        lines.append("history_mutation_mode: forge-verbs-v1")
    elif context == "invalid":
        lines.append("history_mutation_mode: unknown-v9")
    elif context != "plugin-mode-missing":
        raise AssertionError(f"unknown manifest context: {context}")
    lines.append("region: project-overview")
    return ("\n".join(lines) + "\n").encode("utf-8")


class V2CorpusContractTests(unittest.TestCase):
    def test_reason_v2_is_the_exact_sorted_revision7_union(self) -> None:
        payload = read_json(V2_REASON)
        self.assertEqual(tuple(payload), ("schema", "codes"))
        self.assertEqual(payload["schema"], "fr223-reason-codes/2")
        rows = payload["codes"]
        self.assertEqual(len(rows), 41)
        self.assertTrue(
            all(tuple(row) == ("code", "exit_class", "precondition") for row in rows)
        )
        codes = [row["code"] for row in rows]
        self.assertEqual(codes, sorted(codes))
        self.assertEqual(len(codes), len(set(codes)))
        self.assertEqual(rows, v2_reason_rows(committed_spec()))
        self.assertTrue(
            {"activation-policy-invalid", "raw-git-commit-denied", "raw-git-push-denied"}
            .isdisjoint(codes)
        )

    def test_all_v1_rows_and_artifacts_remain_immutable(self) -> None:
        self.assertEqual(hashlib.sha256(V1_REASON.read_bytes()).hexdigest(), V1_REASON_SHA256)
        self.assertEqual(hashlib.sha256(V1_HOOK.read_bytes()).hexdigest(), V1_HOOK_SHA256)
        self.assertEqual(
            hashlib.sha256(V1_MANIFEST.read_bytes()).hexdigest(), V1_MANIFEST_SHA256
        )
        v1_rows = read_json(V1_REASON)["codes"]
        v2_by_code = {row["code"]: row for row in read_json(V2_REASON)["codes"]}
        self.assertEqual(len(v1_rows), 25)
        for row in v1_rows:
            with self.subTest(code=row["code"]):
                self.assertEqual(v2_by_code[row["code"]], row)

    def test_hook_v2_reference_layout_enums_and_partition_are_exact(self) -> None:
        payload = read_json(V2_HOOK)
        self.assertEqual(tuple(payload), ("schema", "v1", "case_count", "cases"))
        self.assertEqual(payload["schema"], "fr223-hook-argv/2")
        self.assertEqual(
            payload["v1"],
            {
                "path": "system/fr223/hook-argv-cases-v1.json",
                "schema": "fr223-hook-argv/1",
                "sha256": V1_HOOK_SHA256,
                "case_count": 112,
            },
        )
        cases = payload["cases"]
        self.assertEqual(payload["case_count"], 18)
        self.assertEqual(len(cases), 18)
        self.assertEqual(payload["v1"]["case_count"] + len(cases), 130)
        identifiers = tuple(case["id"] for case in cases)
        self.assertEqual(identifiers, EXPECTED_IDS)
        self.assertEqual(identifiers, tuple(sorted(identifiers)))
        self.assertFalse(
            set(identifiers)
            & {case["id"] for case in read_json(V1_HOOK)["cases"]}
        )
        self.assertEqual(Counter(case["expect"] for case in cases), EXPECTED_PARTITION)
        self.assertEqual(
            {case["activation"]["head_manifest"] for case in cases},
            ACTIVATION_CONTEXTS,
        )
        for case in cases:
            with self.subTest(case=case["id"]):
                self.assertEqual(
                    tuple(case), ("id", "command", "activation", "expect", "reason")
                )
                self.assertEqual(
                    tuple(case["activation"]), ("head_manifest", "worktree_manifest")
                )
                self.assertIn(case["expect"], EXPECTATIONS)
                self.assertIn(case["activation"]["head_manifest"], ACTIVATION_CONTEXTS)
                self.assertIn(
                    case["activation"]["worktree_manifest"],
                    ACTIVATION_CONTEXTS | {None},
                )
                self.assertTrue(case["command"])
                self.assertTrue(case["reason"])
                if case["expect"].startswith("deny-"):
                    self.assertEqual(case["reason"], DENIALS[case["expect"]])


class HookHarnessMixin:
    """Scratch repositories and a guard invocation helper for hook tests."""

    scratch: Path

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="forge-fr223-v2-hook-")
        self.addCleanup(self.temp_dir.cleanup)
        self.scratch = Path(self.temp_dir.name)

    def git(self, repo: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *arguments],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        )

    def repository(self, head_context: str, worktree_context: str | None) -> Path:
        repo = self.scratch / f"repo-{len(list(self.scratch.iterdir())):02d}"
        repo.mkdir()
        self.git(repo, "init", "--quiet")
        self.git(repo, "config", "user.name", "Forge Tests")
        self.git(repo, "config", "user.email", "forge-tests@example.invalid")
        (repo / "tracked.txt").write_text("baseline\n", encoding="utf-8")
        head = manifest_bytes(head_context)
        if head is not None:
            (repo / ".forge-manifest").write_bytes(head)
        self.git(repo, "add", ".")
        self.git(repo, "commit", "--quiet", "-m", "baseline")
        if worktree_context is not None:
            worktree = manifest_bytes(worktree_context)
            manifest = repo / ".forge-manifest"
            if worktree is None:
                manifest.unlink(missing_ok=True)
            else:
                manifest.write_bytes(worktree)
        return repo

    def invoke(
        self, repo: Path, command: str, *, guard: Path = GUARD
    ) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["CLAUDE_PLUGIN_ROOT"] = str(guard.parents[2])
        environment.pop("CLAUDE_SESSION_ID", None)
        return subprocess.run(
            ["bash", str(guard)],
            cwd=repo,
            env=environment,
            input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command}}),
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def wait_for_advisory_children(self, repo: Path) -> None:
        deadline = time.monotonic() + 5
        pending = repo / ".forge/tmp"
        while time.monotonic() < deadline:
            if not list(pending.glob("decision-event-pending.*")):
                return
            time.sleep(0.01)



class V2HookExecutionTests(HookHarnessMixin, unittest.TestCase):
    def assert_case_result(
        self, result: subprocess.CompletedProcess[str], case: dict[str, object]
    ) -> None:
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        if str(case["expect"]).startswith("deny-"):
            self.assertEqual(json.loads(result.stdout), denial(str(case["reason"])))
        else:
            self.assertEqual(result.stdout, "")

    def test_all_112_v1_classifier_rows_are_unchanged(self) -> None:
        module = load_guard_module(self, "forge_commit_guard_v2_v1_compat")
        for case in read_json(V1_HOOK)["cases"]:
            with self.subTest(case=case["id"]):
                self.assertEqual(
                    module.classify_forge_cli_invocation(case["command"]),
                    case["expect"],
                )

    def test_all_18_additive_cases_execute_against_their_activation_context(self) -> None:
        for case in read_json(V2_HOOK)["cases"]:
            with self.subTest(case=case["id"]):
                activation = case["activation"]
                repo = self.repository(
                    activation["head_manifest"], activation["worktree_manifest"]
                )
                result = self.invoke(repo, case["command"])
                self.assert_case_result(result, case)
                self.wait_for_advisory_children(repo)

    def test_denial_precedence_is_halt_operator_invalid_then_activated(self) -> None:
        enabled = self.repository("forge-verbs-v1", None)
        invalid = self.repository("invalid", None)
        merge_approve = (
            "python3 scripts/forge/cli.py merge approve --candidate "
            + "a" * 64
            + " --chain-id c-2026-08-29T120000Z-abcd"
        )
        operator_over_raw = self.invoke(invalid, merge_approve + "; git push")
        self.assertEqual(json.loads(operator_over_raw.stdout), denial(DENIALS["deny-merge-approve"]))
        invalid_over_raw = self.invoke(invalid, "git commit -m invalid; git push")
        self.assertEqual(json.loads(invalid_over_raw.stdout), denial(DENIALS["deny-invalid-mode"]))
        activated = self.invoke(enabled, "git commit -m activated")
        self.assertEqual(json.loads(activated.stdout), denial(DENIALS["deny-raw-commit"]))

        (enabled / "AGENT_HALT").write_text("halt\n", encoding="utf-8")
        halted = self.invoke(enabled, merge_approve + "; git push")
        self.assertEqual(
            json.loads(halted.stdout),
            denial("forge: operator halt engaged (AGENT_HALT)"),
        )
        self.wait_for_advisory_children(enabled)
        self.wait_for_advisory_children(invalid)

    def test_halt_precedes_a_standalone_operator_verb(self) -> None:
        repo = self.repository("non-forge", None)
        (repo / "AGENT_HALT").write_text("halt\n", encoding="utf-8")
        result = self.invoke(
            repo,
            "python3 scripts/forge/cli.py --repo . merge approve --candidate "
            + "a" * 64,
        )
        self.assertEqual(
            json.loads(result.stdout),
            denial("forge: operator halt engaged (AGENT_HALT)"),
        )
        self.wait_for_advisory_children(repo)

    def test_committed_activation_parser_control_is_load_bearing_in_memory(self) -> None:
        module = load_guard_module(self, "forge_commit_guard_v2_mode_mutant")
        raw = manifest_bytes("forge-verbs-v1")
        process = subprocess.CompletedProcess([], 0, stdout=raw, stderr=b"")
        context = object()
        with mock.patch.object(module, "run_context_git", return_value=process):
            self.assertEqual(
                module.committed_history_mutation_mode(context), "forge-verbs-v1"
            )
            with mock.patch.object(module, "HEAD_PLUGIN_REF_LINE", re.compile(br"a^")):
                self.assertEqual(
                    module.committed_history_mutation_mode(context), "non-forge"
                )

    def test_committed_activation_parser_rejects_every_invalid_form(self) -> None:
        module = load_guard_module(self, "forge_commit_guard_v2_mode_forms")
        context = object()
        valid = manifest_bytes("forge-verbs-v1")
        self.assertIsNotNone(valid)
        prefix, suffix = valid.split(
            b"history_mutation_mode: forge-verbs-v1\n", 1
        )
        cases = {
            "duplicate": (
                prefix
                + b"history_mutation_mode: forge-verbs-v1\n"
                + b"history_mutation_mode: legacy-v1\n"
                + suffix
            ),
            "empty": prefix + b"history_mutation_mode:\n" + suffix,
            "malformed": prefix + b"history_mutation_mode = forge-verbs-v1\n" + suffix,
            "misplaced": prefix + suffix + b"history_mutation_mode: forge-verbs-v1\n",
            "unknown": prefix + b"history_mutation_mode: future-v9\n" + suffix,
            "non-utf8": valid + b"\xff",
            "carriage-return": valid.replace(b"\n", b"\r\n"),
            "unterminated": valid.rstrip(b"\n"),
        }
        for label, raw in cases.items():
            with self.subTest(label=label):
                process = subprocess.CompletedProcess([], 0, stdout=raw, stderr=b"")
                with mock.patch.object(module, "run_context_git", return_value=process):
                    self.assertEqual(
                        module.committed_history_mutation_mode(context), "invalid"
                    )

    def test_all_operator_verbs_deny_with_globals_in_every_position(self) -> None:
        module = load_guard_module(self, "forge_commit_guard_v2_all_operators")
        cases = {
            "deny-approve": (
                "python3 scripts/forge/cli.py --repo=. commit approve --candidate x",
                "python3 scripts/forge/cli.py commit --run-id run-1 approve --candidate x",
                "python3 scripts/forge/cli.py commit approve --chain-id chain-1",
            ),
            "deny-skip": (
                "python3 scripts/forge/cli.py --repo . commit skip gate-1",
                "python3 scripts/forge/cli.py commit --run-id=run-1 skip gate-1",
                "python3 scripts/forge/cli.py commit skip --chain-id chain-1 gate-1",
            ),
        }
        repo = self.repository("non-forge", None)
        for expectation, commands in cases.items():
            for command in commands:
                with self.subTest(expectation=expectation, command=command):
                    self.assertEqual(
                        module.classify_forge_cli_invocation(command), expectation
                    )
                    result = self.invoke(repo, command)
                    self.assertEqual(
                        json.loads(result.stdout),
                        denial(LEGACY_OPERATOR_DENIALS[expectation]),
                    )
        mutant = cases["deny-approve"][0]
        with mock.patch.object(
            module, "_without_forge_global_options", return_value=[]
        ):
            self.assertEqual(module.classify_forge_cli_invocation(mutant), "no-match")
        self.wait_for_advisory_children(repo)

    def test_executable_substitutions_and_groups_cannot_hide_raw_git(self) -> None:
        outer = self.repository("non-forge", None)
        enabled = self.repository("forge-verbs-v1", None)
        invalid = self.repository("invalid", None)
        commands = {
            "dollar substitution": (
                'python3 scripts/forge/cli.py commit finalize --message "$(git push)"',
                "deny-raw-push",
            ),
            "backtick substitution": (
                "python3 scripts/forge/cli.py commit finalize --message `git commit -m nested`",
                "deny-raw-commit",
            ),
            "input process substitution": (
                "python3 scripts/forge/cli.py commit finalize <(git push)",
                "deny-raw-push",
            ),
            "output process substitution": (
                "printf ignored > >(git commit -m nested)",
                "deny-raw-commit",
            ),
            "nested process substitution": (
                "printf %s \"$(printf %s <(printf %s ')' > >(git push)))\"",
                "deny-raw-push",
            ),
            "case in dollar substitution": (
                'echo "$(case x in x) git push;; esac)"',
                "deny-raw-push",
            ),
            "case in input process substitution": (
                "cat <(case x in x) git push;; esac)",
                "deny-raw-push",
            ),
            "case in output process substitution": (
                "cat > >(case x in x) git push;; esac)",
                "deny-raw-push",
            ),
            "nested case in dollar substitution": (
                'echo "$(case x in x) case y in y) git push;; esac;; esac)"',
                "deny-raw-push",
            ),
            "nested case in input process substitution": (
                "cat <(case x in x) case y in y) git push;; esac;; esac)",
                "deny-raw-push",
            ),
            "nested case in output process substitution": (
                "cat > >(case x in x) case y in y) git push;; esac;; esac)",
                "deny-raw-push",
            ),
            "controlled case in dollar substitution": (
                'echo "$(if true; then case x in x) git push;; esac; fi)"',
                "deny-raw-push",
            ),
            "controlled case in input process substitution": (
                "cat <(if true; then case x in x) git push;; esac; fi)",
                "deny-raw-push",
            ),
            "controlled case in output process substitution": (
                "cat > >(if true; then case x in x) git push;; esac; fi)",
                "deny-raw-push",
            ),
            "reserved case words in dollar substitution": (
                'echo "$(case case in case) git push;; esac)"',
                "deny-raw-push",
            ),
            "reserved case words in input process substitution": (
                "cat <(case case in case) git push;; esac)",
                "deny-raw-push",
            ),
            "reserved case words in output process substitution": (
                "cat > >(case case in case) git push;; esac)",
                "deny-raw-push",
            ),
            "escaped nested backticks": (
                r"echo `echo \`git push\``",
                "deny-raw-push",
            ),
            "subshell group": ("(git push origin HEAD:main)", "deny-raw-push"),
            "brace group": ("{ git commit -m grouped; }", "deny-raw-commit"),
        }
        for label, (command, expectation) in commands.items():
            for repo, expected in (
                (enabled, DENIALS[expectation]),
                (invalid, DENIALS["deny-invalid-mode"]),
            ):
                with self.subTest(label=label, context=repo.name):
                    result = self.invoke(repo, command)
                    self.assertEqual(json.loads(result.stdout), denial(expected))

        enabled_arg = shlex.quote(str(enabled))
        invalid_arg = shlex.quote(str(invalid))
        input_with_separator = f"cat <(cd {enabled_arg}; git push)"
        output_with_separator = (
            f"cat > >(cd {invalid_arg}; git commit -m process-substitution)"
        )
        targeted = self.invoke(outer, input_with_separator)
        self.assertEqual(
            json.loads(targeted.stdout), denial(DENIALS["deny-raw-push"])
        )
        invalid_targeted = self.invoke(outer, output_with_separator)
        self.assertEqual(
            json.loads(invalid_targeted.stdout), denial(DENIALS["deny-invalid-mode"])
        )

        quoted_data = self.invoke(
            enabled,
            "python3 scripts/forge/cli.py commit finalize --message "
            "'$(git push); `git commit -m inert`; <(git push); >(git commit)' "
            "--message \"<(git push); >(git commit -m inert)\"",
        )
        self.assertEqual(quoted_data.stdout, "")
        module = load_guard_module(self, "forge_commit_guard_v2_nested_mutant")
        hidden = commands["nested process substitution"][0]
        operator_hidden = (
            "cat <(python3 scripts/forge/cli.py merge approve --candidate "
            + "a" * 64
            + ")"
        )
        self.assertEqual([item.subcommand for item in module.find_actions(hidden)], ["push"])
        self.assertEqual(
            module.classify_forge_cli_invocation(operator_hidden),
            "deny-merge-approve",
        )
        operator_result = self.invoke(outer, operator_hidden)
        self.assertEqual(
            json.loads(operator_result.stdout),
            denial(DENIALS["deny-merge-approve"]),
        )
        direct_operator = (
            "python3 scripts/forge/cli.py merge approve --candidate " + "a" * 64
        )
        for prefix in ("! ", "time "):
            prefixed_operator = prefix + direct_operator
            with self.subTest(prefix=prefix.strip()):
                self.assertEqual(
                    module.classify_forge_cli_invocation(prefixed_operator),
                    "deny-merge-approve",
                )
                prefixed_result = self.invoke(outer, prefixed_operator)
                self.assertEqual(
                    json.loads(prefixed_result.stdout),
                    denial(DENIALS["deny-merge-approve"]),
                )
        with mock.patch.object(module, "RAW_SEGMENT_PASS_ENABLED", False), mock.patch.object(module, "executable_subcommands", return_value=[]):
            self.assertEqual(module.find_actions(hidden), [])
            self.assertEqual(
                module.classify_forge_cli_invocation(operator_hidden), "no-match"
            )
        nested_backticks = commands["escaped nested backticks"][0]
        self.assertEqual(
            [action.subcommand for action in module.find_actions(nested_backticks)],
            ["push"],
        )
        with mock.patch.object(
            module, "_legacy_backtick_body", side_effect=lambda body: body
        ):
            self.assertEqual(module.find_actions(nested_backticks), [])
        case_hidden = commands["case in input process substitution"][0]
        self.assertEqual(
            [action.subcommand for action in module.find_actions(case_hidden)],
            ["push"],
        )
        with mock.patch.object(module, "RAW_SEGMENT_PASS_ENABLED", False), mock.patch.object(module, "executable_case_bodies", return_value=[]):
            self.assertEqual(module.find_actions(case_hidden), [])
        nested_case_hidden = commands["nested case in input process substitution"][0]
        self.assertEqual(
            [action.subcommand for action in module.find_actions(nested_case_hidden)],
            ["push"],
        )
        with mock.patch.object(module, "RAW_SEGMENT_PASS_ENABLED", False), mock.patch.object(module, "_nested_case_end", return_value=None):
            self.assertEqual(module.find_actions(nested_case_hidden), [])
        controlled_case = commands["controlled case in input process substitution"][0]
        self.assertEqual(
            [action.subcommand for action in module.find_actions(controlled_case)],
            ["push"],
        )
        with mock.patch.object(
            module, "_reserved_word_opens_command", return_value=False
        ):
            self.assertEqual(module.find_actions(controlled_case), [])
        reserved_case = commands["reserved case words in input process substitution"][0]
        self.assertEqual(
            [action.subcommand for action in module.find_actions(reserved_case)],
            ["push"],
        )
        with mock.patch.object(module, "RAW_SEGMENT_PASS_ENABLED", False), mock.patch.object(module, "_matching_case_end", return_value=None):
            self.assertEqual(module.find_actions(reserved_case), [])
        quoted_process = 'echo "<(git push)"'
        self.assertEqual(module.find_actions(quoted_process), [])
        with mock.patch.object(
            module,
            "_executable_parenthesis_at",
            side_effect=lambda command, index, quote: command.startswith(
                ("$(", "<(", ">("), index
            ),
        ):
            self.assertEqual(
                [action.subcommand for action in module.find_actions(quoted_process)],
                ["push"],
            )
        with mock.patch.object(module.Path, "cwd", return_value=outer.resolve()):
            protected_actions = module.find_actions(input_with_separator)
        self.assertEqual(
            [action.shell_cwd for action in protected_actions], [enabled.resolve()]
        )
        with (
            mock.patch.object(module.Path, "cwd", return_value=outer.resolve()),
            mock.patch.object(module, "_opaque_executable_end", return_value=None),
        ):
            unprotected_actions = module.find_actions(input_with_separator)
        self.assertEqual(
            [action.shell_cwd for action in unprotected_actions], [outer.resolve()]
        )
        self.assertEqual(module.executable_subcommands(r"echo \<(git push)"), [])
        self.wait_for_advisory_children(outer)
        self.wait_for_advisory_children(enabled)
        self.wait_for_advisory_children(invalid)

    def test_ambiguous_shell_flow_retains_every_security_relevant_cwd(self) -> None:
        enabled = self.repository("forge-verbs-v1", None)
        invalid = self.repository("invalid", None)
        non_forge = self.repository("non-forge", None)
        non_forge_arg = shlex.quote(str(non_forge))
        commands = {
            "conditional": f"true || cd {non_forge_arg}; git push",
            "background": f"cd {non_forge_arg} & git push",
            "pipeline cd": f"cd {non_forge_arg} | git push",
            "pipeline group": f"{{ cd {non_forge_arg}; }} | cat; git push",
        }
        for label, command in commands.items():
            for repo, reason in (
                (enabled, DENIALS["deny-raw-push"]),
                (invalid, DENIALS["deny-invalid-mode"]),
            ):
                with self.subTest(label=label, context=repo.name):
                    result = self.invoke(repo, command)
                    self.assertEqual(json.loads(result.stdout), denial(reason))

        background_list = (
            f"cd {non_forge_arg} && git push & git commit -m bypass"
        )
        enabled_background_list = self.invoke(enabled, background_list)
        self.assertEqual(
            json.loads(enabled_background_list.stdout),
            denial(DENIALS["deny-raw-commit"]),
        )
        invalid_background_list = self.invoke(invalid, background_list)
        self.assertEqual(
            json.loads(invalid_background_list.stdout),
            denial(DENIALS["deny-invalid-mode"]),
        )

        module = load_guard_module(self, "forge_commit_guard_v2_cwd_sets")
        with mock.patch.object(module.Path, "cwd", return_value=enabled.resolve()):
            conditional_actions = module.find_actions(commands["conditional"])
            background_actions = module.find_actions(commands["background"])
            pipeline_cd_actions = module.find_actions(commands["pipeline cd"])
            pipeline_actions = module.find_actions(commands["pipeline group"])
            background_list_actions = module.find_actions(background_list)
        self.assertEqual(
            [action.shell_cwd for action in conditional_actions],
            [enabled.resolve(), non_forge.resolve()],
        )
        self.assertEqual(
            [action.shell_cwd for action in background_actions], [enabled.resolve()]
        )
        self.assertEqual(
            [action.shell_cwd for action in pipeline_cd_actions], [enabled.resolve()]
        )
        self.assertEqual(
            [action.shell_cwd for action in pipeline_actions], [enabled.resolve()]
        )
        self.assertEqual(
            [
                (action.subcommand, action.shell_cwd)
                for action in background_list_actions
            ],
            [("push", non_forge.resolve()), ("commit", enabled.resolve())],
        )

        def drop_conditional_skip(
            tokens: list[str],
            cwds: tuple[Path, ...],
            separator: str | None,
            *,
            may_skip: bool,
            isolated: bool,
        ) -> tuple[Path, ...]:
            del may_skip
            if isolated:
                return cwds
            return module._unique_cwds(
                tuple(module.updated_cwd(tokens, cwd, separator) for cwd in cwds)
            )

        with (
            mock.patch.object(module.Path, "cwd", return_value=enabled.resolve()),
            mock.patch.object(
                module, "updated_cwd_states", side_effect=drop_conditional_skip
            ),
        ):
            conditional_mutant = module.find_actions(commands["conditional"])
        self.assertEqual(
            [action.shell_cwd for action in conditional_mutant],
            [non_forge.resolve()],
        )

        def leak_isolated_cd(
            tokens: list[str],
            cwds: tuple[Path, ...],
            separator: str | None,
            *,
            may_skip: bool,
            isolated: bool,
        ) -> tuple[Path, ...]:
            del separator, may_skip, isolated
            return module._unique_cwds(
                tuple(module.updated_cwd(tokens, cwd, None) for cwd in cwds)
            )

        with (
            mock.patch.object(module.Path, "cwd", return_value=enabled.resolve()),
            mock.patch.object(
                module, "updated_cwd_states", side_effect=leak_isolated_cd
            ),
        ):
            isolated_mutant = module.find_actions(commands["pipeline cd"])
        self.assertEqual(
            [action.shell_cwd for action in isolated_mutant],
            [non_forge.resolve()],
        )

        with (
            mock.patch.object(module.Path, "cwd", return_value=enabled.resolve()),
            mock.patch.object(
                module,
                "cwd_after_group_exit",
                side_effect=lambda opener, inherited, current, isolated: current,
            ),
        ):
            pipeline_mutant = module.find_actions(commands["pipeline group"])
        self.assertEqual(
            [action.shell_cwd for action in pipeline_mutant],
            [non_forge.resolve()],
        )
        with (
            mock.patch.object(module.Path, "cwd", return_value=enabled.resolve()),
            mock.patch.object(
                module,
                "cwd_after_async_list",
                side_effect=lambda inherited, current: current,
            ),
        ):
            async_list_mutant = module.find_actions(background_list)
        self.assertEqual(
            [(action.subcommand, action.shell_cwd) for action in async_list_mutant],
            [("push", non_forge.resolve()), ("commit", non_forge.resolve())],
        )
        self.wait_for_advisory_children(enabled)
        self.wait_for_advisory_children(invalid)
        self.wait_for_advisory_children(non_forge)

    def test_cd_before_commit_is_bundled_even_with_a_valid_marker(self) -> None:
        repo = self.repository("legacy-v1", None)
        staged = repo / "bundled.txt"
        staged.write_text("bundled\n", encoding="utf-8")
        self.git(repo, "add", staged.name)
        diff = subprocess.run(
            ["git", "diff", "--cached"],
            cwd=repo,
            check=True,
            capture_output=True,
        ).stdout
        candidate = hashlib.sha256(diff).hexdigest()
        marker = repo / ".forge/tmp/authorized" / candidate
        marker.parent.mkdir(parents=True)
        marker.write_text(
            candidate
            + "\n"
            + datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            + "\n",
            encoding="utf-8",
        )
        command = f"cd {shlex.quote(str(repo))} && git commit -m reviewed"
        result = self.invoke(self.scratch, command)
        self.assertEqual(
            json.loads(result.stdout),
            denial(
                "forge: commit not authorized — run /forge:commit "
                "(marker hash mismatch)"
            ),
        )

        module = load_guard_module(self, "forge_commit_guard_v2_cd_precedes")
        with mock.patch.object(module.Path, "cwd", return_value=self.scratch.resolve()):
            actions = module.find_actions(command)
        self.assertEqual([action.preceded_by_command for action in actions], [True])
        with (
            mock.patch.object(module.Path, "cwd", return_value=self.scratch.resolve()),
            mock.patch.object(
                module,
                "segment_advances_executable_seen",
                side_effect=lambda tokens: bool(tokens and tokens[0] != "cd"),
            ),
        ):
            mutant_actions = module.find_actions(command)
        self.assertEqual(
            [action.preceded_by_command for action in mutant_actions], [False]
        )
        self.wait_for_advisory_children(repo)

    def test_grouped_cd_uses_group_scope_and_target_repository_context(self) -> None:
        outer = self.repository("non-forge", None)
        enabled = self.repository("forge-verbs-v1", None)
        invalid = self.repository("invalid", None)
        enabled_arg = shlex.quote(str(enabled))
        invalid_arg = shlex.quote(str(invalid))
        cases = {
            "enabled subshell": (
                f"(cd {enabled_arg}; git push)",
                DENIALS["deny-raw-push"],
            ),
            "enabled brace": (
                f"{{ cd {enabled_arg}; git commit -m grouped; }}",
                DENIALS["deny-raw-commit"],
            ),
            "invalid subshell": (
                f"(cd {invalid_arg}; git commit -m grouped)",
                DENIALS["deny-invalid-mode"],
            ),
            "invalid brace": (
                f"{{ cd {invalid_arg}; git push; }}",
                DENIALS["deny-invalid-mode"],
            ),
            "negated enabled subshell": (
                f"! (cd {enabled_arg}; git push)",
                DENIALS["deny-raw-push"],
            ),
            "timed invalid brace": (
                f"time {{ cd {invalid_arg}; git commit -m timed; }}",
                DENIALS["deny-invalid-mode"],
            ),
            "nested prefixed groups": (
                f"(! (cd {enabled_arg}; git push))",
                DENIALS["deny-raw-push"],
            ),
        }
        for label, (command, reason) in cases.items():
            with self.subTest(label=label):
                result = self.invoke(outer, command)
                self.assertEqual(json.loads(result.stdout), denial(reason))

        restored = self.invoke(outer, f"(cd {enabled_arg}); git push")
        self.assertEqual(restored.stdout, "")
        persisted = self.invoke(outer, f"{{ cd {enabled_arg}; }}; git push")
        self.assertEqual(
            json.loads(persisted.stdout), denial(DENIALS["deny-raw-push"])
        )
        invalid_persisted = self.invoke(outer, f"{{ cd {invalid_arg}; }}; git push")
        self.assertEqual(
            json.loads(invalid_persisted.stdout), denial(DENIALS["deny-invalid-mode"])
        )

        module = load_guard_module(self, "forge_commit_guard_v2_group_cwd")
        subshell = f"(cd {enabled_arg}; git push); git commit -m outer"
        brace = f"{{ cd {enabled_arg}; git push; }}; git commit -m after"
        array_in_subshell = (
            f"(cd {enabled_arg}; values=(x); git push); git commit -m outer"
        )
        case_in_subshell = (
            f"(cd {enabled_arg}; case x in x) printf x;; esac; git push); "
            "git commit -m outer"
        )
        with mock.patch.object(module.Path, "cwd", return_value=outer.resolve()):
            subshell_actions = module.find_actions(subshell)
            brace_actions = module.find_actions(brace)
            array_actions = module.find_actions(array_in_subshell)
            case_actions = module.find_actions(case_in_subshell)
        self.assertEqual(
            [(action.subcommand, action.shell_cwd) for action in subshell_actions],
            [("push", enabled.resolve()), ("commit", outer.resolve())],
        )
        # The structured parse tracks the cwd through the case compound; the
        # raw-pass union then adds the pre-slice-7 (HEAD-equivalent) reading in
        # which the pattern's `)` closed the subshell early. That artifact is
        # retained deliberately: the union may only widen what the guard sees.
        self.assertEqual(
            [(action.subcommand, action.shell_cwd) for action in case_actions],
            [
                ("push", enabled.resolve()),
                ("commit", outer.resolve()),
                ("push", outer.resolve()),
            ],
        )
        self.assertEqual(
            [(action.subcommand, action.shell_cwd) for action in brace_actions],
            [("push", enabled.resolve()), ("commit", enabled.resolve())],
        )
        self.assertEqual(
            [(action.subcommand, action.shell_cwd) for action in array_actions],
            [("push", enabled.resolve()), ("commit", outer.resolve())],
        )
        prefixed_group = f"! (cd {enabled_arg}; git push)"
        with (
            mock.patch.object(module.Path, "cwd", return_value=outer.resolve()),
            mock.patch.object(
                module,
                "_shell_prefix_end",
                side_effect=lambda syntax, start, positions: start,
            ),
        ):
            prefix_mutant = module.find_actions(prefixed_group)
        self.assertEqual(
            [action.shell_cwd for action in prefix_mutant], [outer.resolve()]
        )
        with (
            mock.patch.object(module.Path, "cwd", return_value=outer.resolve()),
            mock.patch.object(
                module, "_mask_word_parentheses", side_effect=lambda syntax: syntax
            ),
        ):
            array_mutant = module.find_actions(array_in_subshell)
        self.assertEqual(
            [action.shell_cwd for action in array_mutant],
            [outer.resolve(), outer.resolve()],
        )

        with (
            mock.patch.object(module.Path, "cwd", return_value=outer.resolve()),
            mock.patch.object(
                module, "updated_cwd", side_effect=lambda tokens, cwd, separator: cwd
            ),
        ):
            disabled_cd_actions = module.find_actions(subshell)
        self.assertEqual(
            [action.shell_cwd for action in disabled_cd_actions],
            [outer.resolve(), outer.resolve()],
        )

        real_structure = module.shell_group_structure

        def without_group_scope(segment: str) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
            normalized, _openers, _closers = real_structure(segment)
            return normalized, (), ()

        with (
            mock.patch.object(module.Path, "cwd", return_value=outer.resolve()),
            mock.patch.object(
                module, "shell_group_structure", side_effect=without_group_scope
            ),
        ):
            disabled_scope_actions = module.find_actions(subshell)
        self.assertEqual(
            [action.shell_cwd for action in disabled_scope_actions],
            [enabled.resolve(), enabled.resolve()],
        )
        with (
            mock.patch.object(module.Path, "cwd", return_value=outer.resolve()),
            mock.patch.object(
                module,
                "cwd_after_group_exit",
                side_effect=lambda opener, inherited, current, isolated: inherited,
            ),
        ):
            disabled_brace_actions = module.find_actions(brace)
        self.assertEqual(
            [action.shell_cwd for action in disabled_brace_actions],
            [enabled.resolve(), outer.resolve()],
        )
        self.wait_for_advisory_children(outer)
        self.wait_for_advisory_children(enabled)
        self.wait_for_advisory_children(invalid)

    def test_merge_global_option_control_is_load_bearing_in_memory(self) -> None:
        module = load_guard_module(self, "forge_commit_guard_v2_global_mutant")
        command = next(
            case["command"]
            for case in read_json(V2_HOOK)["cases"]
            if case["id"] == "deny-merge-approve-global-between-middle"
        )
        self.assertEqual(
            module.classify_forge_cli_invocation(command), "deny-merge-approve"
        )
        with mock.patch.object(
            module, "_without_forge_global_options", return_value=[]
        ):
            self.assertEqual(module.classify_forge_cli_invocation(command), "no-match")

    def test_mutated_corpus_byte_changes_behavior_but_retains_exact_denial(self) -> None:
        package = self.scratch / "mutated-package"
        guard = package / "scripts/forge/commit-guard.sh"
        corpus = package / "system/fr223/hook-argv-cases-v2.json"
        guard.parent.mkdir(parents=True)
        corpus.parent.mkdir(parents=True)
        shutil.copy2(GUARD, guard)
        payload = read_json(V2_HOOK)
        mutated_reason = "forge: corpus mutation observed — merge approval denied"
        for case in payload["cases"]:
            if case["expect"] == "deny-merge-approve":
                case["reason"] = mutated_reason
        corpus.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        repo = self.repository("non-forge", None)
        command = next(
            case["command"]
            for case in payload["cases"]
            if case["expect"] == "deny-merge-approve"
        )
        original = self.invoke(repo, command)
        mutated = self.invoke(repo, command, guard=guard)
        self.assertEqual(json.loads(original.stdout), denial(DENIALS["deny-merge-approve"]))
        self.assertEqual(
            json.loads(mutated.stdout), denial(DENIALS["deny-merge-approve"])
        )
        self.assertEqual(original.returncode, 0)
        self.assertEqual(mutated.returncode, 2)
        self.assertEqual(mutated.stderr, DENIALS["deny-merge-approve"] + "\n")

    def test_corpus_byte_pin_and_strict_parser_are_load_bearing(self) -> None:
        module = load_guard_module(self, "forge_commit_guard_v2_corpus_mutants")
        self.assertEqual(module.load_v2_denials(V2_HOOK), DENIALS)
        payload = read_json(V2_HOOK)
        payload["cases"][0]["command"] += " --mutated"
        mutated = self.scratch / "mutated-corpus.json"
        mutated.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "manifested generation"):
            module.load_v2_denials(mutated)
        mutated_digest = hashlib.sha256(mutated.read_bytes()).hexdigest()
        with mock.patch.object(module, "V2_CORPUS_SHA256", mutated_digest):
            self.assertEqual(module.load_v2_denials(mutated), DENIALS)

        malformed_payloads = []
        floating = read_json(V2_HOOK)
        floating["case_count"] = 18.0
        malformed_payloads.append(floating)
        floating_v1 = read_json(V2_HOOK)
        floating_v1["v1"]["case_count"] = 112.0
        malformed_payloads.append(floating_v1)
        surrogate = read_json(V2_HOOK)
        surrogate["cases"][0]["reason"] = "\ud800"
        malformed_payloads.append(surrogate)
        original = read_json(V2_HOOK)
        reordered = {key: original[key] for key in reversed(tuple(original))}
        malformed_payloads.append(reordered)
        for index, malformed in enumerate(malformed_payloads):
            path = self.scratch / f"malformed-{index}.json"
            path.write_text(
                json.dumps(malformed, ensure_ascii=True, indent=2) + "\n",
                encoding="utf-8",
            )
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            with self.subTest(index=index), mock.patch.object(
                module, "V2_CORPUS_SHA256", digest
            ):
                with self.assertRaises(ValueError):
                    module.load_v2_denials(path)


class GuardParserBoundTests(HookHarnessMixin, unittest.TestCase):
    """The guard parser fails closed under hostile nesting, slow parses, and crashes.

    Review-final iteration 1 on chain c-2026-09-02T222538Z-66e0 showed the
    recursive substitution parser escaping ``main()`` with a RecursionError
    (exit 1, no deny JSON: fail-open) and nested case compounds outrunning the
    hook deadline. Every bound here has an in-memory disable proving it is
    load-bearing.
    """

    @staticmethod
    def substitution_bomb(depth: int) -> str:
        return "$(" * depth + "true" + ")" * depth

    @staticmethod
    def case_bomb(depth: int, inner: str = "git push origin HEAD:main") -> str:
        return "case x in x) " * depth + inner + ";; esac" * depth

    def test_failsafe_literals_and_bounds_are_pinned(self) -> None:
        module = load_guard_module(self, "forge_commit_guard_bounds_literals")
        self.assertEqual(module.GUARD_FAILSAFE_DENIALS, FAILSAFE_DENIALS)
        self.assertEqual(module.GUARD_FAILSAFE_REASON_CODES, FAILSAFE_REASON_CODES)
        self.assertEqual(module.MAX_NESTING_DEPTH, 64)
        self.assertEqual(module.PARSE_TIME_BUDGET_SECONDS, 10.0)
        self.assertLess(module.MAX_NESTING_DEPTH * 4, sys.getrecursionlimit())

    def test_nesting_bound_denies_deep_substitutions_and_is_load_bearing(self) -> None:
        module = load_guard_module(self, "forge_commit_guard_bounds_nesting")
        command = "git push origin HEAD:main; : " + self.substitution_bomb(100)
        with self.assertRaises(module.GuardInputBoundExceeded) as caught:
            module._classify_command_bounded(command)
        self.assertEqual(caught.exception.kind, "nesting")
        self.assertEqual(module._nesting_depth, 0)
        quoted = 'git push origin HEAD:main; echo "' + self.substitution_bomb(100) + '"'
        with self.assertRaises(module.GuardInputBoundExceeded):
            module._classify_command_bounded(quoted)
        with mock.patch.object(module, "MAX_NESTING_DEPTH", 10**6):
            actions, cli_class = module._classify_command_bounded(command)
        self.assertEqual([action.subcommand for action in actions], ["push"])
        self.assertEqual(cli_class, "no-match")
        self.assertEqual(module._nesting_depth, 0)
        # The pinned literal states the true threshold: 63 classifies, 64 denies.
        admitted, _cli_class = module._classify_command_bounded(
            "git push origin HEAD:main; : " + self.substitution_bomb(63)
        )
        self.assertEqual([action.subcommand for action in admitted], ["push"])
        with self.assertRaises(module.GuardInputBoundExceeded):
            module._classify_command_bounded(
                "git push origin HEAD:main; : " + self.substitution_bomb(64)
            )

    def test_case_nesting_bound_is_load_bearing(self) -> None:
        module = load_guard_module(self, "forge_commit_guard_bounds_case")
        command = self.case_bomb(66)
        with self.assertRaises(module.GuardInputBoundExceeded) as caught:
            module._classify_command_bounded(command)
        self.assertEqual(caught.exception.kind, "nesting")
        with mock.patch.object(module, "MAX_NESTING_DEPTH", 10**6):
            actions, _cli_class = module._classify_command_bounded(command)
        self.assertEqual([action.subcommand for action in actions], ["push"])

    def test_interpreter_recursion_failure_reaches_the_failsafe_deny(self) -> None:
        module = load_guard_module(self, "forge_commit_guard_bounds_recursion")
        command = "git push origin HEAD:main; : " + self.substitution_bomb(1200)
        with mock.patch.object(module, "MAX_NESTING_DEPTH", 10**6):
            with self.assertRaises(RecursionError):
                module._classify_command_bounded(command)
        # With the nesting bound disabled in a copied guard, the failsafe handler
        # is the last line of defence: still a deny on both channels, exit 2.
        package = self.scratch / "unbounded-package"
        guard = package / "scripts/forge/commit-guard.sh"
        guard.parent.mkdir(parents=True)
        for sibling in ("check-halt.sh", "risk_tier.py", "emit-decision-event.py"):
            shutil.copy2(GUARD.parent / sibling, guard.parent / sibling)
        (package / "system/fr223").mkdir(parents=True)
        shutil.copy2(V2_HOOK, package / "system/fr223/hook-argv-cases-v2.json")
        source = GUARD.read_text(encoding="utf-8")
        self.assertEqual(source.count("\nMAX_NESTING_DEPTH = 64\n"), 1)
        guard.write_text(
            source.replace("\nMAX_NESTING_DEPTH = 64\n", "\nMAX_NESTING_DEPTH = 1000000\n"),
            encoding="utf-8",
        )
        shutil.copymode(GUARD, guard)
        repo = self.repository("forge-verbs-v1", None)
        result = self.invoke(repo, command, guard=guard)
        expected = FAILSAFE_DENIALS["internal"].format(failure="RecursionError")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout), denial(expected))
        self.assertEqual(result.stderr, expected + "\n")

    def test_time_budget_denies_a_slow_parse_and_is_load_bearing(self) -> None:
        module = load_guard_module(self, "forge_commit_guard_bounds_time")

        def slow_find_actions(_command: str) -> list[object]:
            time.sleep(2.0)
            return []

        with mock.patch.object(module, "find_actions", slow_find_actions):
            with mock.patch.object(module, "PARSE_TIME_BUDGET_SECONDS", 0.1):
                started = time.monotonic()
                with self.assertRaises(module.GuardInputBoundExceeded) as caught:
                    module._classify_command_bounded("git status")
                self.assertEqual(caught.exception.kind, "time")
                self.assertLess(time.monotonic() - started, 1.5)
            self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))
            with mock.patch.object(module, "PARSE_TIME_BUDGET_SECONDS", 0):
                self.assertEqual(
                    module._classify_command_bounded("git status"), ([], "no-match")
                )
            self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))

    def test_hostile_nesting_is_denied_on_every_precedence_path(self) -> None:
        enabled = self.repository("forge-verbs-v1", None)
        legacy = self.repository("legacy-v1", None)
        halted = self.repository("forge-verbs-v1", None)
        (halted / "AGENT_HALT").write_text("halt\n", encoding="utf-8")
        push_bomb = "git push origin HEAD:main; : " + self.substitution_bomb(1200)
        expected = FAILSAFE_DENIALS["nesting"]
        for repo, command in (
            (enabled, push_bomb),
            (enabled, 'git push origin HEAD:main; echo "' + self.substitution_bomb(1200) + '"'),
            (legacy, "git commit -m bypass; : " + self.substitution_bomb(1200)),
            (halted, push_bomb),
            (enabled, self.case_bomb(700)),
        ):
            started = time.monotonic()
            result = self.invoke(repo, command)
            self.assertLess(time.monotonic() - started, 30.0)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual(json.loads(result.stdout), denial(expected))
            self.assertEqual(result.stderr, expected + "\n")
        self.wait_for_advisory_children(enabled)
        audit = (enabled / ".forge/tmp/halt-audit.log").read_text(encoding="utf-8")
        self.assertIn("executable=guard deny=guard-input-bound", audit)

    def test_ordinary_nesting_and_baseline_denials_are_unchanged(self) -> None:
        enabled = self.repository("forge-verbs-v1", None)
        baseline = self.invoke(enabled, "git push origin HEAD:main")
        self.assertEqual(baseline.returncode, 0, baseline.stderr)
        self.assertEqual(json.loads(baseline.stdout), denial(DENIALS["deny-raw-push"]))
        for command in (
            "git status; : " + self.substitution_bomb(40),
            self.case_bomb(40, inner="git status"),
            "git push origin HEAD:main; : " + self.substitution_bomb(40),
        ):
            result = self.invoke(enabled, command)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, "")
        denied = self.invoke(enabled, "git push origin HEAD:main; : " + self.substitution_bomb(40))
        self.assertEqual(json.loads(denied.stdout), denial(DENIALS["deny-raw-push"]))


class GuardSegmentationAndResolutionTests(HookHarnessMixin, unittest.TestCase):
    """Review-final iteration 2 on chain c-2026-09-02T222538Z-66e0.

    A double-quoted `case` word must never merge the surrounding segments
    (CRITICAL), post-parse context resolution must be memoized and budgeted so a
    flood of distinct actions cannot outrun the hook deadline (MAJOR), and case
    bodies must be visited once so alternating nesting stays linear (MINOR).
    """

    QUOTED_CASE_SHAPES = (
        'echo "; case"; {inner}; case a in a) :;; esac',
        'echo "\ncase"; {inner}; case a in a) :;; esac',
        'echo "&& case"; {inner}; case a in a) :;; esac',
        'echo "| case"; {inner}; case a in a) :;; esac',
    )

    def test_quoted_case_word_never_merges_segments_and_the_seam_is_load_bearing(
        self,
    ) -> None:
        module = load_guard_module(self, "forge_commit_guard_quoted_case")
        for shape in self.QUOTED_CASE_SHAPES:
            with self.subTest(shape=shape):
                push = shape.format(inner="git push origin HEAD:main")
                self.assertEqual(len(module.split_segments(push)), 3)
                self.assertEqual(
                    [action.subcommand for action in module.find_actions(push)],
                    ["push"],
                )
                commit = shape.format(inner="git commit -m bypass")
                self.assertEqual(
                    [action.subcommand for action in module.find_actions(commit)],
                    ["commit"],
                )
                approve = shape.format(
                    inner="python3 scripts/forge/cli.py merge approve "
                    "--candidate abc --chain-id c-2026-09-01T000000Z-0000"
                )
                self.assertEqual(
                    module.classify_forge_cli_invocation(approve), "deny-merge-approve"
                )
        # A quoted case word inside a real compound's body must not disturb it.
        real = 'case a in a) echo "; case"; git push origin HEAD:main;; esac'
        self.assertEqual(
            [action.subcommand for action in module.find_actions(real)], ["push"]
        )
        # Layering: with the admission seam disabled the structured split still
        # collapses the segments, but the raw-pass union keeps finding the push;
        # only disabling the union as well hides it.
        exploit = self.QUOTED_CASE_SHAPES[0].format(inner="git push origin HEAD:main")
        with mock.patch.object(
            module, "_case_starts_command", lambda *_arguments: True
        ):
            self.assertEqual(len(module.split_segments(exploit)), 1)
            self.assertEqual(
                [action.subcommand for action in module.find_actions(exploit)],
                ["push"],
            )
            with mock.patch.object(module, "RAW_SEGMENT_PASS_ENABLED", False):
                self.assertEqual(module.find_actions(exploit), [])

    def test_quoted_case_wrapper_is_denied_end_to_end(self) -> None:
        enabled = self.repository("forge-verbs-v1", None)
        legacy = self.repository("legacy-v1", None)
        halted = self.repository("forge-verbs-v1", None)
        (halted / "AGENT_HALT").write_text("halt\n", encoding="utf-8")
        plain = self.repository("non-forge", None)
        shape = self.QUOTED_CASE_SHAPES[0]
        expectations = (
            (enabled, shape.format(inner="git push origin HEAD:main"), DENIALS["deny-raw-push"]),
            (
                legacy,
                shape.format(inner="git commit -m bypass"),
                "forge: commit not authorized — run /forge:commit (marker missing)",
            ),
            (
                halted,
                shape.format(inner="git push origin HEAD:main"),
                "forge: operator halt engaged (AGENT_HALT)",
            ),
            (
                plain,
                shape.format(
                    inner="python3 scripts/forge/cli.py merge approve "
                    "--candidate abc --chain-id c-2026-09-01T000000Z-0000"
                ),
                DENIALS["deny-merge-approve"],
            ),
        )
        for repo, command, reason in expectations:
            with self.subTest(reason=reason):
                result = self.invoke(repo, command)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout), denial(reason))

    def test_distinct_action_flood_is_memoized_and_stays_under_the_deadline(
        self,
    ) -> None:
        enabled = self.repository("forge-verbs-v1", None)
        flood = "; ".join(f"git push origin HEAD:branch-{index}" for index in range(2000))
        started = time.monotonic()
        result = self.invoke(enabled, flood)
        self.assertLess(time.monotonic() - started, 30.0)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), denial(DENIALS["deny-raw-push"]))
        # In memory: memoized resolution costs a handful of Git calls for fifty
        # distinct actions; with the memo disabled every action pays again.
        module = load_guard_module(self, "forge_commit_guard_context_memo")
        actions = [
            module.GitAction(
                subcommand="push",
                executable="git",
                shell_cwd=enabled,
                structural_globals=(),
                assignments=(),
                subcommand_args=("origin", f"HEAD:branch-{index}"),
            )
            for index in range(50)
        ]
        with mock.patch.object(
            module, "run_action_git", wraps=module.run_action_git
        ) as runner:
            module._reset_resolution_memos()
            contexts = [module.resolve_repo_context(action) for action in actions]
            self.assertTrue(all(context is not None for context in contexts))
            memoized_calls = runner.call_count
        self.assertLessEqual(memoized_calls, 6)
        with mock.patch.object(module, "CONTEXT_MEMO_ENABLED", False):
            with mock.patch.object(
                module, "run_action_git", wraps=module.run_action_git
            ) as runner:
                module._reset_resolution_memos()
                for action in actions:
                    module.resolve_repo_context(action)
                unmemoized_calls = runner.call_count
        self.assertGreaterEqual(unmemoized_calls, 100)
        # The budget now also covers resolution: a slow resolver is denied as time.
        def slow_context(_action: object) -> None:
            time.sleep(2.0)
            return None

        with mock.patch.object(module, "repo_context", slow_context):
            with mock.patch.object(module, "PARSE_TIME_BUDGET_SECONDS", 0.1):
                with self.assertRaises(module.GuardInputBoundExceeded) as caught:
                    module._classify_command_bounded(
                        "git push origin HEAD:main", Path("/nonexistent/check-halt.sh")
                    )
        self.assertEqual(caught.exception.kind, "time")
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))

    def test_case_bodies_are_visited_once_and_subject_substitutions_survive(
        self,
    ) -> None:
        module = load_guard_module(self, "forge_commit_guard_case_once")
        alternating = "git push origin HEAD:main"
        for _level in range(16):
            alternating = "$(case x in x) " + alternating + ";; esac)"
        started = time.monotonic()
        actions = module.find_actions(alternating)
        self.assertLess(time.monotonic() - started, 5.0)
        self.assertEqual([action.subcommand for action in actions], ["push"])
        sequential = "; ".join("case a in a) :;; esac" for _index in range(1000))
        started = time.monotonic()
        actions = module.find_actions(sequential + "; git push origin HEAD:main")
        self.assertLess(time.monotonic() - started, 5.0)
        self.assertEqual([action.subcommand for action in actions], ["push"])
        for command in (
            "case $(git push origin HEAD:main) in a) :;; esac",
            "case a in $(git push origin HEAD:main)) :;; esac",
            "case a in a) git push origin HEAD:main;; esac",
            "case a in a) : $(git push origin HEAD:main);; esac",
        ):
            with self.subTest(command=command):
                self.assertEqual(
                    [action.subcommand for action in module.find_actions(command)],
                    ["push"],
                )


class GuardRawSegmentUnionTests(HookHarnessMixin, unittest.TestCase):
    """Review-final iteration 3 on chain c-2026-09-02T222538Z-66e0.

    Bash never treats `case` as reserved after a comment, in a heredoc body, or
    inside `${}`, `[[ ]]`, `(( ))`, but the structured swallow admitted it there
    and merged every later segment into an inert one. The guard now unions the
    structured parse with a raw split (swallow disabled), so no swallow can hide
    a segment that a separator split exposes.
    """

    WRAPPERS = {
        "comment": "true # ; case x in\n{inner}; case a in a) :;; esac",
        "heredoc": "cat <<EOF\ncase x in\nEOF\n{inner}; case a in a) :;; esac",
        "parameter": "echo ${x:-\ncase x in}; {inner}; case a in a) :;; esac",
        "double-bracket": "[[ -n x ||\ncase == x ]]; {inner}; case a in a) :;; esac",
        "arithmetic": "(( 1 +\ncase )); {inner}; case a in a) :;; esac",
        "substitution": "echo $(true # ; case x in\n{inner}; case a in a) :;; esac)",
        "quoted": 'echo "; case"; {inner}; case a in a) :;; esac',
    }
    PUSH = "git push origin HEAD:main"
    COMMIT = "git commit -m bypass"
    APPROVE = (
        "python3 scripts/forge/cli.py merge approve "
        "--candidate abc --chain-id c-2026-09-01T000000Z-0000"
    )

    @classmethod
    def wrap(cls, name: str, inner: str) -> str:
        return cls.WRAPPERS[name].replace("{inner}", inner)

    def test_every_wrapper_is_seen_and_the_union_is_load_bearing(self) -> None:
        module = load_guard_module(self, "forge_commit_guard_raw_union")
        for name in self.WRAPPERS:
            with self.subTest(wrapper=name):
                self.assertEqual(
                    [a.subcommand for a in module.find_actions(self.wrap(name, self.PUSH))],
                    ["push"],
                )
                self.assertEqual(
                    [a.subcommand for a in module.find_actions(self.wrap(name, self.COMMIT))],
                    ["commit"],
                )
                self.assertEqual(
                    module.classify_forge_cli_invocation(self.wrap(name, self.APPROVE)),
                    "deny-merge-approve",
                )
        with mock.patch.object(module, "RAW_SEGMENT_PASS_ENABLED", False):
            for name in ("comment", "heredoc", "parameter"):
                with self.subTest(disabled=name):
                    self.assertEqual(module.find_actions(self.wrap(name, self.PUSH)), [])
                    self.assertEqual(
                        module.classify_forge_cli_invocation(self.wrap(name, self.APPROVE)),
                        "no-match",
                    )

    def test_raw_pass_invents_no_actions_for_genuine_compounds(self) -> None:
        module = load_guard_module(self, "forge_commit_guard_raw_union_genuine")
        for command, expected in (
            ("case a in a) git push origin HEAD:main;; esac", ["push"]),
            ("case x in a) :;; esac; git status", []),
            ("case x in a) :;; b) :;; esac", []),
            ("case $(git push origin HEAD:main) in a) :;; esac", ["push"]),
            ("case a in a) : $(git push origin HEAD:main);; esac", ["push"]),
            ('echo "$(case x in x) git push;; esac)"', ["push"]),
        ):
            with self.subTest(command=command):
                actions = module.find_actions(command)
                self.assertEqual([a.subcommand for a in actions], expected)
                self.assertEqual(len(actions), len(expected))

    def test_wrappers_are_denied_end_to_end(self) -> None:
        enabled = self.repository("forge-verbs-v1", None)
        legacy = self.repository("legacy-v1", None)
        halted = self.repository("forge-verbs-v1", None)
        (halted / "AGENT_HALT").write_text("halt\n", encoding="utf-8")
        plain = self.repository("non-forge", None)
        for name in ("comment", "heredoc", "parameter", "substitution"):
            for repo, inner, reason in (
                (enabled, self.PUSH, DENIALS["deny-raw-push"]),
                (
                    legacy,
                    self.COMMIT,
                    "forge: commit not authorized — run /forge:commit (marker missing)",
                ),
                (halted, self.PUSH, "forge: operator halt engaged (AGENT_HALT)"),
                (plain, self.APPROVE, DENIALS["deny-merge-approve"]),
            ):
                with self.subTest(wrapper=name, reason=reason):
                    result = self.invoke(repo, self.wrap(name, inner))
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(json.loads(result.stdout), denial(reason))

    def test_wide_case_word_input_stays_linear(self) -> None:
        module = load_guard_module(self, "forge_commit_guard_wide_case")
        command = "echo " + "case " * 10000 + "; git push origin HEAD:main"
        started = time.monotonic()
        actions = module.find_actions(command)
        self.assertLess(time.monotonic() - started, 5.0)
        self.assertEqual([a.subcommand for a in actions], ["push"])


if __name__ == "__main__":
    unittest.main()
