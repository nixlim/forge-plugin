"""Contracts for the Revision-17 review-lane documentation."""

from __future__ import annotations

import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMIT_PATH = ROOT / "skills/commit/SKILL.md"
MERGE_PATH = ROOT / "skills/worktree-merge/SKILL.md"
REVIEW_PATH = ROOT / "skills/orchestrate/references/review.md"
DESIGN_PATH = ROOT / "docs/design/0003-forge-cli-plumbing.md"

COMMIT = COMMIT_PATH.read_text(encoding="utf-8")
MERGE = MERGE_PATH.read_text(encoding="utf-8")
REVIEW = REVIEW_PATH.read_text(encoding="utf-8")
DESIGN = DESIGN_PATH.read_text(encoding="utf-8")
DOCUMENTS = (COMMIT, MERGE, REVIEW, DESIGN)
DISABLED_CONTROL = "DISABLED_CONTROL"

COMMIT_SECTION_PHRASES = (
    "`standard`: select role `review-cheap`",
    "`hard`: select role `review-final`",
    "The resolved `review-cheap` route supplies its provider, model, and effort",
    "The resolved `review-final` route supplies its provider, model, and effort",
    "A Claude reviewer in either role is instruction-bounded and execution-capable",
    "not an OS-level read-only sandbox",
    "A Codex reviewer runs in the `read-only` sandbox",
    "The Forge engine alone launches either reviewer, on the persisted commit chain that holds "
    "this exact candidate",
    "`forge review request --chain-id <id>`",
    "`forge review collect --chain-id <id>` is the only way a new request's verdict binds",
    "never issue another request",
    "`forge review cancel --chain-id <id>` is used only when collect names it",
    "you never hand a reviewer a prompt, instruction, or package yourself",
    "For a persisted chain's candidate, never spawn an interactive or Agent-tool `review-final`",
    "never launch a chain reviewer by prose",
    "never run `review attach` for a new request",
    "the legacy `invocation` shape",
    "A commit run without a persisted chain has no admissible standard or hard reviewer",
    "so this skill alone completes only `fast` candidates",
)
COMMIT_STEP_PHRASES = (
    "One bound verdict, including the engine's synthetic BLOCK, is one iteration",
    "consumes none",
)
COMMIT_FORBIDDEN = (
    "`review-final` Claude agent",
    "fresh, read-only Codex `review-cheap`",
    "--verdict-file",
    "One reviewer invocation is one iteration",
)
MERGE_PHRASES = (
    "Start the `review-final` Claude agent as a reviewer distinct from the author",
    "FR-060's engine-owned `review request` plus `review collect` path is not available to it",
    "Revision-17 headless-review amendment to FR-246",
    "a developer-local `review-final` route does not apply to it",
    "`forge review attach` is never used for it",
)
REVIEW_PHRASES = (
    "never a commit or merge gate review",
    "do not attach its handoff or verdict to a chain",
    "`forge review request --chain-id <id>`",
    "`forge review collect --chain-id <id>`",
    "never use `review attach` for a new request",
    "keeps its interactive Gate 3 `review-final`",
)
DESIGN_PHRASES = (
    "supersedes the tier split in `review request`, `review collect`, and `review attach` above",
    "`review cancel`",
    "legacy `invocation` shape",
    "held for an interactive Agent-tool subagent, not for the headless Claude CLI",
    "so the limit above still applies to its Gate 3",
    "to spawn as a Claude subagent — a CLI subprocess cannot spawn one.",
    "review-final is a Claude subagent spawned through the Agent tool by the orchestrator",
)


def normalized(text: str) -> str:
    return " ".join(text.split())


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def require_once(text: str, phrase: str) -> None:
    require(text.count(phrase) == 1, f"expected exactly once: {phrase}")


def assert_commit_contract(text: str) -> None:
    prose = normalized(text)
    section = prose.split("Route the review as follows:", 1)[1].split("Give the reviewer", 1)[0]
    step_four = prose.split("## Step 4 —", 1)[1].split("## Step 5 —", 1)[0]
    for phrase in COMMIT_SECTION_PHRASES:
        require_once(section, phrase)
    for phrase in COMMIT_STEP_PHRASES:
        require_once(step_four, phrase)
    request = section.index("`forge review request --chain-id <id>`")
    collect = section.index("`forge review collect --chain-id <id>`")
    cancel = section.index("`forge review cancel --chain-id <id>`")
    require(request < collect < cancel, "commit review verbs are out of order")
    for phrase in COMMIT_FORBIDDEN:
        require(phrase not in step_four, f"forbidden Step 4 phrase: {phrase}")


