#!/usr/bin/env python3
"""Count an orchestrator Claude Code session's tokens from its transcript (GOAL.md §0.8): input, cache reads,
cache writes and output, summed over assistant messages (each message id once, its last usage record).
Usage: count_tokens.py <transcript.jsonl> <label>   appends a row to evidence/orchestrator/tokens.csv"""
import csv, json, os, sys, datetime
path, label = sys.argv[1], sys.argv[2]
msgs = {}
models = set()
for line in open(path):
    try:
        e = json.loads(line)
    except ValueError:
        continue
    m = e.get('message') if isinstance(e.get('message'), dict) else None
    if e.get('type') == 'assistant' and m and m.get('usage'):
        msgs[m.get('id') or len(msgs)] = m['usage']
        models.add(m.get('model'))
t = {'input': 0, 'cache_read': 0, 'cache_write': 0, 'output': 0}
for u in msgs.values():
    t['input'] += u.get('input_tokens') or 0
    t['cache_read'] += u.get('cache_read_input_tokens') or 0
    t['cache_write'] += u.get('cache_creation_input_tokens') or 0
    t['output'] += u.get('output_tokens') or 0
total = sum(t.values())
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tokens.csv')
new = not os.path.exists(out)
with open(out, 'a', newline='') as f:
    w = csv.writer(f)
    if new:
        w.writerow(['recorded', 'label', 'session', 'models', 'messages', 'input', 'cache_read', 'cache_write', 'output', 'total'])
    w.writerow([datetime.datetime.now().astimezone().isoformat(timespec='seconds'), label, os.path.basename(path).split('.')[0],
                ' '.join(sorted(x for x in models if x)), len(msgs), t['input'], t['cache_read'], t['cache_write'], t['output'], total])
print('%s: %d messages, %d tokens %s' % (label, len(msgs), total, t))
