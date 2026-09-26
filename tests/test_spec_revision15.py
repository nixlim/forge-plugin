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
DEFERRED_MARKERS = {
    "FR-245": "(Revision 15 authority; implementation deferred to chain E/I/B)",
    "FR-246": "(Revision 15 authority; implementation deferred to chain E)",
    "DM-018": (
        "(Revision 15 authority; `review.request.route` implementation deferred "
        "to chain E)"
    ),
}
IMPLEMENTED = ("FR-244", "FR-247")
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
    for requirement_id in IMPLEMENTED:
        block = requirement_block(specification, requirement_id)
        markers = re.findall(
            r"\(Revision 15 authority; (?:`[^`]+` )?implementation deferred "
            r"to chain [^)]+\)",
            block,
        )
        if markers:
            raise AssertionError(
                f"{requirement_id} retains deferral markers {markers!r}"
            )
    for requirement_id, expected in DEFERRED_MARKERS.items():
        block = requirement_block(specification, requirement_id)
        markers = re.findall(
            r"\(Revision 15 authority; (?:`[^`]+` )?implementation deferred "
            r"to chain [^)]+\)",
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
    def test_revision_and_deferral_state_are_explicit(self) -> None:
        self.assertIn("**Status**: Draft (Revision 17)", SPEC)
        intent = next(
            line for line in SPEC.splitlines() if line.startswith("**Intent**:")
        )
        self.assertIn("Revision 15", intent)
        assert_deferred_authority(SPEC)

    def test_fr244_deferral_assertion_detects_its_reinsertion(self) -> None:
        block = requirement_block(SPEC, "FR-244")
        self.assertNotIn("implementation deferred to chain L", block)
        mutant = SPEC.replace(
            "**FR-244** (MUST): Routes file.",
            "**FR-244** (MUST): Routes file "
            "(Revision 15 authority; implementation deferred to chain L).",
            1,
        )
        with self.assertRaisesRegex(AssertionError, "FR-244"):
            assert_deferred_authority(mutant)

    def test_fr247_deferral_assertion_detects_its_reinsertion(self) -> None:
        block = requirement_block(SPEC, "FR-247")
        self.assertNotIn("implementation deferred to chain J", block)
        mutant = SPEC.replace(
            "**FR-247** (MUST): Task-completion provenance.",
            "**FR-247** (MUST): Task-completion provenance "
            "(Revision 15 authority; implementation deferred to chain J).",
            1,
        )
        with self.assertRaisesRegex(AssertionError, "FR-247"):
            assert_deferred_authority(mutant)

    def test_chain_j_shipped_contracts_are_explicit(self) -> None:
        dm018 = requirement_block(SPEC, "DM-018")
        for literal in (
            "emits both `route` and `orchestrator_model` on every new `run_started`",
            "typed `run-open` unconditionally resolves all four launched roles",
            "forge: routes file refused — malformed line 1",
            "`when present` clauses retain compatibility only for historical records",
            "uses exactly one of `var-unset`, `transcript-absent`, or `unreadable`",
            "can never refuse typed `run-open`",
            "forge: execution refused — role <role> has no frozen route in the run snapshot",
        ):
            self.assertIn(literal, dm018)
        for helper in ("route_evidence.py", "route_provenance.py"):
            self.assertIn(
                f"`scripts/forge/{helper}`",
                SPEC.split("## 6. Data Model", 1)[0],
            )
        self.assertIn(
            "`route_source` is exactly `local`, `committed-default`, "
            "`plugin-default`, or `unrecorded`, and `status` is exactly `local`, "
            "`matched`, `mismatched`, or `unavailable`",
            SPEC,
        )
        self.assertIn(
            "Status `local` is produced when the recorded model or effort differs "
            "from the committed default because a developer-local route was selected.",
            SPEC,
        )
        self.assertEqual(
            SPEC.count('"route_source":"plugin-default","run_id":"run-01"'), 2
        )
        self.assertIn("routing local/matched/mismatched/unavailable cases", SPEC)

    def test_fr244_amendments_pin_probe_and_review_final_defaults(self) -> None:
        block = requirement_block(SPEC, "FR-244")
        labels = (
            "Revision-16 route-probe amendment to **FR-244**:",
            "Revision-16 review-final default amendment to **FR-244**:",
        )
        for label in labels:
            self.assertEqual(block.count(label), 1)
        review_final_chain = (
            "`.codex/agents/review-final.toml` when present at the launch HEAD, "
            "otherwise `system/codex/agents/review-final.toml`, otherwise the "
            "`model:` and `effort:` frontmatter of `agents/review-final.md` read "
            "as provider `claude` (FR-111's committed-default compatibility "
            "metadata), otherwise the plugin default; every step in that chain "
            "reports `route_source: committed-default` except the plugin default"
        )
        self.assertIn(review_final_chain, block)
        probe_contract = (
            "one bounded launch per distinct resolved "
            "`(provider, model, effort)` tuple",
            "codex exec --json --output-last-message "
            "<scratch>/last-message.txt -s read-only",
            "claude -p --safe-mode --strict-mcp-config --output-format "
            "stream-json --verbose",
            "Confirm that this model route is available and reply briefly.\\n",
            "only the FR-245 allowlisted environment",
            "<common-root>/.forge/tmp/route-probe/",
            "`start_new_session`",
            "probe timeout at 120 seconds independently of FR-245's launch timeouts",
            "caps stdout at 16 MiB and stderr at 1 MiB",
            "waits at most 5 seconds",
            "exits 1 when any tuple fails",
            "never writes repository or working-tree content",
        )
        for clause in probe_contract:
            self.assertIn(clause, block)
        refusal_literals = (
            "forge: codex launch refused — codex CLI is not logged in; "
            "run codex login manually and retry",
            "forge: claude launch refused — claude CLI is not logged in; "
            "run interactive /login manually and retry",
            "forge: <provider> launch refused — route probe timed out",
            "forge: <provider> launch refused — route probe "
            "<stdout|stderr> exceeded limit",
            "forge: <provider> launch refused — route probe failed",
            "forge: <provider> launch refused — <provider> CLI could not be started",
            "forge: route probe refused — unsafe scratch directory",
        )
        for literal in refusal_literals:
            self.assertIn(literal, block)
        report_fields = (
            "`provider`, `model`, `effort`, `roles`, `ok`, `returncode`, "
            "`timed_out`, `output_limit`, `observed_model`, "
            "`permission_denials`, and `environment_names`"
        )
        self.assertIn(report_fields, block)
        self.assertIn(
            "`scripts/forge/route_config_git.py` is the non-executable stdlib "
            "Git-boundary helper",
            SPEC,
        )

    def test_each_deferral_assertion_detects_its_removal(self) -> None:
        for requirement_id, marker in DEFERRED_MARKERS.items():
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
