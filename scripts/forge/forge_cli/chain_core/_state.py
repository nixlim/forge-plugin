"""Extracted from scripts/forge/forge_cli/chain_core/__init__.py."""
from __future__ import annotations
from forge_cli import runtime
import re
import threading
import contextlib
import errno
import fcntl
import os
import stat
import time
from typing import Callable, Iterable


_MERGE_SCOPE_OVERLAY = {
    "LC_ALL": "C",
    "LANG": "C",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_ATTR_NOSYSTEM": "1",
    "GIT_OPTIONAL_LOCKS": "0",
    "GIT_NO_REPLACE_OBJECTS": "1",
    "GIT_NO_LAZY_FETCH": "1",
    "GIT_PAGER": "cat",
    "PAGER": "cat",
}


_MERGE_SCOPE_UNSET = frozenset(
    {
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_COMMON_DIR",
        "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_NAMESPACE",
        "GIT_PREFIX",
        "GIT_EXTERNAL_DIFF",
        "GIT_DIFF_OPTS",
        "GIT_SHALLOW_FILE",
        "GIT_GRAFT_FILE",
    }
)


_MERGE_REMOTE_ONLY_IDENTITY_FIELDS = (
    "remote",
    "destination_ref",
    "candidate_head",
    "diff_sha256",
    "policy_commit",
    "policy_digest",
    "worktree_identity",
)