def assert_merge_contract(text: str) -> None:
    prose = normalized(text)
    gate_three = prose.split("## Gate 3", 1)[1].split("## Gate 4", 1)[0]
    for phrase in MERGE_PHRASES:
        require_once(gate_three, phrase)
    launch = gate_three.index(MERGE_PHRASES[0])
    deferral = gate_three.index(MERGE_PHRASES[1])
    review_diff = gate_three.index("exact, unmodified diff")
    require(launch < deferral < review_diff, "legacy merge review explanation is out of order")


def assert_review_reference_contract(text: str) -> None:
    prose = normalized(text)
    heading = "## Gate Reviews Are Engine-Launched"
    require_once(prose, heading)
    first_review = prose.index("For the first independent review:")
    before_launch = prose.index("Immediately before launch")
    verified = prose.index("Verify review findings against the repository")
    heading_at = prose.index(heading)
    require(heading_at > verified, "gate-review section must follow finding verification")
    require(
        not first_review < heading_at < before_launch,
        "gate-review section entered launch span",
    )
    section = prose[heading_at:]
    for phrase in REVIEW_PHRASES:
        require_once(section, phrase)
    link = "[commit skill](../../commit/SKILL.md)"
    require_once(section, link)
    require(
        (REVIEW_PATH.parent / "../../commit/SKILL.md").resolve().is_file(),
        "broken commit link",
    )


def assert_design_contract(text: str) -> None:
    prose = normalized(text)
    for phrase in DESIGN_PHRASES:
        require_once(prose, phrase)
    review_end_anchor = text.index("mechanism (FR-053).")
    review_fence = text.index("```", review_end_anchor)
    anti_anchoring = text.index("### Anti-anchoring")
    note_one = text.index("supersedes the tier split")
    require(review_fence < note_one < anti_anchoring, "first Revision-17 note is misplaced")
    asymmetry = prose.index("asymmetry rather than paper over it.")
    system_record = prose.index("## System of Record (D7)")
    note_two = prose.index(DESIGN_PHRASES[3])
    merge_limit = prose.index(DESIGN_PHRASES[4])
    require(asymmetry < note_two < system_record, "second Revision-17 note is misplaced")
    require(asymmetry < merge_limit < system_record, "legacy merge limit is misplaced")


def swapped_once(text: str, first: str, second: str) -> str:
    require_once(text, first)
    require_once(text, second)
    marker = "SWAPPED_CONTROL_MARKER"
    return text.replace(first, marker, 1).replace(second, first, 1).replace(marker, second, 1)


def assert_verb_contract(documented: set[str], cli_verbs: set[str]) -> None:
    require(documented <= cli_verbs, "documented review verb is absent from CLI help")
    require("cancel" in documented, "cancel is absent from documentation")
    require("cancel" in cli_verbs, "cancel is absent from CLI help")


