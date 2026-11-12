#!/usr/bin/env python3
"""Tests for check_overlay.py, prove.py, scan.py, mutate.py and lock.py (GOAL.md §1.9).

Builds a scratch root that copies tools/ and proofs/{CHECKS,CONFIGS,Makefile.common,include} and
puts a toy sqlite3.c (toy functions, not SQLite) in upstream/ and overlay/, with toy cards and
harnesses. Each case states what the tool must say. Run: tools/tests/test_tools.py [--keep] [-k NAME]
Ends with: RESULT tool-tests PASS|FAIL <passed>/<total>
"""
import argparse
import csv
import hashlib
import io
import json
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


# checkpoint 1 fix 1: os_unix keeps close, read and fcntl in a table of function pointers (aSyscall); DFCC aborts
# (casting_replace_symbol.cpp invariant) on any goto program that keeps such a table
SYSCALL_TOY = r'''/* toy sqlite3.c for tool tests: not SQLite */
#include <unistd.h>
typedef void (*syscall_ptr)(void);
static struct { const char *zName; syscall_ptr pCurrent; } aSyscall[] = {
  { "close", (syscall_ptr)close },
  { "read",  (syscall_ptr)read },
};
static int toyClose(int fd){
  return ((int(*)(int))aSyscall[0].pCurrent)(fd);
}
static int toyMaybeClose(int x){
  if( x>100 ) return toyClose(x);
  return 0;
}
static int toyOuter(int x){
  if( x>100 ) x = 100;
  return toyMaybeClose(x);
}
'''

# checkpoint 1: tools/campaign.py's session guards (Q2, Q4), round limit (D4) and repro runner (fix 2), called from a
# scratch root's copy of tools/; run by the 'campaign' tool tests
CAMPAIGN_CHECK_NAMES = {
    'codex-bwrap': 'a builder (codex) session starts inside bwrap, and a codex command without it is refused (Q2)',
    'codex-home-hidden': 'a codex command that leaves $HOME or /mnt visible, or $HOME writable, is refused (Q2, Q4)',
    'codex-rules-hidden': 'a codex command that shows ~/.codex/rules or lets codex write ~/.codex/skills is refused (Q2)',
    'codex-agents-md': 'a codex session is refused while ~/.codex/AGENTS.md exists (Q2)',
    'claude-home-hidden': 'a reviewer (claude) command that leaves $HOME or /mnt visible, or $HOME writable, is refused (Q4)',
    'claude-no-skills-mcp': 'a claude command without --disable-slash-commands or --strict-mcp-config is refused (Q2)',
    'claude-keeps-dot-claude': 'a claude command without its own tmpfs over ~/.claude is refused (Q4 keeps it)',
    'd4-round-7': 'a seventh builder round is never started: the card goes to triage (D4)',
    'repro-sandboxed': 'campaign.py builds and runs a repro itself, sandboxed: no $HOME, no network (fix 2)',
}
CAMPAIGN_CHECKS = r'''
import os, sys
os.makedirs('@HOME@/.codex/skills', exist_ok=True)
os.environ['HOME'] = '@HOME@'
sys.path.insert(0, '@ROOT@/tools')
import campaign as C
p = C.P('@ROOT@')
home = os.path.expanduser('~')
def res(name, ok, why=''):
    print('%s %s: %s' % ('PASS' if ok else 'FAIL', name, why))
def filled(vendor, key='start'):
    return C.fill(C.SESSION_COMMANDS[vendor][key], dir=p.wt + '/C-01', model='m', effort='high', home=home, wtroot=p.wt,
                  repo=p.primary, config=p.state + '/claude-config/J0001-x', session='S')
def drop(a, k, v):
    return [x for i, x in enumerate(a) if not (x == v and i and a[i - 1] == k) and not (x == k and i + 1 < len(a) and a[i + 1] == v)]
def probs(vendor, a):
    return C.command_problems(vendor, a, p.wt + '/C-01', p)
try:
    a = filled('codex')
    res('codex-bwrap', a[0] == 'bwrap' and not probs('codex', a) and any('bwrap' in x for x in probs('codex', a[a.index('codex'):])),
        str(probs('codex', a))[:300])
    ok = all(probs('codex', b) for b in (drop(a, '--tmpfs', home), drop(a, '--tmpfs', '/mnt'), drop(a, '--remount-ro', home)))
    res('codex-home-hidden', ok)
    res('codex-rules-hidden', probs('codex', drop(a, '--tmpfs', home + '/.codex/rules')) and
        probs('codex', drop(a, '--remount-ro', home + '/.codex/skills')))
    open(home + '/.codex/AGENTS.md', 'w').write('x')
    res('codex-agents-md', any('AGENTS.md' in x for x in probs('codex', a)))
    os.remove(home + '/.codex/AGENTS.md')
except Exception as e:
    for n in ('codex-bwrap', 'codex-home-hidden', 'codex-rules-hidden', 'codex-agents-md'):
        res(n, False, '%s: %s' % (type(e).__name__, e))
try:
    a = filled('claude')
    ok = not probs('claude', a) and all(probs('claude', b) for b in (drop(a, '--tmpfs', home), drop(a, '--tmpfs', '/mnt'),
                                                                     drop(a, '--remount-ro', home)))
    res('claude-home-hidden', ok, str(probs('claude', a))[:300])
    res('claude-no-skills-mcp', probs('claude', [x for x in a if x != '--disable-slash-commands']) and
        probs('claude', [x for x in a if x != '--strict-mcp-config']))
    res('claude-keeps-dot-claude', probs('claude', drop(a, '--tmpfs', home + '/.claude')))
except Exception as e:
    for n in ('claude-home-hidden', 'claude-no-skills-mcp', 'claude-keeps-dot-claude'):
        res(n, False, '%s: %s' % (type(e).__name__, e))
try:
    class St:
        d = {'triage_seq': 0, 'jobs': {}, 'job_seq': 0}
        def journal(self, *a, **k):
            pass
    import cards as cardlib
    text = ('# C-01: f\n- Property: P1\n- Functions: f (upstream/sqlite3.c:1)\n- In-scope callees, with approved contracts: none\n'
            '- Boundary callees, with ledger entries: none\n- In-scope callers, whose call sites must satisfy the requires: none\n'
            '- Depends on: none\n- May change: ' + ', '.join('reports/C-01-b%d.md' % k for k in range(1, 8)) +
            '\n- Cap: builder 5M; reviewer half that. Tier: standard\n- Notes: x\n')
    c = {'id': 'C-01', 'state': 'ready', 'round': 6, 'epoch_rounds': 0, 'interruptions': 0, 'history': [], 'tokens_builder': 0,
         'job': None, 'notes': []}
    started = []
    C.spawn_runner = lambda *a, **k: started.append(a)
    C.Campaign(p).start_builder_round(St(), c, cardlib.Card('C-01', text), C.load_sessions('@ROOT@'))
    res('d4-round-7', c['state'] == 'triage' and 'round 7' in (c.get('reason') or '') and not started, str(c.get('reason')))
except Exception as e:
    res('d4-round-7', False, '%s: %s' % (type(e).__name__, e))
try:
    d = '@ROOT@/repro'
    os.makedirs(d + '/up', exist_ok=True)
    os.makedirs(d + '/wt/tests/repro', exist_ok=True)
    open(d + '/up/sqlite3.c', 'w').write('#include <stdio.h>\n#include <stdlib.h>\n')
    open(home + '/secret', 'w').write('s')
    open(d + '/wt/tests/repro/F-draft-C-01-1.c', 'w').write(
        '#include "sqlite3.c"\n#include <sys/socket.h>\n#include <netinet/in.h>\n#include <arpa/inet.h>\n'
        'int main(void){ printf("home:%s\\n", fopen("' + home + '/secret", "r") ? "yes" : "no");\n'
        ' int s = socket(AF_INET, SOCK_STREAM, 0); struct sockaddr_in a = {0}; a.sin_family = AF_INET; a.sin_port = htons(443);\n'
        ' inet_pton(AF_INET, "1.1.1.1", &a.sin_addr);\n'
        ' printf("net:%s\\n", (s >= 0 && connect(s, (struct sockaddr*)&a, sizeof a) == 0) ? "yes" : "no"); return 0; }\n')
    rr = C.run_repros(d + '/wt', 'C-01', d + '/up', d + '/out')
    txt = open(d + '/out/F-draft-C-01-1.txt').read()
    res('repro-sandboxed', 'build exit 0' in rr.get('tests/repro/F-draft-C-01-1.c', '') and 'home:no' in txt and 'net:no' in txt, txt[-600:])
except Exception as e:
    res('repro-sandboxed', False, '%s: %s' % (type(e).__name__, e))
'''

def line_of(text, needle):
    for i, ln in enumerate(text.split('\n'), 1):
        if needle in ln:
            return i
    raise KeyError(needle)


def card_md(cid, fns, depends='none', extra_may='', src=None):
    fl = ', '.join('%s (upstream/sqlite3.c:%d)' % (f, line_of(src or TOY, ' %s(' % f)) for f in fns)
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


# T-006 (Zach, 2026-11-10, evidence/approvals/T-006-dfcc-loop-pointer/): CBMC's legacy contracts, opted into per proof.
# The validation toys are in tools/tests/legacy/: toys.c (the "upstream"), heads/<fn>.h (contract_<fn>), harness.c.
LEGACY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'legacy')
# proof: (entry, enforced, replaced, loop contracts, the check its bad variant must fail by; None: no bad variant)
LEGACY_PROOFS = [
    ('forget', 'h_forget', 't_forget', ['keep'], False, 'Check ensures clause'),
    ('callee_frame', 'h_callee_frame', 't_callee_frame', ['reset'], True, 'other->flags (assigned by the contract of reset) is assignable'),
    ('alias_frame', 'h_alias_frame', 't_alias_frame', [], True, 'Check that q->flags is assignable'),
    ('invariant', 'h_invariant', 't_invariant', [], True, 'Check that loop invariant is preserved'),
    ('decreases', 'h_decreases', 't_decreases', [], True, 'Check decreases clause on loop iteration'),
    ('after', 'h_after', 't_after', [], True, 'Check ensures clause'),
    ('oob', 'h_oob', 't_oob', [], True, 'pointer outside object bounds'),
    ('callee_requires', 'h_callee_requires', 't_callee_requires', ['reset'], False, 'Check requires clause of reset'),
    ('flex', 'h_flex', 't_flex', [], False, 'dynamic object upper bound'),
    ('fresh', 'h_fresh', 't_fresh', ['two'], False, 'Check requires clause of two'),
    ('two', 'h_two', 'two', [], False, None),
    ('carried', 'h_carried', 't_carried', ['reset'], True, None),
]


def legacy_text(rel):
    with open(os.path.join(LEGACY_DIR, rel)) as f:
        return f.read()


def legacy_makefile(card, proofs, contracts='legacy'):
    out = ['CARD := %s' % card, 'PROOFS := ' + ' '.join(p[0] for p in proofs)]
    for name, entry, enf, rep, loops, _ in proofs:
        out += ['%s_ENTRY := %s' % (name, entry), '%s_ENFORCE := %s/contract_%s' % (name, enf, enf),
                '%s_CONTRACTS := %s' % (name, contracts)]
        if rep:
            out.append('%s_REPLACE := ' % name + ' '.join('%s/contract_%s' % (r, r) for r in rep))
        if loops:
            out.append('%s_LOOPS := contracts' % name)
    return '\n'.join(out + ['include ../Makefile.common']) + '\n'


def legacy_repo(t, card='C-15', proofs=None):
    proofs = LEGACY_PROOFS if proofs is None else proofs
    toys = legacy_text('toys.c')
    r = t.fresh()
    t.write(r, 'upstream/sqlite3.c', toys)
    t.write(r, 'overlay/sqlite3.c', toys)
    t.write(r, 'overlay-bad/sqlite3.c', ''.join('#define VARIANT_%s\n' % p[0] for p in LEGACY_PROOFS) + toys)
    heads = sorted(n[:-2] for n in os.listdir(os.path.join(LEGACY_DIR, 'heads')))
    for fn in heads:
        t.write(r, 'proofs/contracts/%s.h' % fn, legacy_text('heads/%s.h' % fn))
    inc = ''.join('#include "contracts/%s.h"\n' % fn for fn in heads)
    t.write(r, 'proofs/%s/harness.c' % card, '#include "sqlite3.c"\n' + inc + legacy_text('harness.c'))
    t.write(r, 'cards/%s.md' % card, card_md(card, sorted(set(p[2] for p in proofs)), src=toys))
    t.write(r, 'proofs/%s/Makefile' % card, legacy_makefile(card, proofs))
    return r


def legacy_failures(r, card, name):
    import json as _json
    j = os.path.join(r, 'proofs', card, 'build', 'lp64-le', name + '.json')
    return [f.get('desc', '') for f in (_json.load(open(j)).get('failures') or [])] if os.path.exists(j) else []

# B2 (Zach, 2026-11-10, evidence/approvals/B2-memcmp-contract/): memcmp's boundary contract, clause guards, kept bodies
B2_TOY = r"""#include <stdlib.h>
#include <string.h>
typedef struct Cell { unsigned flags; void *payload; } Cell;
int cmpneg(const unsigned char *a, const unsigned char *b, size_t n) {
#ifdef BAD
  int rc = memcmp(a, b, n + 1);
#else
  int rc = memcmp(a, b, n);
#endif
  return -rc;
}
void bump(Cell *p) { p->flags++; }
void walk(Cell *a, Cell *other, unsigned n) {
  unsigned i = 0;
  while (i < n)
    __CPROVER_assigns(i, __CPROVER_object_whole(a)
#ifndef BAD
                      , other->flags
#endif
                      )
    __CPROVER_loop_invariant(i <= n)
    __CPROVER_decreases(n - i)
  { bump(other); i++; }
}
"""
B2_MEMCMP_H = open(os.path.join(REPO, 'proofs', 'contracts', 'memcmp.h')).read()
B2_HEADS = {
    'cmpneg': 'int contract_cmpneg(const unsigned char *a, const unsigned char *b, size_t n)\n'
              '  __CPROVER_requires(n <= 1000000 && __CPROVER_r_ok(a, n + 1) && __CPROVER_r_ok(b, n))\n'
              '  __CPROVER_assigns()\n'
              '  __CPROVER_ensures(-255 <= __CPROVER_return_value && __CPROVER_return_value <= 255);\n',
    'walk': 'void contract_walk(Cell *a, Cell *other, unsigned n)\n'
            '  __CPROVER_requires(n <= 4 && __CPROVER_w_ok(a, 4 * sizeof(Cell)) && __CPROVER_w_ok(other, sizeof(Cell)))\n'
            '  __CPROVER_assigns(__CPROVER_object_whole(a), other->flags);\n',
}
B2_HARNESS = ('#include "sqlite3.c"\n#include "contracts/memcmp.h"\n#include "contracts/cmpneg.h"\n#include "contracts/walk.h"\n'
              'void h_cmp(void) { size_t n; __CPROVER_assume(n <= 1000000);\n'
              '  unsigned char *a = malloc(n + 1), *b = malloc(n); __CPROVER_assume(a && b); cmpneg(a, b, n); }\n'
              'void h_walk(void) { unsigned n; Cell *a = malloc(4 * sizeof(Cell)), *o = malloc(sizeof(Cell));\n'
              '  __CPROVER_assume(a && o); walk(a, o, n); }\n')


