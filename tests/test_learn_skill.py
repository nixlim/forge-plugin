from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


def _flat(text: str) -> str:
    """Collapse whitespace so contract assertions test claims, not line wrapping."""
    return " ".join(text.split())



ROOT = Path(__file__).resolve().parents[1]
LEARN_PATH = ROOT / "skills" / "learn" / "SKILL.md"
WORKFLOW_PATH = ROOT / "skills" / "workflow" / "SKILL.md"
DRIFT_PATH = ROOT / "skills" / "drift" / "SKILL.md"
README_PATH = ROOT / "README.md"
PROJECT_PATH = ROOT / "forge-project.md"
PROJECT_TEMPLATE_PATH = ROOT / "system" / "template" / "forge-project.md"

LEARN = LEARN_PATH.read_text(encoding="utf-8")
WORKFLOW = WORKFLOW_PATH.read_text(encoding="utf-8")
DRIFT = DRIFT_PATH.read_text(encoding="utf-8")
README = README_PATH.read_text(encoding="utf-8")
PROJECT = PROJECT_PATH.read_text(encoding="utf-8")
PROJECT_TEMPLATE = PROJECT_TEMPLATE_PATH.read_text(encoding="utf-8")

INPUT_CONTROL_ANCHORS = (
    "Materialize the following three evidence inputs as three distinct files.",
    "Do not attach any other repository content, tool output, prior conversation, or\n"
    "working-tree file to the reviewer.",
    "unless `journal_patterns.available` is literally `true`",
    'git -C "$REPO" ls-tree -r --name-only "$INPUT_HEAD" -- .forge/history/runs/',
    '`git -C "$REPO" show "$INPUT_HEAD:$path"`; never read the worktree copy.',
    'git -C "$REPO" show "$INPUT_HEAD:.forge/history/gotchas.md"',
    "This explicit\nempty object is still the third input.",
    "Give it exactly `PATTERNS_FILE`, `ARCHIVES_FILE`, and `GOTCHAS_FILE` as its three\n"
    "separately named evidence inputs.",
    "profile `review-periodic`\nversion 1.1",
)

ARCHIVE_PROVENANCE_ANCHORS = (
    "Only an archive whose committed `content` contains one canonical JSON object between the exact\n"
    "`<!-- BEGIN FORGE LEARNING PROVENANCE v1 -->` and\n"
    "`<!-- END FORGE LEARNING PROVENANCE v1 -->` delimiters may supply proposal provenance.",
    "`decisions` as exact recorded `id`/`task` mappings",
    "`executions` as exact recorded\n"
    "`agent`/`execution`/`role`/`task`/`prompt`/`prompt_sha256` mappings",
    "`failed_or_inconclusive_verifications` as exact recorded\n"
    "`id`/`task`/`result`/`criterion`/`observation` mappings",
    "An older archive without that section remains\nreview context but cannot earn a candidate or gotcha.",
    "Never supplement missing archive provenance by\n"
    "reading the live journal, the worktree, Input 1, Input 3, or by guessing.",
    "For every candidate and gotcha, select one exact archive element as its provenance authority.",
    "Input 1 and\nInput 3 may support clustering and shape naming, but they cannot supply or repair proposal identity.",
    "string `input_head`, and `candidates` and `gotchas` arrays. Set `input_head` to\n"
    "the literal full `INPUT_HEAD`",
    "lacks the full input head, names an archive absent at that\n"
    "commit, or uses a proposal provenance value not exposed by the single run-id-derived committed\n"
    "archive",
    "requires the journal prompt path and the SHA-256 of its\n"
    "single-link regular-file bytes to match the archive",
    "renders the exact\n`<input_head>:<archive-path>` citation into each candidate and gotcha",
    "require the repository's current committed `HEAD` to remain exactly\n`input_head`",
    "Refuse a candidate path already present at `input_head`, even when its working-tree\n"
    "copy was deleted.",
    "require those exact bytes to remain\nthe working file's prefix",
    "preserve and append after any prior uncommitted learning suffix.",
)

