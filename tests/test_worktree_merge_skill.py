from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
from dataclasses import dataclass
from pathlib import Path

from tests._git_env import init_quiet_repository, quiet_repository

ROOT = Path(__file__).resolve().parents[1]
SKILL = (ROOT / "skills/worktree-merge/SKILL.md").read_text(encoding="utf-8")
RENAME_FLAGS = (" --no-renames ", " --no-ext-diff ", " --no-textconv ")
FULL_PATCH_COMMANDS = (
    'git diff "origin/${DEFAULT_BRANCH}...HEAD"',
    'git diff "${REVIEWED_BASE}...${CANDIDATE_HEAD}"',
    'git diff "${INTEGRATED_BASE}...${INTEGRATED_HEAD}"',
)
GIT_TEST_ENV = {
    key: value for key, value in os.environ.items() if not key.startswith("GIT_")
}
GIT_TEST_ENV.update(
    GIT_AUTHOR_NAME="Forge Cleanup Test", GIT_AUTHOR_EMAIL="forge-cleanup@example.invalid",
    GIT_COMMITTER_NAME="Forge Cleanup Test", GIT_COMMITTER_EMAIL="forge-cleanup@example.invalid",
    GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0",
)


def name_only_listings(text: str) -> list[str]:
    return [
        line
        for line in text.splitlines()
        if line.startswith("git diff") and "--name-only" in line
    ]


def assert_rename_listing_contract(case: unittest.TestCase, text: str) -> None:
    listings = name_only_listings(text)
    case.assertEqual(len(listings), 2)
    for listing in listings:
        for flag in RENAME_FLAGS:
            case.assertIn(flag, listing)
    lines = text.splitlines()
    for patch in FULL_PATCH_COMMANDS:
        patch_lines = [line for line in lines if patch in line]
        case.assertEqual(len(patch_lines), 1)
        for flag in RENAME_FLAGS:
            case.assertNotIn(flag, patch_lines[0])


def rename_listing_mutants(text: str) -> tuple[tuple[str, str], ...]:
    removed_flags = tuple(
        (
            f"remove {flag} from {listing}",
            text.replace(listing, listing.replace(flag, " ", 1), 1),
        )
        for listing in name_only_listings(text)
        for flag in RENAME_FLAGS
    )
    added_flags = tuple(
        (
            f"add {flag} to {patch}",
            text.replace(patch, f"{patch}{flag}", 1),
        )
        for patch in FULL_PATCH_COMMANDS
        for flag in RENAME_FLAGS
    )
    return removed_flags + added_flags


def assert_cleanup_contract(case: unittest.TestCase, skill: str) -> None:
    cleanup = skill.split("## Cleanup after successful push", 1)[1].split(
        "## Record authority and report", 1
    )[0]
    ordered = (
        'git fetch origin "$DEFAULT_BRANCH" --quiet || {',
        'git merge-base --is-ancestor "$PUSHED_HEAD"',
        'CURRENT_BRANCH_TIP="$(git -C "$MAIN_WORKTREE" rev-parse --verify -q',
        'WORKTREE_BRANCH="$(git -C "$WORKTREE_DIR" symbolic-ref --quiet HEAD)"',
        '[ "$WORKTREE_BRANCH" = "refs/heads/${BRANCH}" ]',
        'WORKTREE_HEAD="$(git -C "$WORKTREE_DIR" rev-parse --verify HEAD^{commit})"',
        '[ "$WORKTREE_HEAD" = "$CURRENT_BRANCH_TIP" ]',
        'WORKTREE_STATUS="$(git -C "$WORKTREE_DIR" status',
        '[ -z "$WORKTREE_STATUS" ]',
        '[ "$CURRENT_BRANCH_TIP" != "$PUSHED_HEAD" ]',
        '"$CURRENT_BRANCH_TIP" "origin/${DEFAULT_BRANCH}"',
        'cd "$MAIN_WORKTREE" || {',
        'git -C "$MAIN_WORKTREE" worktree remove "$WORKTREE_DIR" || {',
        'DELETE_BRANCH_TIP="$(git -C "$MAIN_WORKTREE" rev-parse --verify -q',
        '[ "$DELETE_BRANCH_TIP" = "$CURRENT_BRANCH_TIP" ]',
        '"$DELETE_BRANCH_TIP" "origin/${DEFAULT_BRANCH}"',
        'git -C "$MAIN_WORKTREE" update-ref -d',
        '"refs/heads/$BRANCH" "$DELETE_BRANCH_TIP"',
    )
    for fragment in ordered:
        case.assertEqual(cleanup.count(fragment), 1)
    case.assertEqual([cleanup.index(x) for x in ordered], sorted(cleanup.index(x) for x in ordered))
    case.assertNotIn('worktree-check', cleanup)
    case.assertNotIn('git branch -D "', cleanup)
    case.assertIn('Never use `branch -D`', cleanup)
    case.assertIn('No failed merge path removes a worktree', cleanup)


def run_git(
    repo: Path, *args: str, check: bool = True
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=check,
        capture_output=True,
        env=GIT_TEST_ENV,
        text=True,
    )


