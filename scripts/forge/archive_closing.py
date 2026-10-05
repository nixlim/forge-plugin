"""Closing-mode authority and retrospective archive proofs."""

from __future__ import annotations

import datetime as dt
import os
import re
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from codex_orchestrator import journal as journal_engine
from codex_orchestrator import recorded_repository

LEGACY_APPROVAL_REFUSAL = (
    "forge: archive refused — legacy recovery approval missing or mismatched"
)
BACKFILL_APPROVAL_REFUSAL = (
    "forge: archive refused — backfill approval missing or mismatched"
)
BACKFILL_MODE_CONFLICT = (
    "forge: archive refused — backfill closing mode cannot be combined with "
    "normal or legacy closing mode"
)
BLOCKED_ADMISSION_REFUSAL = (
    "forge: archive refused — blocked judgment requires an approved backfill archive"
)
HEX_HEAD = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
APPROVAL_TOKEN = re.compile(
    r"^(?P<run>[A-Za-z0-9][A-Za-z0-9._-]{0,127}):"
    r"(?P<decision>[A-Za-z0-9][A-Za-z0-9._-]{0,127})$"
)
BACKFILL_RESOLUTION = re.compile(
    r"^backfill-archive: (?P<target>[A-Za-z0-9][A-Za-z0-9._-]{0,127}) "
    r"closing HEAD (?P<closing>[0-9a-f]{40}(?:[0-9a-f]{24})?); "
    r"archive HEAD (?P<archive>[0-9a-f]{40}(?:[0-9a-f]{24})?); "
    r"judgment (?P<judgment>passed|blocked); (?P<reason>[\s\S]+)$"
)

_REQUIRED_BACKFILL_CONTROLS = (
    "approval-binding",
    "archive-head-binding",
    "strict-passed-history",
    "archive-head-ancestry",
    "starting-head-ancestry",
    "landed-commit-enumeration",
    "landed-commit-containment",
    "basis-stability",
    "closing-time-order",
    "closing-identification",
    "archive-time-order",
    "blocked-admission",
)
BACKFILL_CONTROLS = _REQUIRED_BACKFILL_CONTROLS
_REQUIRED_APPROVAL_BINDING_CHECKS = (
    "approval-run-differs",
    "session-owner-match",
    "approval-run-activated",
    "approval-run-open",
    "operator-approval-outcome",
    "recorded-repository-match",
)
APPROVAL_BINDING_CHECKS = _REQUIRED_APPROVAL_BINDING_CHECKS


class ArchiveRefusal(Exception):
    """A fail-closed archive precondition or transaction failure."""

    def __init__(self, message: str, *, contamination: bool = False) -> None:
        super().__init__(message)
        self.message = message
        self.contamination = contamination


@dataclass(frozen=True)
class ClosingMode:
    head: str
    legacy_approval: str | None = None
    backfill_approval: str | None = None
    archive_head: str | None = None
    backfill_reason: str | None = None

    @property
    def is_backfill(self) -> bool:
        return self.backfill_approval is not None


@dataclass(frozen=True)
class ClosingOptions:
    closing_head: str | None
    legacy_recovered_head: str | None
    legacy_approval: str | None
    backfill_closing_head: str | None
    backfill_approval: str | None
    prove_legacy_approval: bool = True


@dataclass(frozen=True)
class ClosingServices:
    run_git: Callable[..., subprocess.CompletedProcess[bytes]]
    stable_journal_snapshot: Callable[[Path], tuple[list[dict[str, Any]], bytes]]
    only_record: Callable[[list[dict[str, Any]], str], dict[str, Any]]
    authoritative_discrepancy: Callable[[str], None]
    renderer_controls: frozenset[str]


@dataclass(frozen=True)
class LegacyRequest:
    records: list[dict[str, Any]]
    recovered_head: object
    approval: object
    prove_approval: bool


@dataclass(frozen=True)
class ApprovalEvidence:
    run_id: str
    decision_id: str
    directory: Path
    records: list[dict[str, Any]]
    raw: bytes
    owner_before: tuple[Any, Any]
    start: dict[str, Any]
    decision: dict[str, Any]
    scope: tuple[str, ...]