VERDICT_CONTROL_ANCHORS = (
    "Select `expected_verdict` from exactly `PASS`, `BLOCK`, or `FLAG` using FR-100 semantics",
    "the example's\n`BLOCK` value is illustrative, not the only allowed verdict.",
    "Use `FLAG` only for a recorded non-review\nmonitoring agent, and never for a review agent",
    "review agents have only `PASS` or `BLOCK` outcomes.",
)

AUTHORITY_SURFACES = (
    "`.forge/evals/tasks/`",
    "any `.result` baseline",
    "`rules/` or the review constitution",
    "`forge-project.md`",
    "`.forge-manifest`",
    "routing configuration",
    "hooks",
    "gates",
    "execpolicy",
    "agent definitions",
    "any other control surface",
)

ACTION_CONTROL_ANCHORS = (
    "Never auto-apply, promote, approve, weaken, or commit a proposal.",
    "Never stage candidates or\ngotchas.",
    "`/forge:learn` cannot perform or authorize it.",
    "Proposal creation must not\nwrite, reopen, or amend `run_closed`, the committed archive, or `report.md`.",
    "It never consumes candidates as a gate.",
    "Leave all proposal changes unstaged and uncommitted for a later\nordinary commit.",
)

CANDIDATE_KEYS = {
    "agent",
    "category",
    "execution",
    "expected",
    "expected_verdict",
    "id",
    "run_id",
    "scenario",
}
GOTCHA_KEYS = {"agent", "entries", "execution", "line", "run_id"}


def proposal_example(text: str) -> dict[str, object]:
    match = re.search(r"```json\n(.*?)\n```", text, flags=re.DOTALL)
    if match is None:
        raise AssertionError("learn skill lacks a JSON proposal example")
    return json.loads(match.group(1))


def assert_input_contract(test_case: unittest.TestCase, text: str) -> None:
    headings = re.findall(r"^### Input ([1-3]) —", text, flags=re.MULTILINE)
    test_case.assertEqual(headings, ["1", "2", "3"])
    for anchor in INPUT_CONTROL_ANCHORS:
        test_case.assertIn(anchor, text)
    test_case.assertIn("one immutable input snapshot", text)
    test_case.assertIn("Record `INPUT_HEAD`, each input file identity", _flat(text))
    test_case.assertIn("every source path in the launch assignment", text)
    test_case.assertIn("Inputs 2 and 3 also embed their committed HEAD/path", text)
    test_case.assertIn("current committed", text.lower())
    test_case.assertIn("Do not resume a prior reviewer", text)
    test_case.assertIn("read-only tools", text)


def assert_proposal_contract(test_case: unittest.TestCase, text: str) -> None:
    example = proposal_example(text)
    test_case.assertEqual(
        set(example), {"candidates", "gotchas", "input_head", "schema_version"}
    )
    test_case.assertEqual(example["schema_version"], 1)
    test_case.assertEqual(example["input_head"], "<full INPUT_HEAD>")
    candidates = example["candidates"]
    gotchas = example["gotchas"]
    test_case.assertIsInstance(candidates, list)
    test_case.assertIsInstance(gotchas, list)
    test_case.assertEqual(len(candidates), 1)
    test_case.assertEqual(len(gotchas), 1)
    test_case.assertEqual(set(candidates[0]), CANDIDATE_KEYS)
    test_case.assertEqual(set(gotchas[0]), GOTCHA_KEYS)
    entries = gotchas[0]["entries"]
    test_case.assertIsInstance(entries, list)
    test_case.assertGreater(len(entries), 0)
    for entry in entries:
        test_case.assertEqual(set(entry), {"id", "type"})
        test_case.assertIn(entry["type"], {"decision", "verification"})
    test_case.assertNotIn("prompt", candidates[0])
    test_case.assertIn(
        "The reviewer never receives or returns the recorded prompt.", text
    )
    test_case.assertIn(
        "writer to hydrate the exact recorded `prompt.md` from that\n"
        "run's journal provenance",
        text,
    )
    test_case.assertIn(
        "every cited entry must exist exactly once in the named run and name\n"
        "the same task as the recorded execution",
        text,
    )
    test_case.assertIn(
        "renders the appended gotcha line with citations to its run ID, execution ID, and every decision or\n"
        "verification ID used",
        text,
    )
    test_case.assertIn(
        "At least one cited entry must be a `verification` whose\n"
        "recorded result is `failed` or `inconclusive`",
        text,
    )
    test_case.assertIn(
        "require the named journal to end in exactly one final `run_closed`\n"
        "with judgment `passed` or `blocked`",
        text,
    )
    test_case.assertIn(
        "require the named execution's task to contain a recorded\n"
        "`failed` or `inconclusive` verification",
        text,
    )
    test_case.assertIn("must contain no CR or LF", text)
    test_case.assertIn(
        'python3 "${CLAUDE_PLUGIN_ROOT}/scripts/forge/learn-proposals-locked.py" \\\n'
        '  --repo "$REPO" --proposal "$PROPOSALS_FILE"',
        text,
    )


