"""Behavior contracts for routed-launch skill prose."""

from __future__ import annotations

import shlex
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/forge"))

from forge_cli.engine import _cli_options, _parser  # noqa: E402

SKILL = (ROOT / "skills/orchestrate/SKILL.md").read_text(encoding="utf-8")
MONITORING = (
    ROOT / "skills/orchestrate/references/monitoring.md"
).read_text(encoding="utf-8")
DOCUMENTS = (SKILL, MONITORING)
DISABLED_CONTROL = "DISABLED_CONTROL"

START_IMPLEMENTER = (
    "forge launch --repo <repo> --run-id <run-id> --role implementer --task <task-id> "
    "--worktree <absolute-worktree> --brief <absolute-brief>"
)
START_PLAN = (
    "forge launch --repo <repo> --run-id <run-id> --role plan --task <task-id> "
    "--worktree <absolute-worktree> --brief <absolute-brief>"
)
COLLECT = (
    "forge launch collect --repo <repo> --run-id <run-id> "
    "--execution <execution-NN>"
)
CANCEL = (
    "forge launch cancel --repo <repo> --run-id <run-id> "
    "--execution <execution-NN>"
)
CANONICAL_COMMANDS = (START_IMPLEMENTER, START_PLAN, COLLECT, CANCEL)
PLACEHOLDERS = {
    "<repo>": "/abs/repo",
    "<run-id>": "run-x",
    "<task-id>": "task-01",
    "<absolute-worktree>": "/abs/wt",
    "<absolute-brief>": "/abs/b.md",
    "<execution-NN>": "execution-01",
}
OUTSIDE_ROUTE = (
    "if it carries any of `sandbox`, `route_source`, or `route_sha256`, it must "
    "carry all three, equal to that role's frozen run snapshot"
)
SKILL_CONTROLS = (
    "# Forge Focused Orchestration",
    "Use this skill, not the upstream codex-orchestrator orchestrate skill",
    "whenever a Forge-governed repository",
    "Codex `gpt-5.6-sol` / `high` / `read-only` | session, by the procedure",
    "Forge review engine (`forge review request` / `forge review collect`)",
    "never hand-substitute provider flags for those roles",
    "Put this sentence verbatim in every implementer brief",
    "You may commit inside this worktree. You must NEVER push, never touch any "
    "branch other than your own, and never run destructive git commands.",
    "a canonical absolute owner-owned regular file writable only by its owner or "
    "owner-private group, UTF-8 without NUL bytes, at most 1 MiB",
    "Resolve it to its filesystem realpath after writing it and pass that exact "
    "canonical spelling",
    "forge: launch refused — brief path is not canonical; pass its absolute realpath",
    "Keep the brief outside the target worktree",
    "collect reports every untracked worktree path in `files_changed`",
    '`forge` is `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/forge/cli.py"',
    "successful start receipt reads `launch started for execution-NN`",
    "Create the agent directory when absent and the owner-only `execution-NN` "
    "directory",
    OUTSIDE_ROUTE,
    "completion.json` when the provider exits or hits its fixed timeout",
    "implementer 14400 seconds, plan 1200 seconds",
    "non-blocking poll for that file, bounded at 60 minutes",
    'bash "${CLAUDE_PLUGIN_ROOT}/scripts/forge/check-halt.sh"',
    "checks only the shared global `AGENT_HALT` sentinel before every start, "
    "collect, and cancel",
    "all three verbs refuse with reason code `halt-engaged`",
    "on a halt do not invoke `forge launch collect` or `forge launch cancel`",
    "fresh implementer or planner only through `forge launch`",
    "Write the brief, resolve it to its absolute filesystem realpath, then pass the "
    "absolute worktree and canonical brief path to `forge launch`",
    "saves the exact prompt and appends `execution` before launch",
    "owner record carries no `branch` field",
    "git -C <worktree> branch --show-current",
    "never append an `execution_result` for a typed execution by hand",
    "before reading typed-launch artifacts on disk",
    "before verifying a handoff or starting a first-pass reviewer",
    "when Claude and an agent disagree or a decision outcome is recorded",
    "before running tasks in parallel or creating worktrees",
)
MONITOR_CONTROLS = (
    "## Launching And Collecting Executions",
    "commands, the outcome table, and the prompt layout are canonical",
    "provider streams, capped at 16 MiB and 1 MiB",
    "`launch.json` is the owner-only `forge-launch-marker/1`",
    "`completion.json` appearing is the wake signal",
    "For Codex, `prompt.md` and stdin start with the applicable plugin role template",
    "Claude `prompt.md` and stdin start with the exact bytes",
    "Both committed inputs come from the recorded absolute worktree at its committed HEAD",
    OUTSIDE_ROUTE,
    "typed Codex and typed Claude launches only when their owner record names a "
    "stream-JSON `events` file",
    "Subagent-mode Claude records have no events file and are not monitor targets",
    "`forge launch collect` and `forge launch cancel` remain the only lifecycle "
    "authorities",
    "After collect, confirm that `handoff.md` carries these headings in order",
    "create the reviewer's next execution directory, write `prompt.md`",
    '`bash "${CLAUDE_PLUGIN_ROOT}/scripts/forge/check-halt.sh"` to exit 0',
    "Never use `--ephemeral` or a harness-managed background task",
    "resume command has no `-C`",
    "While any reviewer prose session is in flight, re-arm the monitor no later "
    "than 60 minutes",
    "Treat `codex_agent_stale` as ambiguous",
    "check the events file mtime, read PID and PGID",
    "For `codex_agent_unknown`, inspect the actual event vocabulary",
    "Run any non-provider command whose runtime can exceed a session's patience",
    "Implementer and plan providers are launched only by `forge launch`",
    "a `still running` collect refusal is the liveness answer",
)
WORKFLOW_CONTROLS = (
    "Forge's end-to-end owner workflow for a governed repository run",
    "launch a fresh routed implementer through `forge launch`",
    "collect its result with `forge launch collect`",
    "independently verify the result",
)
OUTCOME_RULES = (
    (
        "any typed-lane refusal with reason code `halt-engaged`",
        "wait for the operator to clear global `AGENT_HALT`",
    ),
    (
        "launch collect: complete` or `launch collect: failed",
        "Terminal; the one result exists",
    ),
    ("is still launching; retry after the identity deadline", "Wait at least 60 seconds"),
    ("is still running", "Append nothing, do not relaunch"),
    ("wrapper-dead / child-alive", "Run the named `forge launch cancel`"),
    ("identity-unproven", "Signal nothing yourself"),
    ("pid sidecar unavailable", "Run `forge launch collect`"),
    ("still in flight in <worktree>", "One typed execution per worktree"),
    ("journal batch-recover", "Run the named recovery before anything else"),
    ("initialization, version floor, not logged in, or route", "Stop and report"),
)
REVIEWER_PREPARATION_ORDER = (
    "create the reviewer's next execution directory",
    "write `prompt.md`",
    "create an empty `events.jsonl`",
    "append the `execution` entry with the recorded `session_id`",
    "then launch",
)
DURABLE_TREE_LINES = (
    ".codex-orchestrator/runs/<run-id>/",
    "  journal.jsonl",
    "  <provider>-<role>-<NN>/execution-<NN>/",
    "    prompt.md",
    "    events.jsonl",
    "    handoff.md",
    "    pid",
    "    stderr.log              # typed launches only",
    "    launch.json             # typed launches only",
    "    identity.json           # typed launches only",
    "    completion.json         # typed launches only",
    "  evidence/                 # optional",
    "  report.md                 # after the committed durable archive",
)
HANDOFF_HEADINGS = (
    "## Status",
    "## Summary",
    "## Files Changed",
    "## Claims / Findings",
    "## Commands Reported",
    "## Caveats / Blockers",
)


