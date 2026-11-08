#!/usr/bin/env python3
"""Tests for check_overlay.py, prove.py, scan.py, mutate.py and lock.py (GOAL.md §1.9).

Builds a scratch root that copies tools/ and proofs/{CHECKS,CONFIGS,Makefile.common,include} and
puts a toy sqlite3.c (toy functions, not SQLite) in upstream/ and overlay/, with toy cards and
harnesses. Each case states what the tool must say. Run: tools/tests/test_tools.py [--keep] [-k NAME]
Ends with: RESULT tool-tests PASS|FAIL <passed>/<total>
"""
import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TOY = r'''/* toy sqlite3.c for tool tests: not SQLite */
#include <string.h>
typedef unsigned char u8;
typedef unsigned long long u64;
static int toyLen(u64 v){
  int i;
  for(i=1; (v >>= 7)!=0; i++){ }
  return i;
}
static int toySum(const u8 *p, int n){
  int s = 0, i = 0;
  while( i<n ){
    s += p[i];
    i++;
  }
  return s;
}
static int toyDo(int n){
  int i = 0;
  do{
    i++;
  }while( i<n );
  return i;
}
static int toyGet(const u8 *p){
  if( p[0]<0x80 ) return p[0];
  return ((p[0]&0x7f)<<7) | p[1];
}
static int toyDead(int x){
  int r = 0;
  if( x>10 ) r = 1;
  if( x>20 && x<15 ){
    r = 2;
  }
  return r;
}
int toyLog(int);
static int toyCallsLog(int x){
  return toyLog(x);
}
'''


def line_of(text, needle):
    for i, ln in enumerate(text.split('\n'), 1):
        if needle in ln:
            return i
    raise KeyError(needle)


def card_md(cid, fns, depends='none', extra_may=''):
    fl = ', '.join('%s (upstream/sqlite3.c:%d)' % (f, line_of(TOY, ' %s(' % f)) for f in fns)
    may = 'proofs/%s/harness.c, proofs/%s/Makefile, proofs/%s/NOTES.md, %sreports/%s-b*.md' % (
        cid, cid, cid, extra_may, cid)
    return ('# %s: %s\n- Property: P1\n- Functions: %s\n- In-scope callees, with approved contracts: none\n'
            '- Boundary callees, with ledger entries: none\n- In-scope callers, whose call sites must satisfy the requires: none\n'
            '- Depends on: %s\n- May change: %s\n- Cap: builder 1M; reviewer half that. Tier: standard\n- Notes: toy\n') % (
        cid, ', '.join(fns), fl, depends, may)


HARNESS_GET = r'''#include "sqlite3.c"
#include <stdlib.h>
#include "contracts/toyGet.h"
void harness_toyGet(void) {
  /* SETUP */
  u8 *p = malloc(FOOT);
  __CPROVER_assume(p != 0);
  /* END SETUP */
  toyGet(p);
}
'''
CONTRACT_GET = r'''/* contract for toyGet */
int contract_toyGet(const u8 *p)
  __CPROVER_requires(__CPROVER_r_ok(p, FOOT))
  __CPROVER_ensures(__CPROVER_return_value >= 0);
'''
MK_GET = '''CARD := C-90
PROOFS := get
get_ENTRY := harness_toyGet
get_ENFORCE := toyGet/contract_toyGet
include ../Makefile.common
'''

HARNESS_SUM = r'''#include "sqlite3.c"
#include <stdlib.h>
void harness_toySum(void) {
  int n;
  /* SETUP */
  __CPROVER_assume(n >= 0 && n <= 64);
  u8 *p = malloc(n);
  __CPROVER_assume(p != 0);
  /* END SETUP */
  toySum(p, n);
}
'''
MK_SUM = '''CARD := C-91
PROOFS := sum
sum_ENTRY := harness_toySum
sum_LOOPS := contracts
include ../Makefile.common
'''
SUM_SPAN_GOOD = 'PROOF(\n    __CPROVER_assigns(i, s) __CPROVER_loop_invariant(0 <= i && i <= n && s >= 0 && s <= 255 * i)\n    __CPROVER_decreases(n - i)\n  )'
SUM_SPAN_BAD = 'PROOF(__CPROVER_assigns(i, s) __CPROVER_loop_invariant(0 <= i && i < n) __CPROVER_decreases(n - i))'

