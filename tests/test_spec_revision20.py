from __future__ import annotations

import hashlib
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = (ROOT / "docs/specs/forge-plugin-spec.md").read_text(encoding="utf-8")

# Task TZ removes each marker and empties this set after the named implementations land.
DEFERRED = frozenset({"G40", "G42"})
RUN_ID = "run-20261003-archive"
MARKER_RE = re.compile(r"\(Revision 20 authority;[^)]*\)")

HEADINGS = {
    "G40": (
        "Revision-20 installed-root harness-qualification amendment to **FR-223** "
        "(GH#40):"
    ),
    "G41": "The current complete LF-terminated table, SHA-256",
    "G42": "Project content preservation under DM-003 and FR-038, FR-072, FR-080 and FR-084:",
    "FR100": "Revision-20 candidate-checkout clarification to **FR-100** (GH#41):",
}

AMENDMENT_LITERALS = {
    "G40": (
        "FR-218 layer-2 approval qualification runs the byte-identical DM-016 phase-0 v1 "
        "evaluator against the invoking plugin root",
        "exactly its Git work-tree top level",
        "`HEAD:docs/specs/forge-plugin-spec.md` remains authority",
        "working-tree spec bytes are never used",
        "An `lstat`-present `.git` entry",
        "Git resolves a different top level",
        "MUST refuse and MUST NOT fall back",
        "no `.git` entry and no enclosing-work-tree classification",
        "regular non-symlink file",
        "7741b877b1ed45047d680a077c5303b2314cd1f3ef0339821bd7105ac9acd5c9",
        "b2b7157e42fa6622091c2fd02567379068f76eb5daf67e0969861184a8230001",
        "decode as strict UTF-8",
        (
            "7741b877b1ed45047d680a077c5303b2314cd1f3ef0339821bd7105ac9acd5c9  "
            ".forge/evals/tasks/fr223-phase0-v1.manifest.json"
        ),
        "replaces only their committed-spec reader",
        "every existing manifest/artifact, corpus-versus-spec, evidence, "
        "harness-qualification, exit, and result check then runs unchanged",
        "proves self-consistency of the installed tree, not authenticity or provenance",
        "remain byte-identical and are neither copied nor re-minted",
    ),
    "G41": (
        "e347704d6b910b38c617b712c2eb14f0c4a512903c1a4cf3a72ecc30db629790",
        "3d1be7b789a8ee5cc7b5f65ac7f77a5ce3622fe0214a09650c85424c91147d93",
        "releases 0.6.11–0.6.12",
        "9ad0623e2eb7c9d56df44a0c57cb4c7c79e30e4322d9bbc0ea2e50b8817c3ce2",
        "release 0.6.13",
        "45e2e69e0067f06f99cb0e3d42f185d3fdc8ee45f6961100eb51f3298c9500c3",
        "release 0.6.14",
        "895486c4ef0392b704860dbfc3fe52fdf51583544e354d1375544c2e487bdea1",
        "every other body remain malformed",
        "per control and in current canonical control order",
        "current canonical row's patterns followed by every pattern present for that "
        "control only in the authenticated base body, without duplication",
        "trigger matching and fresh-reviewer-evaluation applicability use those effective rows",
        "authenticated base region's own exact bytes",
        "No admitted superseded table can therefore narrow current coverage",
        "`scripts/forge/forge_cli/engine.py` pattern",
        "`reviewer-routing` and `model-provider-version` rows",
        "non-admitted base region retains required fresh-evaluation applicability",
        "FR-220's INVALID exit-2 result",
        "an admitted superseded body does not by itself justify that skip",
        "FR-072's reinstall refresh to current canonical bytes remains unchanged",
        "MUST append the exact superseded bytes and their SHA-256 digest",
    ),
    "G42": (
        "exactly one `<!-- FORGE:PROJECT-SPINE BEGIN -->` / "
        "`<!-- FORGE:PROJECT-SPINE END -->` pair",
        "under the fixed heading `### Project Spine Addenda`",
        "at the end of the DVRR spine before `## Plugin Skills`",
        "it is not a region and does not change the sixteen-region inventory",
        "never to weaken a gate or expand authority",
        "carries the complete block forward byte-for-byte",
        "carries the prior header `Install date` forward",
        "forge: project spine addenda block malformed — repair forge-project.md",
        "refuses before mutation",
        "preserved byte-for-byte as `forge-project.md.forge-prev`",
        "reported as a blocking init collision",
        "substitutes the prior `Install date` into the fresh render",
        "removes only the fresh contiguous addenda stanza from its fixed heading through "
        "the END-marker line and its single following separator blank line",
        "compares every remaining outside-region byte exactly",
        "existing `.forge-prev` is accepted idempotently only when it is a regular "
        "non-symlink",
        "any differing or unsafe sibling refuses before mutation",
        "before the first target-repository mutation",
        "preflight every Codex-layer template and every existing `.codex/hooks.json` or "
        "`.codex/config.toml` input",
        "regular non-symlink strict UTF-8 file of at most 1 MiB",
        "JSON is parsed with duplicate-key rejection",
        "an oversized input, or a hooks-shape violation refuses before any mutation",
        "A hooks document has a root object",
        "event values are arrays of group objects",
        "every group has a `hooks` array of handler objects",
        "every handler has a string `command`",
        "complete object of a marker-owned handler is plugin-owned and replaced",
        "`: 'forge-managed';`",
        "removes all prior plugin-owned handlers",
        "A prior group's residual is the same group after those handlers are removed",
        "retained when at least one foreign handler remains or when the group has any "
        "member other than `hooks`",
        "only an empty hooks-only residual is dropped",
        "fresh template's events, groups, and handlers first in template order",
        "for each event present in that template",
        "prior events absent from the template, with their retained residual groups",
        "prior foreign top-level members in prior order",
        "preserving every foreign handler, group member, event, and top-level member",
        "Every template handler MUST carry that marker",
        "a foreign project SessionStart handler is outside the Forge layer and is preserved",
        "top-level `approval_policy` and `sandbox_mode` keys",
        "complete `agents` table tree",
        "any content outside that namespace or any project-added member under `agents.*`",
        "keep the existing `.codex/config.toml` byte-for-byte",
        "write the fresh template as `.codex/config.toml.forge-new`",
        "whitespace, key and table order, and the spelling of owned values are "
        "plugin-owned and refresh from the template",
        "a comment token is plugin-owned only when its comment bytes begin exactly "
        "`# forge-managed` or `# forge: modified from upstream —`",
        "every other comment is foreign content and takes the same collision path",
        "a project comment that copies either prefix is intentionally treated as "
        "plugin-owned",
        "Missing `tomllib` takes that same collision path",
        "malformed TOML still refuses during preflight",
        "Valid unmarked non-Forge Codex files retain their existing collision behavior",
        "valid FR-184 upstream-signature inputs retain backup-and-replace behavior",
        "existing `.forge-new` is accepted idempotently only when it is a regular "
        "non-symlink with bytes equal to the fresh template",
        "every differing or unsafe sibling refuses before mutation",
        "never silently drops foreign content",
    ),
    "FR100": (
        "Since 0.6.11",
        "has refused, anywhere in the whole tree",
        "absolute symlink targets",
        "symlink targets that escape the checkout root",
        "Git gitlinks",
    ),
}

