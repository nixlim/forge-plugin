"""Tier 2 driver for the MergeEngine decompose (bead forge-plugin-37fr, second wave).

For each extraction in .refactor/merge-engine-tier2-plan.json (optionally a range): require a
clean tracked tree, dry-run extract_ranges.py, check rope's inferred parameters (<= 6) and
outputs (<= 1) against the plan, snapshot exactly the gate's --pkg scope, apply, run verify.sh
(manifest oracle --strict-bodies, per-cluster focused set), record the mypy key delta (stop on
NEW or GONE), run the parallel full set at the scheduled checkpoints, and commit. Stops on the
first failure and leaves the tree as it is.

    python3 .refactor/merge-engine-run-extract.py e01 [e10] [--pause-before-commit]
"""
import json
import os
import subprocess
import sys

D = os.path.expanduser("~/foundry-of-zero/refactor-python/skills/decompose/scripts")
S = os.path.expanduser("~/foundry-of-zero/refactor-python/skills/split-module/scripts")
PKG = "scripts/forge/forge_cli"
PLAN = ".refactor/merge-engine-tier2-plan.json"
PER_CLUSTER_TESTS = (
    "python3 -m unittest tests.test_cli_merge_adapters tests.test_cli_merge_lifecycle "
    "tests.test_cli_merge_store tests.test_cli_loader"
)
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


def main():
    ids = [a for a in sys.argv[1:] if a.startswith("e") and a[1:].isdigit()]
    first, last = ids[0], (ids[1] if len(ids) > 1 else ids[0])
    pause = "--pause-before-commit" in sys.argv
    plan = json.load(open(PLAN, encoding="utf-8"))
    selected = [e for e in plan["extractions"] if first <= e["id"] <= last]
    for item in selected:
        run_extract(item, set(plan["full_set_after"]), pause and item is selected[-1])


def paths_for(item):
    eid, name = item["id"], item["name"]
    return {
        "manifest": f".refactor/merge-engine-t2-{eid}-{name}.json",
        "snap": f".refactor/merge-engine-t2-{eid}-before.json",
        "log": f".refactor/apply-merge-engine-t2-{eid}-{name}.txt",
        "gate": f".refactor/gate-merge-engine-t2-{eid}-{name}.txt",
        "types": f".refactor/types-delta-merge-engine-t2-{eid}-{name}.txt",
        "full": f".refactor/fullset-merge-engine-t2-{eid}-{name}",
    }


def preflight(eid, p):
    rc, dirty = run(["git", "status", "--porcelain", "--untracked-files=no"])
    if rc or dirty.split("\n", 1)[1].split("[exit")[0].strip():
        fail(f"{eid}: tracked tree not clean:\n{dirty}")
    for key in ("manifest", "snap", "log", "gate", "types"):
        if os.path.exists(p[key]):
            fail(f"{eid}: evidence path already exists: {p[key]}")
    head = run(["git", "rev-parse", "HEAD"])[1].split("\n")[1].strip()
    with open(p["log"], "w", encoding="utf-8") as handle:
        handle.write(f"extraction {eid} on HEAD {head}\n\n")


def extractor_argv(item, p):
    argv = [
        "python3", f"{D}/extract_ranges.py", "--project", ".", "--source", item["source"],
        "--function", item["function"], "--start", str(item["start"]), "--end", str(item["end"]),
        "--name", item["name"], "--import-root", "scripts/forge", "--format-imports",
        "--manifest", p["manifest"],
    ]
    if item.get("dest"):
        argv += ["--dest", item["dest"]]
    return argv


def check_manifest_text(eid, item, out):
    """The dry run prints the manifest; check rope's inference against the plan and the rule."""
    start = out.find("{")
    end = out.rfind("}")
    if start < 0 or end < 0:
        fail(f"{eid}: no manifest in dry-run output")
    manifest = json.loads(out[start : end + 1])
    op = manifest["operations"][0]
    params, outputs = op.get("parameters", []), op.get("outputs", [])
    if len(params) > 6 or len(outputs) > 1:
        fail(f"{eid}: rope inferred {len(params)} params / {len(outputs)} outputs: "
             f"{params} {outputs}")
    expect = item["expect"]
    if (len(params), len(outputs)) != (expect["params"], expect["outputs"]):
        fail(f"{eid}: inference differs from plan: {params} -> {outputs}")
    if (op["start_line"], op["end_line"], op["name"]) != (item["start"], item["end"], item["name"]):
        fail(f"{eid}: manifest range/name differs from plan")
    return params, outputs


