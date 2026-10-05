from __future__ import annotations

import hashlib
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = (ROOT / "docs/specs/forge-plugin-spec.md").read_text(encoding="utf-8")

# Task TZ removes task markers and flips this set to empty after those implementations land.
DEFERRED = frozenset({"T1", "T2a", "T3", "T5b", "T6"})
RUN_ID = "run-20261003-archive"
BEAD_OWNER = "bead:forge-plugin-c2i8"
MARKER_RE = re.compile(r"\(Revision 19 authority;[^)]*\)")

HEADINGS = {
    "T1": "Revision-19 historical-binding amendment to **DM-001** and **FR-171**:",
    "T2a": "Revision-19 backfill amendment to **FR-172**:",
    "T3": "Revision-19 judgment amendment to **FR-172**:",
    "T5b": "Revision-19 recorded-repository amendment to **FR-019**:",
    "T6": "Revision-19 cleanup-deferral amendment to **FR-064**:",
    "T8": "Revision-19 archive-changelog amendment to **FR-214** and **FR-018**:",
}
AMENDMENT_HEADINGS = {
    **HEADINGS,
    BEAD_OWNER: "Revision-19 renderer-version amendment to **DM-008** and **FR-173**:",
}

BLOCKED_ADMISSION_SENTENCE = (
    "`judgment: blocked` is admitted only in backfill mode with `judgment blocked` in the "
    "approval and only while the run is gate-clean; the closing HEAD may equal the archive "
    "HEAD for a blocked run, while normal and legacy modes keep refusing non-passed runs."
)
LANDED_COMMIT_SENTENCE = (
    "Every `chain-landing`-bound chain in the captured package MUST yield exactly one landed "
    "commit—commit chain `commit_result.commit_sha` or merge chain "
    "`integration.push.landed_head`—with tombstoned chains excluded."
)
JUDGMENT_PROVENANCE_SENTENCE = (
    "Every archive's provenance prints after the closing-head lines "
    "`Run judgment: <passed|blocked>` and `Run summary: <summary>`."
)
WORKTREE_PRESERVATION_SENTENCE = (
    "Cleanup proceeds only on exit 0; guard exit 1 or 2 preserves the worktree and branch."
)

