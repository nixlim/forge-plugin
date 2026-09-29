"""Revision-17 typed-launch specification controls and disable legs."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = (ROOT / "docs/specs/forge-plugin-spec.md").read_text(encoding="utf-8")

MARKER_KEYS = (
    "`schema`, `run_id`, `task`, `agent`, `execution`, `attempt`, `role`, "
    "`provider`, `model`, `effort`, `sandbox`, `route_source`, `route_sha256`, "
    "`worktree`, `head`, `plugin_root`, `role_body_path`, `role_body_sha256`, "
    "`argv_digest`, `prompt_digest`, `launcher_argv_digest`, `timeout_seconds`, "
    "`environment_names`, `omitted_short`, `requested_at`, `collected_at`, and "
    "`collected_status`"
)
IMPLEMENTER_CELL = (
    "claude -p --safe-mode --strict-mcp-config --output-format stream-json --verbose "
    "--model <m> --effort <e> --append-system-prompt-file "
    "<plugin>/system/claude/prompts/implementer.md --tools "
    '"Read,Write,Edit,Bash,Grep,Glob" --permission-mode acceptEdits '
    '--allowedTools "Bash" --permission-prompts none --no-session-persistence'
)
PLAN_CELL = (
    "claude -p --safe-mode --strict-mcp-config --output-format stream-json --verbose "
    "--model <m> --effort <e> --system-prompt-file "
    '<plugin>/system/claude/prompts/plan.md --tools "Read,Grep,Glob" '
    "--permission-prompts none --no-session-persistence"
)
PROFILE_SENTENCE = (
    "The Claude implementer and plan cells also run with "
    "`--no-session-persistence`; the implementer retains "
    '`--permission-mode acceptEdits` and `--allowedTools "Bash"`, while the plan '
    "cell exposes only `Read,Grep,Glob` with no Bash, write tool, or permission bypass."
)
INVENTORY_LITERAL = (
    "`scripts/forge/route_floor.py` is the non-executable, interpreter-invoked "
    "CLI version-floor helper"
)

CONTROLS = {
    "FR-034": (
        "Revision-17 typed-launch amendment to **FR-034**:",
        "FR-210's subcommands gain the run-scoped, unserialized surfaces",
        "`launch --role implementer|plan --task <task-id> --worktree <abs> "
        "--brief <abs>`",
        "`launch collect --execution <execution-NN>`",
        "`launch cancel --execution <execution-NN>`",
        "all three require explicit global `--repo <abs>` and `--run-id <run>`",
        "forge: launch refused — explicit --repo and --run-id are required",
        "forge: launch refused — --chain-id is not admitted",
        "forge: launch refused — --role, --task, --worktree and --brief are "
        "required, and --execution is not admitted",
        "forge: launch <collect|cancel> refused — exactly --execution execution-NN "
        "is required",
        "Before creating any directory, file, or record, start performs in order",
        "forge: launch refused — worktree is not a registered worktree of this "
        "repository: <path>",
        "forge: launch refused — implementer worktree must be a dedicated linked "
        "worktree: <path>",
        "forge: forge initialization incomplete — run /forge:init",
        "forge: journal builder refused — task <task> is not active",
        "forge: launch refused — brief path is not canonical; pass its absolute "
        "realpath",
        "forge: launch refused — opened brief path could not be verified against "
        "the checked canonical path",
        "forge: launch refused — brief must be a canonical absolute owner-owned "
        "regular UTF-8 file writable only by its owner or owner-private group, with "
        "no NUL byte and size at most 1 MiB",
        "the caller path is canonical only when it is absolute and equals its strict "
        "filesystem realpath",
        '"Owner-controlled" means a regular file whose `st_uid == os.geteuid()` and '
        "whose world-write bit is unset",
        "Group write is admitted only when the file GID is the owner's consistently "
        "enumerable primary group",
        "every explicit member name resolves to that same UID, no different UID has "
        "that GID as its primary group, and no access ACL may widen writes",
        "opens the canonical leaf with `O_NOFOLLOW` and `O_NONBLOCK`, obtains the "
        "opened descriptor's real path through `/proc/self/fd/<fd>` on Linux or "
        "`fcntl(F_GETPATH)` on macOS",
        "requires exact equality with the already-checked canonical caller path",
        "unavailable Linux procfs or macOS `F_GETPATH`, or any other platform fails "
        "closed with the opened-brief-path refusal",
        "does not claim an inode identity captured before `open`; same-path "
        "replacement remains subject to the opened descriptor's owner, mode, type, "
        "and size controls",
        "forge: execution refused — route diverges from run snapshot for <role>: "
        "<field>",
        "forge: execution refused — role <role> has no frozen route in the run snapshot",
        "forge: <provider> launch refused — <provider> CLI could not be started",
        "forge: launch refused — execution <execution-NN> is still in flight in "
        "<worktree>; run launch collect or launch cancel",
        "forge: launch refused — <provider> executable is unavailable: <executable>",
        "forge: launch refused — <provider> version probe timed out after 10 s",
        "forge: launch refused — <provider> version probe output exceeded 4096 bytes",
        "forge: launch refused — <provider> version probe failed with exit <n>",
        "forge: launch refused — <provider> version output is unparseable",
        "forge: launch refused — <provider> version <x.y.z> is below required <floor>",
        "this is FR-036's required order",
        "attempt-[0-9a-f]{16}",
        "mode: detached",
        "launch_marker: <agent>/<execution>/launch.json",
        "schema: forge-launch-idempotency/1",
        "step: execution-start",
        "step: execution-result",
        "FR-037 prompt assembly is provider-specific but byte-stable",
        "Claude stdin starts with the exact bytes `\\n--- committed "
        "agent-project-context ---\\n`",
        "forge: launch refused — committed prompt inputs unavailable at <head>",
        "The FR-030 inline tuples remain the committed defaults",
        "schema `forge-launch-marker/1` and exactly the keys",
        MARKER_KEYS,
        "leaves: {prompt: prompt.md, events: events.jsonl, stderr: stderr.log, "
        "capture: handoff.md, staging: handoff.staging}",
        "`events_existing: true`, and `role_body_digest: null`",
        "implementer timeout is 14400 seconds and plan timeout is 1200 seconds",
        "redacts it exactly as the review lane redacts verdicts",
        "Launch completions reuse `forge-review-process/2` unchanged",
        "`verdict_digest` and `verdict_size` bind the handoff",
        "forge launch collect --repo <repo> --run-id <run> --execution <execution-NN>",
        "launch-failed: errno <n>",
        "launch-failed: spawn error",
        "launch collect: <complete|failed>; returncode <n|none>; error <error|none>; "
        "timed_out <true|false>; handoff <n> bytes; observed_model <id|none>",
        "The two NUL-delimited Git path listings share one 1-MiB output budget",
        "forge: launch collect refused — worktree paths are not UTF-8 for "
        "<execution-NN>; restore changed tracked paths or rename/remove untracked "
        "paths, then retry launch collect",
        "forge: launch collect refused — worktree path list exceeds 1 MiB for "
        "<execution-NN>; reduce changed or untracked paths, then retry launch collect",
        "a repeat returns the recorded status without a second result",
        "forge: journal builder refused — execution result does not match one "
        "open execution",
        "forge: launch collect refused — execution <execution-NN> has no "
        "launch_marker; collect a prose launch by prose",
        "forge: launch collect refused — launch marker does not bind execution "
        "<execution-NN>: <field>",
        "forge: launch collect refused — attempt record is invalid for "
        "<execution-NN>: <detail>",
        "forge: launch collect refused — completion does not bind execution "
        "<execution-NN>: <field>",
        "forge: launch collect refused — worktree facts unavailable for <execution-NN>",
        "Launch-lane recovery is exhaustive",
        "`Clear` means, in order: exclusively publish the terminal completion only "
        "once the wrapper can no longer publish; write a failed terminal "
        "`execution_result`; then set the marker's `collected_at` and `collected_status`",
        "forge: launch collect refused — execution <execution-NN> is still "
        "launching; retry after the identity deadline",
        "collect re-observes rather than guessing",
        "forge: launch collect refused — execution <execution-NN> is still running",
        "forge: launch collect refused — wrapper-dead / child-alive for "
        "<execution-NN>; run launch cancel --repo <repo> --run-id <run> --execution "
        "<execution-NN>",
        "`events cap`, `stderr cap`, `bad line N`, `provider exit N`, `claude result "
        "error`, `redaction damaged <field>`, `wrapper failure`, `verdict missing`, "
        "`verdict empty`, `verdict cap`, `verdict invalid`",
        "`not-logged-in`",
        "forge: launch cancel refused — execution <execution-NN> has no launch_marker",
        "forge: launch cancel refused — execution <execution-NN> already has a "
        "completion or a terminal result; run launch collect",
        "forge: launch cancel refused — execution <execution-NN> has no wrapper "
        "identity yet; run launch collect",
        "holds the attempt publication lock from its identity re-read through "
        "exclusive completion publication",
        "forge: launch cancel refused — attempt publication lock was not acquired "
        "for <execution-NN>",
        "An abandonment-claim identity whose `wrapper_pid` is null calls the shared "
        "`claim_abandoned`",
        "a winning claim publishes `abandoned`, while a wrapper that won the identity "
        "claim routes cancel to collect",
        "forge: launch cancel refused — kill-unconfirmed for <execution-NN>: <pids>",
        "forge: launch cancel refused — unexpected group proof <outcome> for "
        "<execution-NN>",
        "Immediately before publication cancel re-reads `identity.json`",
        "`attempt`, `wrapper_pid`, `pgid`, and `wrapper_birth` MUST be unchanged",
        "a change to `reviewer_pid`, `reviewer_birth`, or `started_at` repeats "
        "ownership proof against the refreshed identity",
        "If the wrapper publishes a different completion first, cancel validates it "
        "and routes to collect",
        "forge: launch collect refused — identity-unproven for <execution-NN>; "
        "member PIDs <pids>; recorded PGID <pgid>; nothing was signalled",
        "forge: launch cancel refused — identity-unproven for <execution-NN>; "
        "member PIDs <pids>; recorded PGID <pgid>; nothing was signalled",
        "forge: execution refused — role <role> carries no route fields in a run "
        "with a route snapshot",
    ),
    "FR-080": (
        "Revision-17 init-probe amendment to **FR-080**:",
        "rev-parse --verify --quiet 'HEAD^{commit}'",
        'scripts/forge/route_config.py\" init --repo \"$REPO_ROOT\"',
        'scripts/forge/route_floor.py\" --repo \"$REPO_ROOT\"',
        'scripts/forge/route_config.py\" probe --repo \"$REPO_ROOT\"',
        "forge: init stopped — the current branch has no commit yet; make a first "
        "commit, then re-run /forge:init",
        "forge: route init refused — routes file already exists",
        "forge: route floor refused — <provider> executable is unavailable: <executable>",
        "forge: route floor refused — <provider> version probe timed out after 10 s",
        "forge: route floor refused — <provider> version probe output exceeded 4096 bytes",
        "forge: route floor refused — <provider> version probe failed with exit <n>",
        "forge: route floor refused — <provider> version output is unparseable",
        "forge: route floor refused — <provider> version <x.y.z> is below required <floor>",
        "does not activate the FR-083 headless-init amendment or the FR-183 "
        "init-review amendment",
    ),
    "DM-018": (
        "Revision-17 typed-launch amendment to **DM-018** (2026-09-28):",
        "this amendment supersedes the earlier chain-I parenthetical that placed "
        "process identity in `launch.json`",
        "wrapper and child identity remain only in the attempt-keyed `identity.json`",
        "`launch collect` binds that identity to the marker through `attempt`",
        "owner-only `forge-launch-marker/1` object has exactly",
        MARKER_KEYS,
        "`attempt` is `attempt-` plus sixteen lowercase hexadecimal characters",
        "the two environment arrays contain sorted names and never values",
        "`requested_at` is a parseable UTC-Z timestamp and never null",
        "`collected_at` and `collected_status` are initially null and thereafter are "
        "either both null or respectively a parseable UTC-Z timestamp and exactly "
        "`complete` or `failed`",
        "forge: journal append refused — invalid journal record: "
        "execution.launch_marker must equal <agent>/<execution>/launch.json and "
        "requires the route trio and mode detached",
        "forge: execution refused — role <role> carries no route fields in a run "
        "with a route snapshot",
        "historical replay remains accepted",
    ),
    "FR-245": (
        "chain I supplies the deferred implementer and plan cells",
        IMPLEMENTER_CELL,
        PLAN_CELL,
        PROFILE_SENTENCE,
        "Fixed profile timeouts are review 2400 seconds, implementer 14400 seconds, "
        "and plan 1200 seconds",
    ),
}

ORDERED_CONTROLS = (
    (
        "FR-034",
        (
            "the halt check",
            "registered-worktree and dedicated linked-worktree check for an implementer",
            "HEAD and committed `init_completed: true` check",
            "active-task check",
            "canonical-realpath, owner-controlled, no-follow-leaf, regular UTF-8, "
            "NUL-free, at-most-1-MiB brief check",
            "route resolution and sandbox selection",
            "committed-prompt-input read",
            "snapshot and proposed-record validation",
            "executable lookup",
            "provider version-floor check",
            "same-worktree in-flight check",
        ),
    ),
    (
        "FR-034",
        (
            "creates the agent directory when absent and the owner-only execution "
            "directory exclusively",
            "writes owner-only `prompt.md`",
            "creates an empty owner-only `events.jsonl`",
            "opens the execution directory through its inherited owner-controlled "
            "descriptor",
            "builds the wrapper configuration",
            "atomically writes and fsyncs `launch.json`",
            "only then appends the `execution` owner record",
        ),
    ),
    (
        "FR-080",
        (
            "rev-parse --verify --quiet 'HEAD^{commit}'",
            'scripts/forge/route_config.py" init --repo "$REPO_ROOT"',
            'scripts/forge/route_floor.py" --repo "$REPO_ROOT"',
            'scripts/forge/route_config.py" probe --repo "$REPO_ROOT"',
        ),
    ),
)


def requirement_block(text: str, requirement_id: str) -> str:
    pattern = re.compile(rf"(?m)^(?:- )?\*\*{re.escape(requirement_id)}\*\*")
    match = pattern.search(text)
    if match is None:
        raise AssertionError(f"{requirement_id} heading missing")
    remainder = text[match.end() :]
    boundary = re.search(r"(?m)^(?:(?:- )?\*\*(?:FR|DM)-\d{3}\*\*|## )", remainder)
    return text[match.start() : match.end() + (boundary.start() if boundary else len(remainder))]


def assert_typed_launch_controls(text: str) -> None:
    for requirement_id, literals in CONTROLS.items():
        block = requirement_block(text, requirement_id)
        for literal in literals:
            if literal not in block:
                raise AssertionError(f"{requirement_id} lacks {literal}")
    for requirement_id, literals in ORDERED_CONTROLS:
        block = requirement_block(text, requirement_id)
        positions = [block.index(literal) for literal in literals]
        if positions != sorted(positions):
            raise AssertionError(f"{requirement_id} controls are out of order")
    heading = requirement_block(text, "FR-245").splitlines()[0]
    if re.search(r"\(Revision 15 authority; [^)]*deferred[^)]*\)", heading):
        raise AssertionError("FR-245 retains its chain-I deferral marker")
    if INVENTORY_LITERAL not in text:
        raise AssertionError("inventory lacks route_floor.py")


def remove_from_block(text: str, requirement_id: str, literal: str) -> str:
    block = requirement_block(text, requirement_id)
    if literal not in block:
        raise AssertionError(f"{requirement_id} fixture lacks {literal}")
    return text.replace(block, block.replace(literal, ""), 1)


class TypedLaunchSpecificationTests(unittest.TestCase):
    def test_typed_launch_amendments_and_profiles_are_pinned(self) -> None:
        assert_typed_launch_controls(SPEC)

    def test_each_typed_launch_control_is_load_bearing(self) -> None:
        for requirement_id, literals in CONTROLS.items():
            for literal in literals:
                with self.subTest(requirement=requirement_id, literal=literal):
                    mutant = remove_from_block(SPEC, requirement_id, literal)
                    with self.assertRaisesRegex(AssertionError, requirement_id):
                        assert_typed_launch_controls(mutant)

    def test_each_control_order_is_load_bearing(self) -> None:
        for requirement_id, literals in ORDERED_CONTROLS:
            block = requirement_block(SPEC, requirement_id)
            first, second = literals[:2]
            swapped = block.replace(first, "ORDER-SENTINEL", 1)
            swapped = swapped.replace(second, first, 1).replace("ORDER-SENTINEL", second, 1)
            with self.subTest(requirement=requirement_id):
                with self.assertRaisesRegex(AssertionError, "out of order"):
                    assert_typed_launch_controls(SPEC.replace(block, swapped, 1))

    def test_fr245_deferral_reinsertion_is_detected(self) -> None:
        mutant = SPEC.replace(
            "**FR-245** (MUST): Provider profiles.",
            "**FR-245** (MUST): Provider profiles "
            "(Revision 15 authority; implementer and plan cells deferred to chain I).",
            1,
        )
        with self.assertRaisesRegex(AssertionError, "FR-245"):
            assert_typed_launch_controls(mutant)

    def test_route_floor_inventory_control_is_load_bearing(self) -> None:
        with self.assertRaisesRegex(AssertionError, "inventory"):
            assert_typed_launch_controls(SPEC.replace(INVENTORY_LITERAL, "", 1))


if __name__ == "__main__":
    unittest.main()
