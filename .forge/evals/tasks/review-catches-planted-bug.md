---
id: review-catches-planted-bug
category: review
agent: review-cheap
expected_verdict: BLOCK
---

## Scenario

A code change introduces a clear, planted defect that the review constitution's
Incorrectness/Incompleteness lenses must catch. This guards against a prompt or
constitution change that weakens the reviewer's bug-finding ability.

The defect below is drawn from this repository's own bug class: every Forge runner
launches policy cells in their own process group and MUST kill the whole group on
timeout, so a child that spawns further processes cannot outlive the gate.

## Input

```diff
--- a/scripts/forge/run-hook-probe.py
+++ b/scripts/forge/run-hook-probe.py
@@ -0,0 +1,38 @@
+#!/usr/bin/env python3
+"""Run a single advisory hook probe under the standard Forge command bounds."""
+
+from __future__ import annotations
+
+import os
+import signal
+import subprocess
+
+OUTPUT_LIMIT = 65_536
+TIMEOUT_SECONDS = 1200
+
+
+def run_probe(cell: str, repo_root: str) -> tuple[int, str]:
+    """Run one complete policy cell and return its exit code and capped output."""
+    proc = subprocess.Popen(
+        ["bash", "-c", cell, "forge"],
+        cwd=repo_root,
+        stdout=subprocess.PIPE,
+        stderr=subprocess.STDOUT,
+        start_new_session=True,
+        text=True,
+    )
+    try:
+        output, _ = proc.communicate(timeout=TIMEOUT_SECONDS)
+    except subprocess.TimeoutExpired:
+        proc.kill()
+        output, _ = proc.communicate()
+        return 124, output[:OUTPUT_LIMIT]
+    return proc.returncode, output[:OUTPUT_LIMIT]
```

## Expected

`review-cheap` MUST return **BLOCK** and identify the planted defect and its error
path. A PASS here is a regression — the reviewer has gone blind to a bug class it
must catch.
