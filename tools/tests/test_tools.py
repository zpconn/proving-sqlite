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
static int toyDead2(int x){
  int q = 0;
  if( x>20 && x<15 ){
    q = 2;
    q = q + 1;
    q = q * 3;
  }
  return q;
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
  /* SETUP */
  /* END SETUP */
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
        t.write(r, 'proofs/C-92/NOTES.md', '## Requires\n| caller | sqlite3.c:%d |\n' % dead)
        rc, out, res = t.run(r, ['make', '-C', 'proofs/C-92', 'coverage', cfg])
        t.expect('coverage: the gap cited in NOTES.md outside "Unreached lines" (a requires table) is not an explanation',
                 rc != 0 and 'NOT EXPLAINED' in out and '1 unexplained' in res, out)
        t.write(r, 'proofs/C-92/NOTES.md', '## Requires\n| caller | sqlite3.c:1 |\n\n## Unreached lines\n'
                '- sqlite3.c:%d: x>20 && x<15 is unsatisfiable\n\n## Loops\n- none\n' % dead)
        rc, out, res = t.run(r, ['make', '-C', 'proofs/C-92', 'coverage', cfg])
        t.expect('coverage: the same gap listed under "## Unreached lines" in NOTES.md passes', rc == 0 and '1 uncovered 0 unexplained' in res, out)
        r = setup_get(t)
        rc, out, res = t.run(r, ['make', '-C', 'proofs/C-90', 'coverage', cfg])
        t.expect('coverage: an enforced function is measured on its wrapped body (no false gaps)', rc == 0 and '0 uncovered' in res, out)
        # follow-up 3: each entry is one line or a range within one uncovered block, with a reason, and must be
        # uncovered in this run
        r = t.fresh()
        t.write(r, 'cards/C-95.md', card_md('C-95', ['toyDead2']))
        t.write(r, 'proofs/C-95/harness.c', HARNESS_DEAD.replace('toyDead', 'toyDead2'))
        t.write(r, 'proofs/C-95/Makefile', MK_DEAD.replace('C-92', 'C-95').replace('toyDead', 'toyDead2'))
        qa, qc, qcov = line_of(TOY, '    q = 2;'), line_of(TOY, '    q = q * 3;'), line_of(TOY, '  int q = 0;')
        head = '## Requires\nnone\n\n## Unreached lines\n'

        def cov(entries):
            t.write(r, 'proofs/C-95/NOTES.md', head + entries + '\n## Loops\n- none\n')
            return t.run(r, ['make', '-C', 'proofs/C-95', 'coverage', cfg])
        rc, out, res = cov('- sqlite3.c:%d-%d: x>20 && x<15 is unsatisfiable\n' % (qa, qc))
        t.expect('coverage: a range within one uncovered block, with a reason, explains the gap',
                 rc == 0 and '3 uncovered 0 unexplained' in res, out)
        rc, out, res = cov('- sqlite3.c:1-%d: lines the harness bounds\n' % (qc + 3))
        t.expect('coverage rejects: a blanket range wider than the uncovered block (the auditor\'s 37900-38099)',
                 rc != 0 and 'not within one uncovered block' in out, out)
        rc, out, res = cov('- sqlite3.c:%d-%d: x>20 && x<15 is unsatisfiable\n' % (qa, qc + 1))
        t.expect('coverage rejects: a range that runs one line past the uncovered block', rc != 0 and 'not within one uncovered block' in out, out)
        rc, out, res = cov('- sqlite3.c:%d-%d: x>20 && x<15 is unsatisfiable\n- sqlite3.c:%d: also unreached\n' % (qa, qc, qcov))
        t.expect('coverage rejects: an entry naming a line this run covers',
                 rc != 0 and ('sqlite3.c:%d is listed as unreached, but no proof' % qcov) in out, out)
        rc, out, res = cov('- sqlite3.c:%d-%d:\n' % (qa, qc))
        t.expect('coverage rejects: an entry with no reason', rc != 0 and 'not an entry' in out, out)
        rc, out, res = cov('- sqlite3.c:%d: and sqlite3.c:%d-%d: unreachable\n' % (qa, qa + 1, qc))
        t.expect('coverage rejects: an entry naming more than one line or range', rc != 0 and 'one line or range per entry' in out, out)
        rc, out, res = cov('Lines %d to %d are unreachable because x>20 && x<15 is unsatisfiable.\n' % (qa, qc))
        t.expect('coverage rejects: prose under "## Unreached lines" instead of entries', rc != 0 and 'not an entry' in out, out)

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
        # checkpoint 0, decision C1: hidden assumes, and SETUP discipline
        G = HARNESS_GET.replace('FOOT', '2')
        END = '  /* END SETUP */\n'
        c1 = [
            ('abort() as a hidden assume', G.replace('  toyGet(p);', '  if (p[0] > 5) abort();\n  toyGet(p);'), 'abort ends or redirects'),
            ('__VERIFIER_assume', G.replace('  toyGet(p);', '  __VERIFIER_assume(p[0] < 5);\n  toyGet(p);'), '__VERIFIER_assume'),
            ('exit through a function pointer', G.replace('  toyGet(p);', '  void (*q)(int) = exit;\n  toyGet(p);'), 'exit ends'),
            ('longjmp', G.replace('  toyGet(p);', '  toyGet(p);\n  longjmp(0, 1);'), 'longjmp'),
            ('__CPROVER_array_set on the data', G.replace('  toyGet(p);', '  __CPROVER_array_set(p, 0);\n  toyGet(p);'), '__CPROVER_array_set'),
            ('return in the entry function', G.replace(END, END + '  if (p[0] > 5) return;\n'), 'return in entry function'),
            ('goto in the entry function', G.replace(END, END + '  if (p[0] > 5) goto out;\n').replace('  toyGet(p);', '  toyGet(p);\nout: ;'), 'goto in entry function'),
            ('two SETUP blocks', G.replace('  toyGet(p);', '  /* SETUP */\n  __CPROVER_assume(p != 0);\n  /* END SETUP */\n  toyGet(p);'), 'exactly one'),
            ('no SETUP block', G.replace('  /* SETUP */\n', '').replace(END, ''), 'exactly one'),
            ('a statement before SETUP', G.replace('void harness_toyGet(void) {\n', 'void harness_toyGet(void) {\n  int x;\n  x = 3;\n'), 'before SETUP'),
            ('a data byte stored in SETUP', G.replace(END, '  p[0] = 1;\n' + END), 'store through a subscript'),
            ('a data byte copied into a local in SETUP', G.replace(END, '  int x = p[1];\n' + END), 'read through'),
            ('a predicate called from a SETUP assume', G.replace(END, '  __CPROVER_assume(toyOk(p));\n' + END), 'may call only'),
            ('the call under proof inside a condition', G.replace('  toyGet(p);', '  if (p[0] < 0x80) toyGet(p);'), 'not inside a condition'),
            ('the call under proof in a short-circuit', G.replace('  toyGet(p);', '  p[0] < 0x80 && toyGet(p);'), 'not inside a condition'),
            ('an entry function that never calls the function under proof', G.replace('  toyGet(p);', '  toyLen(1);'), 'never calls'),
            ('a SETUP block in a helper', G + 'static void helper(u8 *q) {\n  /* SETUP */\n  __CPROVER_assume(q != 0);\n  /* END SETUP */\n}\n', 'SETUP block outside an entry function'),
            ('#pragma GCC system_header', G.replace('void harness', '#pragma GCC system_header\nvoid harness'), 'pragma'),
            ('#line', G.replace('void harness', '#line 1 "x.c"\nvoid harness'), '#line not allowed'),
        ]
        for name, text, needle in c1:
            r = setup_get(t)
            t.write(r, 'proofs/C-90/harness.c', text)
            rc, out, res = t.run(r, [py, 'tools/scan.py'])
            t.expect('scan rejects (C1): %s' % name, rc != 0 and needle in out, out)
        for name, rel, text, needle in [
                ('abort() in a contract', 'proofs/contracts/toyGet.h', CONTRACT_GET.replace('FOOT', '2').replace(
                    '__CPROVER_return_value >= 0', '__CPROVER_return_value >= 0 || (abort(), 1)'), 'abort'),
                ('abort() in preds.h', 'proofs/include/preds.h', 'static int toyOk(const u8 *p) { if (p == 0) abort(); return 1; }\n', 'abort')]:
            r = setup_get(t)
            t.write(r, rel, text)
            rc, out, res = t.run(r, [py, 'tools/scan.py'])
            t.expect('scan rejects (C1): %s' % name, rc != 0 and needle in out, out)
        # checkpoint 0 follow-up 2: harness discipline, one case per way of narrowing the inputs
        DECL_R = 'void harness_toyGet(void) {\n  int r;'
        BOX = 'struct box { int n; u8 *z; };\nvoid harness'
        f2 = [
            ('a #define that hides a store in SETUP', G.replace('void harness', '#define PIN p[0] = 0\nvoid harness').replace(END, '  PIN;\n' + END), '#define: a harness may use no preprocessor directive'),
            ('an #undef', G.replace('void harness', '#undef toyLen\nvoid harness'), '#undef: a harness may use no preprocessor directive'),
            ('a store through a subscript between END SETUP and the call', G.replace(END, END + '  p[0] = 0x7f;\n'), 'between END SETUP and the call under proof'),
            ('a store through a pointer between END SETUP and the call', G.replace(END, END + '  *p = 0x7f;\n'), 'between END SETUP and the call under proof'),
            ('an if between END SETUP and the call', G.replace(END, END + '  if (p[0] & 0x80) p[1] = 0;\n'), 'between END SETUP and the call under proof'),
            ('a loop between END SETUP and the call', G.replace('void harness_toyGet(void) {', 'void harness_toyGet(void) {\n  int i;').replace(END, END + '  for (i = 0; i < 2; i++) p[i] = 1;\n'), 'between END SETUP and the call under proof'),
            ('a helper that stores, called between END SETUP and the call', G.replace('void harness', 'static void pin(u8 *q) { q[0] = 1; }\nvoid harness').replace(END, END + '  pin(p);\n'), 'between END SETUP and the call under proof'),
            ('SETUP takes an address', G.replace('  u8 *p = malloc(2);', '  u8 one;\n  u8 *p = &one;'), 'may not take an address'),
            ('SETUP reads a member through -> in an assume', G.replace('void harness', BOX).replace('  u8 *p = malloc(2);', '  struct box *b = malloc(sizeof(struct box));\n  __CPROVER_assume(b != 0 && b->n < 4);\n  u8 *p = malloc(2);'), 'may not read a member through a pointer'),
            ('SETUP reads a member through -> in an assignment', G.replace('void harness', BOX).replace('  u8 *p = malloc(2);', '  struct box *b = malloc(sizeof(struct box));\n  u8 *p = b->z;'), 'may not read a member through a pointer'),
            ('a string literal in SETUP', G.replace('  u8 *p = malloc(2);', '  u8 *p = (u8 *)"\\x01\\x02";'), 'may not hold string literals'),
            ('a cast to a data pointer in SETUP', G.replace('  u8 *p = malloc(2);', '  unsigned long a;\n  u8 *p = (u8 *)a;'), 'may cast to a data pointer type only a malloc result'),
            ('a data pointer set to a local array in SETUP', G.replace('  u8 *p = malloc(2);', '  u8 buf[2];\n  u8 *p = buf;'), 'may not name a local array'),
            ('a data pointer set to an integer in SETUP', G.replace('  u8 *p = malloc(2);', '  unsigned long a;\n  u8 *p = 0;\n  p = a;'), 'a data pointer may hold only a malloc result'),
            ('a loop invariant on a harness loop', G.replace('  toyGet(p);', '  toyGet(p);\n  { int i; for (i = 0; i < 2; i++) __CPROVER_loop_invariant(i <= 2) { } }'), '__CPROVER_loop_invariant: no loop or function contract clauses'),
            ('PROOF() on a harness loop', G.replace('#include <stdlib.h>', '#include <stdlib.h>\n#include "proof.h"').replace('  toyGet(p);', '  toyGet(p);\n  { int i; for (i = 0; i < 2; i++) PROOF(__CPROVER_decreases(2 - i)) { } }'), 'PROOF: no loop or function contract clauses'),
            ('__builtin_unreachable after the call', G.replace('void harness_toyGet(void) {', DECL_R).replace('  toyGet(p);', '  r = toyGet(p);\n  if (r > 0x7f) __builtin_unreachable();'), '__builtin_unreachable not allowed in a harness'),
            ('__builtin_assume after the call', G.replace('void harness_toyGet(void) {', DECL_R).replace('  toyGet(p);', '  r = toyGet(p);\n  __builtin_assume(r < 0x80);'), '__builtin_assume not allowed in a harness'),
            ('__attribute__((constructor))', G.replace('void harness', '__attribute__((constructor)) static void early(void) { }\nvoid harness'), '__attribute__ not allowed in a harness'),
            ('a digraph subscript in a SETUP assume', G.replace('  __CPROVER_assume(p != 0);', '  __CPROVER_assume(p != 0 && p<:0:> < 0x80);'), 'digraph <: not allowed'),
            ('a trigraph subscript in a SETUP assume', G.replace('  __CPROVER_assume(p != 0);', '  __CPROVER_assume(p != 0 && p??(0??) < 0x80);'), 'trigraph ??( not allowed'),
            ('a line splice that hides an assume', G.replace('  toyGet(p);', '  toyGet(p);\n  __CPROVER_ass\\\nume(p[1] < 5);'), 'line splice'),
        ]
        for name, text, needle in f2:
            r = setup_get(t)
            t.write(r, 'proofs/C-90/harness.c', text)
            rc, out, res = t.run(r, [py, 'tools/scan.py'])
            t.expect('scan rejects (follow-up 2): %s' % name, rc != 0 and needle in out and 'RESULT scan FAIL' in res, out)
        # the one snapshot form allowed between END SETUP and the call (Zach's decision on follow-up 2)
        rc, out, res = t.run(REPO, [py, 'tools/scan.py', '--card', 'C-02'])
        t.expect('scan (snapshot): C-02\'s merged harness passes', rc == 0 and 'RESULT scan PASS' in res, out)
        GI = G.replace(' *p = ', ' *in = ').replace('assume(p != 0)', 'assume(in != 0)').replace('toyGet(p)', 'toyGet(in)')
        DECL_S = 'void harness_toyGet(void) {\n  u8 snap[2];\n  int i;'
        SNAP_LOOP = '  for(i = 0; i < 2; ++i) snap[i] = in[i];\n'
        snap_ok = [
            ('a snapshot loop into a local array', GI.replace('void harness_toyGet(void) {', DECL_S).replace(END, END + SNAP_LOOP)),
            ('a constant-index snapshot', GI.replace('void harness_toyGet(void) {', DECL_S).replace(END, END + '  snap[1] = in[1];\n')),
        ]
        for name, text in snap_ok:
            r = setup_get(t)
            t.write(r, 'proofs/C-90/harness.c', text)
            rc, out, res = t.run(r, [py, 'tools/scan.py'])
            t.expect('scan (snapshot): %s passes' % name, rc == 0, out)
        snap_bad = [
            ('in[0] &= 0x7f; before the call', GI.replace(END, END + '  in[0] &= 0x7f;\n'), 'between END SETUP and the call under proof'),
            ('a snapshot whose S is a pointer', GI.replace('void harness_toyGet(void) {', 'void harness_toyGet(void) {\n  u8 *snap;\n  int i;').replace(END, END + SNAP_LOOP), 'not a pointer'),
            ('a snapshot into an array then passed to the call', GI.replace('void harness_toyGet(void) {', DECL_S).replace(END, END + SNAP_LOOP).replace('toyGet(in)', 'toyGet(snap)'), 'appears in the call under proof'),
            ('a snapshot loop body with a second statement (braces)', GI.replace('void harness_toyGet(void) {', DECL_S).replace(END, END + '  for(i = 0; i < 2; ++i){ snap[i] = in[i]; in[i] = 0; }\n'), 'between END SETUP and the call under proof'),
            ('a snapshot loop body with a second statement (comma)', GI.replace('void harness_toyGet(void) {', DECL_S).replace(END, END + '  for(i = 0; i < 2; ++i) snap[i] = in[i], in[i] = 0;\n'), 'between END SETUP and the call under proof'),
            ('a snapshot into a static array', GI.replace('void harness_toyGet(void) {', 'void harness_toyGet(void) {\n  static u8 snap[2];\n  int i;').replace(END, END + SNAP_LOOP), 'static'),
            ('a snapshot whose array SETUP names', GI.replace('void harness_toyGet(void) {', DECL_S).replace(END, '  __CPROVER_assume(sizeof(snap) == 2);\n' + END + SNAP_LOOP), 'appears in SETUP'),
            ('a loop counter two snapshot loops assign', GI.replace('void harness_toyGet(void) {', DECL_S + '\n  u8 snap2[2];').replace(END, END + SNAP_LOOP + '  for(i = 0; i < 2; ++i) snap2[i] = in[i];\n'), 'assigned by another snapshot loop'),
            ('a snapshot loop counting with i++', GI.replace('void harness_toyGet(void) {', DECL_S).replace(END, END + '  for(i = 0; i < 2; i++) snap[i] = in[i];\n'), 'between END SETUP and the call under proof'),
        ]
        for name, text, needle in snap_bad:
            r = setup_get(t)
            t.write(r, 'proofs/C-90/harness.c', text)
            rc, out, res = t.run(r, [py, 'tools/scan.py'])
            t.expect('scan rejects (snapshot): %s' % name, rc != 0 and needle in out and 'RESULT scan FAIL' in res, out)
        # auditor recheck item 1: a card function's arguments are only id, &id or id + id
        real = os.path.join(t.base, 'real%d' % t.total)
        for d in ('tools', 'proofs', 'cards', 'overlay', 'upstream'):
            shutil.copytree(os.path.join(REPO, d), os.path.join(real, d),
                            ignore=shutil.ignore_patterns('__pycache__', 'tests', 'fakecli', 'build'))
        shutil.copy(os.path.join(REPO, 'pin.txt'), os.path.join(real, 'pin.txt'))
        subprocess.run(['git', 'init', '-q', '-b', 'main', real], check=True)
        rc, out, res = t.run(real, [py, 'tools/scan.py'])
        t.expect('scan (card calls): a copy of the repo passes', rc == 0 and 'RESULT scan PASS' in res, out)
        h01 = open(os.path.join(REPO, 'proofs/C-01/harness.c')).read()
        assert '  sqlite3PutVarint(output + offset, value);' in h01
        t.write(real, 'proofs/C-01/harness.c', h01.replace('  sqlite3PutVarint(output + offset, value);',
                                                          '  sqlite3PutVarint(output + offset, value | 1);'))
        rc, out, res = t.run(real, [py, 'tools/scan.py', '--card', 'C-01'])
        t.expect('scan rejects (card calls): C-01 with sqlite3PutVarint(output + offset, value | 1)',
                 rc != 0 and 'argument `value | 1` of sqlite3PutVarint' in out and 'RESULT scan FAIL' in res, out)
        t.write(real, 'proofs/C-01/harness.c', h01.replace('  sqlite3PutVarint(output + offset, value);',
                                                          '  sqlite3PutVarint(output + offset, value + value);'))
        rc, out, res = t.run(real, [py, 'tools/scan.py', '--card', 'C-01'])
        t.expect('scan rejects (card calls): C-01 with sqlite3PutVarint(output + offset, value + value) (only even values)',
                 rc != 0 and 'argument `value + value` of sqlite3PutVarint: in x + y, x must be a data pointer' in out
                 and 'RESULT scan FAIL' in res, out)
        # auditor 2026-11-09: every name in a card-call argument is a local the entry function declares before or in SETUP
        ENUM_H01 = h01.replace('#include <stdlib.h>\n', '#include <stdlib.h>\nenum { K = 100 };\n')
        CALL01 = '  sqlite3PutVarint(output + offset, value);'
        for kind, n, base in (('a sqlite3.c macro', 'SQLITE_ROW', h01), ('an enum constant', 'K', ENUM_H01),
                              ('a sqlite3.c global', 'sqlite3PendingByte', h01)):
            for pos, call in (('the id argument', '  sqlite3PutVarint(output + offset, %s);' % n),
                              ('x in x + y', '  sqlite3PutVarint(%s + offset, value);' % n),
                              ('y in x + y', '  sqlite3PutVarint(output + %s, value);' % n)):
                t.write(real, 'proofs/C-01/harness.c', base.replace(CALL01, call))
                rc, out, res = t.run(real, [py, 'tools/scan.py', '--card', 'C-01'])
                t.expect('scan rejects (card calls): C-01 with %s (%s) as %s' % (kind, n, pos),
                         rc != 0 and '%s is not a local variable harness_sqlite3PutVarint declares' % n in out
                         and 'RESULT scan FAIL' in res, out)
        t.write(real, 'proofs/C-01/harness.c', ENUM_H01)
        rc, out, res = t.run(real, [py, 'tools/scan.py', '--card', 'C-01'])
        t.expect('scan (card calls): C-01 with a file-scope enum it does not pass to the call passes', rc == 0, out)
        h02 = open(os.path.join(REPO, 'proofs/C-02/harness.c')).read()
        assert 'getVarint32(encoded, decoded32);' in h02
        t.write(real, 'proofs/C-01/harness.c', h01)
        t.write(real, 'proofs/C-02/harness.c', h02.replace('getVarint32(encoded, decoded32);',
                                                          'getVarint32(encoded + 1, decoded32);'))
        rc, out, res = t.run(real, [py, 'tools/scan.py', '--card', 'C-02'])
        t.expect('scan rejects (card calls): C-02 through sqlite3.c\'s getVarint32 macro with encoded + 1',
                 rc != 0 and 'argument `encoded + 1` of getVarint32' in out and 'RESULT scan FAIL' in res, out)
        DECL_R2 = 'void harness_toyGet(void) {\n  int r;\n  u8 *q;'
        cc_ok = [
            ('&id and id + id arguments', G.replace('void harness_toyGet(void) {', 'void harness_toyGet(void) {\n  u64 k;\n  u8 b;').replace(
                '  toyGet(p);', '  toyGet(p);\n  toyGet(p + k);\n  toyGet(&b);')),
        ]
        for name, text in cc_ok:
            r = setup_get(t)
            t.write(r, 'proofs/C-90/harness.c', text)
            rc, out, res = t.run(r, [py, 'tools/scan.py'])
            t.expect('scan (card calls): %s passes' % name, rc == 0, out)
        cc_bad = [
            ('a constant offset in the call under proof', G.replace('  toyGet(p);', '  toyGet(p + 1);'), 'argument `p + 1` of toyGet'),
            ('a cast argument', G.replace('  toyGet(p);', '  toyGet((const u8 *)p);'), 'argument `(const u8 *)p` of toyGet'),
            ('x + y with x an integer', G.replace('void harness_toyGet(void) {', 'void harness_toyGet(void) {\n  u64 k;').replace(
                '  toyGet(p);', '  toyGet(k + p);'), 'argument `k + p` of toyGet: in x + y, x must be a data pointer'),
            ('x + y with y the same pointer', G.replace('  toyGet(p);', '  toyGet(p + p);'), 'argument `p + p` of toyGet: in x + y'),
            ('x + y with x a pointer declared after the call', G.replace('void harness_toyGet(void) {', 'void harness_toyGet(void) {\n  u64 k;').replace(
                '  toyGet(p);', '  toyGet(p);\n  u8 *q;\n  toyGet(q + k);'), 'argument `q + k` of toyGet: in x + y'),
            ('a conditional argument', G.replace('  toyGet(p);', '  toyGet(p ? p : p);'), 'argument `p ? p : p` of toyGet'),
            ('a narrowed second call after the call under proof', G.replace('void harness_toyGet(void) {', DECL_R2).replace(
                '  toyGet(p);', '  toyGet(p);\n  q = p;\n  r = toyGet(q - 1);'), 'argument `q - 1` of toyGet'),
            ('a card call inside an assert', G.replace('  toyGet(p);', '  toyGet(p);\n  __CPROVER_assert(toyGet(p + 1) >= 0, "x");'), 'argument `p + 1` of toyGet'),
            ('a call through a function pointer', G.replace('void harness_toyGet(void) {', 'void harness_toyGet(void) {\n  int (*f)(const u8 *);').replace(
                '  toyGet(p);', '  toyGet(p);\n  f = toyGet;\n  f(p + 1);'), 'toyGet is used other than as a call'),
            ('a helper that calls the card function', G.replace('void harness', 'static int via(const u8 *q) { return toyGet(q); }\nvoid harness').replace(
                '  toyGet(p);', '  toyGet(p);\n  via(p + 1);'), 'is named outside an entry function'),
        ]
        for name, text, needle in cc_bad:
            r = setup_get(t)
            t.write(r, 'proofs/C-90/harness.c', text)
            rc, out, res = t.run(r, [py, 'tools/scan.py'])
            t.expect('scan rejects (card calls): %s' % name, rc != 0 and needle in out and 'RESULT scan FAIL' in res, out)
        r = setup_get(t)
        TOYM = TOY + '#define TOYGET(A) toyGet(A)\n'
        t.write(r, 'upstream/sqlite3.c', TOYM)
        t.write(r, 'overlay/sqlite3.c', TOYM)
        t.write(r, 'pin.txt', 'upstream/sqlite3.c: %s\n' % hashlib.sha256(TOYM.encode()).hexdigest())
        t.write(r, 'proofs/C-90/harness.c', G.replace('  toyGet(p);', '  toyGet(p);\n  TOYGET(p + 1);'))
        rc, out, res = t.run(r, [py, 'tools/scan.py'])
        t.expect('scan rejects (card calls): a sqlite3.c macro that expands to the card function, with p + 1',
                 rc != 0 and 'argument `p + 1` of TOYGET' in out and 'RESULT scan FAIL' in res, out)
        r = setup_get(t)
        t.write(r, 'proofs/C-90/harness.c', G.replace('void harness', BOX).replace(
            'void harness_toyGet(void) {', 'void harness_toyGet(void) {\n  struct box *b;\n  int n;').replace(
            '  u8 *p = malloc(2);\n  __CPROVER_assume(p != 0);',
            '  __CPROVER_assume(n >= 0 && n < 4);\n  b = malloc(sizeof(struct box));\n  __CPROVER_assume(b != 0);\n  b->n = n;\n'
            '  u8 *p = (u8 *)malloc(2 + sizeof(u8 *));\n  __CPROVER_assume(p != 0);\n  b->z = p + 1;'))
        rc, out, res = t.run(r, [py, 'tools/scan.py'])
        t.expect('scan (follow-up 2): a SETUP with field stores, a cast malloc, pointer arithmetic and sizeof(T *) passes', rc == 0, out)
        # checkpoint 0, decision C2: files and symlinks
        r = setup_get(t)
        t.write(r, 'proofs/C-90/contracts/toyGet.h', '#error shadow\n')
        rc, out, res = t.run(r, [py, 'tools/scan.py'])
        t.expect('scan rejects (C2): a shadow header in proofs/C-90/contracts/', rc != 0 and 'may hold only harness.c' in out, out)
        r = setup_get(t)
        os.makedirs(os.path.join(t.base, 'outside'), exist_ok=True)
        t.write(t.base, 'outside/harness.c', G)
        os.remove(os.path.join(r, 'proofs/C-90/harness.c'))
        os.symlink(os.path.join(t.base, 'outside/harness.c'), os.path.join(r, 'proofs/C-90/harness.c'))
        rc, out, res = t.run(r, [py, 'tools/scan.py'])
        t.expect('scan rejects (C2): a symlinked harness.c', rc != 0 and 'symlink not allowed' in out, out)
        r = setup_get(t)
        t.write(r, 'overlay/contracts/toyGet.h', '/* shadow */\n')
        rc, out, res = t.run(r, [py, 'tools/scan.py'])
        t.expect('scan rejects (C2): an extra file in overlay/', rc != 0 and 'overlay/ may hold only' in out, out)
        r = setup_get(t)
        t.write(r, 'tests/repro/F-draft-C-90-1.c', 'int main(void){return 0;}\n')
        os.symlink('/etc/hostname', os.path.join(r, 'tests/repro/link.c'))
        rc, out, res = t.run(r, [py, 'tools/scan.py'])
        t.expect('scan rejects (C2): a symlink under tests/repro/', rc != 0 and 'tests/repro/link.c' in out, out)
        # checkpoint 0, decision C10
        r = setup_get(t)
        t.write(r, 'cards/C-90.md', card_md('C-90', ['toyGet', 'toyLen'], extra_may='proofs/contracts/toyGet.h, '))
        rc, out, res = t.run(r, [py, 'tools/scan.py'])
        t.expect('scan rejects (C10): a card function no proof\'s COVER names', rc != 0 and 'toyLen is a function of C-90' in out, out)
        # checkpoint 0, decision C4: preds.h may only gain predicates
        r = setup_get(t)
        t.write(r, 'proofs/include/preds.h', '#pragma once\nstatic int toyPos(int x) { return x > 0; }\n')
        subprocess.run(['git', '-C', r, 'add', '-A'], check=True)
        subprocess.run(['git', '-C', r, '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-qm', 'base'], check=True)
        t.write(r, 'proofs/include/preds.h', '#pragma once\nstatic int toyPos(int x) { return x > 0; }\nstatic int toyNeg(int x) { return x < 0; }\n')
        rc, out, res = t.run(r, [py, 'tools/scan.py', '--card', 'C-90', '--base', 'HEAD'])
        t.expect('scan (C4): preds.h gaining a predicate passes', rc == 0, out)
        t.write(r, 'proofs/include/preds.h', '#pragma once\nstatic int toyPos(int x) { return x >= 0; }\n')
        rc, out, res = t.run(r, [py, 'tools/scan.py', '--card', 'C-90', '--base', 'HEAD'])
        t.expect('scan rejects (C4): a predicate in preds.h changed', rc != 0 and 'may only gain predicates' in out, out)
        # checkpoint 0 follow-up 4: shared headers #define only their include guard
        r = setup_get(t)
        PG = '#ifndef PREDS_H\n#define PREDS_H\nstatic int toyPos(int x) { return x > 0; }\n#endif\n'
        t.write(r, 'proofs/include/preds.h', PG)
        subprocess.run(['git', '-C', r, 'add', '-A'], check=True)
        subprocess.run(['git', '-C', r, '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-qm', 'base'], check=True)
        rc, out, res = t.run(r, [py, 'tools/scan.py', '--card', 'C-90', '--base', 'HEAD'])
        t.expect('scan (follow-up 4): preds.h with only its include guard passes', rc == 0, out)
        t.write(r, 'proofs/include/preds.h', PG.replace('#endif', 'static int toyNeg(int x) { return x < 0; }\n#endif'))
        rc, out, res = t.run(r, [py, 'tools/scan.py', '--card', 'C-90', '--base', 'HEAD'])
        t.expect('scan (follow-up 4): guarded preds.h gaining a predicate passes', rc == 0, out)
        for name, text in [
                ('a macro redefining an existing predicate', PG.replace('#endif', '#define toyPos(x) 1\n#endif')),
                ('an #undef and redefinition of an existing predicate', PG.replace('#endif', '#undef toyPos\n#define toyPos(x) ((x) >= 0)\n#endif')),
                ('an object-like macro naming a SQLite function', PG.replace('#endif', '#define toyGet toyLen\n#endif'))]:
            t.write(r, 'proofs/include/preds.h', text)
            rc, out, res = t.run(r, [py, 'tools/scan.py', '--card', 'C-90', '--base', 'HEAD'])
            t.expect('scan --base rejects (follow-up 4): %s in preds.h' % name,
                     rc != 0 and 'may #define only its include guard' in out and 'RESULT scan FAIL' in res, out)
        for name, rel, text, needle in [
                ('a macro in a contract', 'proofs/contracts/toyGet.h',
                 CONTRACT_GET.replace('FOOT', '2') + '#define toyLen(n) 1\n', 'may #define only its include guard'),
                ('a #define in proofs/spec/', 'proofs/spec/toy.h', '#define TOY_MAX 9\n', 'may #define only its include guard'),
                ('an include guard named after a SQLite function', 'proofs/include/preds.h',
                 '#ifndef toyLen\n#define toyLen\n#endif\n', 'include guard toyLen')]:
            r = setup_get(t)
            t.write(r, rel, text)
            rc, out, res = t.run(r, [py, 'tools/scan.py'])
            t.expect('scan rejects (follow-up 4): %s' % name, rc != 0 and needle in out, out)
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
        r = setup_get(t)
        rc, out, res = t.run(r, [py, 'tools/lock.py', 'check'])
        t.expect('lock (C7): before the freeze, no proof.lock passes', rc == 0 and 'PASS 0 files (no proof.lock)' in res, out)
        t.write(r, 'GOAL.md', 'x\n')
        subprocess.run(['git', '-C', r, 'add', '-A'], check=True)
        t.run(r, [py, 'tools/lock.py', 'write'])
        subprocess.run(['git', '-C', r, 'add', '-A'], check=True)
        subprocess.run(['git', '-C', r, '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-qm', 'freeze'], check=True)
        os.remove(os.path.join(r, 'proof.lock'))
        rc, out, res = t.run(r, [py, 'tools/lock.py', 'check'])
        t.expect('lock (C7): proof.lock deleted after the freeze commit fails', rc != 0 and 'missing after the freeze' in res, out)
        subprocess.run(['git', '-C', r, '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-qam', 'drop the lock'], check=True)
        rc, out, res = t.run(r, [py, 'tools/lock.py', 'check'])
        t.expect('lock (C7): ... and still fails once its deletion is committed', rc != 0 and 'FAIL' in res, out)
        r = setup_get(t)
        t.write(r, 'HANDOFF.md', '# handoff\n')
        rc, out, res = t.run(r, [py, 'tools/lock.py', 'check'])
        t.expect('lock (C7): no proof.lock while HANDOFF.md exists fails', rc != 0 and 'HANDOFF.md' in out, out)

    # ---- includes (checkpoint 0, decision C2): the gate's check on the preprocessed harness
    if want('includes'):
        r = setup_get(t)
        rc, out, res = t.run(r, [py, 'tools/prove.py', 'includes', '--card-dir', 'proofs/C-90'])
        t.expect('includes: a harness that includes the overlay, proofs/contracts/ and system headers passes on every configuration',
                 rc == 0 and 'RESULT includes C-90 all PASS' in res, out)
        t.write(r, 'proofs/C-90/contracts/toyGet.h', CONTRACT_GET.replace('FOOT', '1'))
        rc, out, res = t.run(r, [py, 'tools/prove.py', 'includes', '--card-dir', 'proofs/C-90', '--config', 'lp64-le'])
        t.expect('includes: a shadow proofs/C-90/contracts/toyGet.h (quoted includes resolve there first) fails',
                 rc != 0 and 'proofs/C-90/contracts/toyGet.h' in out and 'FAIL' in res, out)
        r = setup_get(t)
        t.write(r, 'proofs/include/contracts/toyGet.h', CONTRACT_GET.replace('FOOT', '1'))
        t.write(r, 'proofs/C-90/harness.c', HARNESS_GET.replace('FOOT', '2').replace('#include "contracts/toyGet.h"', '#include "contracts/toyGet.h"\n#include "preds.h"'))
        t.write(r, 'proofs/include/preds.h', '#include "../../upstream/sqlite3.c"\n')
        rc, out, res = t.run(r, [py, 'tools/prove.py', 'includes', '--card-dir', 'proofs/C-90', '--config', 'lp64-le'])
        t.expect('includes: a header that pulls in upstream/ or a nested proofs/include/contracts/ file fails',
                 rc != 0 and 'upstream/sqlite3.c' in out and 'proofs/include/contracts/toyGet.h' in out, out)

    # ---- gate (checkpoint 0, decision C4): a preds.h change reruns every card that includes it
    if want('gate'):
        # follow-up item 1: card Makefiles are parsed by load_card, never evaluated by make
        r = setup_get(t)
        marker = os.path.join(r, 'make-ran')
        t.write(r, 'proofs/C-90/Makefile', MK_GET + 'prove:\n\t@touch %s\ncoverage:\n\t@touch %s\n' % (marker, marker))
        rc, out, res = t.run(r, [py, 'tools/gate.py', 'gate', '--card', 'C-90'])
        t.expect('gate: a card Makefile with a rule load_card rejects fails the gate, and make never runs it (no marker)',
                 rc != 0 and 'FAIL' in res and 'rejected by load_card' in out and 'prove C-90' in res
                 and not os.path.exists(marker), out + ('\nMARKER EXISTS' if os.path.exists(marker) else ''))
        rc, out, res = t.run(r, [py, 'tools/gate.py', 'prove'])
        t.expect('gate: make prove skips the rejected card Makefile too (no marker)',
                 rc != 0 and 'rejected by load_card' in out and not os.path.exists(marker), out)
        r = setup_get(t)
        t.write(r, 'cards/C-91.md', card_md('C-91', ['toySum']))
        t.write(r, 'proofs/C-91/harness.c', HARNESS_SUM.replace('#include <stdlib.h>', '#include <stdlib.h>\n#include "preds.h"'))
        t.write(r, 'proofs/C-91/Makefile', MK_SUM)
        t.write(r, 'overlay/sqlite3.c', TOY.replace('  while( i<n ){', '  while( i<n )' + SUM_SPAN_GOOD + '{'))
        t.write(r, 'proofs/include/preds.h', '#pragma once\nstatic int toyPos(int x) { return x > 0; }\n')
        t.write(r, 'Makefile', open(os.path.join(REPO, 'Makefile')).read())
        subprocess.run(['git', '-C', r, 'add', '-A'], check=True)
        subprocess.run(['git', '-C', r, '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-qm', 'base'], check=True)
        rc, out, res = t.run(r, [py, 'tools/gate.py', 'gate', '--card', 'C-90', '--base', 'HEAD'])
        t.expect('gate: preds.h unchanged: make gate CARD=C-90 runs C-90 only, with its includes step',
                 'gate: cards to run: C-90\n' in out and 'includes C-90' in out, out)
        t.write(r, 'proofs/include/preds.h', '#pragma once\nstatic int toyPos(int x) { return x > 0; }\nstatic int toyNeg(int x) { return x < 0; }\n')
        rc, out, res = t.run(r, [py, 'tools/gate.py', 'gate', '--card', 'C-90', '--base', 'HEAD'])
        t.expect('gate: preds.h changed: make gate CARD=C-90 also reruns C-91, whose harness includes preds.h',
                 'also running the cards that include it: C-91' in out and 'gate: cards to run: C-90, C-91' in out
                 and 'prove C-91' in out, out)

    # ---- regression tests for the fixes the pilot exposed (checkpoint 0, decision C9)
    if want('regress'):
        r = t.fresh()
        code = ('import sys; sys.path.insert(0, "tools"); import cards\n'
                'c = {"C-01": cards.Card("C-01", open("cards/C-01.md").read()), "C-02": cards.Card("C-02", open("cards/C-02.md").read()),'
                ' "C-03": cards.Card("C-03", open("cards/C-03.md").read())}\n'
                'print("C-01", cards.callers_of(c, "C-01")); print("C-02", cards.callers_of(c, "C-02")); print("C-03", cards.callers_of(c, "C-03"))\n')
        t.write(r, 'cards/C-01.md', card_md('C-01', ['toyLen', 'toySum']))
        t.write(r, 'cards/C-02.md', card_md('C-02', ['toyLen', 'toySum', 'toyGet']))
        t.write(r, 'cards/C-03.md', card_md('C-03', ['toyDead'], depends='C-02'))
        rc, out, res = t.run(r, [py, '-c', code])
        t.expect('cards.callers_of: two cards sharing functions name each other, never themselves (pilot: "C-02, C-02")',
                 "C-01 ['C-02', 'C-03']" in out and "C-02 ['C-01', 'C-03']" in out and 'C-03 []' in out, out)
        r = setup_get(t)
        os.makedirs(os.path.join(r, 'evidence', 'results'))
        old = {'card': 'C-90', 'mutants': [{'verdict': 'KILLED', 'mutant': {'id': 'M-001'}, 'detail': 'by C-90/get'}],
               'prove_summary': [], 'coverage_summary': [],
               'provenance': {'mutants': {'commit': 'aaaa', 'gate_log': 'evidence/gate/C-90-r1.log'}}}
        import json as _json
        t.write(r, 'evidence/results/C-90.json', _json.dumps(old))
        t.write(r, 'proofs/C-90/build/prove-summary.json', _json.dumps([{'card': 'C-90', 'proof': 'get', 'config': 'lp64-le',
                'status': 'PASS', 'seconds': 1, 'cbmc_seconds': 1, 'properties': 7, 'failed': 0}]))
        t.write(r, 'proofs/C-90/build/coverage-summary.json', _json.dumps([]))
        code = ('import sys, json; sys.path.insert(0, "tools"); import campaign\n'
                'class P: state = %r\n'
                'campaign.collect_results(P(), %r, ["C-90"], 2, None, commit="bbbb", gate_log="evidence/gate/C-91-r1.log", merged="caller gate")\n'
                'd = json.load(open("evidence/results/C-90.json")); print(json.dumps(d, sort_keys=True))\n' % (os.path.join(r, 'st'), r))
        os.makedirs(os.path.join(r, 'st'))
        rc, out, res = t.run(r, [py, '-c', code])
        rec = None
        try:
            rec = _json.loads(out.strip().split('\n')[-1])
        except ValueError:
            pass
        csvt = open(os.path.join(r, 'results.csv')).read() if os.path.exists(os.path.join(r, 'results.csv')) else ''
        t.expect('collect_results: a caller\'s gate (no mutants.json) keeps the card\'s mutant results, and each field records '
                 'its own commit and gate log (pilot: C-02 lost its mutants)',
                 rec and len(rec.get('mutants') or []) == 1 and rec['provenance']['mutants']['commit'] == 'aaaa'
                 and rec['provenance']['prove_summary'] == {'commit': 'bbbb', 'gate_log': 'evidence/gate/C-91-r1.log', 'gate': 'caller gate'}
                 and ',1,1,0,' in csvt and 'bbbb evidence/gate/C-91-r1.log' in csvt and 'aaaa evidence/gate/C-90-r1.log' in csvt, out + csvt)

    # ---- probe (checkpoint 0, decision B): lp64-be's plain char is unsigned, as on PowerPC
    if want('probe'):
        r = t.fresh()
        rc, out, res = t.run(r, [py, 'tools/prove.py', 'probe', '--config', 'lp64-be', '--overlay', os.path.join(REPO, 'overlay')])
        t.expect('probe: lp64-be with -funsigned-char passes, char signedness included',
                 rc == 0 and 'plain char signedness (CBMC): SUCCESS' in out and 'RESULT probe lp64-be PASS' in out, out)
        t.write(r, 'proofs/CONFIGS', open(os.path.join(REPO, 'proofs', 'CONFIGS')).read().replace(' -funsigned-char', ''))
        rc, out, res = t.run(r, [py, 'tools/prove.py', 'probe', '--config', 'lp64-be', '--overlay', os.path.join(REPO, 'overlay')])
        t.expect('probe: lp64-be without -funsigned-char (x86\'s signed char) fails', rc != 0 and 'RESULT probe lp64-be FAIL' in out, out)
        rc, out, res = t.run(r, [py, 'tools/scan.py'])
        t.write(r, 'proofs/CONFIGS', open(os.path.join(REPO, 'proofs', 'CONFIGS')).read().replace('-funsigned-char', '-fsigned-char'))
        rc, out, res = t.run(r, [py, 'tools/scan.py'])
        t.expect('scan: CONFIGS may carry -funsigned-char but not another char flag', rc != 0 and '-fsigned-char' in out and '-funsigned-char' not in out.replace('-fsigned', ''), out)

    print('RESULT tool-tests %s %d/%d' % ('PASS' if t.passed == t.total else 'FAIL', t.passed, t.total))
    if not a.keep:
        shutil.rmtree(t.base, ignore_errors=True)
    else:
        print('kept %s' % t.base)
    return 0 if t.passed == t.total else 1


if __name__ == '__main__':
    sys.exit(main())
