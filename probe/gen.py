#!/usr/bin/env python3
"""T-006 probe: the legacy translation unit for C-15's proof `unpack`, generated as the lost prove.py patch did.
harness.c, then each enforced or replaced function redeclared with the clauses of its proofs/contracts/<fn>.h
contract_<fn> declaration, with only the name changed. Usage: gen.py <repo root> <out.c>"""
import os
import re
import sys

root, out = sys.argv[1], sys.argv[2]
FNS = ['sqlite3VdbeRecordUnpack', 'sqlite3GetVarint32', 'sqlite3VdbeSerialGet', 'sqlite3VdbeSerialTypeLen',
       'sqlite3VdbeMemSetNull']


def strip_comments(t):
    return re.sub(r'//[^\n]*', '', re.sub(r'/\*.*?\*/', lambda m: ' ' * len(m.group(0)), t, flags=re.S))


def declaration(text, fn):
    t = strip_comments(text)
    hits = list(re.finditer(r'\bcontract_%s\s*\(' % re.escape(fn), t))
    assert len(hits) == 1, (fn, len(hits))
    p = hits[0].start()
    start = max(t.rfind(';', 0, p), t.rfind('}', 0, p)) + 1
    nl = t.rfind('\n#', 0, p)
    if nl >= start:
        start = t.index('\n', nl + 1) + 1
    depth, i = 0, hits[0].end() - 1
    while i < len(t):
        if t[i] == '(':
            depth += 1
        elif t[i] == ')':
            depth -= 1
        elif t[i] == ';' and depth == 0:
            return t[start:i + 1].strip()
        i += 1
    raise SystemExit('no closing ; for contract_%s' % fn)


parts = ['/* T-006 probe: generated legacy unit for C-15 proof unpack */',
         '#include "%s"' % os.path.join(root, 'proofs', 'C-15', 'harness.c')]
for fn in FNS:
    decl = declaration(open(os.path.join(root, 'proofs', 'contracts', fn + '.h')).read(), fn)
    parts.append('/* from proofs/contracts/%s.h */\n' % fn + re.sub(r'\bcontract_%s(\s*\()' % fn, fn + r'\1', decl, count=1))
open(out, 'w').write('\n'.join(parts) + '\n')
print('wrote %s: %d redeclarations' % (out, len(FNS)))