def _replace_placeholders(line: str) -> str:
    for placeholder, value in PLACEHOLDERS.items():
        line = line.replace(placeholder, value)
    return line


def _documented_commands(documents: tuple[str, ...]) -> list[str]:
    return [
        line.strip()
        for document in documents
        for line in document.splitlines()
        if line.strip().startswith("forge launch")
    ]


def _parse_command(line: str):
    argv = shlex.split(_replace_placeholders(line))[1:]
    options, remaining = _parser._extract_global_options(argv)
    args = _parser.build_parser().parse_args(remaining)
    _cli_options._validate_revision9_cross_options(options, args)
    return args


def _assert_canonical_commands(documents: tuple[str, ...]) -> None:
    corpus = "\n".join(documents)
    for command in CANONICAL_COMMANDS:
        if corpus.count(command) != 1:
            raise AssertionError(f"canonical command count changed: {command}")
    parsed = [_parse_command(line) for line in _documented_commands(documents)]
    pairs = {(args.launch_command, args.role) for args in parsed}
    expected = {
        (None, "implementer"),
        (None, "plan"),
        ("collect", None),
        ("cancel", None),
    }
    if pairs != expected:
        raise AssertionError(f"documented launch command set changed: {pairs!r}")


def _fenced_blocks(document: str) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    heading = ""
    body: list[str] | None = None
    block_heading = ""
    for line in document.splitlines():
        if line.startswith("#"):
            heading = line
        if line.startswith("```"):
            if body is None:
                body = []
                block_heading = heading
            else:
                blocks.append((block_heading, "\n".join(body)))
                body = None
            continue
        if body is not None:
            body.append(line)
    if body is not None:
        raise AssertionError("unterminated fenced block")
    return blocks


