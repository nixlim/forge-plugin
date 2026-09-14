"""Extracted from scripts/forge/forge_cli/chain_core/__init__.py."""
from __future__ import annotations
import os
import subprocess
from pathlib import Path
from typing import Mapping, Sequence
from forge_cli import candidate as candidate_module, runtime
from forge_cli.chain_core._controls import COMMON_LOCK_OWNER_KINDS as COMMON_LOCK_OWNER_KINDS, COMMON_LOCK_OPERATIONS as COMMON_LOCK_OPERATIONS, COMMON_LOCK_FENCE_OPERATIONS as COMMON_LOCK_FENCE_OPERATIONS, COMMON_LOCK_RECOVERY_KINDS as COMMON_LOCK_RECOVERY_KINDS, _COMMON_LOCK_OWNER_KEYS as _COMMON_LOCK_OWNER_KEYS, _COMMON_LOCK_FENCE_KEYS as _COMMON_LOCK_FENCE_KEYS, _COMMON_LOCK_RECOVERY_KEYS as _COMMON_LOCK_RECOVERY_KEYS, _CHAIN_LEASE_KEYS as _CHAIN_LEASE_KEYS, _REQUIRED_COMMON_LOCK_CONTROLS as _REQUIRED_COMMON_LOCK_CONTROLS, COMMON_LOCK_CONTROLS as COMMON_LOCK_CONTROLS, CHAIN_TOMBSTONE_SCHEMA as CHAIN_TOMBSTONE_SCHEMA, CHAIN_TOMBSTONE_EVENT as CHAIN_TOMBSTONE_EVENT, CHAIN_TOMBSTONE_KEYS as CHAIN_TOMBSTONE_KEYS, _REQUIRED_MERGE_STORE_CONTROLS as _REQUIRED_MERGE_STORE_CONTROLS, MERGE_STORE_CONTROLS as MERGE_STORE_CONTROLS, _REQUIRED_MERGE_ADAPTER_CONTROLS as _REQUIRED_MERGE_ADAPTER_CONTROLS, MERGE_ADAPTER_CONTROLS as MERGE_ADAPTER_CONTROLS, _REQUIRED_MERGE_INTEGRATION_CONTROLS as _REQUIRED_MERGE_INTEGRATION_CONTROLS, MERGE_INTEGRATION_CONTROLS as MERGE_INTEGRATION_CONTROLS, INGEST_PROOF_ORDER as INGEST_PROOF_ORDER, _REQUIRED_INGEST_PROOF_CONTROLS as _REQUIRED_INGEST_PROOF_CONTROLS, INGEST_PROOF_CONTROLS as INGEST_PROOF_CONTROLS, _MERGE_CLEANUP_INTENT_SCHEMA as _MERGE_CLEANUP_INTENT_SCHEMA, _MERGE_CLEANUP_RESULT_SCHEMA as _MERGE_CLEANUP_RESULT_SCHEMA, _MERGE_CLEANUP_CLOSE_SCHEMA as _MERGE_CLEANUP_CLOSE_SCHEMA, _MERGE_CLEANUP_RECOVERY_SCHEMA as _MERGE_CLEANUP_RECOVERY_SCHEMA, _MERGE_CLEANUP_FENCE_OPERATIONS as _MERGE_CLEANUP_FENCE_OPERATIONS, _EPOCH_FETCH_OBSERVATION_SCHEMA as _EPOCH_FETCH_OBSERVATION_SCHEMA, _MERGE_CANDIDATE_OBSERVATION_SCHEMA as _MERGE_CANDIDATE_OBSERVATION_SCHEMA, _MERGE_CANDIDATE_OBSERVATION_EVIDENCE_SCHEMA as _MERGE_CANDIDATE_OBSERVATION_EVIDENCE_SCHEMA, _BOOTSTRAP_FETCH_OBSERVATION_SCHEMA as _BOOTSTRAP_FETCH_OBSERVATION_SCHEMA
from forge_cli.chain_core._core import canonical_bytes as canonical_bytes, _chain_storage_root as _chain_storage_root, _validated_commitment_path as _validated_commitment_path, _parsed_run_captured_path as _parsed_run_captured_path, _require_ingest_proof as _require_ingest_proof, iso_z as iso_z, parse_time as parse_time, _require_merge_store_control as _require_merge_store_control, _require_merge_adapter_control as _require_merge_adapter_control, _require_merge_integration_control as _require_merge_integration_control, _require_common_lock_control as _require_common_lock_control, CommonLockBoundaryCrash as CommonLockBoundaryCrash, PublishedLockRecord as PublishedLockRecord, CommonLockInspection as CommonLockInspection, CommonLockUnavailable as CommonLockUnavailable, CommonLockReleaseFailure as CommonLockReleaseFailure, ChainLeaseUnavailable as ChainLeaseUnavailable, FencedChildSurvived as FencedChildSurvived, _valid_utc_second as _valid_utc_second, _valid_positive_int as _valid_positive_int, _valid_nonnegative_int as _valid_nonnegative_int, _valid_host as _valid_host, _valid_nonce as _valid_nonce, _valid_nullable_chain as _valid_nullable_chain, _write_all as _write_all, _PublicationCleanupFailure as _PublicationCleanupFailure, _process_probe as _process_probe, _group_probe as _group_probe, _sleep_with_deadline as _sleep_with_deadline, _require_deadline_open as _require_deadline_open, FencedProcessResult as FencedProcessResult, merge_gate_intent_digest as merge_gate_intent_digest, _forge_command as _forge_command, MergeRunTaskSnapshot as MergeRunTaskSnapshot, _merge_refusal as _merge_refusal, _valid_sorted_unique_strings as _valid_sorted_unique_strings
from forge_cli.chain_core._state import SCHEMA as SCHEMA, KIND as KIND, FRESH_REVIEWER_EVALS_GATE as FRESH_REVIEWER_EVALS_GATE, FRESH_REVIEWER_EVALS_REQUESTS as FRESH_REVIEWER_EVALS_REQUESTS, FRESH_REVIEWER_EVALS_REQUESTED_EVENT as FRESH_REVIEWER_EVALS_REQUESTED_EVENT, STATES as STATES, STATE_KEYS as STATE_KEYS, EVENT_KEYS as EVENT_KEYS, MERGE_STATE_KEYS as MERGE_STATE_KEYS, _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES as _MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES, _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES as _MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES, MERGE_EVENT_KEYS as MERGE_EVENT_KEYS, MERGE_EVENT_NAMES as MERGE_EVENT_NAMES, MERGE_CONSEQUENTIAL_EVENTS as MERGE_CONSEQUENTIAL_EVENTS, TIER_RANK as TIER_RANK, INACTIVE_SECONDS as INACTIVE_SECONDS, FENCED_CHILD_ACK_TIMEOUT_SECONDS as FENCED_CHILD_ACK_TIMEOUT_SECONDS, FENCED_CHILD_DRAIN_SECONDS as FENCED_CHILD_DRAIN_SECONDS, FENCED_CHILD_DRAIN_CAP_BYTES as FENCED_CHILD_DRAIN_CAP_BYTES, FENCED_CHILD_STOP_GRACE_SECONDS as FENCED_CHILD_STOP_GRACE_SECONDS, FENCED_CHILD_REAP_SECONDS as FENCED_CHILD_REAP_SECONDS, ZERO_DIGEST as ZERO_DIGEST, COMMON_LOCK_TIMEOUT_SECONDS as COMMON_LOCK_TIMEOUT_SECONDS, COMMON_LOCK_POLL_SECONDS as COMMON_LOCK_POLL_SECONDS, COMMON_LOCK_RECORD_CAP_BYTES as COMMON_LOCK_RECORD_CAP_BYTES, MERGE_SCOPE_BINDING_CAP_BYTES as MERGE_SCOPE_BINDING_CAP_BYTES, COMMON_LOCK_INTENT_NAME as COMMON_LOCK_INTENT_NAME, COMMON_LOCK_DIRECTORY_NAME as COMMON_LOCK_DIRECTORY_NAME, COMMON_LOCK_OWNER_NAME as COMMON_LOCK_OWNER_NAME, COMMON_LOCK_FLOCK_NAME as COMMON_LOCK_FLOCK_NAME, COMMON_LOCK_RECOVERY_NAME as COMMON_LOCK_RECOVERY_NAME, COMMON_LOCK_INFLIGHT_NAME as COMMON_LOCK_INFLIGHT_NAME, CHAIN_ID_RE as CHAIN_ID_RE, SHA256_RE as SHA256_RE, COMMIT_RE as COMMIT_RE, RUN_ID_RE as RUN_ID_RE, _WORKTREE_LOCKS_GUARD as _WORKTREE_LOCKS_GUARD, _WORKTREE_LOCKS as _WORKTREE_LOCKS, _WORKTREE_LOCK_STATE as _WORKTREE_LOCK_STATE, _exclusive_descriptor_lock as _exclusive_descriptor_lock, _MERGE_REMOTE_ONLY_IDENTITY_FIELDS as _MERGE_REMOTE_ONLY_IDENTITY_FIELDS, _MERGE_SCOPE_UNSET as _MERGE_SCOPE_UNSET, _MERGE_SCOPE_OVERLAY as _MERGE_SCOPE_OVERLAY
from forge_cli.envelope import FrozenError, REVISION9_OUTPUT_SCHEMA, ReasonCode, Refusal
from forge_cli.policy import sha256_bytes, Policy, PolicyError