def b2_repo(t, card, contracts):
    r = t.fresh()
    t.write(r, 'upstream/sqlite3.c', B2_TOY)
    t.write(r, 'overlay/sqlite3.c', B2_TOY)
    t.write(r, 'overlay-bad/sqlite3.c', '#define BAD\n' + B2_TOY)
    t.write(r, 'proofs/contracts/memcmp.h', B2_MEMCMP_H)
    for fn, text in B2_HEADS.items():
        t.write(r, 'proofs/contracts/%s.h' % fn, text)
    t.write(r, 'proofs/%s/harness.c' % card, B2_HARNESS)
    t.write(r, 'cards/%s.md' % card, card_md(card, ['cmpneg', 'walk'], src=B2_TOY))
    lines = ['CARD := %s' % card, 'PROOFS := cmp walk',
             'cmp_ENTRY := h_cmp', 'cmp_ENFORCE := cmpneg/contract_cmpneg', 'cmp_REPLACE := memcmp/contract_memcmp',
             'walk_ENTRY := h_walk', 'walk_ENFORCE := walk/contract_walk', 'walk_LOOPS := contracts']
    if contracts == 'legacy':
        lines += ['cmp_CONTRACTS := legacy', 'walk_CONTRACTS := legacy']
    t.write(r, 'proofs/%s/Makefile' % card, '\n'.join(lines + ['include ../Makefile.common']) + '\n')
    return r

# Bounded proofs (Zach, 2026-11-11, evidence/approvals/C-15-bounded/): prove.py BOUNDS, scan rule 16 with its two
# allocation shapes (start-exact and end-exact), results.py's Bounds and Assigns columns, tools/native.py and the gate's
# native step; and T-015's legacy frame check
BOUNDS_TOY = TOY + r'''typedef struct Rec { int n; u8 *z; } Rec;
static int toyRec(Rec *r){
  int s = 0, i;
  for(i=0; i<r->n; i++) s += r->z[i];
  return s;
}
static int toyPeek(const u8 *p, int n){
  int s = 0, i;
  for(i=0; i<n; i++) s += p[i];
#ifdef PLANT_UNDER
  if( n>0 && n<8 ) s += p[-1];
#endif
#ifdef PLANT_OVER
  if( n>0 && n<8 ) s += p[n];
#endif
  return s;
}
'''
SUM_ENTRY = r'''void harness_NAME(void) {
  int n;
  size_t off;
  u8 *buf, *p;
  /* SETUP */
  __CPROVER_assume(n >= 0);
  __CPROVER_assume(n <= 64);
  off = OFFSET;
  buf = malloc(64);
  __CPROVER_assume(buf != 0);
  p = buf + off;
  /* END SETUP */
  toySum(p, n);
}
'''
REC_ENTRY = r'''void harness_toyRec(void) {
  int m;
  Rec *r;
  u8 *z;
  /* SETUP */
  __CPROVER_assume(m >= 0);
  r = malloc(sizeof(Rec));
  z = malloc(m);
  __CPROVER_assume(r != 0 && z != 0);
  r->n = m;
  r->z = z;
  /* END SETUP */
  toyRec(r);
}
'''
BOUNDS_HARNESS = ('#include "sqlite3.c"\n#include <stdlib.h>\n'
                  + SUM_ENTRY.replace('NAME', 'toySum').replace('OFFSET', '(64) - (n)')
                  + SUM_ENTRY.replace('NAME', 'toySumStart').replace('OFFSET', '0') + REC_ENTRY)
UNB_HARNESS = r'''#include "sqlite3.c"
#include <stdlib.h>
void harness_toySum(void) {
  int n;
  u8 *p;
  /* SETUP */
  __CPROVER_assume(n >= 0);
  p = malloc(n);
  __CPROVER_assume(p != 0);
  /* END SETUP */
  toySum(p, n);
}
''' + REC_ENTRY
REC_MK = 'rec_ENTRY := harness_toyRec\nrec_LOOPS := unwind\nrec_UNWINDSET := toyRec.0:3\nrec_COVER := toyRec\n'
BOUNDS_MK = ('CARD := C-92\nPROOFS := sum sum_start rec\n'
             'sum_ENTRY := harness_toySum\nsum_LOOPS := unwind\nsum_UNWINDSET := toySum.0:65\nsum_COVER := toySum\n'
             'sum_start_ENTRY := harness_toySumStart\nsum_start_LOOPS := unwind\nsum_start_UNWINDSET := toySum.0:65\n'
             'sum_start_COVER := toySum\n' + REC_MK + 'include ../Makefile.common\n')
UNB_MK = ('CARD := C-92\nPROOFS := sum rec\nsum_ENTRY := harness_toySum\nsum_LOOPS := unwind\nsum_UNWINDSET := toySum.0:65\n'
          'sum_COVER := toySum\n' + REC_MK + 'include ../Makefile.common\n')


def bspec(k=64, size='64', extent='n', tails='()'):
    one = lambda exact: "{'bounds': (('n', %d, 'n'),), 'exact': '%s', 'buffers': (('buf', '%s', 'off', '%s', %s),)}" % (  # noqa: E731
        k, exact, size, extent, tails)
    return "{'sum': %s, 'sum_start': %s}" % (one('end'), one('start'))


BOUNDS_DEFAULT = "{'C-92': %s}" % bspec()
BOUNDS_LINES = ['C-92 sum: bounded: n <= 64', 'C-92 sum_start: bounded: n <= 64']
BOUNDS_LINE = BOUNDS_LINES[0]
BOUNDS_NATIVE = r'''#include "sqlite3.c"
#include <stdlib.h>
int main(void) {
  int n, i;
  for (n = 65; n < 2048; n++) {
    u8 *p = malloc(n);
    for (i = 0; i < n; i++) p[i] = (u8)i;
    if (toySum(p, n) < 0) return 3;
    free(p);
  }
  return 0;
}
'''


def set_bounds(t, r, bounds):
    pp = os.path.join(r, 'tools', 'prove.py')
    text = open(pp).read()
    new, k = re.subn(r'\nBOUNDS = \{.*?\n\}\n', '\nBOUNDS = %s\n' % bounds.replace('\\', '\\\\'), text, count=1, flags=re.S)
    assert k == 1
    t.write(r, 'tools/prove.py', new)


def bounds_repo(t, bounds=BOUNDS_DEFAULT, harness=BOUNDS_HARNESS, mk=BOUNDS_MK):
    r = t.fresh()
    t.write(r, 'upstream/sqlite3.c', BOUNDS_TOY)
    t.write(r, 'overlay/sqlite3.c', BOUNDS_TOY)
    t.write(r, 'pin.txt', 'upstream/sqlite3.c: %s\n' % hashlib.sha256(BOUNDS_TOY.encode()).hexdigest())
    set_bounds(t, r, bounds)
    t.write(r, 'cards/C-92.md', card_md('C-92', ['toySum', 'toyRec'], src=BOUNDS_TOY).replace(
        '- Notes: toy\n', '- Notes: toy. %s\n' % '; '.join(BOUNDS_LINES)))
    t.write(r, 'PROPERTIES.md', '# PROPERTIES\n\n## Bounded proofs\n\n' + ''.join('- %s\n' % x for x in BOUNDS_LINES))
    t.write(r, 'proofs/C-92/harness.c', harness)
    t.write(r, 'proofs/C-92/Makefile', mk)
    t.write(r, 'tests/bounded/C-92-1.c', BOUNDS_NATIVE)
    return r


PEEK_HARNESS = '#include "sqlite3.c"\n#include <stdlib.h>\n' + ''.join(
    SUM_ENTRY.replace('NAME', name).replace('OFFSET', off).replace('64', '8').replace('toySum(p, n)', 'toyPeek(p, n)')
    for name, off in (('toyPeek', '(8) - (n)'), ('toyPeekStart', '0')))
PEEK_MK = ('CARD := C-93\nPROOFS := peek peek_start\n'
           'peek_ENTRY := harness_toyPeek\npeek_LOOPS := unwind\npeek_UNWINDSET := toyPeek.0:9\npeek_COVER := toyPeek\n'
           'peek_start_ENTRY := harness_toyPeekStart\npeek_start_LOOPS := unwind\npeek_start_UNWINDSET := toyPeek.0:9\n'
           'peek_start_COVER := toyPeek\ninclude ../Makefile.common\n')


def peek_repo(t):
    """A bounded toy, end-exact and start-exact, whose function may carry a planted underread or overread."""
    r = t.fresh()
    for d, pre in (('upstream', ''), ('overlay', ''), ('overlay-under', '#define PLANT_UNDER\n'), ('overlay-over', '#define PLANT_OVER\n')):
        t.write(r, d + '/sqlite3.c', pre + BOUNDS_TOY)
    t.write(r, 'pin.txt', 'upstream/sqlite3.c: %s\n' % hashlib.sha256(BOUNDS_TOY.encode()).hexdigest())
    one = lambda exact: "{'bounds': (('n', 8, 'n'),), 'exact': '%s', 'buffers': (('buf', '8', 'off', 'n', ()),)}" % exact  # noqa: E731
    set_bounds(t, r, "{'C-93': {'peek': %s, 'peek_start': %s}}" % (one('end'), one('start')))
    lines = ['C-93 peek: bounded: n <= 8', 'C-93 peek_start: bounded: n <= 8']
    t.write(r, 'cards/C-93.md', card_md('C-93', ['toyPeek'], src=BOUNDS_TOY).replace('- Notes: toy\n', '- Notes: toy. %s\n' % '; '.join(lines)))
    t.write(r, 'PROPERTIES.md', '# PROPERTIES\n\n' + ''.join('- %s\n' % x for x in lines))
    t.write(r, 'proofs/C-93/harness.c', PEEK_HARNESS)
    t.write(r, 'proofs/C-93/Makefile', PEEK_MK)
    t.write(r, 'tests/bounded/C-93-1.c', BOUNDS_NATIVE.replace('toySum', 'toyPeek'))
    return r


# Follow-up 2 (the auditor and Zach, 2026-11-11): a buffer as large as the largest extent its bounds allow makes a
# constant shift of the pointer visible. toySum is enforced against a contract that requires exactly n readable bytes.
SHIFT_HEAD = ('int contract_toySum(const u8 *p, int n)\n'
              '  __CPROVER_requires(n >= 1 && n <= 8 && __CPROVER_r_ok(p, n))\n'
              '  __CPROVER_assigns();\n')
SHIFT_HARNESS = ('#include "sqlite3.c"\n#include "contracts/toySum.h"\n#include <stdlib.h>\n'
                 'void harness_shift(void) {\n  int n;\n  size_t off;\n  u8 *buf, *p;\n  /* SETUP */\n'
                 '  __CPROVER_assume(n >= 1);\n  __CPROVER_assume(n <= 8);\n  off = (8) - (n);\n  buf = malloc(8);\n'
                 '  __CPROVER_assume(buf != 0);\n  p = buf + off SHIFT;\n  /* END SETUP */\n  toySum(p, n);\n}\n')


def shift_repo(t, shift):
    r = t.fresh()
    t.write(r, 'proofs/contracts/toySum.h', SHIFT_HEAD)
    t.write(r, 'cards/C-94.md', card_md('C-94', ['toySum'], extra_may='proofs/contracts/toySum.h, '))
    t.write(r, 'proofs/C-94/harness.c', SHIFT_HARNESS.replace(' SHIFT', shift))
    t.write(r, 'proofs/C-94/Makefile', 'CARD := C-94\nPROOFS := shift\nshift_ENTRY := harness_shift\n'
            'shift_ENFORCE := toySum/contract_toySum\nshift_LOOPS := unwind\nshift_UNWINDSET := toySum_wrapped_for_contract_checking.0:9\n'
            'include ../Makefile.common\n')
    return r


# T-015: the legacy frame check. f may assign cells[0].a and cells[n-1].a; the loop's frame is either object_from(p),
# which isn't among f's targets (the check refuses it), or exactly f's targets (the check passes, and CBMC then checks
# the body's writes against it)
T015_TOY = r'''#include <stdlib.h>
typedef struct { unsigned a, b; } Cell;
void f(Cell *cells, unsigned n) {
  unsigned i=0;
  Cell *p=cells;
PRE  while(i<n)
    __CPROVER_assigns(i, p, FRAME)
    __CPROVER_loop_invariant(i<=n && p==cells+i)
    __CPROVER_decreases(n-i)
  { p->WRITE=0; i++; p++; }
}
'''
T015_HEAD = ('void contract_f(Cell *cells, unsigned n)\n'
             '  __CPROVER_requires(n>0 && n<=2 && __CPROVER_w_ok(cells, sizeof(Cell)*n))\n'
             '  __CPROVER_assigns(cells[0].a, cells[n-1].a);\n')
T015_HARNESS = ('#include "sqlite3.c"\n#include "contracts/f.h"\n#include <stdlib.h>\n'
                'void h_f(void) {\n  unsigned n;\n  Cell *c;\n  /* SETUP */\n  __CPROVER_assume(n > 0 && n <= 2);\n'
                '  c = malloc(sizeof(Cell) * n);\n  __CPROVER_assume(c != 0);\n  /* END SETUP */\n  f(c, n);\n}\n')


