"""Per-cluster driver for the MergeEngine decompose on the project tree (bead forge-plugin-37fr).

For each cluster in .refactor/merge-engine-sim-clusters.json (optionally a range): require a
clean tracked tree, dry-run the mover, snapshot exactly the gate's --pkg scope, apply, run
verify.sh (manifest oracle --strict-bodies, per-cluster focused set), record the mypy key delta
(stop on NEW or GONE), run the parallel full set at the scheduled checkpoints, and commit the
pure mover output plus its evidence. Stops on the first failure and leaves the tree as it is.

    python3 .refactor/merge-engine-run-cluster.py c01 [c29] [--pause-before-commit]
"""
import json
import os
import subprocess
import sys

D = os.path.expanduser("~/foundry-of-zero/refactor-python/skills/decompose/scripts")
S = os.path.expanduser("~/foundry-of-zero/refactor-python/skills/split-module/scripts")
SRC = "scripts/forge/forge_cli/app/_merge_engine.py"
PKG = "scripts/forge/forge_cli"
SPEC = ".refactor/merge-engine-sim-clusters.json"
PER_CLUSTER_TESTS = (
    "python3 -m unittest tests.test_cli_merge_adapters tests.test_cli_merge_lifecycle "
    "tests.test_cli_merge_store tests.test_cli_loader"
)
# Every fifth cluster, every cluster moving a census-patched method, and the last one.
FULL_SET = {"c01", "c05", "c10", "c15", "c16", "c17", "c19", "c20", "c23", "c25", "c29"}
TRAILER = (
    "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>\n"
    "Claude-Session: https://claude.ai/code/session_01R2nYdBUZ5BtVD28Tx45xe3\n"
)

ENV = dict(os.environ)
for key in ("FORGE_SESSION_PID", "REFACTOR_TYPE_CMD"):
    ENV.pop(key, None)
ENV.update(
    PYTHONPATH="scripts:scripts/forge",
    MYPYPATH="scripts:scripts/forge",
    TMPDIR="/dev/shm/forge-gate",
    PATH=os.path.expanduser("~/.local/bin") + ":" + ENV["PATH"],
    REFACTOR_TEST_CMD=PER_CLUSTER_TESTS,
)


def run(argv, log=None, label=""):
    proc = subprocess.run(argv, env=ENV, capture_output=True, text=True)
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


def cluster_ids(argv):
    ids = [a for a in argv if a.startswith("c") and a[1:].isdigit()]
    first = ids[0]
    last = ids[1] if len(ids) > 1 else first
    return first, last


def main():
    first, last = cluster_ids(sys.argv[1:])
    pause = "--pause-before-commit" in sys.argv
    spec = json.load(open(SPEC, encoding="utf-8"))
    selected = [c for c in spec["clusters"] if first <= c["id"] <= last]
    for cluster in selected:
        run_cluster(cluster, pause and cluster is selected[-1])


def paths_for(cluster):
    cid, name = cluster["id"], cluster["name"]
    return {
        "dest": f"scripts/forge/forge_cli/app/{cluster['dest']}",
        "manifest": f".refactor/merge-engine-{name}.json",
        "snap": f".refactor/merge-engine-{cid}-before.json",
        "log": f".refactor/apply-merge-engine-{cid}-{name}.txt",
        "gate": f".refactor/gate-merge-engine-{cid}-{name}.txt",
        "types": f".refactor/types-delta-merge-engine-{cid}-{name}.txt",
        "full": f".refactor/fullset-merge-engine-{cid}-{name}",
    }


def preflight(cid, p):
    rc, dirty = run(["git", "status", "--porcelain", "--untracked-files=no"])
    if rc or dirty.split("\n", 1)[1].split("[exit")[0].strip():
        fail(f"{cid}: tracked tree not clean:\n{dirty}")
    for key in ("manifest", "snap", "log", "gate", "types"):
        if os.path.exists(p[key]):
            fail(f"{cid}: evidence path already exists: {p[key]}")
    head = run(["git", "rev-parse", "HEAD"])[1].split("\n")[1].strip()
    with open(p["log"], "w", encoding="utf-8") as handle:
        handle.write(f"cluster {cid} on HEAD {head}\n\n")