CROSS_CUTTING_LINES = (
    (
        "G40",
        "`scripts/forge/fr223_verify.py`",
        "85e06c1acdfc9a58a35de8894a1129ef53d734e1cde1195b345ecd958acdb1db",
    ),
    (
        "G42",
        "`scripts/forge/codex_layer_merge.py`",
        "5bff7023f0608bfe889f50d8f724cd8e196106bbb8014afac3b4edf1536460b3",
    ),
    (
        "G40",
        "Revision-20 installed-root qualification tests cover",
        "3d94a6d0a3cf68dbf5bb34df0009765a916aceb778bb4b95b4688a136e785812",
    ),
    (
        "G42",
        "Given** a forge-initialized repo with project spine addenda",
        "ac2324bbc9768acd0b9320564f3bd3bde27ad61271aa7a9a2de0873ab1fc1e1e",
    ),
    (
        "G42",
        "When** `/forge:init` preflights every Codex input",
        "c204dd985d17ef598268eaf8dc921fcc8899be588ab44a109c8233cfd4cf45a1",
    ),
    (
        "G42",
        "Then** the addenda, original install date, and foreign hook",
        "9fce3caf189b272850bfe1b826c886f01cb8871747aaa1b05d10d3e3bb699bd0",
    ),
    (
        "G42",
        "Revision-20 project-content preservation tests cover",
        "c165ac99b74fc0adeb47383c2728c89ae8ad7186dce4f4d94464220ce8e90b8a",
    ),
    (
        "G42",
        "DM-003; FR-038/FR-072/FR-080/FR-084 | Revision-20",
        "932fcc4e62a14472f637b6737ba3022b4b9b4221d930a11cd3d103ef76b14192",
    ),
)