TASK_LITERALS = {
    "T1": (
        "runs every DM-001 replay proof and skips only the currency check",
        "`historical-binding-replay`",
        "`BUILDER_VALIDATION_CONTROLS`",
        '`{"binding": ..., "currency": ...}`',
        "a bare dict passed to the archive refuses",
        "a source scan MUST prove that the archive renderer is its only caller",
        "`historical-binding` → `superseded candidate`",
        "`historical-abort` → `aborted chain`",
        "`historical-recheck` → `failed gate cleared by passing recheck`",
        "`historical-rerun` → `earlier run of the same step`",
        "Resolution is two-pass: every current binding first",
        "every current binding first as a terminal anchor",
        "then every non-current binding",
        "The historical classes are evaluated after every current binding has resolved.",
        (
            "`superseded candidate` means the binding ID is in "
            "`journal._superseded_binding_ids(records)` and replay shows that the chain's "
            "candidate changed at an event after the record's source event."
        ),
        (
            "`aborted chain` means the chain's final state is a terminal abort with a null "
            "outbox and the journal holds a current carried `chain-abort` decision for that "
            "chain and task; this class applies to any record of that chain, current or not."
        ),
        (
            "`failed gate cleared by passing recheck` means a `failed` gate verification on "
            "the chain's final candidate is followed by a `passed` verification with the "
            "identical criterion on the same `(chain, candidate)` whose binding resolves current."
        ),
        (
            "`earlier run of the same step` means a non-newest record of a step on the final "
            "candidate whose newest same-criterion record on the same `(chain, candidate)` "
            "resolves current."
        ),
        "chain-side and journal-side classes agree by selecting the same historical class",
        "A non-current binding is historical only when its chain is terminal",
        "`closed`",
        "`chain-landing`",
        "`chain-abort`",
        (
            "`forge: archive refused — authoritative chain discrepancy: "
            "structured_chain_mismatch`"
        ),
        (
            "`BOUND — source-authenticated history; NOT LANDING EVIDENCE "
            "(<reason>; <binding-id>)`"
        ),
        "`superseded candidate`",
        "`aborted chain`",
        "`failed gate cleared by passing recheck`",
        "`earlier run of the same step`",
        (
            "in precedence order, `superseded candidate`, `aborted chain`, `failed gate "
            "cleared by passing recheck`, or `earlier run of the same step`"
        ),
        "A current record retired by a carried chain abort also uses `aborted chain`",
        "`BOUND (<binding-id>)`",
        "no DM-001 discrepancy code",
        "append-time, ingest, terminal-guard, and close-law currency remain unchanged",
        "`Candidate` column",
        "`git-tree-candidate-v2`",
        "64-hex `authorization_id`",
    ),
    "T2a": (
        "`--backfill-closing-head <full-object-id>`",
        "`--backfill-approval <approval-run-id>:<decision-id>`",
        "is mutually exclusive with `--closing-head`",
        (
            "and with the legacy pair `--legacy-recovered-head <full-object-id>` and "
            "`--legacy-approval <recovery-run-id>:<decision-id>`"
        ),
        (
            "is accepted identically by `scripts/forge/archive-run.py` and "
            "`forge commit start --archive-run-id <run-id>`"
        ),
        (
            "`python3 \"${CLAUDE_PLUGIN_ROOT}/scripts/forge/cli.py\" "
            "commit start ...`"
        ),
        "The approval run is the open run holding the decision",
        "the target run is the run being archived",
        "open, activated run owned by the current session",
        "legacy-approval proof machinery",
        (
            "`backfill-archive: <target-run-id> closing HEAD <closing-oid>; "
            "archive HEAD <archive-oid>; judgment <passed|blocked>; <reason>`"
        ),
        "`<reason>` is nonempty and single-line",
        (
            "`approval-binding` treats an approval as mismatched unless it compares equal on "
            "the target run ID"
        ),
        (
            "approved closing HEAD, approved archive HEAD, and judgment equal to "
            "`run_closed.judgment`"
        ),
        (
            "the named decision exists with `outcome: operator_approval` in an open, "
            "activated run owned by the current session"
        ),
        "`BACKFILL_CONTROLS`",
        "Their positionally corresponding exact refusals",
        (
            "the first failing control in that exact `BACKFILL_CONTROLS` order supplies "
            "the sole refusal"
        ),
        "`forge: archive refused — backfill approval missing or mismatched`",
        (
            "`forge: archive refused — repository HEAD is not the approved "
            "archive HEAD`"
        ),
        (
            "`forge: archive refused — backfill closing HEAD equals archive HEAD "
            "for a passed run`"
        ),
        (
            "`forge: archive refused — backfill closing HEAD is not an ancestor "
            "of archive HEAD`"
        ),
        (
            "`forge: archive refused — backfill closing HEAD does not contain "
            "starting HEAD`"
        ),
        "`forge: archive refused — could not authenticate every landed run commit`",
        (
            "`forge: archive refused — backfill closing HEAD does not contain "
            "landed commit <full-object-id>`"
        ),
        (
            "`forge: archive refused — basis document changed after closing HEAD: "
            "<label>`"
        ),
        "`forge: archive refused — backfill closing HEAD postdates run_closed`",
        (
            "`forge: archive refused — backfill closing HEAD is not the last "
            "commit before run_closed`"
        ),
        "`forge: archive refused — archive HEAD predates run_closed`",
        (
            "`forge: archive refused — blocked judgment requires an approved "
            "backfill archive`"
        ),
        "committer timestamps as repository-native evidence, not attested wall clock",
        (
            "`closing-time-order` always requires the closing commit to be committed at or "
            "before `run_closed.recorded_at`."
        ),
        (
            "Only when the closing HEAD differs from the archive HEAD, "
            "`closing-identification` requires the closing commit's first-parent successor on "
            "the path to the archive HEAD to be committed after `run_closed.recorded_at`"
        ),
        (
            "`archive-time-order` requires the archive HEAD to be committed at or after "
            "`run_closed.recorded_at`."
        ),
        (
            "When the closing HEAD equals the archive HEAD, which is admitted only for a "
            "blocked run, no successor exists and both `closing-identification` and "
            "`archive-time-order` are satisfied by that equality; only "
            "`closing-time-order` applies."
        ),
        (
            "Basis stability (`basis-stability`) means that, for every basis document path "
            "tracked in the closing HEAD tree or the archive HEAD tree, "
            "`git diff --quiet <closing-oid> <archive-oid> -- <path>` succeeds; untracked "
            "basis documents are read from the working tree as today."
        ),
        LANDED_COMMIT_SENTENCE,
        (
            "`Closing-head status: recovered after run_closed; not a "
            "contemporaneous FR-172 capture`"
        ),
        "existing 9-key set stays valid for in-flight chains",
        "the archiving HEAD is a recorded rerender input and is never re-read",
        BLOCKED_ADMISSION_SENTENCE,
        "a blocked run whose journal is otherwise valid refuses exactly",
        "`forge: archive refused — invalid run journal` first",
        "legacy recovery approval missing or mismatched` precedes the blocked-judgment refusal",
        (
            "Gate-clean means the run's embedded pre-close validation payload and the "
            "post-close validation payload supplied by `--post-close-validation` are passing "
            "gated payloads (`profile: \"gates\"`, `ok: true`) and each equals its fresh "
            "recomputation."
        ),
        "`render_archive`",
        "delegates its repository check to the Revision-19 recorded-repository resolver",
        "admits the absent-worktree archive path only when it runs from the main checkout",
        "where the state root equals the repository root",
        "prints immediately after `Starting HEAD:`",
        (
            "`Recorded repository: absent worktree <path relative to the state root>; "
            "resolved to the state root`"
        ),
        "a non-UTF-8-encodable character refuses exactly",
        "instead. A linked-worktree invocation does not print that line",
        (
            "`forge: archive refused — closing HEAD does not match repository HEAD`"
        ),
    ),
    "T3": (
        "`Run judgment: <passed|blocked>`",
        "`Run summary: <summary>`",
        JUDGMENT_PROVENANCE_SENTENCE,
        "A present `<summary>` is exactly one canonical JSON string literal",
        "including its surrounding double quotes",
        r'`"` and `\` become `\"` and `\\`',
        (
            r"U+0008, U+0009, U+000A, U+000C, and U+000D become `\b`, `\t`, `\n`, "
            r"`\f`, and `\r`"
        ),
        r"every other U+0000..U+001F scalar becomes lowercase `\u00xx`",
        (
            r"every unpaired surrogate code point U+D800..U+DFFF becomes the six ASCII "
            r"characters `\u` followed by its four lowercase hexadecimal digits (for example, "
            r"U+D800 becomes `\ud800`)"
        ),
        "every other Unicode scalar is emitted unescaped as UTF-8",
        "This literal is the one escaped block",
        "it occupies only the remainder of that one physical `Run summary: ` line",
        "whose terminating LF is the delimiter and is not part of the summary",
        "`None recorded`",
        "a backfilled run's delivery range is its starting HEAD to its backfill closing HEAD",
        "an archived blocked run may have `report.md`",
    ),
    "T5b": (
        "The reader map is explicit rather than governed by one resolver",
        '`RECORDED_REPOSITORY_LEGS = {"absent-worktree"}`',
        "Repository root means the Git toplevel of the `--repo` checkout",
        (
            "State root is the parent directory of the Git common directory (the main "
            "checkout's root; equal to the repository root when run from the main checkout)."
        ),
        "The journal writer and typed builders use `journal._recorded_repository_root`",
        "it first requires a leading `run_started`",
        (
            "then handles the pre-coordination case, then delegates every non-null `repo` "
            "to `recorded_repository.resolve`"
        ),
        "an omitted `repo` and explicit `repo: null` are identical",
        (
            "either resolves to the state root only when the `scope` key is absent, preserving "
            "the existing pre-coordination behavior"
        ),
        "either is a recorded-repository failure when the `scope` key is present",
        "The resolver itself has present, eligible-absent, and failure outcomes.",
        (
            "A present recorded path resolves strictly through symlinks to a directory inside "
            "a Git checkout whose Git common directory equals the caller's Git common directory, "
            "and resolves to that checkout's toplevel"
        ),
        (
            "the caller's common directory comes from the caller's own repository, never from "
            "the state root"
        ),
        (
            "A recorded subdirectory, which `run-open` admits, therefore resolves to its "
            "checkout toplevel"
        ),
        "Comparison with the caller uses that repository root, not the raw `--repo` spelling",
        "and only an `lstat` `FileNotFoundError` or `ENOTDIR`",
        "`<state root>/.worktrees/`",
        "`<state root>/.codex-orchestrator/runs/<run-id>`",
        "resolves to the state root only when the recorded path is absolute",
        "absolute, normalized, and strictly below `<state root>/.worktrees/`",
        "strictly below `<state root>/.worktrees/`",
        "the run directory is exactly `<state root>/.codex-orchestrator/runs/<run-id>`",
        "Everything else is a resolution failure.",
        "The commitment audit calls the resolver directly for a run in the fixed layout",
        "a fixed-layout pre-coordination journal refuses with exit 2",
        "`run_started repo must name an existing absolute directory`",
        (
            "an out-of-layout run directory retains its legacy existing-absolute-directory "
            "resolution"
        ),
        "`forge-plugin-9acq`",
        "`journal batch-recover` first strictly resolves its supplied `--repo` directory",
        "no branch reachable from `recover_batch` calls `_recorded_repository_root`",
        "Four direct `batch.py` raw consumers plus one indirect `journal.py` scan consumer",
        "`_repair_receipt_gap_locked`, only after proving one repairable interior receipt gap",
        "`_recover_scope_change_locked`, for pending readmission",
        "`_recover_spent_legacy_activation_locked`, for spent legacy activation",
        "each compare the raw leading `run_started.repo` exactly with `str(repository)`",
        "the gap helper's early-return paths perform no comparison",
        "`batch._validate_repair_receipts`", "`journal._validate_adopted_receipt_coverage`",
        "use it only to deterministically rederive the repair receipt",
        "neither resolves it nor compares it with the caller",
        "`forge: journal batch recovery refused — journal diverged from intent`",
        "`_recover_current_locked` and `_ensure_recovery_owner`",
        "makes no recorded-repository comparison",
        "`worktree-check` does not use the resolver",
        "it treats an omitted or null `repo` as the state root",
        "requires a nonempty absolute string",
        (
            "applies `os.path.realpath`, and treats the recorded repository as a dependency "
            "exactly when it is at or below the strictly resolved cleanup target"
        ),
        "Only for an existing leading `run_started`",
        "fails resolution or differs from the caller's repository root",
        "journal writer, typed builders, and four `batch.py` mismatch sites",
        (
            "`forge: journal append refused — recorded repository unavailable for "
            "run <run-id>`"
        ),
        (
            "At those named journal-writer, typed-builder, and four `batch.py` sites, these "
            "resolution and mismatch cases never report `run registry unavailable`"
        ),
        (
            "`scripts/forge/forge_cli/chain_core/_chain_batch_carrier.py::"
            "_validate_chain_batch_target` keeps its existing mismatch refusal `forge: new run "
            "refused — run registry unavailable`"
        ),
        "In the same module, `_prevalidate_chain_batch_carrier`",
        "propagates the shared recorded-repository-unavailable diagnostic on resolution failure",
        (
            "keeps its combined mismatch refusal `forge: journal append refused — invalid "
            "journal record` when resolution succeeds and the recorded repository differs"
        ),
        (
            "A journal without a leading `run_started` retains its existing "
            "`run registry unavailable` refusal."
        ),
        (
            "the archive renderer keeps `forge: archive refused — run repository does not "
            "match current repository`"
        ),
        (
            "approval proof keeps `forge: archive refused — legacy recovery approval missing "
            "or mismatched` or `forge: archive refused — backfill approval missing or "
            "mismatched`"
        ),
        (
            "a `worktree-check` input failure keeps exit 2 with `forge: worktree check "
            "refused — unreadable input`"
        ),
        (
            "a successfully resolved recorded repository that is not at or below the cleanup "
            "target is not a recorded-repository dependency"
        ),
    ),
    "T6": (
        (
            "`python3 \"${CLAUDE_PLUGIN_ROOT}/scripts/codex_orch_tools.py\" worktree-check "
            "--repo <repo> --worktree <path>`"
        ),
        "the workflow MUST run",
        "the cleanup worktree supplied as an absolute path",
        "Cleanup proceeds only on exit 0",
        WORKTREE_PRESERVATION_SENTENCE,
        "Exit 0 means nothing depends on the worktree",
        "Exit 1 is only the deferral result",
        (
            "Every other failure, including an unexpected error, exits 2 and prints as its "
            "first stderr line exactly `forge: worktree check "
            "refused — unreadable input`"
        ),
        (
            "when unreadable input is attributable to a validated run, it adds exactly the "
            "second line `forge: worktree check refused — run <run-id>`"
        ),
        "The bytewise scan of `<state root>/.codex-orchestrator/runs/`",
        "silently skips a child only when it is either a non-dot regular file",
        "completely empty, ownerless, and lacks `journal.jsonl`",
        "the guard does not consult the registry to recognize that placeholder",
        "A real directory containing `journal.jsonl` is scanned", "Every child DM-011 refuses",
        "owner-bearing or otherwise nonempty journal-less directory",
        "symlinked, empty, malformed, unreadable, or non-regular journal",
        "any scan, race, or inspection error", "`HEAD:.forge/history/runs/<run-id>.md`",
        "`os.path.realpath`-resolved recorded repository is at or below",
        "Cited evidence means every FR-017 citation surface",
        "`execution.prompt`, `execution.events`, `execution.handoff`",
        "`execution_result.handoff`", "every `verification.evidence[]` entry",
        "every path-like token in `decision.basis[]`",
        "every path token in `verification.observation`",
        "all selected by FR-017's shared tokenizer",
        "A relative citation uses FR-017's ordered roots",
        "the run directory first, then the run's layout-derived repository root",
        "with the first anchored spelling decisive",
        "a historical absolute citation resolves from its absolute spelling",
        "the first in bytewise run-id order is reported",
        "`<run-id>` is a validated journal identifier",
        "`<worktree-relative-path>` is relative to the state root",
        "a C0 control (U+0000..U+001F), DEL (U+007F), a C1 control (U+0080..U+009F)",
        "a filesystem byte that cannot be decoded as UTF-8 refuses with exit 2",
        "Each run-directory name is checked when the bytewise journal scan reaches it",
        "even where `journal._valid_run_id` would accept it",
        "the first dependency is reported without checking later names",
        (
            "`forge: worktree cleanup deferred — run <run-id> has no committed "
            "archive and depends on <worktree-relative-path>`"
        ),
        '`WORKTREE_GUARD_LEGS = {"recorded-repo", "cited-evidence"}`',
        ('`WORKTREE_INPUT_CONTROLS = {"symlinked-runs-root", '
         '"symlinked-run-directory", "symlinked-journal"}`'),
        "whose enabled members make a symlinked runs root, run directory, or journal fail closed",
        "The deferred workflow retry is the workflow skill's post-archive re-run",
        "including a deferral first raised by standalone `/forge:worktree-merge`",
        "both `/forge:worktree-merge` cleanup and the deferred workflow retry MUST first fetch",
        "prove the recorded pushed oid is contained in it, then run the plugin-root guard",
        "After guard exit 0 and before worktree removal",
        "each MUST freshly prove the current named branch tip exists",
        "the worktree remains attached to that branch",
        "its `HEAD` equals the current branch tip",
        "its status is clean including untracked files",
        (
            "the current branch tip either equals the recorded pushed oid or is contained in "
            "the fetched remote default branch"
        ),
        "`git worktree remove` without `--force`",
        "After worktree removal and before branch deletion",
        "require it to equal the pre-removal tip",
        "re-prove its containment in the fetched remote default branch",
        "`git update-ref -d <branch-ref> <verified-old-oid>`",
        "MUST never use `git branch -D`",
        "Any pre-removal proof failure preserves both worktree and branch",
        "any post-removal branch-ref failure preserves the branch and reports incomplete cleanup",
        ("The CLI merge cleanup in `scripts/forge/forge_cli/app/_engine_cleanup.py` "
         "remains dormant"),
        "this revision does not activate `MERGE_LIFECYCLE_ACTIVE`",
        "while it is false the CLI cleanup does not run this guard",
        (
            "MUST first amend the closed `cleanup.condition` set and its state tables to "
            "carry guard exit 1 as a distinct cleanup deferral"
        ),
        (
            "map exit 1 to that deferral and exit 2 to cleanup failure, and run removal on "
            "neither result"
        ),
        ("A worktree on which a permanently unarchivable run depends—a passed run that "
         "remains unarchivable after the deferred workflow retry, a retired run, or a "
         "blocked run that is not gate-clean—may be released only as an operator-reserved "
         "cleanup under explicit terminal direction recorded as an operator decision in an "
         "open run"),
        ("agents MUST never release that worktree themselves or treat the decision as "
         "guard exit 0"),
    ),
    "T8": (
        "Archive-only commit chains do not schedule the `changelog` step",
        '`ARCHIVE_CHANGELOG_EXEMPTION = {"archive-only"}`',
    ),
}

