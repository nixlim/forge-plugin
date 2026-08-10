---
id: review-catches-planted-bug
category: review
agent: review-cheap
expected_verdict: BLOCK
---
<!-- forge-init: concretize this fixture for the target repo — write a small, realistic
     diff in the project's primary language that plants ONE clear defect the
     constitution's Incorrectness/Incompleteness lenses must catch (a resource leak,
     an unchecked error path, an off-by-one on a boundary the project actually has).
     Prefer a bug class from the project's own history. Keep this file's frontmatter. -->

## Scenario

A code change introduces a clear, planted defect that the review constitution's
Incorrectness/Incompleteness lenses must catch. This guards against a prompt or
constitution change that weakens the reviewer's bug-finding ability.

## Input

A diff (paste inline when running, or point the agent at a fixture branch) that
introduces the planted defect:

```
<!-- forge-init: insert the planted-bug diff here -->
```

## Expected

`review-cheap` MUST return **BLOCK** and identify the planted defect and its error
path. A PASS here is a regression — the reviewer has gone blind to a bug class it
must catch.
