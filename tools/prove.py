#!/usr/bin/env python3
"""prove.py: build and run a card's CBMC proofs, coverage, and the configuration probe.

Every proof is one translation unit: the card's harness.c, whose first line is
`#include "sqlite3.c"` (the overlay, found with -I), followed by contracts and predicates. Per
configuration the pipeline is:

  goto-cc <CONFIGS flags> -include proof.h -I overlay -I proofs/include -I proofs -c harness.c
  goto-cc --function <entry>                     (link; one goto program per proof)
  goto-instrument --drop-unused-functions
  goto-instrument --dfcc <entry> [--enforce-contract f/contract_f] [--replace-call-with-contract g/contract_g]...
                  [--apply-loop-contracts]       (only if the proof uses contracts)
  goto-instrument --slice-global-inits
  cbmc <every option in proofs/CHECKS> [--unwindset ...] [solver] [--object-bits n]
  cbmc ... --conversion-check --property <id>... (the %float-to-int pass, when such properties exist)

A proof also FAILS if CBMC reports a function without a body: calls to it would be unconstrained.

The card's Makefile is declarative (tools/scan.py enforces it):
  CARD := C-NN
  PROOFS := <name> ...
  <name>_ENTRY := <harness function>                 required
  <name>_ENFORCE := <fn>/contract_<fn>               at most one (DFCC checks one contract per run)
  <name>_REPLACE := <fn>/contract_<fn> ...           callees replaced by their contracts
  <name>_LOOPS := contracts | unwind | none          default none
  <name>_UNWINDSET := <fn>.<loop>:<bound>,...        bounds for unwound loops; assertions always on
  <name>_SOLVER := --smt2 | --z3 | --sat-solver cadical | --sat-solver minisat2 | --sat-solver glucose
  <name>_OBJECT_BITS := <8..16>
  <name>_COVER := <fn> ...                           functions whose lines coverage reports
  include ../Makefile.common

Every command prints one RESULT line last, e.g.
  RESULT prove C-03 lp64-le PASS 212s 1843 properties 0 failed
"""
import argparse
import json
import os
import re
import resource
import shlex
import signal
import subprocess
import sys
import time

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
import overlay as ov  # noqa: E402

DEFAULT_TIMEOUT = 600          # seconds per CBMC run, per configuration (GOAL.md §0.9)
MEM_LIMIT = 12 * 1024 ** 3     # address-space cap per tool process, so CBMC fails instead of swapping
ALLOWED_SOLVERS = ['', '--smt2', '--z3', '--sat-solver cadical', '--sat-solver minisat2',
                   '--sat-solver glucose']
FLOAT2INT_DIRECTIVE = '%float-to-int'

IDENT = r'[A-Za-z_][A-Za-z0-9_]*'
RE_PAIR = re.compile(r'^(%s)/contract_(%s)$' % (IDENT, IDENT))
RE_UNWIND = re.compile(r'^%s\.[0-9]+:[0-9]+$' % IDENT)


class CardError(Exception):
    pass


# ---------------------------------------------------------------- configuration files

def read_configs(root=ROOT):
    """proofs/CONFIGS: `name  goto-cc flags...` per line; '#' comments."""
    cfgs = []
    with open(os.path.join(root, 'proofs', 'CONFIGS')) as f:
        for line in f:
            line = line.split('#', 1)[0].strip()
            if not line:
                continue
            parts = shlex.split(line)
            cfgs.append((parts[0], parts[1:]))
    return cfgs


def read_checks(root=ROOT):
    """proofs/CHECKS: option lines and %directives. Returns (options, float2int) where float2int
    is (extra option, description regex) or None."""
    opts, f2i = [], None
    with open(os.path.join(root, 'proofs', 'CHECKS')) as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith('#'):
                continue
            if s.startswith(FLOAT2INT_DIRECTIVE):
                rest = s[len(FLOAT2INT_DIRECTIVE):].strip()
                opt, pat = rest.split(None, 1)
                f2i = (opt, pat)
            elif s.startswith('--'):
                opts.extend(shlex.split(s))
            else:
                raise CardError('proofs/CHECKS: unrecognised line %r' % s)
    return opts, f2i


