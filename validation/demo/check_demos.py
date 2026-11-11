"""Check validation/demo results: each deliberate violation is logged with
its entry and kind, and each control logs nothing.  Prints one line per
case and a final RESULT line."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
import ledgerlib as L

OUT = sys.argv[1]
# (build, case) -> list of (entry, substring of args) that must be logged.
# Nothing else may be logged.
EXPECT = {
  'asan': {
    'a001_control': [],
    'a001_slack': [('A-001', 'kind=slack nKey=3 '), ('A-001', 'kind=slack nKey=0 ')],
    'a001_overread': [('A-001', 'kind=slack nKey=2 ')],
    'a001_negative': [('A-001', 'kind=nKey_negative')],
    'a002_control': [],
    'a002_misaligned': [('A-002', 'aligned8=0')],
    'a002_short': [('A-002', 'DbMallocSize=72')],
    'a003_control': [],
    'a003_assigns': [('A-003', 'kind=assigns')],
    'a003_requires': [('A-003', 'site=vdbeCompareMemString@C-17-call kind=requires'),
                      ('A-003', 'site=vdbeCompareMemString@entry kind=requires')],
    'a004_control': [],
    'a004_assigns': [('A-004', 'kind=assigns changed=*pPKey2;')],
    'a004_rc': [('A-004', 'kind=return rc=0')],
    'a005_control': [],
    'a005_heap1': [('A-005', 'site=sqlite3PutVarint p=')],
    'a005_heap3': [('A-005', 'site=sqlite3PutVarint p='), ('A-005', 'site=putVarint64 p=')],
    'a005_stack': [('A-005', 'site=sqlite3PutVarint p='), ('A-005', 'site=putVarint64 p=')],
  },
}
# Without ASan only the field checks can fire.
EXPECT['plain'] = {k: [] for k in EXPECT['asan']}
EXPECT['plain'].update({
    'a001_negative': [('A-001', 'kind=nKey_negative')],
    'a002_misaligned': [('A-002', 'aligned8=0')],
    'a002_short': [('A-002', 'DbMallocSize=72')],
    'a003_assigns': [('A-003', 'kind=assigns')],
    'a003_requires': EXPECT['asan']['a003_requires'],
    'a004_assigns': [('A-004', 'kind=assigns changed=*pPKey2;')],
    'a004_rc': [('A-004', 'kind=return rc=0')],
})
# Counters that must be non-zero in each case (the site was reached).
REACH = {'a001': 'LC_A001_REACHED', 'a002': 'LC_A002_REACHED',
         'a003': 'LC_A003_REACHED', 'a004': 'LC_A004_REACHED',
         'a005': 'LC_A005_REACHED'}

bad = 0
for build in ('asan', 'plain'):
    for case, exp in EXPECT[build].items():
        d = os.path.join(OUT, build, case)
        recs = L.read_violations(d)
        cnt = L.total(L.read_counter_dir(d))
        got = [(r['entry'], r.get('args', '')) for r in recs]
        missing = [e for e in exp if not any(g[0] == e[0] and e[1] in g[1] for g in got)]
        extra = [g for g in got if not any(g[0] == e[0] and e[1] in g[1] for e in exp)]
        reached = cnt.get(REACH[case[:4]], 0)
        asan_err = 'AddressSanitizer' in open(os.path.join(d, 'stderr.txt'), errors='replace').read()
        ok = not missing and not extra and reached > 0
        if case == 'a001_overread' and build == 'asan':
            ok = ok and asan_err      # the real overread follows the log
        bad += not ok
        print('%-5s %-16s %s logged=%d reached(%s)=%d asan_report=%s%s%s' % (
            build, case, 'PASS' if ok else 'FAIL', len(got), REACH[case[:4]],
            reached, asan_err,
            (' missing=%r' % missing) if missing else '',
            (' extra=%r' % extra) if extra else ''))
print('RESULT demos: %s (%d failing)' % ('PASS' if bad == 0 else 'FAIL', bad))
sys.exit(1 if bad else 0)
