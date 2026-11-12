#!/usr/bin/env python3
"""Build and run the auditor's F-001 misorder test (misorder.c, unchanged) in campaign.py's repro sandbox: no network,
no $HOME, an empty environment, unmodified upstream. gcc -O2 and -O0, no sanitizers; INT_MIN with a DESC index, and the
controls (-1 with DESC, INT_MIN with ASC). Writes run.txt beside this file."""
import os, shutil, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import campaign  # noqa: E402
up = os.path.join(ROOT, 'upstream')
src = os.path.join(HERE, 'misorder.c')
lines = ['upstream/sqlite3.c sha256 %s' % campaign.sha256_file(os.path.join(up, 'sqlite3.c'))]
for opt in ('-O2', '-O0'):
    out = os.path.join(HERE, 'build' + opt)
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    sb = campaign.repro_sandbox(os.path.expanduser('~'), up, src, out)
    cc = ['cc', '-std=gnu11', opt, '-I', '/tmp/repro/upstream', '-o', '/tmp/repro/out/m', '/tmp/repro/src/repro.c',
          '/tmp/repro/upstream/sqlite3.c', '-lm', '-lpthread', '-ldl']
    p = subprocess.run(['nice', '-n', '10'] + sb + cc, capture_output=True, text=True, timeout=1800)
    lines.append('$ %s\nbuild exit %d %s' % (' '.join(cc), p.returncode, (p.stdout + p.stderr)[-2000:]))
    for args in ([], ['control'], ['intmin', 'asc']):
        r = subprocess.run(sb + ['/tmp/repro/out/m'] + args, capture_output=True, text=True, timeout=600)
        lines.append('== %s %s\n%s(exit %d)' % (opt, ' '.join(args) or 'intmin desc', r.stdout + r.stderr, r.returncode))
    shutil.rmtree(out, ignore_errors=True)
open(os.path.join(HERE, 'run.txt'), 'w').write('\n'.join(lines) + '\n')
print('\n'.join(lines))
