export const meta = {
  name: 'split-chain-core',
  description: 'Split forge_cli.chain_core into a package from an approved plan: package conversion, per-wave rope extraction in worktrees, gated merges with FR-230 re-mint, Codex + Fable review, finalize.',
  phases: [
    { title: 'Package', detail: 'git mv to chain_core/__init__.py, re-mint, gate, commit' },
    { title: 'Extract', detail: 'one extractor per cluster in its own worktree' },
    { title: 'Merge', detail: 'merge leaves-first, focused gate, wave-end re-exports + re-mint + full gate-1' },
    { title: 'Codex review', detail: 'headless GPT-5.6 Sol review of the whole split' },
    { title: 'Review', detail: 'Fable adjudicates diff and Codex findings; consensus round' },
    { title: 'Finalize', detail: 'spec sentence, baseline, import contract, strict oracle, full gate-1, report' },
  ],
}

// args: { plan: {planPath, pkgDir, preWave, sourceModule, waves}, branch, baselineCommit, scripts,
//         focusedTests: string[] , mintCmd: string, overBudgetAllowed: string[] }
const plan = args && args.plan
if (!plan || !plan.waves || !plan.waves.length) throw new Error('args.plan with waves is required')
const BRANCH = args.branch
const BASE = args.baselineCommit
const S = args.scripts
const PKG = plan.pkgDir
const SRC = plan.sourceModule
const SNAP = '.refactor/before.json'
const PLAN_MD = plan.planPath
const MINT = args.mintCmd
const FOCUSED = 'python3 -m unittest ' + (args.focusedTests || []).join(' ')

// Environment every gate run needs in this repository (verify.sh reads REFACTOR_* ; tests need the
// forge-gate TMPDIR and no session pid; import-linter needs the two source roots on PYTHONPATH; the
// type step is mypy through type_baseline.py, ratcheted against .refactor/type-baseline.json).
const GATE_ENV =
  `export PYTHONPATH=scripts:scripts/forge; export TMPDIR=/tmp/forge-gate; mkdir -p /tmp/forge-gate; unset FORGE_SESSION_PID; ` +
  `export MYPYPATH=scripts:scripts/forge; unset REFACTOR_TYPE_CMD; export REFACTOR_TEST_CMD='${FOCUSED}'; export PATH="$HOME/.local/bin:$PATH"`
// Every gate is strict on bodies: a CHANGED body is a stop, never a note (the oracle is the split's contract).
const GATE = `${GATE_ENV}; bash ${S}/verify.sh --pkg ${PKG} --snapshot ${SNAP} --strict-bodies`
// Merge-time and wave-end gates are strict on bodies: a CHANGED body is a stop, never a note.
const GATE_STRICT = `${GATE_ENV}; bash ${S}/verify.sh --pkg ${PKG} --snapshot ${SNAP} --strict-bodies`
const GATE_FAST = `${GATE_ENV}; bash ${S}/verify.sh --pkg ${PKG} --snapshot ${SNAP} --strict-bodies --fast`
// The repository's own full test gate: the committed gate-1 cell from forge-project.md, run the way CI runs it.
const GATE1 =
  `${GATE_ENV}; python3 - <<'PY'\n` +
  `import subprocess, sys\nfrom pathlib import Path\nsys.path.insert(0, "scripts/forge")\n` +
  `from forge_cli.policy import parse_policy\nfrom forge_cli.runtime import run_bounded\n` +
  `head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()\n` +
  `raw = subprocess.run(["git", "show", f"{head}:forge-project.md"], capture_output=True, check=True).stdout\n` +
  `cell = parse_policy(head, raw).gate1\n` +
  `result = run_bounded(["bash", "-c", cell, "forge"], cwd=Path.cwd(), timeout=1800)\n` +
  `sys.stdout.buffer.write(result.output[-6000:]); print()\n` +
  `raise SystemExit(2 if result.timed_out or result.output_limit else result.returncode)\nPY`
// FR-230: the manifest lists production subjects by path; after a move the package's files must be the
// subjects, then the minter rewrites digests. Extractors never do this; wave-end and finalize agents do.
const REMINT =
  `python3 - <<'PY'\n` +
  `import json, subprocess\np = ".forge/evals/tasks/fr230-phase3-4-v2.manifest.json"\nm = json.load(open(p))\n` +
  `prod = [x for x in m["subjects"]["production"] if not x.startswith("${PKG}/chain_core")]\n` +
  `files = subprocess.run(["git", "ls-files", "${PKG}/chain_core"], capture_output=True, text=True, check=True).stdout.split()\n` +
  `m["subjects"]["production"] = sorted(set(prod + [f for f in files if f.endswith(".py")]))\n` +
  `json.dump(m, open(p, "w"), ensure_ascii=False, indent=2); open(p, "a").write("\\n")  # member order is validated: never sort_keys\nPY\n` +
  `${GATE_ENV}; ${MINT} && python3 -m unittest tests.test_fr230_phase3_manifest tests.test_fr223_v2_byte_pins tests.test_docs_contract`

