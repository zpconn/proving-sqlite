#!/usr/bin/env python3
"""Generate C-17's bounded-P1 measurement inputs: the contract (fields unrolled to KMAX), and for a grid point
(K, L, mode) a card dir <out>/C-17 with harness.c and Makefile. L = 0 means string/blob lengths unbounded.
mode: 'loop' (legacy loop contract, PROOF span in the overlay) or 'unwind' (loop unwound K times)."""
import sys, os

def contract(kmax, nzero=True):
    per = []
    for j in range(kmax):
        m = 'pPKey2->aMem[%d]' % j
        z = ('((%s.flags & (MEM_Int|MEM_IntReal|MEM_Real)) != 0 || (%s.flags & (MEM_Str|MEM_Blob)) == 0\n'
             '        || ((%s.flags & (MEM_Str|MEM_Zero)) == MEM_Zero ? %s\n'
             '        : (%s.n >= 0 && __CPROVER_r_ok(%s.z, %s.n))))') % (
                 m, m, m, ('%s.u.nZero >= 0' % m) if nzero else '1', m, m, m)
        c = ('(pPKey2->pKeyInfo->nAllField <= %d || pPKey2->pKeyInfo->aColl[%d] == 0\n'
             '        || __CPROVER_r_ok(pPKey2->pKeyInfo->aColl[%d], sizeof(CollSeq)))') % (j, j, j)
        per.append('  __CPROVER_requires(pPKey2->nField <= %d || (%s\n      && %s))' % (j, z, c))
    return '''#ifndef CONTRACT_SQLITE3VDBERECORDCOMPAREWITHSKIP_H
#define CONTRACT_SQLITE3VDBERECORDCOMPAREWITHSKIP_H
/* C-17, round 4: a BOUNDED measurement contract (nField <= %d), pending Zach's decision on the bound. */
int contract_sqlite3VdbeRecordCompareWithSkip(int nKey1, const void *pKey1, UnpackedRecord *pPKey2, int bSkip)
  __CPROVER_requires(nKey1 >= 0
    && __CPROVER_r_ok(pKey1, (size_t)(nKey1 > FLOOR + (bSkip != 0) ? nKey1 : FLOOR + (bSkip != 0)) + 8))
  __CPROVER_requires(__CPROVER_rw_ok(pPKey2, sizeof(UnpackedRecord)))
  __CPROVER_requires(pPKey2->nField >= 1 + (bSkip != 0) && pPKey2->nField <= %d)
  __CPROVER_requires(__CPROVER_r_ok(pPKey2->aMem, sizeof(Mem) * pPKey2->nField))
  __CPROVER_requires(__CPROVER_r_ok(pPKey2->pKeyInfo, SZ_KEYINFO(0)) && pPKey2->pKeyInfo->nAllField >= 1
    && __CPROVER_r_ok(pPKey2->pKeyInfo, SZ_KEYINFO(pPKey2->nField < pPKey2->pKeyInfo->nAllField
                                                  ? pPKey2->nField : pPKey2->pKeyInfo->nAllField)))
  __CPROVER_requires(__CPROVER_r_ok(pPKey2->pKeyInfo->aSortFlags, pPKey2->nField))
%s
  __CPROVER_assigns(pPKey2->errCode, pPKey2->eqSeen);
#endif
''' .replace('FLOOR', '10') % (kmax, kmax, '\n'.join(per))

def entry(b, n, L, slack, nkey):
    d = ['  int nKey1;', '  const void *pKey1;', '  UnpackedRecord *pPKey2;', '  int bSkip;',
         '  size_t ext, nA;', '  u16 nField, nAllField;', '  KeyInfo *ki;', '  Mem *mem;', '  u8 *sf;']
    s = ['  __CPROVER_assume(nKey1 >= 0%s);' % ((' && nKey1 <= %s' % nkey) if nkey else ''),
         '  bSkip = %d;' % b,
         '  ext = (size_t)(nKey1 > FLOOR + (bSkip != 0) ? nKey1 : FLOOR + (bSkip != 0)) + %d;' % slack,
         '  pKey1 = malloc(ext);',
         '  nField = %d;' % n, '  __CPROVER_assume(nAllField >= 1);',
         '  nA = nField < nAllField ? nField : nAllField;',
         '  pPKey2 = malloc(sizeof(UnpackedRecord));',
         '  mem = malloc(sizeof(Mem) * %d);' % n,
         '  ki = malloc(sizeof(KeyInfo) + sizeof(CollSeq *) * nA);',
         '  sf = malloc(%d);' % n,
         '  __CPROVER_assume(pKey1 != 0 && pPKey2 != 0 && mem != 0 && ki != 0 && sf != 0);',
         '  pPKey2->pKeyInfo = ki;', '  pPKey2->aMem = mem;', '  pPKey2->nField = nField;',
         '  ki->nAllField = nAllField;', '  ki->aSortFlags = sf;']
    for k in range(n):
        d += ['  size_t k%d;' % k, '  Mem *m%d;' % k, '  char *z%d;' % k, '  int n%d;' % k]
        s += ['  k%d = %d;' % (k, k),
              ('  __CPROVER_assume(n%d >= 0 && n%d <= %d);' % (k, k, L)) if L else '  __CPROVER_assume(n%d >= 0);' % k,
              '  z%d = malloc(n%d);' % (k, k),
              '  m%d = mem + k%d;' % (k, k), '  m%d->z = z%d;' % (k, k), '  m%d->n = n%d;' % (k, k)]
    for k in reversed(range(n)):
        d += ['  size_t a%d;' % k, '  CollSeq *c%d;' % k]
        s += ['  a%d = nA > %d ? %d : 0;' % (k, k, k), '  c%d = malloc(sizeof(CollSeq));' % k,
              '  ki->aColl[a%d] = c%d;' % (k, k)]
    s = [x.replace('FLOOR', os.environ.get('FLOOR', '10')) for x in s]
    return ('void harness_b%dn%d(void){\n%s\n\n  /* SETUP */\n%s\n  /* END SETUP */\n\n'
            '  sqlite3VdbeRecordCompareWithSkip(nKey1, pKey1, pPKey2, bSkip);\n}\n') % (
                b, n, '\n'.join(d), '\n'.join(s))