def parse_card_makefile(path):
    """Parse the declarative card Makefile. Returns dict of variables. Raises CardError on any
    line that is not a simple assignment, comment, blank, or the include."""
    vars_ = {}
    with open(path) as f:
        lines = f.read().split('\n')
    i = 0
    while i < len(lines):
        raw = lines[i]
        i += 1
        s = raw.strip()
        if not s or s.startswith('#'):
            continue
        if s == 'include ../Makefile.common':
            continue
        m = re.match(r'^(%s)\s*:?=\s*(.*)$' % IDENT, s)
        if not m:
            raise CardError('%s: line %d is not NAME := value: %r' % (path, i, raw))
        name, val = m.group(1), m.group(2)
        if '$' in val or '`' in val:
            raise CardError('%s: line %d: no make expansions or shell in values' % (path, i))
        if '#' in val:
            val = val.split('#', 1)[0]
        vars_[name] = val.strip()
    return vars_


class Proof:
    def __init__(self, name, v):
        g = lambda k, d='': v.get('%s_%s' % (name, k), d)  # noqa: E731
        self.name = name
        self.entry = g('ENTRY')
        if not re.match('^%s$' % IDENT, self.entry or ''):
            raise CardError('%s_ENTRY must name the harness function' % name)
        self.enforce = g('ENFORCE').split()
        self.replace = g('REPLACE').split()
        self.loops = g('LOOPS', 'none') or 'none'
        self.unwindset = g('UNWINDSET')
        self.solver = ' '.join(g('SOLVER').split())
        self.object_bits = g('OBJECT_BITS')
        self.cover = g('COVER').split()
        if len(self.enforce) > 1:
            raise CardError('%s_ENFORCE: at most one function per proof (DFCC checks one contract per run)' % name)
        for p in self.enforce + self.replace:
            if not RE_PAIR.match(p) or RE_PAIR.match(p).group(1) != RE_PAIR.match(p).group(2):
                raise CardError('%s: %r must be <fn>/contract_<fn>' % (name, p))
        if self.loops not in ('contracts', 'unwind', 'none'):
            raise CardError('%s_LOOPS must be contracts, unwind or none' % name)
        if self.unwindset:
            for item in self.unwindset.split(','):
                if not RE_UNWIND.match(item.strip()):
                    raise CardError('%s_UNWINDSET item %r must be fn.N:K' % (name, item))
        if self.solver not in ALLOWED_SOLVERS:
            raise CardError('%s_SOLVER %r not one of %s' % (name, self.solver, ALLOWED_SOLVERS))
        if self.object_bits and not (self.object_bits.isdigit() and 8 <= int(self.object_bits) <= 16):
            raise CardError('%s_OBJECT_BITS must be 8..16' % name)
        if not self.cover:
            self.cover = [p.split('/')[0] for p in self.enforce]
        self.enforced = [p.split('/')[0] for p in self.enforce]

    def uses_dfcc(self):
        return bool(self.enforce or self.replace or self.loops == 'contracts')


def load_card(card_dir):
    mk = os.path.join(card_dir, 'Makefile')
    v = parse_card_makefile(mk)
    card = v.get('CARD')
    if not card or not re.match(r'^C-[0-9]{2}$', card):
        raise CardError('%s: CARD := C-NN missing' % mk)
    if os.path.basename(os.path.normpath(card_dir)) != card:
        raise CardError('%s: CARD %s does not match its directory' % (mk, card))
    names = v.get('PROOFS', '').split()
    if not names:
        raise CardError('%s: PROOFS is empty' % mk)
    allowed = {'CARD', 'PROOFS'}
    for n in names:
        for k in ('ENTRY', 'ENFORCE', 'REPLACE', 'LOOPS', 'UNWINDSET', 'SOLVER', 'OBJECT_BITS', 'COVER'):
            allowed.add('%s_%s' % (n, k))
    extra = sorted(set(v) - allowed)
    if extra:
        raise CardError('%s: variables not allowed: %s' % (mk, ' '.join(extra)))
    return card, [Proof(n, v) for n in names]


# ---------------------------------------------------------------- running tools

def _limits():
    os.setsid()
    try:
        resource.setrlimit(resource.RLIMIT_AS, (MEM_LIMIT, MEM_LIMIT))
    except (ValueError, OSError):
        pass