def extract(item, p):
    eid = item["id"]
    argv = extractor_argv(item, p)
    rc, out = run(argv, p["log"], "dry run")
    if rc or "DRY RUN: verified" not in out:
        fail(f"{eid}: dry run refused (see {p['log']})")
    params, outputs = check_manifest_text(eid, item, out)
    snapshot = ["python3", f"{S}/snapshot_bodies.py", "snapshot", PKG, "--out", p["snap"]]
    if run(snapshot, p["log"], "snapshot")[0]:
        fail(f"{eid}: snapshot failed (see {p['log']})")
    if run(argv + ["--apply"], p["log"], "apply")[0]:
        fail(f"{eid}: apply failed (see {p['log']}); inspect git diff before recovering")
    return params, outputs


def gate(eid, p, full_set):
    verify = [
        "bash", f"{S}/verify.sh", "--pkg", PKG, "--snapshot", p["snap"],
        "--manifest", p["manifest"], "--strict-bodies",
    ]
    rc, out = run(verify, p["gate"], "verify.sh (per-cluster focused set)")
    if rc or "GATE: PASS" not in out:
        fail(f"{eid}: gate FAILED (see {p['gate']} and .refactor-gate.log)")
    delta = ["python3", ".refactor/merge-engine-sim-tool-types_delta.py", eid]
    rc, out = run(delta, p["types"], "mypy keys")
    if rc or "NEW=0 GONE=0" not in out:
        fail(f"{eid}: mypy key delta is not zero (see {p['types']})")
    evidence = [p["manifest"], p["snap"], p["log"], p["gate"], p["types"]]
    if full_set:
        full_log = p["full"] + ".txt"
        rc, out = run(["bash", ".refactor/merge-engine-full-set.sh", p["full"]], full_log, "full")
        if rc or "7/7 modules OK" not in out:
            fail(f"{eid}: full set FAILED (see {full_log})")
        evidence.append(full_log)
    return evidence


def run_extract(item, full_after, pause):
    eid, name = item["id"], item["name"]
    p = paths_for(item)
    print(f"--- {eid} {item['function']} {item['start']}-{item['end']} -> {name}")
    preflight(eid, p)
    params, outputs = extract(item, p)
    evidence = gate(eid, p, eid in full_after)
    src_lines = code_lines(item["source"])
    dest_lines = code_lines(item["dest"]) if item.get("dest") else None
    print(f"{eid}: gate PASS, mypy NEW 0 GONE 0, params {params} -> {outputs}, "
          f"source {src_lines}, dest {dest_lines}")
    if pause:
        print(f"{eid}: paused before commit; evidence: {evidence}")
        return
    commit(item, evidence, params, outputs, src_lines, dest_lines)


def commit(item, evidence, params, outputs, src_lines, dest_lines):
    eid, name = item["id"], item["name"]
    paths = [item["source"], *evidence] + ([item["dest"]] if item.get("dest") else [])
    run(["git", "add", *paths])
    where = f" into {item['dest']} ({dest_lines} code lines)" if item.get("dest") else ""
    message = (
        f"refactor(app): extract {name} from {item['function']} (tier 2, declared range)\n\n"
        f"Extraction {eid} of the MergeEngine decomposition second wave (bead forge-plugin-37fr,\n"
        f".refactor/merge-engine-tier2-plan.json): lines {item['start']}-{item['end']} of\n"
        f"{item['source']} extracted by extract_ranges.py --format-imports{where};\n"
        f"rope inferred parameters {params} and outputs {outputs}. Manifest oracle\n"
        f"--strict-bodies, ruff, file-length, mypy ratchet (NEW 0, GONE 0), lint-imports and the\n"
        f"focused tests PASS (evidence under .refactor/). Source module now {src_lines} code\n"
        f"lines.\n\n"
        f"{TRAILER}"
    )
    proc = subprocess.run(["git", "commit", "-q", "-F", "-"], env=ENV, input=message,
                          capture_output=True, text=True)
    if proc.returncode:
        fail(f"{eid}: commit failed:\n{proc.stdout}{proc.stderr}")
    sha = run(["git", "rev-parse", "--short", "HEAD"])[1].split("\n")[1].strip()
    print(f"{eid} {name}: committed {sha}")


if __name__ == "__main__":
    main()
