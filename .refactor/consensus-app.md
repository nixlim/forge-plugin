# Consensus round: forge_cli.app split
Codex follow-ups (thread 01a0b571-c486-74a3-889a-7296be03ac6c, gpt-5.6-sol) on each finding the Fable reviewer disputed; run by workflow wf_e219f9ff-718 on 2026-09-18.

## Finding 1



**Codex outcome: RETRACT**

Codex follow-up on B1 concluded RETRACT: "the binding observation is correct, but treating it as a blocking ordinary-caller behavior/API regression was unsupported. Root mutation propagation is documented as intentionally unsupported package behavior, no production caller relies on it, and the callable import/call surface remains unchanged." Supporting points from Codex: (1) at efc7b20, scripts/forge/forge_cli/app/__init__.py:37 re-exports dispatch and _dispatch.py:296 calls the owner-module binding, with snapshot behavior documented at __init__.py lines 13-14; (2) baseline b764d5a already documents identical behavior at engine/__init__.py:15-17 (verified via git show); (3) runtime probe confirmed the mechanism (app.dispatch is _dispatch.dispatch True initially, False after root rebind, patch_app restores both) but not a production regression; (4) git grep over scripts hooks skills system agents rules for app attribute assignment and setattr returned empty; (5) the only production consumer is scripts/forge/cli.py:131 calling app.main() without rebinding, same site as at baseline; (6) .refactor/plan-app.md:128 scopes the issue to test patch targets, routed through tests/_cli_loader.py:170 patch_app.

## Finding 2



**Codex outcome: RETRACT**

Codex (thread 01a0b571-c486-74a3-889a-7296be03ac6c, output in /home/agents/foundry-of-zero/forge-plugin/.refactor/codex-review.md) stated RETRACT for finding B2. Its evidence: .refactor/plan-app.md:112,122-124,133 requires exactly 17 defined-symbol re-exports and says "no unused header import re-bound"; scripts/forge/forge_cli/app/__init__.py:18 implements all 17 (runtime probe printed `missing_required []`) and lines 45-53 preserve the seven-name __all__; docs/specs/forge-plugin-spec.md:117 defines package roots as re-exporting symbols the historical module *defined*, excluding unused imports (chain_core) and retaining engine imports only when consumed; baseline b764d5a applies the same convention in engine/__init__.py:12-36 (Policy absent there too); scripts/forge/cli.py:86-93 forwards only each package's __all__; a repo-wide search of scripts tests hooks skills system agents rules for the 35 names via APP / CLI.app / forge_cli.app found no executable reads — the sole textual match tests/test_cli_loader.py:306 is `APP.os` inside a synthetic string, and its AST census printed `[]`. Codex confirmed the namespace contraction is real (`from forge_cli.app import Policy` raises ImportError) but concluded classifying it as a blocking public-API break was unsupported: the contract is the 17 symbols app.py defined, all of which remain importable.

## Finding 3



**Codex outcome: RETRACT**

Codex retracted A1. Its evidence: (1) the syntactic difference is real — baseline app.py named chain_core at line 13 and runtime at line 20, current scripts/forge/forge_cli/app/_mutation_journal.py:4 names runtime first; (2) scripts/forge/cli.py:73-76 imports runtime, chain_core, engine, then app, and `git diff --quiet b764d5a..HEAD -- scripts/forge/cli.py` returned 0, so the entry order is unchanged across the refactor; (3) an import trace through cli.py printed ['forge_cli.runtime', 'forge_cli.chain_core', 'forge_cli.engine', 'forge_cli.app']; (4) `git grep -n -E 'from forge_cli import app|import forge_cli\.app' HEAD -- scripts hooks skills system agents rules` found only cli.py:76, and scripts/forge/forge_cli/__init__.py:3 states cli.py is the sole invoked entry point; (5) even under the baseline's isolated direct-import path, scripts/forge/forge_cli/chain_core/__init__.py:12 first imports _state, which imports runtime at chain_core/_state.py:3 before its first state assignment at line 15, so runtime's cache and lock were initialized before meaningful chain-core state in both versions. Codex's verdict verbatim: "RETRACT — only an isolated module-start trace changed. Every production path initializes runtime first, substantive chain-core state already depended on runtime first at the baseline, and no observer or initialization-dependent behavior was found."
