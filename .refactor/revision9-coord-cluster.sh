#!/usr/bin/env bash
# Per-cluster driver for the test_revision9_coordination split (lane A, bead forge-plugin-6g67).
# usage: revision9-coord-cluster.sh <label> <shape:mixin|class> <dest> <TargetClass> <methods,csv> "<commit subject>"
#   label   e.g. c00-mixin or c03-gap_repair (unique; names every evidence file)
#   class shape: dest must be tests/test_revision9_coordination_<family>.py; id map built from the fresh snapshot
# Steps: clean-tree check, fresh ID + body snapshots, (id map), dry run, apply, verify.sh (identity|mapping),
# repo file-length guard, production-path check, commit on PASS (evidence, driver log and the decompose
# record ride in the same commit; the record's SHA is filled in by one --amend); on any failure revert the
# two touched test paths (apply failure) or leave them for inspection (gate failure) and exit 1.
set -u
label=$1; shape=$2; dest=$3; cls=$4; methods=$5; subject=$6
export TMPDIR=/dev/shm/refactor-s4 PYTHONPATH=scripts:scripts/forge MYPYPATH=scripts:scripts/forge REFACTOR_MAX_LINES=1000
export REFACTOR_TEST_CMD="python3 -m unittest discover -s tests -p 'test_revision9_coordination*.py'"
export REFACTOR_TYPE_CMD="mypy --no-error-summary --no-color-output --show-error-codes --hide-error-context scripts/forge/forge_cli"
unset FORGE_SESSION_PID
D=/home/agents/foundry-of-zero/refactor-python/skills/decompose/scripts
S=/home/agents/foundry-of-zero/refactor-python/skills/split-module/scripts
SRC=tests/test_revision9_coordination.py
CLASS=Revision9BuilderBatchTests
R=.refactor
REC=$R/decompose-records-revision9-coord.json
log="$R/driver-revision9-coord-$label.txt"
exec 3>&1
exec > >(tee -a "$log") 2>&1
echo "== $label start=$(date -u +%FT%TZ) head=$(git rev-parse --short HEAD) load=$(cut -d' ' -f1-3 /proc/loadavg)"
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then echo "FAIL: tracked tree not clean"; exit 1; fi
if [ -e "$dest" ] && [ "$shape" = class ]; then echo "FAIL: destination exists: $dest"; exit 1; fi
revert() {
  git checkout -- "$SRC"
  if ! git ls-files --error-unmatch "$dest" >/dev/null 2>&1; then rm -f "$dest"; fi
  echo "reverted $SRC and $dest"
}
ids="$R/tests-revision9-coord-$label.json"; bodies="$R/revision9-coord-$label-before.json"
if [ "$shape" = mixin ]; then manifest="$R/mixin-revision9-coord.json"; else manifest="$R/family-revision9-coord-${label#*-}.json"; fi
python3 "$D/collect_tests.py" snapshot --start tests --out "$ids" || { echo "FAIL: id snapshot"; exit 1; }
python3 "$S/snapshot_bodies.py" snapshot tests --out "$bodies" || { echo "FAIL: body snapshot"; exit 1; }
args=(--project . --import-root "$PWD" --source "$SRC" --class "$CLASS" --methods "$methods" --dest "$dest" --shape "$shape" --target-class "$cls" --test-only --test-snapshot "$ids" --format-imports --manifest "$manifest")
mode=identity
idmap=""
if [ "$shape" = class ]; then
  stem=$(basename "$dest" .py); idmap="$R/idmap-revision9-coord-${label#*-}.json"
  python3 "$R/revision9-coord-idmap.py" "$ids" "$stem" "$cls" "$idmap" "$methods" || { echo "FAIL: id map"; exit 1; }
  args+=(--id-map "$idmap"); mode=mapping
