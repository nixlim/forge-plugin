# Lane A (session 4, bead forge-plugin-6g67): base record

- BASE: 69bc28d39bdcd317ea70b65af57b800598794b80 (main = origin/main at launch, 2026-09-23)
- Branch: refactor/split-test-revision9-coordination, worktree forge-plugin-wt/s4
- Brief: docs/analysis/refactor-overnight-brief-2026-09-23.md (lane A)
- Plugin: refactor-python 0.1.3 (d265b57, branch plugin-0.1.3)
- Target: tests/test_revision9_coordination.py, 13,222 code lines (baseline entry line 59)
- Forge: off for the night by the MAIN clone's .claude/settings.local.json ("forge@forge": false; brief section 1, corrected 01:25 - the worktree file's enabledPlugins line is inert); no forge:* skill listed; FORGE_SESSION_PID unset. Relaunched 01:27 after the first run stopped at its first commit with the plugin still loaded.
- Env: PYTHONPATH=MYPYPATH=scripts:scripts/forge, REFACTOR_MAX_LINES=1000, REFACTOR_TYPE_CMD -> scripts/forge/forge_cli,
  REFACTOR_TEST_CMD = python3 -m unittest discover -s tests -p 'test_revision9_coordination*.py'
- Env note: the settings file's TMPDIR=/dev/shm/refactor-s4 was not propagated into the session shell by the harness
  (only GOTMPDIR present); every gate command in this session exports TMPDIR=/dev/shm/refactor-s4 explicitly.
- Preflight --decompose: PREFLIGHT OK (missing: none; optional radon/vulture absent)
- Baseline focused set on the untouched branch: 144 tests, OK, 17 s wall (16.3 s reported), load 6.0
- ID freeze: .refactor/tests-revision9-coord-before.json (unittest 1908, pytest 1908, auto preset -> namespace tests/, 5 s)
- Body freeze: .refactor/before-revision9-coord.json (2,906 bodies across 2,884 names, 4 s)
- Gate dry run (--pkg tests --strict-bodies --fast): see .refactor/gate-revision9-coord-dryrun.txt
- Relaunch re-checks (01:27 run): focused set 144 OK in 18 s (load 19..26); gate dry run --fast PASS on every step in 5 s
  (.refactor/gate-revision9-coord-dryrun.txt); ID and body snapshots from the 01:17 run reused unchanged (tip still 69bc28d).