REVIEWED_WEAKENINGS = (
    ("T2a", "only while the run is gate-clean", "always"),
    ("T2a", "`judgment: blocked` is admitted only in backfill mode",
     "`judgment: blocked` is admitted in any mode"),
    ("T2a", "normal and legacy modes keep refusing non-passed runs",
     "normal and legacy modes admit non-passed runs"),
    ("T2a", "the closing HEAD may equal the archive HEAD for a blocked run",
     "the closing HEAD may equal the archive HEAD for any run"),
    ("T6", "guard exit 1 or 2 preserves the worktree and branch",
     "guard exit 1 or 2 may discard the worktree or branch"),
    ("T2a", "with tombstoned chains excluded", "with tombstoned chains included"),
    ("T3", "prints after the closing-head lines", "prints before the closing-head lines"),
    ("T2a", "prints immediately after `Starting HEAD:`", "prints before `Starting HEAD:`"),
    ("T6", "the workflow MUST run", "the workflow MAY run"),
    ("T5b", "resolves to the state root only when the recorded path is absolute",
     "resolves to the state root when the recorded path is absolute"),
    ("T5b", "strictly below `<state root>/.worktrees/`",
     "below `<state root>/.worktrees/`"),
    ("T5b", "absolute, normalized, and strictly below `<state root>/.worktrees/`",
     "absolute and strictly below `<state root>/.worktrees/`"),
    ("T5b", "and only an `lstat` `FileNotFoundError` or `ENOTDIR`",
     "and also an `lstat` `FileNotFoundError` or `ENOTDIR`"),
    ("T5b", "The reader map is explicit rather than governed by one resolver",
     "One resolver governs every reader of `run_started.repo`"),
    ("T5b", "the run directory is exactly", "the run directory is below"),
    ("T5b", "requires a nonempty absolute string", "requires a nonempty string"),
    ("T5b", "diagnostic on resolution failure", "diagnostic on mismatch"),
    ("T5b", "`forge: journal append refused — invalid journal record`", "the registry diagnostic"),
    ("T6", '`WORKTREE_GUARD_LEGS = {"recorded-repo", "cited-evidence"}`',
     '`WORKTREE_GUARD_LEGS = {"recorded-repo"}`'),
    ("T6", "the cleanup worktree supplied as an absolute path", "a relative cleanup path"),
    ("T6", "at or below the strictly resolved cleanup target", "equal to the target"),
    ("T6", "A real directory containing `journal.jsonl` is scanned", "may be skipped"),
    ("T6", "the first in bytewise run-id order", "an arbitrary run"),
    ("T6", "relative to the state root", "relative to the repository root"),
    ("T6", "refuses with exit 2 rather than being printed", "is printed"),
    ("T6", "prints as its first stderr line exactly", "may print"),
    ("T6", "adds exactly the second line", "may omit the second line"),
    ("T6", '`WORKTREE_INPUT_CONTROLS = {"symlinked-runs-root", '
     '"symlinked-run-directory", "symlinked-journal"}`',
     '`WORKTREE_INPUT_CONTROLS = {"symlinked-runs-root", "symlinked-run-directory"}`'),
    ("T6", "prove the recorded pushed oid is contained in it", "assume containment"),
    ("T6", "After guard exit 0 and before worktree removal", "After worktree removal"),
    ("T6", "the worktree remains attached to that branch", "the worktree may be detached"),
    ("T6", "its `HEAD` equals the current branch tip", "its `HEAD` may differ"),
    ("T6", "clean including untracked files", "clean except for untracked files"),
    ("T6", "the current branch tip either equals the recorded pushed oid or is contained",
     "the recorded pushed oid is contained"),
    ("T6", "After worktree removal and before branch deletion", "After branch deletion"),
    ("T6", "require it to equal the pre-removal tip", "permit a changed tip"),
    ("T6", "`git update-ref -d <branch-ref> <verified-old-oid>`", "`update-ref -d`"),
    ("T6", "MUST never use `git branch -D`", "MAY use `git branch -D`"),
    ("T6", "Exit 1 is only the deferral result", "Exit 1 may report another failure"),
    ("T6", "even where `journal._valid_run_id` would accept it",
     "only where `journal._valid_run_id` would refuse it"),
    ("T6", "the first dependency is reported without checking later names", "checks all first"),
    ("T6", "deferred workflow retry MUST first fetch", "deferred retry MAY skip fetch"),
    ("T6", "symlinked runs root, run directory, or journal fail closed", "symlinks pass"),
    ("T6", "each MUST freshly prove the current named branch tip exists", "each MAY assume it"),
    ("T6", "`git worktree remove` without `--force`", "`git worktree remove --force`"),
    ("T6", "proof failure preserves both worktree and branch", "failure may remove either"),
    ("T6", "any post-removal branch-ref failure preserves the branch", "failure may delete it"),
    ("T2a", "is mutually exclusive with `--closing-head`",
     "may be combined with `--closing-head`"),
    ("T2a", "and with the legacy pair", "and may be combined with the legacy pair"),
    (
        "T2a",
        (
            "is accepted identically by `scripts/forge/archive-run.py` and "
            "`forge commit start --archive-run-id <run-id>`"
        ),
        (
            "is accepted by `scripts/forge/archive-run.py` and "
            "`forge commit start --archive-run-id <run-id>`"
        ),
    ),
    ("T2a", "is never re-read", "may be re-read"),
    (
        "T1",
        "historical only when its chain is terminal",
        "historical whenever its chain is terminal",
    ),
    (
        "T1",
        "and a source scan MUST prove that the archive renderer is its only caller",
        "and the archive renderer may be one caller",
    ),
    (
        "T1",
        (
            "in precedence order, `superseded candidate`, `aborted chain`, `failed gate "
            "cleared by passing recheck`, or `earlier run of the same step`"
        ),
        (
            "in precedence order, `aborted chain`, `superseded candidate`, `failed gate "
            "cleared by passing recheck`, or `earlier run of the same step`"
        ),
    ),
    (
        "T1",
        "A current record retired by a carried chain abort also uses `aborted chain`",
        "A current record retired by a carried chain abort remains current",
    ),
    ("T2a", "positionally corresponding exact refusals", "unordered exact refusals"),
    ("T2a", "first failing control in that exact `BACKFILL_CONTROLS` order", "any failing control"),
    ("T2a", "legacy recovery approval missing or "
     "mismatched` precedes", "blocked judgment precedes"),
    ("T2a", "a non-UTF-8-encodable character refuses exactly", "that character is printed"),
    ("T5b", "Repository root means the Git toplevel of the `--repo` checkout",
     "Repository root means the process cwd"),
    ("T5b", "no branch reachable from `recover_batch` calls", "a recovery branch calls"),
    ("T5b", "only after proving one repairable interior receipt gap",
     "before proving a receipt gap"),
    ("T5b", "each compare the raw leading `run_started.repo` exactly",
     "each may resolve the recorded repository"),
    ("T5b", "neither resolves it nor compares it with the caller", "either may resolve it"),
    ("T5b", "makes no recorded-repository comparison", "may compare the recorded repository"),
    ("T6", "silently skips a child only when it is either", "may skip a child whenever it is"),
    ("T6", "Every child DM-011 refuses", "Some child DM-011 refuses"),
    ("T6", "Cited evidence means every FR-017 citation surface",
     "Cited evidence means some FR-017 surfaces"),
    ("T6", "the run directory first, then the run's layout-derived repository root",
     "the repository root first"),
    ("T6", "with the first anchored spelling decisive", "with fallback after an escaping spelling"),
    ("T6", "a historical absolute citation resolves from its absolute spelling",
     "a historical absolute citation is ignored"),
)