fi
python3 "$D/move_methods.py" "${args[@]}" > "$R/dryrun-revision9-coord-$label.txt" 2>&1
rc=$?; tail -1 "$R/dryrun-revision9-coord-$label.txt"
if [ $rc -ne 0 ] || ! grep -q '^DRY RUN: verified' "$R/dryrun-revision9-coord-$label.txt"; then echo "FAIL: dry run rc=$rc"; exit 1; fi
python3 "$D/move_methods.py" "${args[@]}" --apply > "$R/apply-revision9-coord-$label.txt" 2>&1
rc=$?; tail -1 "$R/apply-revision9-coord-$label.txt"
if [ $rc -ne 0 ]; then echo "FAIL: apply rc=$rc"; revert; exit 1; fi
t0=$(date +%s)
bash "$S/verify.sh" --pkg tests --snapshot "$bodies" --manifest "$manifest" --strict-bodies --test-snapshot "$ids" --test-mode "$mode" > "$R/gate-revision9-coord-$label.txt" 2>&1
rc=$?
echo "gate rc=$rc wall=$(( $(date +%s)-t0 ))s load=$(cut -d' ' -f1-3 /proc/loadavg)" >> "$R/gate-revision9-coord-$label.txt"
grep -E '^(PASS|FAIL|SKIP|GATE|BASELINED)|^Ran |^OK$|^FAILED' "$R/gate-revision9-coord-$label.txt"
if [ $rc -ne 0 ]; then echo "FAIL: gate rc=$rc (files left in place for inspection; revert by hand)"; exit 1; fi
if ! git ls-files -z "*.py" | xargs -0 python3 scripts/check_file_length.py "$dest"; then echo "FAIL: repo file-length guard"; exit 1; fi
if [ -n "$(git diff --stat HEAD -- scripts docs/specs .forge)" ]; then echo "FAIL: production paths changed"; exit 1; fi
# Standalone-import check (operator ruling 2026-09-23 11:30, brief section 4 item 1): the destination module must
# import and run in a fresh process WITHOUT PYTHONPATH, as the committed Gate 1 cell does in CI and the merge chain.
stem=$(basename "$dest" .py)
if ! env -u PYTHONPATH -u MYPYPATH python3 -m unittest "tests.$stem" > "$R/standalone-revision9-coord-$label.txt" 2>&1; then
  tail -5 "$R/standalone-revision9-coord-$label.txt"; echo "FAIL: standalone import/run of tests.$stem without PYTHONPATH"; exit 1
fi
grep -E '^Ran |^OK' "$R/standalone-revision9-coord-$label.txt" | tr '\n' ' '; echo "(standalone tests.$stem without PYTHONPATH)"
python3 - "$label" "$bodies" "$manifest" "$ids" "$dest" "$cls" "$shape" <<'EOF'
import json, os, sys
label, bodies, manifest, ids, dest, cls, shape = sys.argv[1:]
p = ".refactor/decompose-records-revision9-coord.json"
recs = json.load(open(p)) if os.path.exists(p) else []
recs.append({"cluster": label, "commit": "(pending)", "snapshot": bodies, "manifest": manifest,
             "test_snapshot": ids, "dest": dest, "target_class": cls, "shape": shape})
json.dump(recs, open(p, "w"), indent=1)
EOF
git add "$SRC" "$dest" "$ids" "$bodies" "$manifest" "$REC" "$log" "$R/dryrun-revision9-coord-$label.txt" "$R/apply-revision9-coord-$label.txt" "$R/gate-revision9-coord-$label.txt" "$R/standalone-revision9-coord-$label.txt"
if [ -n "$idmap" ]; then git add "$idmap"; fi
git commit -q -m "$subject

Mover: move_methods.py --shape $shape --target-class $cls --test-only --format-imports --import-root \$PWD (tier 1).
Gate: verify.sh --pkg tests --strict-bodies --test-mode $mode PASS (see .refactor/gate-revision9-coord-$label.txt);
manifest $manifest; body snapshot $bodies; id snapshot $ids.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_013wij85NCdPt57LTPrfKdJw" || { echo "FAIL: commit"; exit 1; }
sha=$(git rev-parse HEAD)
python3 - "$label" "$sha" <<'EOF'
import json, sys
label, sha = sys.argv[1:]
p = ".refactor/decompose-records-revision9-coord.json"
recs = json.load(open(p))
for r in recs:
    if r["cluster"] == label and r["commit"] == "(pending)":
        r["commit"] = sha
json.dump(recs, open(p, "w"), indent=1)
EOF
echo "== $label record SHA $sha (pre-amend); amending the record and the driver log into it end=$(date -u +%FT%TZ)"
sleep 1  # let tee flush the log before it is staged
git add "$REC" "$log" && git commit -q --amend --no-edit || { echo "FAIL: amend" >&3; exit 1; }
echo "== $label COMMITTED $(git rev-parse HEAD) (the amended commit is the record)" >&3