const RULES =
  `Rules: move only with python3 ${S}/rope_move.py --project . (the repository's .refactor/rope-ignore already hides ` +
  `importers outside the package from rope; do not pass --ignore); never edit a function or class body; never add ` +
  `abstractions; never Read the source module whole; never touch tests/, engine.py, app.py, cli.py, .refactor-baseline.json ` +
  `or the FR-230 manifest; one cluster per commit. rope_move.py --apply already restores bare names in the source ` +
  `(it prints 'source: restored N bare reference(s)') and repairs the destination's 'from forge_cli.chain_core import' ` +
  `line; do NOT hand-edit bodies or references afterwards. After 'ruff check --fix --select I,F401 <src> <dst>', if the ` +
  `destination still imports a name from the package root 'forge_cli.chain_core' (not from a submodule), that name is ` +
  `still defined in __init__.py: report it in notes and keep going only if the gate passes. Before verify.sh run exactly: ` +
  `${GATE_ENV}. Gate (strict on bodies; any CHANGED body is a FAIL you must not work around): ${GATE}. Plan: ${PLAN_MD}.`

const GATE_SCHEMA = { type: 'object', required: ['gate'], properties: { gate: { type: 'string', enum: ['PASS', 'FAIL'] }, cause: { type: 'string' }, commit: { type: 'string' } } }
const EXTRACT = { type: 'object', required: ['cluster', 'branch', 'gate'], properties: { cluster: { type: 'string' }, branch: { type: 'string' }, commit: { type: ['string', 'null'] }, gate: { type: 'string', enum: ['pass', 'fail'] }, moved: { type: 'array', items: { type: 'string' } }, notes: { type: 'string' } } }
const VERDICT = { type: 'object', required: ['verdict'], properties: { verdict: { type: 'string', enum: ['APPROVE', 'REVISE', 'BLOCK', 'REJECT'] }, blocking: { type: 'array', items: { type: 'string' } }, disputed: { type: 'array', items: { type: 'string' } }, allowedChanged: { type: 'array', items: { type: 'string' } }, summary: { type: 'string' } } }

const brief = (c) =>
  `Cluster: ${c.cluster}\nSource module: ${SRC}\nDestination module: ${c.dest}\nSymbols to move, in this order: ${c.symbols.join(', ')}\n` +
  `Snapshot: ${SNAP}\nPackage dir for the gate: ${PKG}\nScripts: ${S}\n${RULES}\nReturn the JSON report described in your instructions.`

const extract = (c, label, extra) => agent(brief(c), { label, phase: 'Extract', agentType: 'refactor-python:extractor', isolation: 'worktree', schema: EXTRACT, ...(extra || {}) })

// args.mergeGen: bump to re-run merge agents on resume (their cached FAIL results would otherwise replay).
const MERGE_GEN = args.mergeGen ? ` [merge generation ${args.mergeGen}]` : ''
const mergeOne = (r, c) => agent(
  `On branch ${BRANCH} in the repository root.${MERGE_GEN} The extractor for cluster "${c.cluster}" committed ${r.commit} on its worktree branch ${r.branch}; merge BY COMMIT, never by the branch name. Steps:\n` +
  `1. Require 'git rev-parse --abbrev-ref HEAD' to print ${BRANCH} and 'git status --porcelain --untracked-files=no' to be empty; otherwise return {gate:"FAIL", cause:"dirty or wrong branch"}.\n` +
  `2. If 'git merge-base --is-ancestor ${r.commit} HEAD' succeeds the commit is already merged: skip to step 4.\n` +
  `3. before=$(git rev-parse HEAD); run 'git merge --no-ff ${r.commit} -m "Merge ${c.cluster} (${r.commit}) into ${BRANCH}"'. If git reports conflicts run 'git merge --abort' and return {gate:"FAIL", cause:"conflict"}. Then require 'git rev-parse HEAD' to differ from before AND 'git merge-base --is-ancestor ${r.commit} HEAD' to succeed; otherwise return {gate:"FAIL", cause:"nothing merged"}.\n` +
  `4. Run exactly: ${GATE_STRICT}\nReturn {gate, cause, commit:<git rev-parse HEAD>} from its "== gate results ==" block (FAIL if any line is FAIL). Do not fix anything.`,
  { label: `merge:${c.cluster}`, phase: 'Merge', agentType: 'refactor-python:gate-runner', schema: GATE_SCHEMA },
)