def run(cmd, log, timeout=None, cwd=None):
    """Run cmd under nice -n 10 in its own process group, output to log file. Returns
    (returncode or 'timeout', seconds)."""
    t0 = time.time()
    with open(log, 'w') as lf:
        lf.write('$ ' + ' '.join(shlex.quote(c) for c in cmd) + '\n')
        lf.flush()
        p = subprocess.Popen(['nice', '-n', '10'] + cmd, stdout=lf, stderr=subprocess.STDOUT,
                             cwd=cwd, preexec_fn=_limits)
        try:
            rc = p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            p.wait()
            rc = 'timeout'
    return rc, time.time() - t0


RE_RESULT = re.compile(r'^\[([^\]]+)\] (?:line (\d+) )?(.*): (SUCCESS|FAILURE|UNKNOWN|ERROR)$')
RE_NOBODY = re.compile(r'no body for (?:function|callee) (\S+)')


def parse_cbmc(text):
    props = []
    for line in text.split('\n'):
        m = RE_RESULT.match(line.strip())
        if m:
            props.append({'id': m.group(1), 'line': int(m.group(2)) if m.group(2) else None,
                          'desc': m.group(3), 'status': m.group(4)})
    verdict = None
    if 'VERIFICATION SUCCESSFUL' in text:
        verdict = 'SUCCESSFUL'
    elif 'VERIFICATION FAILED' in text:
        verdict = 'FAILED'
    elif 'VERIFICATION ERROR' in text:
        verdict = 'ERROR'
    nobody = sorted(set(RE_NOBODY.findall(text)))
    return props, verdict, nobody


def parse_show_properties(text):
    """Return [(id, description)] from cbmc --show-properties output."""
    out = []
    cur = None
    for line in text.split('\n'):
        m = re.match(r'^Property (\S+):$', line.strip())
        if m:
            cur = [m.group(1), []]
            out.append(cur)
        elif cur is not None and line.startswith('  '):
            cur[1].append(line.strip())
    return [(i, ' '.join(d)) for i, d in out]


# ---------------------------------------------------------------- build

def build_proof(card_dir, proof, cfg_name, cfg_flags, overlay_dir, bdir, log):
    """Build the instrumented goto program for one proof and config. Returns (path, error)."""
    os.makedirs(bdir, exist_ok=True)
    obj = os.path.join(bdir, 'harness.o.goto')
    harness = os.path.join(card_dir, 'harness.c')
    stamp = os.path.join(bdir, 'harness.o.stamp')
    key = json.dumps([cfg_flags, os.path.abspath(overlay_dir), _mtimes(card_dir, overlay_dir)])
    if not (os.path.exists(obj) and os.path.exists(stamp) and open(stamp).read() == key):
        cmd = ['goto-cc'] + cfg_flags + ['-include', os.path.join(ROOT, 'proofs', 'include', 'proof.h'),
                                         '-I', overlay_dir, '-I', os.path.join(ROOT, 'proofs', 'include'),
                                         '-I', os.path.join(ROOT, 'proofs'), '-c', harness, '-o', obj]
        rc, _ = run(cmd, log + '.goto-cc', timeout=900)
        if rc != 0:
            return None, 'goto-cc failed (%s); see %s' % (rc, log + '.goto-cc')
        with open(stamp, 'w') as f:
            f.write(key)
    p0 = os.path.join(bdir, proof.name + '.0.goto')
    steps = [(['goto-cc', '--function', proof.entry, obj, '-o', p0], 'link')]
    p1 = os.path.join(bdir, proof.name + '.1.goto')
    steps.append((['goto-instrument', '--drop-unused-functions', p0, p1], 'drop-unused'))
    cur = p1
    if proof.uses_dfcc():
        p2 = os.path.join(bdir, proof.name + '.2.goto')
        cmd = ['goto-instrument', '--dfcc', proof.entry]
        for e in proof.enforce:
            cmd += ['--enforce-contract', e]
        for r in proof.replace:
            cmd += ['--replace-call-with-contract', r]
        if proof.loops == 'contracts':
            cmd += ['--apply-loop-contracts']
        cmd += [cur, p2]
        steps.append((cmd, 'dfcc'))
        cur = p2
    p3 = os.path.join(bdir, proof.name + '.goto')
    steps.append((['goto-instrument', '--slice-global-inits', cur, p3], 'slice-global-inits'))
    for cmd, tag in steps:
        rc, _ = run(cmd, log + '.' + tag, timeout=900)
        if rc != 0:
            return None, '%s failed (%s); see %s' % (tag, rc, log + '.' + tag)
    for f in (p0, p1, os.path.join(bdir, proof.name + '.2.goto')):
        if os.path.exists(f):
            os.remove(f)
    return p3, None