def assert_archive_provenance_contract(test_case: unittest.TestCase, text: str) -> None:
    for anchor in ARCHIVE_PROVENANCE_ANCHORS:
        test_case.assertIn(anchor, text)
    example = proposal_example(text)
    candidate = example["candidates"][0]
    gotcha = example["gotchas"][0]
    test_case.assertNotIn("[archive:", candidate["scenario"])
    test_case.assertNotIn("[archive:", gotcha["line"])
    test_case.assertEqual(example["input_head"], "<full INPUT_HEAD>")


def assert_verdict_contract(test_case: unittest.TestCase, text: str) -> None:
    for anchor in VERDICT_CONTROL_ANCHORS:
        test_case.assertIn(anchor, text)
    example = proposal_example(text)
    test_case.assertEqual(example["candidates"][0]["expected_verdict"], "BLOCK")


def assert_authority_contract(test_case: unittest.TestCase, text: str) -> None:
    matrix_match = re.search(
        r"Apply this complete negative-write matrix.*?\n\n(.*?)\n\nNever auto-apply",
        text,
        flags=re.DOTALL,
    )
    if matrix_match is None:
        raise AssertionError("learn skill lacks the authority matrix")
    matrix = matrix_match.group(1)
    test_case.assertEqual(
        len([line for line in matrix.splitlines() if line.startswith("|")]), 13
    )
    for surface in AUTHORITY_SURFACES:
        test_case.assertIn(f"| {surface} |", matrix)
    for anchor in ACTION_CONTROL_ANCHORS:
        test_case.assertIn(anchor, text)
    test_case.assertIn("read-only and the deterministic proposal writer", text)
    test_case.assertIn("the only mutation mechanism", text)
    test_case.assertIn("Candidate promotion remains a separate FR-051", text)


def assert_workflow_order(test_case: unittest.TestCase, text: str) -> None:
    canonical = (
        "`validate --gates → run_closed → validate --gates → archive → report.md`."
    )
    heading = "## Post-Report Best-Effort Learning"
    test_case.assertEqual(text.count(canonical), 1)
    test_case.assertEqual(text.count(heading), 1)
    test_case.assertLess(text.index(canonical), text.index(heading))
    section = text[text.index(heading) :]
    test_case.assertIn("Only after Step 13 has finished", section)
    test_case.assertIn("outside the canonical close sequence", section)
    test_case.assertIn("never runs inside the archive commit", _flat(section))
    test_case.assertIn("must not reopen, block, delay, or change", section)
    test_case.assertIn("unstaged and uncommitted", section)


def assert_drift_order(test_case: unittest.TestCase, text: str) -> None:
    block_heading = "## 4. Apply CRITICAL-Only Run Blocking"
    learn_heading = "## 5. Post-Report Best-Effort Learning"
    test_case.assertEqual(text.count(learn_heading), 1)
    test_case.assertLess(text.index(block_heading), text.index(learn_heading))
    section = text[text.index(learn_heading) :]
    test_case.assertIn("Only after the durable drift report commit is verified", section)
    test_case.assertIn("Section 4 has finished all applicable CRITICAL-block handling", _flat(section))
    test_case.assertIn("primary drift outcome has been reported", section)
    test_case.assertIn("available `journal_patterns` object as learning Input 1", section)
    test_case.assertIn("failure or refusal does not block drift completion", _flat(section))
    test_case.assertIn("unstaged and uncommitted", _flat(section))


