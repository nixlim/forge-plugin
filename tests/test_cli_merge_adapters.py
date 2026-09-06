"""Focused dormant candidate, gate, review, and run-binding adapter tests."""

from __future__ import annotations

import copy
import contextlib
import datetime as dt
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from types import ModuleType
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
CLI_PATH = ROOT / "scripts" / "forge" / "cli.py"


from tests._cli_loader import load_script  # cli split phase 0: one shared loader


CLI = load_script("forge_cli_merge_adapter_tests", CLI_PATH)
FIXTURE_SUPPORT = load_script(
    "forge_cli_merge_adapter_fixture_support",
    ROOT / "tests" / "test_cli_chain.py",
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


RANGE_RISK_TIER_HELPER = r"""
import argparse
import json
import subprocess


parser = argparse.ArgumentParser()
parser.add_argument("--repo", required=True)
parser.add_argument("--policy-sha", required=True)
parser.add_argument("--range", dest="revision_range", required=True)
parser.add_argument("--declared-tier", choices=("fast", "standard", "hard"))
args = parser.parse_args()

result = subprocess.run(
    [
        "git",
        "diff",
        "--name-only",
        "-z",
        "--diff-filter=ACDMRTUXB",
        args.revision_range,
        "--",
    ],
    cwd=args.repo,
    check=True,
    capture_output=True,
)
paths = [item.decode("utf-8") for item in result.stdout.split(b"\0") if item]
rank = {"fast": 0, "standard": 1, "hard": 2}
derived = "fast"
records = []
for path in paths:
    control = path.startswith(("scripts/", "rules/", "agents/", "system/"))
    if control:
        tier = "hard"
        categories = ["python"]
    elif path.endswith(".md"):
        tier = "fast"
        categories = ["docs"]
    else:
        tier = "standard"
        categories = ["python"]
    if rank[tier] > rank[derived]:
        derived = tier
    records.append(
        {
            "path": path,
            "categories": categories,
            "control_floor": control,
            "tier": tier,
        }
    )
effective = derived
if args.declared_tier and rank[args.declared_tier] > rank[effective]:
    effective = args.declared_tier
if any(record["control_floor"] for record in records):
    effective = "hard"
print(
    json.dumps(
        {
            "policy_sha": args.policy_sha,
            "derived_tier": derived,
            "effective_tier": effective,
            "paths": records,
        },
        sort_keys=True,
    )
)
"""


class MergeAdapterFixture(FIXTURE_SUPPORT.ForgeCLIFixture):
    chain_id = "c-2026-08-30T150000Z-d001"
    run_id = "run-20260830-merge-adapters"
    task_id = "task-merge-adapters"

    def setUp(self) -> None:
        super().setUp()
        environment = self.environment(FORGE_SESSION_PID=str(os.getpid()))
        environment_patch = mock.patch.dict(os.environ, environment, clear=True)
        environment_patch.start()
        self.addCleanup(environment_patch.stop)
        script_patch = mock.patch.object(CLI, "SCRIPT_DIR", self.helpers)
        script_patch.start()
        self.addCleanup(script_patch.stop)
        plugin_patch = mock.patch.object(CLI, "PLUGIN_ROOT", ROOT)
        plugin_patch.start()
        self.addCleanup(plugin_patch.stop)
        CLI.register_coordination_seams()

        policy = (self.repo / "forge-project.md").read_text(encoding="utf-8")
        policy = policy.replace(
            '| Fixture invariant | `python3 "$FORGE_CLI_SCRIPTS_DIR/gate.py" '
            'invariant:1 "$@"` | commit |',
            '| Fixture invariant | `python3 "$FORGE_CLI_SCRIPTS_DIR/gate.py" '
            'invariant:1 "$@"` | merge |',
        )
        self.assertIn("| merge |", policy)
        (self.repo / "forge-project.md").write_text(policy, encoding="utf-8")
        manifest = "\n".join(
            [
                "forge_version: 1",
                "plugin_ref: forge-merge-adapter-test",
                "installed: 2026-08-30",
                "project_name: merge-adapter-fixture",
                "default_branch: fixture-main",
                "init_completed: true",
                *(f"region: {name}" for name in CLI.REGION_ORDER),
                "",
            ]
        )
        (self.repo / ".forge-manifest").write_text(manifest, encoding="utf-8")
        self.git("add", "forge-project.md", ".forge-manifest")
        self.git("commit", "--quiet", "-m", "configure merge fixture")

        self.origin = self.temp_root / "origin.git"
        result = subprocess.run(
            ["git", "init", "--bare", "--quiet", str(self.origin)],
            cwd=self.temp_root,
            env=self.environment(),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.git("remote", "add", "origin", str(self.origin))
        self.git("push", "--quiet", "--set-upstream", "origin", "fixture-main")
        self.base = self.git("rev-parse", "fixture-main")

        self.worktree = (self.temp_root / "candidate").resolve()
        self.git("branch", "feature")
        self.git("worktree", "add", "--quiet", str(self.worktree), "feature")
        (self.worktree / "src" / "app.py").write_text(
            "VALUE = 2\n", encoding="utf-8"
        )
        self.git_at(self.worktree, "add", "src/app.py")
        self.git_at(
            self.worktree,
            "commit",
            "--quiet",
            "-m",
            "candidate change",
        )
        self.candidate_head = self.git_at(self.worktree, "rev-parse", "HEAD")

        (self.helpers / "risk_tier.py").write_text(
            textwrap.dedent(RANGE_RISK_TIER_HELPER).lstrip(), encoding="utf-8"
        )
        (self.helpers / "run-scoped-mutation.py").write_text(
            "import json\n"
            "print(json.dumps({'result': 'passed', 'scope': 'candidate'}))\n",
            encoding="utf-8",
        )
        (self.helpers / "check-halt.sh").write_text(
            "#!/usr/bin/env bash\n"
            "test \"${1:-}\" = merge || exit 9\n"
            "common_dir=$(git rev-parse --git-common-dir) || exit 8\n"
            "case \"$common_dir\" in /*) ;; *) common_dir=\"$(pwd)/$common_dir\" ;; esac\n"
            "main_root=$(cd \"$(dirname \"$common_dir\")\" && pwd -P) || exit 8\n"
            "test ! -f \"$main_root/AGENT_HALT\" || exit 1\n"
            "test ! -f \"$main_root/AGENT_HALT_merge\" || exit 1\n",
            encoding="utf-8",
        )

    def context(
        self,
        *,
        chain_id: str | None = None,
        run_id: str | None = None,
    ) -> object:
        repository = CLI.Repository(self.repo)
        return CLI.CommandContext(
            repository,
            CLI.MergeChainStore(repository.common_root()),
            CLI.CLIOptions(
                chain_id=chain_id,
                run_id=run_id,
                revision9_face=True,
            ),
        )

    def open_run(self) -> None:
        _batch, builders, _journal = CLI._coordination_modules()
        builders.run_open(
            self.repo,
            self.run_id,
            idempotency_key=digest(b"merge-adapter-run-open"),
            goal="Exercise run-bound merge adapters",
            scope=["src/**"],
            plugin_ref="forge-merge-adapter-test",
        )
        builders.task_start(
            self.repo,
            self.run_id,
            idempotency_key=digest(b"merge-adapter-task-start"),
            task=self.task_id,
            goal="Verify merge gate and review outbox parity",
            acceptance=["Every merge fact is generation-bound"],
            files=["src/app.py"],
        )

    def admission_and_generation(
        self, *, bound: bool = False
    ) -> tuple[object, object]:
        if bound:
            self.open_run()
        context = self.context(run_id=self.run_id if bound else None)
        engine = CLI.MergeEngine(context)
        admission = engine.start(
            str(self.worktree),
            task=self.task_id if bound else None,
        )
        generation = engine.bind_candidate(admission, self.base)
        return admission, generation

    def create_chain(
        self,
        admission: object,
        generation: object,
        *,
        bound: bool = False,
    ) -> tuple[object, dict[str, object]]:
        chain_id = self.chain_id
        created = CLI.utc_now() - dt.timedelta(seconds=5)
        at = CLI.iso_z(created)
        owner = {
            "pid": os.getpid(),
            "host": "merge-adapter-test",
            "session": "merge-adapter-session",
            "started_at": at,
        }
        worktree_identity = copy.deepcopy(admission.worktree_identity)
        worktree_digest = digest(CLI.canonical_bytes(worktree_identity))
        claim_path = str(
            Path(worktree_identity["common_dir"]).parent
            / ".forge"
            / "chains"
            / "owners"
            / f"{worktree_digest}.claim"
        )
        claim_record = {
            "chain_id": chain_id,
            "host": owner["host"],
            "pid": owner["pid"],
            "session": owner["session"],
            "started_at": owner["started_at"],
            "worktree_digest": worktree_digest,
        }
        claim_digest = digest(CLI.canonical_bytes(claim_record))
        run_binding = (
            copy.deepcopy(admission.run_task.binding)
            if bound and admission.run_task is not None
            else None
        )
        initial = {
            "schema": "forge-merge-chain/1",
            "chain_id": chain_id,
            "kind": "merge",
            "state": "classifying",
            "created_at": at,
            "owner": owner,
            "run": self.run_id if bound else None,
            "repository": str(self.repo.resolve()),
            "worktree": {
                **worktree_identity,
                "claim": {
                    "status": "unpublished",
                    "path": claim_path,
                    "inode": None,
                    "digest": None,
                },
            },
            "branch": admission.branch,
            "target": copy.deepcopy(admission.target),
            "policy_source": {
                "commit": admission.candidate_head,
                "digest": admission.policy.digest,
            },
            "candidate": None,
            "tier": None,
            "steps": {},
            "review": {},
            "approval": {},
            "authorization": {},
            "integration": {
                "condition": "none",
                "primary_condition": "none",
                "epoch": None,
                "remote_movement_count": 0,
                "intent": None,
                "observed": None,
                "pre_rebase": None,
                "conflict": None,
                "push": None,
            },
            "cleanup": {"condition": "none"},
            "run_binding": run_binding,
        }
        store = self.context().store
        state = store.create(initial, at=at, session="merge-adapter-session")
        state = store.transition(
            state,
            "ownership_intent",
            {
                "worktree_digest": worktree_digest,
                "claim_path": claim_path,
                "intended_claim_digest": claim_digest,
                "predecessor_chain_id": None,
                "predecessor_release_digest": None,
            },
            generation_digest=None,
            at=CLI.iso_z(created + dt.timedelta(seconds=1)),
            session="merge-adapter-session",
        )
        intent_digest = json.loads(
            store.events_path(chain_id).read_text(encoding="utf-8").splitlines()[-1]
        )["digest"]
        state = store.transition(
            state,
            "ownership_claimed",
            {
                "ownership_intent_digest": intent_digest,
                "claim_inode": 1,
                "claim_digest": claim_digest,
                "predecessor_chain_id": None,
                "predecessor_release_digest": None,
            },
            generation_digest=None,
            at=CLI.iso_z(created + dt.timedelta(seconds=2)),
            session="merge-adapter-session",
        )
        operation_nonce = digest(b"merge-adapter-bootstrap")[:32]
        state = store.transition(
            state,
            "fetch_intent",
            {
                "repository": str(self.repo.resolve()),
                "worktree": worktree_identity,
                "branch": admission.branch,
                "target": copy.deepcopy(admission.target),
                "pre_fetch_head": admission.candidate_head,
                "policy_digest": admission.policy.digest,
                "operation_nonce": operation_nonce,
                "attempt": 1,
            },
            generation_digest=None,
            at=CLI.iso_z(created + dt.timedelta(seconds=3)),
            session="merge-adapter-session",
        )
        integration = copy.deepcopy(initial["integration"])
        integration["intent"] = {
            "operation": "fetch-result",
            "operation_nonce": operation_nonce,
            "attempt": 1,
            "result": "success",
            "resolved_tip": self.base,
        }
        state = store.transition(
            state,
            "fetch_result",
            {
                "delta": {
                    "candidate": copy.deepcopy(generation.candidate),
                    "tier": copy.deepcopy(generation.tier),
                    "state": "verifying",
                    "integration": integration,
                }
            },
            generation_digest=generation.candidate["generation_digest"],
            at=CLI.iso_z(created + dt.timedelta(seconds=4)),
            session="merge-adapter-session",
        )
        return store, state

    @staticmethod
    def passing_process(argv, **_kwargs):
        output = ("pass " + " ".join(str(value) for value in argv) + "\n").encode()
        return CLI.ProcessResult(
            argv=list(argv),
            returncode=0,
            duration_seconds=0.01,
            output=output,
            output_digest=digest(output),
        )

    def verify_chain(self, *, bound: bool = False):
        admission, generation = self.admission_and_generation(bound=bound)
        store, _state = self.create_chain(admission, generation, bound=bound)
        context = self.context(chain_id=self.chain_id)
        engine = CLI.MergeEngine(context)
        calls: list[tuple[list[str], dict[str, object]]] = []

        def passing(argv, **kwargs):
            calls.append((list(argv), dict(kwargs)))
            return self.passing_process(argv, **kwargs)

        with mock.patch.object(CLI, "run_bounded", side_effect=passing):
            outcome = engine.verify()
        return admission, generation, store, engine, outcome, calls


class MergeAdmissionAdapterTests(MergeAdapterFixture):
    def test_merge_start_routing_remains_dormant(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(
            CLI.Refusal
        ) as caught:
            CLI.build_parser().parse_args(
                ["merge", "start", "--worktree", str(self.worktree)]
            )
        self.assertEqual(
            caught.exception.message.split(":", 1)[0], "invalid CLI invocation"
        )

    def test_bound_admission_generation_and_scope_are_exactly_fixed(self) -> None:
        self.open_run()
        engine = CLI.MergeEngine(self.context(run_id=self.run_id))
        admission = engine.start(str(self.worktree), task=self.task_id)
        with mock.patch.object(
            CLI, "run_bounded", wraps=CLI.run_bounded
        ) as bounded:
            generation = engine.bind_candidate(admission, self.base)
        launched = [list(call.args[0]) for call in bounded.call_args_list]
        self.assertEqual(
            launched[0],
            CLI._merge_scope_argv(self.worktree, self.base, self.candidate_head),
        )
        self.assertEqual(Path(launched[1][1]).name, "risk_tier.py")
        self.assertEqual(admission.repository, self.repo.resolve())
        self.assertEqual(admission.worktree, self.worktree)
        self.assertEqual(admission.branch, "refs/heads/feature")
        self.assertEqual(
            admission.target,
            {
                "remote": "origin",
                "destination_ref": "refs/heads/fixture-main",
                "manifest_commit": self.base,
            },
        )
        self.assertEqual(admission.candidate_head, self.candidate_head)
        self.assertRegex(admission.candidate_head, r"^[0-9a-f]{40}$")
        self.assertEqual(
            admission.run_task.binding,
            {
                "run_id": self.run_id,
                "task_id": self.task_id,
                "repository": str(self.repo.resolve()),
                "policy_digest": admission.policy.digest,
            },
        )
        self.assertEqual(admission.run_task.task_files, ("src/app.py",))
        self.assertEqual(admission.run_task.admitted_scope, ("src/**",))

        candidate = generation.candidate
        self.assertEqual(
            set(candidate),
            {
                "remote",
                "destination_ref",
                "remote_tip",
                "candidate_head",
                "diff_sha256",
                "policy_commit",
                "policy_digest",
                "worktree_identity",
                "generation",
                "generation_digest",
            },
        )
        self.assertEqual(candidate["remote_tip"], self.base)
        self.assertEqual(candidate["candidate_head"], self.candidate_head)
        preimage = {name: value for name, value in candidate.items() if name != "generation_digest"}
        self.assertEqual(
            candidate["generation_digest"], digest(CLI.canonical_bytes(preimage))
        )
        self.assertEqual(generation.changed_paths, ("src/app.py",))
        self.assertIsNotNone(generation.scope)
        self.assertEqual(generation.scope.result, "contained")
        self.assertEqual(generation.scope.out_of_scope_paths, ())
        self.assertEqual(
            generation.scope.argv,
            tuple(CLI._merge_scope_argv(self.worktree, self.base, self.candidate_head)),
        )

    def test_target_comes_only_from_main_committed_manifest(self) -> None:
        candidate_manifest = (self.worktree / ".forge-manifest").read_text(
            encoding="utf-8"
        )
        candidate_manifest = candidate_manifest.replace(
            "default_branch: fixture-main", "default_branch: attacker-target"
        )
        (self.worktree / ".forge-manifest").write_text(
            candidate_manifest, encoding="utf-8"
        )
        self.git_at(self.worktree, "add", ".forge-manifest")
        self.git_at(
            self.worktree,
            "commit",
            "--quiet",
            "-m",
            "candidate manifest must not retarget",
        )
        admission = CLI.MergeEngine(self.context()).start(str(self.worktree))
        self.assertEqual(
            admission.target["destination_ref"], "refs/heads/fixture-main"
        )
        self.assertEqual(admission.target["manifest_commit"], self.base)

    def test_exact_admission_refusals_change_no_history(self) -> None:
        main_before = self.git("rev-parse", "HEAD")
        origin_before = self.git_at(self.origin, "rev-parse", "refs/heads/fixture-main")
        engine = CLI.MergeEngine(self.context())
        cases = (
            (
                self.temp_root / "missing",
                CLI.V2ReasonCode.WORKTREE_MISSING,
                "forge: merge start refused — worktree path does not exist",
            ),
            (
                self.repo,
                CLI.V2ReasonCode.WORKTREE_INVALID,
                "forge: merge start refused — source is not one registered non-main worktree",
            ),
        )
        for path, reason, message in cases:
            with self.subTest(path=path), self.assertRaises(CLI.Refusal) as caught:
                engine.start(str(path))
            self.assertEqual(caught.exception.reason_code, reason)
            self.assertEqual(caught.exception.message, message)

        link = self.temp_root / "candidate-link"
        link.symlink_to(self.worktree, target_is_directory=True)
        with self.assertRaises(CLI.Refusal) as caught:
            engine.start(str(link))
        self.assertEqual(caught.exception.reason_code, CLI.V2ReasonCode.WORKTREE_INVALID)
        self.assertEqual(
            caught.exception.message,
            "forge: merge start refused — worktree path has an ambiguous symlink spelling",
        )
        self.assertEqual(self.git("rev-parse", "HEAD"), main_before)
        self.assertEqual(
            self.git_at(self.origin, "rev-parse", "refs/heads/fixture-main"),
            origin_before,
        )

    def test_dirty_worktree_and_invalid_committed_manifest_fail_closed(self) -> None:
        dirty = self.worktree / "untracked.txt"
        dirty.write_text("dirty\n", encoding="utf-8")
        with self.assertRaises(CLI.Refusal) as caught:
            CLI.MergeEngine(self.context()).start(str(self.worktree))
        self.assertEqual(caught.exception.reason_code, CLI.V2ReasonCode.DIRTY_WORKTREE)
        self.assertEqual(
            caught.exception.message,
            "forge: merge start refused — source worktree is not clean",
        )
        dirty.unlink()

        (self.repo / ".forge-manifest").write_text(
            "default_branch: attacker\n", encoding="utf-8"
        )
        self.git("add", ".forge-manifest")
        self.git("commit", "--quiet", "-m", "corrupt committed manifest")
        with self.assertRaises(CLI.Refusal) as caught:
            CLI.MergeEngine(self.context()).start(str(self.worktree))
        self.assertEqual(caught.exception.reason_code, CLI.V2ReasonCode.PUSH_TARGET_INVALID)
        self.assertEqual(
            caught.exception.message,
            "forge: merge start refused — committed target manifest is invalid",
        )

    def test_merge_halt_scope_refuses_before_admission(self) -> None:
        sentinel = self.repo / "AGENT_HALT_merge"
        sentinel.write_text("operator pause\n", encoding="utf-8")
        before = self.git("rev-parse", "HEAD")
        with self.assertRaises(CLI.Refusal) as caught:
            CLI.MergeEngine(self.context()).start(str(self.worktree))
        self.assertEqual(caught.exception.reason_code, CLI.V2ReasonCode.HALT_ENGAGED)
        self.assertEqual(
            caught.exception.message,
            "operator halt check refused state mutation",
        )
        self.assertEqual(self.git("rev-parse", "HEAD"), before)

    def test_run_task_flags_are_paired_and_later_flags_are_rejected(self) -> None:
        with self.assertRaises(CLI.Refusal) as caught:
            CLI.MergeEngine(self.context(run_id=self.run_id)).start(str(self.worktree))
        self.assertEqual(
            caught.exception.reason_code,
            CLI.V2ReasonCode.RUN_TASK_BINDING_REQUIRED,
        )
        self.assertEqual(
            caught.exception.message,
            "forge: merge start refused — --run-id and --task must be supplied together",
        )

        with self.assertRaises(CLI.Refusal) as caught:
            CLI.MergeEngine(
                self.context(chain_id=self.chain_id, run_id=self.run_id)
            ).status()
        self.assertEqual(
            caught.exception.reason_code,
            CLI.V2ReasonCode.RUN_TASK_BINDING_INVALID,
        )
        self.assertEqual(
            caught.exception.message,
            "forge: merge transition refused — later verbs inherit the immutable run/task binding",
        )

    def test_generation_rejects_unavailable_base_and_incomplete_classifier_rows(self) -> None:
        engine = CLI.MergeEngine(self.context())
        admission = engine.start(str(self.worktree))
        with self.assertRaises(CLI.Refusal) as caught:
            engine.bind_candidate(admission, "f" * 40)
        self.assertEqual(caught.exception.reason_code, CLI.V2ReasonCode.FETCH_FAILED)
        self.assertEqual(
            caught.exception.message,
            "forge: merge start refused — fetched target tip is invalid",
        )

        malformed = json.dumps(
            {
                "policy_sha": self.candidate_head,
                "derived_tier": "standard",
                "effective_tier": "standard",
                "paths": [],
            }
        ).encode()
        process = CLI.ProcessResult(
            argv=[],
            returncode=0,
            duration_seconds=0.0,
            output=malformed,
            output_digest=digest(malformed),
        )
        with mock.patch.object(CLI, "run_bounded", return_value=process):
            with self.assertRaises(CLI.Refusal) as caught:
                engine.bind_candidate(admission, self.base)
        self.assertEqual(
            caught.exception.reason_code, CLI.V2ReasonCode.EVIDENCE_INCOMPLETE
        )
        self.assertEqual(
            caught.exception.message,
            "forge: merge start refused — risk-tier evidence is not candidate-bound",
        )

    def test_unavailable_bound_scope_child_uses_existing_binding_refusal(self) -> None:
        self.open_run()
        engine = CLI.MergeEngine(self.context(run_id=self.run_id))
        admission = engine.start(str(self.worktree), task=self.task_id)
        with mock.patch.object(
            CLI, "run_bounded", side_effect=OSError("scope executable missing")
        ):
            with self.assertRaises(CLI.Refusal) as caught:
                engine.bind_candidate(admission, self.base)
        self.assertEqual(
            caught.exception.reason_code,
            CLI.V2ReasonCode.RUN_TASK_BINDING_INVALID,
        )
        self.assertEqual(
            caught.exception.message,
            "forge: merge start refused — run/task scope derivation is invalid",
        )

    def test_scope_argv_parser_and_environment_contract_are_closed(self) -> None:
        expected = [
            "git",
            "--no-pager",
            "--no-replace-objects",
            "-c",
            "core.quotePath=false",
            "-c",
            "color.ui=false",
            "-c",
            "diff.renames=copies",
            "-c",
            "diff.renameLimit=0",
            "-c",
            "diff.algorithm=myers",
            "-C",
            str(self.worktree),
            "diff",
            "--no-color",
            "-O/dev/null",
            "--name-status",
            "-z",
            "--find-renames=50%",
            "--find-copies=50%",
            "--find-copies-harder",
            "-l0",
            "--no-ext-diff",
            "--no-textconv",
            "--ignore-submodules=none",
            "--diff-filter=ACDMRTUXB",
            f"{self.base}...{self.candidate_head}",
            "--",
        ]
        self.assertEqual(
            CLI._merge_scope_argv(self.worktree, self.base, self.candidate_head),
            expected,
        )
        with mock.patch.dict(
            os.environ,
            {
                "PATH": os.defpath,
                "GIT_DIR": "/attacker",
                "GIT_CONFIG_COUNT": "2",
                "UNRELATED": "retained",
            },
            clear=True,
        ):
            environment = CLI._merge_scope_environment()
        self.assertNotIn("GIT_DIR", environment)
        self.assertNotIn("GIT_CONFIG_COUNT", environment)
        self.assertEqual(environment["UNRELATED"], "retained")
        for name, value in CLI._MERGE_SCOPE_OVERLAY.items():
            self.assertEqual(environment[name], value)
        self.assertEqual(
            CLI._parse_merge_scope_output(b"R100\0old.py\0new.py\0M\0src/app.py\0"),
            ("new.py", "old.py", "src/app.py"),
        )
        for malformed in (b"M\0src/app.py", b"R101\0old.py\0new.py\0", b"M\0"):
            with self.subTest(malformed=malformed), self.assertRaises(ValueError):
                CLI._parse_merge_scope_output(malformed)

    def test_each_new_adapter_control_is_load_bearing(self) -> None:
        admission = CLI.MergeEngine(self.context()).start(str(self.worktree))
        calls = {
            "admission-and-generation": lambda: CLI.MergeEngine(self.context()).start(
                str(self.worktree)
            ),
            "halt": lambda: CLI.MergeEngine(self.context()).start(
                str(self.worktree)
            ),
            "ordered-gate-suite": lambda: CLI._merge_gate_suite({}, admission.policy),
            "mandatory-review-final": lambda: CLI.MergeEngine(
                self.context(chain_id=self.chain_id)
            ).review_request(),
            "run-relative-evidence": lambda: CLI._capture_run_evidence(
                self.repo,
                self.repo / ".codex-orchestrator" / "runs" / self.run_id,
                b"evidence\n",
            ),
        }
        for control, call in calls.items():
            with self.subTest(control=control), mock.patch.object(
                CLI,
                "MERGE_ADAPTER_CONTROLS",
                CLI.MERGE_ADAPTER_CONTROLS - {control},
            ), self.assertRaisesRegex(
                CLI.FrozenError,
                f"merge adapter control is unavailable: {control}",
            ):
                call()


class MergeGateAdapterTests(MergeAdapterFixture):
    def test_historical_chain_evidence_is_recaptured_run_relative(self) -> None:
        self.open_run()
        run_dir = self.repo / ".codex-orchestrator" / "runs" / self.run_id
        evidence = (
            self.repo
            / ".forge"
            / "chains"
            / self.chain_id
            / "evidence"
            / "gate.log"
        )
        evidence.parent.mkdir(parents=True)
        evidence_bytes = b"historical gate evidence\n"
        evidence.write_bytes(evidence_bytes)
        record: dict[str, object] = {
            "evidence": [evidence.relative_to(self.repo).as_posix()]
        }
        CLI._capture_ingest_record_evidence(self.repo, run_dir, record)
        citations = record["evidence"]
        self.assertEqual(len(citations), 1)
        self.assertTrue(citations[0].startswith("captured/sha256/"))
        self.assertNotIn(".forge/chains/", citations[0])
        self.assertEqual((run_dir / citations[0]).read_bytes(), evidence_bytes)

    def test_verify_runs_normative_order_with_bounded_existing_runner(self) -> None:
        _admission, generation, store, _engine, outcome, calls = self.verify_chain()
        self.assertTrue(outcome.ok)
        state = store.load(self.chain_id)
        self.assertEqual(state["state"], "reviewing")
        events = [
            json.loads(line)
            for line in store.events_path(self.chain_id)
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        gate_order = []
        prior_steps: dict[str, object] = {}
        for event in events:
            if event["event"] != "gate_recorded":
                continue
            current_steps = event["payload"]["delta"]["steps"]
            changed = [
                name
                for name in set(prior_steps) | set(current_steps)
                if prior_steps.get(name) != current_steps.get(name)
            ]
            self.assertEqual(len(changed), 1)
            gate_order.append(changed[0])
            prior_steps = current_steps
        self.assertEqual(
            gate_order,
            ["gate-1", "stack:python", "invariant:1", "assertion-sensor"],
        )
        self.assertEqual(
            [
                "scoped-mutation"
                if Path(call[0][1]).name == "run-scoped-mutation.py"
                else call[0][2]
                if call[0][:2] == ["bash", "-c"]
                else Path(call[0][1]).name
                for call in calls
                if Path(call[0][1]).name != "check-halt.sh"
            ],
            [
                state["steps"]["gate-1"][-1]["command_argv"][2],
                "scoped-mutation",
                state["steps"]["stack:python"][-1]["command_argv"][2],
                state["steps"]["invariant:1"][-1]["command_argv"][2],
            ],
        )
        for argv, kwargs in calls:
            if Path(argv[1]).name == "check-halt.sh":
                self.assertEqual(argv[2], "merge")
                self.assertEqual(kwargs["timeout"], 30.0)
                continue
            self.assertEqual(kwargs["timeout"], 1200.0)
            self.assertEqual(kwargs["cap"], 65536)
            if argv[0] == "bash":
                self.assertEqual(argv[:2], ["bash", "-c"])
                self.assertEqual(argv[3], "forge")
        facts = [fact[-1] for fact in state["steps"].values()]
        self.assertTrue(
            all(
                fact["generation_digest"]
                == generation.candidate["generation_digest"]
                for fact in facts
            )
        )
        self.assertEqual(
            state["steps"]["gate-1"][-1]["scoped_mutation"]["result"],
            "passed",
        )
        self.assertEqual(
            self.git_at(self.origin, "rev-parse", "refs/heads/fixture-main"),
            self.base,
        )

    def test_failed_gate_is_durable_remote_safe_and_resumable(self) -> None:
        admission, generation = self.admission_and_generation()
        store, _state = self.create_chain(admission, generation)
        engine = CLI.MergeEngine(self.context(chain_id=self.chain_id))
        def unavailable_gate(argv, **kwargs):
            if Path(argv[1]).name == "check-halt.sh":
                return self.passing_process(argv, **kwargs)
            raise OSError("fixture gate missing")

        with mock.patch.object(CLI, "run_bounded", side_effect=unavailable_gate):
            with self.assertRaises(CLI.Refusal) as caught:
                engine.verify()
        self.assertEqual(caught.exception.reason_code, CLI.V2ReasonCode.MERGE_GATE_FAILED)
        self.assertEqual(
            caught.exception.message, "forge: merge gate failed — gate-1"
        )
        state = store.load(self.chain_id)
        self.assertEqual(state["state"], "verifying")
        self.assertEqual(state["steps"]["gate-1"][-1]["result"], "failed")
        self.assertEqual(
            self.git_at(self.origin, "rev-parse", "refs/heads/fixture-main"),
            self.base,
        )
        with mock.patch.object(
            CLI, "run_bounded", side_effect=self.passing_process
        ):
            outcome = engine.verify()
        self.assertTrue(outcome.ok)
        state = store.load(self.chain_id)
        self.assertEqual(
            [fact["result"] for fact in state["steps"]["gate-1"]],
            ["failed", "passed"],
        )
        self.assertEqual(state["state"], "reviewing")

    def test_run_bound_gate_review_and_replay_use_receipted_run_relative_facts(self) -> None:
        _admission, _generation, store, engine, _outcome, _calls = self.verify_chain(
            bound=True
        )
        engine.review_request()
        request = store.load(self.chain_id)["review"]["request"]
        verdict = self.write_verdict("merge-pass.txt", "PASS", request)
        engine.review_attach(str(verdict))
        attached = store.load(self.chain_id)
        self.assertEqual(attached["state"], "authorized")

        _batch, builders, journal = CLI._coordination_modules()
        run_dir = self.repo / ".codex-orchestrator" / "runs" / self.run_id
        run_state = journal._scan_run(run_dir)
        verification = [
            record
            for record in run_state.records
            if record.get("type") == "verification"
            and record.get("task") == self.task_id
        ]
        self.assertEqual(len(verification), 5)
        self.assertEqual(
            {record["binding"]["schema"] for record in verification},
            {"forge-gate-binding/1"},
        )
        prefix = "captured/sha256/"
        citations = [
            citation
            for record in verification
            for citation in record.get("evidence", [])
        ]
        self.assertTrue(citations)
        self.assertTrue(
            all(citation.startswith(prefix) for citation in citations), citations
        )
        self.assertTrue(all((run_dir / citation).is_file() for citation in citations))
        self.assertTrue(
            any(record["criterion"] == journal.GATE_3_CRITERION for record in verification)
        )

        with mock.patch.object(
            builders,
            "_binding_is_current",
            side_effect=AssertionError("historical receipt was rechecked"),
        ):
            replayed = store.load(self.chain_id)
        self.assertEqual(replayed, attached)

    def test_run_bound_block_records_failed_gate_three_fact(self) -> None:
        _admission, _generation, _store, engine, _outcome, _calls = self.verify_chain(
            bound=True
        )
        engine.review_request()
        state = engine.store.load(self.chain_id)
        request = state["review"]["request"]
        verdict = self.write_verdict(
            "merge-bound-block.txt",
            "BLOCK",
            request,
            ("MAJOR", "fixture block"),
        )
        engine.review_attach(str(verdict))
        _batch, _builders, journal = CLI._coordination_modules()
        run_dir = self.repo / ".codex-orchestrator" / "runs" / self.run_id
        gate_three = [
            record
            for record in journal._scan_run(run_dir).records
            if record.get("type") == "verification"
            and record.get("criterion") == journal.GATE_3_CRITERION
        ]
        self.assertEqual(len(gate_three), 1)
        self.assertEqual(gate_three[0]["result"], "failed")
        self.assertEqual(gate_three[0]["binding"]["schema"], "forge-gate-binding/1")


class MergeReviewAdapterTests(MergeAdapterFixture):
    def test_review_is_mandatory_single_master_and_collect_cannot_skip(self) -> None:
        _admission, generation, store, engine, _outcome, _calls = self.verify_chain()
        before = store.events_path(self.chain_id).read_bytes()
        with self.assertRaises(CLI.Refusal) as caught:
            engine.review_collect()
        self.assertEqual(caught.exception.reason_code, CLI.V2ReasonCode.SKIP_NOT_PERMITTED)
        self.assertEqual(
            caught.exception.message,
            "forge: review collect refused — merge review-final cannot be skipped or replaced",
        )
        self.assertEqual(store.events_path(self.chain_id).read_bytes(), before)

        engine.review_request()
        requested = store.load(self.chain_id)
        request = requested["review"]["request"]
        self.assertEqual(request["reviewer"], "review-final")
        self.assertEqual(request["candidate"], self.candidate_head)
        self.assertEqual(
            request["generation_digest"], generation.candidate["generation_digest"]
        )
        package = self.repo / request["package"]
        package_bytes = package.read_bytes()
        self.assertEqual(digest(package_bytes), request["package_digest"])
        self.assertEqual(request["byte_length"], len(package_bytes))
        self.assertIn(b"FORGE MERGE REVIEW MASTER PACKAGE v1", package_bytes)
        self.assertIn(
            f"target: {CLI.canonical_bytes(requested['target']).decode()}".encode(),
            package_bytes,
        )
        self.assertIn(b"--- BEGIN UNTRUSTED CANDIDATE DIFF ---", package_bytes)

    def test_oversized_master_package_uses_exact_fail_closed_literal(self) -> None:
        _admission, _generation, store, engine, _outcome, _calls = self.verify_chain()
        before_events = store.events_path(self.chain_id).read_bytes()
        oversized = b"x" * (CLI.OUTPUT_CAP_BYTES + 1)
        with mock.patch.object(
            engine,
            "_review_package",
            return_value=(oversized, [], {}),
        ):
            with self.assertRaises(CLI.Refusal) as caught:
                engine.review_request()
        self.assertEqual(caught.exception.reason_code, CLI.V2ReasonCode.EVIDENCE_INCOMPLETE)
        self.assertEqual(
            caught.exception.message,
            "forge: review refused — reviewer cannot inspect the complete authoritative package",
        )
        self.assertEqual(store.events_path(self.chain_id).read_bytes(), before_events)
        self.assertEqual(store.load(self.chain_id)["review"], {})
        self.assertEqual(len(caught.exception.evidence_refs), 1)

    def test_disposition_slot_allows_minor_then_exactly_one_above_minor(self) -> None:
        starter = CLI.MergeEngine(self.context())
        started = starter.start_chain(str(self.worktree), remote_tip=self.base)
        self.chain_id = str(started.chain_id)
        store = starter.store
        engine = CLI.MergeEngine(self.context(chain_id=self.chain_id))
        with mock.patch.object(CLI, "run_bounded", side_effect=self.passing_process):
            verified = engine.verify()
        self.assertEqual(verified.state, "reviewing")
        admitted_history = [
            json.loads(line)
            for line in store.events_path(self.chain_id).read_bytes().splitlines()
        ]
        self.assertTrue(CLI._merge_history_uses_additive_grammar(admitted_history))
        engine.review_request()
        request = store.load(self.chain_id)["review"]["request"]
        verdict = self.write_verdict(
            "merge-block.txt",
            "BLOCK",
            request,
            ("MINOR", "minor finding"),
            ("MAJOR", "major finding"),
            ("CRITICAL", "critical finding"),
            ("MAJOR", "second major finding"),
        )
        engine.review_attach(str(verdict))
        self.assertEqual(store.load(self.chain_id)["state"], "revising")

        engine.review_disposition(1, "MINOR", "accept minor risk")
        self.assertFalse(
            store.load(self.chain_id)["review"]["operator_cosign_required"]
        )
        with self.assertRaises(CLI.Refusal) as parked:
            engine.review_disposition(2, "MAJOR", "repair in follow-up")
        self.assertEqual(parked.exception.reason_code, CLI.V2ReasonCode.APPROVAL_REQUIRED)
        self.assertTrue(parked.exception.chain["review"]["operator_cosign_required"])

        before_minor_events = store.events_path(self.chain_id).read_bytes()
        artifact_root = store.artifact_dir(self.chain_id)
        before_artifacts = {
            path.relative_to(artifact_root).as_posix(): digest(path.read_bytes())
            for path in artifact_root.rglob("*")
            if path.is_file()
        }
        minor = engine.review_disposition(
            1, "MINOR", "must not clear pending slot"
        )
        after_minor = store.load(self.chain_id)
        self.assertTrue(minor.ok)
        self.assertTrue(after_minor["review"]["operator_cosign_required"])
        self.assertEqual(len(after_minor["review"]["dispositions"]), 3)
        self.assertEqual(
            after_minor["review"]["dispositions"][-1]["resolution"],
            "must not clear pending slot",
        )
        appended = store.events_path(self.chain_id).read_bytes()[
            len(before_minor_events) :
        ].splitlines()
        self.assertEqual(len(appended), 1)
        self.assertEqual(json.loads(appended[0])["event"], "review_disposition")

        admitted_events = [
            json.loads(line)
            for line in store.events_path(self.chain_id).read_bytes().splitlines()
        ]
        admitted_replay = CLI._replay_merge_event_bytes(
            self.chain_id,
            store.events_path(self.chain_id).read_bytes(),
        )
        admitted_tail = admitted_events[-1]
        self.assertEqual(admitted_tail["event"], "review_disposition")
        self.assertTrue(
            admitted_replay.entries[-1][1]["review"][
                "operator_cosign_required"
            ]
        )
        self.assertEqual(
            admitted_tail["payload"]["delta"]["review"][
                "operator_cosign_required"
            ],
            True,
        )
        for finding, severity in ((4, "MAJOR"), (3, "CRITICAL")):
            with self.subTest(replay_severity=severity):
                hostile_events = copy.deepcopy(admitted_events)
                hostile = hostile_events[-1]
                hostile_disposition = hostile["payload"]["delta"]["review"][
                    "dispositions"
                ][-1]
                hostile_disposition.update(
                    {
                        "finding": finding,
                        "severity": severity,
                        "resolution": "digest-valid second occupied-slot disposition",
                    }
                )
                unsigned = {
                    name: value
                    for name, value in hostile.items()
                    if name != "digest"
                }
                hostile["digest"] = digest(CLI.canonical_bytes(unsigned))
                self.assertEqual(
                    hostile["digest"],
                    digest(
                        CLI.canonical_bytes(
                            {
                                name: value
                                for name, value in hostile.items()
                                if name != "digest"
                            }
                        )
                    ),
                )
                hostile_bytes = b"".join(
                    CLI.canonical_bytes(event) + b"\n"
                    for event in hostile_events
                )
                with self.assertRaisesRegex(
                    CLI.FrozenError,
                    rf"merge event {hostile['sequence']} transition is invalid",
                ):
                    CLI._replay_merge_event_bytes(self.chain_id, hostile_bytes)

        before_events = store.events_path(self.chain_id).read_bytes()
        before_state = store.state_path(self.chain_id).read_bytes()
        with self.assertRaises(CLI.Refusal) as caught:
            engine.review_disposition(3, "CRITICAL", "replace pending slot")
        self.assertEqual(
            caught.exception.reason_code, CLI.V2ReasonCode.STATE_PRECONDITION
        )
        self.assertEqual(
            caught.exception.message,
            "forge: review disposition refused — above-MINOR disposition already awaits operator co-sign",
        )
        self.assertEqual(store.events_path(self.chain_id).read_bytes(), before_events)
        self.assertEqual(store.state_path(self.chain_id).read_bytes(), before_state)
        self.assertEqual(
            {
                path.relative_to(artifact_root).as_posix(): digest(path.read_bytes())
                for path in artifact_root.rglob("*")
                if path.is_file()
            },
            before_artifacts,
        )


if __name__ == "__main__":
    import unittest

    unittest.main()