def _mtimes(card_dir, overlay_dir):
    paths = [os.path.join(card_dir, 'harness.c'), os.path.join(overlay_dir, 'sqlite3.c')]
    for sub in ('proofs/include', 'proofs/contracts', 'proofs/spec'):
        d = os.path.join(ROOT, sub)
        if os.path.isdir(d):
            for n in sorted(os.listdir(d)):
                paths.append(os.path.join(d, n))
    out = []
    for p in paths:
        try:
            st = os.stat(p)
            out.append([p, st.st_mtime_ns, st.st_size])
        except FileNotFoundError:
            out.append([p, None])
    return out


def cbmc_base(proof, goto, checks, drop_unwinding_assertions=False):
    cmd = ['cbmc', goto] + [c for c in checks if not (drop_unwinding_assertions and c == '--unwinding-assertions')]
    if proof.unwindset:
        cmd += ['--unwindset', proof.unwindset]
    if proof.solver:
        cmd += proof.solver.split()
    if proof.object_bits:
        cmd += ['--object-bits', proof.object_bits]
    return cmd


# ---------------------------------------------------------------- prove

def prove_one(card, card_dir, proof, cfg_name, cfg_flags, overlay_dir, build_root, timeout, trace):
    bdir = os.path.join(build_root, cfg_name)
    os.makedirs(bdir, exist_ok=True)
    log = os.path.join(bdir, proof.name)
    res = {'card': card, 'proof': proof.name, 'config': cfg_name, 'status': 'FAIL', 'seconds': 0,
           'properties': 0, 'failed': 0, 'failures': [], 'error': None, 'float_to_int_properties': 0}
    t0 = time.time()
    goto, err = build_proof(card_dir, proof, cfg_name, cfg_flags, overlay_dir, bdir, log)
    if err:
        res['error'] = err
        res['seconds'] = round(time.time() - t0)
        return res
    checks, f2i = read_checks()
    cmd = cbmc_base(proof, goto, checks)
    if trace:
        cmd.append('--trace')
    rc, secs = run(cmd, log + '.cbmc', timeout=timeout)
    text = open(log + '.cbmc', errors='replace').read()
    props, verdict, nobody = parse_cbmc(text)
    res['properties'] = len(props)
    res['failures'] = [p for p in props if p['status'] != 'SUCCESS']
    if rc == 'timeout':
        res['error'] = 'cbmc timed out after %ds; see %s' % (timeout, log + '.cbmc')
    elif verdict is None:
        res['error'] = 'cbmc gave no verdict (rc %s); see %s' % (rc, log + '.cbmc')
    elif verdict == 'ERROR':
        res['error'] = 'cbmc VERIFICATION ERROR; see %s' % (log + '.cbmc')
    if nobody:
        res['error'] = (res['error'] + '; ' if res['error'] else '') + \
            'functions without a body are called (unconstrained): ' + ', '.join(nobody)
    # float-to-integer pass
    if f2i and not res['error']:
        opt, pat = f2i
        rx = re.compile(pat)
        rc2, _ = run(cbmc_base(proof, goto, checks) + [opt, '--show-properties'], log + '.f2i-show', timeout=timeout)
        ids = [i for i, d in parse_show_properties(open(log + '.f2i-show', errors='replace').read()) if rx.search(d)]
        res['float_to_int_properties'] = len(ids)
        if rc2 != 0:
            res['error'] = 'float-to-int --show-properties failed (%s); see %s' % (rc2, log + '.f2i-show')
        elif ids:
            cmd2 = cbmc_base(proof, goto, checks) + [opt]
            for i in ids:
                cmd2 += ['--property', i]
            if trace:
                cmd2.append('--trace')
            rc3, s3 = run(cmd2, log + '.f2i', timeout=timeout)
            secs += s3
            t2 = open(log + '.f2i', errors='replace').read()
            p2, v2, _ = parse_cbmc(t2)
            res['properties'] += len(p2)
            res['failures'] += [p for p in p2 if p['status'] != 'SUCCESS']
            if rc3 == 'timeout' or v2 not in ('SUCCESSFUL', 'FAILED'):
                res['error'] = 'float-to-int pass gave no verdict (%s); see %s' % (rc3, log + '.f2i')
    res['failed'] = len(res['failures'])
    res['seconds'] = round(time.time() - t0)
    res['cbmc_seconds'] = round(secs)
    if not res['error'] and res['failed'] == 0 and verdict == 'SUCCESSFUL':
        res['status'] = 'PASS'
    with open(log + '.json', 'w') as f:
        json.dump(res, f, indent=1)
    return res