EXPECTED_MARKER_COUNTS = {"G40": 3, "G42": 6}

AMENDMENT_PARAGRAPH_SHA256 = {
    "G40": "82d2ed9632ea9bf4b61407e97c8e9cbfea4bb4bad21ba7b22059ec542e8e8009",
    "G41": "dc3f48c62ee5171c09e4f74d1b326113ca3a9eb31b3c8d7476716f3cd7f7802b",
    "G42": "bad232fb7568b104539d20e8ac0067d67beed1c2bff66ec0f222cc805c003d5d",
    "FR100": "41fde4565a0f8a8a3568695582e2d185258f3af315168fc6a3fb0a2f136c21a9",
}

HEADER_LITERALS = (
    "**Revised**: 2026-10-06",
    "**Status**: Draft (Revision 22)",
)

REVIEWED_WEAKENINGS = (
    ("G40", "runs the byte-identical", "may run a modified"),
    ("G40", "exactly its Git work-tree top level", "inside any Git work tree"),
    ("G40", "working-tree spec bytes are never used", "working-tree spec bytes may be used"),
    ("G40", "MUST refuse and MUST NOT fall back", "MAY fall back"),
    ("G40", "Only a genuinely non-Git root", "Any root"),
    (
        "G40",
        "DM-016-pinned SHA-256 "
        "`7741b877b1ed45047d680a077c5303b2314cd1f3ef0339821bd7105ac9acd5c9`",
        "DM-016-pinned SHA-256 "
        "`0741b877b1ed45047d680a077c5303b2314cd1f3ef0339821bd7105ac9acd5c9`",
    ),
    ("G40", "only then may it parse", "it may parse before checking"),
    (
        "G40",
        "b2b7157e42fa6622091c2fd02567379068f76eb5daf67e0969861184a8230001",
        "02b7157e42fa6622091c2fd02567379068f76eb5daf67e0969861184a8230001",
    ),
    ("G40", "decode as strict UTF-8", "decode with replacement"),
    ("G40", "replaces only their committed-spec reader", "may replace evaluator checks"),
    ("G40", "then runs unchanged", "may be skipped"),
    (
        "G40",
        "proves self-consistency of the installed tree, not authenticity or provenance",
        "proves authenticity of the installed tree",
    ),
    (
        "G40",
        "remain byte-identical and are neither copied nor re-minted",
        "may be copied or re-minted",
    ),
    ("G41", "byte-for-byte equal", "structurally equivalent"),
    (
        "G41",
        "3d1be7b789a8ee5cc7b5f65ac7f77a5ce3622fe0214a09650c85424c91147d93",
        "0d1be7b789a8ee5cc7b5f65ac7f77a5ce3622fe0214a09650c85424c91147d93",
    ),
    (
        "G41",
        "9ad0623e2eb7c9d56df44a0c57cb4c7c79e30e4322d9bbc0ea2e50b8817c3ce2",
        "0ad0623e2eb7c9d56df44a0c57cb4c7c79e30e4322d9bbc0ea2e50b8817c3ce2",
    ),
    (
        "G41",
        "45e2e69e0067f06f99cb0e3d42f185d3fdc8ee45f6961100eb51f3298c9500c3",
        "05e2e69e0067f06f99cb0e3d42f185d3fdc8ee45f6961100eb51f3298c9500c3",
    ),
    ("G41", "and every other body remain malformed", "is also admitted"),
    (
        "G41",
        "current canonical row's patterns followed by every pattern present",
        "authenticated base row's patterns alone",
    ),
    ("G41", "without duplication", "with duplicates permitted"),
    (
        "G41",
        "authenticated base region's own exact bytes",
        "effective trigger rows",
    ),
    (
        "G41",
        "No admitted superseded table can therefore narrow current coverage",
        "An admitted superseded table may narrow current coverage",
    ),
    (
        "G41",
        "non-admitted base region retains required fresh-evaluation applicability",
        "non-admitted base region is unconfigured",
    ),
    (
        "G41",
        "an admitted superseded body does not by itself justify that skip",
        "an admitted superseded body justifies that skip",
    ),
    ("G41", "MUST append", "MAY append"),
    ("G42", "exactly one", "zero or more"),
    ("G42", "it is not a region", "it is the seventeenth region"),
    ("G42", "never to weaken a gate or expand authority", "to override any gate"),
    ("G42", "forward byte-for-byte", "forward after normalization"),
    ("G42", "prior header `Install date` forward", "current date into the header"),
    (
        "G42",
        "in-region project-spine marker refuses before mutation",
        "in-region project-spine marker refuses after mutation",
    ),
    (
        "G42",
        "preserved byte-for-byte as `forge-project.md.forge-prev`",
        "discarded",
    ),
    ("G42", "reported as a blocking init collision", "reported as a warning"),
    (
        "G42",
        "removes only the fresh contiguous addenda stanza from its fixed heading through "
        "the END-marker line and its single following separator blank line",
        "compares the fresh stanza as legacy divergence",
    ),
    (
        "G42",
        "existing `.forge-prev` is accepted idempotently only when it is a regular "
        "non-symlink whose bytes equal the legacy file being preserved",
        "existing `.forge-prev` may be overwritten",
    ),
    (
        "G42",
        "before the first target-repository mutation",
        "after forge-project.md is written",
    ),
    (
        "G42",
        "every existing `.codex/hooks.json` or `.codex/config.toml` input",
        "only forge-managed Codex inputs",
    ),
    (
        "G42",
        "regular non-symlink strict UTF-8 file of at most 1 MiB",
        "readable file of unbounded size",
    ),
    ("G42", "a duplicate JSON key", "duplicate JSON keys are accepted"),
    (
        "G42",
        "an oversized input, or a hooks-shape violation refuses before any mutation",
        "an oversized or shape-invalid input may continue",
    ),
    (
        "G42",
        "every group has a `hooks` array of handler objects; and every handler has a "
        "string `command`",
        "groups and handlers may have any shape",
    ),
    ("G42", "removes all prior plugin-owned handlers", "keeps stale plugin handlers"),
    (
        "G42",
        "retained when at least one foreign handler remains or when the group has any "
        "member other than `hooks`",
        "retained only when a foreign handler remains",
    ),
    (
        "G42",
        "only an empty hooks-only residual is dropped",
        "every handler-empty residual is dropped",
    ),
    (
        "G42",
        "fresh template's events, groups, and handlers first in template order",
        "foreign entries first in implementation-defined order",
    ),
    (
        "G42",
        "it next emits prior events absent from the template, with their retained residual "
        "groups, in prior event and group order",
        "it next emits prior events in arbitrary order",
    ),
    (
        "G42",
        "preserving every foreign handler, group member, event, and top-level member",
        "may discard foreign handlers",
    ),
    ("G42", "Every template handler MUST carry", "A template handler MAY omit"),
    (
        "G42",
        "foreign project SessionStart handler is outside the Forge layer and is preserved",
        "foreign project SessionStart handler is removed",
    ),
    (
        "G42",
        "any content outside that namespace or any project-added member under `agents.*`",
        "only malformed content",
    ),
    (
        "G42",
        "keep the existing `.codex/config.toml` byte-for-byte",
        "replace the existing `.codex/config.toml`",
    ),
    (
        "G42",
        "every other comment is foreign content and takes the same collision path",
        "project comments may be discarded",
    ),
    ("G42", "Missing `tomllib` takes that same collision path", "Missing `tomllib` is ignored"),
    ("G42", "malformed TOML still refuses during preflight", "malformed TOML collides"),
    (
        "G42",
        "Valid unmarked non-Forge Codex files retain their existing collision behavior",
        "unmarked Codex files are merged",
    ),
    (
        "G42",
        "valid FR-184 upstream-signature inputs retain backup-and-replace behavior",
        "upstream-signature migration merges",
    ),
    (
        "G42",
        "existing `.forge-new` is accepted idempotently only when it is a regular "
        "non-symlink with bytes equal to the fresh template",
        "an existing `.forge-new` may be overwritten",
    ),
    ("FR100", "Since 0.6.11", "Since 0.7.0"),
    ("FR100", "absolute symlink targets", "selected absolute symlink targets"),
    ("FR100", "anywhere in the whole tree", "only in changed paths"),
)


