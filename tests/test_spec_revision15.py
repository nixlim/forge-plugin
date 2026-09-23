from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = (ROOT / "docs/specs/forge-plugin-spec.md").read_text(encoding="utf-8")
POLICIES = {
    "root": (ROOT / "forge-project.md").read_text(encoding="utf-8"),
    "template": (ROOT / "system/template/forge-project.md").read_text(
        encoding="utf-8"
    ),
}
DEFERRED_TO = {
    "FR-244": "L",
    "FR-245": "E/I/B",
    "FR-246": "E",
    "FR-247": "J",
    "DM-018": "J/E",
}
NEW_CONTROL_PATHS = ("system/claude/**", "system/local/**")
REVIEWER_PATTERNS = (
    ("agent-prompt-template", "system/claude/prompts/**"),
    ("reviewer-routing", "scripts/forge/forge_cli/app/**"),
    ("reviewer-routing", "system/local/**"),
)


def requirement_block(text: str, requirement_id: str) -> str:
    pattern = re.compile(rf"(?m)^(?:- )?\*\*{re.escape(requirement_id)}\*\*")
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise AssertionError(
            f"expected one {requirement_id}, found {len(matches)}"
        )
    start = matches[0].start()
    remainder = text[matches[0].end() :]
    boundary = re.search(
        r"(?m)^(?:(?:- )?\*\*(?:FR|DM)-\d{3}\*\*|## )",
        remainder,
    )
    end = matches[0].end() + (
        boundary.start() if boundary is not None else len(remainder)
    )
    return text[start:end]


def region(document: str, name: str) -> str:
    pattern = re.compile(
        rf"<!-- FORGE:REGION {re.escape(name)} BEGIN -->\n(.*?)"
        rf"<!-- FORGE:REGION {re.escape(name)} END -->",
        flags=re.DOTALL,
    )
    matches = pattern.findall(document)
    if len(matches) != 1:
        raise AssertionError(f"expected one {name} region")
    return matches[0]


def active_region(document: str, name: str) -> str:
    return re.sub(r"<!--.*?-->", "", region(document, name), flags=re.DOTALL)


def canonical_reviewer_table(specification: str) -> str:
    match = re.search(
        r"The `reviewer-facing-eval-triggers` region is the sole maintained "
        r"reviewer-facing trigger path list and contains exactly these ordered rows:\n\n"
        r"(\| control \| path patterns \|\n"
        r"\|---\|---\|\n"
        r"(?:\| [^\n]+ \|\n)+)",
        specification,
    )
    if match is None:
        raise AssertionError("specification lacks the canonical reviewer table")
    return match.group(1)


def assert_deferred_authority(specification: str) -> None:
    for requirement_id, destination in DEFERRED_TO.items():
        block = requirement_block(specification, requirement_id)
        expected = (
            "(Revision 15 authority; implementation deferred "
            f"to chain {destination})"
        )
        markers = re.findall(
            r"\(Revision 15 authority; implementation deferred to chain [^)]+\)",
            block,
        )
        if markers != [expected]:
            raise AssertionError(
                f"{requirement_id} deferral markers {markers!r} != {[expected]!r}"
            )


def assert_trigger_controls(specification: str, policies: dict[str, str]) -> None:
    canonical = canonical_reviewer_table(specification)
    canonical_rows = canonical.splitlines()
    for control, pattern in REVIEWER_PATTERNS:
        matching_rows = [line for line in canonical_rows if line.startswith(f"| {control} |")]
        if len(matching_rows) != 1 or pattern not in matching_rows[0]:
            raise AssertionError(f"canonical {control} lacks {pattern}")
    for label, document in policies.items():
        reviewer = region(document, "reviewer-facing-eval-triggers")
        if reviewer != canonical:
            raise AssertionError(f"{label} reviewer trigger table diverges")
        for path in NEW_CONTROL_PATHS:
            trigger_paths = active_region(document, "trigger-paths")
            if re.search(rf"(?m)^\|\s*`?{re.escape(path)}`?\s*\|$", trigger_paths) is None:
                raise AssertionError(f"{label} trigger-paths lacks {path}")
            expected_project_row = (
                f"| `{path}` | STRICT evals and routing conformance |"
            )
            project_rows = active_region(
                document, "project-triggers"
            ).splitlines()
            if project_rows.count(expected_project_row) != 1:
                raise AssertionError(
                    f"{label} project-triggers lacks exact row for {path}"
                )


class SpecificationRevision15Tests(unittest.TestCase):
    def test_revision_and_new_authority_are_explicitly_deferred(self) -> None:
        self.assertIn("**Status**: Draft (Revision 15)", SPEC)
        intent = next(
            line for line in SPEC.splitlines() if line.startswith("**Intent**:")
        )
        self.assertIn("Revision 15", intent)
        assert_deferred_authority(SPEC)

    def test_each_deferral_assertion_detects_its_removal(self) -> None:
        for requirement_id, destination in DEFERRED_TO.items():
            marker = (
                "(Revision 15 authority; implementation deferred "
                f"to chain {destination})"
            )
            with self.subTest(requirement=requirement_id):
                block = requirement_block(SPEC, requirement_id)
                self.assertIn(marker, block)
                block_start = SPEC.index(block)
                marker_start = block_start + block.index(marker)
                mutant = (
                    SPEC[:marker_start]
                    + "(Revision 15 authority)"
                    + SPEC[marker_start + len(marker) :]
                )
                with self.assertRaisesRegex(AssertionError, requirement_id):
                    assert_deferred_authority(mutant)

    def test_trigger_regions_are_mirrored_and_fail_closed(self) -> None:
        assert_trigger_controls(SPEC, POLICIES)

    def test_trigger_assertion_detects_disabled_control(self) -> None:
        mutant = POLICIES["template"].replace(
            "scripts/forge/forge_cli/app/**, ", "", 1
        )
        with self.assertRaisesRegex(AssertionError, "reviewer trigger table diverges"):
            assert_trigger_controls(
                SPEC, {"root": POLICIES["root"], "template": mutant}
            )

    def test_reviewer_pattern_assertions_detect_coherent_removal(self) -> None:
        removals = {
            "system/claude/prompts/**": ("system/claude/prompts/**, ", ""),
            "scripts/forge/forge_cli/app/**": (
                "scripts/forge/forge_cli/app/**, ",
                "",
            ),
            "system/local/**": (", system/local/** |", " |"),
        }
        for pattern, (old, new) in removals.items():
            with self.subTest(pattern=pattern):
                mutant_spec = SPEC.replace(old, new, 1)
                mutant_policies = {
                    label: document.replace(old, new, 1)
                    for label, document in POLICIES.items()
                }
                with self.assertRaisesRegex(AssertionError, re.escape(pattern)):
                    assert_trigger_controls(mutant_spec, mutant_policies)

    def test_path_row_assertions_detect_each_removal(self) -> None:
        for path in NEW_CONTROL_PATHS:
            with self.subTest(path=path):
                trigger_row = f"| {path} |\n"
                project_row = (
                    f"| `{path}` | STRICT evals and routing conformance |\n"
                )
                for row in (trigger_row, project_row):
                    mutant = POLICIES["template"].replace(row, "", 1)
                    with self.assertRaisesRegex(AssertionError, re.escape(path)):
                        assert_trigger_controls(
                            SPEC,
                            {"root": POLICIES["root"], "template": mutant},
                        )


if __name__ == "__main__":
    unittest.main()