HARNESS_DEAD = r'''#include "sqlite3.c"
void harness_toyDead(void) {
  int x;
  toyDead(x);
}
'''
MK_DEAD = '''CARD := C-92
PROOFS := dead
dead_ENTRY := harness_toyDead
dead_COVER := toyDead
include ../Makefile.common
'''


class T:
    def __init__(self, keep):
        self.base = tempfile.mkdtemp(prefix='tooltests-')
        self.keep = keep
        self.passed = 0
        self.total = 0

    def fresh(self):
        root = os.path.join(self.base, 'r%d' % self.total)
        os.makedirs(root)
        shutil.copytree(os.path.join(REPO, 'tools'), os.path.join(root, 'tools'),
                        ignore=shutil.ignore_patterns('__pycache__', 'tests', 'fakecli'))
        os.makedirs(os.path.join(root, 'proofs', 'include'))
        for f in ('CHECKS', 'CONFIGS', 'Makefile.common'):
            shutil.copy(os.path.join(REPO, 'proofs', f), os.path.join(root, 'proofs', f))
        shutil.copy(os.path.join(REPO, 'proofs', 'include', 'proof.h'), os.path.join(root, 'proofs', 'include', 'proof.h'))
        os.makedirs(os.path.join(root, 'upstream'))
        os.makedirs(os.path.join(root, 'overlay'))
        os.makedirs(os.path.join(root, 'cards'))
        os.makedirs(os.path.join(root, 'proofs', 'contracts'))
        self.write(root, 'upstream/sqlite3.c', TOY)
        self.write(root, 'overlay/sqlite3.c', TOY)
        self.write(root, 'pin.txt', 'upstream/sqlite3.c: %s\n' % hashlib.sha256(TOY.encode()).hexdigest())
        subprocess.run(['git', 'init', '-q', '-b', 'main', root], check=True)
        return root

    def write(self, root, rel, text):
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'w') as f:
            f.write(text)

    def run(self, root, args, timeout=900):
        env = dict(os.environ, GNUMAKEFLAGS='--no-print-directory')
        p = subprocess.run(args, cwd=root, capture_output=True, text=True, timeout=timeout, env=env)
        out = p.stdout + p.stderr
        res = [ln for ln in p.stdout.split('\n') if ln.startswith('RESULT ')]
        return p.returncode, out, (res[-1] if res else '')

    def expect(self, name, cond, out):
        self.total += 1
        if cond:
            self.passed += 1
            print('ok   %s' % name)
        else:
            print('FAIL %s\n%s' % (name, '\n'.join('     | ' + ln for ln in out.strip().split('\n')[-25:])))
        sys.stdout.flush()


def setup_get(t, foot_contract=2, foot_alloc=2):
    root = t.fresh()
    t.write(root, 'cards/C-90.md', card_md('C-90', ['toyGet'], extra_may='proofs/contracts/toyGet.h, '))
    t.write(root, 'proofs/C-90/harness.c', HARNESS_GET.replace('FOOT', str(foot_alloc)))
    t.write(root, 'proofs/C-90/Makefile', MK_GET)
    t.write(root, 'proofs/contracts/toyGet.h', CONTRACT_GET.replace('FOOT', str(foot_contract)))
    return root


