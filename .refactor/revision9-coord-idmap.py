#!/usr/bin/env python3
"""Build the class-shape id map for one family of the test_revision9_coordination split.

usage: revision9-coord-idmap.py <snapshot.json> <family-stem> <FamilyClass> <out.json> <test,...>
Old IDs are read from the current test snapshot (namespace preset); new IDs substitute the
module stem and class. Fails if any listed test is missing from the snapshot in either collector.
"""
import json
import sys

snapshot_path, stem, cls, out_path, tests_csv = sys.argv[1:6]
tests = [t for t in tests_csv.split(",") if t and t.startswith("test_")]
snap = json.load(open(snapshot_path))


def ids(collector):
    node = snap["ids"][collector]
    if isinstance(node, dict):
        node = list(node)
    return list(node)


unit = set(ids("unittest"))
pyt = set(ids("pytest"))
old_module = "test_revision9_coordination"
old_class = "Revision9BuilderBatchTests"
mapping = {"unittest": {}, "pytest": {}}
missing = []
for t in tests:
    u_old = f"{old_module}.{old_class}.{t}"
    p_old = f"tests/{old_module}.py::{old_class}::{t}"
    if u_old not in unit or p_old not in pyt:
        missing.append(t)
        continue
    mapping["unittest"][u_old] = f"{stem}.{cls}.{t}"
    mapping["pytest"][p_old] = f"tests/{stem}.py::{cls}::{t}"
if missing:
    print("missing from snapshot:", missing, file=sys.stderr)
    sys.exit(1)
json.dump(mapping, open(out_path, "w"), indent=1, sort_keys=True)
count = len(mapping["unittest"])
print(f"id map: {count} unittest + {len(mapping['pytest'])} pytest -> {out_path}")