def t015_repo(t, card, frame, write, pre='', head=None):
    r = t.fresh()
    src = T015_TOY.replace('FRAME', frame).replace('WRITE', write).replace('PRE', pre)
    for d in ('upstream', 'overlay'):
        t.write(r, d + '/sqlite3.c', src)
    t.write(r, 'proofs/contracts/f.h', head or T015_HEAD)
    t.write(r, 'cards/%s.md' % card, card_md(card, ['f'], src=src))
    t.write(r, 'proofs/%s/harness.c' % card, T015_HARNESS)
    t.write(r, 'proofs/%s/Makefile' % card, 'CARD := %s\nPROOFS := f\nf_ENTRY := h_f\nf_ENFORCE := f/contract_f\n'
            'f_LOOPS := contracts\nf_CONTRACTS := legacy\ninclude ../Makefile.common\n' % card)
    return r

# C-17's package (Zach, 2026-11-11, evidence/approvals/C-17-bounded/): the legacy-unwind pass, the aColl SETUP rule,
# exact symbolic allocations and fixed inputs in rule 16, card-wide labels, and the strict F-001 exception table
C17_TOY = TOY + r'''typedef struct Cell { unsigned a, b; } Cell;
void g(Cell *cells, unsigned n) {
  unsigned i = 0;
  Cell *p = cells;
  while( i<n ){ p->a = 0; i++; p++; }
}
typedef struct CollSeq { int x; } CollSeq;
typedef struct KI { int n; void *aColl[2]; unsigned char aSortFlags[2]; } KI;
static int toyK(KI *k){ return k->aColl[0] != 0; }
static int toyNeg(int rc){
  return -rc;
}
'''
G_HEAD = ('void contract_g(Cell *cells, unsigned n)\n'
          '  __CPROVER_requires(n > 0 && __CPROVER_w_ok(cells, sizeof(Cell) * n))\n'
          '  __CPROVER_assigns(FRAME);\n')
G_HARNESS = ('#include "sqlite3.c"\n#include "contracts/g.h"\n#include <stdlib.h>\n'
             'void h_g(void) {\n  unsigned n;\n  Cell *c;\n  /* SETUP */\n  __CPROVER_assume(n > 0 && n <= NMAX);\n'
             '  c = malloc(sizeof(Cell) * n);\n  __CPROVER_assume(c != 0);\n  /* END SETUP */\n  g(c, n);\n}\n')


def unwind_repo(t, nmax=2, frame='__CPROVER_object_whole(cells)', unwindset='g.0:2'):
    r = t.fresh()
    for d in ('upstream', 'overlay'):
        t.write(r, d + '/sqlite3.c', C17_TOY)
    t.write(r, 'proofs/contracts/g.h', G_HEAD.replace('FRAME', frame))
    t.write(r, 'cards/C-17.md', card_md('C-17', ['g'], src=C17_TOY))
    t.write(r, 'proofs/C-17/harness.c', G_HARNESS.replace('NMAX', str(nmax)))
    t.write(r, 'proofs/C-17/Makefile', 'CARD := C-17\nPROOFS := u\nu_ENTRY := h_g\nu_ENFORCE := g/contract_g\n'
            'u_LOOPS := unwind\nu_CONTRACTS := legacy\n' + ('u_UNWINDSET := %s\n' % unwindset if unwindset else '')
            + 'include ../Makefile.common\n')
    return r


K_HARNESS = r'''#include "sqlite3.c"
#include <stdlib.h>
void harness_toyK(void) {
  KI *key;
  size_t i0;
  CollSeq *c0;
  /* SETUP */
  key = malloc(sizeof(KI));
  __CPROVER_assume(key != 0);
  i0 = 0;
  c0 = malloc(sizeof(CollSeq));
  key->aColl[i0] = c0;
  /* END SETUP */
  toyK(key);
}
'''


def k_repo(t, harness=K_HARNESS):
    r = t.fresh()
    for d in ('upstream', 'overlay'):
        t.write(r, d + '/sqlite3.c', C17_TOY)
    t.write(r, 'pin.txt', 'upstream/sqlite3.c: %s\n' % hashlib.sha256(C17_TOY.encode()).hexdigest())
    t.write(r, 'cards/C-96.md', card_md('C-96', ['toyK'], src=C17_TOY))
    t.write(r, 'proofs/C-96/harness.c', harness)
    t.write(r, 'proofs/C-96/Makefile', 'CARD := C-96\nPROOFS := k\nk_ENTRY := harness_toyK\nk_COVER := toyK\ninclude ../Makefile.common\n')
    return r


NEG_HARNESS = ('#include "sqlite3.c"\n#include <stdlib.h>\nvoid harness_toyNeg(void) {\n  int rc;\n  /* SETUP */\n'
               'PRE  /* END SETUP */\n  toyNeg(rc);\nPOST}\n')


def set_table(t, r, name, value):
    pp = os.path.join(r, 'tools', 'prove.py')
    text = open(pp).read()
    new, k = re.subn(r'\n%s = (?:\{\}|\{.*?\n\})\n' % name, '\n%s = %s\n' % (name, value.replace('\\', '\\\\')), text, count=1, flags=re.S)
    assert k == 1, name
    t.write(r, 'tools/prove.py', new)