@contextlib.contextmanager
def _exclusive_descriptor_lock(
    lock_key: str,
    opener: Callable[[], int],
    *,
    deadline: float | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> Iterable[None]:
    """Cross-process exclusive lock with safe same-thread re-entry."""
    with _WORKTREE_LOCKS_GUARD:
        local_lock = _WORKTREE_LOCKS.setdefault(lock_key, threading.RLock())

    def wait_for_deadline(stage: str) -> None:
        if deadline is None:
            return
        remaining = deadline - clock()
        if remaining <= 0:
            raise TimeoutError(f"{stage} exhausted the shared deadline")
        sleeper(min(COMMON_LOCK_POLL_SECONDS, remaining))

    if deadline is None:
        local_lock.acquire()
    else:
        while not local_lock.acquire(blocking=False):
            wait_for_deadline("process-local descriptor lock acquisition")
    try:
        state_key = (lock_key, threading.get_ident())
        with _WORKTREE_LOCKS_GUARD:
            held = _WORKTREE_LOCK_STATE.get(state_key)
            if held is not None:
                descriptor, depth = held
                _WORKTREE_LOCK_STATE[state_key] = (descriptor, depth + 1)
            else:
                descriptor = -1
        if held is None:
            descriptor = opener()
            try:
                opened = os.fstat(descriptor)
                if not stat.S_ISREG(opened.st_mode) or opened.st_uid != os.geteuid():
                    raise OSError("lock path is not an owner-controlled regular file")
                os.fchmod(descriptor, 0o600)
                if deadline is None:
                    fcntl.flock(descriptor, fcntl.LOCK_EX)
                else:
                    while True:
                        try:
                            fcntl.flock(
                                descriptor,
                                fcntl.LOCK_EX | fcntl.LOCK_NB,
                            )
                            break
                        except OSError as exc:
                            if exc.errno not in {errno.EACCES, errno.EAGAIN}:
                                raise
                            wait_for_deadline(
                                "cross-process descriptor lock acquisition"
                            )
            except BaseException:
                os.close(descriptor)
                raise
            with _WORKTREE_LOCKS_GUARD:
                _WORKTREE_LOCK_STATE[state_key] = (descriptor, 1)
        try:
            yield
        finally:
            release = False
            with _WORKTREE_LOCKS_GUARD:
                current_descriptor, depth = _WORKTREE_LOCK_STATE[state_key]
                if depth == 1:
                    del _WORKTREE_LOCK_STATE[state_key]
                    release = True
                else:
                    _WORKTREE_LOCK_STATE[state_key] = (
                        current_descriptor,
                        depth - 1,
                    )
            if release:
                try:
                    fcntl.flock(current_descriptor, fcntl.LOCK_UN)
                finally:
                    os.close(current_descriptor)
    finally:
        local_lock.release()


_WORKTREE_LOCK_STATE: dict[tuple[str, int], tuple[int, int]] = {}


_WORKTREE_LOCKS: dict[str, threading.RLock] = {}


_WORKTREE_LOCKS_GUARD = threading.Lock()


RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


COMMIT_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


CHAIN_ID_RE = re.compile(r"^c-\d{4}-\d{2}-\d{2}T\d{6}Z-[0-9a-f]{4}$")


COMMON_LOCK_INFLIGHT_NAME = "agent-rebase.inflight"


COMMON_LOCK_RECOVERY_NAME = "agent-rebase.recover"


COMMON_LOCK_FLOCK_NAME = "agent-rebase.lock"


COMMON_LOCK_OWNER_NAME = "owner.json"


COMMON_LOCK_DIRECTORY_NAME = "agent-rebase.lockdir"


COMMON_LOCK_INTENT_NAME = "agent-rebase.lock.intent"


MERGE_SCOPE_BINDING_CAP_BYTES = 16384


COMMON_LOCK_RECORD_CAP_BYTES = 16384


COMMON_LOCK_POLL_SECONDS = 0.05


COMMON_LOCK_TIMEOUT_SECONDS = 300.0


ZERO_DIGEST = "0" * 64


FENCED_CHILD_REAP_SECONDS = 0.5


FENCED_CHILD_STOP_GRACE_SECONDS = 0.25


FENCED_CHILD_DRAIN_CAP_BYTES = runtime.OUTPUT_CAP_BYTES + 1


FENCED_CHILD_DRAIN_SECONDS = 0.1


FENCED_CHILD_ACK_TIMEOUT_SECONDS = 1.0


INACTIVE_SECONDS = 24 * 60 * 60


TIER_RANK = {"fast": 0, "standard": 1, "hard": 2}


MERGE_CONSEQUENTIAL_EVENTS = frozenset(
    {
        "gate_recorded",
        "review_attached",
        "approval_recorded",
        "generation_carried_forward",
        "push_observed",
    }
)


MERGE_EVENT_NAMES = frozenset(
    {
        "chain_started",
        "ownership_intent",
        "ownership_claimed",
        "ownership_release_intent",
        "ownership_released",
        "gate_recorded",
        "review_requested",
        "review_attached",
        "review_disposition",
        "approval_recorded",
        "generation_refreshed",
        "generation_carried_forward",
        "epoch_intent",
        "fetch_intent",
        "fetch_result",
        "rebase_intent",
        "rebase_conflict",
        "rebase_result",
        "reverification_result",
        "push_intent",
        "push_observed",
        "cleanup_intent",
        "cleanup_result",
        "condition_recorded",
        "lock_release_result",
        "aborted",
        "closed",
        "journal_receipted",
    }
)


MERGE_EVENT_KEYS = frozenset(
    {
        "schema",
        "chain_id",
        "sequence",
        "at",
        "event",
        "generation_digest",
        "previous_digest",
        "payload",
        "digest",
    }
)


_MERGE_INACTIVE_POST_ATTEMPT_RECOVERY_SOURCES = frozenset(
    {"authorized", "awaiting_approval", "pushing"}
)


_MERGE_INACTIVE_ATTEMPT_OBSERVATION_SOURCES = frozenset(
    {
        "classifying",
        "verifying",
        "reviewing",
        "revising",
        "awaiting_approval",
        "authorized",
        "reverifying",
        "reverification_failed",
        "pushing",
    }
)


MERGE_STATE_KEYS = frozenset(
    {
        "schema",
        "chain_id",
        "kind",
        "state",
        "created_at",
        "last_event_at",
        "inactive_after",
        "owner",
        "run",
        "repository",
        "worktree",
        "branch",
        "target",
        "policy_source",
        "candidate",
        "tier",
        "steps",
        "review",
        "approval",
        "authorization",
        "integration",
        "cleanup",
        "run_binding",
        "journal_outbox",
    }
)


EVENT_KEYS = {"sequence", "prev_digest", "payload", "digest"}


STATE_KEYS = {
    "schema",
    "chain_id",
    "kind",
    "state",
    "created_at",
    "last_event_at",
    "inactive_after",
    "repo_head",
    "policy_source",
    "paths",
    "staging",
    "candidate",
    "tier",
    "steps",
    "review",
    "approval",
    "authorization",
    "commit_result",
    "run_binding",
    "journal_outbox",
}


STATES = {
    "classifying",
    "verifying",
    "reviewing",
    "revising",
    "awaiting_approval",
    "authorized",
    "committing",
    "closed",
    "aborted",
}


FRESH_REVIEWER_EVALS_REQUESTED_EVENT = "fresh_reviewer_evals_requested"


FRESH_REVIEWER_EVALS_REQUESTS = "fresh-reviewer-evals-requests"


FRESH_REVIEWER_EVALS_GATE = "fresh-reviewer-evals"


KIND = "commit"


SCHEMA = "forge-chain/1"