@dataclass(frozen=True)
class BasisReference:
    label: str
    path: Path


@dataclass(frozen=True)
class BackfillEvidence:
    repo: Path
    records: Sequence[dict[str, Any]]
    package: Any
    documents: Sequence[Any]
    closing: ClosingMode
    archiving_head: str | None
    run_git: Callable[..., subprocess.CompletedProcess[bytes]]

    @property
    def closing_judgment(self) -> object:
        closures = [
            record for record in self.records if record.get("type") == "run_closed"
        ]
        return closures[0].get("judgment") if len(closures) == 1 else None


def _refuse(message: str, cause: BaseException | None = None) -> None:
    if cause is None:
        raise ArchiveRefusal(message)
    raise ArchiveRefusal(message) from cause


def _require_approval_binding_check(name: str, refusal: str) -> None:
    position = _REQUIRED_APPROVAL_BINDING_CHECKS.index(name)
    actual = tuple(APPROVAL_BINDING_CHECKS)
    if actual[: position + 1] != _REQUIRED_APPROVAL_BINDING_CHECKS[: position + 1]:
        _refuse(refusal)
    if position + 1 == len(_REQUIRED_APPROVAL_BINDING_CHECKS) and actual != (
        _REQUIRED_APPROVAL_BINDING_CHECKS
    ):
        _refuse(refusal)


def _approval_identity(token: object, refusal: str) -> tuple[str, str]:
    match = APPROVAL_TOKEN.fullmatch(token) if isinstance(token, str) else None
    if match is None:
        _refuse(refusal)
    return match.group("run"), match.group("decision")


def _approval_directory(target: Path, run_id: str, refusal: str) -> Path:
    _require_approval_binding_check("approval-run-differs", refusal)
    if run_id == target.name:
        _refuse(refusal)
    try:
        parent = target.parent.resolve(strict=True)
        directory = (target.parent / run_id).resolve(strict=True)
        directory.relative_to(parent)
    except (OSError, RuntimeError, ValueError) as exc:
        _refuse(refusal, exc)
    return directory


def _owned_approval(
    directory: Path, refusal: str
) -> tuple[Any, tuple[Any, Any]]:
    _require_approval_binding_check("session-owner-match", refusal)
    try:
        current = journal_engine._session_owner()
        observed = journal_engine._read_owner_observation(directory / "owner")
    except (
        OSError,
        RuntimeError,
        ValueError,
        journal_engine.CoordinationRefusal,
    ) as exc:
        _refuse(refusal, exc)
    if (
        observed is None
        or observed[1].pid != current.pid
        or observed[1].host != current.host
    ):
        _refuse(refusal)
    return current, observed


def _approval_parts(
    records: list[dict[str, Any]], run_id: str, decision_id: str, refusal: str
) -> tuple[dict[str, Any], dict[str, Any], tuple[str, ...]]:
    starts = [record for record in records if record.get("type") == "run_started"]
    decisions = [
        record
        for record in records
        if record.get("type") == "decision" and record.get("id") == decision_id
    ]
    scope = starts[0].get("scope") if starts else None
    valid_scope = bool(
        isinstance(scope, list)
        and scope
        and all(isinstance(item, str) and item for item in scope)
    )
    if (
        len(starts) != 1
        or starts[0].get("run_id") != run_id
        or not valid_scope
        or len(decisions) != 1
        or "decision" in decisions[0]
    ):
        _refuse(refusal)
    _require_approval_binding_check("approval-run-activated", refusal)
    if not journal_engine.writer_contract_active(records):
        _refuse(refusal)
    _require_approval_binding_check("approval-run-open", refusal)
    if any(record.get("type") == "run_closed" for record in records):
        _refuse(refusal)
    _require_approval_binding_check("operator-approval-outcome", refusal)
    if decisions[0].get("outcome") != "operator_approval":
        _refuse(refusal)
    assert isinstance(scope, list)
    return starts[0], decisions[0], tuple(scope)