DISCREPANCY_ENUM = """```text
ambiguous_legacy_candidate
ignored_nonreview_verdict
legacy_decision_shape
missing_chain_artifact
result_verdict_conflict
snapshot_changed
structured_chain_mismatch
tombstoned_chain
unbound_approval
```"""

REVISION_18_PRECEDENCE = (
    "Revision 18 adds only these narrow diagnostic-precedence exceptions to the rule above, "
    "lettered across the Revision-18 amendments: (a) run-close legibility diagnostics MAY "
    "carry only the validation issue strings that `validate --gates` already emits; (b) "
    "diagnostics MAY carry journal-allocated `execution-NN`, `check-NN`, and `decision-NN` "
    "identifiers; nonempty task IDs already recorded by `task-start`; run IDs accepted by "
    "`journal._valid_run_id`; chain IDs matching `journal.CHAIN_ID_PATTERN`; and full commit "
    "object IDs read from Git or chain state, but never agent strings or caller-supplied paths "
    "(a task ID is journal-recorded, not syntax-validated beyond being nonempty); (c) "
    "diagnostics MAY carry FR-210 proof names and the closed `<observed>` vocabulary defined by "
    "the Revision-18 legibility amendment to FR-220; (d), for that ingest refusal only and "
    "under `--verbose` only, its structured observation MAY carry a raise site as a "
    "repository-relative path under `scripts/`, with `:line`, plus exception class names, never "
    "an exception message; and (e), for the FR-249 inspection-unavailable refusal only and "
    "under `--verbose` only, structured `observed` MAY carry exception class names in "
    "cause/context order, never exception messages."
)

