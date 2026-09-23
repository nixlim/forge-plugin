"""Per-cluster driver for the revision9 cli-surfaces test split (bead forge-plugin-kzu0, lane B2 of
docs/analysis/refactor-overnight-brief-2026-09-23.md).

    python3 .refactor/revision9-cli-run-cluster.py mixin
    python3 .refactor/revision9-cli-run-cluster.py <family> [<family> ...]

For each label: require a clean tracked tree and absent evidence paths, collect the current
test IDs, build the id map (families only), dry-run the mover, freeze the body snapshot of the
gate's --pkg scope (tests), apply, run verify.sh (manifest oracle --strict-bodies, ruff,
file-length, types, lint-imports, ID compare in identity or mapping mode, the focused set),
run the repository's own file-length guard, prove the new module imports without PYTHONPATH,
record the cluster in .refactor/decompose-records-revision9-cli.json and commit the pure mover
output plus its evidence. Stops on the first failure and leaves the tree as it is for
inspection (section 8 of the brief: the orchestrator reverts, never the driver).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

D = os.path.expanduser("~/foundry-of-zero/refactor-python/skills/decompose/scripts")
S = os.path.expanduser("~/foundry-of-zero/refactor-python/skills/split-module/scripts")
SRC = "tests/test_revision9_cli_surfaces.py"
SRC_MODULE = "test_revision9_cli_surfaces"
SRC_CLASS = "Revision9BoundCLIIntegrationTests"
PKG = "tests"
PLAN = ".refactor/plan-revision9-cli.json"
RECORDS = ".refactor/decompose-records-revision9-cli.json"
TRAILER = (
    "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>\n"
)

ENV = dict(os.environ)
ENV.pop("FORGE_SESSION_PID", None)
ENV.update(
    PYTHONPATH="scripts:scripts/forge",
    MYPYPATH="scripts:scripts/forge",
    TMPDIR="/dev/shm/refactor-s6",
    PATH=os.path.expanduser("~/.local/bin") + ":" + ENV["PATH"],
    REFACTOR_MAX_LINES="1000",
    REFACTOR_TYPE_CMD=(
        "mypy --no-error-summary --no-color-output --show-error-codes "
        "--hide-error-context scripts/forge/forge_cli"
    ),
    REFACTOR_TEST_CMD="python3 -m unittest discover -s tests -p 'test_revision9_cli_surfaces*.py'",
)
ROOT = os.getcwd()


def run(argv, log=None, label="", env=None):
    proc = subprocess.run(argv, env=env or ENV, capture_output=True, text=True)
    text = f"$ {' '.join(argv)}\n{proc.stdout}{proc.stderr}[exit {proc.returncode}]\n"
    if log:
        with open(log, "a", encoding="utf-8") as handle:
            handle.write(f"== {label}\n{text}\n")
    return proc.returncode, text


def code_lines(path):
    with open(path, encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip() and not line.strip().startswith("#"))


def fail(msg):
    print(f"STOP: {msg}")
    sys.exit(1)


def head_sha(short=False):
    argv = ["git", "rev-parse", "--short", "HEAD"] if short else ["git", "rev-parse", "HEAD"]
    return run(argv)[1].split("\n")[1].strip()


def load_cluster(label):
    plan = json.load(open(PLAN, encoding="utf-8"))
    if label == "mixin":
        mixin = plan["mixin"]
        return {
            "label": "mixin", "shape": "mixin", "methods": mixin["methods"],
            "dest": "tests/_revision9_cli_support.py", "target_class": "Revision9CliSupport",
            "module": "_revision9_cli_support", "test_mode": "identity",
        }
    for family in plan["families"]:
        if family["name"] == label:
            return {
                "label": label, "shape": "class", "methods": family["methods"],
                "dest": family["module"], "target_class": family["class"],
                "module": os.path.splitext(os.path.basename(family["module"]))[0],
                "test_mode": "mapping",
            }
    fail(f"unknown label {label!r} (not 'mixin' and not a family in {PLAN})")


def paths_for(label):
    return {
        "manifest": (
            f".refactor/{'mixin' if label == 'mixin' else 'family'}-revision9-cli-{label}.json"
        ),
        "snap": f".refactor/revision9-cli-{label}-before.json",
        "ids": f".refactor/tests-revision9-cli-{label}.json",
        "idmap": f".refactor/idmap-revision9-cli-{label}.json",
        "dryrun": f".refactor/dryrun-revision9-cli-{label}.txt",
        "log": f".refactor/apply-revision9-cli-{label}.txt",
        "gate": f".refactor/gate-revision9-cli-{label}.txt",
    }


def preflight(cluster, p):
    label = cluster["label"]
    rc, dirty = run(["git", "status", "--porcelain", "--untracked-files=no"])
    if rc or dirty.split("\n", 1)[1].split("[exit")[0].strip():
        fail(f"{label}: tracked tree not clean:\n{dirty}")
    # The planner's id maps (.refactor/idmap-revision9-cli-<family>.json) may pre-exist; collect_ids
    # regenerates them from the current IDs and refuses a mismatch instead of a pre-existing file.
    keys = ["manifest", "snap", "ids", "log", "gate"]
    if label != "mixin":
        keys.append("dryrun")
    for key in keys:
        if os.path.exists(p[key]):
            fail(f"{label}: evidence path already exists: {p[key]}")
    if os.path.exists(cluster["dest"]):
        fail(f"{label}: destination already exists: {cluster['dest']}")
    with open(p["log"], "w", encoding="utf-8") as handle:
        handle.write(f"cluster {label} on HEAD {head_sha()}\n\n")


def collect_ids(cluster, p):
    label = cluster["label"]
    snapshot = ["python3", f"{D}/collect_tests.py", "snapshot", "--start", PKG, "--out", p["ids"]]
    rc, out = run(snapshot, p["log"], "collect current test IDs")
    if rc:
        fail(f"{label}: ID snapshot failed (see {p['log']})")
    if cluster["shape"] != "class":
        return
    ids = json.load(open(p["ids"], encoding="utf-8"))["ids"]
    unit_old = {f"{SRC_MODULE}.{SRC_CLASS}.{m}" for m in cluster["methods"]}
    py_old = {f"{SRC}::{SRC_CLASS}::{m}" for m in cluster["methods"]}
    missing_unit = sorted(unit_old - set(ids["unittest"]))
    missing_py = sorted(py_old - set(ids["pytest"]))
    if missing_unit or missing_py:
        fail(f"{label}: methods absent from the current IDs: {missing_unit} {missing_py}")
    idmap = {
        "unittest": {
            f"{SRC_MODULE}.{SRC_CLASS}.{m}": f"{cluster['module']}.{cluster['target_class']}.{m}"
            for m in cluster["methods"]
        },
        "pytest": {
            f"{SRC}::{SRC_CLASS}::{m}": f"{cluster['dest']}::{cluster['target_class']}::{m}"
            for m in cluster["methods"]
        },
    }
    if os.path.exists(p["idmap"]):
        existing = json.load(open(p["idmap"], encoding="utf-8"))
        if existing != idmap:
            fail(f"{label}: pre-existing {p['idmap']} differs from the generated id map")
    with open(p["idmap"], "w", encoding="utf-8") as handle:
        json.dump(idmap, handle, indent=2, sort_keys=True)
        handle.write("\n")


def mover_argv(cluster, p):
    argv = [
        "python3", f"{D}/move_methods.py", "--project", ".", "--import-root", ROOT,
        "--source", SRC, "--class", SRC_CLASS, "--methods", ",".join(cluster["methods"]),
        "--dest", cluster["dest"], "--shape", cluster["shape"],
        "--target-class", cluster["target_class"], "--test-only",
        "--test-snapshot", p["ids"], "--format-imports", "--manifest", p["manifest"],
    ]
    if cluster["shape"] == "class":
        argv += ["--id-map", p["idmap"]]
    return argv


def move(cluster, p):
    label = cluster["label"]
    mover = mover_argv(cluster, p)
    rc, out = run(mover, p["log"], "dry run")
    if label != "mixin":
        with open(p["dryrun"], "w", encoding="utf-8") as handle:
            handle.write(out)
    if rc or "DRY RUN: verified" not in out:
        fail(f"{label}: dry run refused (see {p['log']})")
    snapshot = ["python3", f"{S}/snapshot_bodies.py", "snapshot", PKG, "--out", p["snap"]]
    if run(snapshot, p["log"], "snapshot")[0]:
        fail(f"{label}: snapshot failed (see {p['log']})")
    if run(mover + ["--apply"], p["log"], "apply")[0]:
        fail(f"{label}: apply failed (see {p['log']}); inspect git diff before recovering")


def gate(cluster, p):
    label = cluster["label"]
    verify = [
        "bash", f"{S}/verify.sh", "--pkg", PKG, "--snapshot", p["snap"],
        "--manifest", p["manifest"], "--strict-bodies",
        "--test-snapshot", p["ids"], "--test-mode", cluster["test_mode"],
    ]
    rc, out = run(verify, p["gate"], f"verify.sh (--test-mode {cluster['test_mode']})")
    if rc or "GATE: PASS" not in out:
        fail(f"{label}: gate FAILED (see {p['gate']} and .refactor-gate.log)")
    guard = ["python3", "scripts/check_file_length.py", "tests"]
    rc, out = run(guard, p["gate"], "repository file-length guard")
    if rc:
        fail(f"{label}: scripts/check_file_length.py FAILED (see {p['gate']})")
    # Lane B2 (brief section 5): the loader sweep must stay green after the relocation.
    rc, out = run(["python3", "-m", "unittest", "tests.test_cli_loader"], p["gate"], "loader sweep")
    if rc or "\nOK" not in out:
        fail(f"{label}: tests.test_cli_loader FAILED (see {p['gate']})")
    bare = dict(ENV)
    bare.pop("PYTHONPATH", None)
    module = SRC_MODULE if label == "mixin" else cluster["module"]
    rc, out = run(["python3", "-m", "unittest", f"tests.{module}"], p["gate"],
                  "import without PYTHONPATH", env=bare)
    if rc or "\nOK" not in out:
        fail(f"{label}: tests.{module} does not pass without PYTHONPATH (see {p['gate']})")
    # Critique finding 3: the new module must also import STANDALONE (first in a Gate 1 shard)
    # without PYTHONPATH, i.e. its generated header must not import codex_orchestrator before
    # the constants module has inserted scripts/ into sys.path.
    standalone = ["python3", "-c", f"import tests.{cluster['module']}"]
    rc, out = run(standalone, p["gate"], "standalone import without PYTHONPATH", env=bare)
    if rc:
        fail(f"{label}: tests.{cluster['module']} is not importable standalone without PYTHONPATH")
    evidence = [p["manifest"], p["snap"], p["ids"], p["log"], p["gate"]]
    if cluster["shape"] == "class":
        evidence += [p["idmap"], p["dryrun"]]
    return evidence


def record(cluster, p, sha, dest_lines, src_lines):
    records = []
    if os.path.exists(RECORDS):
        records = json.load(open(RECORDS, encoding="utf-8"))
    records.append({
        "label": cluster["label"], "shape": cluster["shape"], "commit": sha,
        "snapshot": p["snap"], "manifest": p["manifest"], "test_snapshot": p["ids"],
        "id_map": p["idmap"] if cluster["shape"] == "class" else None,
        "dest": cluster["dest"], "dest_code_lines": dest_lines, "source_code_lines": src_lines,
        "methods": len(cluster["methods"]),
    })
    with open(RECORDS, "w", encoding="utf-8") as handle:
        json.dump(records, handle, indent=2)
        handle.write("\n")


def commit(cluster, p, evidence, dest_lines, src_lines):
    label = cluster["label"]
    run(["git", "add", SRC, cluster["dest"], *evidence])
    if cluster["shape"] == "mixin":
        subject = f"refactor(tests): move the {len(cluster['methods'])} revision9 cli-surfaces "
        subject += "helpers into "
        subject += "tests/_revision9_cli_support.py (mixin shape, tier 1)"
        what = (
            "Every non-test helper of Revision9BoundCLIIntegrationTests moved verbatim by\n"
            "move_methods.py --shape mixin --import-root \"$PWD\" --format-imports; the class\n"
            "header becomes (Revision9CliSupport, CLI_FIXTURE_SUPPORT.ForgeCLIFixture).\n"
            "Test IDs identical.\n"
        )
    else:
        subject = (
            f"refactor(tests): move the {label} family ({len(cluster['methods'])} tests) to "
            f"{cluster['dest']} (class shape, tier 1)"
        )
        what = (
            f"Family {label} of the revision9 cli-surfaces split moved verbatim by\n"
            f"move_methods.py --shape\n"
            f"class --import-root \"$PWD\" --format-imports into {cluster['target_class']};\n"
            f"test IDs mapped 1:1 in both collectors ({p['idmap']}).\n"
        )
    message = (
        f"{subject}\n\n{what}"
        "Manifest oracle --strict-bodies, ruff, file-length, types, lint-imports, the ID compare\n"
        "the focused revision9 cli-surfaces set and tests.test_cli_loader PASS "
        "(evidence under .refactor/). "
        f"{cluster['dest']}: {dest_lines} code lines; {SRC}: {src_lines}. "
        "No production file changed.\n\n" + TRAILER
    )
    proc = subprocess.run(["git", "commit", "-q", "-F", "-"], env=ENV, input=message,
                          capture_output=True, text=True)
    if proc.returncode:
        fail(f"{label}: commit failed:\n{proc.stdout}{proc.stderr}")
    sha = head_sha()
    # The records file stays untracked until the finalize commit (brief section 7 item 1).
    record(cluster, p, sha, dest_lines, src_lines)
    print(f"{label}: committed {sha[:7]}")


def run_cluster(label):
    cluster = load_cluster(label)
    p = paths_for(label)
    count = len(cluster["methods"])
    print(f"--- {label} ({cluster['shape']}, {count} methods) -> {cluster['dest']}")
    preflight(cluster, p)
    collect_ids(cluster, p)
    move(cluster, p)
    evidence = gate(cluster, p)
    dest_lines, src_lines = code_lines(cluster["dest"]), code_lines(SRC)
    print(f"{label}: gate PASS, dest {dest_lines} code lines, source {src_lines}")
    commit(cluster, p, evidence, dest_lines, src_lines)


def main():
    labels = sys.argv[1:]
    if not labels:
        fail("usage: revision9-cli-run-cluster.py mixin | <family> [<family> ...]")
    for label in labels:
        run_cluster(label)


if __name__ == "__main__":
    main()