def authority_marker(task: str) -> str:
    return f"(Revision 20 authority; deferred to task {task} of {RUN_ID})"


def expected_marker(task: str) -> str | None:
    return authority_marker(task) if task in DEFERRED else None


def strip_markers(text: str) -> str:
    return re.sub(r" ?\(Revision 20 authority;[^)]*\)", "", text).rstrip()


def amendment_paragraph(document: str, owner: str) -> str:
    heading = HEADINGS[owner]
    matches = [part for part in document.split("\n\n") if part.startswith(heading)]
    if len(matches) != 1:
        raise AssertionError(f"expected one {owner} amendment, found {len(matches)}")
    return matches[0]


def line_containing(document: str, needle: str) -> str:
    matches = [line for line in document.splitlines() if needle in line]
    if len(matches) != 1:
        raise AssertionError(f"expected one line containing {needle!r}, found {len(matches)}")
    return matches[0]


def assert_header(document: str) -> None:
    lines = document.splitlines()
    if tuple(lines[3:5]) != HEADER_LITERALS:
        raise AssertionError("Revision-20 header lines moved or reordered")
    for literal in HEADER_LITERALS:
        if lines.count(literal) != 1:
            raise AssertionError(f"Revision-20 header literal changed: {literal!r}")


def assert_amendments(document: str) -> None:
    for owner, literals in AMENDMENT_LITERALS.items():
        paragraph = amendment_paragraph(document, owner)
        for literal in literals:
            if literal not in paragraph:
                raise AssertionError(f"{owner} authority lacks {literal!r}")
        markers = MARKER_RE.findall(paragraph)
        marker = expected_marker(owner) if owner == "G40" else None
        expected = [marker] if marker else []
        if markers != expected:
            raise AssertionError(f"{owner} markers {markers!r} != {expected!r}")
        if expected and not paragraph.endswith(expected[0]):
            raise AssertionError(f"{owner} marker does not end its paragraph")


