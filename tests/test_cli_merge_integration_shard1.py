"""Second serial shard of the real-remote merge integration matrix."""

from __future__ import annotations

import unittest

from tests import test_cli_merge_integration as INTEGRATION


def load_tests(
    _loader: unittest.TestLoader,
    _standard_tests: unittest.TestSuite,
    _pattern: str | None,
) -> unittest.TestSuite:
    return INTEGRATION.merge_integration_shard_suite(1)