def neg_repo(t, pre='', post=''):
    r = t.fresh()
    for d in ('upstream', 'overlay'):
        t.write(r, d + '/sqlite3.c', C17_TOY)
    line = line_of(C17_TOY, '  return -rc;')
    set_table(t, r, 'EXCEPTED_FAILURES', "{'C-97': ({'finding': 'F-T', 'label': 'proved except F-T at %d', 'function': 'toyNeg', "
              "'line': %d, 'check': 'overflow', 'desc': r'^arithmetic overflow on signed unary minus in -rc$'},)}" % (line, line))
    t.write(r, 'cards/C-97.md', card_md('C-97', ['toyNeg'], src=C17_TOY).replace('- Notes: toy\n', '- Notes: toy. proved except F-T at %d\n' % line))
    t.write(r, 'proofs/C-97/harness.c', NEG_HARNESS.replace('PRE', pre).replace('POST', post))
    t.write(r, 'proofs/C-97/Makefile', 'CARD := C-97\nPROOFS := neg\nneg_ENTRY := harness_toyNeg\nneg_COVER := toyNeg\ninclude ../Makefile.common\n')
    t.write(r, 'proofs/MUTANTS', "M-901 toyNeg %d 'return -rc' 'return  -rc' card=C-97\n"
                                 "M-902 toyNeg %d 'return -rc' 'return -rc + rc' card=C-97\n" % (line, line))
    return r

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
        # a scratch repo has none of the real cards' excepted failures (C-17's F-001); tests that need one set it
        set_table(self, root, 'EXCEPTED_FAILURES', '{}')
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

        # auditor 2026-11-09 night: the type check must find the call under proof, not pass by finding nothing.
        # (A call through a function pointer is no such case: --drop-unused-functions has already turned `f(p)` into
        # a guarded direct call `toyGet(p)`, whose arguments are checked.)
        for name, mk, text, needle in (
                ('a harness whose entry never calls its ENFORCE function', MK_GET,
                 HARNESS_GET.replace('FOOT', '2').replace('  toyGet(p);', '  toyLen(1);'),
                 'harness_toyGet makes no direct call to toyGet, the function under proof'),
                ('a COVER-only proof whose entry calls no card function',
                 MK_GET.replace('get_ENFORCE := toyGet/contract_toyGet', 'get_COVER := toyGet'),
                 HARNESS_GET.replace('FOOT', '2').replace('  toyGet(p);', '  toyLen(1);'),
                 'harness_toyGet makes no direct call to a card function')):
            r = setup_get(t)
            t.write(r, 'proofs/C-90/Makefile', mk)
            t.write(r, 'proofs/C-90/harness.c', text)
            rc, out, res = t.run(r, ['make', '-C', 'proofs/C-90', 'prove', cfg])
            t.expect('prove rejects (argument types): %s' % name, rc != 0 and needle in out and 'FAIL' in res, out)
        # auditor 2026-11-09 evening: a card-call argument narrowed by its declared type (u32 value for a u64
        # parameter) fails the proof; checked on the linked goto program, so on the real C-01 and C-02 (lp64-le)
        real = os.path.join(t.base, 'real-prove')
        for d in ('tools', 'proofs', 'cards', 'overlay'):
            shutil.copytree(os.path.join(REPO, d), os.path.join(real, d),
                            ignore=shutil.ignore_patterns('__pycache__', 'tests', 'fakecli', 'build'))
        for c in ('C-01', 'C-02'):
            rc, out, res = t.run(real, [py, 'tools/prove.py', 'prove', '--card-dir', 'proofs/' + c, '--config', 'lp64-le'])
            t.expect('prove (argument types): %s as merged passes' % c, rc == 0 and 'RESULT prove %s lp64-le PASS' % c in res, out)
        h01 = open(os.path.join(REPO, 'proofs/C-01/harness.c')).read()
        k = h01.index('void harness_sqlite3PutVarint')
        for ty, shown in (('u32', 'unsignedbv[32]'), ('int', 'signedbv[32]'), ('u8', 'unsignedbv[8]')):
            t.write(real, 'proofs/C-01/harness.c', h01[:k] + h01[k:].replace('  u64 value;\n', '  %s value;\n' % ty, 1))
            rc, out, res = t.run(real, [py, 'tools/prove.py', 'prove', '--card-dir', 'proofs/C-01', '--config', 'lp64-le'])
            t.expect('prove rejects (argument types): C-01 with %s value in harness_sqlite3PutVarint' % ty,
                     rc != 0 and 'RESULT prove C-01/put lp64-le FAIL' in out and 'RESULT prove C-01 lp64-le FAIL' in res
                     and 'argument 2 of sqlite3PutVarint: value has type %s before any cast; the parameter has '
                         'unsignedbv[64]' % shown in out, out)
        t.write(real, 'proofs/C-01/harness.c', h01[:k] + h01[k:].replace('  size_t extent, offset;\n', '  size_t extent;\n  u32 offset;\n', 1))
        rc, out, res = t.run(real, [py, 'tools/prove.py', 'prove', '--card-dir', 'proofs/C-01', '--config', 'lp64-le'])
        t.expect('prove rejects (argument types): C-01 with a u32 offset in output + offset (k must be size_t)',
                 rc != 0 and 'the offset offset has type unsignedbv[32]; it must be size_t (unsignedbv[64])' in out, out)

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
        shutil.copy(os.path.join(REPO, 'PROPERTIES.md'), os.path.join(real, 'PROPERTIES.md'))   # rule 16's labels
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
        # auditor 2026-11-09 later: no static, extern or thread-local declarations in an entry function
        DECL_V, SETUP_M, PUT64 = '  u64 value;\n', '  /* SETUP */\n', 'putVarint64(output + offset, value);'
        EXT = '  extern int sqlite3PendingByte;\n'
        for name, text, needle in (
                ('static u64 value; before SETUP', h01.replace(DECL_V, '  static u64 value;\n', 1), 'static declaration in entry function harness_putVarint64'),
                ('static u64 value; in SETUP', h01.replace(DECL_V, '', 1).replace(SETUP_M, SETUP_M + '  static u64 value;\n', 1), 'static declaration in entry function harness_putVarint64'),
                ('extern int sqlite3PendingByte; before SETUP, passed to the call', h01.replace(DECL_V, DECL_V + EXT, 1).replace(
                    PUT64, 'putVarint64(output + offset, sqlite3PendingByte);'), 'extern declaration in entry function harness_putVarint64'),
                ('extern int sqlite3PendingByte; in SETUP, passed to the call', h01.replace(SETUP_M, SETUP_M + EXT, 1).replace(
                    PUT64, 'putVarint64(output + offset, sqlite3PendingByte);'), 'extern declaration in entry function harness_putVarint64'),
                ('_Thread_local u64 value; before SETUP', h01.replace(DECL_V, '  _Thread_local u64 value;\n', 1), '_Thread_local declaration in entry function')):
            t.write(real, 'proofs/C-01/harness.c', text)
            rc, out, res = t.run(real, [py, 'tools/scan.py', '--card', 'C-01'])
            t.expect('scan rejects (entry storage class): C-01 with %s' % name,
                     rc != 0 and needle in out and 'RESULT scan FAIL' in res, out)
        # auditor 2026-11-09 afternoon: no macro in an entry function's declarations (SQLITE_PRIVATE is static,
        # SQLITE_EXTERN extern); typedef names still pass
        EXT2 = '  SQLITE_EXTERN int sqlite3PendingByte;\n'
        PB = 'putVarint64(output + offset, sqlite3PendingByte);'
        for name, text, needle in (
                ('SQLITE_PRIVATE u64 value; before SETUP', h01.replace(DECL_V, '  SQLITE_PRIVATE u64 value;\n', 1), 'SQLITE_PRIVATE in a declaration in entry function harness_putVarint64 is a macro'),
                ('SQLITE_PRIVATE u64 value; in SETUP', h01.replace(DECL_V, '', 1).replace(SETUP_M, SETUP_M + '  SQLITE_PRIVATE u64 value;\n', 1), 'SQLITE_PRIVATE in a declaration in entry function harness_putVarint64 is a macro'),
                ('SQLITE_EXTERN int sqlite3PendingByte; before SETUP, passed to the call', h01.replace(DECL_V, DECL_V + EXT2, 1).replace(PUT64, PB), 'SQLITE_EXTERN in a declaration in entry function harness_putVarint64 is a macro'),
                ('SQLITE_EXTERN int sqlite3PendingByte; in SETUP, passed to the call', h01.replace(SETUP_M, SETUP_M + EXT2, 1).replace(PUT64, PB), 'SQLITE_EXTERN in a declaration in entry function harness_putVarint64 is a macro'),
                ('a system header\'s macro type (bool from <stdbool.h>) before SETUP', h01.replace('#include <stdlib.h>\n', '#include <stdlib.h>\n#include <stdbool.h>\n').replace(DECL_V, DECL_V + '  bool flag;\n', 1), 'bool in a declaration in entry function harness_putVarint64 is a macro')):
            t.write(real, 'proofs/C-01/harness.c', text)
            rc, out, res = t.run(real, [py, 'tools/scan.py', '--card', 'C-01'])
            t.expect('scan rejects (declaration macros): C-01 with %s' % name,
                     rc != 0 and needle in out and 'RESULT scan FAIL' in res, out)
        t.write(real, 'proofs/C-01/harness.c', h01.replace(DECL_V, DECL_V + '  i64 spare;\n  size_t more;\n', 1).replace(
            SETUP_M, SETUP_M + '  u32 extra;\n', 1))
        rc, out, res = t.run(real, [py, 'tools/scan.py', '--card', 'C-01'])
        t.expect('scan (declaration macros): C-01 with typedef names (u64, i64, u32, size_t) declared before and in SETUP passes',
                 rc == 0 and 'RESULT scan PASS' in res, out)
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
        # checkpoint 1, fix 5: a Depends on item that is not a callee gives its reason in parentheses
        r5 = setup_get(t)
        t.write(r5, 'cards/C-91.md', card_md('C-91', ['toySum'], depends='C-90'))
        rc, out, res = t.run(r5, [py, 'tools/scan.py'])
        t.expect('scan rejects: a Depends on item whose card proves none of the card\'s callees, with no reason',
                 rc != 0 and 'Depends on C-90' in out and 'not its callees' in out, out)
        t.write(r5, 'cards/C-91.md', card_md('C-91', ['toySum'], depends='C-90 (not a callee: its requires are what C-90 ensures)'))
        rc, out, res = t.run(r5, [py, 'tools/scan.py'])
        t.expect('scan: a Depends on item that is not a callee passes with its reason in parentheses', rc == 0, out)
        # checkpoint 1, D2: a boundary header is its LEDGER.md clause word for word, and a clause has its header
        t.write(r, 'LEDGER.md', '# Ledger\n## A-007 toyLog\n- Clause:\n  ~~~\n  int contract_toyLog(int x)\n'
                '    __CPROVER_ensures(1);\n  ~~~\n- Status: draft\n')
        rc, out, res = t.run(r, [py, 'tools/scan.py'])
        t.expect('scan: a boundary header equal to its ledger clause (spacing and comments aside) passes', rc == 0, out)
        t.write(r, 'proofs/contracts/toyLog.h', '/* Ledger: A-007 */\nint contract_toyLog(int x) __CPROVER_ensures(x > 0);\n')
        rc, out, res = t.run(r, [py, 'tools/scan.py'])
        t.expect('scan rejects: a boundary header that is not its ledger clause word for word',
                 rc != 0 and 'word for word' in out and 'A-007' in out, out)
        os.remove(os.path.join(r, 'proofs/contracts/toyLog.h'))
        t.write(r, 'proofs/C-90/Makefile', MK_GET)
        rc, out, res = t.run(r, [py, 'tools/scan.py'])
        t.expect('scan rejects: a ledger clause whose boundary header does not exist',
                 rc != 0 and 'proofs/contracts/toyLog.h does not exist' in out, out)
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
        t.write(r, 'proofs/MUTANTS', "M-001 toyGet %d 'p[1]' 'p[2]' card=C-90\nM-002 toyGet %d '0x7f' '0x3f' card=C-90\n" % (gl, gl))
        h0 = hashlib.sha256(open(os.path.join(r, 'overlay/sqlite3.c'), 'rb').read()).hexdigest()
        rc, out, res = t.run(r, [py, 'tools/mutate.py', '--card', 'C-90', '--config', 'lp64-le'])
        h1 = hashlib.sha256(open(os.path.join(r, 'overlay/sqlite3.c'), 'rb').read()).hexdigest()
        t.expect('mutate: out-of-bounds mutant killed, functional mutant survives -> FAIL, overlay untouched',
                 rc != 0 and 'M-001' in out and re.search(r'M-001 .* KILLED', out) and re.search(r'M-002 .* SURVIVED', out)
                 and 'FAIL 1/2 killed' in res and h0 == h1, out)
        t.write(r, 'proofs/MUTANTS', "M-001 toyGet %d 'p[1]' 'p[2]' card=C-90\nM-002 toyGet %d '0x7f' '0x3f' card=C-90 equivalent='UB-free either way' review=reviews/C-90-r1.md\n" % (gl, gl))
        rc, out, res = t.run(r, [py, 'tools/mutate.py', '--card', 'C-90', '--config', 'lp64-le'])
        t.expect('mutate: survivor with a reviewed equivalence argument passes', rc == 0 and '1/2 killed 1 equivalent' in res, out)
        t.write(r, 'proofs/MUTANTS', "M-001 toyGet %d 'p' 'q' card=C-90\n" % gl)
        rc, out, res = t.run(r, [py, 'tools/mutate.py', '--card', 'C-90', '--config', 'lp64-le'])
        t.expect('mutate: ambiguous mutant (token occurs several times) is an error', rc != 0 and 'occurs' in out, out)
        rc, out, res = t.run(r, [py, 'tools/mutate.py', '--card', 'C-90', '--config', 'lp64-le', '--adhoc', "toyGet %d '<<7' '<<70'" % gl])
        t.expect('mutate --adhoc: planted shift bug is killed', rc == 0 and 'KILLED' in out and 'shift' in out, out)
        t.write(r, 'proofs/MUTANTS', "M-001 toyGet %d '0x7f' '0x3f'\n" % gl)
        rc, out, res = t.run(r, [py, 'tools/mutate.py', '--all', '--config', 'lp64-le'])
        t.expect('mutate: a MUTANTS line with no card= is an error', rc != 0 and 'needs card=C-NN' in out, out)
        t.write(r, 'proofs/MUTANTS', "M-001 toyGet %d '0x7f' '0x3f' card=C-95\n" % gl)
        rc, out, res = t.run(r, [py, 'tools/mutate.py', '--card', 'C-90', '--config', 'lp64-le'])
        t.expect('mutate --card: a card with no mutant of its own fails (its gate would pass vacuously)',
                 rc != 0 and 'no mutant with card=C-90' in out, out)
        # checkpoint 1, D1 (amended by the auditor): only the mutant's own card's proofs kill it
        t.write(r, 'cards/C-95.md', card_md('C-95', ['toySum']))
        t.write(r, 'proofs/C-95/harness.c', '#include "sqlite3.c"\nvoid harness_toyLen(void) {\n  u64 v;\n  /* SETUP */\n'
                '  /* END SETUP */\n  toyLen(v);\n}\n')
        t.write(r, 'proofs/C-95/Makefile', 'CARD := C-95\nPROOFS := len\nlen_ENTRY := harness_toyLen\nlen_LOOPS := unwind\n'
                'len_UNWINDSET := toyLen.0:12\nlen_COVER := toyLen\ninclude ../Makefile.common\n')
        t.write(r, 'proofs/MUTANTS', "M-001 toyGet %d 'p[1]' 'p[2]' card=C-95\n" % gl)
        rc, out, res = t.run(r, [py, 'tools/mutate.py', '--card', 'C-95', '--with', 'C-90', '--config', 'lp64-le'])
        t.expect('mutate --card C-95 --with C-90: a mutant only C-90\'s proofs kill SURVIVED (C-90\'s failure does not count)',
                 rc != 0 and re.search(r'M-001 .* SURVIVED .*C-90/get lp64-le: .*does not count', out) and 'FAIL 0/1 killed' in res, out)
        rc, out, res = t.run(r, [py, 'tools/mutate.py', '--all', '--config', 'lp64-le'])
        t.expect('mutate --all: the same mutant survives when its card has proofs, whoever else kills it',
                 rc != 0 and re.search(r'M-001 .* SURVIVED', out) and 'FAIL 0/1 killed' in res, out)
        # pending: only while the card has no proofs here or on main; --all fails on it unless --allow-pending
        shutil.rmtree(os.path.join(r, 'proofs', 'C-95'))
        subprocess.run(['git', '-C', r, 'add', '-A'], check=True)
        subprocess.run(['git', '-C', r, '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-qm', 'base'], check=True)
        rc, out, res = t.run(r, [py, 'tools/mutate.py', '--all', '--config', 'lp64-le'])
        t.expect('mutate --all: a mutant of a card with no proofs is PENDING, not run, even if another card would kill it; '
                 'and --all fails on it (the §5 gate)',
                 rc != 0 and re.search(r'M-001 .* PENDING not run: C-95', out) and 'FAIL 0/1 killed 0 equivalent 1 pending' in res, out)
        rc, out, res = t.run(r, [py, 'tools/mutate.py', '--all', '--allow-pending', '--config', 'lp64-le'])
        t.expect('mutate --all --allow-pending: the pending mutant passes', rc == 0 and 'PASS 0/1 killed 0 equivalent 1 pending' in res, out)
        t.write(r, 'proofs/C-95/Makefile', 'CARD := C-95\n')
        subprocess.run(['git', '-C', r, 'add', '-A'], check=True)
        subprocess.run(['git', '-C', r, '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-qm', 'c95'], check=True)
        os.remove(os.path.join(r, 'proofs', 'C-95', 'Makefile'))
        rc, out, res = t.run(r, [py, 'tools/mutate.py', '--all', '--allow-pending', '--config', 'lp64-le'])
        t.expect('mutate --all: a card with proofs on main but none here is not pending: the mutant fails',
                 rc != 0 and 'C-95 has proofs on main but none here' in out and 'pending' not in res, out)
        rc, out, res = t.run(r, [py, 'tools/gate.py', 'gate'])
        t.expect('gate (full): any pending mutant fails it', rc != 0 and re.search(r'mutants all\s+FAIL', out), out)
        subprocess.run(['git', '-C', r, 'rm', '-q', '-r', 'proofs/C-95'], check=True)
        subprocess.run(['git', '-C', r, '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-qm', 'rm c95'], check=True)
        rc, out, res = t.run(r, [py, 'tools/gate.py', 'gate', '--allow-pending'])
        t.expect('gate --allow-pending (make gate ALLOW_PENDING=1): the pending mutant passes the mutants step',
                 re.search(r'mutants all\s+PASS', out) and '--allow-pending' in out, out)

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
        # checkpoint 1, D2: proof.lock covers the boundary headers written from LEDGER.md
        t.write(r, 'proofs/contracts/sqlite3CorruptError.h', '/* Ledger: A-004 */\nint contract_sqlite3CorruptError(int lineno);\n')
        os.remove(os.path.join(r, 'tools/extra.py'))
        subprocess.run(['git', '-C', r, 'add', '-A'], check=True)
        rc, out, res = t.run(r, [py, 'tools/lock.py', 'check'])
        t.expect('lock: a boundary header (proofs/contracts/sqlite3CorruptError.h) is frozen',
                 rc != 0 and 'proofs/contracts/sqlite3CorruptError.h is under a frozen path' in out, out)
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

    # ---- C-11 decision (2026-11-10, evidence/approvals/C-11-f2i-exact-min/): RESULTS.md and results.csv say what is argued
    if want('results'):
        r = t.fresh()
        code = ('import sys; sys.path.insert(0, "tools"); import results\n'
                'class Pr:\n'
                '    def __init__(s, cover, replace): s.cover, s.replace = cover, replace\n'
                'own = results.argued_notes(Pr(["sqlite3IntFloatCompare"], ["sqlite3IsNaN/contract_sqlite3IsNaN"]))\n'
                'user = results.argued_notes(Pr(["sqlite3VdbeRecordCompareWithSkip"], ["sqlite3IntFloatCompare/contract_sqlite3IntFloatCompare"]))\n'
                'other = results.argued_notes(Pr(["sqlite3IsNaN"], []))\n'
                'row = dict((c, "") for c in results.COLS); row.update(card="C-11", proof="compare", argued=own)\n'
                'md = results.results_md([row])\n'
                'print("OWN", own); print("USER", user); print("OTHER", repr(other))\n'
                'print("COLS", "argued" in results.COLS); print("MDHEAD", "| Argued |" in md); print("MDROW", own in md)\n'
                'print("MDCLAIM", "except for what its Argued column names" in md)\n')
        rc, out, res = t.run(r, [py, '-c', code])
        want_txt = 'proved for every other (i, r); argued and tested at r = −2^63'
        t.expect('results: a proof of sqlite3IntFloatCompare is "proved for every other (i, r); argued and tested at r = -2^63"',
                 ('OWN sqlite3IntFloatCompare: ' + want_txt) in out, out)
        t.expect('results: a proof that uses contract_sqlite3IntFloatCompare says so',
                 ('USER uses contract_sqlite3IntFloatCompare, which is ' + want_txt) in out, out)
        t.expect('results: a proof that neither covers nor uses it argues nothing', "OTHER ''" in out, out)
        t.expect('results: results.csv has an argued column, and RESULTS.md an Argued column and its claim',
                 'COLS True' in out and 'MDHEAD True' in out and 'MDROW True' in out and 'MDCLAIM True' in out, out)

    # ---- checkpoint 1 Q2, Q4, D4 and fix 2, in tools/campaign.py itself (the selftest repeats these end to end)
    if want('campaign'):
        r = t.fresh()
        shutil.copy(os.path.join(REPO, 'tools', 'sessions.toml'), os.path.join(r, 'tools', 'sessions.toml'))
        code = CAMPAIGN_CHECKS.replace('@ROOT@', r).replace('@HOME@', r + '-home')   # a home outside the checkout, as on the host
        rc, out, res = t.run(r, [py, '-c', code], timeout=900)
        got = {}
        for ln in out.split('\n'):
            m = re.match(r'^(PASS|FAIL) ([a-z0-9-]+):', ln)
            if m:
                got.setdefault(m.group(2), []).append(m.group(1))
        for name in ('codex-bwrap', 'codex-home-hidden', 'codex-rules-hidden', 'codex-agents-md', 'claude-home-hidden',
                     'claude-no-skills-mcp', 'claude-keeps-dot-claude', 'd4-round-7', 'repro-sandboxed'):
            t.expect('campaign.py: %s' % CAMPAIGN_CHECK_NAMES[name], got.get(name) == ['PASS'],
                     '\n'.join(ln for ln in out.split('\n') if name in ln)[:1500] or out[-1500:])

    # ---- checkpoint 1 fix 2: no session runs make in a card directory, and no reviewer builds a repro
    if want('docs'):
        found = []
        for rel in ('agents/builder/GOAL.md', 'agents/reviewer/GOAL.md', 'agents/ledger/GOAL.md', 'proofs/HOWTO.md', 'tools/campaign.py'):
            path = os.path.join(REPO, rel)
            if not os.path.exists(path):
                continue
            for n, ln in enumerate(open(path), 1):
                if re.search(r'make -C proofs/C-NN (prove|coverage)|`make prove`|CONFIG=lp64-le', ln) and 'Never' not in ln:
                    found.append('%s:%d: %s' % (rel, n, ln.strip()[:120]))
        t.expect('docs: builder, reviewer and HOWTO instructions run tools/prove.py, never make in a card directory',
                 not found, '\n'.join(found))
        rv = open(os.path.join(REPO, 'agents/reviewer/GOAL.md')).read()
        t.expect('docs: reviewer rule 8 reads campaign.py\'s repro output instead of building builder-written repros',
                 '.campaign/repro/' in rv and 'build `tests/repro` natively' not in rv, rv[-2000:])

    # ---- checkpoint 1 fixes 3, 4, 6, 7, Q5 and D2: the repository's specs, ledger, cards and mutants say what the audit asked
    if want('docs'):
        rd = lambda rel: open(os.path.join(REPO, rel)).read() if os.path.exists(os.path.join(REPO, rel)) else ''  # noqa: E731
        props, spec, ledger, ub = rd('PROPERTIES.md'), rd('proofs/spec/record_format.h'), rd('LEDGER.md'), rd('UB-CLASSES.md')
        t.expect('fix 3: P3 states departure D4 (types 8 and 9, schema format 4), and record_format.h cites it at rows 8, 9',
                 re.search(r'\*\*D4\.[^\n]*8 and 9[^\n]*schema-format', props) and 'schema format 4 and higher' in props
                 and re.search(r'D4\. Rows 8, 9', spec) and re.search(r't==8 \|\| t==9 .*\(D4\)', spec), props[-1500:])
        a3 = re.search(r'^## A-003 .*?(?=^## )', ledger, re.M | re.S)
        t.expect('fix 4: A-003 says the clause leaves out the encoding-change path\'s allocation and db->mallocFailed, and why',
                 a3 and '92324' in a3.group(0) and 'mallocFailed' in a3.group(0) and 'no milestone-1 caller reads them' in a3.group(0),
                 a3.group(0)[:1500] if a3 else ledger[:500])
        a1 = re.search(r'^## A-001 .*?(?=^## )', ledger, re.M | re.S)
        c15 = rd('cards/C-15.md')
        t.expect('Q5: A-001 and C-15 state the read extent max(nKey, 1) + 8, derived from the lines that bound it, and drop '
                 '"not by nKey"',
                 a1 and '(nKey > 0 ? nKey : 1) + 8' in a1.group(0) and '(nKey > 0 ? nKey : 1) + 8' in c15
                 and 'max(nKey, 1) + 7' in c15 and 'idx is bounded by szHdr and by the field count, not by nKey' not in c15
                 and 'idx is bounded only by szHdr and by the field count, not by nKey.' not in (a1.group(0) if a1 else ''),
                 (a1.group(0)[:800] if a1 else '') + c15[:300])
        t.expect('fix 7: UB-CLASSES argues integer-to-double conversion (6.3.1.4p2) at sqlite3IntFloatCompare',
                 re.search(r'^\| An integer converted to a real floating type[^\n]*6\.3\.1\.4p2[^\n]*sqlite3IntFloatCompare', ub, re.M),
                 ub[:300])
        sys.path.insert(0, os.path.join(REPO, 'tools'))
        import mutate as _m
        muts = {m['id']: m for m in _m.read_mutants(os.path.join(REPO, 'proofs', 'MUTANTS'))}
        want6 = [('sqlite3VdbeRecordUnpack', 92134, '(u32)nKey', '(u32)nKey+1', 'C-15'), ('sqlite3VdbeSerialGet', 92055, 'buf+2', 'buf+1', 'C-09'),
                 ('sqlite3VdbeSerialGet', 92006, 'pMem->n = 0', 'pMem->n = 1', 'C-09')]
        have6 = [m for m in muts.values() if (m['function'], m['line'], m['from'], m['to'], m['card']) in want6]
        ovl = open(os.path.join(REPO, 'overlay', 'sqlite3.c'), 'rb').read()
        applied = []
        for m in have6:
            try:
                _m.apply(ovl, m)
                applied.append(m['id'])
            except _m.MutantError as e:
                applied.append(str(e))
        t.expect('fix 6: proofs/MUTANTS has the audit\'s three mutants, and each applies exactly once to the overlay',
                 len(have6) == 3 and all(x.startswith('M-') for x in applied), str((have6, applied)))
        c14, c17, bg = rd('cards/C-14.md'), rd('cards/C-17.md'), rd('agents/builder/GOAL.md')
        may = lambda c: re.search(r'^- May change: (.*)$', c, re.M).group(1) if re.search(r'^- May change: (.*)$', c, re.M) else ''  # noqa: E731
        t.expect('D2: the boundary headers are off C-14\'s and C-17\'s May change lines, and builder §1 no longer lets builders write them',
                 'sqlite3DbMallocRaw.h' not in may(c14) and 'vdbeCompareMemString.h' not in may(c17)
                 and 'sqlite3CorruptError.h' not in may(c17) and 'for a boundary callee whose header your card' not in bg
                 and 'C-17 writes' not in rd('cards/C-19.md') and "written by C-14's builder" not in ledger, may(c14) + ' | ' + may(c17))

    # ---- checkpoint 1 fix 1: DFCC aborts on os_unix's syscall table (close, read) unless prove.py removes the bodies
    # of REPLACEd functions and of the card's unreached callees before drop-unused-functions
    if want('dfcc'):
        r = t.fresh()
        t.write(r, 'upstream/sqlite3.c', SYSCALL_TOY)
        t.write(r, 'overlay/sqlite3.c', SYSCALL_TOY)
        card = card_md('C-96', ['toyMaybeClose'], extra_may='proofs/contracts/toyMaybeClose.h, ', src=SYSCALL_TOY).replace(
            '- Depends on:', '- Unreached callees, bodies removed: toyClose (upstream/sqlite3.c:%d)\n- Depends on:' % line_of(SYSCALL_TOY, ' toyClose('))
        t.write(r, 'cards/C-96.md', card)
        t.write(r, 'proofs/contracts/toyMaybeClose.h', 'int contract_toyMaybeClose(int x)\n  __CPROVER_requires(x <= 100)\n'
                '  __CPROVER_ensures(__CPROVER_return_value == 0);\n')
        t.write(r, 'proofs/C-96/harness.c', '#include "sqlite3.c"\n#include "contracts/toyMaybeClose.h"\n'
                'void harness_toyMaybeClose(void) {\n  int x;\n  /* SETUP */\n  /* END SETUP */\n  toyMaybeClose(x);\n}\n')
        t.write(r, 'proofs/C-96/Makefile', 'CARD := C-96\nPROOFS := mc\nmc_ENTRY := harness_toyMaybeClose\n'
                'mc_ENFORCE := toyMaybeClose/contract_toyMaybeClose\ninclude ../Makefile.common\n')
        rc, out, res = t.run(r, [py, 'tools/prove.py', 'prove', '--card-dir', 'proofs/C-96', '--config', 'lp64-le',
                                 '--overlay', 'overlay', '--build-dir', 'proofs/C-96/build'])
        t.expect('prove: the card\'s unreached callee loses its body, so DFCC does not abort on the syscall table, and the proof passes',
                 rc == 0 and 'RESULT prove C-96 lp64-le PASS' in res, out)
        t.write(r, 'proofs/contracts/toyMaybeClose.h', 'int contract_toyMaybeClose(int x)\n  __CPROVER_ensures(1);\n')
        rc, out, res = t.run(r, [py, 'tools/prove.py', 'prove', '--card-dir', 'proofs/C-96', '--config', 'lp64-le',
                                 '--overlay', 'overlay', '--build-dir', 'proofs/C-96/build'])
        t.expect('prove: an unreached callee the proof does reach fails it (undefined function should be unreachable)',
                 rc != 0 and 'FAIL' in res and 'toyClose' in out and 'unreachable' in out, out)
        # a REPLACEd callee's body goes too: toyOuter's proof replaces toyMaybeClose, whose body reaches the table
        t.write(r, 'cards/C-96.md', card.replace('- Unreached callees, bodies removed: toyClose (upstream/sqlite3.c:%d)\n' % line_of(SYSCALL_TOY, ' toyClose('), ''))
        t.write(r, 'proofs/contracts/toyMaybeClose.h', 'int contract_toyMaybeClose(int x)\n  __CPROVER_requires(x <= 100)\n'
                '  __CPROVER_ensures(__CPROVER_return_value == 0);\n')
        t.write(r, 'cards/C-97.md', card_md('C-97', ['toyOuter'], src=SYSCALL_TOY))
        t.write(r, 'proofs/contracts/toyOuter.h', 'int contract_toyOuter(int x)\n  __CPROVER_ensures(__CPROVER_return_value == 0);\n')
        t.write(r, 'proofs/C-97/harness.c', '#include "sqlite3.c"\n#include "contracts/toyMaybeClose.h"\n#include "contracts/toyOuter.h"\n'
                'void harness_toyOuter(void) {\n  int x;\n  /* SETUP */\n  /* END SETUP */\n  toyOuter(x);\n}\n')
        t.write(r, 'proofs/C-97/Makefile', 'CARD := C-97\nPROOFS := o\no_ENTRY := harness_toyOuter\n'
                'o_ENFORCE := toyOuter/contract_toyOuter\no_REPLACE := toyMaybeClose/contract_toyMaybeClose\ninclude ../Makefile.common\n')
        rc, out, res = t.run(r, [py, 'tools/prove.py', 'prove', '--card-dir', 'proofs/C-97', '--config', 'lp64-le',
                                 '--overlay', 'overlay', '--build-dir', 'proofs/C-97/build'])
        t.expect('prove: a REPLACEd callee loses its body before drop-unused, so DFCC does not abort, and the proof passes',
                 rc == 0 and 'RESULT prove C-97 lp64-le PASS' in res, out)
        t.write(r, 'cards/C-98.md', card_md('C-98', ['toyClose'], src=SYSCALL_TOY).replace(
            '- Depends on:', '- Unreached callees, bodies removed: toyClose (upstream/sqlite3.c:%d)\n- Depends on:' % line_of(SYSCALL_TOY, ' toyClose(')))
        rc, out, res = t.run(r, [py, 'tools/scan.py'])
        t.expect('cards: a card function listed as its own unreached callee is rejected', rc != 0 and 'both a function of the card' in out, out)

    # ---- T-006: legacy contracts (Zach's conditions 1-3, evidence/approvals/T-006-dfcc-loop-pointer/)
    if want('legacy'):
        r = legacy_repo(t)
        prove = lambda ov, card='C-15': t.run(r, [py, 'tools/prove.py', 'prove', '--card-dir', 'proofs/' + card, '--config',  # noqa: E731
                                                  'lp64-le', '--overlay', ov, '--build-dir', 'proofs/%s/build' % card])
        rc, out, res = prove('overlay')
        t.expect('legacy: every validation toy proves under legacy contracts, T-006\'s loop-carried pointer included',
                 rc == 0 and 'RESULT prove C-15 lp64-le PASS' in res, out[-1500:])
        gen = os.path.join(r, 'proofs', 'C-15', 'build', 'lp64-le', 'callee_frame.legacy.c')
        gtext = open(gen).read() if os.path.exists(gen) else ''
        t.expect('legacy: the generated unit redeclares the enforced and replaced functions with their headers\' clauses',
                 'void t_callee_frame(Cell *a, Cell *other, unsigned n)' in gtext and 'void reset(Cell *p)' in gtext
                 and '__CPROVER_ensures(p->flags == 0)' in gtext and 'contract_reset' not in gtext.split('*/', 1)[-1], gtext)
        keep_h = legacy_text('heads/keep.h')
        t.write(r, 'proofs/contracts/keep.h', keep_h.replace('\n  __CPROVER_ensures(p->flags == __CPROVER_old(p->flags))', ''))
        rc, out, res = prove('overlay-bad')
        for name, _, _, _, _, check in LEGACY_PROOFS:
            if check is None:
                continue
            fails = legacy_failures(r, 'C-15', name)
            t.expect('legacy: the %s toy\'s bad variant fails by "%s"' % (name, check), any(check in f for f in fails),
                     str(fails) if fails else out[-1500:])
        # no stored copy to diverge: a header edit changes the next build
        t.write(r, 'proofs/contracts/keep.h', keep_h)
        after_h = legacy_text('heads/t_after.h')
        t.write(r, 'proofs/contracts/t_after.h', after_h.replace('__CPROVER_return_value == n', '__CPROVER_return_value == n + 1'))
        rc, out, res = prove('overlay')
        fa = legacy_failures(r, 'C-15', 'after')
        t.expect('legacy: a header edit reaches the next build (contract_t_after\'s ensures made false fails the proof)',
                 rc != 0 and any('Check ensures clause' in f for f in fa), str(fa) if fa else out[-800:])
        t.write(r, 'proofs/contracts/t_after.h', after_h)
        # globals start unconstrained under legacy, as TRUSTED.md says of DFCC
        toys = legacy_text('toys.c')
        t.write(r, 'cards/C-17.md', card_md('C-17', ['t_glob', 't_static'], src=toys))
        t.write(r, 'proofs/C-17/harness.c', open(os.path.join(r, 'proofs', 'C-15', 'harness.c')).read())
        t.write(r, 'proofs/C-17/Makefile', legacy_makefile('C-17', [('glob', 'h_glob', 't_glob', [], False, None)]))
        rc, out, res = prove('overlay', 'C-17')
        t.expect('legacy: globals start unconstrained (a contract claiming a global\'s initial value fails), as under DFCC',
                 rc != 0 and 'RESULT prove C-17 lp64-le FAIL' in res and any('Check ensures clause' in f for f in legacy_failures(r, 'C-17', 'glob')), out[-600:])
        # T-012: a replaced callee with a static local aborts the legacy enforce pass; prove.py says so, and keeping its body works
        t.write(r, 'proofs/C-17/Makefile', legacy_makefile('C-17', [('st', 'h_static', 't_static', ['stat'], True, None)]))
        rc, out, res = prove('overlay', 'C-17')
        t.expect('legacy: a replaced callee with a static local fails the build, and prove.py names T-012',
                 rc != 0 and 'legacy-enforce failed' in out and 'T-012' in out, out[-800:])
        t.write(r, 'proofs/C-17/Makefile', legacy_makefile('C-17', [('st', 'h_static', 't_static', [], True, None)]))
        rc, out, res = prove('overlay', 'C-17')
        t.expect('legacy: the same proof with that callee\'s body kept proves (T-012\'s workaround)',
                 rc == 0 and 'RESULT prove C-17 lp64-le PASS' in res, out[-800:])
        # T-006 follow-up (C-15 round 4): coverage under the legacy engine reads the enforced body by its legacy name,
        # and counts only the function's own lines, not those of a kept callee inlined into it
        rc, out, res = t.run(r, [py, 'tools/prove.py', 'coverage', '--card-dir', 'proofs/C-17', '--config', 'lp64-le',
                                 '--build-dir', 'proofs/C-17/build'])
        import json as _json
        cj = os.path.join(r, 'proofs', 'C-17', 'build', 'lp64-le', 'st.cover.json')
        fj = (_json.load(open(cj)).get('functions') or {}).get('t_static', {}) if os.path.exists(cj) else {}
        rng = (line_of(legacy_text('toys.c'), 'void t_static('), line_of(legacy_text('toys.c'), '{ stat(p); ++p; ++k; }') + 1)
        t.expect('legacy: coverage finds the enforced function\'s goals under the legacy engine, all within its own lines '
                 '(the kept callee stat\'s line is not counted)',
                 'no coverage goals found' not in out and fj.get('goal_lines') and
                 all(rng[0] <= x <= rng[1] for x in fj['goal_lines']) and line_of(legacy_text('toys.c'), 'void stat(') not in fj['goal_lines'],
                 out[-800:] + str(fj))
        # only LEGACY_CARDS may opt in
        r2 = legacy_repo(t, card='C-96')
        rc, out, res = t.run(r2, [py, 'tools/prove.py', 'prove', '--card-dir', 'proofs/C-96', '--config', 'lp64-le',
                                  '--overlay', 'overlay', '--build-dir', 'proofs/C-96/build'])
        t.expect('legacy: a card not in LEGACY_CARDS may not use legacy contracts', rc != 0 and 'only C-15, C-17 may use' in out, out[-600:])
        # a legacy harness may carry no function contract clauses of its own
        h = open(os.path.join(r, 'proofs', 'C-15', 'harness.c')).read()
        t.write(r, 'proofs/C-15/harness.c', h + 'void reset(Cell *p) __CPROVER_ensures(1);\n')
        rc, out, res = prove('overlay')
        t.expect('legacy: a harness with function contract clauses is refused', rc != 0 and 'no function contract clauses' in out, out[-600:])
        t.write(r, 'proofs/C-15/harness.c', h)
        # the generator: exactly one declaration, copied with only the name changed
        code = ('import sys; sys.path.insert(0, "tools"); import prove\n'
                'h = open("proofs/contracts/reset.h").read()\n'
                'print("REDECL", repr(prove.legacy_redeclaration(h, "reset")))\n'
                'try:\n    prove.legacy_redeclaration(h + h.replace("C_reset_H", "X"), "reset"); print("TWO ok")\n'
                'except prove.CardError as e:\n    print("TWO refused", e)\n')
        rc, out, res = t.run(r, [py, '-c', code])
        t.expect('legacy: the redeclaration is the header\'s declaration with only its name changed; two declarations are refused',
                 "REDECL 'void reset(Cell *p)\\n  __CPROVER_requires(__CPROVER_w_ok(p, sizeof(Cell)))\\n  __CPROVER_assigns(p->flags)\\n  __CPROVER_ensures(p->flags == 0);'" in out
                 and 'TWO refused' in out, out)
        # DFCC stays the default, and an unknown engine is refused
        t.write(r, 'proofs/C-15/Makefile', legacy_makefile('C-15', LEGACY_PROOFS[:1]).replace('legacy', 'cbmc5'))
        rc, out, res = prove('overlay')
        t.expect('legacy: <name>_CONTRACTS takes only dfcc or legacy', rc != 0 and 'must be dfcc or legacy' in out, out[-400:])

    # ---- B2 (Zach, 2026-11-10): memcmp's contract, clause guards, kept bodies under legacy, land rules
    if want('b2'):
        for engine, card in (('dfcc', 'C-93'), ('legacy', 'C-15')):
            r = b2_repo(t, card, engine)
            run = lambda ov, c=card, rr=r: t.run(rr, [py, 'tools/prove.py', 'prove', '--card-dir', 'proofs/' + c, '--config',  # noqa: E731
                                                      'lp64-le', '--overlay', ov, '--build-dir', 'proofs/%s/build' % c])
            rc, out, res = run('overlay')
            t.expect('b2 (%s): memcmp replaced by A-006\'s contract proves for lengths up to 10^6, and a kept callee body '
                     'writing only inside the loop\'s assigns proves' % engine, rc == 0 and 'PASS' in res, out[-1200:])
            rc, out, res = run('overlay-bad')
            fc = legacy_failures(r, card, 'cmp')
            t.expect('b2 (%s): a memcmp call one byte past an argument fails by the contract\'s requires' % engine,
                     any('requires clause' in f for f in fc), str(fc) if fc else out[-1000:])
            if engine == 'legacy':
                fw = legacy_failures(r, card, 'walk')
                t.expect('b2 (legacy): a kept callee body writing outside the loop\'s assigns fails ("is assignable")',
                         any('is assignable' in f for f in fw), str(fw) if fw else out[-1000:])
            # a clause smuggled onto the ENFORCE function in preds.h, or onto a REPLACE function in a contracts header
            for where, text, name in (
                    ('proofs/include/preds.h', 'int cmpneg(const unsigned char *a, const unsigned char *b, size_t n)\n'
                     '  __CPROVER_ensures(1);\n', 'preds.h, onto the ENFORCE function'),
                    ('proofs/contracts/cmpneg.h', B2_HEADS['cmpneg'] + 'int memcmp(const void *s1, const void *s2, size_t n)\n'
                     '  __CPROVER_ensures(__CPROVER_return_value == 0);\n', 'a contracts header, onto the REPLACE function')):
                old = open(os.path.join(r, where)).read() if os.path.exists(os.path.join(r, where)) else None
                t.write(r, where, (old or '') + text)
                rc, out, res = run('overlay')
                t.expect('b2 (%s): a contract clause smuggled into %s fails the build' % (engine, name),
                         rc != 0 and 'contract clause' in out, out[-600:])
                rc, out, res = t.run(r, [py, 'tools/scan.py'])
                if where.endswith('preds.h'):
                    t.expect('b2 (%s): scan rejects a function contract clause in proofs/include/preds.h' % engine,
                             rc != 0 and 'no function contract clauses in proofs/include/' in out, out[-600:])
                if old is None:
                    os.remove(os.path.join(r, where))
                else:
                    t.write(r, where, old)
        # memcmp.h is frozen; a land may carry it only with an approval record and proof.lock; sessions.toml may land
        code = ('import sys; sys.path.insert(0, "tools"); import lock, campaign\n'
                'print("FROZEN", "proofs/contracts/memcmp.h" in lock.FROZEN)\n'
                'print("BARE", campaign.land_paths_problems(["proofs/contracts/memcmp.h"], [])[0])\n'
                'print("OK", campaign.land_paths_problems(["proofs/contracts/memcmp.h", "proof.lock", "evidence/approvals/x/APPROVED.md"], ["evidence/approvals/x/APPROVED.md"])[0])\n'
                'print("TOML", campaign.land_paths_problems(["tools/sessions.toml"], [])[0])\n')
        rc, out, res = t.run(t.fresh(), [py, '-c', code])
        rt = os.path.join(t.base, 'toml-keys')
        os.makedirs(rt)
        subprocess.run(['git', 'init', '-q', rt], check=True)
        t.write(rt, 'tools/sessions.toml', '[vendors.codex]\nusage_limit_patterns = ["a"]\n[roles.builder.high]\nmodel = "m1"\neffort = "high"\n')
        subprocess.run(['git', 'add', '-A'], cwd=rt, check=True)
        subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-q', '-m', 'x'], cwd=rt, check=True)
        t.write(rt, 'tools/sessions.toml', '[vendors.codex]\nusage_limit_patterns = ["a", "b"]\n[roles.builder.high]\nmodel = "m2"\neffort = "high"\n')
        subprocess.run(['git', 'add', 'tools/sessions.toml'], cwd=rt, check=True)
        rc2, out2, _ = t.run(rt, [py, '-c', 'import sys; sys.path.insert(0, %r); import campaign; print("KEYS", campaign.sessions_toml_changes("."))' % os.path.join(REPO, 'tools')])
        t.expect('b2: a land that changes tools/sessions.toml names the changed keys in its trailer',
                 "KEYS ['roles.builder.high.model', 'vendors.codex.usage_limit_patterns']" in out2, out2)
        t.expect('b2: memcmp.h is frozen and lands only with an approval record and proof.lock; tools/sessions.toml may land (T-007)',
                 'FROZEN True' in out and "BARE ['frozen" in out and 'OK []' in out and 'TOML []' in out, out)
        # T-017 (Zach, 2026-11-11): proofs/HOWTO.md is frozen; it lands only with an approval record and proof.lock
        code = ('import sys; sys.path.insert(0, "tools"); import lock, campaign\n'
                'print("FROZEN", "proofs/HOWTO.md" in lock.FROZEN)\n'
                'print("BARE", campaign.land_paths_problems(["proofs/HOWTO.md"], [])[0])\n'
                'print("OK", campaign.land_paths_problems(["proofs/HOWTO.md", "proof.lock", "evidence/approvals/x/APPROVED.md"], ["evidence/approvals/x/APPROVED.md"])[0])\n')
        rc, out, res = t.run(t.fresh(), [py, '-c', code])
        t.expect('T-017: proofs/HOWTO.md is frozen, and lands only with an approval record and proof.lock',
                 'FROZEN True' in out and "BARE ['frozen" in out and 'OK []' in out, out)

    # ---- bounded proofs (Zach, 2026-11-11, evidence/approvals/C-15-bounded/): scan rule 16, results, native, gate
    if want('bounds'):
        def bscan(rr):
            return t.run(rr, [py, 'tools/scan.py'])

        def edit(rr, rel, old, new):
            text = open(os.path.join(rr, rel)).read()
            assert old in text, (rel, old)
            t.write(rr, rel, text.replace(old, new, 1))

        r = bounds_repo(t)
        rc, out, res = bscan(r)
        t.expect('bounds: an end-exact and a start-exact bounded proof, with their BOUNDS assumes and buffers, both labels '
                 'and a native test, pass scan', rc == 0 and 'PASS' in res, out)
        # without a BOUNDS entry: every constant upper bound on an input of the call under proof fails
        def unbounded():
            return bounds_repo(t, '{}', UNB_HARNESS, UNB_MK)
        r = bounds_repo(t, '{}', UNB_HARNESS.replace('  __CPROVER_assume(n >= 0);', '  __CPROVER_assume(n >= 0);\n  __CPROVER_assume(n <= 64);'), UNB_MK)
        rc, out, res = bscan(r)
        t.expect('bounds: without a BOUNDS entry, a constant bound on a call argument fails, and tests/bounded/ may hold '
                 'nothing', rc != 0 and 'a constant upper bound on n,' in out and 'tests/bounded/ holds only' in out, out)
        for name, old, new, who in (
                ('a bound on a field of the object passed', '  r->n = m;', '  r->n = m;\n  __CPROVER_assume(m < 9);', 'm'),
                ('a bound on a local that a field is set from', '  r->n = m;', '  r->n = k;\n  k = m;\n  __CPROVER_assume(m <= 8);', 'm'),
                ('a bound on a field set through an alias', '  r->n = m;', '  q = r;\n  q->n = j;\n  __CPROVER_assume(j <= 8);', 'j'),
                ('a negated bound in a conjunction', '  __CPROVER_assume(m >= 0);', '  __CPROVER_assume(m >= 0 && !(m > 8));', 'm'),
                ('a bound with the constant on the left', '  __CPROVER_assume(m >= 0);', '  __CPROVER_assume(8 >= m);', 'm'),
                ('an equality', '  __CPROVER_assume(m >= 0);', '  __CPROVER_assume(m == 4);', 'm')):
            rr = unbounded()
            os.remove(os.path.join(rr, 'tests', 'bounded', 'C-92-1.c'))
            edit(rr, 'proofs/C-92/harness.c', '  int m;\n', '  int m, k, j;\n  Rec *q;\n')
            edit(rr, 'proofs/C-92/harness.c', old, new)
            rc, out, res = bscan(rr)
            t.expect('bounds: scan rejects %s, an input of the call under proof' % name,
                     rc != 0 and 'a constant upper bound on %s,' % who in out, out)
        for name, old, new in (
                ('a lower bound only', '', ''),
                ('a bound on an allocation\'s size in an unbounded proof (as C-01\'s extent)',
                 '  z = malloc(m);', '  size_t ext;\n  z = malloc(ext);\n  __CPROVER_assume(ext <= 80);'),
                ('a bound on a pointer\'s offset in `x + y`', '  toySum(p, n);', '  toySum(p + k, n);'),
                ('a bound on a field of an object the call never sees', '  r->n = m;',
                 '  r->n = m;\n  Rec *other;\n  int j;\n  other = malloc(sizeof(Rec));\n  __CPROVER_assume(other != 0);\n'
                 '  other->n = j;\n  __CPROVER_assume(j <= 3);')):
            rr = unbounded()
            os.remove(os.path.join(rr, 'tests', 'bounded', 'C-92-1.c'))
            if new.startswith('  toySum(p + k'):
                edit(rr, 'proofs/C-92/harness.c', '  int n;\n', '  int n, k;\n')
                edit(rr, 'proofs/C-92/harness.c', '  p = malloc(n);', '  p = malloc(n + 1);\n  __CPROVER_assume(k >= 0 && k <= 1);')
            if old:
                edit(rr, 'proofs/C-92/harness.c', old, new)
            rc, out, res = bscan(rr)
            t.expect('bounds: scan passes %s' % name, rc == 0 and 'PASS' in res, out)
        # a bounded proof: its bounds as BOUNDS gives them, one of the two allocation shapes, labels and a native test
        H = 'proofs/C-92/harness.c'
        for name, bounds, change, want_text in (
                ('BOUNDS giving another K', "{'C-92': %s}" % bspec(k=32), None, 'exactly once (found 0)'),
                ('the bound inside a conjunction', None, ('  __CPROVER_assume(n >= 0);\n  __CPROVER_assume(n <= 64);',
                 '  __CPROVER_assume(n >= 0 && n <= 64);'), 'exactly once (found 0)'),
                ('the bound twice', None, ('  __CPROVER_assume(n <= 64);', '  __CPROVER_assume(n <= 64);\n  __CPROVER_assume(n <= 64);'),
                 'exactly once (found 2)'),
                ('a second, tighter bound', None, ('  __CPROVER_assume(n <= 64);', '  __CPROVER_assume(n <= 64);\n  __CPROVER_assume(n < 10);'),
                 'a constant upper bound on n,'),
                ('an allocation that is neither one object nor a BOUNDS buffer', None,
                 ('  p = buf + off;', '  p = buf + off;\n  u8 *q = malloc(32);'), 'allocates only single objects'),
                ('its buffer allocated at another size', None, ('  buf = malloc(64);', '  buf = malloc(65);'),
                 'which SETUP must hold exactly once (found 0)'),
                ('its BOUNDS buffer allocated at a variable size', None, ('  buf = malloc(64);', '  buf = malloc(n);'),
                 'which SETUP must hold exactly once (found 0)'),
                ('a bound on an allocation\'s size', None, ('  buf = malloc(64);', '  size_t ext;\n  __CPROVER_assume(ext <= 80);\n  buf = malloc(ext);'),
                 'a constant upper bound on ext,'),
                ('an end-exact offset of 0', None, ('  off = (64) - (n);', '  off = 0;'), 'an end-exact proof sets off exactly once, to `(64) - (n)`'),
                ('a start-exact offset of size minus extent', None, ('  off = 0;', '  off = (64) - (n);'), 'a start-exact proof sets off exactly once, to `0`'),
                ('the offset set twice', None, ('  off = (64) - (n);', '  off = (64) - (n);\n  off = (64) - (n);'), 'exactly once, to'),
                ('the buffer used with another offset', None, ('  p = buf + off;', '  p = buf + 1;'), 'is used only as `buf + off`'),
                ('the label missing from the card', None, ('cards/C-92.md', ' ' + BOUNDS_LINE + ';', ''), 'cards/C-92.md: a bounded proof is labelled here'),
                ('the label missing from PROPERTIES.md', None, ('PROPERTIES.md', BOUNDS_LINE + '\n', 'C-92 sum: bounded\n'),
                 'PROPERTIES.md: a bounded proof is labelled here'),
                ('no native test', None, 'rm', 'needs a native test past the bound'),
                ('a native test named for another card', None, 'stray', 'tests/bounded/ holds only'),
                ('a symlinked native test', None, 'link', 'symlink not allowed'),
                ('BOUNDS naming a proof the Makefile lacks', "{'C-92': %s}" % bspec().replace(
                    "{'sum':", "{'nope': {'bounds': (('m', 1, 'm'),), 'exact': 'end', 'buffers': ()}, 'sum':"), None, 'which the Makefile lacks')):
            rr = bounds_repo(t, bounds or BOUNDS_DEFAULT)
            if change == 'rm':
                os.remove(os.path.join(rr, 'tests', 'bounded', 'C-92-1.c'))
            elif change == 'stray':
                t.write(rr, 'tests/bounded/C-93-1.c', BOUNDS_NATIVE)
            elif change == 'link':
                os.symlink('C-92-1.c', os.path.join(rr, 'tests', 'bounded', 'C-92-2.c'))
            elif change and len(change) == 3:
                edit(rr, change[0], change[1], change[2])
            elif change:
                edit(rr, H, change[0], change[1])
            rc, out, res = bscan(rr)
            t.expect('bounds: scan rejects a bounded proof with %s' % name, rc != 0 and want_text in out, out)
        rr = bounds_repo(t)
        shutil.rmtree(os.path.join(rr, 'proofs', 'C-92'))
        os.remove(os.path.join(rr, 'tests', 'bounded', 'C-92-1.c'))
        rc, out, res = bscan(rr)
        t.expect('bounds: a bounded card with no proofs yet (before its builder\'s round) needs only its labels',
                 rc == 0 and 'PASS' in res, out)
        rr = bounds_repo(t)
        edit(rr, H, '  p = buf + off;', '  Rec *one;\n  one = malloc(sizeof(Rec));\n  p = buf + off;')
        rc, out, res = bscan(rr)
        t.expect('bounds: a bounded proof may also allocate one object, sizeof(T)', rc == 0 and 'PASS' in res, out)
        # the two shapes in CBMC: a planted underread passes the end-exact proof and fails the start-exact one; a planted
        # overread does the opposite; without a plant both pass
        r = peek_repo(t)
        import json as _json

        def peek_status(rr, ov):
            t.run(rr, [py, 'tools/prove.py', 'prove', '--card-dir', 'proofs/C-93', '--config', 'lp64-le', '--overlay', ov,
                       '--build-dir', 'tmp/peek-' + ov])
            st = {}
            for pn in ('peek', 'peek_start'):
                j = os.path.join(rr, 'tmp', 'peek-' + ov, 'lp64-le', pn + '.json')
                st[pn] = _json.load(open(j)).get('status') if os.path.exists(j) else 'none'
            return st
        st0, stu, sto = peek_status(r, 'overlay'), peek_status(r, 'overlay-under'), peek_status(r, 'overlay-over')
        t.expect('bounds: with no plant, the end-exact and the start-exact proof both pass', st0 == {'peek': 'PASS', 'peek_start': 'PASS'}, str(st0))
        t.expect('bounds: a planted underread passes the end-exact proof and fails the start-exact one',
                 stu == {'peek': 'PASS', 'peek_start': 'FAIL'}, str(stu))
        t.expect('bounds: a planted overread fails the end-exact proof and passes the start-exact one',
                 sto == {'peek': 'FAIL', 'peek_start': 'PASS'}, str(sto))
        rc, out, res = bscan(r)
        t.expect('bounds: the underread toy\'s two proofs pass scan', rc == 0 and 'PASS' in res, out)
        # results.py: the Bounds and Assigns columns
        r = bounds_repo(t)
        rec = {'prove_summary': [{'proof': p_, 'config': 'lp64-le', 'status': 'PASS', 'cbmc_seconds': 1, 'properties': 9,
                                  'failed': 0} for p_ in ('sum', 'sum_start', 'rec')], 'coverage_summary': [], 'mutants': [], 'provenance': {}}
        t.write(r, 'evidence/results/C-92.json', _json.dumps(rec))
        rc, out, res = t.run(r, [py, 'tools/results.py', '--root', r])
        csvt = open(os.path.join(r, 'results.csv')).read() if os.path.exists(os.path.join(r, 'results.csv')) else ''
        mdt = open(os.path.join(r, 'RESULTS.md')).read() if os.path.exists(os.path.join(r, 'RESULTS.md')) else ''
        rows_ = list(csv.DictReader(io.StringIO(csvt)))
        t.expect('bounds: results.csv and RESULTS.md carry each bounded proof\'s label, and only its rows',
                 rc == 0 and [x.get('bounds') for x in rows_] == ['bounded: n <= 64', 'bounded: n <= 64', '']
                 and '| bounded: n <= 64 |' in mdt and '| Bounds | Assigns |' in mdt, out + csvt + mdt)
        # tools/native.py, in campaign.py's repro sandbox
        r = bounds_repo(t)
        nat = lambda rr, c='C-92': t.run(rr, [py, 'tools/native.py', '--card', c], timeout=3600)  # noqa: E731
        rc, out, res = nat(r)
        t.expect('bounds: native.py builds and runs a bounded card\'s native test, which passes',
                 rc == 0 and res == 'RESULT native C-92 PASS 1 tests 0 failed'
                 and os.path.exists(os.path.join(r, 'proofs', 'C-92', 'build', 'native', 'C-92-1.txt')), out)
        t.write(r, 'tests/bounded/C-92-2.c', BOUNDS_NATIVE.replace('toySum(p, n)', 'toySum(p, n + 1)'))
        t.write(r, 'tests/bounded/C-92-3.c', BOUNDS_NATIVE.replace('return 0;\n}', 'return 3;\n}'))
        rc, out, res = nat(r)
        t.expect('bounds: native.py fails a test that overreads (a sanitizer report) and one that exits nonzero',
                 rc != 0 and res == 'RESULT native C-92 FAIL 3 tests 2 failed' and 'C-92-2.c FAIL' in out
                 and 'sanitizer report' in out and 'C-92-3.c FAIL: build exit 0, run exit 3' in out, out)
        for n_ in ('C-92-1.c', 'C-92-2.c', 'C-92-3.c'):
            os.remove(os.path.join(r, 'tests', 'bounded', n_))
        rc, out, res = nat(r)
        rc2, out2, res2 = nat(r, 'C-90')
        t.expect('bounds: native.py fails a bounded card with no test, and a card BOUNDS doesn\'t name',
                 rc != 0 and 'FAIL 0 tests' in res and rc2 != 0 and 'not in tools/prove.py BOUNDS' in out2, out + out2)
        # the gate runs the native step for a bounded card
        r = bounds_repo(t)
        t.write(r, 'Makefile', open(os.path.join(REPO, 'Makefile')).read())
        rc, out, res = t.run(r, [py, 'tools/gate.py', 'gate', '--card', 'C-92'], timeout=3600)
        t.expect('bounds: make gate CARD=C-92 runs its native tests as a step (native C-92 PASS)',
                 re.search(r'^  native C-92\s+PASS', out, re.M) is not None, out)
        # T-015: prove.py's legacy frame check, on T-015's toy
        def t015(card, frame, write, pre='', head=None):
            rr = t015_repo(t, card, frame, write, pre, head)
            rc_, out_, res_ = t.run(rr, [py, 'tools/prove.py', 'prove', '--card-dir', 'proofs/' + card, '--config', 'lp64-le',
                                         '--build-dir', 'proofs/%s/build' % card])
            return rc_, out_, res_, legacy_failures(rr, card, 'f')
        rc, out, res, _ = t015('C-17', '__CPROVER_object_from(p)', 'b')
        t.expect('T-015: a legacy build fails when a loop assigns a target that is neither a local nor among the function\'s '
                 'assigns (the bad toy: object_from(p))', rc != 0 and 'legacy loop frame (T-015)' in out
                 and '__CPROVER_object_from(p)' in out, out[-1200:])
        rc, out, res, _ = t015('C-17', 'cells[0].a, cells[n-1].a', 'a')
        t.expect('T-015: the good toy, whose loop frame is the function\'s own targets, passes the check and proves',
                 rc == 0 and 'PASS' in res, out[-1200:])
        rc, out, res, fails = t015('C-17', 'cells[0].a, cells[n-1].a', 'b')
        t.expect('T-015: with that frame, a body write outside it fails by CBMC\'s own check',
                 rc != 0 and any('assignable' in f_ for f_ in fails), out[-800:] + str(fails))
        rc, out, res, _ = t015('C-15', '__CPROVER_object_from(p)', 'b')
        t.expect('T-015 pin: for a card that argues its frame (C-15, LEGACY_FRAME_ARGUED), the legacy engine still passes a '
                 'write outside the function\'s assigns inside a wider loop frame; a CBMC that catches it fails this test',
                 rc == 0 and 'PASS' in res, out[-1200:])
        # follow-up 1: a conditional target matches only under the same condition; a name the body reassigns refuses a match
        HC = T015_HEAD.replace('__CPROVER_assigns(cells[0].a, cells[n-1].a)', '__CPROVER_assigns(cells[0].a; n > 1: cells[1].a)')
        rc, out, res, _ = t015('C-17', 'cells[0].a, cells[1].a', 'a', head=HC)
        t.expect('T-015 follow-up: a loop target matching a conditional function target (`n > 1: cells[1].a`) without '
                 'its condition fails the build', rc != 0 and 'legacy loop frame (T-015)' in out
                 and 'under the same condition' in out, out[-1200:])
        rc, out, res, _ = t015('C-17', 'cells[0].a; n > 1: cells[1].a', 'a', head=HC)
        t.expect('T-015 follow-up: the same target under the same condition passes the check',
                 'legacy loop frame (T-015)' not in out, out[-1200:])
        rc, out, res, _ = t015('C-17', 'cells[0].a, cells[n-1].a', 'a', pre='  if( n>1 ) n = 1;\n')
        t.expect('T-015 follow-up: a verbatim match fails the build when the body reassigns a name it uses '
                 '(the parameter n, before the loop)', rc != 0 and 'legacy loop frame (T-015)' in out
                 and 'assigns n, which it names' in out, out[-1200:])
        # follow-up 2: named tail terms, and why each buffer is exactly as large as the largest extent
        rr = bounds_repo(t)
        edit(rr, H, '  p = buf + off;', '  size_t z0;\n  z0 = 0;\n  p = buf + off + z0;')
        rc, out, res = bscan(rr)
        t.expect('T-015 follow-up: a tail term after buffer + offset that BOUNDS doesn\'t name fails scan, even a constant',
                 rc != 0 and 'then the tail terms BOUNDS names (none)' in out, out)
        rr = bounds_repo(t, "{'C-92': %s}" % bspec(tails="('z0',)"))
        edit(rr, H, '  p = buf + off;', '  size_t z0;\n  z0 = 0;\n  p = buf + off + z0;')
        edit(rr, H, '  p = buf + off;', '  size_t z0;\n  z0 = 0;\n  p = buf + off + z0;')
        rc, out, res = bscan(rr)
        t.expect('T-015 follow-up: a tail term BOUNDS names, a constant local, passes scan', rc == 0 and 'PASS' in res, out)

        def shift_run(shift):
            rr = shift_repo(t, shift)
            pr = t.run(rr, [py, 'tools/prove.py', 'prove', '--card-dir', 'proofs/C-94', '--config', 'lp64-le',
                            '--build-dir', 'proofs/C-94/build'])
            cv = t.run(rr, [py, 'tools/prove.py', 'coverage', '--card-dir', 'proofs/C-94', '--config', 'lp64-le',
                            '--build-dir', 'proofs/C-94/build'])
            return pr, cv
        (prc, pout, pres), (crc, cout, cres) = shift_run('')
        t.expect('bounds shift control: the end-exact pointer with no shift proves and covers every line',
                 prc == 0 and 'PASS' in pres and crc == 0 and 'PASS' in cres, pout[-600:] + cout[-600:])
        (prc, pout, pres), (crc, cout, cres) = shift_run(' - 1')
        t.expect('bounds shift: a constant -1 shift fails the proof (at the largest n the pointer leaves the buffer)',
                 prc != 0 and 'FAIL' in pres, pout[-800:])
        (prc, pout, pres), (crc, cout, cres) = shift_run(' + 1')
        t.expect('bounds shift: a constant +1 shift fails coverage (every input lacks a byte the requires asks for, so the '
                 'proof passes vacuously)', prc == 0 and 'PASS' in pres and crc != 0 and 'FAIL' in cres, pout[-600:] + cout[-800:])

    # ---- C-17's package (Zach, 2026-11-11, evidence/approvals/C-17-bounded/)
    if want('c17'):
        import json as _json

        def prv(rr, card):
            return t.run(rr, [py, 'tools/prove.py', 'prove', '--card-dir', 'proofs/' + card, '--config', 'lp64-le',
                              '--build-dir', 'proofs/%s/build' % card])

        def edit(rr, rel, old, new):
            text = open(os.path.join(rr, rel)).read()
            assert old in text, (rel, old)
            t.write(rr, rel, text.replace(old, new, 1))
        # the legacy-unwind pass
        r = unwind_repo(t)
        rc, out, res = prv(r, 'C-17')
        t.expect('legacy-unwind: a legacy proof with LOOPS := unwind is unwound (with --unwinding-assertions) before '
                 'enforcement, and proves', rc == 0 and 'PASS' in res
                 and os.path.exists(os.path.join(r, 'proofs', 'C-17', 'build', 'lp64-le', 'u.legacy-unwind')), out[-1200:])
        r = unwind_repo(t, nmax=3)
        rc, out, res = prv(r, 'C-17')
        fs = legacy_failures(r, 'C-17', 'u')
        t.expect('legacy-unwind: a harness allowing n = K+1 fails by the unwinding assertion',
                 rc != 0 and any('unwinding assertion' in f for f in fs), out[-1000:] + str(fs))
        r = unwind_repo(t, unwindset=None)
        rc, out, res = prv(r, 'C-17')
        t.expect('legacy-unwind: a legacy LOOPS := unwind proof without an UNWINDSET is refused',
                 rc != 0 and 'needs u_UNWINDSET' in out, out[-800:])
        r = unwind_repo(t, frame='cells[0].a')
        rc, out, res = prv(r, 'C-17')
        fs = legacy_failures(r, 'C-17', 'u')
        t.expect('legacy-unwind: with the loop unwound, a write outside the function\'s assigns fails enforcement',
                 rc != 0 and any('assignable' in f for f in fs), out[-1000:] + str(fs))
        # scan's aColl rule
        for name, change, ok, needle in (
                ('the aColl store of a CollSeq', None, True, ''),
                ('the aColl store of 0 (it fixes the entry as NULL; --malloc-may-fail already gives NULL or valid)',
                 ('  c0 = malloc(sizeof(CollSeq));', '  c0 = 0;'), False, 'malloc(sizeof(CollSeq))'),
                ('another member', ('  key->aColl[i0] = c0;', '  key->aSortFlags[i0] = c0;'), False, 'key->aSortFlags[i0] = c0'),
                ('a data value', ('  c0 = malloc(sizeof(CollSeq));', '  c0 = malloc(8);'), False, 'malloc(sizeof(CollSeq))'),
                ('a literal on the right', ('  key->aColl[i0] = c0;', '  key->aColl[i0] = 0;'), False, 'key->aColl[i0] = 0'),
                ('a shared right-hand side', ('  key->aColl[i0] = c0;', '  key->aColl[i0] = c0;\n  key->aColl[i0] = c0;'), False,
                 'stored into aColl 2 times'),
                ('its right-hand side set twice', ('  c0 = malloc(sizeof(CollSeq));', '  c0 = malloc(sizeof(CollSeq));\n  c0 = 0;'),
                 False, 'malloc(sizeof(CollSeq))')):
            rr = k_repo(t)
            if change:
                edit(rr, 'proofs/C-96/harness.c', change[0], change[1])
            rc, out, res = t.run(rr, [py, 'tools/scan.py'])
            t.expect('scan aColl: %s %s' % ('passes' if ok else 'rejects', name),
                     (rc == 0 and 'PASS' in res) if ok else (rc != 0 and needle in out), out)
        # rule 16: exact symbolic allocations, fixed inputs, card-wide and '*' labels
        def b16(spec, harness, lines=None, card_label=None):
            rr = bounds_repo(t, "{'C-92': %s}" % spec, harness, UNB_MK)
            os.remove(os.path.join(rr, 'tests', 'bounded', 'C-92-1.c'))
            t.write(rr, 'tests/bounded/C-92-1.c', BOUNDS_NATIVE)
            ls = lines if lines is not None else []
            t.write(rr, 'cards/C-92.md', card_md('C-92', ['toySum', 'toyRec'], src=BOUNDS_TOY).replace(
                '- Notes: toy\n', '- Notes: toy. %s\n' % '; '.join(ls)))
            t.write(rr, 'PROPERTIES.md', '# PROPERTIES\n\n' + ''.join('- %s\n' % x for x in ls))
            return t.run(rr, [py, 'tools/scan.py'])
        BH = UNB_HARNESS.replace('  __CPROVER_assume(n >= 0);', '  __CPROVER_assume(n >= 0);\n  __CPROVER_assume(n <= 64);')
        SP = "{'sum': {'bounds': (('n', 64, 'n'),)}, 'rec': {'bounds': (('m', 9, 'm'),)}}"
        BH2 = BH.replace('  __CPROVER_assume(m >= 0);', '  __CPROVER_assume(m >= 0);\n  __CPROVER_assume(m <= 9);')
        L2 = ['C-92 rec: bounded: m <= 9', 'C-92 sum: bounded: n <= 64']
        rc, out, res = b16(SP, BH2, L2)
        t.expect('rule 16: a bounded proof may allocate exactly at a symbolic size, malloc(<input local>)', rc == 0 and 'PASS' in res, out)
        rc, out, res = b16(SP, BH2.replace('  p = malloc(n);', '  p = malloc(sizeof(u8) * n);'), L2)
        t.expect('rule 16: ... and malloc(sizeof(T) * <input local>)', rc == 0 and 'PASS' in res, out)
        rc, out, res = b16(SP, BH2.replace('  p = malloc(n);', '  p = malloc(n + 1);'), L2)
        t.expect('rule 16: a bounded proof\'s inexact symbolic allocation, malloc(n + 1), is refused',
                 rc != 0 and 'exact symbolic sizes' in out, out)
        FX = "{'sum': {'fixed': (('n', 5, 'n'),)}, 'rec': {'bounds': (('m', 9, 'm'),)}}"
        LF = ['C-92 rec: bounded: m <= 9', 'C-92 sum: bounded: n = 5']
        rc, out, res = b16(FX, BH2.replace('  __CPROVER_assume(n <= 64);', '  n = 5;'), LF)
        t.expect('rule 16: an input fixed as BOUNDS gives it (`n = 5;`) passes', rc == 0 and 'PASS' in res, out)
        rc, out, res = b16(FX, BH2.replace('  __CPROVER_assume(n <= 64);', '  n = 6;'), LF)
        t.expect('rule 16: an input fixed to another value fails', rc != 0 and 'exactly once (found 0)' in out
                 and 'a constant value for n' in out, out)
        r = bounds_repo(t, '{}', UNB_HARNESS.replace('  __CPROVER_assume(n >= 0);', '  n = 5;'), UNB_MK)
        os.remove(os.path.join(r, 'tests', 'bounded', 'C-92-1.c'))
        rc, out, res = t.run(r, [py, 'tools/scan.py'])
        t.expect('rule 16: in an unbounded proof, a constant value for an input fails, as a bound would',
                 rc != 0 and 'a constant value for n' in out, out)
        CW = SP[:-1] + ", '_label': 'bounded: n <= 64 and m <= 9'}"
        rc, out, res = b16(CW, BH2, L2)
        t.expect('rule 16: a card-wide _label replaces the per-proof lines, which then do not do',
                 rc != 0 and 'C-92: bounded: n <= 64 and m <= 9' in out, out)
        rc, out, res = b16(CW, BH2, ['C-92: bounded: n <= 64 and m <= 9'])
        t.expect('rule 16: ... and with the card-wide line, scan passes', rc == 0 and 'PASS' in res, out)
        ST = "{'*': {'bounds': (('n', 64, 'n'),), 'via': 'C-17'}, '_label': \"bounded: n <= 64 (through C-17's contract)\"}"
        rc, out, res = b16(ST, BH, ["C-92: bounded: n <= 64 (through C-17's contract)"])
        t.expect('rule 16: a card\'s \'*\' entry binds every proof of it (rec lacks n <= 64)',
                 rc != 0 and 'rec: tools/prove.py BOUNDS gives n <= 64' in out, out)
        # the F-001 exception table, on a toy
        r = neg_repo(t)
        rc, out, res = prv(r, 'C-97')
        j = os.path.join(r, 'proofs', 'C-97', 'build', 'lp64-le', 'neg.json')
        jj = _json.load(open(j)) if os.path.exists(j) else {}
        t.expect('exception: a proof whose only failure is the excepted one passes, and records it',
                 rc == 0 and 'PASS' in res and 'EXCEPTED neg' in out and len(jj.get('excepted') or []) >= 1 and jj.get('failed') == 0, out[-1000:])
        r = neg_repo(t, post='  int y = rc + 1;\n  (void)y;\n')
        rc, out, res = prv(r, 'C-97')
        t.expect('exception: any other failure fails the proof', rc != 0 and 'FAIL' in res, out[-800:])
        r = neg_repo(t, pre='  __CPROVER_assume(rc != -2147483647 - 1);\n')
        rc, out, res = prv(r, 'C-97')
        t.expect('exception: a configuration where no proof fails the excepted check fails (the table no longer matches)',
                 rc != 0 and 'no proof failed the excepted F-T check' in out, out[-800:])
        r = neg_repo(t)
        mj = os.path.join(r, 'm.json')
        rc, out, res = t.run(r, [py, 'tools/mutate.py', '--card', 'C-97', '--config', 'lp64-le', '--json', mj], timeout=1800)
        mv = {x['mutant']['id']: x['verdict'] for x in _json.load(open(mj))} if os.path.exists(mj) else {}
        t.expect('exception in mutate.py: an unchanged mutant (whitespace) is not killed by the excepted failure; a mutant '
                 'adding another failure is killed', mv.get('M-901') == 'SURVIVED' and mv.get('M-902') == 'KILLED', out[-1200:] + str(mv))
        rr = neg_repo(t)
        rec = {'prove_summary': [{'proof': 'neg', 'config': 'lp64-le', 'status': 'PASS', 'cbmc_seconds': 1, 'properties': 9,
                                  'failed': 0, 'excepted': [{'id': 'toyNeg.overflow.1'}]}], 'coverage_summary': [], 'mutants': [], 'provenance': {}}
        t.write(rr, 'evidence/results/C-97.json', _json.dumps(rec))
        rc, out, res = t.run(rr, [py, 'tools/results.py', '--root', rr])
        mdt = open(os.path.join(rr, 'RESULTS.md')).read() if os.path.exists(os.path.join(rr, 'RESULTS.md')) else ''
        t.expect('exception in results.py: the row reads "PASS (proved except F-T at <line>)"',
                 rc == 0 and '| PASS (proved except F-T at %d) |' % line_of(C17_TOY, '  return -rc;') in mdt, out + mdt)
        rr = neg_repo(t)
        edit(rr, 'cards/C-97.md', ' proved except F-T at', ' proved but F-T at')
        rc, out, res = t.run(rr, [py, 'tools/scan.py'])
        t.expect('exception in scan: the card must say "proved except F-T at <line>"', rc != 0 and 'a card with an excepted failure says so' in out, out)

    # ---- finding-review (Zach, 2026-11-11): a one-off Codex judgement of F-002 and F-001's second repro
    if want('finding'):
        code = ('import sys; sys.path.insert(0, "tools"); import campaign as C\n'
                's = C.load_sessions(".")\n'
                'print("CFG", C.role_config(s, "finding-review", "high")[:3])\n'
                'print("PATHS", C.ROLE_PATHS["finding-review"])\n'
                'pr = C.prompt_oneoff("finding-review", 1)\n'
                'print("PROMPT", all(x in pr for x in ("F-002", "tests/repro/F-001-b.c", "evidence/orchestrator/F-002/", '
                '"evidence/orchestrator/F-001-b/run.txt", "reviews/finding-r1.md", "Do not modify any tracked file", '
                '"campaign-control.txt", "Rebuild and run its repro and its clean control")))\n')
        r = t.fresh()
        shutil.copy(os.path.join(REPO, 'tools', 'sessions.toml'), os.path.join(r, 'tools', 'sessions.toml'))
        rc, out, res = t.run(r, [py, '-c', code])
        t.expect('finding-review: a one-off role on Codex (gpt-6-astra, xhigh) that writes only reviews/finding-, and its '
                 'prompt names F-002, F-001-b, their evidence and its verdict file',
                 "CFG ('codex', 'gpt-6-astra', 'xhigh')" in out and "PATHS ['reviews/finding-']" in out and 'PROMPT True' in out, out)

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