class ReviewLaneProseTests(unittest.TestCase):
    def test_document_contracts(self) -> None:
        assert_commit_contract(COMMIT)
        assert_merge_contract(MERGE)
        assert_review_reference_contract(REVIEW)
        assert_design_contract(DESIGN)

    def test_commit_controls_have_disable_legs(self) -> None:
        prose = normalized(COMMIT)
        for phrase in (*COMMIT_SECTION_PHRASES, *COMMIT_STEP_PHRASES):
            with self.subTest(required=phrase):
                require_once(prose, phrase)
                with self.assertRaises(AssertionError):
                    assert_commit_contract(prose.replace(phrase, DISABLED_CONTROL, 1))
        for phrase in COMMIT_FORBIDDEN:
            with self.subTest(forbidden=phrase):
                mutant = prose.replace("Give the reviewer", f"{phrase} Give the reviewer", 1)
                with self.assertRaises(AssertionError):
                    assert_commit_contract(mutant)
        for first, second in (
            ("`forge review request --chain-id <id>`", "`forge review collect --chain-id <id>`"),
            ("`forge review collect --chain-id <id>`", "`forge review cancel --chain-id <id>`"),
        ):
            with self.subTest(order=f"{first} before {second}"):
                with self.assertRaises(AssertionError):
                    assert_commit_contract(swapped_once(prose, first, second))

    def test_merge_controls_have_disable_legs(self) -> None:
        prose = normalized(MERGE)
        for phrase in MERGE_PHRASES:
            with self.subTest(required=phrase):
                require_once(prose, phrase)
                with self.assertRaises(AssertionError):
                    assert_merge_contract(prose.replace(phrase, DISABLED_CONTROL, 1))
        for first, second in (
            (MERGE_PHRASES[0], MERGE_PHRASES[1]),
            (MERGE_PHRASES[1], "exact, unmodified diff"),
        ):
            with self.subTest(order=f"{first} before {second}"):
                with self.assertRaises(AssertionError):
                    assert_merge_contract(swapped_once(prose, first, second))

    def test_review_reference_controls_have_disable_legs(self) -> None:
        prose = normalized(REVIEW)
        controls = (
            "## Gate Reviews Are Engine-Launched",
            *REVIEW_PHRASES,
            "[commit skill](../../commit/SKILL.md)",
        )
        for phrase in controls:
            with self.subTest(required=phrase):
                require_once(prose, phrase)
                with self.assertRaises(AssertionError):
                    assert_review_reference_contract(prose.replace(phrase, DISABLED_CONTROL, 1))
        heading = "## Gate Reviews Are Engine-Launched"
        without_heading = prose.replace(heading, "", 1)
        before_verify = without_heading.replace(
            "Verify review findings against the repository",
            f"{heading} Verify review findings against the repository",
            1,
        )
        in_launch_span = without_heading.replace(
            "Immediately before launch", f"{heading} Immediately before launch", 1
        )
        order_mutants = (
            ("after verification", before_verify),
            ("outside launch", in_launch_span),
        )
        for label, mutant in order_mutants:
            with self.subTest(order=label), self.assertRaises(AssertionError):
                assert_review_reference_contract(mutant)

    def test_design_controls_have_disable_legs(self) -> None:
        prose = normalized(DESIGN)
        for phrase in DESIGN_PHRASES:
            with self.subTest(required=phrase):
                require_once(prose, phrase)
                with self.assertRaises(AssertionError):
                    assert_design_contract(prose.replace(phrase, DISABLED_CONTROL, 1))
        note_one = DESIGN_PHRASES[0]
        moved_one = prose.replace(note_one, "", 1).replace(
            "mechanism (FR-053).", f"{note_one} mechanism (FR-053).", 1
        )
        note_two = DESIGN_PHRASES[3]
        moved_two = prose.replace(note_two, "", 1).replace(
            "asymmetry rather than paper over it.",
            f"{note_two} asymmetry rather than paper over it.",
            1,
        )
        merge_limit = DESIGN_PHRASES[4]
        moved_limit = prose.replace(merge_limit, "", 1).replace(
            "## System of Record (D7)", f"## System of Record (D7) {merge_limit}", 1
        )
        for label, mutant in (
            ("after review fence", moved_one),
            ("after asymmetry", moved_two),
            ("before system of record", moved_limit),
        ):
            with self.subTest(order=label), self.assertRaises(AssertionError):
                assert_design_contract(mutant)

    def test_documented_review_verbs_exist_in_cli(self) -> None:
        documented = set(re.findall(r"forge review ([a-z]+) --chain-id", "\n".join(DOCUMENTS)))
        result = subprocess.run(
            [sys.executable, "scripts/forge/cli.py", "review", "--help"],
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        match = re.search(r"\{([a-z,]+)\}", result.stdout + result.stderr)
        self.assertIsNotNone(match, result.stdout + result.stderr)
        cli_verbs = set(match.group(1).split(",")) if match else set()
        assert_verb_contract(documented, cli_verbs)
        with self.subTest(disabled="cancel missing from CLI"), self.assertRaises(AssertionError):
            assert_verb_contract(documented, cli_verbs - {"cancel"})


if __name__ == "__main__":
    unittest.main()
