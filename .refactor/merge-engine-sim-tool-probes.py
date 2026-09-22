"""Census + structure probes on the final sim tree. Run from the sim root with \
PYTHONPATH=scripts:scripts/forge.
Every probe prints PASS/FAIL with the observed value; exit 1 on any FAIL."""

import ast
import glob
import inspect
import json
import os
import re
import subprocess
import sys
from unittest import mock

import forge_cli.app as app_root
import forge_cli.app._merge_engine as me
from forge_cli.app import MergeEngine

fails = 0


def probe(label, ok, observed=""):
    global fails
    fails += 0 if ok else 1
    print(f"{'PASS' if ok else 'FAIL'}  {label}  [{observed}]")


class _Ctx:  # __init__ only assigns ctx and one None attribute
    pass


eng = MergeEngine(_Ctx())

# 1. patch.object round trip on a plain binding
# (census: _complete_epoch_fetch_locked x3, side_effect form)
orig = MergeEngine.__dict__["_complete_epoch_fetch_locked"]
with mock.patch.object(
    MergeEngine, "_complete_epoch_fetch_locked", side_effect=RuntimeError("boundary")
) as m:
    inside = MergeEngine._complete_epoch_fetch_locked is m
    try:
        eng._complete_epoch_fetch_locked(1, 2)
        raised = False
    except RuntimeError:
        raised = True
probe(
    "patch.object(_complete_epoch_fetch_locked): mock installed, side_effect reached through \
instance, original restored",
    inside and raised and MergeEngine.__dict__["_complete_epoch_fetch_locked"] is orig,
    f"module={orig.__module__} name={orig.__name__}",
)

# 2. staticmethod binding: unbound call site yields the plain function
# (census: _push_classification x3)
raw = MergeEngine.__dict__["_push_classification"]
fn = MergeEngine._push_classification
probe(
    "staticmethod binding _push_classification: class dict holds staticmethod, class access \
yields plain function, instance access too",
    isinstance(raw, staticmethod) and inspect.isfunction(fn) and eng._push_classification is fn,
    f"type={type(raw).__name__} module={fn.__module__} \
params={list(inspect.signature(fn).parameters)}",
)

# 3. autospec patch + unbound read (census: _run_carried_successor_ancestry)
original_ancestry = MergeEngine._run_carried_successor_ancestry
seen = {}


def side(self, *args, **kwargs):
    seen["self_is_engine"] = self is eng
    seen["args"] = args
    return "sentinel"


with mock.patch.object(
    MergeEngine, "_run_carried_successor_ancestry", autospec=True, side_effect=side
):
    sig = inspect.signature(original_ancestry)
    n_required = [
        p
        for p in list(sig.parameters.values())[1:]
        if p.default is p.empty and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
    ]
    kw_required = {
        p.name: None
        for p in sig.parameters.values()
        if p.default is p.empty and p.kind is p.KEYWORD_ONLY
    }
    out = eng._run_carried_successor_ancestry(*range(len(n_required)), **kw_required)
probe(
    "autospec patch of _run_carried_successor_ancestry: signature introspectable, self passed, \
restored",
    out == "sentinel"
    and seen.get("self_is_engine") is True
    and MergeEngine._run_carried_successor_ancestry is original_ancestry,
    f"sig={sig} first_param_annotation={list(sig.parameters.values())[0].annotation!r}",
)

# 4. contextmanager binding (lock cluster)
lock = MergeEngine.__dict__["_recording_common_lock"]
wrapped = getattr(lock, "__wrapped__", None)
probe(
    "contextmanager binding _recording_common_lock: function with __wrapped__ generator \
function in _engine_lock, name preserved",
    inspect.isfunction(lock)
    and wrapped is not None
    and inspect.isgeneratorfunction(wrapped)
    and wrapped.__module__ == "forge_cli.app._engine_lock"
    and lock.__name__ == "_recording_common_lock",
    f"module={getattr(wrapped, '__module__', None)} name={lock.__name__} \
qualname={lock.__qualname__} "
    f"return_annotation={inspect.signature(lock).return_annotation!r}",
)

# 5. _head_contained tripwire patch (census) round trip on a staticmethod binding
raw_hc = MergeEngine.__dict__["_head_contained"]
with mock.patch.object(MergeEngine, "_head_contained", side_effect=AssertionError("tripwire")):
    try:
        MergeEngine._head_contained(None, "a", "b")
        tripped = False
    except AssertionError:
        tripped = True