BINDING_PRECEDENCE = (
    "The exact binding member sets, candidate variants, null/non-null review rule, digest "
    "preimage, activation, and discrepancy enum are DM-001. Resolution precedence is: (1) an "
    "activated record requires its complete structured object; (2) the producing builder or "
    "ingest replays the named immutable chain event and requires exact equality plus "
    "current-generation freshness; (3) FR-021 later correlates only the resulting journal "
    "fields; (4) "
    "pre-activation prose is escaped display only. There is no `legacy-inferred` authority. "
    "Missing or ambiguous legacy authority renders `UNBOUND`."
)

BOOKKEEPING_MARKED_LINES = (
    (BEAD_OWNER, "DM-008 and FR-174 immutability remain absolute."),
    ("T1", "before evaluating any historical class."),
    ("T1", "the first applicable reason in the required precedence order."),
    ("T1", "append, ingest, terminal guards, and close law remain current-only."),
    ("T2a", "neither normal nor legacy closing flags may accompany it."),
    ("T2a", "and refuses unsafe absent-worktree path text rather than printing it."),
    (BEAD_OWNER, "every committed DM-008 archive remains byte-identical."),
    ("T3", "after the closing-head lines."),
    ("T3", "an absent summary renders unquoted `None recorded`."),
    ("T3", "an archived blocked run may carry `report.md`."),
    ("T5b", "the five raw batch-recovery consumers, and `worktree-check` follow "
     "their reader-specific routes."),
    ("T5b", "every other case refuses."),
    ("T5b", "`worktree-check` applies independent realpath containment."),
    ("T6", "the first dependency in bytewise run-ID order."),
    ("T6", "every nonzero guard result preserves the worktree and branch."),
    ("T6", "an agent never releases it."),
    ("T8", "the chain classifies as archive-only."),
    ("T8", "the archive-only chain does not schedule `changelog`."),
    ("T8", "a configured mutating changelog step in archive mode still refuses."),
    ("T1", "and a focused weakening mutant for every normative clause."),
    ("T2a", "immediately after `Starting HEAD:`."),
    (BEAD_OWNER, "including pre-Revision-19 archives."),
    ("T3", "and blocked-run report admission."),
    ("T5b", "bead `forge-plugin-9acq` out-of-layout audit behavior."),
    ("T6", "the operator-reserved release protocol for every permanently unarchivable run class."),
    ("T8", "the exemption control is disabled."),
    ("T1", "every non-archive currency check unchanged."),
    ("T2a", "the safely printable main-checkout-only state-root absent-worktree line "
     "in its fixed position."),
    (BEAD_OWNER, "the renderer revision that produced the immutable archive."),
    ("T3", "blocked-run eligibility without ambiguity."),
    ("T5b", "out-of-layout audit compatibility remains isolated and tracked."),
    ("T6", "an explicitly recorded operator-reserved release."),
    ("T8", "an attempted direct changelog mutation in archive mode remains refused."),
    ("T1", "Success: SC-031."), ("T2a", "Success: SC-032."),
    (BEAD_OWNER, "exact mismatch refusal."), ("T3", "Success: SC-033."),
    ("T5b", "Success: SC-034."), ("T6", "Success: SC-035."), ("T8", "Success: SC-036."),
)