def proofs(K):
    return [(b, n) for b in (0, 1) for n in range(1 + b, K + 1)]

def harness(K, L, slack=8, nkey=None):
    inc = ''.join('#include "contracts/%s.h"\n' % f for f in ['sqlite3VdbeRecordCompareWithSkip', 'sqlite3GetVarint32',
        'sqlite3VdbeSerialGet', 'serialGet7', 'sqlite3VdbeSerialTypeLen', 'sqlite3VarintLen', 'vdbeRecordDecodeInt',
        'sqlite3IntFloatCompare', 'isAllZero', 'vdbeCompareMemString', 'sqlite3CorruptError', 'memcmp'])
    return ('#include "sqlite3.c"\n' + inc + '#include <stdlib.h>\n\n'
            '/* C-17 round 4, bounded measurement harness: one proof per (bSkip, nField), nField <= %d; '
            'string/blob lengths %s. */\n\n' % (K, ('<= %d' % L) if L else 'unbounded')
            + '\n'.join(entry(b, n, L, slack, nkey) for b, n in proofs(K)))

REPL = ('sqlite3GetVarint32/contract_sqlite3GetVarint32 serialGet7/contract_serialGet7 '
        'sqlite3VdbeSerialTypeLen/contract_sqlite3VdbeSerialTypeLen sqlite3VarintLen/contract_sqlite3VarintLen '
        'vdbeRecordDecodeInt/contract_vdbeRecordDecodeInt sqlite3IntFloatCompare/contract_sqlite3IntFloatCompare '
        'isAllZero/contract_isAllZero vdbeCompareMemString/contract_vdbeCompareMemString '
        'sqlite3CorruptError/contract_sqlite3CorruptError memcmp/contract_memcmp')

KEEPREPL = ('sqlite3IntFloatCompare/contract_sqlite3IntFloatCompare isAllZero/contract_isAllZero '
            'vdbeCompareMemString/contract_vdbeCompareMemString sqlite3CorruptError/contract_sqlite3CorruptError '
            'memcmp/contract_memcmp')

def makefile(K, extra=''):
    ps = ['b%dn%d' % bn for bn in proofs(K)]
    lines = ['CARD := C-17', 'PROOFS := ' + ' '.join(ps)]
    for p in ps:
        lines += ['%s_ENTRY := harness_%s' % (p, p),
                  '%s_ENFORCE := sqlite3VdbeRecordCompareWithSkip/contract_sqlite3VdbeRecordCompareWithSkip' % p,
                  ('%s_REPLACE := %s' % (p, KEEPREPL)) if os.environ.get('KEEP') else
                  '%s_REPLACE := %s sqlite3VdbeSerialGet/contract_sqlite3VdbeSerialGet' % (p, REPL),
                  '%s_LOOPS := unwind' % p,
                  '%s_UNWINDSET := sqlite3VdbeRecordCompareWithSkip_wrapped_for_contract_checking.0:%d%s' % (p, int(p.split('n')[1]), ',sqlite3VarintLen.0:10' if os.environ.get('KEEP') else ''),
                  '%s_COVER := sqlite3VdbeRecordCompareWithSkip' % p] + (['%s_%s' % (p, extra)] if extra else [])
    return '\n'.join(lines) + '\ninclude ../Makefile.common\n'

if __name__ == '__main__':
    what = sys.argv[1]
    if what == 'contract':
        sys.stdout.write(contract(int(sys.argv[2]), sys.argv[3:4] != ['nonzero']))
    else:
        K, L, out = int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
        extra = sys.argv[5] if len(sys.argv) > 5 else ''
        slack = int(os.environ.get('SLACK', '8'))
        os.makedirs(os.path.join(out, 'C-17'), exist_ok=True)
        open(os.path.join(out, 'C-17', 'harness.c'), 'w').write(harness(K, L, slack, os.environ.get('NKEY')))
        open(os.path.join(out, 'C-17', 'Makefile'), 'w').write(makefile(K, extra))
