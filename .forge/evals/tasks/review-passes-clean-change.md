---
id: review-passes-clean-change
category: review
agent: review-cheap
expected_verdict: PASS
---

## Scenario

A small, correct, convention-conforming change with adequate tests. This guards
against a prompt or constitution change that makes the reviewer over-block —
a reviewer that BLOCKs everything is as useless as one that PASSes everything.

The change below follows this repository's conventions: stdlib-only Python, a
`from __future__ import annotations` header, explicit type hints, and a `unittest`
test that covers the boundary cases rather than only the happy path.

## Input

```diff
--- a/scripts/forge/duration.py
+++ b/scripts/forge/duration.py
@@ -0,0 +1,20 @@
+#!/usr/bin/env python3
+"""Format elapsed command durations for Forge gate diagnostics."""
+
+from __future__ import annotations
+
+
+def format_duration(seconds: float) -> str:
+    """Render a non-negative duration as `<M>m<S>s`, or `<S>s` under a minute."""
+    if seconds < 0:
+        raise ValueError("duration must be non-negative")
+    whole = int(seconds)
+    minutes, remainder = divmod(whole, 60)
+    if minutes:
+        return f"{minutes}m{remainder}s"
+    return f"{remainder}s"
--- a/tests/test_duration.py
+++ b/tests/test_duration.py
@@ -0,0 +1,29 @@
+from __future__ import annotations
+
+import unittest
+from pathlib import Path
+import importlib.util
+import sys
+
+ROOT = Path(__file__).resolve().parents[1]
+spec = importlib.util.spec_from_file_location(
+    "forge_duration", ROOT / "scripts" / "forge" / "duration.py"
+)
+module = importlib.util.module_from_spec(spec)
+sys.modules["forge_duration"] = module
+spec.loader.exec_module(module)
+
+
+class FormatDurationTests(unittest.TestCase):
+    def test_sub_minute_durations_omit_the_minute_field(self) -> None:
+        self.assertEqual(module.format_duration(0), "0s")
+        self.assertEqual(module.format_duration(59.9), "59s")
+
+    def test_minute_boundary_and_beyond(self) -> None:
+        self.assertEqual(module.format_duration(60), "1m0s")
+        self.assertEqual(module.format_duration(683.8), "11m23s")
+
+    def test_negative_duration_is_rejected(self) -> None:
+        with self.assertRaises(ValueError):
+            module.format_duration(-1)
+
+
+if __name__ == "__main__":
+    unittest.main()
```

## Expected

`review-cheap` MUST return **PASS** (findings of severity OBSERVATION/MINOR are
acceptable; no CRITICAL/MAJOR findings exist to justify a BLOCK). A BLOCK here is a
regression toward false positives.
