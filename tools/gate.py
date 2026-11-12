#!/usr/bin/env python3
"""gate.py: the gate (GOAL.md §3.4), behind `make gate`, `make gate CARD=C-NN`, `make prove`, `make coverage`.

make gate CARD=C-NN runs, in order, stopping at nothing (every step reports):
  check_overlay; proof.lock; scan (with --card and, if given, --base); the configuration probe;
  the includes, proofs, coverage (and, for a bounded card in tools/prove.py BOUNDS, native tests: tools/native.py)
  and mutants of C-NN and of every card whose proofs call its functions
  (tools/cards.py callers_of), restricted to cards that have proofs/C-XX/Makefile. With --base, if
  proofs/include/preds.h differs from BASE, also every card whose preprocessed harness includes it.
The includes step (tools/prove.py includes) preprocesses each harness on every configuration and fails if it
pulls in any file but the overlay's sqlite3.c, proofs/{include,contracts,spec}/*.h and system headers.
make gate (full) runs check_overlay; proof.lock; scan; probe; every proof dir's proofs and coverage on
every configuration, and every bounded card's native tests; every mutant in proofs/MUTANTS against every proof; and requires each function
named by a card with proofs to have at least two mutants.
Mutants (checkpoint 1, D1): a mutant counts as killed only by its own card='s proofs (tools/mutate.py), so
make gate CARD=C-NN fails unless C-NN's own proofs kill each of its mutants; callers' proofs still run, and don't
count. The full gate fails on any pending mutant (one whose card has no proofs here or on main): that is the §5
gate. `make gate ALLOW_PENDING=1` (--allow-pending) lets pending mutants pass, for full gates during the campaign.
Card Makefiles are read only by tools/prove.py's declarative parser (load_card), never evaluated by make
(checkpoint 0 follow-up, item 1): each card's prove and coverage steps call tools/prove.py directly, with the
same arguments proofs/Makefile.common would pass, and a card whose Makefile load_card rejects gets a failing
`prove C-NN` step and no includes, prove or coverage run.
Each step's output is copied to stdout; the last line is
  RESULT gate <C-NN|all> PASS|FAIL <seconds>s <failed steps>
"""
import argparse
import os
import re
import subprocess
import sys
import time

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
import cards as cardlib  # noqa: E402
import mutate  # noqa: E402
import prove  # noqa: E402


def step(name, cmd, results):
    print('==== %s: %s' % (name, ' '.join(cmd)))
    sys.stdout.flush()
    t0 = time.time()
    p = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    last = ''
    for line in p.stdout:
        sys.stdout.write('  ' + line)
        if line.startswith('RESULT '):
            last = line.strip()
    rc = p.wait()
    ok = rc == 0 and ' PASS' in last and ' FAIL' not in last
    results.append((name, ok, last or '(no RESULT line, rc %s)' % rc, round(time.time() - t0)))
    print('==== %s %s (%ds)' % (name, 'PASS' if ok else 'FAIL', time.time() - t0))
    sys.stdout.flush()
    return ok


def proof_cards():
    d = os.path.join(ROOT, 'proofs')
    return sorted(x for x in os.listdir(d) if re.match(r'^C-[0-9]{2}$', x) and os.path.exists(os.path.join(d, x, 'Makefile')))


def prove_cmd(card, target, config='all'):
    """tools/prove.py <target> for one card, as proofs/Makefile.common runs it, without make."""
    cd = os.path.join(ROOT, 'proofs', card)
    return [sys.executable, os.path.join(TOOLS, 'prove.py'), target, '--card-dir', cd, '--config', config,
            '--overlay', os.path.join(ROOT, 'overlay'), '--build-dir', os.path.join(cd, 'build')]


def loadable(card, results, target='prove'):
    """True if load_card accepts the card's Makefile; otherwise record a failing step and say why."""
    try:
        prove.load_card(os.path.join(ROOT, 'proofs', card))
        return True
    except (prove.CardError, OSError) as e:
        msg = 'proofs/%s/Makefile rejected by load_card (not run): %s' % (card, e)
        print('==== %s %s: %s' % (target, card, msg))
        print('==== %s %s FAIL (0s)' % (target, card))
        results.append(('%s %s' % (target, card), False, msg[:200], 0))
        return False


def preds_users(have):
    """Cards whose preprocessed harness includes proofs/include/preds.h on some configuration."""
    target = os.path.realpath(os.path.join(ROOT, 'proofs', 'include', 'preds.h'))
    out = []
    for c in have:
        for _, flags in prove.read_configs(ROOT):
            files, _ = prove.include_problems(os.path.join(ROOT, 'proofs', c), flags, os.path.join(ROOT, 'overlay'))
            if any(os.path.realpath(f) == target for f in files if not f.startswith('<')):
                out.append(c)
                break
    return out