def assert_amendment_digests(document: str) -> None:
    for owner, expected in AMENDMENT_PARAGRAPH_SHA256.items():
        paragraph = strip_markers(amendment_paragraph(document, owner))
        digest = hashlib.sha256(paragraph.encode()).hexdigest()
        if digest != expected:
            raise AssertionError(f"{owner} Revision-20 amendment changed: {digest}")


def assert_cross_cutting_lines(document: str) -> None:
    for task, needle, expected_digest in CROSS_CUTTING_LINES:
        line = line_containing(document, needle)
        marker = expected_marker(task)
        markers = MARKER_RE.findall(line)
        expected_markers = [marker] if marker else []
        if markers != expected_markers:
            raise AssertionError(f"{task} cross-cutting markers are wrong")
        marker_is_final = not marker or line.endswith(marker) or line.endswith(f"{marker} |")
        if not marker_is_final:
            raise AssertionError(f"{task} cross-cutting marker is misplaced")
        digest = hashlib.sha256(strip_markers(line).encode()).hexdigest()
        if digest != expected_digest:
            raise AssertionError(f"cross-cutting line {needle!r} changed: {digest}")


def assert_global_markers(document: str) -> None:
    actual = MARKER_RE.findall(document)
    expected = []
    for task, count in EXPECTED_MARKER_COUNTS.items():
        expected.extend([authority_marker(task)] * count * bool(expected_marker(task)))
    if sorted(actual) != sorted(expected):
        raise AssertionError(f"global Revision-20 markers {actual!r} != {expected!r}")


def assert_revision20_contract(document: str) -> None:
    assert_header(document)
    assert_amendments(document)
    assert_amendment_digests(document)
    assert_cross_cutting_lines(document)
    assert_global_markers(document)


def weakening_scope(document: str, owner: str) -> str:
    if owner in HEADINGS:
        return amendment_paragraph(document, owner)
    raise AssertionError(f"unknown weakening owner {owner}")