def select_configs(config):
    cfgs = read_configs()
    if config in (None, '', 'all'):
        return cfgs
    sel = [c for c in cfgs if c[0] == config]
    if not sel:
        raise CardError('unknown CONFIG %r; proofs/CONFIGS has %s' % (config, ', '.join(c[0] for c in cfgs)))
    return sel


def cmd_prove(a):
    card_dir = os.path.abspath(a.card_dir)
    try:
        card, proofs = load_card(card_dir)
        cfgs = select_configs(a.config)
    except (CardError, OSError) as e:
        print('prove: %s' % e)
        print('RESULT prove %s %s FAIL 0s 0 properties 0 failed' % (os.path.basename(card_dir), a.config or 'all'))
        return 1
    build_root = a.build_dir or os.path.join(card_dir, 'build')
    overlay_dir = os.path.abspath(a.overlay or os.path.join(ROOT, 'overlay'))
    total = {'s': 0, 'p': 0, 'f': 0, 'ok': True}
    summary = []
    for cname, cflags in cfgs:
        cs = {'s': 0, 'p': 0, 'f': 0, 'ok': True}
        for proof in proofs:
            r = prove_one(card, card_dir, proof, cname, cflags, overlay_dir, build_root, a.timeout, a.trace)
            summary.append(r)
            for fl in r['failures'][:20]:
                print('  FAILED %s %s [%s] line %s %s' % (proof.name, cname, fl['id'], fl['line'], fl['desc']))
            if r['error']:
                print('  ERROR %s %s: %s' % (proof.name, cname, r['error']))
            print('RESULT prove %s/%s %s %s %ds %d properties %d failed' % (
                card, proof.name, cname, r['status'], r['seconds'], r['properties'], r['failed']))
            sys.stdout.flush()
            cs['s'] += r['seconds']
            cs['p'] += r['properties']
            cs['f'] += r['failed']
            cs['ok'] = cs['ok'] and r['status'] == 'PASS'
        if len(cfgs) > 1:
            print('RESULT prove %s %s %s %ds %d properties %d failed' % (
                card, cname, 'PASS' if cs['ok'] else 'FAIL', cs['s'], cs['p'], cs['f']))
        for k in ('s', 'p', 'f'):
            total[k] += cs[k]
        total['ok'] = total['ok'] and cs['ok']
    with open(os.path.join(build_root, 'prove-summary.json'), 'w') as f:
        json.dump(summary, f, indent=1)
    label = cfgs[0][0] if len(cfgs) == 1 else 'all'
    print('RESULT prove %s %s %s %ds %d properties %d failed' % (
        card, label, 'PASS' if total['ok'] else 'FAIL', total['s'], total['p'], total['f']))
    return 0 if total['ok'] else 1


# ---------------------------------------------------------------- coverage

RE_COVER = re.compile(r'^\[([^\]]+)\] file (\S+) line (\d+) function (\S+) block (\d+) \(lines (.*)\): (SATISFIED|FAILED)$')


def parse_cover(text, overlay_path):
    """Return list of (function, set(overlay lines), satisfied) for blocks in overlay_path."""
    out = []
    base = os.path.basename(overlay_path)
    for line in text.split('\n'):
        m = RE_COVER.match(line.strip())
        if not m:
            continue
        fn = m.group(4)
        sat = m.group(7) == 'SATISFIED'
        lines = set()
        for part in m.group(6).split(';'):
            part = part.strip()
            fm = re.match(r'^(.*):([^:]*):([0-9,\- ]+)$', part)
            if not fm:
                continue
            if os.path.basename(fm.group(1)) != base:
                continue
            for rng in fm.group(3).split(','):
                rng = rng.strip()
                if '-' in rng:
                    lo, hi = rng.split('-')
                    lines.update(range(int(lo), int(hi) + 1))
                elif rng:
                    lines.add(int(rng))
        if lines:
            out.append((fn, lines, sat))
    return out


