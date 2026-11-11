"""Summarize ledger.patch evidence from one or more raw LEDGER_DIRs.

Usage: python3 -I ledger_summary.py OUT_DIR NAME=RAW_DIR [NAME=RAW_DIR ...]
Writes OUT_DIR/summary.json, OUT_DIR/summary.md, OUT_DIR/reach-<NAME>.tsv
(per build and test file: the counters each reached) and
OUT_DIR/violations-<NAME>.txt (every logged record, verbatim fields).
"""
import os, sys, re, json, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledgerlib as L

ENTRIES = {
  'A-001': dict(reached='LC_A001_REACHED', asan='LC_A001_ASAN_CHECKED',
                viol=['LC_A001_VIOL'],
                kinds=['LC_A001_VIOL_NKEY_NEG', 'LC_A001_VIOL_NULL',
                       'LC_A001_VIOL_RECORD', 'LC_A001_VIOL_SLACK'],
                hist=['LH_A001', 'LH_A001_N0'],
                site='sqlite3VdbeRecordUnpack entry'),
  'A-002': dict(reached='LC_A002_REACHED', asan='LC_A002_ASAN_CHECKED',
                viol=['LC_A002_VIOL'],
                kinds=['LC_A002_VIOL_ALIGN', 'LC_A002_VIOL_SIZE',
                       'LC_A002_VIOL_POISON', 'LC_A002_NULL'],
                hist=[], site='sqlite3DbMallocRaw return, in sqlite3VdbeAllocUnpackedRecord'),
  'A-003 (C-17 call site)': dict(reached='LC_A003_REACHED', asan='LC_A003_ASAN_CHECKED',
                viol=['LC_A003_VIOL_REQ', 'LC_A003_VIOL_ASSIGNS'],
                kinds=['LC_A003_ASSIGNS_CHECKED', 'LC_A003_ENCCHANGE',
                       'LC_A003_PRCERR_WRITTEN', 'LC_A003_ZNULL_N0'],
                hist=[], site='vdbeCompareMemString call in sqlite3VdbeRecordCompareWithSkip'),
  'A-003 requires (entry, all callers)': dict(reached='LC_A003E_REACHED', asan='LC_A003E_ASAN_CHECKED',
                viol=['LC_A003E_VIOL'], kinds=['LC_A003E_ZNULL_N0'],
                hist=[], site='vdbeCompareMemString entry'),
  'A-004': dict(reached='LC_A004_REACHED', asan=None,
                viol=['LC_A004_VIOL_RC', 'LC_A004_VIOL_ASSIGNS'],
                kinds=['LC_A004_ASSIGNS_CHECKED', 'LC_A004_XLOG_SET'],
                hist=[], site='SQLITE_CORRUPT_BKPT in sqlite3VdbeRecordCompareWithSkip and vdbeRecordCompareString'),
  'A-005 (sqlite3PutVarint)': dict(reached='LC_A005_REACHED', asan='LC_A005_ASAN_CHECKED',
                viol=['LC_A005_VIOL'], kinds=['LC_A005_VIOL_NULL', 'LC_A005_REAL_OVERFLOW'],
                hist=['LH_A005'], site='sqlite3PutVarint entry'),
  'A-005 (putVarint64)': dict(reached='LC_A005P_REACHED', asan='LC_A005P_ASAN_CHECKED',
                viol=['LC_A005P_VIOL'], kinds=[], hist=['LH_A005P'],
                site='putVarint64 entry'),
  'comparator slack (measurement only)': dict(reached='LC_CMP_WITHSKIP', asan=None,
                viol=[], kinds=['LC_CMP_INT', 'LC_CMP_STRING'],
                hist=['LH_WITHSKIP', 'LH_INT', 'LH_STRING'],
                site='entries of sqlite3VdbeRecordCompareWithSkip, vdbeRecordCompareInt, vdbeRecordCompareString'),
}

def build_of(r):
    """A short build name from the executable path."""
    exe = r['exe']
    parts = exe.split('/')
    for p in parts:
        if p.startswith('testrunner_bld_'):
            return p[len('testrunner_bld_'):] + '/' + parts[-1]
    m = re.search(r'/run-([^/]+)/', exe)
    if m:
        return 'run-%s/%s' % (m.group(1), parts[-1])
    return exe

def testfile_of(r):
    toks = r['cmd'].split()
    tests = [os.path.basename(t) for t in toks if t.endswith(('.test', '.db', '.tcl'))]
    tests = [t for t in tests if t not in ('testrunner.tcl', 'testrunner_data.tcl')]
    return ' '.join(tests) if tests else os.path.basename(toks[0]) if toks else '?'

def flags_str(f):
    out = []
    for bit, name in ((1, 'asan'), (2, 'debug'), (4, 'omit-lookaside'), (8, 'memdebug'), (16, 'test')):
        if f & bit:
            out.append(name)
    return ','.join(out) or 'none'

def minbucket(h):
    for i, c in enumerate(h):
        if c:
            return i
    return None