CROSS_CUTTING_LINES_SHA256 = "eab24dc6e09c1250a316d962004933eb745a42042c12817f622a62884a97063e"
EXPECTED_MARKER_COUNTS = {"T1": 9, "T2a": 11, "T3": 7, "T5b": 9, "T6": 8, "T8": 0, BEAD_OWNER: 7}
AMENDMENT_PARAGRAPH_SHA256 = {
    "T1": "4545d92167d90ccb9691818343c5245968233c4cc2e359d43026187c9db79e21",
    "T2a": "2085a7e43d49cb899f2085c11c8c0799bad000e4ed2b422ff7ead63bb94a5dce",
    "T3": "bd0f0b1dac0a903c6d61b8a3316003ffad80395effeb980e7645faf2944caa50",
    "T5b": "1cc0571aecdb4d255857b2e5e978be06e8286e2f0de91234dec67fb6d99f5324",
    "T6": "e1f5cf9b8299c8de4fc01e0badb9565d67239852870d355520e5c068f28be4c7",
    "T8": "a8e9a7be49aa3d627af20a0fc78f5d561343a65169fbe50270ceccb0b89045bb",
    BEAD_OWNER: "d8e159da4024edc117eb689b15822b475d0d73ab865e95ceb4e63b44b9ec1aef",
}
PINNED_LINE_SHA256 = (
    ("19 marker scope**", "3dea7e4bc12724cdc5ce665f4c86aec0b5a1eefeb75ebfcfc0cdb38e9b0b7ef0"),
    ("FR-170 archive mode", "9948228fa2bb26d374092f4f722fe854d4a252dc3b33825b2cdf522af1a34a4e"),
    ("FR-172 legacy mode", "baf74cc5e19fbc5fbced7e16aee6f197b85efcd46f55b7b1bf2ecd4fd1ca7668"),
    ("FR-173 report check", "c23171fb62f42f3d43aef0bb8fb0e45aabcbb0d322ce0715e7108aa6b422beb9"),
    ("Normal archive", "6668fe8932b6057c7ade6da63186748d2a3281e6b749bd966877772f646af3fc"),
    ("| `run_started` |", "6334d44c5c6710c4a7d793e3d23b8d85ced93946918f80e5207640d498950592"),
    ("An append target exists", "b67992d5c35925f20bc8da7ebc613e779a55c91c5c57864dd54015596bae55af"),
    ("also rerenders", "34f0cd1ec47faad24b26abe9c1e61ebf49dfd6ae8fdca499b03e32b5da8a044d"),
    ("Committed archive", "e0a00eae70130cce541e974da19a7f7a19bdaef76710bea4ffc640e6caf424b7"),
    ("not gate-clean refuses", "10fb6142ed96dd83215a29dd865d6481fc1a23198b1352353dc267617943c393"),
)

CROSS_CUTTING_LINES = (
    (
        "T6",
        "and deletes with `git update-ref -d <branch-ref> <verified-old-oid>`, never "
        "`git branch -D`.",
    ),
    (
        "T5b",
        "Later readers apply the reader-specific Revision-19 recorded-repository rule.",
    ),
    ("T2a", "for a gate-validation failure."),
    (
        "T2a",
        "In Revision-19 backfill mode, the recorded closing mode uses the recorded archiving "
        "HEAD, which is an input and is never re-read.",
    ),
    ("T2a", "Revision 19 adds backfill mode as the other closing-HEAD exception."),
    ("T2a", "A backfill rerender uses the archive's printed `Archiving HEAD`."),
    (
        BEAD_OWNER,
        "a later renderer never supplies this equality proof, and archives committed before "
        "Revision 19 are never compared with it.",
    ),
    (
        "T1",
        "Revision 19 adds only the archive's historical-acceptance exception described in "
        "DM-001; all other resolution precedence remains in force.",
    ),
    (
        "T2a",
        "requires the exact Revision-19 approval and provenance grammar, and consumes no "
        "manifest.",
    ),
    (BEAD_OWNER, "the existing archive is not rewritten."),
    (
        "T5b",
        "for its combined successfully-resolved mismatch predicate.",
    ),
    (
        "T1",
        "Append, ingest, terminal guards, and close law retain current-only acceptance.",
    ),
    *BOOKKEEPING_MARKED_LINES,
)