def _approval_repository_matches(
    repo: Path,
    directory: Path,
    start: Mapping[str, object],
    refusal: str,
) -> None:
    _require_approval_binding_check("recorded-repository-match", refusal)
    try:
        canonical_repo = repo.resolve(strict=True)
        state_root = journal_engine._resolve_state_root(canonical_repo, "archive")
        resolved, _absent = recorded_repository.resolve(
            start.get("repo"),
            state_root=state_root,
            run_dir=directory,
            caller_repository=canonical_repo,
        )
    except (
        OSError,
        RuntimeError,
        ValueError,
        journal_engine.CoordinationRefusal,
        recorded_repository.ResolutionError,
    ) as exc:
        _refuse(refusal, exc)
    if resolved != canonical_repo:
        _refuse(refusal)


def _replay_approval(evidence: ApprovalEvidence, repo: Path, refusal: str) -> None:
    canonical_records = tuple(
        {name: value for name, value in record.items() if name != "_line"}
        for record in evidence.records
    )
    try:
        for index, proposed in enumerate(canonical_records):
            if journal_engine._writer_activation_marker(proposed):
                continue
            journal_engine._validate_proposed_record(
                proposed,
                run_id=evidence.run_id,
                repo_root=repo,
                scope=evidence.scope,
                prior_records=canonical_records[:index],
                _historical_replay=journal_engine._HISTORICAL_REPLAY,
            )
    except (
        journal_engine.CoordinationRefusal,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        _refuse(refusal, exc)


def _recheck_approval(
    evidence: ApprovalEvidence,
    current_owner: Any,
    services: ClosingServices,
) -> None:
    if journal_engine._stable_journal_read(
        evidence.directory / "journal.jsonl"
    ) != evidence.raw:
        services.authoritative_discrepancy("snapshot_changed")
    owner_after = journal_engine._read_owner_observation(evidence.directory / "owner")
    if (
        owner_after is None
        or owner_after[0] != evidence.owner_before[0]
        or owner_after[1].pid != current_owner.pid
        or owner_after[1].host != current_owner.host
    ):
        services.authoritative_discrepancy("snapshot_changed")


def _approval_evidence(
    repo: Path,
    target: Path,
    token: object,
    refusal: str,
    services: ClosingServices,
) -> ApprovalEvidence:
    run_id, decision_id = _approval_identity(token, refusal)
    directory = _approval_directory(target, run_id, refusal)
    current_owner, owner_before = _owned_approval(directory, refusal)
    try:
        records, raw = services.stable_journal_snapshot(directory)
    except ArchiveRefusal as exc:
        _refuse(refusal, exc)
    start, decision, scope = _approval_parts(records, run_id, decision_id, refusal)
    _approval_repository_matches(repo, directory, start, refusal)
    evidence = ApprovalEvidence(
        run_id,
        decision_id,
        directory,
        records,
        raw,
        owner_before,
        start,
        decision,
        scope,
    )
    _replay_approval(evidence, repo, refusal)
    _recheck_approval(evidence, current_owner, services)
    return evidence


def _target_parts(
    records: list[dict[str, Any]], target: Path, services: ClosingServices, refusal: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        started = services.only_record(records, "run_started")
        closed = services.only_record(records, "run_closed")
    except ArchiveRefusal as exc:
        _refuse(refusal, exc)
    if (
        started.get("run_id") != target.name
        or records[-1] is not closed
    ):
        _refuse(refusal)
    return started, closed


def _backfill_reason_is_valid(reason: str) -> bool:
    """Recognize nonempty single-line provenance without normalizing its text."""

    return bool(reason.strip()) and not any(
        ord(character) <= 0x1F
        or 0x7F <= ord(character) <= 0x9F
        or character in "\u2028\u2029"
        for character in reason
    )


def legacy_closing_mode(
    repo: Path,
    target: Path,
    request: LegacyRequest,
    services: ClosingServices,
) -> ClosingMode:
    records = request.records
    recovered_head = request.recovered_head
    approval = request.approval
    if not isinstance(recovered_head, str) or HEX_HEAD.fullmatch(recovered_head) is None:
        _refuse(LEGACY_APPROVAL_REFUSAL)
    if services.run_git(repo, "cat-file", "-e", f"{recovered_head}^{{commit}}").returncode:
        _refuse(LEGACY_APPROVAL_REFUSAL)
    _started, _closed = _target_parts(
        records, target, services, LEGACY_APPROVAL_REFUSAL
    )
    if journal_engine.writer_contract_active(records):
        _refuse(LEGACY_APPROVAL_REFUSAL)
    if request.prove_approval:
        if "legacy-approval" not in services.renderer_controls:
            _refuse(LEGACY_APPROVAL_REFUSAL)
        evidence = _approval_evidence(
            repo, target, approval, LEGACY_APPROVAL_REFUSAL, services
        )
        resolution = evidence.decision.get("resolution")
        prefix = (
            f"legacy-archive-recovery: {target.name} recovered closing HEAD "
            f"{recovered_head}; "
        )
        reason = (
            resolution[len(prefix) :]
            if isinstance(resolution, str) and resolution.startswith(prefix)
            else ""
        )
        if not reason.strip() or "\r" in reason or "\n" in reason:
            _refuse(LEGACY_APPROVAL_REFUSAL)
    else:
        approval_run_id, _decision_id = _approval_identity(
            approval, LEGACY_APPROVAL_REFUSAL
        )
        if approval_run_id == target.name:
            _refuse(LEGACY_APPROVAL_REFUSAL)
    assert isinstance(approval, str)
    return ClosingMode(recovered_head, legacy_approval=approval)


def backfill_closing_mode(
    repo: Path,
    target: Path,
    records: list[dict[str, Any]],
    closing_head: object,
    approval: object,
    services: ClosingServices,
) -> ClosingMode:
    _require_control("approval-binding", BACKFILL_APPROVAL_REFUSAL)
    if not isinstance(closing_head, str) or HEX_HEAD.fullmatch(closing_head) is None:
        _refuse(BACKFILL_APPROVAL_REFUSAL)
    _started, closed = _target_parts(
        records, target, services, BACKFILL_APPROVAL_REFUSAL
    )
    evidence = _approval_evidence(
        repo, target, approval, BACKFILL_APPROVAL_REFUSAL, services
    )
    resolution = evidence.decision.get("resolution")
    match = BACKFILL_RESOLUTION.match(resolution) if isinstance(resolution, str) else None
    judgment = closed.get("judgment")
    if (
        match is None
        or match.group("target") != target.name
        or match.group("closing") != closing_head
        or match.group("judgment") != judgment
        or not _backfill_reason_is_valid(match.group("reason"))
    ):
        _refuse(BACKFILL_APPROVAL_REFUSAL)
    assert isinstance(approval, str)
    return ClosingMode(
        closing_head,
        backfill_approval=approval,
        archive_head=match.group("archive"),
        backfill_reason=match.group("reason"),
    )


def closing_mode_from_options(
    repo: Path,
    run_dir: Path,
    records: list[dict[str, Any]],
    options: ClosingOptions,
    services: ClosingServices,
) -> ClosingMode:
    normal = options.closing_head is not None
    legacy = options.legacy_recovered_head is not None or options.legacy_approval is not None
    backfill = options.backfill_closing_head is not None or options.backfill_approval is not None
    if backfill and (normal or legacy):
        _refuse(BACKFILL_MODE_CONFLICT)
    if backfill:
        if options.backfill_closing_head is None or options.backfill_approval is None:
            _refuse(BACKFILL_APPROVAL_REFUSAL)
        return backfill_closing_mode(
            repo,
            run_dir,
            records,
            options.backfill_closing_head,
            options.backfill_approval,
            services,
        )
    if normal and legacy:
        _refuse(LEGACY_APPROVAL_REFUSAL)
    if normal:
        head = options.closing_head
        if not isinstance(head, str) or HEX_HEAD.fullmatch(head) is None:
            _refuse("forge: archive refused — invalid closing HEAD")
        if services.run_git(repo, "cat-file", "-e", f"{head}^{{commit}}").returncode:
            _refuse("forge: archive refused — closing HEAD is not a repository commit")
        return ClosingMode(head)
    if not legacy:
        _refuse("forge: archive refused — choose normal or paired legacy closing mode")
    if options.legacy_recovered_head is None or options.legacy_approval is None:
        _refuse(LEGACY_APPROVAL_REFUSAL)
    return legacy_closing_mode(
        repo,
        run_dir,
        LegacyRequest(
            records,
            options.legacy_recovered_head,
            options.legacy_approval,
            options.prove_legacy_approval,
        ),
        services,
    )


def _require_control(name: str, refusal: str) -> None:
    position = _REQUIRED_BACKFILL_CONTROLS.index(name)
    if tuple(BACKFILL_CONTROLS)[: position + 1] != _REQUIRED_BACKFILL_CONTROLS[: position + 1]:
        _refuse(refusal)


def _git_success(evidence: BackfillEvidence, *arguments: str) -> bool:
    try:
        return evidence.run_git(evidence.repo, *arguments).returncode == 0
    except (OSError, subprocess.SubprocessError, ValueError):
        return False


def _prove_archive_head(evidence: BackfillEvidence) -> None:
    refusal = "forge: archive refused — repository HEAD is not the approved archive HEAD"
    _require_control("archive-head-binding", refusal)
    if (
        not isinstance(evidence.archiving_head, str)
        or HEX_HEAD.fullmatch(evidence.archiving_head) is None
        or evidence.closing.archive_head != evidence.archiving_head
        or not _git_success(
            evidence, "cat-file", "-e", f"{evidence.archiving_head}^{{commit}}"
        )
    ):
        _refuse(refusal)


def _prove_strict_passed_history(evidence: BackfillEvidence) -> None:
    refusal = (
        "forge: archive refused — backfill closing HEAD equals archive HEAD for a passed run"
    )
    _require_control("strict-passed-history", refusal)
    judgment = evidence.closing_judgment
    if judgment == "passed" and evidence.closing.head == evidence.archiving_head:
        _refuse(refusal)


def _prove_archive_ancestry(evidence: BackfillEvidence) -> None:
    refusal = (
        "forge: archive refused — backfill closing HEAD is not an ancestor of archive HEAD"
    )
    _require_control("archive-head-ancestry", refusal)
    assert isinstance(evidence.archiving_head, str)
    if not _git_success(
        evidence,
        "merge-base",
        "--is-ancestor",
        evidence.closing.head,
        evidence.archiving_head,
    ):
        _refuse(refusal)


def _opening(evidence: BackfillEvidence) -> Mapping[str, object]:
    starts = [record for record in evidence.records if record.get("type") == "run_started"]
    return starts[0] if len(starts) == 1 else {}


def _closure(evidence: BackfillEvidence) -> Mapping[str, object]:
    closures = [record for record in evidence.records if record.get("type") == "run_closed"]
    return closures[0] if len(closures) == 1 else {}


def _prove_starting_ancestry(evidence: BackfillEvidence) -> None:
    refusal = "forge: archive refused — backfill closing HEAD does not contain starting HEAD"
    _require_control("starting-head-ancestry", refusal)
    starting = _opening(evidence).get("repo_head")
    if (
        not isinstance(starting, str)
        or HEX_HEAD.fullmatch(starting) is None
        or not _git_success(
            evidence, "merge-base", "--is-ancestor", starting, evidence.closing.head
        )
    ):
        _refuse(refusal)


def _landing_chain_ids(evidence: BackfillEvidence) -> tuple[str, ...] | None:
    tombstones = {
        item.chain_id for item in getattr(evidence.package, "tombstones", ())
    }
    identifiers: set[str] = set()
    for record in evidence.records:
        if record.get("type") != "decision" or record.get("outcome") != "chain-landing":
            continue
        binding = record.get("binding")
        source = binding.get("source_record") if isinstance(binding, Mapping) else None
        chain_id = source.get("chain_id") if isinstance(source, Mapping) else None
        if not isinstance(chain_id, str):
            return None
        if chain_id not in tombstones:
            identifiers.add(chain_id)
    return tuple(sorted(identifiers, key=os.fsencode))


def _landed_oid(chain: Any) -> str | None:
    state = getattr(chain, "state", None)
    family = getattr(chain, "family", None)
    if not isinstance(state, Mapping):
        return None
    if family == "commit":
        result = state.get("commit_result")
        value = result.get("commit_sha") if isinstance(result, Mapping) else None
    elif family == "merge":
        integration = state.get("integration")
        push = integration.get("push") if isinstance(integration, Mapping) else None
        value = push.get("landed_head") if isinstance(push, Mapping) else None
    else:
        return None
    return value if isinstance(value, str) and HEX_HEAD.fullmatch(value) else None


def _enumerate_landed_commits(evidence: BackfillEvidence) -> tuple[str, ...]:
    refusal = "forge: archive refused — could not authenticate every landed run commit"
    _require_control("landed-commit-enumeration", refusal)
    identifiers = _landing_chain_ids(evidence)
    chains = tuple(getattr(evidence.package, "chains", ()))
    if identifiers is None:
        _refuse(refusal)
    landed: list[str] = []
    for chain_id in identifiers:
        matches = [chain for chain in chains if getattr(chain, "chain_id", None) == chain_id]
        oid = _landed_oid(matches[0]) if len(matches) == 1 else None
        if oid is None or not _git_success(evidence, "cat-file", "-e", f"{oid}^{{commit}}"):
            _refuse(refusal)
        landed.append(oid)
    return tuple(landed)


def _prove_landed_containment(
    evidence: BackfillEvidence, landed: Sequence[str]
) -> None:
    prefix = "forge: archive refused — backfill closing HEAD does not contain landed commit "
    _require_control("landed-commit-containment", prefix + "<full-object-id>")
    for oid in landed:
        if not _git_success(
            evidence, "merge-base", "--is-ancestor", oid, evidence.closing.head
        ):
            _refuse(prefix + oid)


def _repository_relative_path(repo: Path, document: Any) -> str | None:
    path = getattr(document, "path", None)
    if not isinstance(path, Path):
        return None
    try:
        relative = path.resolve(strict=False).relative_to(repo.resolve(strict=True))
    except (OSError, RuntimeError, ValueError):
        return None
    return relative.as_posix() if relative.parts else None


def _tree_tracks(evidence: BackfillEvidence, head: str, relative: str) -> bool:
    return _git_success(evidence, "cat-file", "-e", f"{head}:{relative}")


def _prove_basis_stability(evidence: BackfillEvidence) -> None:
    assert isinstance(evidence.archiving_head, str)
    for document in evidence.documents:
        label = str(getattr(document, "label", ""))
        refusal = (
            "forge: archive refused — basis document changed after closing HEAD: "
            + label
        )
        _require_control("basis-stability", refusal)
        relative = _repository_relative_path(evidence.repo, document)
        if relative is None:
            continue
        tracked = _tree_tracks(evidence, evidence.closing.head, relative) or _tree_tracks(
            evidence, evidence.archiving_head, relative
        )
        if tracked and not _git_success(
            evidence,
            "diff",
            "--quiet",
            evidence.closing.head,
            evidence.archiving_head,
            "--",
            relative,
        ):
            _refuse(refusal)
    if not evidence.documents:
        _require_control(
            "basis-stability",
            "forge: archive refused — basis document changed after closing HEAD: <label>",
        )


def _recorded_time(evidence: BackfillEvidence) -> float | None:
    value = _closure(evidence).get("recorded_at")
    if not isinstance(value, str):
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.timestamp() if parsed.tzinfo is not None else None


def _commit_time(evidence: BackfillEvidence, oid: str) -> int | None:
    try:
        result = evidence.run_git(evidence.repo, "show", "-s", "--format=%ct", oid)
        rendered = result.stdout.decode("ascii").strip()
    except (OSError, UnicodeError, ValueError, subprocess.SubprocessError):
        return None
    valid = result.returncode == 0 and rendered.isdigit()
    return int(rendered) if valid else None


def _prove_closing_time(evidence: BackfillEvidence) -> float:
    refusal = "forge: archive refused — backfill closing HEAD postdates run_closed"
    _require_control("closing-time-order", refusal)
    recorded = _recorded_time(evidence)
    committed = _commit_time(evidence, evidence.closing.head)
    if recorded is None or committed is None or committed > recorded:
        _refuse(refusal)
    return recorded


def _first_parent_successor(evidence: BackfillEvidence) -> str | None:
    assert isinstance(evidence.archiving_head, str)
    try:
        result = evidence.run_git(
            evidence.repo,
            "rev-list",
            "--first-parent",
            "--reverse",
            f"{evidence.closing.head}..{evidence.archiving_head}",
        )
        values = result.stdout.decode("ascii").splitlines()
    except (OSError, UnicodeError, ValueError, subprocess.SubprocessError):
        return None
    if result.returncode or not values or HEX_HEAD.fullmatch(values[0]) is None:
        return None
    try:
        parent = evidence.run_git(
            evidence.repo, "rev-parse", f"{values[0]}^1"
        ).stdout.decode("ascii").strip()
    except (OSError, UnicodeError, ValueError, subprocess.SubprocessError):
        return None
    return values[0] if parent == evidence.closing.head else None


def _prove_closing_identification(
    evidence: BackfillEvidence, recorded: float
) -> None:
    refusal = (
        "forge: archive refused — backfill closing HEAD is not the last commit before run_closed"
    )
    _require_control("closing-identification", refusal)
    if evidence.closing.head == evidence.archiving_head:
        return
    successor = _first_parent_successor(evidence)
    successor_time = _commit_time(evidence, successor) if successor is not None else None
    if successor_time is None or successor_time <= recorded:
        _refuse(refusal)


def _prove_archive_time(evidence: BackfillEvidence, recorded: float) -> None:
    refusal = "forge: archive refused — archive HEAD predates run_closed"
    _require_control("archive-time-order", refusal)
    if evidence.closing.head == evidence.archiving_head:
        return
    assert isinstance(evidence.archiving_head, str)
    archived = _commit_time(evidence, evidence.archiving_head)
    if archived is None or archived < recorded:
        _refuse(refusal)


def _prove_blocked_admission(evidence: BackfillEvidence) -> None:
    _require_control("blocked-admission", BLOCKED_ADMISSION_REFUSAL)
    if evidence.closing_judgment not in {"passed", "blocked"}:
        _refuse(BLOCKED_ADMISSION_REFUSAL)


def prove_backfill_controls(evidence: BackfillEvidence) -> None:
    """Run controls 2..12 after caller-owned gated-validation proofs."""

    _prove_archive_head(evidence)
    _prove_strict_passed_history(evidence)
    _prove_archive_ancestry(evidence)
    _prove_starting_ancestry(evidence)
    landed = _enumerate_landed_commits(evidence)
    _prove_landed_containment(evidence, landed)
    _prove_basis_stability(evidence)
    recorded = _prove_closing_time(evidence)
    _prove_closing_identification(evidence, recorded)
    _prove_archive_time(evidence, recorded)
    _prove_blocked_admission(evidence)


def require_passed_without_backfill(closing: ClosingMode, judgment: object) -> None:
    """Retain legacy approval precedence, then use the shared blocked literal."""

    if not closing.is_backfill and judgment != "passed":
        _refuse(BLOCKED_ADMISSION_REFUSAL)


def provenance_lines(closing: ClosingMode) -> list[str]:
    if closing.is_backfill:
        return [
            f"Backfill closing HEAD: {closing.head}",
            "",
            f"Archiving HEAD: {closing.archive_head}",
            "",
            f"Backfill approval: {closing.backfill_approval}",
            "",
            f"Backfill reason: {closing.backfill_reason}",
            "",
            "Closing-head status: recovered after run_closed; not a contemporaneous FR-172 capture",
            "",
        ]
    if closing.legacy_approval is not None:
        return [
            f"Legacy recovered closing HEAD: {closing.head}",
            "",
            f"Legacy recovery approval: {closing.legacy_approval}",
            "",
        ]
    return [f"Closing HEAD: {closing.head}", ""]