// ----------------------------------------------------------------- Package
phase('Package')
const pkg = args.packageDone ? { gate: 'PASS', commit: String(args.packageDone) } : await agent(
  `On branch ${BRANCH} at the repository root; 'git status --porcelain --untracked-files=no' must be empty (stop and return FAIL if not; untracked files such as docs/notes/ are fine and must not be added). Convert the module to a package with no code moved:\n` +
  `1. ${plan.preWave.step}\n` +
  `2. Update the FR-230 subjects and re-mint, then confirm: ${REMINT}\n` +
  `3. Gate: ${GATE}\n` +
  `4. If every check passed: git add -A -- ${PKG}/chain_core .forge/evals/tasks tests/fixtures/fr230-results tests/test_fr223_v2_byte_pins.py && git commit -m "${plan.preWave.commit}" (also stage the removed ${PKG}/chain_core.py path). ` +
  `Return {gate, cause, commit}. Do not edit any file by hand except through the commands above.`,
  { label: 'package', phase: 'Package', schema: GATE_SCHEMA },
)
if (!pkg || pkg.gate !== 'PASS') throw new Error('package conversion failed: ' + JSON.stringify(pkg))
log(`package conversion committed ${pkg.commit || ''}`)

// ---------------------------------------------------- Extract + Merge waves
const waveReports = []
const DONE_WAVES = new Set(args.doneWaves || [])   // waves already extracted, merged and closed on the branch (resume after a stop)
for (let w = 0; w < plan.waves.length; w++) {
  const wave = plan.waves[w]
  if (DONE_WAVES.has(w)) { waveReports.push({ wave: w, merged: wave.map((c) => c.cluster), failed: [], end: { gate: 'PASS', commit: 'done-before-resume' } }); log(`wave ${w}: already closed on the branch, skipping`); continue }
  // args.sequential: every cluster rewrites chain_core/__init__.py, so parallel extraction only ever lands its first
  // merge and re-extracts the rest; sequential extraction from the merged HEAD never conflicts.
  const sequential = !!args.sequential || w === 0 || wave.length === 1
  const merged = []
  const failedClusters = []

  const runCluster = async (c, results) => {
    let r = await extract(c, `extract:w${w}:${c.cluster}`)
    if (!r || r.gate !== 'pass') {
      log(`wave ${w} cluster ${c.cluster}: first extractor failed (${r && r.notes}); retrying on Opus 5`)
      r = await extract(c, `extract2:w${w}:${c.cluster}`, { model: 'claude-opus-5' })
    }
    results.push(r && r.gate === 'pass' ? r : { cluster: c.cluster, gate: 'fail', branch: '', notes: (r && r.notes) || 'no report' })
  }

  phase('Extract')
  const results = []
  const DONE = new Set(args.doneClusters || [])   // clusters already extracted and merged on the branch (resume after a stop)
  for (const c of wave) if (DONE.has(c.cluster)) { merged.push(c.cluster); log(`wave ${w}: ${c.cluster} already merged, skipping`) }
  const pending = wave.filter((c) => !DONE.has(c.cluster))
  if (sequential) {
    // wave 0 (state -> controls -> core hubs) and single-cluster waves: extract, merge, then the next cluster starts from merged HEAD
    for (const c of pending) {
      await runCluster(c, results)
      const r = results[results.length - 1]
      if (r.gate !== 'pass' || !r.commit) { failedClusters.push(c.cluster); break }
      phase('Merge')
      const m = await mergeOne(r, c)
      if (!m || m.gate !== 'PASS') { failedClusters.push(c.cluster); log(`wave ${w}: merge of ${c.cluster} failed: ${m && m.cause}`); break }
      merged.push(c.cluster)
      phase('Extract')
    }
  } else {
    await parallel(pending.map((c) => () => runCluster(c, results)))
    phase('Merge')
    for (const c of pending) {
      let r = results.find((x) => x.cluster === c.cluster)
      if (!r || r.gate !== 'pass' || !r.commit) { failedClusters.push(c.cluster); log(`wave ${w}: ${c.cluster} has no passing report with a commit`); continue }
      let ok = false
      for (let attempt = 0; attempt < 2 && !ok; attempt++) {
        const m = await mergeOne(r, c)
        if (m && m.gate === 'PASS') { ok = true; break }
        if (m && /conflict/i.test(String(m.cause || '')) && attempt === 0) {   // agents sometimes describe the conflict instead of returning the literal
          r = await extract(c, `reextract:w${w}:${c.cluster}`)
          if (!r || r.gate !== 'pass') break
          continue
        }
        log(`wave ${w}: merge of ${c.cluster} failed: ${m && m.cause}`)
        break
      }
      if (ok) merged.push(c.cluster); else failedClusters.push(c.cluster)
    }
  }
  if (failedClusters.length) {
    log(`wave ${w}: stopping; failed clusters: ${failedClusters.join(', ')}; merged so far: ${merged.join(', ')}`)
    waveReports.push({ wave: w, merged, failed: failedClusters })
    break
  }

  phase('Merge')
  // Wave close is two agents on purpose: the 7-minute gate-1 exhausted a single agent's turn budget in wave 0.
  const COMMIT_PATHS = `${PKG}/chain_core .forge/evals/tasks tests/fixtures/fr230-results tests/test_fr223_v2_byte_pins.py`
  const commitMsg = `refactor(chain_core): re-exports and re-mint after wave ${w} (${wave.map((c) => c.dest.replace(/^.*\//, '')).join(', ')})`
  const prep = await agent(
    `On branch ${BRANCH} at the repository root, prepare the close of wave ${w} of ${PLAN_MD} (clusters: ${wave.map((c) => c.cluster).join(', ')}). Do NOT commit.\n` +
    `1. In ${SRC} add a backwards-compatible re-export for every symbol moved in this wave, using the explicit form 'from .<target> import A as A' ` +
    `(one line per symbol or grouped per target), so that every name in __all__ and every attribute read by engine.py, app.py, cli.py and tests still resolves; keep __all__ verbatim; do not add anything else.\n` +
    `2. Fast gate (no tests): ${GATE_FAST}\n` +
    `3. FR-230 subjects and re-mint, then confirm: ${REMINT}\n` +
    `Return {gate, cause}: PASS only if steps 2 and 3 both passed. Leave the working tree as it is for the next agent.`,
    { label: `wave-end-prep:w${w}`, phase: 'Merge', schema: GATE_SCHEMA },
  )
  const end = (!prep || prep.gate !== 'PASS') ? prep : await agent(
    `On branch ${BRANCH} at the repository root (working tree already prepared; do not edit anything). Run the full gate-1 as ONE foreground Bash call with timeout 600000 (it takes about 7 minutes; never background it, never poll):\n${GATE1}\n` +
    `If its exit status is 0: git add -A -- ${COMMIT_PATHS} && git commit -m "${commitMsg}" and return {gate:"PASS", commit:<sha>}. ` +
    `Otherwise return {gate:"FAIL", cause:<the failing test names from the output>} without committing; a pre-existing failure unrelated to the split is still a FAIL.`,
    { label: `wave-end-gate1:w${w}`, phase: 'Merge', agentType: 'refactor-python:gate-runner', schema: GATE_SCHEMA },
  )
  waveReports.push({ wave: w, merged, failed: [], end })
  if (!end || end.gate !== 'PASS') { log(`wave ${w}: wave-end gate failed: ${end && end.cause}`); break }
  log(`wave ${w} closed: ${merged.length} cluster(s) merged, commit ${end.commit || ''}`)
}
const completed = waveReports.filter((r) => !r.failed.length && r.end && r.end.gate === 'PASS').length
if (completed < plan.waves.length) {
  return { branch: BRANCH, status: 'stopped', wavesCompleted: completed, wavesPlanned: plan.waves.length, waveReports }
}

