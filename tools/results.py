#!/usr/bin/env python3
"""results.py: generate RESULTS.md and results.csv from evidence/results/C-NN.json (written by campaign.py at each
merge from that merge's gate run), and CAMPAIGN.md from campaign.py's state. Never edit the outputs by hand.
results.csv depends only on committed files, so it regenerates identically from a clean clone.

Usage: tools/results.py [--root DIR] [--state STATE.json] [--check]
  --check   regenerate results.csv in memory and compare it with the committed file
Ends with: RESULT results PASS|FAIL <n> rows
"""
import argparse
import csv
import io
import json
import os
import re
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
import cards as cardlib  # noqa: E402
import prove  # noqa: E402

COLS = ['card', 'property', 'proof', 'functions', 'config', 'status', 'cbmc_seconds', 'properties', 'failed',
        'lines_covered', 'lines_total', 'uncovered_lines', 'mutants_killed', 'mutants_total', 'mutants_equivalent',
        'review', 'ledger_entries', 'argued', 'bounds', 'assigns', 'excepted', 'prove_from', 'coverage_from', 'mutants_from']

# Inputs a proof leaves to argument, by function (Zach's decision on C-11, 2026-11-10,
# evidence/approvals/C-11-f2i-exact-min/; PROPERTIES.md change 7). Fixed here, in a frozen file, so no card can drop it.
ARGUED = {'sqlite3IntFloatCompare': 'proved for every other (i, r); argued and tested at r = −2^63 (UB-CLASSES.md)'}


def argued_notes(proof):
    """What a row's proof leaves to argument: for a function it covers, or one whose contract it uses (REPLACE)."""
    if proof is None:
        return ''
    notes = []
    for fn, text in sorted(ARGUED.items()):
        if fn in proof.cover:
            notes.append('%s: %s' % (fn, text))
        elif any(r.split('/')[0] == fn for r in proof.replace):
            notes.append('uses contract_%s, which is %s' % (fn, text))
    return '; '.join(notes)


def assigns_status(cid, proof):
    """How a row's contract frame (assigns) is established: 'proved' by CBMC, or 'reviewed (T-015)' for a legacy proof
    whose card argues its loop frame's inclusion instead of passing prove.py's frame check (Zach, 2026-11-11)."""
    if proof is None or not proof.enforced:
        return ''
    return 'reviewed (T-015)' if proof.uses_legacy() and cid in prove.LEGACY_FRAME_ARGUED else 'proved'


def review_verdict(root, cid):
    best = None
    for n in sorted(os.listdir(os.path.join(root, 'reviews'))) if os.path.isdir(os.path.join(root, 'reviews')) else []:
        m = re.match(r'^%s-r([0-9]+)\.md$' % cid, n)
        if m:
            k = int(m.group(1))
            if best is None or k > best[0]:
                best = (k, n)
    if not best:
        return ''
    with open(os.path.join(root, 'reviews', best[1]), errors='replace') as f:
        for line in f:
            if line.strip():
                return '%s (%s)' % (re.sub(r'[*#`_]', '', line.strip()).split()[0], best[1])
    return ''


def ledger_entries(root, proof):
    ids = []
    for r in proof.replace:
        fn = r.split('/')[0]
        p = os.path.join(root, 'proofs', 'contracts', fn + '.h')
        if os.path.exists(p):
            ids += re.findall(r'Ledger:\s*(A-[0-9]{3})', open(p, errors='replace').read())
    return ' '.join(sorted(set(ids)))


def prov_text(pv):
    """'<commit> <gate log>' for one field's provenance record (campaign.py collect_results), or ''."""
    pv = pv or {}
    return ' '.join(x for x in ((pv.get('commit') or '')[:12], pv.get('gate_log') or '') if x)