def cover_one(card, card_dir, proof, cfg_name, cfg_flags, overlay_dir, build_root, timeout):
    bdir = os.path.join(build_root, cfg_name)
    log = os.path.join(bdir, proof.name + '.cover')
    res = {'card': card, 'proof': proof.name, 'config': cfg_name, 'functions': {}, 'error': None}
    goto, err = build_proof(card_dir, proof, cfg_name, cfg_flags, overlay_dir, bdir, log)
    if err:
        res['error'] = err
        return res
    checks, _ = read_checks()
    cmd = cbmc_base(proof, goto, checks, drop_unwinding_assertions=True) + ['--cover', 'location']
    rc, secs = run(cmd, log + '.cbmc', timeout=timeout)
    text = open(log + '.cbmc', errors='replace').read()
    if rc == 'timeout' or '** coverage results' not in text and 'coverage results' not in text:
        res['error'] = 'coverage run gave no results (%s); see %s' % (rc, log + '.cbmc')
        return res
    ovpath = os.path.join(overlay_dir, 'sqlite3.c')
    lm = ov.LineMap(open(ovpath, 'rb').read())
    blocks = parse_cover(text, ovpath)
    for fn in proof.cover:
        body = fn + '_wrapped_for_contract_checking' if fn in proof.enforced else fn
        mine = [(l, s) for f, l, s in blocks if f == body]
        all_lines, unc = set(), set()
        for l, s in mine:
            all_lines |= l
            if not s:
                unc |= l
        res['functions'][fn] = {
            'goal_lines': sorted(lm.upstream_line(x) for x in all_lines),
            'uncovered': sorted(set(lm.upstream_line(x) for x in unc)),
            'blocks': len(mine), 'blocks_failed': sum(1 for _, s in mine if not s)}
        if not mine:
            res['error'] = 'no coverage goals found for %s (is it reached? is the name right?)' % fn
    res['seconds'] = round(secs)
    with open(log + '.json', 'w') as f:
        json.dump(res, f, indent=1)
    return res


def explained_lines(card_dir):
    """Upstream line numbers NOTES.md mentions as sqlite3.c:<line>."""
    p = os.path.join(card_dir, 'NOTES.md')
    if not os.path.exists(p):
        return set()
    return set(int(x) for x in re.findall(r'sqlite3\.c:(\d+)', open(p, errors='replace').read()))


def cmd_coverage(a):
    card_dir = os.path.abspath(a.card_dir)
    try:
        card, proofs = load_card(card_dir)
        cfgs = select_configs(a.config)
    except (CardError, OSError) as e:
        print('coverage: %s' % e)
        print('RESULT coverage %s %s FAIL' % (os.path.basename(card_dir), a.config or 'all'))
        return 1
    build_root = a.build_dir or os.path.join(card_dir, 'build')
    overlay_dir = os.path.abspath(a.overlay or os.path.join(ROOT, 'overlay'))
    explained = explained_lines(card_dir)
    ok = True
    tot_goal, tot_unc, tot_unexpl = 0, 0, 0
    allres = []
    for cname, cflags in cfgs:
        for proof in proofs:
            r = cover_one(card, card_dir, proof, cname, cflags, overlay_dir, build_root, a.timeout)
            allres.append(r)
            if r['error']:
                print('  ERROR %s %s: %s' % (proof.name, cname, r['error']))
                ok = False
            for fn, d in r['functions'].items():
                unexpl = [x for x in d['uncovered'] if x not in explained]
                tot_goal += len(set(d['goal_lines']))
                tot_unc += len(d['uncovered'])
                tot_unexpl += len(unexpl)
                print('  coverage %s %s %s: %d/%d lines; uncovered %s%s' % (
                    proof.name, cname, fn, len(set(d['goal_lines'])) - len(d['uncovered']), len(set(d['goal_lines'])),
                    ', '.join('sqlite3.c:%d' % x for x in d['uncovered']) or 'none',
                    ('; NOT EXPLAINED in NOTES.md: ' + ', '.join('sqlite3.c:%d' % x for x in unexpl)) if unexpl else ''))
                if unexpl:
                    ok = False
    os.makedirs(build_root, exist_ok=True)
    with open(os.path.join(build_root, 'coverage-summary.json'), 'w') as f:
        json.dump(allres, f, indent=1)
    label = cfgs[0][0] if len(cfgs) == 1 else 'all'
    print('RESULT coverage %s %s %s %d/%d lines %d uncovered %d unexplained' % (
        card, label, 'PASS' if ok else 'FAIL', tot_goal - tot_unc, tot_goal, tot_unc, tot_unexpl))
    return 0 if ok else 1