def seed_rename_repo(path: Path) -> None:
    init_quiet_repository(path, "-q", environment=GIT_TEST_ENV).check_returncode()
    (path / "skills").mkdir()
    (path / "skills/x.md").write_text("guarded\n", encoding="utf-8")
    commands = (
        ("add", "."),
        (
            "-c",
            "user.name=Forge",
            "-c",
            "user.email=forge@example.invalid",
            "commit",
            "-qm",
            "initial",
        ),
        ("mv", "skills/x.md", "docs-x.md"),
        (
            "-c",
            "user.name=Forge",
            "-c",
            "user.email=forge@example.invalid",
            "commit",
            "-qm",
            "rename",
        ),
    )
    for command in commands:
        run_git(path, *command)


@dataclass(frozen=True)
class CleanupFixture:
    main: Path
    worktree: Path
    pushed_head: str


@dataclass(frozen=True)
class CleanupOutcome:
    process: subprocess.CompletedProcess[str]
    worktree_exists: bool
    branch_tip: str | None
    expected_tip: str


def seed_cleanup_fixture(root: Path) -> CleanupFixture:
    origin = root / "origin.git"
    seed = root / "seed"
    main = root / "main"
    worktree = root / "linked-topic"
    init_quiet_repository(origin, "--bare", "--quiet",
                          environment=GIT_TEST_ENV).check_returncode()
    init_quiet_repository(
        seed, "--quiet", "--initial-branch=main", environment=GIT_TEST_ENV,
    ).check_returncode()
    (seed / "tracked.txt").write_text("base\n", encoding="utf-8")
    run_git(seed, "add", "--", "tracked.txt")
    run_git(seed, "commit", "--quiet", "-m", "base")
    run_git(seed, "remote", "add", "origin", str(origin))
    run_git(seed, "push", "--quiet", "origin", "main")
    run_git(origin, "symbolic-ref", "HEAD", "refs/heads/main")
    run_git(root, "clone", "--quiet", str(origin), str(main))
    quiet_repository(main)
    run_git(main, "worktree", "add", "--quiet", "-b", "topic", str(worktree))
    (worktree / "topic.txt").write_text("topic\n", encoding="utf-8")
    run_git(worktree, "add", "--", "topic.txt")
    run_git(worktree, "commit", "--quiet", "-m", "topic")
    pushed_head = run_git(worktree, "rev-parse", "HEAD").stdout.strip()
    run_git(worktree, "push", "--quiet", "origin", "HEAD:main")
    return CleanupFixture(main, worktree, pushed_head)


def apply_cleanup_scenario(fixture: CleanupFixture, scenario: str) -> str:
    if scenario == "unpushed":
        (fixture.worktree / "topic.txt").write_text(
            "topic\nunpushed\n", encoding="utf-8")
        run_git(fixture.worktree, "add", "--", "topic.txt")
        run_git(fixture.worktree, "commit", "--quiet", "-m", "unpushed")
    elif scenario == "untracked":
        (fixture.worktree / "untracked.txt").write_text(
            "untracked\n", encoding="utf-8")
    elif scenario == "modified":
        (fixture.worktree / "topic.txt").write_text("modified\n", encoding="utf-8")
    elif scenario == "detached":
        run_git(fixture.worktree, "checkout", "--detach", "--quiet")
    elif scenario != "clean":
        raise AssertionError(f"unknown cleanup scenario: {scenario}")
    return run_git(fixture.main, "rev-parse", "refs/heads/topic").stdout.strip()


def extracted_cleanup_block(skill: str) -> str:
    section = skill.split("## Cleanup after successful push", 1)[1].split(
        "## Record authority and report", 1
    )[0]
    blocks = re.findall(r"```bash\n(.*?)```", section, flags=re.DOTALL)
    if len(blocks) != 1:
        raise AssertionError("expected one merge cleanup block")
    return blocks[0]


