from __future__ import annotations

import os
import tempfile
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from tests._revision9_coord_constants import key
from tests._revision9_coord_support import Revision9BuilderBatchSupport

from codex_orchestrator import builders, journal

_LEGACY_ACTIVATION_EVENTS_CAP_BYTES = 8_388_608
_OBSERVED_EVENTS_BYTES = 8_433_733
_NINE_MIB = 9 * 1024 * 1024
_BINDING_REPLAY_REFUSAL = (
    "forge: journal append refused — invalid journal record: "
    "binding chain replay failed"
)


@contextmanager
def _open_temporary_directory() -> Iterator[tuple[Path, int]]:
    with tempfile.TemporaryDirectory(
        prefix="forge-activation-events-cap-"
    ) as temporary:
        directory = Path(temporary)
        descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            yield directory, descriptor
        finally:
            os.close(descriptor)


class ActivationReplayEventsCapTests(unittest.TestCase):
    def test_activation_events_cap_is_64_mib_above_observed_log(self) -> None:
        self.assertEqual(builders._ACTIVATION_EVENTS_CAP_BYTES, 67_108_864)
        self.assertGreater(
            builders._ACTIVATION_EVENTS_CAP_BYTES,
            _OBSERVED_EVENTS_BYTES,
        )
        self.assertEqual(builders._ACTIVATION_STATE_CAP_BYTES, 1_048_576)
        self.assertEqual(builders._ACTIVATION_EVENT_ONE_CAP_BYTES, 65_536)

    def test_activation_events_cap_reads_nine_mib_completely(self) -> None:
        payload = b"e" * _NINE_MIB
        with _open_temporary_directory() as (directory, descriptor):
            (directory / "events.jsonl").write_bytes(payload)

            actual = builders._read_regular_bytes_at(
                descriptor,
                "events.jsonl",
                cap=builders._ACTIVATION_EVENTS_CAP_BYTES,
            )

        self.assertEqual(actual, payload)

    def test_regular_read_accepts_exact_cap_and_refuses_cap_plus_one(self) -> None:
        cap = 32
        with _open_temporary_directory() as (directory, descriptor):
            (directory / "exact").write_bytes(b"x" * cap)
            (directory / "over").write_bytes(b"y" * (cap + 1))

            self.assertEqual(
                builders._read_regular_bytes_at(descriptor, "exact", cap=cap),
                b"x" * cap,
            )
            with self.assertRaises(journal.CoordinationRefusal) as raised:
                builders._read_regular_bytes_at(descriptor, "over", cap=cap)

        self.assertEqual(
            str(raised.exception),
            _BINDING_REPLAY_REFUSAL,
        )

    def test_legacy_activation_events_cap_refuses_nine_mib_in_memory(self) -> None:
        with _open_temporary_directory() as (directory, descriptor):
            (directory / "events.jsonl").write_bytes(b"e" * _NINE_MIB)

            with mock.patch.object(
                builders,
                "_ACTIVATION_EVENTS_CAP_BYTES",
                _LEGACY_ACTIVATION_EVENTS_CAP_BYTES,
            ), self.assertRaises(journal.CoordinationRefusal) as raised:
                builders._read_regular_bytes_at(
                    descriptor,
                    "events.jsonl",
                    cap=builders._ACTIVATION_EVENTS_CAP_BYTES,
                )

        self.assertEqual(
            str(raised.exception),
            _BINDING_REPLAY_REFUSAL,
        )


class ActivationScanEventsCapTests(
    Revision9BuilderBatchSupport,
    unittest.TestCase,
):
    def test_activation_scan_passes_events_cap_to_binding_replay(self) -> None:
        run_id = "run-20260927-activation-events-cap"
        chain_id = "c-2026-09-27T171244Z-a677"
        run_binding = {
            "run_id": run_id,
            "task_id": "task-01",
            "repository": str(self.repo.resolve()),
            "policy_digest": key("activation-events-cap-policy"),
        }
        with self.api_environment():
            self._open_legacy_run(self.repo, run_id)
            self._write_bound_chain_state(
                self.repo,
                run_id,
                chain_id=chain_id,
                run_binding=run_binding,
            )
            original_resolver = builders._resolve_binding_from_descriptor
            observed: list[int | None] = []

            def record_events_cap(*args: object, **kwargs: object) -> object:
                if (
                    kwargs.get("replay_only") is True
                    and kwargs.get("validate_lineage") is False
                    and kwargs.get("resolve_tombstone") is False
                ):
                    observed.append(kwargs.get("events_cap"))
                return original_resolver(*args, **kwargs)

            with mock.patch.object(
                builders,
                "_resolve_binding_from_descriptor",
                side_effect=record_events_cap,
            ):
                outcome = self.start_task(self.repo, run_id)

        self.assertTrue(journal._writer_activation_marker(outcome.records[0]))
        self.assertEqual(observed, [builders._ACTIVATION_EVENTS_CAP_BYTES])


if __name__ == "__main__":
    unittest.main()