class LearnSkillContractTests(unittest.TestCase):
    def test_packaging_frontmatter_and_only_required_skill_file(self) -> None:
        files = sorted(
            path.relative_to(LEARN_PATH.parent).as_posix()
            for path in LEARN_PATH.parent.rglob("*")
            if path.is_file()
        )
        self.assertEqual(files, ["SKILL.md"])
        self.assertTrue(LEARN.startswith("---\nname: learn\ndescription:"))
        frontmatter = LEARN.split("---\n", 2)[1]
        keys = [line.split(":", 1)[0] for line in frontmatter.splitlines()]
        self.assertEqual(keys, ["name", "description"])

    def test_exact_three_committed_provenanced_inputs_and_refusal(self) -> None:
        assert_input_contract(self, LEARN)
        self.assertIn("require the caller to identify which completed lifecycle boundary", LEARN)
        self.assertIn("Refuse when that ordering provenance is absent", LEARN)
        self.assertIn("This is an orchestration precondition, not semantic-review evidence", LEARN)

    def test_proposal_shape_traceability_and_prompt_hydration(self) -> None:
        assert_proposal_contract(self, LEARN)

    def test_committed_archive_is_complete_exclusive_proposal_authority(self) -> None:
        assert_archive_provenance_contract(self, LEARN)

    def test_expected_verdict_uses_full_fr100_semantics(self) -> None:
        assert_verdict_contract(self, LEARN)

    def test_complete_advisory_negative_write_matrix(self) -> None:
        assert_authority_contract(self, LEARN)

    def test_failure_shapes_are_named_clustered_and_tied_to_earlier_control(self) -> None:
        self.assertIn("Cluster recurring failures by shape.", LEARN)
        self.assertIn("Give every proposed shape a concise name", LEARN)
        self.assertIn("state which earlier control would have caught it", LEARN)

    def test_workflow_and_drift_learning_are_separate_best_effort_tail_steps(self) -> None:
        assert_workflow_order(self, WORKFLOW)
        assert_drift_order(self, DRIFT)

    def test_readme_and_project_pointers_expose_the_eighth_skill(self) -> None:
        self.assertIn("You should see eight skills:", _flat(README))
        skill_rows = re.findall(r"^\| `/forge:[^`]+` \|", README, flags=re.MULTILINE)
        self.assertEqual(len(skill_rows), 8)
        self.assertIn("| `/forge:learn` | Advisory journal-derived learning", README)
        self.assertIn("After the archive commit and final report", README)
        self.assertIn("best-effort advisory pass", README)
        self.assertIn("never promotes or applies a fixture, changes a control", README)
        pointer = "${CLAUDE_PLUGIN_ROOT}/skills/learn/SKILL.md"
        self.assertEqual(PROJECT.count(pointer), 1)
        self.assertEqual(PROJECT_TEMPLATE.count(pointer), 1)

    def test_each_input_control_discriminates_when_disabled_in_memory(self) -> None:
        assert_input_contract(self, LEARN)
        for anchor in INPUT_CONTROL_ANCHORS:
            with self.subTest(anchor=anchor):
                self.assertEqual(LEARN.count(anchor), 1)
                mutated = LEARN.replace(anchor, "DISABLED INPUT CONTROL", 1)
                with self.assertRaises(AssertionError):
                    assert_input_contract(self, mutated)

    def test_archive_provenance_controls_discriminate_when_disabled_in_memory(self) -> None:
        assert_archive_provenance_contract(self, LEARN)
        for anchor in ARCHIVE_PROVENANCE_ANCHORS:
            with self.subTest(anchor=anchor):
                self.assertEqual(LEARN.count(anchor), 1)
                mutated = LEARN.replace(anchor, "DISABLED ARCHIVE PROVENANCE", 1)
                with self.assertRaises(AssertionError):
                    assert_archive_provenance_contract(self, mutated)

    def test_expected_verdict_controls_discriminate_when_disabled_in_memory(self) -> None:
        assert_verdict_contract(self, LEARN)
        for anchor in VERDICT_CONTROL_ANCHORS:
            with self.subTest(anchor=anchor):
                self.assertEqual(LEARN.count(anchor), 1)
                mutated = LEARN.replace(anchor, "DISABLED VERDICT CONTROL", 1)
                with self.assertRaises(AssertionError):
                    assert_verdict_contract(self, mutated)

    def test_each_authority_surface_discriminates_when_disabled_in_memory(self) -> None:
        assert_authority_contract(self, LEARN)
        for surface in AUTHORITY_SURFACES:
            with self.subTest(surface=surface):
                self.assertEqual(LEARN.count(f"| {surface} |"), 1)
                mutated = LEARN.replace(
                    f"| {surface} |", "| DISABLED AUTHORITY CONTROL |", 1
                )
                with self.assertRaises(AssertionError):
                    assert_authority_contract(self, mutated)

    def test_each_advisory_action_control_discriminates_when_disabled(self) -> None:
        assert_authority_contract(self, LEARN)
        for anchor in ACTION_CONTROL_ANCHORS:
            with self.subTest(anchor=anchor):
                self.assertEqual(LEARN.count(anchor), 1)
                mutated = LEARN.replace(anchor, "DISABLED ACTION CONTROL", 1)
                with self.assertRaises(AssertionError):
                    assert_authority_contract(self, mutated)

    def test_proposal_schema_and_hydration_controls_discriminate(self) -> None:
        assert_proposal_contract(self, LEARN)
        mutations = (
            LEARN.replace('"schema_version": 1', '"schema_version": 2', 1),
            LEARN.replace('"expected_verdict":', '"disabled_verdict":', 1),
            LEARN.replace('"entries":', '"disabled_entries":', 1),
            LEARN.replace('"line":', '"disabled_line":', 1),
            LEARN.replace(
                "The reviewer never receives or returns the recorded prompt.",
                "DISABLED PROMPT ISOLATION",
                1,
            ),
            LEARN.replace(
                "At least one cited entry must be a `verification` whose\n"
                "recorded result is `failed` or `inconclusive`",
                "DISABLED EARNED CITATION",
                1,
            ),
            LEARN.replace(
                "require the named journal to end in exactly one final `run_closed`\n"
                "with judgment `passed` or `blocked`",
                "DISABLED CLOSED RUN",
                1,
            ),
            LEARN.replace(
                "require the named execution's task to contain a recorded\n"
                "`failed` or `inconclusive` verification",
                "DISABLED FAILURE SOURCE",
                1,
            ),
            LEARN.replace(
                '  --repo "$REPO" --proposal "$PROPOSALS_FILE"',
                "  --disabled-writer-contract",
                1,
            ),
        )
        for index, mutated in enumerate(mutations):
            with self.subTest(mutation=index):
                with self.assertRaises(AssertionError):
                    assert_proposal_contract(self, mutated)

    def test_post_close_and_drift_order_controls_discriminate(self) -> None:
        assert_workflow_order(self, WORKFLOW)
        workflow_heading = "## Post-Report Best-Effort Learning"
        workflow_prefix, workflow_tail = WORKFLOW.split(workflow_heading, 1)
        close_anchor = "The canonical close sequence is"
        moved_workflow = workflow_prefix.replace(
            close_anchor,
            workflow_heading + workflow_tail + "\n\n" + close_anchor,
            1,
        )
        with self.assertRaises(AssertionError):
            assert_workflow_order(self, moved_workflow)

        assert_drift_order(self, DRIFT)
        drift_heading = "## 5. Post-Report Best-Effort Learning"
        drift_prefix, drift_tail = DRIFT.split(drift_heading, 1)
        block_anchor = "## 4. Apply CRITICAL-Only Run Blocking"
        moved_drift = drift_prefix.replace(
            block_anchor, drift_heading + drift_tail + "\n\n" + block_anchor, 1
        )
        with self.assertRaises(AssertionError):
            assert_drift_order(self, moved_drift)


if __name__ == "__main__":
    unittest.main()