// ------------------------------------------------------------ Codex review
phase('Codex review')
// args.codexDone: {ok, path, verdict, thread} from a review already run by the orchestrator (the headless review
// outlives a subagent's turn budget); when present the review agent is skipped.
const codex = args.codexDone ? args.codexDone : await agent(
  `On branch ${BRANCH}, run: ${GATE_ENV}; bash ${S}/codex_review.sh --base ${BASE} --plan ${PLAN_MD} --out .refactor/codex-review-chain_core.md\n` +
  `Do not read the .jsonl log. Return JSON {ok:boolean, path:string, verdict:string, thread:string} from the output file (the thread id is on its last lines; verdict "unavailable" and ok:false if codex failed).`,
  { label: 'codex-review', phase: 'Codex review', schema: { type: 'object', required: ['ok', 'path', 'verdict'], properties: { ok: { type: 'boolean' }, path: { type: 'string' }, verdict: { type: 'string' }, thread: { type: 'string' } } } },
)

// ------------------------------------------------------------------ Review
phase('Review')
const review = await agent(
  `Review the split of forge_cli.chain_core on branch ${BRANCH}: baseline commit ${BASE}, HEAD, plan ${PLAN_MD}, critique .refactor/critique-chain_core.md, snapshot ${SNAP}, scripts ${S}, ` +
  `codex review at ${(codex && codex.path) || 'unavailable'}. Gate environment for any command you run: ${GATE_ENV}. Do your own check first (oracle compare, targeted reads, ` +
  `grep for new direct patch.object sites on chain_core aliases in tests/, import-time side effects, byte-identical reason literals), then adjudicate every Codex BLOCKING finding as CONFIRMED/REFUTED/UNVERIFIABLE with evidence. ` +
  `Return JSON {verdict, blocking[], disputed[], allowedChanged[], summary}; allowedChanged must be [] unless you explicitly approve a body change.`,
  { label: 'fable-review', phase: 'Review', agentType: 'refactor-python:refactor-reviewer', schema: VERDICT },
)
const consensus = []
for (const finding of (review && review.disputed) || []) {
  if (!codex || !codex.ok || !codex.thread) { consensus.push({ finding, outcome: 'codex unavailable; escalate to user' }); continue }
  const reply = await agent(
    `Run: ${GATE_ENV}; bash ${S}/codex_review.sh --followup ${codex.thread} ${JSON.stringify(finding)}\nReturn JSON {outcome:"AGREE"|"DISAGREE"|"RETRACT", evidence:string} from Codex's answer.`,
    { label: 'consensus', phase: 'Review', schema: { type: 'object', required: ['outcome'], properties: { outcome: { type: 'string' }, evidence: { type: 'string' } } } },
  )
  consensus.push({ finding, outcome: (reply && reply.outcome) || 'no answer', evidence: reply && reply.evidence })
}