GLOBAL_LITERALS = (
    (
        "**Revision 19 marker scope**: A Revision-19 marker scopes only the Revision-19 "
        "sentence(s) it directly follows, never older in-force text on the same line; task TZ "
        "removes task markers after their code lands but preserves bead markers until the named "
        "bead lands."
    ),
    (
        "- `python3 \"${CLAUDE_PLUGIN_ROOT}/scripts/codex_orch_tools.py\" worktree-check "
        "--repo <repo> --worktree <path>` — read-only archive-dependency guard for safe "
        "worktree cleanup"
    ),
    (
        "| `run_started` | `run_id`; nonempty `goal`; absolute `repo` matching the target "
        "repository. Later readers apply the reader-specific Revision-19 "
        "recorded-repository rule. "
    ),
    (
        "Full Git object ID `repo_head`; string-array `repo_status`; "
        "nonempty `plugin_ref`. Canonical nonempty `scope` is engine-injected before pure "
        "validation; known optional `successor_of` MUST be a valid run ID; known optional "
        "`writer_contract` MUST be a string equal to `forge-journal-binding/1`."
    ),
    "A gate-clean blocked close is archivable only through an approved backfill archive.",
    "Revision 19 adds backfill mode as the other closing-HEAD exception.",
    (
        "In Revision-19 backfill mode, the recorded closing mode uses the recorded archiving "
        "HEAD, which is an input and is never re-read."
    ),
    "normal, legacy, and backfill archives retain the existing committed/clean check.",
    "A backfill rerender uses the archive's printed `Archiving HEAD`.",
    BINDING_PRECEDENCE,
    (
        "Backfill mode instead adds the inseparable pair "
        "`--backfill-closing-head <full-object-id> "
        "--backfill-approval <approval-run-id>:<decision-id>`"
    ),
    "Normal and legacy modes consume no manifest.",
    (
        "| An append, close, owner-takeover, or scope-change target has an existing leading "
        "`run_started` whose recorded repository cannot be resolved under the reader-specific "
        "Revision-19 rule, or resolves to a repository other than the caller's repository "
        "root | "
        "journal writer / typed builders / four `batch.py` mismatch sites | refusal, "
        "`forge: journal append refused — recorded repository unavailable for run <run-id>`"
        "; no mutation | At only these named sites, the validated run ID may be named; "
        "recorded/raw repository "
        "values and exceptions are not emitted; and these resolution and mismatch cases never "
        "report `run registry unavailable`, while a journal without a leading `run_started` "
        "retains that existing refusal. `scripts/forge/forge_cli/chain_core/"
        "_chain_batch_carrier.py::_validate_chain_batch_target` is a separate reader and retains "
        "`forge: new run refused — run registry unavailable` when its resolved recorded repository "
        "differs from its caller-resolved repository. The same module's "
        "`_prevalidate_chain_batch_carrier` propagates recorded-repository-unavailable on "
        "resolution failure and retains `forge: journal append refused — invalid journal record` "
        "for its combined successfully-resolved mismatch predicate."
    ),
    (
        "| Archive encounters an activated binding that replays exactly but is not current "
        "(Revision 19) | archive renderer | display `BOUND — source-authenticated history; NOT "
        "LANDING EVIDENCE (<reason>; <binding-id>)` when the Revision-19 historical conditions "
        "hold; otherwise refuse with `forge: archive refused — authoritative chain discrepancy: "
        "structured_chain_mismatch` | Append, ingest, terminal guards, and close law retain "
        "current-only acceptance."
    ),
    REVISION_18_PRECEDENCE,
)


def authority_marker(owner: str) -> str:
    if owner == BEAD_OWNER:
        return "(Revision 19 authority; deferred to bead forge-plugin-c2i8)"
    return f"(Revision 19 authority; deferred to task {owner} of {RUN_ID})"


def expected_marker(owner: str) -> str | None:
    return authority_marker(owner) if owner == BEAD_OWNER or owner in DEFERRED else None


def strip_markers(text: str) -> str:
    return re.sub(r" ?\(Revision 19 authority;[^)]*\)", "", text).rstrip()


def amendment_paragraph(document: str, heading: str) -> str:
    matches = [
        paragraph
        for paragraph in document.split("\n\n")
        if paragraph.startswith(heading)
    ]
    if len(matches) != 1:
        raise AssertionError(f"expected one paragraph starting {heading!r}, found {len(matches)}")
    return matches[0]


def line_containing(document: str, needle: str) -> str:
    matches = [line for line in document.splitlines() if needle in line]
    if len(matches) != 1:
        raise AssertionError(f"expected one line containing {needle!r}, found {len(matches)}")
    return matches[0]


def assert_header(document: str) -> None:
    lines = document.splitlines()
    if lines.count("**Status**: Draft (Revision 21)") != 1:
        raise AssertionError("Revision-21 status header is not unique")
    if lines.count("**Revised**: 2026-10-05") != 1:
        raise AssertionError("Revision-21 revised date is not unique")


def assert_authority_paragraphs(document: str) -> None:
    for task, heading in HEADINGS.items():
        paragraph = amendment_paragraph(document, heading)
        for literal in TASK_LITERALS[task]:
            if literal not in paragraph:
                raise AssertionError(f"{task} authority lacks {literal!r}")
        markers = MARKER_RE.findall(paragraph)
        marker = expected_marker(task)
        expected = [marker] if marker else []
        if markers != expected:
            raise AssertionError(f"{task} markers {markers!r} != {expected!r}")
        if marker and not paragraph.endswith(marker):
            raise AssertionError(f"{task} marker does not end its paragraph")


def assert_amendment_digests(document: str) -> None:
    for owner, heading in AMENDMENT_HEADINGS.items():
        paragraph = strip_markers(amendment_paragraph(document, heading))
        digest = hashlib.sha256(paragraph.encode()).hexdigest()
        if digest != AMENDMENT_PARAGRAPH_SHA256[owner]:
            raise AssertionError(f"{owner} Revision-19 amendment changed: {digest}")