def _assert_controls(document: str, controls: tuple[str, ...]) -> None:
    document = " ".join(document.split())
    for control in controls:
        if control not in document:
            raise AssertionError(f"missing launch behavior: {control}")


def _assert_outcome_table(document: str) -> None:
    rows = [
        tuple(cell.strip() for cell in line.strip().strip("|").split("|"))
        for line in document.splitlines()
        if line.startswith("|") and "---" not in line
    ]
    for result, action in OUTCOME_RULES:
        if not any(result in cells[0] and action in cells[1] for cells in rows):
            raise AssertionError(f"missing outcome action: {result} -> {action}")


def _assert_reviewer_preparation_order(document: str) -> None:
    section = document.split(
        "### Reviewer-Only Confirmation Outside The Typed Lane", 1
    )[1].split("## Agent State And Monitor", 1)[0]
    section = " ".join(section.split())
    positions = [section.index(control) for control in REVIEWER_PREPARATION_ORDER]
    if positions != sorted(positions):
        raise AssertionError("reviewer preparation order changed")


def _assert_durable_tree(document: str) -> None:
    section = document.split("## Durable Run", 1)[1]
    blocks = _fenced_blocks(section)
    tree = blocks[0][1].splitlines()
    positions = [tree.index(line) for line in DURABLE_TREE_LINES]
    if positions != sorted(positions):
        raise AssertionError("durable-run tree order changed")


def _assert_handoff_headings(document: str) -> None:
    blocks = [body for _heading, body in _fenced_blocks(document) if "## Status" in body]
    if len(blocks) != 1:
        raise AssertionError("expected one canonical handoff block")
    headings = [line for line in blocks[0].splitlines() if line.startswith("## ")]
    if tuple(headings) != HANDOFF_HEADINGS:
        raise AssertionError("handoff headings changed")