def move(cluster, p):
    cid = cluster["id"]
    mover = [
        "python3", f"{D}/move_methods.py", "--project", ".", "--source", SRC,
        "--class", "MergeEngine", "--methods", ",".join(cluster["methods"]),
        "--dest", p["dest"], "--import-root", "scripts/forge", "--shape", "function",
        "--annotate-self", "--format-imports", "--manifest", p["manifest"],
    ]
    rc, out = run(mover, p["log"], "dry run")
    if rc or "DRY RUN: verified" not in out:
        fail(f"{cid}: dry run refused (see {p['log']})")
    snapshot = ["python3", f"{S}/snapshot_bodies.py", "snapshot", PKG, "--out", p["snap"]]
    if run(snapshot, p["log"], "snapshot")[0]:
        fail(f"{cid}: snapshot failed (see {p['log']})")
    if run(mover + ["--apply"], p["log"], "apply")[0]:
        fail(f"{cid}: apply failed (see {p['log']}); inspect git diff before recovering")


def gate(cid, p):
    verify = [
        "bash", f"{S}/verify.sh", "--pkg", PKG, "--snapshot", p["snap"],
        "--manifest", p["manifest"], "--strict-bodies",
    ]
    rc, out = run(verify, p["gate"], "verify.sh (per-cluster focused set)")
    if rc or "GATE: PASS" not in out:
        fail(f"{cid}: gate FAILED (see {p['gate']} and .refactor-gate.log)")
    delta = ["python3", ".refactor/merge-engine-sim-tool-types_delta.py", cid]
    rc, out = run(delta, p["types"], "mypy keys")
    if rc or "NEW=0 GONE=0" not in out:
        fail(f"{cid}: mypy key delta is not zero (see {p['types']})")
    evidence = [p["manifest"], p["snap"], p["log"], p["gate"], p["types"]]
    if cid in FULL_SET:
        full_log = p["full"] + ".txt"
        full_set = ["bash", ".refactor/merge-engine-full-set.sh", p["full"]]
        rc, out = run(full_set, full_log, "full set")
        if rc or "7/7 modules OK" not in out:
            fail(f"{cid}: full set FAILED (see {full_log})")
        evidence.append(full_log)
    return evidence


def run_cluster(cluster, pause):
    cid, name = cluster["id"], cluster["name"]
    p = paths_for(cluster)
    print(f"--- {cid} {name} -> {p['dest']}")
    preflight(cid, p)
    move(cluster, p)
    evidence = gate(cid, p)
    dest_lines, src_lines = code_lines(p["dest"]), code_lines(SRC)
    print(f"{cid} {name}: gate PASS, mypy NEW 0 GONE 0, dest {dest_lines}, shell {src_lines}")
    if pause:
        print(f"{cid}: paused before commit for operator inspection; evidence: {evidence}")
        return
    commit(cluster, p["dest"], evidence, dest_lines, src_lines)


def commit(cluster, dest, evidence, dest_lines, src_lines):
    cid, name = cluster["id"], cluster["name"]
    run(["git", "add", SRC, dest, *evidence])
    message = (
        f"refactor(app): move {name} methods to {cluster['dest']} (tier 1, function shape)\n\n"
        f"Cluster {cid} of the MergeEngine decomposition (bead forge-plugin-37fr, plan\n"
        f".refactor/plan-merge-engine.md): {len(cluster['methods'])} method(s) moved verbatim by\n"
        f"move_methods.py --shape function --annotate-self --format-imports; the class keeps\n"
        f"same-named bindings. Manifest oracle --strict-bodies, ruff, file-length, mypy ratchet\n"
        f"(NEW 0, GONE 0), lint-imports and the focused tests PASS (evidence under .refactor/).\n"
        f"{dest}: {dest_lines} code lines; _merge_engine.py: {src_lines}.\n\n{TRAILER}"
    )
    proc = subprocess.run(["git", "commit", "-q", "-F", "-"], env=ENV, input=message,
                          capture_output=True, text=True)
    if proc.returncode:
        fail(f"{cid}: commit failed:\n{proc.stdout}{proc.stderr}")
    sha = run(["git", "rev-parse", "--short", "HEAD"])[1].split("\n")[1].strip()
    print(f"{cid} {name}: committed {sha}")


if __name__ == "__main__":
    main()
