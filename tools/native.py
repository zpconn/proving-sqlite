#!/usr/bin/env python3
"""native.py: build and run a bounded card's native tests (Zach, 2026-11-11, evidence/approvals/C-15-bounded/).

A proof in tools/prove.py BOUNDS proves its property only within its bounds; tests/bounded/<card>-<k>.c (k 1 to 9)
test the card's functions past them. Each is built with campaign.py's repro command (REPRO_CC: ASan and UBSan,
-fno-sanitize-recover=undefined, against unmodified upstream/sqlite3.c) and run in campaign.py's repro sandbox
(repro_sandbox: no network, no $HOME, /mnt hidden, an empty environment, nothing writable but its output
directory), so builder-written C runs here exactly as campaign.py runs repro files (checkpoint 1, fix 2). The gate
runs this step for every bounded card it runs; sessions don't run the gate, and inside one the sandbox can't start,
which fails the step.

A test passes if it builds, exits 0 within NATIVE_TIMEOUTS, and prints no sanitizer report. A bounded card with no
test fails, and so does a card BOUNDS doesn't name. Each test's commands, exit codes and output go to
<out>/<card>-<k>.txt (default proofs/<card>/build/native/).

Usage: tools/native.py --card C-NN [--root DIR] [--out DIR]
Ends with: RESULT native C-NN PASS|FAIL <n> tests <m> failed
"""
import argparse
import os
import re
import shutil
import stat
import subprocess
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
import campaign  # noqa: E402
import prove  # noqa: E402

NATIVE_TIMEOUTS = (1800, 600)      # seconds: compiling sqlite3.c with sanitizers, then the run
SANITIZER_REPORTS = ('ERROR: AddressSanitizer', 'runtime error:', 'ERROR: LeakSanitizer')
TEST_RX = re.compile(r'^(C-[0-9]{2})-([1-9])\.c$')


def run_one(root, src, out):
    """(ok, summary, transcript) for one test file."""
    upstream = os.path.join(root, 'upstream')
    lines = ['native.py built and ran %s against %s/sqlite3.c (sha256 %s), in campaign.py\'s repro sandbox.' % (
        os.path.relpath(src, root), os.path.relpath(upstream, root), campaign.sha256_file(os.path.join(upstream, 'sqlite3.c')))]
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    home = os.path.expanduser('~')
    rcs = []
    for what, cmd, tmo in (('build', campaign.REPRO_CC, NATIVE_TIMEOUTS[0]), ('run', campaign.REPRO_RUN, NATIVE_TIMEOUTS[1])):
        lines.append('$ ' + ' '.join(cmd))
        try:
            p = subprocess.run(['nice', '-n', '10'] + campaign.repro_sandbox(home, upstream, src, out) + cmd,
                               capture_output=True, timeout=tmo)
            body, rc = (p.stdout + p.stderr).decode('utf-8', 'replace'), p.returncode
        except subprocess.TimeoutExpired as e:
            body = ((e.stdout or b'') + (e.stderr or b'')).decode('utf-8', 'replace') + '\n(timed out after %d s)' % tmo
            rc = 'timeout'
        lines += [body[-60000:], 'exit: %s' % rc]
        rcs.append('%s exit %s' % (what, rc))
        if rc != 0:
            break
    text = '\n'.join(lines)
    reports = [r for r in SANITIZER_REPORTS if r in text]
    ok = rcs == ['build exit 0', 'run exit 0'] and not reports
    shutil.rmtree(out, ignore_errors=True)
    return ok, ', '.join(rcs + (['sanitizer report'] if reports else [])), text + '\n'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--card', required=True)
    ap.add_argument('--root', default=os.path.dirname(TOOLS))
    ap.add_argument('--out')
    a = ap.parse_args()
    root = os.path.abspath(a.root)
    out = os.path.abspath(a.out or os.path.join(root, 'proofs', a.card, 'build', 'native'))
    d = os.path.join(root, 'tests', 'bounded')
    tests = sorted(n for n in (os.listdir(d) if os.path.isdir(d) else []) if TEST_RX.match(n) and TEST_RX.match(n).group(1) == a.card)
    if a.card not in prove.BOUNDS:
        print('native: %s is not in tools/prove.py BOUNDS, so it has no native tests to run' % a.card)
        print('RESULT native %s FAIL 0 tests 0 failed' % a.card)
        return 1
    if not tests:
        print('native: %s is bounded (tools/prove.py BOUNDS) but tests/bounded/ has no %s-<k>.c' % (a.card, a.card))
        print('RESULT native %s FAIL 0 tests 0 failed' % a.card)
        return 1
    os.makedirs(out, exist_ok=True)
    failed = 0
    for n in tests:
        src = os.path.join(d, n)
        if not stat.S_ISREG(os.lstat(src).st_mode):
            ok, summary, text = False, 'not a regular file', 'not built: %s is not a regular file\n' % n
        else:
            ok, summary, text = run_one(root, src, os.path.join(out, n[:-2] + '.build'))
        with open(os.path.join(out, n[:-2] + '.txt'), 'w') as f:
            f.write(text)
        failed += not ok
        print('native %s %s: %s' % (n, 'PASS' if ok else 'FAIL', summary))
    print('RESULT native %s %s %d tests %d failed' % (a.card, 'FAIL' if failed else 'PASS', len(tests), failed))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
