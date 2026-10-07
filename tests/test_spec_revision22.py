"""Revision 22 authority pins with an in-memory disable check for every control."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = (ROOT / "docs/specs/forge-plugin-spec.md").read_text(encoding="utf-8")

HEADER = (
    "**Status**: Draft (Revision 22)",
    "**Revised**: 2026-10-06",
    "## 5A. Record-keeping simplification (Revision 22)",
)
RETIREMENTS = (
    "FR-014 retired by Revision 22 (scope admission).",
    "FR-016..FR-019 retired by Revision 22 (journal policy enforcement, activation and "
    "transactional binding).",
    "FR-020..FR-025 retired by Revision 22 (run-close judgments and gated journal validation).",
    "DM-011 retired by Revision 22 (run scope registry and successor reconciliation).",
    "DM-001..DM-002 retired by Revision 22 (journal gate bindings and gate validation).",
    "FR-170..FR-174 retired by Revision 22 (run archives).",
    "FR-190..FR-194 retired by Revision 22 (scope registry and run ownership).",
    "FR-200..FR-205 retired by Revision 22 (learn pipeline and gotcha hydration).",
    "FR-247 retired by Revision 22 (task-completion provenance).",
    "FR-248..FR-249 retired by Revision 22 (run-close projection and "
    "result-before-gate journal admission).",
)

REQUIREMENTS = {
    "FR-160": (
        "Tracked-file category coverage of such a path is not consumption of the "
        "artefact as an input; the runner never reads its content.",
    ),
    "FR-032": (
        "The binding `review-final` role MUST additionally resolve to a different "
        "provider or model than the implementer role's resolved route",
        "`review request` for `review-final` refuses a route equal to the implementer "
        "route in both provider and model with exit 1, `state-precondition`, and exactly "
        "`forge: review request refused — review-final route equals the implementer route`",
        "The prompt MUST NOT contain the implementer's handoff, claimed test results, "
        "earlier review verdicts, or the orchestrator's tentative conclusion.",
    ),
    "FR-051": (
        "Project `file-categories` MAY extend it and MUST NOT remove or narrow any built-in entry.",
    ),
    "FR-052": (
        "`hard` changes, including every control change, `review-final-floor` match, "
        "and `trigger-paths` match, to `review-final`.",
    ),
    "FR-103": (
        "Every control-class or review-final-floor candidate MUST satisfy Recorded-baseline "
        "integrity over the complete committed `.forge/evals/tasks/` suite by a current "
        "execution;",
    ),
    "FR-034": (
        "Immediately after launch and before arming the monitor, the launcher MUST write "
        "`<execution-dir>/pid` — three lines: PID, PGID, UTC ISO-8601 launch timestamp.",
    ),
    "FR-142": (
        "Every scoped mutation result MUST be printed and supplied to the reviewer as "
        "non-gating evidence, recording command, outcome, scope, timeout and "
        "malformed-policy disposition.",
        "Optional journal references remain advisory and MUST NOT change the mutation "
        "runner's primary outcome.",
        "Untrusted mutation children MUST NOT inherit `FORGE_SESSION_PID`.",
    ),
    "FR-053": (
        "Its hard cap is eight review rounds per chain, counted across candidate generations "
        "within the chain; no verb resets it.",
    ),
    "FR-055": (
        "FR-050's review loop remains outside the repo-wide commit lock.",
        "cleanup always ends the lock epoch, even when it retains the marker and "
        "latch on mismatch.",
    ),
    "FR-250": (
        "Each run directory MUST retain one append-only `journal.jsonl`, one JSON object per line.",
        "New records carry `kind` and `run_id`, where `run_id` is a nonempty string "
        "that is not dot-prefixed and contains no path separator, NUL or control "
        "character (the existing journal run-id grammar), because it forms the run "
        "directory path: `run_started` records the repository, intent text and actor; "
        "`task` records a task id, title and free-text scope; `execution_started` and "
        "`execution_finished` record execution id, task id, role, provider, model, "
        "effort, worktree, applicable start/end times, exit status and output artefact "
        "path, with tokens when reported by the launcher; `decision` records free "
        "text, actor and optional references; `run_closed` records a free-text outcome "
        "and no judgment field.",
        "`run_closed` records a free-text outcome and no judgment field.",
        "Execution records MUST describe the route actually used, with no run-open route snapshot.",
        "Any record MAY cite chain ids and verdict paths as references, which confer no authority "
        "and are never validated against a chain.",
    ),
    "FR-251": (
        "The writer MUST append and return without checking session ownership, scope, routes, "
        "task status, chain state, reference existence, prior close or close eligibility.",
        "It MUST retain a single-writer append lock whose only journal purpose is to "
        "prevent torn or interleaved lines; FR-034 additionally serializes execution and "
        "attempt id allocation under the same lock, and the lock grants no run ownership.",
        "Its only refusals are I/O failure or a malformed envelope: a record that is "
        "not a valid JSON object, lacks `kind` or `run_id`, or carries a `run_id` "
        "outside the FR-250 grammar; an invalid run id is refused before any directory "
        "or file is created and is never echoed.",
        "Content beyond that envelope MUST NOT be a policy refusal.",
        "A failed append MUST be reported without changing any gate, landing, merge, approval, "
        "launch or run-operation decision; recorded closure is descriptive and does not seal "
        "the file against later facts.",
    ),
    "FR-252": (
        "Readers MUST preserve unknown and every pre-Revision-22 kind as opaque data and MUST "
        "NOT fail a read because a kind, field or legacy lifecycle is unfamiliar.",
        "`validate` MUST check only parseable JSON objects whose envelope is either the current "
        "`kind` plus `run_id` or the legacy `type` key alone (legacy records carry `run_id` "
        "only on `run_started`), accept unknown kinds, and never derive a judgment; "
        "`--gates` is retired.",
        "No chain verb, approval, merge, landing or run operation may read the journal to "
        "determine permission.",
    ),
    "FR-253": (
        "The built-in `control` category MUST comprise `forge-project.md`, `.forge-manifest`, "
        "`rules/**`, `agents/**`, `system/**`, `hooks/**`, `skills/**`, `.claude-plugin/**`, "
        "`.codex/**`, `.claude/settings*.json`, `.github/workflows/**`, `AGENTS.md`, "
        "`CLAUDE.md`, `docs/specs/**`, `.forge/evals/tasks/**`, "
        "`.refactor/type-baseline.json`, and `scripts/forge/route_config.py` (the "
        "committed route defaults and provider sandbox table, which can weaken the review).",
        "Project `file-categories` MAY extend this set and MUST NOT remove or narrow any "
        "built-in entry.",
        "Every control change requires `review-final` and explicit operator approval bound to "
        "the reviewed candidate; no other path under `scripts/**`, and no path under "
        "`tests/fixtures/**`, is built-in control; they classify as `python`, `bash`, "
        "`config` or `docs` by suffix unless a project explicitly extends control to them.",
    ),
    "FR-254": (
        "The built-in `review-final-floor` MUST comprise `scripts/**`, `hooks/**`, "
        "`tests/fixtures/**` and every control path, including project control extensions.",
        "A project extends this floor's review selection and no-skip rule by adding patterns "
        "to `trigger-paths` or a `hard` row in `risk-tiers`, while Recorded-baseline "
        "integrity under FR-103 applies to the built-in control set and the built-in floor "
        "only; a project MUST NOT remove or narrow the floor through `file-categories`, "
        "`risk-tiers` or `trigger-paths`.",
        "Every candidate touching it is `hard` and MUST receive `review-final` at commit "
        "and merge; only its control subset requires approval, so floor membership alone "
        "adds no approval wait.",
        "The classifier MUST record the matched built-in and project floor rows in commit "
        "evidence exactly as FR-151 records matched tier rows, and MUST classify the full "
        "new candidate after every restage.",
        "preserve existing eval and other gate triggers, and never fast-route a floor match",
        "The gate engine and commit guard remain under binding final review: removing approval "
        "wait from engine code MUST NOT route it to the cheap reviewer or weaken another gate.",
    ),
    "FR-255": (
        "After a review BLOCK, `commit restage --paths <path>...` MUST accept the revised file "
        "set in the same live chain under exactly the path rules and refusals of `commit "
        "start`; no task, run, scope or earlier path set restricts it.",
        "The engine MUST record on the restage event the superseded and new candidate "
        "identities and the exact tree delta between them (every `git diff-tree --raw` "
        "entry, with both ends of a rename).",
        "Every gate reruns on the new candidate with every exemption freshly derived; no "
        "result carries forward.",
        "Binding review reruns on the complete candidate, is told the prior candidate "
        "identity and the delta, and never inherits a verdict.",
        "A candidate change voids approval, authorization, review dispositions and every "
        "candidate-bound `commit skip` record; returning to an earlier tree restores nothing.",
        "The eight-round cap is the chain's existing per-chain review counter (FR-053, "
        "FR-216), counted across candidate generations within the chain; no verb resets it, "
        "and a new chain starts at zero.",
    ),
    "FR-210": (
        "Every state-mutating subcommand MUST run the halt check first via `check-halt.sh` "
        "and refuse while a halt sentinel is present.",
    ),
    "FR-245": (
        "the committed defaults and sandbox table in `scripts/forge/route_config.py` "
        "are control-class under FR-253, while the argv templates under "
        "`scripts/forge/forge_cli/engine/` are review-final-floor surfaces whose "
        "changes also fire the reviewer-routing fresh evaluations.",
    ),
    "FR-154": (
        "using those authenticated regions as the single committed source for every "
        "region-declared hard/standard floor together with the built-in FR-253 control set "
        "and FR-254 review-final floor, which are not region-sourced and are always applied.",
    ),
    "FR-211": ("Out-of-band index changes invalidate all older evidence.",),
    "FR-212": (
        "always invalidates review, approval, dispositions and authorization, and "
        "invalidates every mechanical result (FR-255).",
        "The new file set MAY include any path `commit start` admits, without task, "
        "run-scope or old-path-set restrictions.",
    ),
    "FR-214": (
        "records the superseded/new tree delta, invalidates every mechanical result "
        "(FR-255), and reruns classification",
    ),
    "FR-217": (
        "No skip covers control approval or mandatory review under the control category "
        "or review-final-floor.",
        "`commit skip --index-drift --reason <text>` retain their existing semantics; "
        "overriding",
    ),
    "FR-256": (
        "Existing run directories, journals and activated bindings MUST remain untouched; "
        "legacy records are readable data, and obsolete owner, registry, binding, receipt "
        "and route-snapshot fields or files MUST neither be consulted for permission nor "
        "migrated in place.",
        "Existing `.forge/history/runs/` files remain readable ordinary history, never "
        "rerendered or required; no archive backfill, archive-only chain, audit or learn "
        "pipeline runs.",
        "A consumer installed at 0.7.1 retains its bytes until a separately reviewed "
        "upgrade; after upgrading, FR-253's built-in control set and FR-254's built-in "
        "floor apply to the consumer's own paths of those names, and its `scripts/**` and "
        "`tests/fixtures/**` become hard with Recorded-baseline integrity where FR-103 "
        "applies. Such a consumer preserves project extensions through init, and receives "
        "no automatic "
        "history rewrite; the next release implementing these contracts is breaking for "
        "callers of `validate --gates`, `journal close-preflight`, `run-readmit`, "
        "`run-retire`, `journal batch-recover`, `journal ingest-chain`, "
        "`chain outbox-drain`, `commit abort-disposition`, `journal verification-add`, "
        "`commit start --archive-run-id <run-id>` including its legacy/backfill flag pairs, "
        "`worktree-check`, `archive-run.py`, `audit-commitments.py`, `journal-patterns.py`, "
        "their interpreter-loaded helper modules `archive_closing.py`, "
        "`chain_evidence_codec.py`, `commitment_paths.py`, `learn-proposals.py`, "
        "`learn-proposals-locked.py` and `route_provenance.py` (FR-247 provenance; the "
        "reviewer-facing trigger rows that name it are updated by its implementing unit "
        "under the trigger-table discipline), and `/forge:learn`.",
        "Retired options, including the former run-open and run-close judgment, scope, "
        "successor, route-snapshot and binding flags, leave the CLI grammar:",
        "`cli.py` refuses them through its argument parser with exit 1, `state-precondition` "
        "and its existing invalid-invocation diagnostic, `codex_orch_tools.py` refuses "
        "its retired run-open and run-close flags through its plain argparse usage error "
        "with exit 2 and no reason code, and `commit start` or `merge start` given the "
        "still-global `--run-id` or `--task` refuses exactly `forge: <verb> refused — "
        "--run-id and --task are not admitted` with `state-precondition`",
        "no retired flag is accepted and ignored",
    ),
}

JOURNAL_READER = (
    "A writer serializes complete line appends under the single-writer append lock and "
    "returns after writing.",
    "It does not consult session ownership, another run, a scope registry, route snapshots, "
    "chain state, references, task provenance, or prior close outcome.",
    "Execution pairing, task status, repeated run opening or closing, and referenced-path "
    "existence never make an append a policy refusal.",
    "I/O failure emits exactly `forge: journal append failed: I/O error`; an input that is "
    "not a JSON object or lacks `kind` or `run_id` emits exactly `forge: journal append "
    "refused: record must be a JSON object with kind and run_id`; a `run_id` outside "
    "the FR-250 grammar emits exactly `forge: <operation> refused — invalid run id` "
    "before any directory or file is created, and the value is never echoed.",
    "These are the only writer refusal classes: I/O failure and a malformed envelope.",
    "Known, unknown, and every legacy kind remain readable data and never require semantic "
    "replay, a chain receipt, or gate evidence.",
    "A validation result has no authority over a writer, chain, approval, merge, or run operation.",
    "a legacy `type` envelope (legacy records carry `run_id` only on `run_started`, so "
    "`run_id` is not required of them)",
    "The committed legacy fixtures under `tests/replay/` validate with no issue.",
)

OTHER_PINS = (
    "scripts/forge/{check-test-quality.py,emit-decision-event.py,route_config.py}",
    "A candidate's mechanical verification runs Gate 1 once, or records a freshly "
    "derived `docs-class candidate` skip under `gate-1` only when every path carries "
    "exactly the docs category and no control, review-final-floor or trigger match.",
    "Since Revision 22 the emitters of these strings under `scripts/forge/` are "
    "review-final-floor surfaces; the FR-223 corpus binding, not control approval, "
    "pins the strings.",
    "| `review request` for `review-final` resolves to the same provider and model "
    "as the implementer route | `review request` | exit 1, `state-precondition`, "
    "`forge: review request refused — review-final route equals the implementer route`; "
    "no request created | FR-032; the committed defaults (Codex implementer, Claude "
    "`review-final`) satisfy the rule; `review-cheap` requires only a distinct agent |",
    "Beyond the ruling's text this revision adds two mechanisms: FR-032's refusal of a "
    "`review-final` route equal to the implementer route, which makes the ruling's "
    "different-model binding review enforceable, and `scripts/forge/route_config.py` as "
    "a built-in control path, because its committed defaults can weaken the review.",
    "The Revision-18 rule that a run-bound chain runs Gate 1 for a docs-class candidate "
    "(`run-bound-gate-one`) retires with run binding, so every chain now takes the "
    "docs-class Gate 1 skip, which still excludes control, floor and trigger matches.",
    "A reader of a committed legacy drift report accepts and ignores its "
    "`journal_patterns` key; `schema_version` stays `1` because the reader rule above "
    "makes legacy and new reports interchangeable for every consumer.",
    "Revision 22 reserves the journal-only member `citation-out-of-root`; it MUST NOT "
    "be emitted. `ambiguous-target` remains live for review-disposition targets. "
    "Retained chain-artifact checks "
    "still fail closed: the chain-storage artifact-root check and the engine's "
    "artifact-path identity check use `evidence-incomplete` when a cited artifact is "
    "missing, unreadable or outside the chain root, and `state-precondition` when an "
    "input's grammar is invalid, including an invalid `--run-id` given to `launch`. "
    "A floor-only attempt to "
    "skip mandatory final review is an unadmitted transition and uses "
    "`state-precondition`, without changing the immutable `skip-not-permitted` corpus "
    "precondition.",
    "Revision 22 reserves the archive, batch, binding, ingest, journal-outbox, "
    "legacy-recovery, and run-task-binding members above; they remain immutable corpus "
    "entries and MUST NOT be emitted. The preceding paragraph is corpus history retained "
    "verbatim; since Revision 22 the FR-019 transaction diagnostics it names are retired "
    "and never emitted.",
    "Revision 22 reserves `run-scope-exceeded`; it remains an immutable corpus entry "
    "and MUST NOT be emitted.",
    "Revision 22 reserves `execution-result-pending` and `lzma-unavailable`; they remain "
    "immutable corpus entries and MUST NOT be emitted, and the Revision-21 §9 renderer "
    "refusal named above is retired with the archive renderer.",
    "`iteration` is an integer from 1 through 8; and `artifact_prefix`",
    "`review` is only a skip target",
    "- **Then** every gate reruns on the new candidate with freshly derived exemptions, "
    "and no prior result carries forward\n",
    "- **Then** Gate 1, candidate-bound mechanical cells, triggered fresh-reviewer evals, "
    "every other gate and review rerun, and approval is void\n",
    "- **And** no missing, failed, skipped or stale result is silently treated as PASS\n",
    "- **And** an eighth BLOCK escalates with residual risk and permits no landing\n",
    "- Fix-in-chain: candidate file additions, deletions, renames, and arbitrary "
    "in-repository replacement paths after BLOCK under `commit start`'s path rules; the "
    "recorded identities and raw tree delta; every gate and review rerun; prior-candidate "
    "identity and full delta in review context; A-B-A cannot revive approval; the "
    "per-chain cap survives restages; mandatory merge in-lock gates remain fresh; every "
    "controlling predicate has a focused in-memory disable proof.",
    "- **SC-038**: A review BLOCK can be fixed by restaging any revised in-repository "
    "candidate in the same chain; every gate and review rerun and pass before landing, "
    "every prior approval is void, and the review cap cannot reset through restage.",
    "A chain created before Revision 22 MAY additionally carry the inert legacy keys "
    "`run_binding` and `journal_outbox`; readers MUST accept them on such chains without "
    "consulting them, and new chains omit them.",
    "After a successful push and immediately before cleanup, the workflow MUST fetch the "
    "remote default branch and prove the recorded pushed object is contained in it.",
    "It MUST freshly prove the named branch tip exists, the worktree remains attached "
    "to that branch, its HEAD equals the branch tip, its status is clean including "
    "untracked files, and its tip equals the recorded pushed object or is contained "
    "in the fetched remote default branch.",
    "A pre-removal proof failure preserves both worktree and branch; a later "
    "branch-ref proof failure preserves the branch and reports incomplete cleanup.",
    "After non-forced worktree removal and before branch deletion, it MUST re-read the branch "
    "tip, require it equal the pre-removal tip, re-prove containment, and delete exactly "
    "that object with `git update-ref -d <branch-ref> <verified-old-oid>`; it MUST NOT use "
    "`git branch -D`.",
    "A frozen commit chain MAY be sealed only by explicit operator abort or by an operator "
    "tombstone written through the operator-bound `chain tombstone` verb after commit-family "
    "proof from event authority or canonical matching raw state;",
    "`forge-chain-tombstone/1` MUST record operator identity, time, reason, and exact "
    "captured-or-absent state/event facts using crash-recoverable owner-controlled publication.",
    "Terminal guards MUST accept an authenticated tombstone only while captured artifact "
    "facts remain exact or after both artifacts are absent, and MUST reject partial or "
    "changed artifacts.",
    "| Authenticated tombstone artifacts are partial or captured state/event facts changed | "
    "terminal builder / chain selection | exit 2, `frozen-chain`; no terminal admission | "
    "Both artifacts must remain exact captured facts or both must be absent; a malformed "
    "or unsafe tombstone never seals a chain |",
    "| Commit-family replay cannot authenticate an immutable source fact, or the latest "
    "appended record set does not match its exact append state and prefix outside the "
    "authenticated `commit_produced` window | commit builder / chain replay | exit 2, "
    "`frozen-chain`; no transition | Earlier record sets remain historical and are not "
    "currentness-rejected merely because later state exists |",
    "| Caller supplies a `run_id` outside the FR-250 grammar (empty, dot-prefixed, or "
    "containing a path separator, NUL or control character) | `run-open` / journal "
    "append | exit 1, `forge: <operation> refused — invalid run id`; no directory or "
    "file created | Malformed-envelope class under FR-251; the rejected value is never echoed |",
)

ERROR_CONTRACT_PREAMBLE = (
    "Raw exceptions and unvalidated caller-supplied IDs, paths, or record values MUST NOT "
    "appear in output.",
    "only as an escaped single-line JSON string literal",
    "a value that fails pathspec field validation remains un-echoed",
    "never agent strings or raw caller-supplied paths",
)

FROZEN_REVISION21_LINES = (
    "Revision-21 amendment to **DM-016**: the new `lzma-unavailable` reason reserves the "
    "next additive reason-code generation after v5. Its exact inventory is "
    "`system/fr223/reason-codes-v6.json`, `.forge/evals/tasks/fr223-reason-code-enum-v6.md`, "
    "`.forge/evals/tasks/fr223-reason-code-enum-v6.result`, and "
    "`.forge/evals/tasks/fr223-reason-code-enum-v6.manifest.json`. The corpus schema is "
    "`fr223-reason-codes/6`; the manifest schema is `fr223-reason-code-enum-manifest/6`; "
    "its predecessor array binds generations 1 through 5 in order under the same immutable "
    "predecessor discipline; and no v1-v5 artifact or row is edited or reminted. "
    "(Revision 21 authority; deferred to task TA of run-20261004-backfill)",
    "Revision-21 `forge-cli/2` reason-union amendment to **FR-220**: no existing reason "
    "member is broadened to cover compression capability. The additive "
    "`fr223-reason-codes/6` corpus is the complete sorted 56-member union: every v5 row "
    "byte-identical plus exactly `lzma-unavailable` with exit class 1 and exact failed "
    "precondition `Required Revision-21 XZ compression reached its import point and the "
    "Python standard-library lzma module is unavailable`. The Revision-21 renderer "
    "refusal in §9 uses this reason code when surfaced through `forge-cli/2`. "
    "(Revision 21 authority; deferred to task TA of run-20261004-backfill)",
)

RETIRED_LITERALS = (
    "inherited_rounds",
    "inherited base",
    "review-cap",
    "unsafe path",
    "applicability proof",
    "selective reuse",
    "applicability record",
    "carry-forward proof",
    "delta-trigger",
    "safe repository path",
    "carries forward only",
    "never reset by aborting or starting another chain",
)

LEGACY_JOURNAL = ROOT / "tests/replay/long-run-001/journal.jsonl"


def requirement_block(document: str, requirement: str) -> str:
    pattern = rf"(?m)^- \*\*{re.escape(requirement)}\*\*.*$"
    matches = re.findall(pattern, document)
    if len(matches) != 1:
        raise AssertionError(f"expected one {requirement}, found {len(matches)}")
    return matches[0]


def journal_section(document: str) -> str:
    marker = "### Journal writer and structural reader\n"
    if document.count(marker) != 1:
        raise AssertionError("expected one journal reader section")
    return document.split(marker, 1)[1].split("\n### ", 1)[0]


def error_contract_preamble(document: str) -> str:
    marker = "## 9. Error Contract\n"
    if document.count(marker) != 1:
        raise AssertionError("expected one error contract section")
    return document.split(marker, 1)[1].split("\n| Condition |", 1)[0]


class SpecificationRevision22Tests(unittest.TestCase):
    def assert_pins(self, document: str) -> None:
        for literal in (*HEADER, *RETIREMENTS, *OTHER_PINS):
            self.assertEqual(document.count(literal), 1, literal)
        for line in FROZEN_REVISION21_LINES:
            self.assertEqual(document.splitlines().count(line), 1, line)
        for requirement, literals in REQUIREMENTS.items():
            block = requirement_block(document, requirement)
            for literal in literals:
                self.assertEqual(block.count(literal), 1, (requirement, literal))
        section = journal_section(document)
        for literal in JOURNAL_READER:
            self.assertEqual(section.count(literal), 1, literal)
        preamble = error_contract_preamble(document)
        for literal in ERROR_CONTRACT_PREAMBLE:
            self.assertEqual(preamble.count(literal), 1, literal)

    def test_revision22_controls_are_load_bearing(self) -> None:
        self.assert_pins(SPEC)
        literals = [*HEADER, *RETIREMENTS, *OTHER_PINS, *FROZEN_REVISION21_LINES]
        literals.extend(literal for group in REQUIREMENTS.values() for literal in group)
        literals.extend(JOURNAL_READER)
        literals.extend(ERROR_CONTRACT_PREAMBLE)
        for literal in literals:
            with self.subTest(literal=literal), self.assertRaises(AssertionError):
                self.assert_pins(SPEC.replace(literal, "DISABLED_CONTROL"))

    def assert_retired_absent(self, document: str) -> None:
        for literal in RETIRED_LITERALS:
            self.assertNotIn(literal, document, literal)

    def test_retired_fix_in_chain_mechanisms_are_absent(self) -> None:
        self.assert_retired_absent(SPEC)
        for literal in RETIRED_LITERALS:
            with self.subTest(literal=literal), self.assertRaises(AssertionError):
                self.assert_retired_absent(SPEC + literal)

    def assert_legacy_envelopes(self, lines: list[str]) -> None:
        self.assertTrue(lines)
        for number, line in enumerate(lines, 1):
            record = json.loads(line)
            self.assertIsInstance(record, dict)
            self.assertTrue(
                ("kind" in record and "run_id" in record) or "type" in record,
                f"line {number} lacks a current or legacy envelope",
            )

    def test_legacy_replay_fixture_has_promised_envelopes(self) -> None:
        lines = LEGACY_JOURNAL.read_text(encoding="utf-8").splitlines()
        self.assert_legacy_envelopes(lines)
        for disabled in ("{}", "[]"):
            with self.subTest(disabled=disabled), self.assertRaises(AssertionError):
                self.assert_legacy_envelopes([disabled, *lines[1:]])