def setup_sum(t, span=SUM_SPAN_GOOD):
    root = t.fresh()
    t.write(root, 'cards/C-91.md', card_md('C-91', ['toySum']))
    t.write(root, 'proofs/C-91/harness.c', HARNESS_SUM)
    t.write(root, 'proofs/C-91/Makefile', MK_SUM)
    ovl = TOY.replace('  while( i<n ){', '  while( i<n )' + span + '{')
    t.write(root, 'overlay/sqlite3.c', ovl)
    return root


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--keep', action='store_true')
    ap.add_argument('-k', default='')
    a = ap.parse_args()
    t = T(a.keep)
    py = sys.executable
    cfg = 'CONFIG=lp64-le'

    def want(name):
        return a.k in name

    # ---- check_overlay
    if want('overlay'):
        r = setup_sum(t)
        rc, out, res = t.run(r, [py, 'tools/check_overlay.py'])
        t.expect('overlay: upstream + one multi-line span passes', rc == 0 and 'PASS 1 spans' in res, out)
        t.write(r, 'overlay/sqlite3.c', open(os.path.join(r, 'overlay/sqlite3.c')).read().replace('s += p[i];', 's += p[i] ;'))
        rc, out, res = t.run(r, [py, 'tools/check_overlay.py'])
        t.expect('overlay: a one-space change to SQLite text fails', rc != 0 and 'FAIL' in res, out)
        t.write(r, 'overlay/sqlite3.c', TOY.replace('  return r;\n}\nint toyLog', '  /* PROOF( */ r = 2; /* ) */return r;\n}\nint toyLog'))
        rc, out, res = t.run(r, [py, 'tools/check_overlay.py'])
        t.expect('overlay: code hidden between commented PROOF( and ) fails', rc != 0, out)
        t.write(r, 'overlay/sqlite3.c', TOY.replace('  return r;\n}\nint toyLog', '  PROOF(r = 2;)return r;\n}\nint toyLog'))
        rc, out, res = t.run(r, [py, 'tools/check_overlay.py'])
        rc2, out2, res2 = t.run(r, [py, 'tools/scan.py'])
        t.expect('overlay: code inside a PROOF span passes check_overlay but fails scan',
                 rc == 0 and rc2 != 0 and 'contract clauses' in out2, out + out2)
        t.write(r, 'upstream/sqlite3.c', TOY + '\n')
        rc, out, res = t.run(r, [py, 'tools/check_overlay.py'])
        t.expect('overlay: upstream not matching pin.txt fails', rc != 0 and 'pin.txt' in out, out)

    # ---- prove
    if want('prove'):
        r = setup_get(t)
        rc, out, res = t.run(r, ['make', '-C', 'proofs/C-90', 'prove', cfg])
        t.expect('prove: enforced contract with 2-byte footprint passes', rc == 0 and re.search(r'RESULT prove C-90 lp64-le PASS \d+s \d+ properties 0 failed$', res), out)
        t.expect('prove: RESULT is the last line of output (GNUMAKEFLAGS=--no-print-directory, as campaign.py sets)', out.strip().split('\n')[-1].startswith('RESULT prove C-90'), out)
        r = setup_get(t, foot_contract=1, foot_alloc=1)
        rc, out, res = t.run(r, ['make', '-C', 'proofs/C-90', 'prove', cfg])
        t.expect('prove: footprint one less (1 byte) fails on p[1]', rc != 0 and 'FAIL' in res and re.search(r'FAILED get .*(pointer outside object bounds|dereference failure)', out), out)
        r = setup_get(t)
        rc, out, res = t.run(r, ['make', '-C', 'proofs/C-90', 'prove', 'CONFIG=lp64-be'])
        t.expect('prove: lp64-be runs', rc == 0 and 'lp64-be PASS' in res, out)
        r = setup_sum(t)
        rc, out, res = t.run(r, ['make', '-C', 'proofs/C-91', 'prove', cfg])
        t.expect('prove: loop contract on a while loop passes', rc == 0 and 'PASS' in res, out)
        r = setup_sum(t, SUM_SPAN_BAD)
        rc, out, res = t.run(r, ['make', '-C', 'proofs/C-91', 'prove', cfg])
        t.expect('prove: false loop invariant fails', rc != 0 and 'loop_invariant' in out, out)
        r = t.fresh()
        t.write(r, 'cards/C-93.md', card_md('C-93', ['toyCallsLog']))
        t.write(r, 'proofs/C-93/harness.c', '#include "sqlite3.c"\nvoid h(void) { int x; toyCallsLog(x); }\n')
        t.write(r, 'proofs/C-93/Makefile', 'CARD := C-93\nPROOFS := p\np_ENTRY := h\ninclude ../Makefile.common\n')
        rc, out, res = t.run(r, ['make', '-C', 'proofs/C-93', 'prove', cfg])
        t.expect('prove: a call to a function without a body fails', rc != 0 and 'without a body' in out and 'toyLog' in out, out)
        r = setup_get(t)
        t.write(r, 'proofs/C-90/Makefile', MK_GET + 'get_FLAGS := --no-bounds-check\n')
        rc, out, res = t.run(r, ['make', '-C', 'proofs/C-90', 'prove', cfg])
        t.expect('prove: a Makefile variable outside the schema fails', rc != 0 and 'not allowed' in out, out)
        r = setup_get(t)
        t.write(r, 'proofs/C-90/Makefile', MK_GET.replace('include', 'get_SOLVER := --no-bounds-check\ninclude'))
        rc, out, res = t.run(r, ['make', '-C', 'proofs/C-90', 'prove', cfg])
        t.expect('prove: a check-disabling option in SOLVER fails', rc != 0 and 'SOLVER' in out, out)
        r = setup_get(t)
        t.write(r, 'proofs/C-90/Makefile', MK_GET.replace('include', 'get_ENFORCE := toyGet/contract_toyLen\ninclude'))
        rc, out, res = t.run(r, ['make', '-C', 'proofs/C-90', 'prove', cfg])
        t.expect('prove: ENFORCE pairing f with another function\'s contract fails', rc != 0 and 'contract_<fn>' in out, out)

    # ---- coverage
    if want('coverage'):
        r = t.fresh()
        t.write(r, 'cards/C-92.md', card_md('C-92', ['toyDead']))
        t.write(r, 'proofs/C-92/harness.c', HARNESS_DEAD)
        t.write(r, 'proofs/C-92/Makefile', MK_DEAD)
        dead = line_of(TOY, '    r = 2;')
        rc, out, res = t.run(r, ['make', '-C', 'proofs/C-92', 'coverage', cfg])
        t.expect('coverage: unreachable line %d is flagged and unexplained fails' % dead,
                 rc != 0 and ('sqlite3.c:%d' % dead) in out and 'NOT EXPLAINED' in out, out)
        t.write(r, 'proofs/C-92/NOTES.md', '- sqlite3.c:%d: x>20 && x<15 is unsatisfiable\n' % dead)
        rc, out, res = t.run(r, ['make', '-C', 'proofs/C-92', 'coverage', cfg])
        t.expect('coverage: the same gap explained in NOTES.md passes', rc == 0 and '1 uncovered 0 unexplained' in res, out)
        r = setup_get(t)
        rc, out, res = t.run(r, ['make', '-C', 'proofs/C-90', 'coverage', cfg])
        t.expect('coverage: an enforced function is measured on its wrapped body (no false gaps)', rc == 0 and '0 uncovered' in res, out)

    # ---- scan
    if want('scan'):
        r = setup_get(t)
        rc, out, res = t.run(r, [py, 'tools/scan.py'])
        t.expect('scan: clean card passes', rc == 0 and 'PASS' in res, out)
        attacks = [
            ('assume outside SETUP', 'proofs/C-90/harness.c', HARNESS_GET.replace('FOOT', '2').replace('  toyGet(p);', '  __CPROVER_assume(p[0] < 0x80);\n  toyGet(p);'), 'outside a /* SETUP */'),
            ('assume on data bytes in SETUP', 'proofs/C-90/harness.c', HARNESS_GET.replace('FOOT', '2').replace('  /* END SETUP */', '  __CPROVER_assume(p[1] == 0);\n  /* END SETUP */'), 'subscripts an array'),
            ('assume dereferencing data in SETUP', 'proofs/C-90/harness.c', HARNESS_GET.replace('FOOT', '2').replace('  /* END SETUP */', '  __CPROVER_assume(*p == 0);\n  /* END SETUP */'), 'dereferences a pointer'),
            ('pragma disabling a check', 'proofs/C-90/harness.c', HARNESS_GET.replace('FOOT', '2').replace('void harness', '#pragma CPROVER check disable "pointer"\nvoid harness'), 'pragma'),
            ('define before sqlite3.c', 'proofs/C-90/harness.c', '#define SQLITE_OMIT_FOO 1\n' + HARNESS_GET.replace('FOOT', '2'), 'first line'),
            ('harness defines toyLog, which SQLite\'s (toy) code calls', 'proofs/C-90/harness.c', HARNESS_GET.replace('FOOT', '2') + 'int toyLog(int x) { return 0; }\n', 'defines toyLog'),
            ('macro hiding assume', 'proofs/C-90/harness.c', HARNESS_GET.replace('FOOT', '2').replace('void harness', '#define A(x) __CPROVER_assume(x)\nvoid harness'), 'macro may not mention'),
            ('zero-filled buffer', 'proofs/C-90/harness.c', HARNESS_GET.replace('FOOT', '2').replace('malloc(2)', 'calloc(2, 1)'), 'calloc'),
            ('file-scope buffer', 'proofs/C-90/harness.c', HARNESS_GET.replace('FOOT', '2').replace('void harness', 'u8 buf[9];\nvoid harness'), 'file-scope object'),
            ('contract declared in harness', 'proofs/C-90/harness.c', HARNESS_GET.replace('FOOT', '2').replace('void harness', 'int contract_toyLen(u64 v) __CPROVER_ensures(1);\nvoid harness'), 'may be declared only'),
            ('CHECKS with --no-bounds-check', 'proofs/CHECKS', open(os.path.join(REPO, 'proofs', 'CHECKS')).read() + '--no-bounds-check\n', 'turns a check off'),
            ('CHECKS missing unwinding assertions', 'proofs/CHECKS', open(os.path.join(REPO, 'proofs', 'CHECKS')).read().replace('--unwinding-assertions\n', ''), '--unwinding-assertions missing'),
            ('CONFIGS with an extra -D', 'proofs/CONFIGS', open(os.path.join(REPO, 'proofs', 'CONFIGS')).read().replace('lp64-le   -m64', 'lp64-le   -m64 -DSQLITE_OMIT_UTF16'), 'not a word-size'),
        ]
        for name, rel, text, needle in attacks:
            r = setup_get(t)
            t.write(r, rel, text)
            rc, out, res = t.run(r, [py, 'tools/scan.py'])
            t.expect('scan rejects: %s' % name, rc != 0 and needle in out, out)
        # spans
        span_cases = [
            ('span with an assignment', SUM_SPAN_GOOD.replace('s <= 255 * i', 's = 0'), 'assignment'),
            ('span with clauses out of order', 'PROOF(__CPROVER_loop_invariant(i <= n) __CPROVER_assigns(i, s) __CPROVER_decreases(n - i))', 'in that order'),
            ('span with an assume', 'PROOF(__CPROVER_assigns(i, s) __CPROVER_loop_invariant(__CPROVER_assume(0)) __CPROVER_decreases(n - i))', 'assume'),
            ('span calling an unknown function', 'PROOF(__CPROVER_assigns(i, s) __CPROVER_loop_invariant(toyLen(i) > 0) __CPROVER_decreases(n - i))', 'neither a CPROVER primitive'),
        ]
        for name, span, needle in span_cases:
            r = setup_sum(t, span)
            rc, out, res = t.run(r, [py, 'tools/scan.py'])
            t.expect('scan rejects: %s' % name, rc != 0 and needle in out, out)
        r = setup_sum(t)
        t.write(r, 'overlay/sqlite3.c', TOY.replace('  if( x>10 ) r = 1;', '  if( x>10 )PROOF(__CPROVER_assigns(r) __CPROVER_loop_invariant(1) __CPROVER_decreases(0)) r = 1;'))
        rc, out, res = t.run(r, [py, 'tools/scan.py'])
        t.expect('scan rejects: span after an if, not a loop', rc != 0 and 'between a loop header' in out, out)
        r = setup_sum(t)
        t.write(r, 'overlay/sqlite3.c', TOY.replace('  }while( i<n );', '  }while( i<n )PROOF(__CPROVER_assigns(i) __CPROVER_loop_invariant(i < n) __CPROVER_decreases(n - i));'))
        rc, out, res = t.run(r, [py, 'tools/scan.py'])
        t.expect('scan rejects: span after a do-while condition', rc != 0 and 'do-while' in out, out)
        r = setup_sum(t)
        t.write(r, 'overlay/sqlite3.c', TOY.replace('  do{', '  do PROOF(__CPROVER_assigns(i) __CPROVER_loop_invariant(i < n) __CPROVER_decreases(n - i)){').replace('  do PROOF', '  doPROOF').replace('  doPROOF', '  do PROOF'))
        # do-while span in toyDo, which no card names
        rc, out, res = t.run(r, [py, 'tools/scan.py'])
        t.expect('scan rejects: span in a function no card names', rc != 0 and 'outside every card' in out, out)
        r = setup_sum(t)
        subprocess.run(['git', '-C', r, 'add', '-A'], check=True)
        subprocess.run(['git', '-C', r, '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-qm', 'base'], check=True)
        t.write(r, 'cards/C-90.md', card_md('C-90', ['toyLen']))
        ovl = open(os.path.join(r, 'overlay/sqlite3.c')).read().replace(SUM_SPAN_GOOD, SUM_SPAN_GOOD.replace('s >= 0', 's >= 0 && 1'))
        t.write(r, 'overlay/sqlite3.c', ovl)
        rc, out, res = t.run(r, [py, 'tools/scan.py', '--card', 'C-90', '--base', 'HEAD'])
        t.expect('scan --card: a span changed in another card\'s function is rejected', rc != 0 and 'does not name' in out, out)
        r = setup_get(t)
        t.write(r, 'proofs/C-90/Makefile', MK_GET.replace('include', 'get_REPLACE := toyLog/contract_toyLog\ninclude'))
        t.write(r, 'proofs/contracts/toyLog.h', 'int contract_toyLog(int x) __CPROVER_ensures(1);\n')
        rc, out, res = t.run(r, [py, 'tools/scan.py'])
        t.expect('scan rejects: boundary contract without a ledger entry', rc != 0 and 'Ledger: A-NNN' in out, out)
        t.write(r, 'proofs/contracts/toyLog.h', '/* Ledger: A-007 */\nint contract_toyLog(int x) __CPROVER_ensures(1);\n')
        rc, out, res = t.run(r, [py, 'tools/scan.py'])
        t.expect('scan: boundary contract naming its ledger entry passes', rc == 0, out)
        t.write(r, 'LEDGER.md', '# Ledger\n## A-001 something\n')
        rc, out, res = t.run(r, [py, 'tools/scan.py'])
        t.expect('scan rejects: ledger entry named but absent from LEDGER.md', rc != 0 and 'A-007' in out, out)
        r = setup_get(t)
        t.write(r, 'cards/C-94.md', card_md('C-94', ['toyLen']))
        t.write(r, 'proofs/contracts/toyLen.h', 'int contract_toyLen(u64 v) __CPROVER_ensures(__CPROVER_return_value == 1);\n')
        t.write(r, 'proofs/C-90/Makefile', MK_GET.replace('include', 'get_REPLACE := toyLen/contract_toyLen\ninclude'))
        rc, out, res = t.run(r, [py, 'tools/scan.py'])
        t.expect('scan rejects: replacing an in-scope callee whose contract no card enforces', rc != 0 and 'no card' in out, out)

    # ---- mutate
    if want('mutate'):
        r = setup_get(t)
        gl = line_of(TOY, 'return ((p[0]&0x7f)<<7) | p[1];')
        t.write(r, 'proofs/MUTANTS', "M-001 toyGet %d 'p[1]' 'p[2]'\nM-002 toyGet %d '0x7f' '0x3f'\n" % (gl, gl))
        h0 = hashlib.sha256(open(os.path.join(r, 'overlay/sqlite3.c'), 'rb').read()).hexdigest()
        rc, out, res = t.run(r, [py, 'tools/mutate.py', '--card', 'C-90', '--config', 'lp64-le'])
        h1 = hashlib.sha256(open(os.path.join(r, 'overlay/sqlite3.c'), 'rb').read()).hexdigest()
        t.expect('mutate: out-of-bounds mutant killed, functional mutant survives -> FAIL, overlay untouched',
                 rc != 0 and 'M-001' in out and re.search(r'M-001 .* KILLED', out) and re.search(r'M-002 .* SURVIVED', out)
                 and 'FAIL 1/2 killed' in res and h0 == h1, out)
        t.write(r, 'proofs/MUTANTS', "M-001 toyGet %d 'p[1]' 'p[2]'\nM-002 toyGet %d '0x7f' '0x3f' equivalent='UB-free either way' review=reviews/C-90-r1.md\n" % (gl, gl))
        rc, out, res = t.run(r, [py, 'tools/mutate.py', '--card', 'C-90', '--config', 'lp64-le'])
        t.expect('mutate: survivor with a reviewed equivalence argument passes', rc == 0 and '1/2 killed 1 equivalent' in res, out)
        t.write(r, 'proofs/MUTANTS', "M-001 toyGet %d 'p' 'q'\n" % gl)
        rc, out, res = t.run(r, [py, 'tools/mutate.py', '--card', 'C-90', '--config', 'lp64-le'])
        t.expect('mutate: ambiguous mutant (token occurs several times) is an error', rc != 0 and 'occurs' in out, out)
        rc, out, res = t.run(r, [py, 'tools/mutate.py', '--card', 'C-90', '--config', 'lp64-le', '--adhoc', "toyGet %d '<<7' '<<70'" % gl])
        t.expect('mutate --adhoc: planted shift bug is killed', rc == 0 and 'KILLED' in out and 'shift' in out, out)

    # ---- lock
    if want('lock'):
        r = setup_get(t)
        for f in ('GOAL.md', 'AGENTS.md', 'CLAUDE.md', 'PROPERTIES.md', 'TRUSTED.md', 'UB-CLASSES.md', 'proofs/MUTANTS', 'Makefile'):
            t.write(r, f, 'x\n')
        subprocess.run(['git', '-C', r, 'add', '-A'], check=True)
        rc, out, res = t.run(r, [py, 'tools/lock.py', 'write'])
        rc, out, res = t.run(r, [py, 'tools/lock.py', 'check'])
        t.expect('lock: freshly written lock checks', rc == 0 and 'PASS' in res, out)
        t.write(r, 'tools/sessions.toml', 'x = 1\n')
        subprocess.run(['git', '-C', r, 'add', '-A'], check=True)
        rc, out, res = t.run(r, [py, 'tools/lock.py', 'check'])
        t.expect('lock: sessions.toml is exempt', rc == 0, out)
        t.write(r, 'tools/scan.py', open(os.path.join(r, 'tools/scan.py')).read() + '\n# weakened\n')
        rc, out, res = t.run(r, [py, 'tools/lock.py', 'check'])
        t.expect('lock: a changed tool fails', rc != 0 and 'tools/scan.py changed' in out, out)
        t.write(r, 'tools/extra.py', '# new\n')
        subprocess.run(['git', '-C', r, 'add', '-A'], check=True)
        rc, out, res = t.run(r, [py, 'tools/lock.py', 'check'])
        t.expect('lock: a new file under a frozen path fails', rc != 0 and 'tools/extra.py is under a frozen path' in out, out)

    print('RESULT tool-tests %s %d/%d' % ('PASS' if t.passed == t.total else 'FAIL', t.passed, t.total))
    if not a.keep:
        shutil.rmtree(t.base, ignore_errors=True)
    else:
        print('kept %s' % t.base)
    return 0 if t.passed == t.total else 1


if __name__ == '__main__':
    sys.exit(main())
