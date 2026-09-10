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
import runpy
import subprocess
import sys
import textwrap
from pathlib import Path
from types import ModuleType
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
CLI_PATH = ROOT / "scripts" / "forge" / "cli.py"


from tests._cli_loader import load_script, package_module  # cli split phase 0: one shared loader


CLI = load_script("forge_cli_merge_adapter_tests", CLI_PATH)
CORE = package_module("chain_core")  # cli split phase 2b: canonical chain-core module
RUNTIME = package_module("runtime")  # cli split phase 2a: canonical patch seam for runtime controls
ENGINE = package_module("engine")  # revision 10: canonical review-transport controls
APP = package_module("app")
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
        script_patch = mock.patch.object(RUNTIME, "SCRIPT_DIR", self.helpers)
        script_patch.start()
        self.addCleanup(script_patch.stop)
        plugin_patch = mock.patch.object(RUNTIME, "PLUGIN_ROOT", ROOT)
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

        with mock.patch.object(RUNTIME, "run_bounded", side_effect=passing):
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
            RUNTIME, "run_bounded", wraps=CLI.run_bounded
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
        with mock.patch.object(RUNTIME, "run_bounded", return_value=process):
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
            RUNTIME, "run_bounded", side_effect=OSError("scope executable missing")
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
                CORE,
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

    def test_bound_mutation_runner_receives_owner_and_exact_run_binding(self) -> None:
        _admission, _generation, _store, _engine, outcome, calls = self.verify_chain(
            bound=True
        )

        self.assertTrue(outcome.ok)
        scoped = [
            (argv, kwargs)
            for argv, kwargs in calls
            if len(argv) > 1 and Path(argv[1]).name == "run-scoped-mutation.py"
        ]
        self.assertEqual(len(scoped), 1)
        argv, kwargs = scoped[0]
        self.assertEqual(
            argv[-6:],
            [
                "--repository",
                str(self.repo.resolve()),
                "--run-id",
                self.run_id,
                "--task",
                self.task_id,
            ],
        )
        self.assertNotIn("--journal", argv)
        self.assertNotIn("--defer-journal", argv)
        self.assertEqual(kwargs["env"]["FORGE_SESSION_PID"], str(os.getpid()))
        ordinary_children = [
            kwargs["env"]
            for child_argv, kwargs in calls
            if kwargs.get("env") is not None
            and not (
                len(child_argv) > 1
                and Path(child_argv[1]).name == "run-scoped-mutation.py"
            )
        ]
        self.assertTrue(ordinary_children)
        self.assertTrue(
            all("FORGE_SESSION_PID" not in environment for environment in ordinary_children)
        )

    def test_unbound_mutation_runner_does_not_receive_owner_or_run_identity(self) -> None:
        _admission, _generation, _store, _engine, outcome, calls = self.verify_chain()

        self.assertTrue(outcome.ok)
        scoped = [
            (argv, kwargs)
            for argv, kwargs in calls
            if len(argv) > 1 and Path(argv[1]).name == "run-scoped-mutation.py"
        ]
        self.assertEqual(len(scoped), 1)
        argv, kwargs = scoped[0]
        self.assertNotIn("--repository", argv)
        self.assertNotIn("--run-id", argv)
        self.assertNotIn("--task", argv)
        self.assertNotIn("FORGE_SESSION_PID", kwargs["env"])

    def test_bound_epoch_mutation_retains_owner_and_wires_deferred_transform(self) -> None:
        engine = CLI.MergeEngine(self.context(chain_id=self.chain_id))
        suite = [{"kind": "scoped-mutation", "id": "scoped-mutation"}]
        plan = {
            "status": "sealed",
            "cursor": 0,
            "suite": suite,
            "suite_digest": digest(CORE.canonical_bytes(suite)),
            "seal_event_digest": "1" * 64,
            "generation_digest": "2" * 64,
            "policy_digest": "3" * 64,
        }
        state = {
            "chain_id": self.chain_id,
            "candidate": {
                "remote_tip": self.base,
                "candidate_head": self.candidate_head,
                "generation_digest": "2" * 64,
            },
            "integration": {
                "epoch": {
                    "intent_digest": "4" * 64,
                    "operation_nonce": "5" * 32,
                    "gate_plan": plan,
                }
            },
            "run_binding": {
                "run_id": self.run_id,
                "task_id": self.task_id,
            },
        }
        repository = CLI.Repository(self.repo)
        budget = mock.Mock()
        captured: dict[str, object] = {}

        class EpochInvocation(RuntimeError):
            pass

        def capture(_lock, **kwargs):
            captured.update(kwargs)
            raise EpochInvocation("captured epoch mutation")

        with mock.patch.object(
            engine,
            "_run_candidate_observation_locked",
            return_value=(state, object()),
        ), mock.patch.object(
            APP,
            "_observe_current_merge_candidate",
            return_value=(repository, object(), ("src/app.py",)),
        ), mock.patch.object(
            ENGINE, "_require_active_merge_epoch"
        ), mock.patch.object(
            ENGINE, "_merge_epoch_suite", return_value=suite
        ), mock.patch.object(
            ENGINE,
            "_merge_run_directory",
            return_value=(
                self.repo.resolve(),
                self.repo / ".codex-orchestrator" / "runs" / self.run_id,
            ),
        ), mock.patch.object(
            CORE, "run_fenced_command", side_effect=capture
        ), self.assertRaisesRegex(EpochInvocation, "captured epoch mutation"):
            engine._run_epoch_suite(
                state,
                mock.sentinel.lock,
                mock.sentinel.lease,
                budget,
            )

        self.assertEqual(
            captured["argv"],
            [
                sys.executable,
                str(self.helpers / "run-scoped-mutation.py"),
                "--base",
                self.base,
                "--head",
                self.candidate_head,
                "--repository",
                str(self.repo.resolve()),
                "--run-id",
                self.run_id,
                "--task",
                self.task_id,
                "--defer-journal",
            ],
        )
        self.assertEqual(
            captured["env"]["FORGE_SESSION_PID"], str(os.getpid())
        )
        self.assertTrue(callable(captured.get("result_transform")))
        raw = mock.sentinel.raw_mutation_result
        with mock.patch.object(
            APP, "_persist_deferred_mutation_result", return_value=raw
        ) as persist:
            self.assertIs(captured["result_transform"](raw), raw)
        persist.assert_called_once_with(
            raw,
            repository=self.repo.resolve(),
            run_id=self.run_id,
            task=self.task_id,
            base=self.base,
            head=self.candidate_head,
        )
        budget.consume.assert_called_once_with("suites")

    def test_deferred_mutation_persists_reentrantly_without_changing_public_fact(self) -> None:
        self.open_run()
        batch, builders, journal_module = CLI._coordination_modules()
        run_dir = self.repo / ".codex-orchestrator" / "runs" / self.run_id
        journal_path = run_dir / "journal.jsonl"
        ledger_path = run_dir / journal_module.BATCH_RECEIPTS_NAME
        receipt_count = len(ledger_path.read_text(encoding="utf-8").splitlines())
        runner = runpy.run_path(str(ROOT / "scripts/forge/run-scoped-mutation.py"))
        record = runner["verification_record"](
            task=self.task_id,
            scope="python",
            result="passed",
            check="true",
            observation="tool=mutmut; scope=python; outcome=completed",
        )
        request = runner["mutation_journal_request"](
            repository=self.repo,
            run_id=self.run_id,
            base=self.base,
            head=self.candidate_head,
            record=record,
        )
        evidence = {
            "type": "mutation_evidence",
            "criterion": record["criterion"],
            "result": record["result"],
            "check": record["check"],
            "observation": record["observation"],
        }
        public_output = (runner["json_text"](evidence) + "\n").encode("utf-8")
        sideband = (
            runner["MUTATION_JOURNAL_SIDEBAND_PREFIX"]
            + runner["json_text"](
                request,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
        raw = CORE.FencedProcessResult(
            argv=["python3", "run-scoped-mutation.py"],
            returncode=0,
            duration_seconds=0.01,
            output=public_output + sideband,
            output_digest=digest(public_output + sideband),
            timed_out=False,
            output_limit=False,
            launch_failed=False,
            group_survived=False,
            authorized=True,
            fence_digest="1" * 64,
            fence_inode=1,
        )

        with batch.batch_lock(run_dir, create=False):
            first = APP._persist_deferred_mutation_result(
                raw,
                repository=self.repo,
                run_id=self.run_id,
                task=self.task_id,
                base=self.base,
                head=self.candidate_head,
            )
            journal_after_first = journal_path.read_bytes()
            ledger_after_first = ledger_path.read_bytes()
            repeated = APP._persist_deferred_mutation_result(
                raw,
                repository=self.repo,
                run_id=self.run_id,
                task=self.task_id,
                base=self.base,
                head=self.candidate_head,
            )

        self.assertEqual(first.output, public_output)
        self.assertEqual(first.output_digest, digest(public_output))
        self.assertEqual(first.returncode, raw.returncode)
        self.assertEqual(first.timed_out, raw.timed_out)
        self.assertEqual(first.output_limit, raw.output_limit)
        self.assertEqual(repeated.output, public_output)
        self.assertEqual(journal_path.read_bytes(), journal_after_first)
        self.assertEqual(ledger_path.read_bytes(), ledger_after_first)
        self.assertEqual(
            len(ledger_path.read_text(encoding="utf-8").splitlines()),
            receipt_count + 1,
        )
        state = journal_module._scan_run(run_dir)
        mutation_records = [
            item
            for item in state.records
            if item.get("type") == "verification"
            and item.get("criterion") == "mutation: python"
        ]
        self.assertEqual(len(mutation_records), 1)
        self.assertEqual(mutation_records[0]["id"], "check-01")
        self.assertFalse(first.timed_out or first.output_limit or first.launch_failed)

        journal_before_refusal = journal_path.read_bytes()
        ledger_before_refusal = ledger_path.read_bytes()
        existing_refusal = (
            "forge: journal append refused — owner record missing or malformed for run "
            + self.run_id
        )
        with mock.patch.object(
            builders,
            "verification_add",
            side_effect=RuntimeError(existing_refusal),
        ), batch.batch_lock(run_dir, create=False):
            advisory = APP._persist_deferred_mutation_result(
                raw,
                repository=self.repo,
                run_id=self.run_id,
                task=self.task_id,
                base=self.base,
                head=self.candidate_head,
            )
        self.assertEqual(
            advisory.output,
            public_output
            + (existing_refusal + "\n").encode()
            + (
                "forge: scoped mutation journal persistence unavailable — advisory "
                "evidence emitted only\n"
            ).encode(),
        )
        self.assertEqual(advisory.output_digest, digest(advisory.output))
        self.assertEqual(advisory.returncode, raw.returncode)
        self.assertEqual(advisory.timed_out, raw.timed_out)
        self.assertEqual(advisory.output_limit, raw.output_limit)
        self.assertEqual(advisory.launch_failed, raw.launch_failed)
        self.assertEqual(advisory.group_survived, raw.group_survived)
        self.assertEqual(journal_path.read_bytes(), journal_before_refusal)
        self.assertEqual(ledger_path.read_bytes(), ledger_before_refusal)

    def test_deferred_mutation_advisory_stays_within_fenced_output_cap(self) -> None:
        prefix = APP._MUTATION_JOURNAL_SIDEBAND_PREFIX
        public_output = b"x" * (RUNTIME.OUTPUT_CAP_BYTES - len(prefix) - 1) + b"\n"
        raw_output = public_output + prefix
        self.assertEqual(len(raw_output), RUNTIME.OUTPUT_CAP_BYTES)
        raw = CORE.FencedProcessResult(
            argv=["python3", "run-scoped-mutation.py"],
            returncode=0,
            duration_seconds=0.01,
            output=raw_output,
            output_digest=digest(raw_output),
            timed_out=False,
            output_limit=True,
            launch_failed=False,
            group_survived=False,
            authorized=True,
            fence_digest="1" * 64,
            fence_inode=1,
        )

        transformed = APP._persist_deferred_mutation_result(
            raw,
            repository=self.repo,
            run_id=self.run_id,
            task=self.task_id,
            base=self.base,
            head=self.candidate_head,
        )

        advisory = (APP._MUTATION_PERSISTENCE_ADVISORY + "\n").encode()
        self.assertEqual(len(transformed.output), RUNTIME.OUTPUT_CAP_BYTES)
        self.assertTrue(transformed.output.endswith(advisory))
        self.assertNotIn(prefix, transformed.output)
        self.assertEqual(transformed.output_digest, digest(transformed.output))
        self.assertTrue(transformed.output_limit)
        self.assertEqual(transformed.returncode, raw.returncode)
        self.assertEqual(transformed.launch_failed, raw.launch_failed)
        self.assertEqual(transformed.group_survived, raw.group_survived)

    def test_failed_gate_is_durable_remote_safe_and_resumable(self) -> None:
        admission, generation = self.admission_and_generation()
        store, _state = self.create_chain(admission, generation)
        engine = CLI.MergeEngine(self.context(chain_id=self.chain_id))
        def unavailable_gate(argv, **kwargs):
            if Path(argv[1]).name == "check-halt.sh":
                return self.passing_process(argv, **kwargs)
            raise OSError("fixture gate missing")

        with mock.patch.object(RUNTIME, "run_bounded", side_effect=unavailable_gate):
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
            RUNTIME, "run_bounded", side_effect=self.passing_process
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

    def test_bound_receipted_mutation_preserves_gate_three_evidence_and_disposition(
        self,
    ) -> None:
        _admission, _generation, store, engine, _outcome, _calls = self.verify_chain(
            bound=True
        )
        engine.review_request()
        request = store.load(self.chain_id)["review"]["request"]
        verdict = self.write_verdict("merge-mutation-pass.txt", "PASS", request)
        engine.review_attach(str(verdict))

        _batch, _builders, journal_module = CLI._coordination_modules()
        run_dir = self.repo / ".codex-orchestrator" / "runs" / self.run_id
        journal_path = run_dir / "journal.jsonl"
        ledger_path = run_dir / journal_module.BATCH_RECEIPTS_NAME
        events_path = store.events_path(self.chain_id)
        state_path = store.state_path(self.chain_id)
        chain_before = store.load(self.chain_id)
        self.assertEqual(chain_before["state"], "authorized")
        journal_before = journal_path.read_bytes()
        ledger_before = ledger_path.read_bytes()
        events_before = events_path.read_bytes()
        state_before = state_path.read_bytes()
        review_package = run_dir / str(request["package"])
        review_package_before = review_package.read_bytes()
        gate_three_before = [
            copy.deepcopy(record)
            for record in journal_module._scan_run(run_dir).records
            if record.get("type") == "verification"
            and record.get("criterion") == journal_module.GATE_3_CRITERION
        ]
        self.assertEqual(len(gate_three_before), 1)

        runner = runpy.run_path(str(ROOT / "scripts/forge/run-scoped-mutation.py"))
        record = runner["verification_record"](
            task=self.task_id,
            scope="python",
            result="passed",
            check="true",
            observation="tool=mutmut; scope=python; outcome=completed",
        )
        mutation_request = runner["mutation_journal_request"](
            repository=self.repo,
            run_id=self.run_id,
            base=self.base,
            head=self.candidate_head,
            record=record,
        )
        evidence = {
            "type": "mutation_evidence",
            "criterion": record["criterion"],
            "result": record["result"],
            "check": record["check"],
            "observation": record["observation"],
        }
        public_output = (runner["json_text"](evidence) + "\n").encode("utf-8")
        sideband = (
            runner["MUTATION_JOURNAL_SIDEBAND_PREFIX"]
            + runner["json_text"](
                mutation_request,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
        raw = CORE.FencedProcessResult(
            argv=["python3", "run-scoped-mutation.py"],
            returncode=0,
            duration_seconds=0.01,
            output=public_output + sideband,
            output_digest=digest(public_output + sideband),
            timed_out=False,
            output_limit=False,
            launch_failed=False,
            group_survived=False,
            authorized=True,
            fence_digest="1" * 64,
            fence_inode=1,
        )

        transformed = APP._persist_deferred_mutation_result(
            raw,
            repository=self.repo,
            run_id=self.run_id,
            task=self.task_id,
            base=self.base,
            head=self.candidate_head,
        )

        self.assertEqual(transformed.output, public_output)
        journal_after = journal_path.read_bytes()
        ledger_after = ledger_path.read_bytes()
        mutation_batch = journal_after[len(journal_before) :]
        receipt_suffix = ledger_after[len(ledger_before) :]
        self.assertTrue(mutation_batch.endswith(b"\n"))
        self.assertTrue(receipt_suffix.endswith(b"\n"))
        self.assertEqual(len(mutation_batch.splitlines()), 1)
        self.assertEqual(len(receipt_suffix.splitlines()), 1)
        persisted = json.loads(mutation_batch)
        receipt = json.loads(receipt_suffix)
        self.assertEqual(persisted["id"], "check-06")
        self.assertEqual(persisted["criterion"], "mutation: python")
        self.assertEqual(receipt["schema"], journal_module.BATCH_RECEIPT_SCHEMA)
        self.assertEqual(receipt["base_size"], len(journal_before))
        self.assertEqual(receipt["record_count"], 1)
        self.assertEqual(receipt["batch_sha256"], digest(mutation_batch))
        self.assertEqual(receipt["journal_size"], len(journal_after))
        self.assertEqual(receipt["journal_sha256"], digest(journal_after))

        gate_three_after = [
            record
            for record in journal_module._scan_run(run_dir).records
            if record.get("type") == "verification"
            and record.get("criterion") == journal_module.GATE_3_CRITERION
        ]
        self.assertEqual(gate_three_after, gate_three_before)
        self.assertEqual(events_path.read_bytes(), events_before)
        self.assertEqual(state_path.read_bytes(), state_before)
        self.assertEqual(store.load(self.chain_id), chain_before)
        self.assertEqual(review_package.read_bytes(), review_package_before)

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

    def test_oversized_master_package_uses_single_master_transport(self) -> None:
        _admission, _generation, store, engine, _outcome, _calls = self.verify_chain()
        before_events = store.events_path(self.chain_id).read_bytes()
        marker = b"OVERSIZED_MERGE_MASTER_BYTES_MUST_NOT_BE_EMBEDDED"
        byte_length = ENGINE.REVIEW_DIRECT_PACKAGE_MAX_BYTES + 1
        oversized = marker + (b"x" * (byte_length - len(marker)))
        with mock.patch.object(
            engine,
            "_review_package",
            return_value=(oversized, [], {}),
        ):
            outcome = engine.review_request()

        state = store.load(self.chain_id)
        request = state["review"]["request"]
        package_path = self.repo / request["package"]
        package_digest = digest(oversized)
        window_size = ENGINE.REVIEW_MASTER_WINDOW_BYTES
        window_count = (byte_length + window_size - 1) // window_size
        receipt = f"{outcome.message}\n{request['invocation']}"

        self.assertEqual(state["state"], "reviewing")
        self.assertEqual(request["transport"], "single-master-package")
        self.assertEqual(request["byte_length"], byte_length)
        self.assertEqual(request["window_size"], 65_536)
        self.assertEqual(request["window_count"], window_count)
        self.assertEqual(request["package_digest"], package_digest)
        self.assertRegex(request["package_digest"], r"^[0-9a-f]{64}$")
        self.assertTrue(package_path.is_file())
        self.assertEqual(package_path.stat().st_uid, os.geteuid())
        self.assertEqual(package_path.stat().st_nlink, 1)
        self.assertEqual(package_path.read_bytes(), oversized)
        self.assertEqual(
            b"".join(
                ENGINE.iter_verified_master_package_windows(
                    package_path, byte_length, package_digest
                )
            ),
            oversized,
        )
        self.assertIn("authoritative-master", receipt)
        self.assertIn(
            f"path={json.dumps(str(package_path), ensure_ascii=True)}", receipt
        )
        self.assertIn(f"byte-length={byte_length}", receipt)
        self.assertIn(f"sha256={package_digest}", receipt)
        self.assertIn(
            "windows=[65536*n, min(65536*(n+1), byte_length))", receipt
        )
        self.assertIn(
            f"window-count=ceil({byte_length}/65536)={window_count}", receipt
        )
        self.assertIn(
            "reader=forge_cli.engine.iter_verified_master_package_windows", receipt
        )
        self.assertNotIn(marker.decode(), receipt)
        self.assertEqual(
            sorted(path.name for path in package_path.parent.iterdir()),
            ["master-package.txt"],
        )
        after_events = store.events_path(self.chain_id).read_bytes()
        self.assertTrue(after_events.startswith(before_events))
        self.assertEqual(
            len(after_events.splitlines()), len(before_events.splitlines()) + 1
        )

    def test_disposition_slot_allows_minor_then_exactly_one_above_minor(self) -> None:
        starter = CLI.MergeEngine(self.context())
        started = starter.start_chain(str(self.worktree), remote_tip=self.base)
        self.chain_id = str(started.chain_id)
        store = starter.store
        engine = CLI.MergeEngine(self.context(chain_id=self.chain_id))
        with mock.patch.object(RUNTIME, "run_bounded", side_effect=self.passing_process):
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