def assert_cross_cutting_markers(document: str) -> None:
    for needle, expected_digest in PINNED_LINE_SHA256:
        line = strip_markers(line_containing(document, needle))
        digest = hashlib.sha256(line.encode()).hexdigest()
        if digest != expected_digest:
            raise AssertionError(f"pinned line {needle!r} changed: {digest}")
    pinned_lines = []
    for owner, needle in CROSS_CUTTING_LINES:
        line = line_containing(document, needle)
        pinned_lines.append(strip_markers(line))
        markers = MARKER_RE.findall(line)
        marker = expected_marker(owner)
        expected = [marker] if marker else []
        if markers != expected:
            raise AssertionError(f"{owner} cross-cutting markers {markers!r} != {expected!r}")
        if marker and f"{needle} {marker}" not in line:
            raise AssertionError(f"{owner} cross-cutting marker is misplaced")
    digest = hashlib.sha256("\n".join(pinned_lines).encode()).hexdigest()
    if digest != CROSS_CUTTING_LINES_SHA256:
        raise AssertionError(f"cross-cutting Revision-19 lines changed: {digest}")
    actual = sorted(MARKER_RE.findall(document))
    owners = (*HEADINGS, *(owner for owner, _needle in CROSS_CUTTING_LINES))
    expected = sorted(marker for owner in owners if (marker := expected_marker(owner)))
    if actual != expected:
        raise AssertionError(f"global Revision-19 markers {actual!r} != {expected!r}")
    for owner, count in EXPECTED_MARKER_COUNTS.items():
        if actual.count(authority_marker(owner)) != count * bool(expected_marker(owner)):
            raise AssertionError(f"{owner} marker count is wrong")


def assert_preserved_and_cross_cutting_contract(document: str) -> None:
    for literal in GLOBAL_LITERALS:
        if document.count(literal) != 1:
            raise AssertionError(f"expected one cross-cutting literal: {literal!r}")
    if document.count(DISCREPANCY_ENUM) != 1:
        raise AssertionError("DM-001 discrepancy enum changed")


def assert_judgment_provenance_order(document: str) -> None:
    paragraph = amendment_paragraph(document, HEADINGS["T3"])
    ordered_literals = (
        "prints after the closing-head lines",
        "`Run judgment: <passed|blocked>`",
        "`Run summary: <summary>`",
    )
    positions = tuple(paragraph.find(literal) for literal in ordered_literals)
    if -1 in positions or positions != tuple(sorted(positions)):
        raise AssertionError("T3 provenance lines are not in closing-head, judgment, summary order")


def assert_revision19_contract(document: str) -> None:
    assert_header(document)
    assert_authority_paragraphs(document)
    assert_amendment_digests(document)
    assert_cross_cutting_markers(document)
    assert_preserved_and_cross_cutting_contract(document)
    assert_judgment_provenance_order(document)


class SpecificationRevision19Tests(unittest.TestCase):
    def assert_mutation_detected(self, original: str, mutant: str) -> None:
        self.assertNotEqual(original, mutant)
        with self.assertRaises(AssertionError):
            assert_revision19_contract(mutant)

    def test_revision19_contract(self) -> None:
        assert_revision19_contract(SPEC)

    def test_amendment_and_line_digests_reject_additive_weakening(self) -> None:
        for owner, heading in AMENDMENT_HEADINGS.items():
            paragraph = amendment_paragraph(SPEC, heading)
            mutant = SPEC.replace(paragraph, f"{paragraph} Agents MAY weaken this.", 1)
            with self.subTest(owner=owner), self.assertRaisesRegex(AssertionError, "changed"):
                assert_amendment_digests(mutant)
        for needle, _digest in PINNED_LINE_SHA256:
            line = line_containing(SPEC, needle)
            mutant = SPEC.replace(line, f"{line} Agents MAY weaken this.", 1)
            with self.subTest(needle=needle), self.assertRaisesRegex(AssertionError, "pinned"):
                assert_cross_cutting_markers(mutant)

    def test_reviewed_weakenings_are_detected(self) -> None:
        self.assertEqual(len(REVIEWED_WEAKENINGS), 71)
        for task, original, replacement in REVIEWED_WEAKENINGS:
            with self.subTest(task=task, original=original):
                paragraph = amendment_paragraph(SPEC, HEADINGS[task])
                self.assertEqual(paragraph.count(original), 1)
                mutated = paragraph.replace(original, replacement, 1)
                mutant = SPEC.replace(paragraph, mutated, 1)
                self.assert_mutation_detected(SPEC, mutant)

    def test_cleanup_condition_enum_remains_exactly_closed(self) -> None:
        prose_sentence = (
            "`cleanup.condition` is exactly `none` or `cleanup-failed`; the latter retains "
            "`cleanup_pending` and admits only `status` or `merge cleanup`."
        )
        self.assertEqual(SPEC.count(prose_sentence), 1)
        self.assertEqual(
            re.findall(r"^cleanup\.condition = .+$", SPEC, flags=re.MULTILINE),
            ["cleanup.condition = none | cleanup-failed"],
        )

    def test_each_cross_cutting_literal_has_a_disable_style_check(self) -> None:
        pinned = (
            "**Status**: Draft (Revision 21)",
            "**Revised**: 2026-10-05",
            DISCREPANCY_ENUM,
            *(needle for _task, needle in CROSS_CUTTING_LINES),
            *GLOBAL_LITERALS,
        )
        for literal in pinned:
            with self.subTest(literal=literal):
                self.assertEqual(SPEC.count(literal), 1)
                mutant = SPEC.replace(literal, "REVISION19_MUTANT", 1)
                self.assert_mutation_detected(SPEC, mutant)

    def test_markers_cannot_be_removed_or_moved(self) -> None:
        sites = [(o, line_containing(SPEC, n), None) for o, n in CROSS_CUTTING_LINES]
        sites += [(o, amendment_paragraph(SPEC, h), h) for o, h in HEADINGS.items()]
        for owner, source, destination in sites:
            marker = expected_marker(owner)
            if marker is None:
                continue
            with self.subTest(owner=owner, destination=destination):
                unmarked = source.replace(f" {marker}", "", 1)
                removed = SPEC.replace(source, unmarked, 1)
                self.assert_mutation_detected(SPEC, removed)
                destination = destination or "**Revised**: 2026-10-05"
                moved = removed.replace(destination, f"{destination} {marker}", 1)
                self.assert_mutation_detected(SPEC, moved)

    def test_deferred_set_can_be_emptied_only_after_markers_are_removed(self) -> None:
        without_markers = SPEC
        for task in DEFERRED:
            without_markers = without_markers.replace(f" {authority_marker(task)}", "")
        original = globals()["DEFERRED"]
        try:
            globals()["DEFERRED"] = frozenset()
            assert_revision19_contract(without_markers)
            if original:
                with self.assertRaises(AssertionError):
                    assert_revision19_contract(SPEC)
            else:
                assert_revision19_contract(SPEC)
        finally:
            globals()["DEFERRED"] = original