class Repository:
    def __init__(self, root: Path) -> None:
        self.root = Path(os.path.realpath(root))
        self._candidate_context: candidate_module.GitContext | None = None

    @classmethod
    def discover(cls, explicit: str | None = None) -> "Repository":
        cwd = Path(explicit).resolve() if explicit else Path.cwd()
        try:
            candidate_context = candidate_module.discover_context(cwd)
        except candidate_module.CandidateError as exc:
            raise FrozenError(
                "cannot resolve Git worktree while attempting Forge CLI command",
                observed=str(exc) or "not a repository",
            ) from exc
        repository = cls(candidate_context.worktree_root)
        repository._candidate_context = candidate_context
        return repository

    def git(
        self,
        args: Sequence[str],
        *,
        input_bytes: bytes | None = None,
        check: bool = True,
        env: Mapping[str, str] | None = None,
    ) -> subprocess.CompletedProcess[bytes]:
        context = self.candidate_context()
        selected_environment = dict(os.environ if env is None else env)
        pinned_environment = candidate_module.context_from_paths(
            worktree_root=context.worktree_root,
            git_dir=context.git_dir,
            common_dir=context.common_dir,
            index_file=context.index_file,
            bare=context.bare,
            environment=selected_environment,
            effective_cwd=context.worktree_root,
        ).environment()
        result = subprocess.run(
            ["git", *args],
            cwd=str(self.root),
            input=input_bytes,
            stdin=subprocess.PIPE if input_bytes is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=pinned_environment,
            check=False,
        )
        if check and result.returncode != 0:
            detail = result.stderr.decode("utf-8", "replace").strip()
            raise OSError(f"git {' '.join(args)} failed: {detail}")
        return result

    def head(self) -> str:
        value = self.git(["rev-parse", "HEAD"]).stdout.decode("ascii").strip()
        if not COMMIT_RE.fullmatch(value):
            raise OSError("Git returned a malformed HEAD")
        return value

    def common_root(self) -> Path:
        runtime._coordination_modules()
        from codex_orchestrator.chain_paths import common_worktree_root

        return common_worktree_root(self.root)

    def git_common_dir(self) -> Path:
        """Resolve the canonical Git common directory for portable locking."""

        for arguments, require_absolute in (
            (["rev-parse", "--path-format=absolute", "--git-common-dir"], True),
            (["rev-parse", "--git-common-dir"], False),
        ):
            result = self.git(arguments, check=False)
            rendered = os.fsdecode(result.stdout.rstrip(b"\n"))
            if (
                result.returncode != 0
                or not rendered
                or "\n" in rendered
                or "\r" in rendered
            ):
                continue
            candidate = Path(rendered)
            if require_absolute and not candidate.is_absolute():
                continue
            if not candidate.is_absolute():
                candidate = self.root / candidate
            try:
                canonical = candidate.resolve(strict=True)
            except OSError:
                continue
            if canonical.is_dir():
                return canonical
        raise FrozenError(
            "Git common directory is unavailable for portable locking",
            observed=str(self.root),
            schema=REVISION9_OUTPUT_SCHEMA,
        )

    def policy(self, sha: str | None = None) -> tuple[str, bytes]:
        resolved = sha or self.head()
        result = self.git(["show", f"{resolved}:forge-project.md"], check=False)
        if result.returncode != 0:
            raise OSError(
                result.stderr.decode("utf-8", "replace").strip()
                or "committed forge-project.md is unavailable"
            )
        return resolved, result.stdout

    def candidate_context(self) -> candidate_module.GitContext:
        """Return the command-lifetime pinned Git worktree/index context."""

        if self._candidate_context is None:
            self._candidate_context = candidate_module.discover_context(self.root)
        return self._candidate_context

    def candidate_snapshot(
        self, *, computed_at: str | None = None
    ) -> candidate_module.CandidateSnapshot:
        return candidate_module.snapshot(
            self.candidate_context(), computed_at=computed_at or iso_z()
        )

    def candidate_observation(self) -> candidate_module.CandidateObservation:
        return candidate_module.observe_index(self.candidate_context())

    def candidate_bytes(self) -> bytes:
        # Compatibility method: these are deterministic immutable review bytes,
        # never the v2 authorization identity.
        return self.candidate_snapshot().review_diff

    def candidate_hash(self) -> str:
        return self.candidate_observation().authorization_id

    def staged_paths(self) -> list[str]:
        return list(candidate_module.index_paths(self.candidate_context()))

    def read_commit_object(self, commit_sha: str) -> candidate_module.CommitObject:
        return candidate_module.read_commit_object(self.candidate_context(), commit_sha)

    def commit_message_argument_digest(self, commit_sha: str) -> str:
        """Return the digest of the exact message body in a commit object."""
        result = self.git(["cat-file", "commit", commit_sha], check=False)
        if result.returncode != 0 or b"\n\n" not in result.stdout:
            return ""
        message = result.stdout.split(b"\n\n", 1)[1]
        return sha256_bytes(message)

    def tree_index_drift(self, paths: Sequence[str]) -> list[str]:
        if not paths:
            return []
        result = self.git(["diff", "--name-only", "-z", "--", *paths])
        return [os.fsdecode(item) for item in result.stdout.split(b"\0") if item]

    def normalize_paths(self, values: Sequence[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            candidate = Path(value)
            absolute = candidate if candidate.is_absolute() else self.root / candidate
            resolved_parent = Path(os.path.realpath(absolute.parent))
            resolved = resolved_parent / absolute.name
            try:
                relative = resolved.relative_to(self.root)
            except ValueError:
                raise Refusal(
                    ReasonCode.PATH_MISSING,
                    f"named path is outside the repository: {value}",
                    observed=value,
                    remediation="forge commit start --paths <repository-relative-path>...",
                )
            label = relative.as_posix()
            tracked = self.git(["ls-files", "--error-unmatch", "--", label], check=False)
            if not resolved.exists() and tracked.returncode != 0:
                raise Refusal(
                    ReasonCode.PATH_MISSING,
                    f"named path does not exist: {label}",
                    observed=label,
                    remediation=f"create {label} or remove it from --paths",
                )
            if label not in normalized:
                normalized.append(label)
        return normalized


def _committed_changelog_output_paths(policy: Policy) -> frozenset[str]:
    """Return only exact outputs from an already authenticated policy snapshot."""

    if policy.changelog is None:
        return frozenset()
    outputs = policy.changelog.get("outputs")
    if not isinstance(outputs, list) or not outputs or not all(
        isinstance(item, str) and item for item in outputs
    ):
        raise PolicyError("configured changelog gate has malformed output paths")
    return frozenset(outputs)
