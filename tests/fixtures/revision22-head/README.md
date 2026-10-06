# Pre-Revision-22 writer fixtures

These unmodified chain state/event bytes were emitted by the production writers
at `b786fa0b4b804c5c38742c78382095b856459c7c`. Both `bound` and `unbound`
contain a merge chain and a commit chain. The revision-22 tests copy these files to a temporary directory and load those
exact bytes in place; neither locks nor repairs touch the fixture tree.

The generator exported HEAD's Python files with `git show HEAD:<path>` to an
isolated temporary directory and imported that copy of `tests.test_cli_merge_store`.
It used `MergeStoreFixture.initial_merge` and `MergeChainStore.create`. The bound
case used a real temporary Git repository, an open run and an active task; the
commit case used `ChainStore.create(..., "chain_started", {"paths": ...})` with
HEAD's initial-state shape and a real committed fixture policy for its binding.
Only the clock was fixed for commit writes. No replay validation was disabled,
and no state/event bytes were edited after production serialization. The source
repository paths in these files intentionally no longer exist.

Both merge start deltas carry `run_binding`; HEAD's reducer supplies the null
`journal_outbox` in materialized state. Both commit snapshots carry both keys.
This distinction reproduces the regression hidden by fixtures from the new writer.

SHA-256 of the writer bytes:

- `bound/.forge/chains/c-2026-08-30T110000Z-c002.events.jsonl`: `0db411db42c60b79508af88f06ec251c4362cdf0ce2ef2e592af20535ccb766a`
- `bound/.forge/chains/c-2026-08-30T110000Z-c002.json`: `e2deb40ad9c144814a43a177596f39b77b9c6d22115a5fa3c3c4106dd5a1b7e7`
- `bound/.forge/chains/c-2026-08-30T120000Z-a001.events.jsonl`: `0af3fe1c83ae32a3e1d29182d6a13fe9e02bf464892532be9326d8bbe8e9575e`
- `bound/.forge/chains/c-2026-08-30T120000Z-a001.json`: `e88df02690d62dbb3aeea813bd5320c0a97209d12d987185a2b5219e1ff655c1`
- `unbound/.forge/chains/c-2026-08-30T110000Z-c002.events.jsonl`: `2b5d06414c2564179743bd69d34dc01d4e2d37a8b7e84fa3d4445db53b9c4769`
- `unbound/.forge/chains/c-2026-08-30T110000Z-c002.json`: `7dbfa9fc56d8079a307a42c1abf36d8e1747d519deddf715ad0da74f44713978`
- `unbound/.forge/chains/c-2026-08-30T120000Z-a001.events.jsonl`: `c11b2a23c1263a7489ad7e9293e51349acd0a3e5feec780457fb45bedba49582`
- `unbound/.forge/chains/c-2026-08-30T120000Z-a001.json`: `bb59e8ea78fb25d3d64d9363a9142e85f74f4c9f1eb736b4aad7efd445a7c000`

## Lifecycle fixtures (iteration 8)

`lifecycle/.forge/chains/` adds complete native histories. No authenticated member,
path, event, digest, timestamp, carrier, or materialized state was edited or stripped.
The tests load temporary copies and verify unchanged state/event bytes, without
consulting a run or journal.

- Commit `c-2026-09-02T182547Z-7ee3` is copied byte for byte from the main
  checkout's `.forge/chains/`. Its 12 events include bound `chain_started`,
  candidate staging/classification, `step_recorded`, two outbox-clearing
  `journal_receipted` events, `chain_aborted`, `head_moved`, and
  `abort_disposition_recorded`. Native `journal_batch` and `source_event_digest`
  carriers remain intact. It predates Revision 22 and exercises the actual
  legacy writer history rather than a snapshot synthesized by the new writer.
- Merge `c-2026-10-06T140613Z-6a38` is emitted by HEAD `b786fa0`'s
  `MergeLifecycleStartTests.start_lifecycle(bound=True)`, which opens a real
  run/task and invokes `MergeEngine.start_chain` with the production store.
  Its fetch result contains a populated `scope_proof` and scope-fetch binding.
  No writer or replay validator was patched. The source was checked out using
  `git --git-dir=/tmp/u2-iteration8-head.git worktree add --detach
  /tmp/u2-iteration8-head HEAD`; the temporary Git directory has its own HEAD
  and metadata, with a read-only object alternate pointing to the source object
  database. The shared repository's index, branch, and worktree metadata were
  untouched. The generator ran through `FORGE_GATE1_NESTED=1 sem-run test`.

The regression mutant adds an equality requirement for the old and new
`journal_outbox` to `_legacy_fact_valid`. The unmodified commit history then
freezes at its first receipt; the ordinary fixture assertion therefore fails.

SHA-256 of the lifecycle writer bytes:

- `lifecycle/.forge/chains/c-2026-09-02T182547Z-7ee3.events.jsonl`: `a12ab4bd8c9572116ee3121d24fde534c4cac0d01ca5d326922c95e81adfde3b`
- `lifecycle/.forge/chains/c-2026-09-02T182547Z-7ee3.json`: `86b13eadc3c9335a32e6eab9d32d0a51ca4cd31f80574a7eb0cb55a52f08eaf2`
- `lifecycle/.forge/chains/c-2026-10-06T140613Z-6a38.events.jsonl`: `d937341ed061e5b9225e2bb1683d3e851e51c17ce1ead52e318c8569da62ec6a`
- `lifecycle/.forge/chains/c-2026-10-06T140613Z-6a38.json`: `326891d0591019e85f1659bf5c392a3e37827909e89d6facabfc3790d977b0eb`

## Merge receipt and scope-exceeded abort (iteration 14)

The `merge-receipt` and `merge-scope-abort` directories contain exact HEAD-writer
bytes from `BoundMergeOutboxTests.test_event_first_carrier_crash_recovery_and_receipt_sequence`
and `MergeLifecycleStartTests.test_post_fetch_run_scope_refusal_releases_ownership_and_aborts`.
The generator reused the isolated HEAD worktree `/tmp/u2-iteration8-head`, verifying
every tracked Python source under `scripts/` and `tests/` against `git show HEAD:<path>`
before importing it. It ran both original test methods through `sem-run test`, then
copied their state/event files before fixture teardown. No Git write command or stash
was used; no writer or validator was patched, and no serialized byte was changed.

The first fixture includes a carried batch, its non-null outbox projection and an
outbox-clearing `journal_receipted` event. The second includes a populated exceeded
scope proof, authenticated ownership release and an `aborted` terminal event. Tests
load temporary copies in place without journal access, compare unchanged bytes,
and reject a rehashed history with a tampered terminal-preconditions digest.

Writer-byte SHA-256:

- `merge-receipt/.forge/chains/c-2026-08-30T130000Z-b001.events.jsonl`: `548e7a0a1729d7c0f962cd84034a4cd5a5f548ef3999b360187223a6b73870ce`
- `merge-receipt/.forge/chains/c-2026-08-30T130000Z-b001.json`: `b881dc6347522922b0cfce90397704e77f3c17b6eb176d258189f5f32e2e8c54`
- `merge-scope-abort/.forge/chains/c-2026-10-06T175931Z-37f3.events.jsonl`: `12bffe5fbbff6745f43bb70365757cbbddef39778d4b0b147953336eb1019de1`
- `merge-scope-abort/.forge/chains/c-2026-10-06T175931Z-37f3.json`: `ddd3cb2a0fdf15639f6b4d696b1aa4cb015eda9967cab6629ad4cb59a8bd2fdb`
