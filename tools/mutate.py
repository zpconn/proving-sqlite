#!/usr/bin/env python3
"""mutate.py: apply mutants from proofs/MUTANTS to a scratch copy of the overlay and run proofs
against it. A mutant is killed when some proof reports a failed property. The original overlay is
never written; its hash is checked before and after every mutant, and it is restored from memory
if it ever differs.

proofs/MUTANTS, one mutant per line ('#' comments):
  M-NNN <function> <upstream line> '<from>' '<to>' card=C-NN [equivalent='<argument>' review=<reviews/file>]
card= names the card whose proofs must kill it (a P1 card for UB-relevant mutants, the P2/P3 card for functional
ones), so a card's gate never depends on a card that merges later. The full gate runs every mutant against every proof.
A mutant that survives every proof while its card= has no proofs yet (no proofs/<card>/Makefile) is PENDING: it does
not fail the run, and the RESULT line counts it. Once every card has proofs, nothing is pending (checkpoint 1).
`from` must occur exactly once on that line (outside PROOF spans); it is replaced by `to`.

Usage:
  tools/mutate.py --card C-NN                     the card's mutants (its functions), against its proofs
  tools/mutate.py --card C-NN --with C-AA,C-BB    ... against those cards' proofs too
  tools/mutate.py --card C-NN --adhoc "<function> <line> '<from>' '<to>'"   one planted bug
  tools/mutate.py --all [--with ...]              every mutant, against every card that has proofs
Ends with: RESULT mutate <card|all> PASS|FAIL <k>/<n> killed <e> equivalent [<p> pending]
"""
import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
import cards as cardlib  # noqa: E402
import overlay as ov  # noqa: E402
import prove  # noqa: E402


class MutantError(Exception):
    pass


def read_mutants(path):
    out = []
    if not os.path.exists(path):
        return out
    for n, line in enumerate(open(path), 1):
        s = line.strip()
        if not s or s.startswith('#'):
            continue
        out.append(parse_mutant(s, 'MUTANTS:%d' % n))
    return out


def parse_mutant(s, where='adhoc'):
    parts = shlex.split(s)
    if parts and not re.match(r'^M-[0-9]{3}$', parts[0]):
        parts = ['M-adhoc'] + parts
    if len(parts) < 5:
        raise MutantError('%s: need id function line from to' % where)
    m = {'id': parts[0], 'function': parts[1], 'line': int(parts[2]), 'from': parts[3], 'to': parts[4],
         'equivalent': None, 'review': None, 'card': None}
    for kv in parts[5:]:
        k, _, v = kv.partition('=')
        if k in ('equivalent', 'review', 'card'):
            m[k] = v
        else:
            raise MutantError('%s: unknown field %r' % (where, k))
    if m['from'] == m['to']:
        raise MutantError('%s: from == to' % where)
    return m


def apply(overlay_bytes, mut):
    """Return mutated bytes. The upstream line is located in the overlay through the line map."""
    lm = ov.LineMap(overlay_bytes)
    lines = overlay_bytes.split(b'\n')
    targets = [i + 1 for i in range(len(lines)) if lm.upstream_line(i + 1) == mut['line']]
    if not targets:
        raise MutantError('%s: upstream line %d not found in overlay' % (mut['id'], mut['line']))
    spans = ov.find_spans(overlay_bytes)
    frm = mut['from'].encode()
    hits = []
    offset = 0
    starts = []
    for i, ln in enumerate(lines):
        starts.append(offset)
        offset += len(ln) + 1
    for t in targets:
        a = starts[t - 1]
        b = a + len(lines[t - 1])
        k = overlay_bytes.find(frm, a, b)
        while k >= 0:
            if not any(s <= k < e for s, e in spans):
                hits.append(k)
            k = overlay_bytes.find(frm, k + 1, b)
    if len(hits) != 1:
        raise MutantError('%s: %r occurs %d times on upstream line %d (need exactly 1)' % (
            mut['id'], mut['from'], len(hits), mut['line']))
    k = hits[0]
    return overlay_bytes[:k] + mut['to'].encode() + overlay_bytes[k + len(frm):]


def check_function(upstream, mut):
    r = ov.function_ranges(upstream, [mut['function']]).get(mut['function'])
    if not r or not (r[0] <= mut['line'] <= r[1]):
        raise MutantError('%s: line %d is not in %s %s' % (mut['id'], mut['line'], mut['function'], r))


