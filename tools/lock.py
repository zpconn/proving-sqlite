#!/usr/bin/env python3
"""lock.py: proof.lock, the SHA-256 of every frozen file (GOAL.md §0.3).

  tools/lock.py write    write proof.lock from the working tree (the setup session runs this once, at the freeze)
  tools/lock.py check    every file proof.lock lists matches, and every file now under a frozen path is listed.
                         Before the freeze there is no proof.lock and check passes. After it, a missing proof.lock
                         fails (checkpoint 0, decision C7). The freeze has happened if HEAD's history has a commit
                         that touched proof.lock, or HANDOFF.md exists (it is written after proof.lock).
Frozen: pin.txt, upstream/, GOAL.md, AGENTS.md, CLAUDE.md, agents/, PROPERTIES.md, TRUSTED.md, UB-CLASSES.md,
proofs/spec/, proofs/CHECKS, proofs/CONFIGS, proofs/MUTANTS, tools/ (except tools/sessions.toml), and the gate's
targets: Makefile, proofs/Makefile.common, proofs/include/proof.h; and the boundary headers proofs/contracts/
{sqlite3DbMallocRaw,vdbeCompareMemString,sqlite3CorruptError}.h (checkpoint 1, D2) and memcmp.h (B2).
Ends with: RESULT lock PASS|FAIL <n> files
"""
import hashlib
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FROZEN = ['pin.txt', 'upstream/', 'GOAL.md', 'AGENTS.md', 'CLAUDE.md', 'agents/', 'PROPERTIES.md', 'TRUSTED.md',
          'UB-CLASSES.md', 'proofs/spec/', 'proofs/CHECKS', 'proofs/CONFIGS', 'proofs/MUTANTS', 'tools/',
          'Makefile', 'proofs/Makefile.common', 'proofs/include/proof.h',
          # checkpoint 1, D2: the boundary headers, LEDGER.md A-002 to A-004 word for word
          'proofs/contracts/sqlite3DbMallocRaw.h', 'proofs/contracts/vdbeCompareMemString.h',
          'proofs/contracts/sqlite3CorruptError.h',
          # B2 (Zach, 2026-11-10): memcmp's boundary contract, LEDGER.md A-006 word for word
          'proofs/contracts/memcmp.h',
          # T-017 (Zach, 2026-11-11): builder guidance the prompts point to, so a change carries an approval record
          'proofs/HOWTO.md']
EXEMPT = {'tools/sessions.toml'}


def tracked(root):
    out = subprocess.run(['git', '-C', root, 'ls-files', '-z'], capture_output=True, check=True).stdout
    return [p for p in out.decode().split('\0') if p]


def frozen_files(root):
    files = []
    for p in tracked(root):
        if p in EXEMPT or '__pycache__' in p:
            continue
        if any(p == f or (f.endswith('/') and p.startswith(f)) for f in FROZEN):
            files.append(p)
    return sorted(files)


def sha(root, p):
    with open(os.path.join(root, p), 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


def after_freeze(root):
    """(True|False|None, reason). None: git cannot say, which fails closed."""
    if os.path.exists(os.path.join(root, 'HANDOFF.md')):
        return True, 'HANDOFF.md exists, so the freeze has happened'
    p = subprocess.run(['git', '-C', root, 'log', '-1', '--format=%h %s', 'HEAD', '--', 'proof.lock'],
                       capture_output=True, text=True)
    if p.returncode != 0:
        q = subprocess.run(['git', '-C', root, 'rev-list', '-n', '1', '--all'], capture_output=True, text=True)
        if q.returncode == 0 and not q.stdout.strip():
            return False, ''          # a repository with no commits yet
        return None, 'git cannot tell whether the freeze happened (%s)' % p.stderr.strip()[:200]
    if p.stdout.strip():
        return True, 'commit %s in HEAD\'s history touched it, so the freeze has happened' % p.stdout.strip()[:80]
    return False, ''


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'check'
    root = sys.argv[2] if len(sys.argv) > 2 else ROOT
    lock = os.path.join(root, 'proof.lock')
    if cmd == 'write':
        files = frozen_files(root)
        missing = [f for f in FROZEN if not f.endswith('/') and f not in files]
        with open(lock, 'w') as f:
            f.write('# proof.lock: SHA-256 of every frozen file (GOAL.md §0.3). Check with tools/lock.py check.\n')
            for p in files:
                f.write('%s  %s\n' % (sha(root, p), p))
        for m in missing:
            print('lock: WARNING frozen path %s does not exist yet' % m)
        print('RESULT lock PASS %d files written' % len(files))
        return 0
    if not os.path.exists(lock):
        frozen, why = after_freeze(root)
        if frozen is None or frozen:
            print('lock: proof.lock is missing, and %s' % why)
            print('RESULT lock FAIL 0 files (proof.lock missing after the freeze)')
            return 1
        print('lock: no proof.lock yet (it is written at the freeze, after checkpoint 1)')
        print('RESULT lock PASS 0 files (no proof.lock)')
        return 0
    want = {}
    for line in open(lock):
        if line.startswith('#') or not line.strip():
            continue
        h, p = line.rstrip('\n').split('  ', 1)
        want[p] = h
    problems = []
    for p, h in sorted(want.items()):
        if not os.path.exists(os.path.join(root, p)):
            problems.append('%s is listed but missing' % p)
        elif sha(root, p) != h:
            problems.append('%s changed since proof.lock' % p)
    for p in frozen_files(root):
        if p not in want:
            problems.append('%s is under a frozen path but not in proof.lock' % p)
    for p in problems:
        print('lock: ' + p)
    print('RESULT lock %s %d files' % ('FAIL' if problems else 'PASS', len(want)))
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