probe(
    "patch.object(_head_contained) tripwire: fires while patched; staticmethod object \
restored afterwards",
    tripped
    and MergeEngine.__dict__["_head_contained"] is raw_hc
    and isinstance(raw_hc, staticmethod),
    type(raw_hc).__name__,
)

# 6. classmethod binding
cm = MergeEngine.__dict__["_recover_can_reach_final_mode"]
probe(
    "classmethod binding _recover_can_reach_final_mode: classmethod in class dict, bound to \
the class",
    isinstance(cm, classmethod)
    and MergeEngine._recover_can_reach_final_mode.__self__ is MergeEngine,
    f"module={MergeEngine._recover_can_reach_final_mode.__func__.__module__}",
)

# 7. store stays a real property on the class; __init__ real
probe(
    "store is a property defined in _merge_engine; __init__ defined in _merge_engine",
    isinstance(MergeEngine.__dict__["store"], property)
    and MergeEngine.__dict__["store"].fget.__module__ == me.__name__
    and MergeEngine.__init__.__module__ == me.__name__,
    "",
)

# 8. class surface: every inventory method name still an attribute of the class
inv = json.load(
    open("/home/agents/foundry-of-zero/forge-plugin/.refactor/merge-engine-inventory.json")
)
missing = [x["name"] for x in inv["methods"] if x["name"] not in MergeEngine.__dict__]
probe("all 93 method names still in MergeEngine.__dict__", not missing, f"missing={missing}")

# 9. defs remaining in the class body vs bindings
tree = ast.parse(open("scripts/forge/forge_cli/app/_merge_engine.py").read())
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "MergeEngine")
defs = [n.name for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
assigns = [n.targets[0].id for n in cls.body if isinstance(n, ast.Assign)]
probe(
    "class body: 7 defs + 86 bindings",
    len(defs) == 7 and len(assigns) == 86,
    f"defs={defs} bindings={len(assigns)}",
)

# 10. no _engine_* module imports _merge_engine at runtime or any other _engine_* module
bad = []
for path in sorted(glob.glob("scripts/forge/forge_cli/app/_engine_*.py")):
    t = ast.parse(open(path).read())
    for (
        node
    ) in t.body:  # top level only: the TYPE_CHECKING block is an ast.If and is skipped on purpose
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            text = ast.unparse(node)
            # tier 2 (second wave): a seam module may import its declared _steps sibling
            if "_merge_engine" in text or re.search(r"_engine_\w+(?<!_steps)\b", text):
                bad.append((os.path.basename(path), text))
    for node in ast.walk(t):
        if isinstance(node, (ast.Import, ast.ImportFrom)) and node not in t.body:
            text = ast.unparse(node)
            if text != "from forge_cli.app._merge_engine import MergeEngine":
                bad.append((os.path.basename(path), "nested: " + text))
probe(
    "no _engine_* module imports _merge_engine at runtime or another _engine_* except its \
declared _steps sibling (only the TYPE_CHECKING class import is nested)",
    not bad,
    bad[:5],
)

# 11. __all__ of the facade unchanged vs d885f97
old = subprocess.run(
    ["git", "show", "d885f97:scripts/forge/forge_cli/app/__init__.py"],
    capture_output=True,
    text=True,
).stdout
probe(
    "app/__init__.py byte-identical to d885f97 (so __all__ verbatim)",
    old == open("scripts/forge/forge_cli/app/__init__.py").read(),
    f"'MergeEngine' in __all__={'MergeEngine' in app_root.__all__}; _engine names in \
__all__={[n for n in app_root.__all__ if n.startswith('_engine_')]}",
)

# 12. fresh-interpreter import of each _engine_* module alone (no runtime cycle)
cyc = []
for path in sorted(glob.glob("scripts/forge/forge_cli/app/_engine_*.py")):
    mod = "forge_cli.app." + os.path.basename(path)[:-3]
    r = subprocess.run(
        [sys.executable, "-c", f"import {mod}"], capture_output=True, text=True, env=os.environ
    )
    if r.returncode:
        cyc.append((mod, r.stderr.strip().splitlines()[-1]))
probe("each _engine_* module imports first in a fresh interpreter", not cyc, cyc[:3])

print(f"\nprobes failed: {fails}")
sys.exit(1 if fails else 0)