def preds_changed(base):
    p = subprocess.run(['git', '-C', ROOT, 'diff', '--quiet', base, '--', 'proofs/include/preds.h'])
    return p.returncode != 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('what', choices=['gate', 'prove', 'coverage'])
    ap.add_argument('--card')
    ap.add_argument('--base')
    ap.add_argument('--config', default='all')
    ap.add_argument('--allow-pending', action='store_true')
    a = ap.parse_args()
    t0 = time.time()
    results = []
    py = sys.executable
    have = proof_cards()
    if a.what in ('prove', 'coverage'):
        for c in have:
            if loadable(c, results, a.what):
                step('%s %s' % (a.what, c), prove_cmd(c, a.what, a.config), results)
        label = 'all'
    else:
        step('check_overlay', [py, 'tools/check_overlay.py'], results)
        step('lock', [py, 'tools/lock.py', 'check'], results)
        scan = [py, 'tools/scan.py']
        if a.card:
            scan += ['--card', a.card] + (['--base', a.base] if a.base else [])
        step('scan', scan, results)
        step('probe', [py, 'tools/prove.py', 'probe'], results)
        cards = cardlib.load_all(ROOT)
        if a.card:
            if a.card not in cards:
                print('gate: no cards/%s.md' % a.card)
                results.append(('card', False, 'missing card', 0))
                todo = []
            else:
                todo = [a.card] + [c for c in cardlib.callers_of(cards, a.card) if c in have]
                if a.base and preds_changed(a.base):
                    users = [c for c in preds_users(have) if c not in todo]
                    print('gate: proofs/include/preds.h differs from %s; also running the cards that include it: %s' % (
                        a.base, ', '.join(users) or 'none'))
                    todo += users
                if a.card not in have:
                    print('gate: proofs/%s/Makefile missing' % a.card)
                    results.append(('card proofs', False, 'missing proofs/%s/Makefile' % a.card, 0))
                    todo = [c for c in todo if c in have]
            label = a.card
        else:
            todo = have
            label = 'all'
        print('gate: cards to run: %s' % (', '.join(todo) or 'none'))
        for c in todo:
            if not loadable(c, results):
                continue
            step('includes %s' % c, [py, 'tools/prove.py', 'includes', '--card-dir', os.path.join('proofs', c)], results)
            step('prove %s' % c, prove_cmd(c, 'prove'), results)
            step('coverage %s' % c, prove_cmd(c, 'coverage'), results)
            if c in prove.BOUNDS:          # a bounded card's native tests past its bounds (tools/native.py, scan rule 16)
                step('native %s' % c, [py, 'tools/native.py', '--card', c], results)
        # mutants
        muts = mutate.read_mutants(os.path.join(ROOT, 'proofs', 'MUTANTS'))
        fns_with_proofs = set()
        for c in (todo if a.card else have):
            if c in cards:
                fns_with_proofs.update(cards[c].functions)
        counts = {}
        for m in muts:
            counts[m['function']] = counts.get(m['function'], 0) + 1
        few = sorted(f for f in fns_with_proofs if counts.get(f, 0) < 2)
        if few:
            print('gate: functions with fewer than two mutants in proofs/MUTANTS: %s' % ', '.join(few))
            results.append(('mutant count', False, 'fewer than two mutants: ' + ', '.join(few), 0))
        if a.card:
            if a.card in have:
                step('mutants %s' % a.card, [py, 'tools/mutate.py', '--card', a.card,
                                             '--with', ','.join(c for c in todo if c != a.card),
                                             '--json', os.path.join('proofs', a.card, 'build', 'mutants.json')], results)
        else:
            step('mutants all', [py, 'tools/mutate.py', '--all', '--json', os.path.join('proofs', 'build', 'mutants-all.json')]
                 + (['--allow-pending'] if a.allow_pending else []), results)
    failed = [n for n, ok, _, _ in results if not ok]
    print('==== summary')
    for n, ok, last, secs in results:
        print('  %-24s %-4s %4ds  %s' % (n, 'PASS' if ok else 'FAIL', secs, last))
    print('RESULT %s %s %s %ds %s' % (a.what, label, 'FAIL' if failed else 'PASS', time.time() - t0,
                                         ('failed: ' + ', '.join(failed)) if failed else '0 failed'))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