def run_cleanup_case(
    scenario: str, *, skill: str = SKILL
) -> CleanupOutcome:
    with tempfile.TemporaryDirectory(prefix="forge-cleanup-exec-") as scratch:
        root = Path(scratch)
        fixture = seed_cleanup_fixture(root)
        expected_tip = apply_cleanup_scenario(fixture, scenario)
        environment = dict(
            GIT_TEST_ENV,
            CLAUDE_PLUGIN_ROOT=str(ROOT),
            DEFAULT_BRANCH="main",
            GIT_COMMON_DIR=str(fixture.main / ".git"),
            WORKTREE_DIR=str(fixture.worktree),
            BRANCH="topic",
            TEST_WORKTREE=str(fixture.worktree),
            TEST_PUSHED_HEAD=fixture.pushed_head,
        )
        script = extracted_cleanup_block(skill)
        process = subprocess.run(
            ["bash", "-c", script],
            cwd=fixture.worktree,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        tip = run_git(
            fixture.main,
            "rev-parse",
            "--verify",
            "-q",
            "refs/heads/topic^{commit}",
            check=False,
        )
        return CleanupOutcome(
            process,
            fixture.worktree.exists(),
            tip.stdout.strip() or None,
            expected_tip,
        )


def weaken_refusal_exit(text: str, diagnostic: str) -> str:
    marker = f'echo "{diagnostic}" >&2'
    marker_at = text.index(marker)
    exit_at = text.index("exit ", marker_at + len(marker))
    return text[:exit_at] + "true" + text[exit_at + len("exit 1") :]


def assert_cleanup_refused(
    case: unittest.TestCase,
    outcome: CleanupOutcome,
    scenario: str,
) -> None:
    if scenario == "unpushed":
        diagnostic = "forge: pushed candidate is not contained in origin/main — cleanup refused"
    elif scenario in {"untracked", "modified"}:
        diagnostic = "forge: worktree is not clean — cleanup refused"
    else:
        diagnostic = "forge: worktree branch is unavailable — cleanup refused"
    case.assertEqual(outcome.process.returncode, 1,
                     outcome.process.stderr)
    case.assertEqual(outcome.process.stderr, diagnostic + "\n")
    case.assertTrue(outcome.worktree_exists)
    case.assertEqual(outcome.branch_tip, outcome.expected_tip)


class WorktreeMergeSkillTests(unittest.TestCase):
    def test_frontmatter_and_single_region_source(self) -> None:
        self.assertTrue(SKILL.startswith("---\nname: worktree-merge\n"))
        self.assertIn("exclusively from that root-level\ncommitted revision", SKILL)
        for region in (
            "gate1-test-command",
            "stack-validations",
            "file-categories",
            "mutation-testing",
        ):
            with self.subTest(region=region):
                self.assertIn(region, SKILL)
        self.assertIn("forge: <region> not configured — run /forge:init", SKILL)

    def test_preconditions_and_gates_are_ordered(self) -> None:
        required = (
            "git status --porcelain=v1 --untracked-files=all",
            "git diff origin/<default-branch>...HEAD",
            "## Gate 1 — Project tests",
            "## Gate 2 — Stack validations",
            "## Gate 3 — Binding adversarial review",
            "## Gate 4 — Summary and authority",
        )
        positions = [SKILL.index(item) for item in required]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("Fail closed", SKILL)
        self.assertIn("maximum of 8 review iterations", SKILL)
        self.assertIn("never merge", SKILL)

    def test_noncritical_drift_is_advisory_before_gate_one(self) -> None:
        clean_tree = SKILL.index("git status --porcelain=v1 --untracked-files=all")
        drift_contract = SKILL.index("### Drift state is not a merge input")
        gate_one = SKILL.index("## Gate 1 — Project tests")
        self.assertLess(clean_tree, drift_contract)
        self.assertLess(drift_contract, gate_one)

        contract = SKILL[drift_contract:gate_one]
        required_in_order = (
            "After the clean-worktree precondition passes",
            "continue toward Gate 1 without consulting drift\nstate",
            "do not read\n`.forge/history/drift/**` or `.forge/tmp/drift-block`",
            "A recorded MAJOR or MINOR finding",
            "advisory to merge and does not stop or change the merge gates",
            "An existing drift-block is likewise\nnot a merge input",
            "Proceed through the remaining configured preconditions to Gate 1",
        )
        positions = [contract.index(item) for item in required_in_order]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("separate workflow-opening rule for CRITICAL drift", contract)
        self.assertIn("does not authorize opening an orchestration run", contract)

    def test_merge_derives_tier_from_exact_committed_candidate_policy(self) -> None:
        invocation = (
            'python3 "${CLAUDE_PLUGIN_ROOT}/scripts/forge/risk_tier.py" \\\n'
            '  --repo "$PWD" --policy-sha "$policy_sha" "${declared_args[@]}" \\\n'
            '  --range "${REVIEWED_BASE}...${CANDIDATE_HEAD}"'
        )
        self.assertIn('policy_sha="$CANDIDATE_HEAD"', SKILL)
        self.assertIn('git show "${policy_sha}:forge-project.md"', SKILL)
        self.assertIn('declared_tier="${declared_tier:-}"', SKILL)
        self.assertIn('declared_args=()', SKILL)
        self.assertIn(invocation, SKILL)
        tiering = SKILL.split("Derive merge-tier evidence", 1)[1].split("Before Gate 1", 1)[0]
        for evidence in (
            "exact path list",
            "matched tier/trigger/category rows",
            "formatting-category decisions",
            "dependency-floor decision",
            "declared, derived, and promote-only\neffective tiers",
            "full policy SHA",
        ):
            self.assertIn(evidence, tiering)
        self.assertIn("can never be demoted at gate time", tiering)
        self.assertIn("non-narrowable floors", tiering)
        self.assertIn("matched tier/trigger/category rows and floor rows", tiering)
        self.assertIn("the built-in\nreview-final floor and project-extended control", tiering)
        self.assertIn("malformed nonempty trigger rows\nmake the range hard", tiering)
        self.assertIn("unmatched paths default standard", tiering)
        self.assertIn("unknown manifest membership are at least standard", tiering)

    def test_merge_skill_has_no_unimplemented_strict_eval_run(self) -> None:
        self.assertNotIn('STRICT=1 bash "${CLAUDE_PLUGIN_ROOT}/scripts/forge/run-evals.sh"', SKILL)

    def test_control_category_and_approval_are_fail_closed(self) -> None:
        for path in (
            "`forge-project.md`",
            "`.forge-manifest`",
            "`.codex/**`",
            "`.forge/evals/tasks/**`",
            "`AGENTS.md`",
            "`CLAUDE.md`",
            "`.claude/settings*.json`",
            "`.github/workflows/**`",
        ):
            with self.subTest(path=path):
                self.assertIn(path, SKILL)
        self.assertIn("`.forge/evals/candidates/**` is the sole eval-path exception", SKILL)
        self.assertIn("classify it as advisory/docs-class", SKILL)
        self.assertIn("`.forge/evals/tasks/**`, or creating or changing its baseline", SKILL)
        self.assertNotIn("`.forge/evals/**`", SKILL)
        self.assertIn("wait for explicit user approval naming that same SHA", SKILL)
        self.assertIn("Never approve a control-class merge autonomously", SKILL)
        self.assertIn("Use `CANDIDATE_HEAD` as the Gate 4\ncandidate identity", SKILL)

    def test_dm001_chain_evidence_and_fixed_review_diff(self) -> None:
        self.assertIn('git diff "${REVIEWED_BASE}...${CANDIDATE_HEAD}"', SKILL)
        self.assertIn("exact, unmodified diff", SKILL)
        self.assertNotIn("gate-3: review-final verdict", SKILL)
        flattened = " ".join(SKILL.split())
        self.assertIn('git diff "${INTEGRATED_BASE}...${INTEGRATED_HEAD}"', SKILL)
        self.assertIn("wait for explicit user approval naming that exact SHA", flattened)
        self.assertIn('require `git rev-parse HEAD` to equal `AUTHORIZED_HEAD`', SKILL)

    def test_gate_three_is_unconditional_after_all_fast_commits(self) -> None:
        gate3 = SKILL.split("## Gate 3", 1)[1].split("## Gate 4", 1)[0]
        self.assertIn("Gate 3 is unconditional", gate3)
        self.assertIn("effective-fast\nrange", gate3)
        self.assertIn("branch composed entirely of four-line fast-marker commits", gate3)
        self.assertIn("`review-final`", gate3)
        self.assertIn("never removes a merge gate", SKILL)

    def test_merge_review_block_event_is_post_outcome_and_advisory(self) -> None:
        gate3 = SKILL.split("## Gate 3", 1)[1].split("## Gate 4", 1)[0]
        delivered = gate3.index("first deliver and preserve the binding BLOCK outcome")
        emitted = gate3.index("emit-decision-event.py")
        self.assertLess(delivered, emitted)
        self.assertIn("event `review_block`", gate3)
        self.assertIn("SHA-256 of the exact reviewed merge diff", gate3)
        self.assertIn("surface `/forge:worktree-merge`", gate3)
        self.assertIn("never changes the Gate 3 verdict or exit status", gate3)
        self.assertIn("registers an in-flight writer but acquires no lock", SKILL)
        self.assertIn("os.O_WRONLY | os.O_APPEND | os.O_CREAT", SKILL)
        self.assertIn("makes exactly one `os.write()`", SKILL)
        self.assertIn("treats a short write as a failure", SKILL)
        self.assertIn("gates only drift-check's prune read-and-replace", SKILL)
        self.assertIn("does not extend to NFS/SMB network filesystems", SKILL)
        self.assertIn("Windows is out of scope", SKILL)
        self.assertIn("deduplicates merge review blocks by `(event, candidate)`", SKILL)

    def test_assertion_and_reviewer_measurement_events_are_exact_and_advisory(self) -> None:
        sensor = SKILL.split("After preserving the sensor's primary result", 1)[1].split(
            "## Gate 3", 1
        )[0]
        for event in (
            "`assertion_blocking`",
            "`assertion_advisory`",
            "`assertion_waived`",
        ):
            with self.subTest(event=event):
                self.assertIn(event, sensor)
        self.assertIn("exact merge-diff bytes", sensor)
        self.assertIn("surface\n`/forge:worktree-merge`", sensor)
        self.assertIn("clean\nsensor result", sensor)
        self.assertIn("emits no assertion event", sensor)
        self.assertIn("in-lock Gate 2 rerun", sensor)
        self.assertIn("never changes the\nGate 2 result or exit status", sensor)

        reviewer = SKILL.split(
            "After preserving each `review-final` invocation's complete verdict", 1
        )[1].split("For a revision", 1)[0]
        self.assertIn("`review_final_finding`", reviewer)
        self.assertIn("exact reviewed merge diff", reviewer)
        self.assertIn("surface\n`/forge:worktree-merge`", reviewer)
        for severity in ("`CRITICAL`", "`MAJOR`", "`MINOR`"):
            self.assertIn(severity, reviewer)
        self.assertIn("every required in-lock review", reviewer)
        self.assertIn("no findings emits no\nfinding event", reviewer)
        self.assertIn("never changes the verdict, review iteration, or exit status", reviewer)

    def test_scoped_mutation_runner_is_ordered_advisory_and_reviewed(self) -> None:
        gate_1_pass = SKILL.index("Require exit 0. Do not substitute")
        mutation = SKILL.index(
            'python3 "${CLAUDE_PLUGIN_ROOT}/scripts/forge/run-scoped-mutation.py"'
        )
        gate_2 = SKILL.index("## Gate 2 — Stack validations")
        gate_3 = SKILL.index("## Gate 3 — Binding adversarial review")
        evidence_handoff = SKILL.index(
            "Also give the reviewer the complete contents of `MUTATION_EVIDENCE_FILE`"
        )
        self.assertLess(gate_1_pass, mutation)
        self.assertLess(mutation, gate_2)
        self.assertLess(gate_2, gate_3)
        self.assertGreater(evidence_handoff, gate_3)
        self.assertIn('--base "$REVIEWED_BASE" --head "$CANDIDATE_HEAD"', SKILL)
        self.assertIn('--range "${INTEGRATED_BASE}...${INTEGRATED_HEAD}"', SKILL)
        integrated = SKILL.split("then replace the earlier tier evidence fail closed:", 1)[1]
        self.assertIn('TIER_EVIDENCE="$(python3', integrated)
        self.assertIn('--policy-sha "$policy_sha"', integrated)
        self.assertIn('"${declared_args[@]}"', integrated)
        self.assertIn(')" || exit 1', integrated)
        self.assertIn("A nonzero result, timeout, output-limit breach, launch failure", SKILL)
        self.assertIn("It never blocks merge and never satisfies Gate 1", SKILL)
        self.assertIn("criterion exactly `mutation: <scope>`", SKILL)
        self.assertIn("Never use\na `gate-` prefix for mutation evidence.", SKILL)

    def test_locked_rebase_contract_is_complete(self) -> None:
        """Revision 13 (9qf.7): the lock is FR-235's portable arbiter via common-lock hold."""
        for command in (
            'bash "${CLAUDE_PLUGIN_ROOT}/scripts/forge/check-halt.sh"',
            "git rev-parse --path-format=absolute --git-common-dir",
            'mkfifo -m 600 "$LOCK_READY_FIFO" "$LOCK_RELEASE_FIFO"',
            'exec 8<>"$LOCK_READY_FIFO" 9<>"$LOCK_RELEASE_FIFO"',
            "common-lock hold --owner-kind push --operation push --ready-fd 8",
            '<"$LOCK_RELEASE_FIFO" >"$LOCK_OUTCOME" 2>&1 9>&- &',
            "must not inherit the shell's read-write descriptor 9",
            "read -r -t 5 LOCK_READY <&8 && break",
            'kill -0 "$LOCK_HOLDER_PID" 2>/dev/null || break',
            '[ "$LOCK_WAITED" -lt 330 ] || break',
            "lock-release-failed",
            "with `8<&- 9>&-`\nappended",
            '[ "$LOCK_RELEASE_WAITED" -lt 60 ]',
            "lock-release-failed: holder still running after 60 s",
            "operator-reserved action",
            "Never delete `agent-rebase.lockdir` or\n`agent-rebase.lock.intent` from this skill",
            'record["schema"] == "forge-common-lock-ready/1"',
            'set(record) == {"schema", "owner_digest", "nonce", "pid"}',
            "printf 'release\\n' >&9",
            "exec 9>&- 8<&-",
            'wait "$LOCK_HOLDER_PID"',
            'outcome["reason_code"] == "ok"',
            'outcome["message"] == "forge: common rebase lock released"',
            "git fetch origin <default-branch>",
            "git rebase origin/<default-branch>",
            "git push origin HEAD:<default-branch>",
        ):
            with self.subTest(command=command):
                self.assertIn(command, SKILL)
        self.assertIn("Never skip locking", SKILL)
        self.assertGreaterEqual(SKILL.count("holder hint:"), 3)
        self.assertIn("agent-rebase.lockdir", SKILL)
        self.assertIn("portable owner first", SKILL)
        self.assertIn("Never create a merge commit", SKILL)
        self.assertIn("Do not defer a\nre-run until after the push", SKILL)
        self.assertIn("closes descriptor 9", SKILL)

    @staticmethod
    def _lock_blocks() -> tuple[str, str, str]:
        """The skill's exact fenced bytes: pipe setup, wrapper start, and release."""
        section = SKILL.split("## Locked rebase reintegration", maxsplit=1)[1].split(
            "## Cleanup after successful push", maxsplit=1
        )[0]
        fences = re.findall(r"```bash\n(.*?)```", section, flags=re.S)
        setup = next(block for block in fences if "mkfifo -m 600" in block)
        start = next(block for block in fences if "common-lock hold" in block)
        release = next(block for block in fences if "printf 'release" in block)
        return setup, start, release

    def _run_protocol(self, *, send_release: bool) -> tuple[subprocess.CompletedProcess, Path, Path]:
        setup, start, release = self._lock_blocks()
        temporary = Path(tempfile.mkdtemp(prefix="forge-wtm-protocol-"))
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", str(temporary)], check=False))
        init_quiet_repository(temporary, "-q", environment=GIT_TEST_ENV).check_returncode()
        common = Path(
            run_git(
                temporary, "rev-parse", "--path-format=absolute", "--git-common-dir"
            ).stdout.strip()
        )
        tail = release if send_release else 'echo early-exit >&2\nexit 7\n'
        script = "\n".join((setup, start, tail))
        environment = dict(GIT_TEST_ENV)
        environment.pop("FORGE_SESSION_PID", None)
        environment.update({
            "CLAUDE_PLUGIN_ROOT": str(ROOT),
            "FORGE_SESSION_PID": "424242",
            "PATH": str(Path(sys.executable).parent) + os.pathsep + environment.get("PATH", ""),
        })
        completed = subprocess.run(
            ["bash", "-c", script],
            cwd=temporary, env=environment, capture_output=True, text=True, timeout=90,
        )
        return completed, common, temporary / ".forge/tmp/rebase-lock-outcome.424242.json"

    @staticmethod
    def _owner_artifacts(common: Path) -> list[str]:
        return sorted(
            name for name in os.listdir(common)
            if name in {"agent-rebase.lockdir", "agent-rebase.lock.intent"}
        )

    def test_protocol_acquires_releases_and_frees_the_namespace(self) -> None:
        """Revision 13 (9qf.7): the exact fenced bytes hold and release the portable arbiter."""
        completed, common, outcome_path = self._run_protocol(send_release=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(self._owner_artifacts(common), [])
        # The fenced bytes remove the pipes and require the wrapper's exact outcome.
        self.assertFalse((outcome_path.parent / "rebase-lock-ready.424242").exists())
        outcome = json.loads(outcome_path.read_bytes().splitlines()[-1])
        self.assertEqual(
            (outcome["schema"], outcome["reason_code"], outcome["message"]),
            ("forge-cli/2", "ok", "forge: common rebase lock released"),
        )

    def test_protocol_early_exit_releases_without_a_frame(self) -> None:
        """Exiting the lock-owning shell closes the release pipe and the wrapper releases."""
        completed, common, outcome_path = self._run_protocol(send_release=False)
        self.assertEqual(completed.returncode, 7, completed.stderr)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and (
            self._owner_artifacts(common) or not outcome_path.exists()
            or not outcome_path.read_bytes().strip()
        ):
            time.sleep(0.2)
        self.assertEqual(self._owner_artifacts(common), [])
        outcome = json.loads(outcome_path.read_bytes().splitlines()[-1])
        self.assertEqual(outcome["reason_code"], "state-precondition")
        self.assertEqual(outcome["message"], "forge: common-lock hold refused — invalid release frame")

    def test_protocol_deadlocks_without_closing_the_inherited_descriptor(self) -> None:
        """Disable proof: the `9>&-` is load-bearing (iteration-1 CRITICAL)."""
        setup, start, release = self._lock_blocks()
        self.assertIn(" 9>&- &", start)
        weakened = start.replace(" 9>&- &", " &")
        temporary = Path(tempfile.mkdtemp(prefix="forge-wtm-weakened-"))
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", str(temporary)], check=False))
        init_quiet_repository(temporary, "-q", environment=GIT_TEST_ENV).check_returncode()
        environment = dict(GIT_TEST_ENV)
        environment.update({"CLAUDE_PLUGIN_ROOT": str(ROOT), "FORGE_SESSION_PID": "424243"})
        # The skill's own bounded release wait reports the hang; shorten only
        # its bound so the proof runs quickly, then reap the stuck holder.
        bounded_release = release.replace('-lt 60 ]', '-lt 3 ]')
        self.assertNotEqual(bounded_release, release)
        bounded_release += '\n'
        script = "\n".join((setup, weakened, bounded_release)) + (
            '\nexit 0\n'
        )
        script = script.replace(
            '  exit 1\nfi\nwait "$LOCK_HOLDER_PID"',
            '  kill "$LOCK_HOLDER_PID"; exit 1\nfi\nwait "$LOCK_HOLDER_PID"',
        )
        completed = subprocess.run(
            ["bash", "-c", script],
            cwd=temporary, env=environment, capture_output=True, text=True, timeout=90,
        )
        self.assertEqual(completed.returncode, 1, completed.stderr)
        self.assertIn("lock-release-failed: holder still running after 60 s", completed.stderr)

    def test_protocol_reports_lock_release_failed_on_a_bad_release_outcome(self) -> None:
        """A release the wrapper refuses is a failed merge step, never a silent success."""
        setup, start, release = self._lock_blocks()
        mutant = release.replace("printf 'release\\n' >&9", "printf 'release' >&9")
        self.assertNotEqual(mutant, release)
        temporary = Path(tempfile.mkdtemp(prefix="forge-wtm-badrelease-"))
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", str(temporary)], check=False))
        init_quiet_repository(temporary, "-q", environment=GIT_TEST_ENV).check_returncode()
        common = Path(
            run_git(
                temporary, "rev-parse", "--path-format=absolute", "--git-common-dir"
            ).stdout.strip()
        )
        environment = dict(GIT_TEST_ENV)
        environment.update({"CLAUDE_PLUGIN_ROOT": str(ROOT), "FORGE_SESSION_PID": "424245"})
        completed = subprocess.run(
            ["bash", "-c", "\n".join((setup, start, mutant, "echo unreachable >&2\n"))],
            cwd=temporary, env=environment, capture_output=True, text=True, timeout=90,
        )
        self.assertEqual(completed.returncode, 1, completed.stderr)
        self.assertIn("lock-release-failed", completed.stderr)
        self.assertNotIn("unreachable", completed.stderr)
        outcome = json.loads(
            (temporary / ".forge/tmp/rebase-lock-outcome.424245.json").read_bytes().splitlines()[-1]
        )
        self.assertEqual(outcome["message"], "forge: common-lock hold refused — invalid release frame")
        # The wrapper still released the owner on its refusal path.
        self.assertEqual(self._owner_artifacts(common), [])

    def test_protocol_refuses_loudly_on_a_dead_owner(self) -> None:
        """A planted dead owner makes the wrapper refuse; the skill stops within one slice."""
        setup, start, _release = self._lock_blocks()
        temporary = Path(tempfile.mkdtemp(prefix="forge-wtm-deadowner-"))
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", str(temporary)], check=False))
        init_quiet_repository(temporary, "-q", environment=GIT_TEST_ENV).check_returncode()
        common = Path(
            run_git(
                temporary, "rev-parse", "--path-format=absolute", "--git-common-dir"
            ).stdout.strip()
        )
        environment = dict(GIT_TEST_ENV)
        environment.pop("FORGE_SESSION_PID", None)
        # Plant the dead owner: hold the lock in one wrapper and SIGKILL it.
        ready_read, ready_write = os.pipe()
        holder = subprocess.Popen(
            [
                sys.executable, str(ROOT / "scripts/forge/cli.py"), "--json", "--repo", str(temporary),
                "common-lock", "hold", "--owner-kind", "push", "--operation", "push",
                "--ready-fd", str(ready_write),
            ],
            cwd=temporary, env=environment, stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, pass_fds=(ready_write,),
        )
        os.close(ready_write)
        with os.fdopen(ready_read, "rb") as ready_stream:
            self.assertTrue(ready_stream.readline())
        holder.kill()
        holder.wait(timeout=10)
        self.assertEqual(self._owner_artifacts(common), ["agent-rebase.lock.intent", "agent-rebase.lockdir"])
        environment.update({"CLAUDE_PLUGIN_ROOT": str(ROOT), "FORGE_SESSION_PID": "424244"})
        started = time.monotonic()
        completed = subprocess.run(
            ["bash", "-c", "\n".join((setup, start, "echo unreachable >&2\nexit 0\n"))],
            cwd=temporary, env=environment, capture_output=True, text=True, timeout=90,
        )
        elapsed = time.monotonic() - started
        self.assertEqual(completed.returncode, 1, completed.stderr)
        self.assertLess(elapsed, 40.0)
        self.assertIn("forge: rebase lock unavailable (holder hint:", completed.stderr)
        self.assertIn('"schema":"forge-cli/2"', completed.stderr)
        self.assertNotIn("unreachable", completed.stderr)
        # The skill created and removed no owner artifact of its own.
        self.assertEqual(self._owner_artifacts(common), ["agent-rebase.lock.intent", "agent-rebase.lockdir"])

    def test_init_skill_reports_the_arbiter_not_a_mkdir_fallback(self) -> None:
        init = (ROOT / "skills/init/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("command -v flock", init)
        self.assertIn("`${GIT_COMMON_DIR}/agent-rebase.lockdir` (with `agent-rebase.lock.intent`)", init)
        self.assertIn("The owner directory is not a disposable mutex", init)
        self.assertIn("portable arbiter alone is the complete lock", init)
        self.assertIn("through Python's `fcntl.flock`", init)
        self.assertIn("The `command -v flock` probe is\n   informational only", init)
        self.assertNotIn("atomic `mkdir`", init)
        self.assertNotIn("Missing both lock mechanisms", init)
        self.assertNotIn("when `flock` exists", init)
        self.assertIn("the `flock` binary is irrelevant to the wrapper", SKILL)

    def test_every_in_lock_fenced_command_closes_the_lock_descriptors(self) -> None:
        """Revision 13 (9qf.7): children of the lock epoch must not inherit the lock pipes."""
        section = SKILL.split("## Locked rebase reintegration", maxsplit=1)[1].split(
            "## Cleanup after successful push", maxsplit=1
        )[0]
        fences = re.findall(r"```bash\n(.*?)```", section, flags=re.S)
        start_index = next(i for i, block in enumerate(fences) if "common-lock hold" in block)
        release_index = next(i for i, block in enumerate(fences) if "printf 'release" in block)
        in_lock = fences[start_index + 1:release_index]
        self.assertGreaterEqual(len(in_lock), 3)
        commands = []
        for block in in_lock:
            joined = re.sub(r"\\\n\s*", " ", block)
            for line in joined.splitlines():
                if re.search(r"(^|[\s(\$])(git|python3)\s", line):
                    commands.append(line)
        self.assertGreaterEqual(len(commands), 6)
        for line in commands:
            with self.subTest(command=line.strip()):
                self.assertIn("8<&- 9>&-", line)
        self.assertIn("git push origin HEAD:<default-branch> 8<&- 9>&-", SKILL)
        self.assertIn("`git rebase --continue 8<&- 9>&-`", SKILL)
        self.assertNotIn("fast-forward the candidate with exactly:", SKILL)

    def test_skill_issues_no_legacy_lock_mechanism(self) -> None:
        """The retired flock/mkdir mechanisms would collide with the arbiter's namespace."""
        lock_section = SKILL.split("## Locked rebase reintegration", maxsplit=1)[1]
        for legacy in (
            "flock --timeout",
            "flock -u",
            "LOCK_KIND",
            "agent-rebase.lock\"",
            "until mkdir",
            "rmdir \"$LOCK_DIR\"",
            "trap 'rmdir",
        ):
            with self.subTest(legacy=legacy):
                self.assertNotIn(legacy, lock_section)
        self.assertNotIn("$LOCK_DIR", SKILL)
        self.assertNotIn("$LOCK_FILE", SKILL)

    def test_reverification_cleanup_and_record_authority(self) -> None:
        self.assertIn(
            "If `DEFAULT_ADVANCED=1` or `CANDIDATE_REWRITTEN=1`, re-run Gate 1 and Gate 2",
            SKILL,
        )
        self.assertIn("If conflicts were resolved, Gate 3 is mandatory", SKILL)
        self.assertIn("If `CANDIDATE_REWRITTEN=1` without conflicts", SKILL)
        self.assertIn("pure fast-forward", SKILL)
        self.assertIn("git merge-base --is-ancestor", SKILL)
        self.assertIn(
            'git -C "$MAIN_WORKTREE" worktree remove "$WORKTREE_DIR"', SKILL
        )
        self.assertIn("worktree removal failed — branch preserved", SKILL)
        self.assertIn("failed to release rebase lock — lock-release-failed (holder hint:", SKILL)
        cleanup = SKILL.split("## Cleanup after successful push", maxsplit=1)[1].split(
            "## Record authority and report", maxsplit=1
        )[0]
        self.assertNotIn("--force", cleanup)
        self.assertIn("agent handoff and claimed gate result as a claim", SKILL)
        self.assertIn("integration target, not in the agent's worktree", SKILL)

    def test_cleanup_proofs_survive_static_mutation(self) -> None:
        assert_cleanup_contract(self, SKILL)
        controls = (
            'git fetch origin "$DEFAULT_BRANCH" --quiet || {',
            'git merge-base --is-ancestor "$PUSHED_HEAD"',
            '[ "$WORKTREE_BRANCH" = "refs/heads/${BRANCH}" ]',
            '[ "$WORKTREE_HEAD" = "$CURRENT_BRANCH_TIP" ]',
            '[ -z "$WORKTREE_STATUS" ]',
            'git -C "$MAIN_WORKTREE" worktree remove "$WORKTREE_DIR" || {',
            '[ "$DELETE_BRANCH_TIP" = "$CURRENT_BRANCH_TIP" ]',
            'git -C "$MAIN_WORKTREE" update-ref -d',
            '"refs/heads/$BRANCH" "$DELETE_BRANCH_TIP"',
            'cd "$MAIN_WORKTREE" || {',
        )
        for fragment in controls:
            with self.subTest(disabled=fragment), self.assertRaises(AssertionError):
                assert_cleanup_contract(self, SKILL.replace(fragment, "DISABLED_CONTROL", 1))

    def test_cleanup_block_executes_in_scratch_repositories(self) -> None:
        clean = run_cleanup_case("clean")
        self.assertEqual(clean.process.returncode, 0, clean.process.stderr)
        self.assertFalse(clean.worktree_exists)
        self.assertIsNone(clean.branch_tip)
        for scenario in ("unpushed", "untracked", "modified", "detached"):
            with self.subTest(scenario=scenario):
                assert_cleanup_refused(self, run_cleanup_case(scenario), scenario)

    def test_cleanup_refusal_exit_mutations_destroy_preservation(self) -> None:
        cases = (
            ("unpushed", "pushed candidate is not contained in"),
            ("modified", "worktree is not clean"),
            ("detached", "worktree branch is unavailable"),
        )
        for scenario, phrase in cases:
            diagnostic = next(
                line.split('echo "', 1)[1].split('" >&2', 1)[0]
                for line in SKILL.splitlines()
                if phrase in line and 'echo "' in line
            )
            mutant = weaken_refusal_exit(SKILL, diagnostic)
            outcome = run_cleanup_case(scenario, skill=mutant)
            with self.subTest(scenario=scenario), self.assertRaises(AssertionError):
                assert_cleanup_refused(self, outcome, scenario)

    def test_name_only_listings_disable_rename_detection(self) -> None:
        assert_rename_listing_contract(self, SKILL)
        for label, mutant in rename_listing_mutants(SKILL):
            with self.subTest(control=label), self.assertRaises(AssertionError):
                assert_rename_listing_contract(self, mutant)
        scratch = tempfile.TemporaryDirectory(prefix="forge-wtm-renames-")
        self.addCleanup(scratch.cleanup)
        repo = Path(scratch.name)
        seed_rename_repo(repo)
        diff_args = (
            "diff",
            "--no-renames",
            "--no-ext-diff",
            "--no-textconv",
            "--name-only",
            "HEAD~1...HEAD",
        )
        self.assertCountEqual(
            run_git(repo, *diff_args).stdout.splitlines(),
            ["skills/x.md", "docs-x.md"],
        )
        rename_enabled = run_git(
            repo,
            "-c",
            "diff.renames=true",
            diff_args[0],
            *diff_args[2:],
        )
        self.assertEqual(rename_enabled.stdout.splitlines(), ["docs-x.md"])

    def test_unsafe_bulk_stage_commands_are_absent(self) -> None:
        self.assertNotIn("git add .", SKILL)
        self.assertNotIn("git add -A", SKILL)


if __name__ == "__main__":
    unittest.main()
