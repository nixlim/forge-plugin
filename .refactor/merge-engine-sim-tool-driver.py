"""Sequential sim driver (throwaway clone only). Per cluster: dry run -> snapshot -> apply ->
verify.sh --fast (compile, ruff, file-length, types, lint-imports, manifest oracle) -> mypy key \
delta -> commit.
Stops on the first failure. Run from the sim repo root."""

import json
import os
import re
import subprocess
import sys

D = "/home/agents/foundry-of-zero/refactor-python/skills/decompose/scripts"
S = "/home/agents/foundry-of-zero/refactor-python/skills/split-module/scripts"
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = "scripts/forge/forge_cli/app/_merge_engine.py"
PKG = "scripts/forge/forge_cli"
INV = "/home/agents/foundry-of-zero/forge-plugin/.refactor/merge-engine-inventory.json"

env = dict(os.environ)
for k in ("FORGE_SESSION_PID", "REFACTOR_TYPE_CMD"):
    env.pop(k, None)
env.update(
    PYTHONPATH="scripts:scripts/forge",
    MYPYPATH="scripts:scripts/forge",
    TMPDIR="/dev/shm/forge-gate",
    PATH=os.path.expanduser("~/.local/bin") + ":" + env["PATH"],
)


def sh(argv, **kw):
    return subprocess.run(argv, env=env, capture_output=True, text=True, **kw)


def code_lines(path):
    return sum(
        1
        for line in open(path, encoding="utf-8")
        if line.strip() and not line.strip().startswith("#")
    )


spec = json.load(open(os.path.join(HERE, "clusters.json")))
inv = json.load(open(INV))
order = [m["name"] for m in inv["methods"]]
pos = {n: i for i, n in enumerate(order)}
assigned = list(spec["stays"])
for c in spec["clusters"]:
    assert c["methods"] == sorted(c["methods"], key=pos.__getitem__), (
        f"{c['id']} not in source order"
    )
    assigned += c["methods"]
assert sorted(assigned) == sorted(order), (
    set(order) - set(assigned),
    [n for n in assigned if assigned.count(n) > 1],
)
names = [c["name"] for c in spec["clusters"]]
assert len(set(names)) == len(names) and not {"inventory", "seeds", "inventory-seeded"} & set(names)
print(
    f"assignment ok: {len(order)} methods = {len(spec['stays'])} stay + \
{len(assigned) - len(spec['stays'])} moved in {len(names)} clusters"
)
if "--check-only" in sys.argv:
    sys.exit(0)

start = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else None
results_path = ".refactor/merge-engine-sim-results.json"
results = json.load(open(results_path)) if os.path.exists(results_path) else []
done = {r["id"] for r in results}
for c in spec["clusters"]:
    if c["id"] in done:
        continue
    cid, name = c["id"], c["name"]
    dest = f"scripts/forge/forge_cli/app/{c['dest']}"
    manifest = f".refactor/merge-engine-{name}.json"
    snap = f".refactor/merge-engine-{cid}-before.json"
    argv = [
        "python3",
        f"{D}/move_methods.py",
        "--project",
        ".",
        "--source",
        SRC,
        "--class",
        "MergeEngine",
        "--methods",
        ",".join(c["methods"]),
        "--dest",
        dest,
        "--import-root",
        "scripts/forge",
        "--shape",
        "function",
        "--annotate-self",
        "--format-imports",
        "--manifest",
        manifest,
    ]
    dry = sh(argv)
    transcript = f".refactor/dryrun-merge-engine-{cid}-{name}.txt"
    open(transcript, "w").write(
        "$ " + " ".join(argv) + "\n" + dry.stdout + dry.stderr + f"\n[exit {dry.returncode}]\n"
    )
    if dry.returncode != 0 or "DRY RUN: verified" not in dry.stdout:
        print(
            f"{cid} {name}: DRY RUN REFUSED/FAILED rc={dry.returncode}\n\
{(dry.stdout + dry.stderr)[-3000:]}"
        )
        sys.exit(1)
    r = sh(["python3", f"{S}/snapshot_bodies.py", "snapshot", PKG, "--out", snap])
    assert r.returncode == 0, r.stdout + r.stderr
    ap = sh(argv + ["--apply"])
    open(f".refactor/merge-engine-sim-apply-{cid}-{name}.log", "w").write(
        ap.stdout[-4000:] + ap.stderr
    )
    if ap.returncode != 0:
        print(f"{cid} {name}: APPLY FAILED rc={ap.returncode}\n{(ap.stdout + ap.stderr)[-3000:]}")
        sys.exit(1)
    gate = sh(
        [
            "bash",
            f"{S}/verify.sh",
            "--pkg",
            PKG,
            "--snapshot",
            snap,
            "--manifest",
            manifest,
            "--strict-bodies",
            "--fast",
        ]
    )
    open(f".refactor/merge-engine-sim-gate-{cid}-{name}.log", "w").write(gate.stdout + gate.stderr)
    delta = sh(["python3", os.path.join(HERE, "types_delta.py"), f"{cid} {name} -> {c['dest']}"])
    open(".refactor/merge-engine-sim-types-delta.txt", "a").write(delta.stdout + delta.stderr)
    head = delta.stdout.splitlines()[0] if delta.stdout else "NO TYPES OUTPUT"
    diff = sh(["git", "diff", "-U0", "--", SRC]).stdout
    bindings = [
        line[1:].strip() for line in diff.splitlines() if re.match(r"^\+    \w+ = ", line)
    ]
    man = json.load(open(manifest))
    op = man["operations"][0]
    rec = {
        "id": cid,
        "name": name,
        "dest": c["dest"],
        "methods": c["methods"],
        "dest_code_lines": code_lines(dest),
        "source_code_lines": code_lines(SRC),
        "bindings": bindings,
        "dest_imports": op["imports"].get(dest),
        "source_imports": op["imports"].get(SRC),
        "remove_imports": op.get("remove_imports"),
        "type_checking_imports": op.get("type_checking_imports"),
        "gate": gate.stdout.strip().splitlines()[-12:],
        "types": head,
    }
    ok = gate.returncode == 0 and "GATE: PASS" in gate.stdout and "NEW=0 GONE=0" in head
    sh(["git", "add", "-A"])
    cm = sh(
        [
            "git",
            "-c",
            "user.name=sim",
            "-c",
            "user.email=sim@sim",
            "commit",
            "-q",
            "-m",
            f"refactor(app): move {name} methods to {c['dest']} (tier 1, function shape) \
[sim {cid}]",
        ]
    )
    rec["sim_commit"] = sh(["git", "rev-parse", "--short", "HEAD"]).stdout.strip()
    results.append(rec)
    json.dump(results, open(results_path, "w"), indent=1)
    print(
        f"{cid} {name}: dest={rec['dest_code_lines']} src={rec['source_code_lines']} \
bindings={len(bindings)}/{len(c['methods'])} "
        f"remove={rec['remove_imports']} | {head} | {'PASS' if ok else 'FAIL'} {rec['sim_commit']}",
        flush=True,
    )
    if not ok:
        print(gate.stdout[-3000:])
        print(delta.stdout[-3000:])
        sys.exit(1)
print("ALL CLUSTERS DONE")
