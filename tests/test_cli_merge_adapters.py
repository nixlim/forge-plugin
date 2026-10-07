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

from tests._git_env import init_quiet_repository


ROOT = Path(__file__).resolve().parents[1]
CLI_PATH = ROOT / "scripts" / "forge" / "cli.py"


from tests._cli_loader import load_script, package_module, patch_app, patch_chain_core, patch_engine  # cli split phase 0: one shared loader


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
    control = path.startswith(("rules/", "agents/", "system/")) or path == "scripts/forge/route_config.py"
    floor = path.startswith("scripts/") or control
    if floor:
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
            "review_final_floor": floor,
            "strict_floor": floor,
            "tier": tier,
        }
    )
effective = derived
if args.declared_tier and rank[args.declared_tier] > rank[effective]:
    effective = args.declared_tier
if any(record["review_final_floor"] for record in records):
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
        for name in ("CODEX", "CLAUDE"):
            provider_patch = patch_engine(
                f"{name}_EXECUTABLE", str(self.helpers / f"fake-{name.lower()}")
            )
            provider_patch.start()
            self.addCleanup(provider_patch.stop)

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
        result = init_quiet_repository(
            self.origin,
            "--bare",
            "--quiet",
            cwd=self.temp_root,
            environment=self.environment(),
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


    def admission_and_generation(
        self, *, bound: bool = False
    ) -> tuple[object, object]:
        context = self.context(run_id=None)
        engine = CLI.MergeEngine(context)
        admission = engine.start(
            str(self.worktree),
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
        initial = {
            "schema": "forge-merge-chain/1",
            "chain_id": chain_id,
            "kind": "merge",
            "state": "classifying",
            "created_at": at,
            "owner": owner,
            "run": None,
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

    def complete_review(self, engine, *, mode: str = "pass"):
        executable = self.helpers / f"fake-claude{'-' + mode if mode != 'pass' else ''}"
        with patch_engine("CLAUDE_EXECUTABLE", str(executable)):
            requested = engine.review_request()
        state = engine.store.load(str(engine.ctx.options.chain_id))
        request = state["review"]["request"]
        return requested, request, self.collect_review(engine, request)

    def collect_review(self, engine, request, verdict=None, *findings):
        completion_path = self.wait_for_review_completion(request)
        if verdict is not None:
            verdict_path = self.repo / str(request["verdict_path"])
            rendered = self.write_verdict("replacement.txt", verdict, request, *findings)
            verdict_bytes = rendered.read_bytes()
            verdict_path.write_bytes(verdict_bytes)
            completion = json.loads(completion_path.read_text(encoding="utf-8"))
            completion.update(verdict_digest=digest(verdict_bytes), verdict_size=len(verdict_bytes))
            completion_path.write_bytes(CLI.canonical_bytes(completion) + b"\n")
        return engine.review_collect()


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

    def test_admission_and_generation_are_exactly_fixed(self) -> None:
        engine = CLI.MergeEngine(self.context())
        admission = engine.start(str(self.worktree))
        with mock.patch.object(
            RUNTIME, "run_bounded", wraps=CLI.run_bounded
        ) as bounded:
            generation = engine.bind_candidate(admission, self.base)
        launched = [list(call.args[0]) for call in bounded.call_args_list]
        self.assertEqual(Path(launched[0][1]).name, "risk_tier.py")
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


    def test_git_environment_contract_is_closed(self) -> None:
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

        }
        for control, call in calls.items():
            with self.subTest(control=control), patch_chain_core("MERGE_ADAPTER_CONTROLS",
                CLI.MERGE_ADAPTER_CONTROLS - {control},
            ), self.assertRaisesRegex(
                CLI.FrozenError,
                f"merge adapter control is unavailable: {control}",
            ):
                call()


class MergeGateAdapterTests(MergeAdapterFixture):

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





class MergeReviewAdapterTests(MergeAdapterFixture):
    def test_review_is_mandatory_single_master_and_collect_requires_request(self) -> None:
        _admission, generation, store, engine, _outcome, _calls = self.verify_chain()
        before = store.events_path(self.chain_id).read_bytes()
        with self.assertRaises(CLI.Refusal) as caught:
            engine.review_collect()
        self.assertEqual(caught.exception.reason_code, CLI.V2ReasonCode.STATE_PRECONDITION)
        self.assertEqual(
            caught.exception.message,
            "forge: review collect refused — merge transition is not admitted",
        )
        self.assertEqual(store.events_path(self.chain_id).read_bytes(), before)

        with patch_engine("new_attempt_id", return_value="attempt-0123456789abcdef") as mint:
            engine.review_request()
        request = store.load(self.chain_id)["review"]["request"]
        self.assertEqual(
            (mint.call_count, request["attempt"], request["reviewer"], request["candidate"]),
            (1, "attempt-0123456789abcdef", "review-final", self.candidate_head),
        )
        self.assertEqual(
            request["generation_digest"], generation.candidate["generation_digest"]
        )
        package_bytes = (self.repo / request["package"]).read_bytes()
        self.assertEqual(digest(package_bytes), request["package_digest"])
        self.assertEqual(request["byte_length"], len(package_bytes))
        self.assertIn(b"FORGE MERGE REVIEW MASTER PACKAGE v1", package_bytes)
        self.assertIn(
            f"target: {CLI.canonical_bytes(request['target']).decode()}".encode(),
            package_bytes,
        )
        self.assertIn(b"--- BEGIN UNTRUSTED CANDIDATE DIFF ---", package_bytes)
        self.collect_review(engine, request)

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
        package_bytes = package_path.read_bytes()
        package_digest = digest(package_bytes)
        byte_length = len(package_bytes)
        window_size = ENGINE.REVIEW_MASTER_WINDOW_BYTES
        window_count = (byte_length + window_size - 1) // window_size
        prompt = (self.repo / request["prompt_path"]).read_text(encoding="utf-8")

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
        self.assertIn(marker, package_bytes)
        self.assertEqual(
            b"".join(
                ENGINE.iter_verified_master_package_windows(
                    package_path, byte_length, package_digest
                )
            ),
            package_bytes,
        )
        self.assertIn("authoritative-master", prompt)
        self.assertIn(f"sha256={package_digest}", prompt)
        self.assertNotIn(marker.decode(), outcome.message)
        self.assertEqual(request["lane"], "forge-review-lane/1")
        self.assertEqual(request["provider"], "claude")
        self.assertEqual(request["attempt"], Path(request["completion_path"]).parent.name)
        self.collect_review(engine, request)
        after_events = store.events_path(self.chain_id).read_bytes()
        self.assertTrue(after_events.startswith(before_events))
        self.assertEqual(
            len(after_events.splitlines()), len(before_events.splitlines()) + 2
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
        with patch_engine("CLAUDE_EXECUTABLE", str(self.helpers / "fake-claude")):
            engine.review_request()
        request = store.load(self.chain_id)["review"]["request"]
        self.collect_review(
            engine,
            request,
            "BLOCK",
            ("MINOR", "minor finding"),
            ("MAJOR", "major finding"),
            ("CRITICAL", "critical finding"),
            ("MAJOR", "second major finding"),
        )
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