# ---------------------------------------------------------------- configuration probe

def expectations(name):
    m = re.match(r'^(lp64|ilp32)-(le|be)$', name)
    if not m:
        raise CardError('configuration name %r is not <lp64|ilp32>-<le|be>' % name)
    w = 8 if m.group(1) == 'lp64' else 4
    le = m.group(2) == 'le'
    return {'EXPECT_PTR': w, 'EXPECT_LONG': w, 'EXPECT_LOW_BYTE': 4 if le else 1,
            'EXPECT_BYTEORDER': 1234 if le else 4321}


def cmd_probe(a):
    """Build tools/probe/config_probe.c against the overlay under each configuration and check
    that word size, byte order and SQLite's byte-order macros are what the name says."""
    overlay_dir = os.path.abspath(a.overlay or os.path.join(ROOT, 'overlay'))
    build_root = a.build_dir or os.path.join(ROOT, 'proofs', 'build', 'probe')
    os.makedirs(build_root, exist_ok=True)
    ok = True
    for cname, cflags in select_configs(a.config):
        exp = expectations(cname)
        bdir = os.path.join(build_root, cname)
        os.makedirs(bdir, exist_ok=True)
        defs = ['-D%s=%d' % kv for kv in sorted(exp.items())]
        g0 = os.path.join(bdir, 'probe.0.goto')
        g1 = os.path.join(bdir, 'probe.1.goto')
        g2 = os.path.join(bdir, 'probe.goto')
        steps = [
            ['goto-cc'] + cflags + ['-include', os.path.join(ROOT, 'proofs', 'include', 'proof.h'), '-I', overlay_dir]
            + defs + ['--function', 'probe', os.path.join(TOOLS, 'probe', 'config_probe.c'), '-o', g0],
            ['goto-instrument', '--drop-unused-functions', g0, g1],
            ['goto-instrument', '--slice-global-inits', g1, g2]]
        err = None
        for i, s in enumerate(steps):
            rc, _ = run(s, os.path.join(bdir, 'step%d.log' % i), timeout=900)
            if rc != 0:
                err = 'step %d failed (%s); see %s' % (i, rc, os.path.join(bdir, 'step%d.log' % i))
                break
        if not err:
            checks, _ = read_checks()
            rc, _ = run(['cbmc', g2] + checks, os.path.join(bdir, 'cbmc.log'), timeout=a.timeout)
            props, verdict, nobody = parse_cbmc(open(os.path.join(bdir, 'cbmc.log')).read())
            asserts = [p for p in props if '.assertion.' in p['id']]
            for p in asserts:
                print('  probe %s: %s: %s' % (cname, p['desc'], p['status']))
            if verdict != 'SUCCESSFUL' or len(asserts) < 7:
                err = 'probe verdict %s with %d assertions' % (verdict, len(asserts))
        if err:
            print('  probe %s: %s' % (cname, err))
            ok = False
        print('RESULT probe %s %s' % (cname, 'FAIL' if err else 'PASS'))
    print('RESULT probe all %s' % ('PASS' if ok else 'FAIL'))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name in ('prove', 'coverage', 'probe'):
        s = sub.add_parser(name)
        s.add_argument('--card-dir', default='.')
        s.add_argument('--config', default='all')
        s.add_argument('--overlay', default=None, help='directory holding the sqlite3.c to prove against')
        s.add_argument('--build-dir', default=None)
        s.add_argument('--timeout', type=int, default=DEFAULT_TIMEOUT)
        s.add_argument('--trace', action='store_true')
    a = ap.parse_args()
    return {'prove': cmd_prove, 'coverage': cmd_coverage, 'probe': cmd_probe}[a.cmd](a)


if __name__ == '__main__':
    sys.exit(main())