// ---------------------------------------------------------------- Finalize
phase('Finalize')
const fin = await agent(
  `On branch ${BRANCH} at the repository root, finalize the split (operator-approved items only):\n` +
  `1. docs/specs/forge-plugin-spec.md: rewrite the one sentence in the section-5 bullet that describes the forge_cli package's files so it names the chain_core package (${PKG}/chain_core/, root __init__.py holding __all__ and re-exports, submodules per ${PLAN_MD}) instead of chain_core.py; change nothing else. Then run ${GATE_ENV}; python3 -m unittest tests.test_docs_contract tests.test_repo_conformance and update the docs-contract pin only if that test names the sentence.\n` +
  `2. .refactor-baseline.json: run ${GATE_ENV}; git ls-files -z '*.py' | xargs -0 python3 scripts/check_file_length.py --write-baseline .refactor-baseline.json --max 500, then verify the ONLY new entries are files under ${PKG}/chain_core/ and every other entry is unchanged or removed (the old chain_core.py entry disappears); report the new entries with their sizes.\n` +
  `3. pyproject.toml [tool.importlinter]: add one 'layers' contract for forge_cli.chain_core in wave order from ${PLAN_MD} (top: the last-wave modules; bottom: _state), no ignore_imports; run ${GATE_ENV}; lint-imports.\n` +
  `4. Strict oracle: ${GATE_ENV}; python3 ${S}/snapshot_bodies.py compare ${SNAP} ${PKG} --strict${(review && review.allowedChanged && review.allowedChanged.length) ? ' --allow-changed ' + review.allowedChanged.join(',') : ''}\n` +
  `5. ${GATE_ENV}; ruff check scripts tests system/fr223 && git ls-files -z '*.py' | xargs -0 python3 scripts/check_file_length.py --baseline .refactor-baseline.json\n` +
  `6. FR-230 subjects and re-mint, then confirm: ${REMINT}\n` +
  `7. Full gate-1: ${GATE1}\n` +
  `8. If all passed: git add docs/specs/forge-plugin-spec.md .refactor-baseline.json pyproject.toml .forge/evals/tasks tests/fixtures/fr230-results tests/test_fr223_v2_byte_pins.py tests/test_docs_contract.py && git commit -m "refactor(chain_core): finalize split (spec sentence, baseline, import contract)"\n` +
  `Return a Markdown report: table of ${PKG}/chain_core/*.py with code-line counts (python3 scripts/check_file_length.py --max 0 on each), symbols moved, gate status of steps 4-7, Codex verdict ${JSON.stringify(codex && codex.verdict)}, Fable verdict ${JSON.stringify(review && review.verdict)}, consensus ${JSON.stringify(consensus)}, the tip SHA, and the exact commands to reproduce the gate.`,
  { label: 'finalize', phase: 'Finalize' },
)

return { branch: BRANCH, status: 'done', wavesCompleted: completed, codex, review, consensus, report: fin }