def summarize(name, raw):
    recs = L.read_counter_dir(raw)
    viols = L.read_violations(raw)
    tot = L.total(recs)
    per_build = collections.defaultdict(collections.Counter)
    build_flags = {}
    reach_files = collections.defaultdict(set)   # counter -> {(build, testfile)}
    procs_build = collections.Counter()
    for r in recs:
        b = build_of(r)
        build_flags[b] = flags_str(r['flags'])
        procs_build[b] += 1
        per_build[b].update({k: v for k, v in r['counters'].items() if v})
        tf = testfile_of(r)
        for k, v in r['counters'].items():
            if v and not k.startswith('LH_'):
                reach_files[k].add((b, tf))
    entries = {}
    for ename, e in ENTRIES.items():
        d = dict(site=e['site'], reached=tot.get(e['reached'], 0),
                 asan_checked=tot.get(e['asan'], 0) if e['asan'] else None,
                 violations={k: tot.get(k, 0) for k in e['viol']},
                 detail={k: tot.get(k, 0) for k in e['kinds']},
                 test_files=len({tf for (b, tf) in reach_files.get(e['reached'], ())}),
                 builds={b: dict(flags=build_flags[b], reached=c.get(e['reached'], 0),
                                 asan_checked=c.get(e['asan'], 0) if e['asan'] else None,
                                 violations={k: c.get(k, 0) for k in e['viol']})
                         for b, c in sorted(per_build.items()) if c.get(e['reached'], 0)},
                 hist={})
        for h in e['hist']:
            hh = L.hist(tot, h)
            d['hist'][h] = dict(total=sum(hh), min=minbucket(hh),
                                nonzero={str(i): c for i, c in enumerate(hh) if c})
        entries[ename] = d
    # Violations grouped by entry, kind, and the first SQLite frames.
    groups = collections.defaultdict(list)
    for v in viols:
        a = L.parse_args(v.get('args', ''))
        frames = [re.sub(r'^#\d+ 0x[0-9a-f]+ in ', '', f) for f in v['bt'][1:9]]
        frames = [re.sub(r' /\S*/', ' ', f) for f in frames]
        key = (v['entry'], a.get('site', '?'), a.get('kind', '?'), tuple(frames[:5]))
        groups[key].append(v)
    vgroups = []
    for (ent, site, kind, fr), vs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        vgroups.append(dict(entry=ent, site=site, kind=kind, frames=list(fr), n_logged=len(vs),
                            tests=sorted({testfile_of(dict(cmd=v.get('cmd', ''))) for v in vs})[:20],
                            builds=sorted({build_of(dict(exe=v.get('exe', ''))) for v in vs}),
                            example_args=vs[0].get('args', '')))
    with open(os.path.join(OUT, 'reach-%s.tsv' % name), 'w') as f:
        f.write('counter\tbuild\ttest_file\n')
        for k in sorted(reach_files):
            for b, tf in sorted(reach_files[k]):
                f.write('%s\t%s\t%s\n' % (k, b, tf))
    with open(os.path.join(OUT, 'violations-%s.txt' % name), 'w') as f:
        for v in viols:
            f.write('=== %s\n' % v['entry'])
            for k in ('pid', 'exe', 'cwd', 'cmd', 'args'):
                f.write('%s: %s\n' % (k, v.get(k, '')))
            f.write('backtrace:\n')
            for b in v['bt']:
                f.write('  %s\n' % b)
    return dict(name=name, raw=raw, processes=len(recs), builds={b: dict(flags=build_flags[b], processes=procs_build[b]) for b in sorted(procs_build)},
                entries=entries, violation_records=len(viols), violation_groups=vgroups)

def md(results):
    out = ['# Ledger checks: summary', '',
           'Generated by validation/tools/ledger_summary.py from the raw counter files and violation logs.',
           'Counts are *tested* evidence: how often each check ran and failed in these runs, nothing more.', '']
    for res in results:
        out.append('## Run `%s` (%d processes wrote counters)' % (res['name'], res['processes']))
        out.append('')
        out.append('| Build | Flags | Processes |')
        out.append('|---|---|---|')
        for b, d in res['builds'].items():
            out.append('| %s | %s | %d |' % (b, d['flags'], d['processes']))
        out.append('')
        out.append('| Entry | Site | Reached | ASan-checked | Violations | Test files reaching it | Detail |')
        out.append('|---|---|---|---|---|---|---|')
        for en, d in res['entries'].items():
            out.append('| %s | %s | %d | %s | %s | %d | %s |' % (
                en, d['site'], d['reached'],
                '-' if d['asan_checked'] is None else d['asan_checked'],
                ', '.join('%s=%d' % (k, v) for k, v in d['violations'].items()) or '-',
                d['test_files'],
                ', '.join('%s=%d' % (k, v) for k, v in d['detail'].items() if v) or '-'))
        out.append('')
        for en, d in res['entries'].items():
            for h, hd in d['hist'].items():
                if hd['total']:
                    items = sorted(((int(k), v) for k, v in hd['nonzero'].items()))
                    out.append('- `%s` (%s): %d measured, smallest %s; %s' % (
                        h, en, hd['total'], hd['min'],
                        ', '.join('%s%s:%d' % (k, '+' if k == L.HMAX else '', v) for k, v in items[:12])
                        + (' ...' if len(items) > 12 else '')))
        out.append('')
        out.append('Violation records logged: %d' % res['violation_records'])
        for g in res['violation_groups']:
            out.append('- %s %s %s: %d logged; builds %s; tests %s' % (
                g['entry'], g['site'], g['kind'], g['n_logged'], ', '.join(g['builds']), ', '.join(g['tests'][:8])))
            out.append('  - frames: %s' % ' <- '.join(g['frames'][:5]))
            out.append('  - example: `%s`' % g['example_args'][:400])
        out.append('')
    return '\n'.join(out) + '\n'

if __name__ == '__main__':
    OUT = sys.argv[1]
    os.makedirs(OUT, exist_ok=True)
    results = []
    for a in sys.argv[2:]:
        n, raw = a.split('=', 1)
        results.append(summarize(n, raw))
    json.dump(results, open(os.path.join(OUT, 'summary.json'), 'w'), indent=1, sort_keys=True)
    open(os.path.join(OUT, 'summary.md'), 'w').write(md(results))
    print('RESULT summary: %d runs, %s' % (len(results), ', '.join('%s:%d procs/%d violation records' % (r['name'], r['processes'], r['violation_records']) for r in results)))