class OrchestrateLaunchProseTests(unittest.TestCase):
    def test_documented_launch_commands_parse_and_are_canonical(self) -> None:
        _assert_canonical_commands(DOCUMENTS)
        for command in CANONICAL_COMMANDS:
            with self.subTest(command=command), self.assertRaises(AssertionError):
                mutant = tuple(
                    document.replace(command, DISABLED_CONTROL) for document in DOCUMENTS
                )
                _assert_canonical_commands(mutant)

    def test_reviewer_role_is_not_admitted_by_typed_launch(self) -> None:
        command = START_IMPLEMENTER.replace("implementer", "review-cheap")
        with self.assertRaises(_parser.Refusal):
            _parse_command(command)

    def test_provider_recipes_are_confined_to_reviewer_confirmation(self) -> None:
        self.assertFalse(
            [body for _heading, body in _fenced_blocks(SKILL) if "codex exec" in body]
        )
        recipes = [
            (heading, body)
            for heading, body in _fenced_blocks(MONITORING)
            if "codex exec" in body
        ]
        self.assertTrue(recipes)
        for heading, body in recipes:
            with self.subTest(heading=heading):
                self.assertEqual(
                    heading, "### Reviewer-Only Confirmation Outside The Typed Lane"
                )
                self.assertIn("resume <session-id> -", body)

    def test_launch_controls_are_behavioral_and_load_bearing(self) -> None:
        self.assertNotIn(
            "typed implementer and plan executions are observed only through",
            MONITORING.lower(),
        )
        self.assertNotIn("global or scoped halt", SKILL)
        self.assertNotIn(
            "read-only collection of an already-launched execution remains allowed",
            SKILL,
        )
        for document, controls in (
            (SKILL, SKILL_CONTROLS),
            (MONITORING, MONITOR_CONTROLS),
            (
                (ROOT / "skills/workflow/SKILL.md").read_text(encoding="utf-8"),
                WORKFLOW_CONTROLS,
            ),
        ):
            _assert_controls(document, controls)
            normalized = " ".join(document.split())
            for control in controls:
                with self.subTest(control=control), self.assertRaises(AssertionError):
                    _assert_controls(
                        normalized.replace(control, DISABLED_CONTROL), controls
                    )

    def test_every_typed_outcome_has_a_load_bearing_action(self) -> None:
        _assert_outcome_table(SKILL)
        for result, action in OUTCOME_RULES:
            for control in (result, action):
                with self.subTest(control=control), self.assertRaises(AssertionError):
                    _assert_outcome_table(SKILL.replace(control, DISABLED_CONTROL))

    def test_reviewer_preparation_order_is_load_bearing(self) -> None:
        _assert_reviewer_preparation_order(MONITORING)
        normalized = " ".join(MONITORING.split())
        for control in REVIEWER_PREPARATION_ORDER:
            with self.subTest(control=control), self.assertRaises(
                (AssertionError, ValueError)
            ):
                _assert_reviewer_preparation_order(
                    normalized.replace(control, DISABLED_CONTROL)
                )

    def test_durable_tree_classification_is_load_bearing(self) -> None:
        _assert_durable_tree(SKILL)
        for line in DURABLE_TREE_LINES:
            with self.subTest(line=line), self.assertRaises(
                (AssertionError, ValueError)
            ):
                _assert_durable_tree(SKILL.replace(line, DISABLED_CONTROL))

    def test_collected_handoff_shape_is_load_bearing(self) -> None:
        _assert_handoff_headings(MONITORING)
        for heading in HANDOFF_HEADINGS:
            with self.subTest(heading=heading), self.assertRaises(AssertionError):
                _assert_handoff_headings(
                    MONITORING.replace(heading, DISABLED_CONTROL)
                )

    def test_skill_descriptions_distinguish_focused_and_full_workflows(self) -> None:
        workflow = (ROOT / "skills/workflow/SKILL.md").read_text(encoding="utf-8")
        focused_description = SKILL.splitlines()[2]
        workflow_description = workflow.splitlines()[2]
        self.assertNotEqual(focused_description, workflow_description)
        self.assertIn("forge launch collect", focused_description)
        self.assertIn("end-to-end owner workflow", workflow_description)


if __name__ == "__main__":
    unittest.main()