def rows(root):
    out = []
    cards = cardlib.load_all(root)
    d = os.path.join(root, 'evidence', 'results')
    for n in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        m = re.match(r'^(C-[0-9]{2})\.json$', n)
        if not m:
            continue
        cid = m.group(1)
        rec = json.load(open(os.path.join(d, n)))
        card = cards.get(cid)
        try:
            _, proofs = prove.load_card(os.path.join(root, 'proofs', cid))
            pmap = {p.name: p for p in proofs}
        except (prove.CardError, OSError):
            pmap = {}
        cov = {}
        for c in rec.get('coverage_summary') or []:
            tot = sum(len(set(f['goal_lines'])) for f in c['functions'].values())
            unc = sorted(set(x for f in c['functions'].values() for x in f['uncovered']))
            cov[(c['proof'], c['config'])] = (tot - len(unc), tot, ' '.join(str(x) for x in unc))
        muts = rec.get('mutants') or []
        mk = sum(1 for x in muts if x['verdict'] == 'KILLED')
        me = sum(1 for x in muts if x['verdict'] == 'EQUIVALENT')
        rv = review_verdict(root, cid)
        prov = rec.get('provenance') or {}
        frm = {k: prov_text(prov.get(k)) for k in ('prove_summary', 'coverage_summary', 'mutants')}
        for r in rec.get('prove_summary') or []:
            pr = pmap.get(r['proof'])
            fns = ' '.join(pr.cover) if pr else ''
            cv = cov.get((r['proof'], r['config']), ('', '', ''))
            out.append({'card': cid, 'property': card.property if card else '', 'proof': r['proof'], 'functions': fns,
                        'config': r['config'], 'status': r['status'], 'cbmc_seconds': r.get('cbmc_seconds', r.get('seconds')),
                        'properties': r['properties'], 'failed': r['failed'], 'lines_covered': cv[0], 'lines_total': cv[1],
                        'uncovered_lines': cv[2], 'mutants_killed': mk, 'mutants_total': len(muts), 'mutants_equivalent': me,
                        'review': rv, 'ledger_entries': ledger_entries(root, pr) if pr else '',
                        'argued': argued_notes(pr), 'bounds': prove.bounds_label(cid, r['proof']),
                        'assigns': assigns_status(cid, pr),
                        'excepted': prove.EXCEPTED_FAILURES[cid][0]['label'] if r.get('excepted') and cid in prove.EXCEPTED_FAILURES else '',
                        'prove_from': frm['prove_summary'], 'coverage_from': frm['coverage_summary'], 'mutants_from': frm['mutants']})
    return out


def csv_text(rs):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLS, lineterminator='\n')
    w.writeheader()
    for r in rs:
        w.writerow(r)
    return buf.getvalue()


def results_md(rs):
    lines = ['# RESULTS', '', 'Generated by tools/results.py from evidence/results/ at each merge. Do not edit.',
             'Every row is *proved*: CBMC verified the proof under proofs/CHECKS on that configuration, except for what '
             'its Argued column names, which is *argued* in UB-CLASSES.md and *tested*. A row with a Bounds column is '
             'proved only for inputs within those bounds, and *tested* past them by tests/bounded/ (PROPERTIES.md, '
             'bounded proofs). The Assigns column says how the contract\'s frame is established: *proved*, or *reviewed* where '
             'CBMC\'s legacy engine leaves a loop\'s frame unchecked against it (T-015, TRUSTED.md). A status of "PASS (proved '
             'except F-001 at 92793)" means the only failure is that finding\'s, which tools/prove.py excepts '
             '(PROPERTIES.md change 9). Ledger entries are '
             '*assumed*; see LEDGER.md. CBMC itself is *trusted*; see TRUSTED.md.', '',
             '| Card | Prop | Proof | Functions | Config | Status | CBMC s | Properties | Failed | Coverage | Mutants killed | Review | Ledger | Argued | Bounds | Assigns |',
             '|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|']
    for r in rs:
        r = dict(r, status=r['status'] + (' (%s)' % r['excepted'] if r.get('excepted') else ''))
        cov = '%s/%s' % (r['lines_covered'], r['lines_total']) if r['lines_total'] != '' else ''
        mu = '%s/%s%s' % (r['mutants_killed'], r['mutants_total'], (' (+%s equiv.)' % r['mutants_equivalent']) if r['mutants_equivalent'] else '')
        lines.append('| %s |' % ' | '.join(str(x) for x in [r['card'], r['property'], r['proof'], r['functions'], r['config'],
                                                             r['status'], r['cbmc_seconds'], r['properties'], r['failed'], cov,
                                                             mu, r['review'], r['ledger_entries'], r.get('argued', ''), r.get('bounds', ''), r.get('assigns', '')]))
    seen = []
    for r in rs:
        k = (r['card'], r['prove_from'], r['coverage_from'], r['mutants_from'])
        if k not in seen:
            seen.append(k)
    if seen:
        lines += ['', 'Where each card\'s numbers come from (the commit whose gate produced them, and its log):', '']
        for cid, pf, cf, mf in seen:
            lines.append('- %s: proofs %s; coverage %s; mutants %s' % (cid, pf or 'unrecorded', cf or 'unrecorded', mf or 'unrecorded'))
    return '\n'.join(lines) + '\n'


