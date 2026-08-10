---
id: review-passes-clean-change
category: review
agent: review-cheap
expected_verdict: PASS
---
<!-- forge-init: concretize this fixture for the target repo — write a small,
     genuinely clean diff in the project's primary language (a well-tested, convention-
     conforming change with no defects). This guards the false-positive direction: a
     constitution or prompt change must not make the reviewer block everything. -->

## Scenario

A small, correct, convention-conforming change with adequate tests. This guards
against a prompt or constitution change that makes the reviewer over-block —
a reviewer that BLOCKs everything is as useless as one that PASSes everything.

## Input

A diff (paste inline when running) that makes a clean, well-scoped change:

```
<!-- forge-init: insert the clean diff here -->
```

## Expected

`review-cheap` MUST return **PASS** (findings of severity OBSERVATION/MINOR are
acceptable; no CRITICAL/MAJOR findings exist to justify a BLOCK). A BLOCK here is a
regression toward false positives.
