"""Wave close: add the nine engine/_verbs_*.py modules to the FR-230 production subjects."""
import json
import sys

path = sys.argv[1]
raw = open(path, encoding='utf-8').read()
m = json.loads(raw)
prod = m['subjects']['production']
STEMS = ('decision', 'finalize', 'gate', 'gate_evals', 'lifecycle', 'review_collect',
         'review_request', 'status', 'tombstone')
new = [f'scripts/forge/forge_cli/engine/_verbs_{x}.py' for x in STEMS]
engine = [p for p in prod if p.startswith('scripts/forge/forge_cli/engine/')]
assert engine == sorted(engine), 'engine block is not sorted; inspect before editing'
merged = sorted(set(engine) | set(new))
first = prod.index(engine[0])
prod[first:first + len(engine)] = merged
assert len(prod) == len(set(prod)), 'duplicate subject'
text = json.dumps(m, ensure_ascii=False, indent=2) + '\n'
if len(sys.argv) > 2 and sys.argv[2] == '--write':
    open(path, 'w', encoding='utf-8').write(text)
    print('written', path)
else:
    # show that the only change is the nine insertions
    import difflib
    for line in difflib.unified_diff(raw.splitlines(), text.splitlines(), lineterm='', n=0):
        print(line)