class SpecificationRevision20Tests(unittest.TestCase):
    def test_cleanup_condition_enum_remains_exactly_closed(self) -> None:
        prose = (
            "`cleanup.condition` is exactly `none` or `cleanup-failed`; the latter retains "
            "`cleanup_pending` and admits only `status` or `merge cleanup`."
        )
        enum = "cleanup.condition = none | cleanup-failed"

        def assert_closed(document: str) -> None:
            self.assertEqual(document.count(prose), 1)
            self.assertEqual(
                re.findall(r"^cleanup\.condition = .+$", document, flags=re.MULTILINE),
                [enum],
            )

        assert_closed(SPEC)
        for literal in (prose, enum):
            with self.subTest(literal=literal), self.assertRaises(AssertionError):
                assert_closed(SPEC.replace(literal, "DISABLED_CONTROL", 1))

    def assert_mutation_detected(self, mutant: str) -> None:
        self.assertNotEqual(SPEC, mutant)
        with self.assertRaises(AssertionError):
            assert_revision20_contract(mutant)

    def test_revision20_contract(self) -> None:
        assert_revision20_contract(SPEC)

    def test_every_required_literal_is_load_bearing(self) -> None:
        for owner, literals in AMENDMENT_LITERALS.items():
            paragraph = amendment_paragraph(SPEC, owner)
            for literal in literals:
                with self.subTest(owner=owner, literal=literal):
                    self.assertIn(literal, paragraph)
                    mutated = paragraph.replace(literal, "REVISION20_LITERAL_MUTANT", 1)
                    self.assert_mutation_detected(SPEC.replace(paragraph, mutated, 1))

    def test_paragraph_and_cross_cutting_digests_reject_additive_weakening(self) -> None:
        for owner in HEADINGS:
            paragraph = amendment_paragraph(SPEC, owner)
            mutant = SPEC.replace(paragraph, f"{paragraph} Agents MAY weaken this.", 1)
            with self.subTest(owner=owner), self.assertRaisesRegex(
                AssertionError, "changed"
            ):
                assert_amendment_digests(mutant)
        for _task, needle, _digest in CROSS_CUTTING_LINES:
            line = line_containing(SPEC, needle)
            marker = MARKER_RE.findall(line)[0]
            weakened = line.replace(f" {marker}", f" Agents MAY weaken this. {marker}", 1)
            mutant = SPEC.replace(line, weakened, 1)
            with self.subTest(needle=needle), self.assertRaisesRegex(
                AssertionError, "changed"
            ):
                assert_cross_cutting_lines(mutant)

    def test_reviewed_weakenings_are_detected(self) -> None:
        self.assertEqual(len(REVIEWED_WEAKENINGS), 60)
        for owner, original, replacement in REVIEWED_WEAKENINGS:
            with self.subTest(owner=owner, original=original):
                scope = weakening_scope(SPEC, owner)
                self.assertEqual(scope.count(original), 1)
                mutated = scope.replace(original, replacement, 1)
                self.assert_mutation_detected(SPEC.replace(scope, mutated, 1))

    def test_header_literals_are_load_bearing(self) -> None:
        self.assertEqual(tuple(SPEC.splitlines()[3:5]), HEADER_LITERALS)
        for literal in HEADER_LITERALS:
            with self.subTest(literal=literal):
                self.assertEqual(SPEC.splitlines().count(literal), 1)
                self.assert_mutation_detected(SPEC.replace(literal, "REV20_HEADER_MUTANT", 1))
                relocated = SPEC.replace(f"{literal}\n", "", 1) + f"\n{literal}\n"
                self.assert_mutation_detected(relocated)
        lines = SPEC.splitlines()
        lines[3], lines[4] = lines[4], lines[3]
        reordered = "\n".join(lines) + ("\n" if SPEC.endswith("\n") else "")
        self.assert_mutation_detected(reordered)

    def test_markers_cannot_be_removed_or_moved(self) -> None:
        sites = [("G40", amendment_paragraph(SPEC, "G40"))]
        sites.extend(
            (task, line_containing(SPEC, needle))
            for task, needle, _digest in CROSS_CUTTING_LINES
        )
        for task, source in sites:
            marker = authority_marker(task)
            with self.subTest(task=task, source=source[:60]):
                self.assertEqual(source.count(marker), 1)
                removed_source = source.replace(f" {marker}", "", 1)
                removed = SPEC.replace(source, removed_source, 1)
                self.assert_mutation_detected(removed)
                moved = removed.replace(
                    "**Revised**: 2026-10-06",
                    f"**Revised**: 2026-10-06 {marker}",
                    1,
                )
                self.assert_mutation_detected(moved)

    def test_fr100_clarification_is_in_force_without_a_marker(self) -> None:
        paragraph = amendment_paragraph(SPEC, "FR100")
        self.assertEqual(MARKER_RE.findall(paragraph), [])
        self.assertIn("Since 0.6.11", paragraph)

    def test_deferred_set_can_be_emptied_only_after_all_markers_are_removed(self) -> None:
        without_markers = SPEC
        for task in DEFERRED:
            without_markers = without_markers.replace(f" {authority_marker(task)}", "")
        original = globals()["DEFERRED"]
        try:
            globals()["DEFERRED"] = frozenset()
            assert_revision20_contract(without_markers)
            if original:
                with self.assertRaises(AssertionError):
                    assert_revision20_contract(SPEC)
        finally:
            globals()["DEFERRED"] = original


if __name__ == "__main__":
    unittest.main()