def run_mutant(mut, proof_cards, orig_path, scratch, configs, timeout):
    """Returns (verdict, detail): KILLED, SURVIVED, or ERROR."""
    orig = open(orig_path, 'rb').read()
    h0 = hashlib.sha256(orig).hexdigest()
    mdir = os.path.join(scratch, mut['id'])
    if os.path.exists(mdir):
        shutil.rmtree(mdir)
    os.makedirs(mdir)
    try:
        mutated = apply(orig, mut)
        with open(os.path.join(mdir, 'sqlite3.c'), 'wb') as f:
            f.write(mutated)
        errors = []
        for cname, cflags in configs:
            for cid, card_dir in proof_cards:
                card, proofs = prove.load_card(card_dir)
                for p in proofs:
                    r = prove.prove_one(card, card_dir, p, cname, cflags, mdir,
                                        os.path.join(mdir, 'build', cid), timeout, False)
                    if r['failed'] > 0:
                        fl = '; '.join('[%s] %s' % (f['id'], f['desc']) for f in r['failures'])
                        return 'KILLED', 'by %s/%s %s: %d failed: %s' % (cid, p.name, cname, r['failed'], fl)
                    if r['error']:
                        errors.append('%s/%s %s: %s' % (cid, p.name, cname, r['error']))
        if errors:
            return 'ERROR', 'no property failed, and: ' + '; '.join(errors[:3])
        return 'SURVIVED', 'every proof passed on %s' % ','.join(c for c, _ in configs)
    finally:
        now = open(orig_path, 'rb').read()
        if hashlib.sha256(now).hexdigest() != h0:
            with open(orig_path, 'wb') as f:
                f.write(orig)
            print('mutate: WARNING original overlay changed during %s; restored' % mut['id'])
        shutil.rmtree(os.path.join(mdir, 'build'), ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--card')
    ap.add_argument('--all', action='store_true')
    ap.add_argument('--with', dest='with_', default='')
    ap.add_argument('--adhoc')
    ap.add_argument('--config', default='all')
    ap.add_argument('--overlay', default=os.path.join(ROOT, 'overlay', 'sqlite3.c'))
    ap.add_argument('--scratch')
    ap.add_argument('--timeout', type=int, default=prove.DEFAULT_TIMEOUT)
    ap.add_argument('--json')
    a = ap.parse_args()
    label = a.card or 'all'
    try:
        all_cards = cardlib.load_all(ROOT)
        upstream = open(os.path.join(ROOT, 'upstream', 'sqlite3.c'), 'rb').read()
        if a.adhoc:
            muts = [parse_mutant(a.adhoc)]
        else:
            muts = read_mutants(os.path.join(ROOT, 'proofs', 'MUTANTS'))
        if a.card and not a.adhoc:
            if a.card not in all_cards:
                raise MutantError('no cards/%s.md' % a.card)
            fns = set(all_cards[a.card].functions)
            muts = [m for m in muts if m['card'] == a.card or (m['card'] is None and m['function'] in fns)]
        for m in muts:
            check_function(upstream, m)
        cids = []
        if a.card:
            cids.append(a.card)
        if a.all:
            cids += sorted(d for d in os.listdir(os.path.join(ROOT, 'proofs'))
                           if re.match(r'^C-[0-9]{2}$', d) and os.path.exists(os.path.join(ROOT, 'proofs', d, 'Makefile')))
        cids += [c for c in a.with_.split(',') if c.strip()]
        seen = []
        for c in cids:
            if c not in seen and os.path.exists(os.path.join(ROOT, 'proofs', c, 'Makefile')):
                seen.append(c)
        proof_cards = [(c, os.path.join(ROOT, 'proofs', c)) for c in seen]
        if not proof_cards:
            raise MutantError('no card proofs to run mutants against')
        configs = prove.select_configs(a.config)
        # lp64-le first: cheapest place to see a kill
        configs.sort(key=lambda c: 0 if c[0] == 'lp64-le' else 1)
    except (MutantError, prove.CardError, cardlib.CardFormatError, OSError) as e:
        print('mutate: %s' % e)
        print('RESULT mutate %s FAIL 0/0 killed 0 equivalent' % label)
        return 1
    scratch = a.scratch or os.path.join(proof_cards[0][1], 'build', 'mutants')
    os.makedirs(scratch, exist_ok=True)
    killed = equiv = pending = 0
    ok = True
    results = []
    for m in muts:
        desc = "%s %s:%d '%s'->'%s'" % (m['id'], m['function'], m['line'], m['from'], m['to'])
        try:
            v, detail = run_mutant(m, proof_cards, a.overlay, scratch, configs, a.timeout)
        except (MutantError, prove.CardError) as e:
            v, detail = 'ERROR', str(e)
        if v == 'KILLED':
            killed += 1
        elif v == 'SURVIVED' and m['equivalent']:
            v = 'EQUIVALENT'
            equiv += 1
            detail += '; argued equivalent: %s (review %s)' % (m['equivalent'], m['review'])
            if not m['review']:
                ok = False
                detail += ' -- NO REVIEW NAMED'
        elif v == 'SURVIVED' and m['card'] and not os.path.exists(os.path.join(ROOT, 'proofs', m['card'], 'Makefile')):
            v = 'PENDING'
            pending += 1
            detail += '; %s, the card that must kill it, has no proofs yet' % m['card']
        else:
            ok = False
        results.append({'mutant': m, 'verdict': v, 'detail': detail})
        print('MUTANT %s %s %s' % (desc, v, detail))
        sys.stdout.flush()
    if a.json:
        os.makedirs(os.path.dirname(os.path.abspath(a.json)), exist_ok=True)
        with open(a.json, 'w') as f:
            json.dump(results, f, indent=1)
    print('RESULT mutate %s %s %d/%d killed %d equivalent%s' % (label, 'PASS' if ok else 'FAIL', killed, len(muts), equiv,
                                                               ' %d pending' % pending if pending else ''))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
