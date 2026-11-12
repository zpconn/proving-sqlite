#!/usr/bin/env python3
"""check_overlay.py: overlay/sqlite3.c must be upstream/sqlite3.c plus PROOF(...) spans and nothing else.

Deletes every PROOF span (the characters from `PROOF(` to its matching `)`) from the overlay and
requires the result to equal upstream byte for byte. Also requires upstream itself to contain no
`PROOF(` token, and upstream's hash to match pin.txt.

Usage: tools/check_overlay.py [--root DIR] [--overlay FILE]
Ends with: RESULT check_overlay PASS|FAIL <n> spans
"""
import argparse
import hashlib
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import overlay as ov  # noqa: E402


def pinned_hash(root):
    with open(os.path.join(root, 'pin.txt')) as f:
        for line in f:
            m = re.match(r'^upstream/sqlite3\.c:\s*([0-9a-f]{64})\s*$', line)
            if m:
                return m.group(1)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument('--overlay', default=None)
    a = ap.parse_args()
    root = a.root
    up_path = os.path.join(root, 'upstream', 'sqlite3.c')
    ov_path = a.overlay or os.path.join(root, 'overlay', 'sqlite3.c')
    problems = []
    up = open(up_path, 'rb').read()
    over = open(ov_path, 'rb').read()
    want = pinned_hash(root)
    got = hashlib.sha256(up).hexdigest()
    if want is None:
        problems.append('pin.txt has no upstream/sqlite3.c hash')
    elif want != got:
        problems.append('upstream/sqlite3.c sha256 %s != pin.txt %s' % (got, want))
    if ov.SPAN_START.search(up):
        problems.append('upstream/sqlite3.c itself contains a PROOF( token')
    nspans = 0
    try:
        stripped, spans = ov.strip_spans(over)
        nspans = len(spans)
        problems.extend(ov.span_lexical_problems(over, spans))
        if stripped != up:
            # report the first difference
            n = min(len(stripped), len(up))
            i = next((k for k in range(n) if stripped[k] != up[k]), n)
            line = up.count(b'\n', 0, i) + 1
            ctx_up = up[max(0, i - 40):i + 40]
            ctx_ov = stripped[max(0, i - 40):i + 40]
            problems.append('overlay minus PROOF spans differs from upstream at upstream byte %d (line %d)\n'
                            '  upstream: %r\n  overlay:  %r' % (i, line, ctx_up, ctx_ov))
    except ov.SpanError as e:
        problems.append(str(e))
    for p in problems:
        print('check_overlay: ' + p)
    if not problems:
        print('check_overlay: overlay = upstream + %d PROOF spans; upstream sha256 matches pin.txt' % nspans)
    print('RESULT check_overlay %s %d spans' % ('FAIL' if problems else 'PASS', nspans))
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