def campaign_md(state):
    lines = ['# CAMPAIGN', '', 'Generated by tools/campaign.py from its state at each merge. Do not edit. '
             'Live view: `tools/campaign.py status`.', '']
    if not state:
        return '\n'.join(lines + ['No campaign state.']) + '\n'
    jobs = state.get('jobs', {})
    lines += ['| Card | State | Round | Builder tokens | Reviewer tokens | Reason |', '|---|---|---|---|---|---|']
    for cid in sorted(state.get('cards', {})):
        c = state['cards'][cid]
        lines.append('| %s | %s | %s | %d | %d | %s |' % (cid, c['state'], c['round'], c.get('tokens_builder', 0),
                                                         c.get('tokens_reviewer', 0), (c.get('reason') or '').replace('|', '/')))
    lines += ['', '## Sessions', '', '| Job | Card | Role | Round | Vendor/model | Effort | Tokens | Exit | Outcome |',
              '|---|---|---|---|---|---|---|---|---|']
    for jid in sorted(jobs):
        j = jobs[jid]
        if j['kind'] not in ('builder', 'reviewer', 'oneoff'):
            continue
        lines.append('| %s | %s | %s | %s | %s/%s | %s | %d | %s | %s |' % (
            jid, j.get('card') or '', j.get('role'), j.get('round'), j.get('vendor'), j.get('model'), j.get('effort'),
            (j.get('usage') or {}).get('total', 0), j.get('rc', ''), (j.get('outcome') or j.get('state') or '').replace('|', '/')))
    return '\n'.join(lines) + '\n'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default=os.path.dirname(TOOLS))
    ap.add_argument('--state')
    ap.add_argument('--check', action='store_true')
    a = ap.parse_args()
    rs = rows(a.root)
    text = csv_text(rs)
    if a.check:
        p = os.path.join(a.root, 'results.csv')
        old = open(p).read() if os.path.exists(p) else ''
        same = old == text
        print('results: results.csv %s the regenerated text (%d rows)' % ('equals' if same else 'DIFFERS FROM', len(rs)))
        print('RESULT results %s %d rows' % ('PASS' if same else 'FAIL', len(rs)))
        return 0 if same else 1
    with open(os.path.join(a.root, 'results.csv'), 'w') as f:
        f.write(text)
    with open(os.path.join(a.root, 'RESULTS.md'), 'w') as f:
        f.write(results_md(rs))
    state = json.load(open(a.state)) if a.state and os.path.exists(a.state) else None
    if a.state:
        with open(os.path.join(a.root, 'CAMPAIGN.md'), 'w') as f:
            f.write(campaign_md(state))
    print('RESULT results PASS %d rows' % len(rs))
    return 0


if __name__ == '__main__':
    sys.exit(main())
