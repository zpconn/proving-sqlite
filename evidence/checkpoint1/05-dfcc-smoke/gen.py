"""Generate trivial-contract DFCC smoke proofs, one per Appendix A function (checkpoint 1, fix 1)."""
import os, sys
OUT = sys.argv[1]
P = {  # fn: (card, return type, [(type, name, init)])
 'sqlite3PutVarint': ('C-01','int',[('unsigned char *','p','malloc(9)'),('u64','v',None)]),
 'putVarint64': ('C-01','int',[('unsigned char *','p','malloc(9)'),('u64','v',None)]),
 'sqlite3GetVarint': ('C-03','u8',[('const unsigned char *','p','malloc(9)'),('u64 *','v','malloc(sizeof(u64))')]),
 'sqlite3GetVarint32': ('C-04','u8',[('const unsigned char *','p','malloc(9)'),('u32 *','v','malloc(sizeof(u32))')]),
 'sqlite3VarintLen': ('C-05','int',[('u64','v',None)]),
 'sqlite3VdbeSerialTypeLen': ('C-06','u32',[('u32','serial_type',None)]),
 'sqlite3VdbeOneByteSerialTypeLen': ('C-06','u8',[('u8','serial_type',None)]),
 'serialGet': ('C-07','void',[('const unsigned char *','buf','malloc(8)'),('u32','serial_type',None),('Mem *','pMem','malloc(sizeof(Mem))')]),
 'serialGet7': ('C-07','int',[('const unsigned char *','buf','malloc(8)'),('Mem *','pMem','malloc(sizeof(Mem))')]),
 'sqlite3VdbeSerialGet': ('C-08','void',[('const unsigned char *','buf','malloc(8)'),('u32','serial_type',None),('Mem *','pMem','malloc(sizeof(Mem))')]),
 'vdbeRecordDecodeInt': ('C-10','i64',[('u32','serial_type',None),('const u8 *','aKey','malloc(8)')]),
 'sqlite3IsNaN': ('C-11','int',[('double','x',None)]),
 'sqlite3IntFloatCompare': ('C-11','int',[('i64','i',None),('double','r',None)]),
 'isAllZero': ('C-12','int',[('const char *','z','malloc(4)'),('int','n',None)]),
 'sqlite3VdbeMemSetNull': ('C-13','void',[('Mem *','pMem','malloc(sizeof(Mem))')]),
 'sqlite3VdbeAllocUnpackedRecord': ('C-14','UnpackedRecord *',[('KeyInfo *','pKeyInfo','malloc(sizeof(KeyInfo))')]),
 'sqlite3VdbeRecordUnpack': ('C-15','void',[('int','nKey',None),('const void *','pKey','malloc(16)'),('UnpackedRecord *','p','malloc(sizeof(UnpackedRecord))')]),
 'sqlite3VdbeFindCompare': ('C-16','RecordCompare',[('UnpackedRecord *','p','malloc(sizeof(UnpackedRecord))')]),
 'sqlite3VdbeRecordCompareWithSkip': ('C-17','int',[('int','nKey1',None),('const void *','pKey1','malloc(16)'),('UnpackedRecord *','pPKey2','malloc(sizeof(UnpackedRecord))'),('int','bSkip',None)]),
 'sqlite3VdbeRecordCompare': ('C-18','int',[('int','nKey1',None),('const void *','pKey1','malloc(16)'),('UnpackedRecord *','pPKey2','malloc(sizeof(UnpackedRecord))')]),
 'vdbeRecordCompareString': ('C-19','int',[('int','nKey1',None),('const void *','pKey1','malloc(16)'),('UnpackedRecord *','pPKey2','malloc(sizeof(UnpackedRecord))')]),
 'vdbeRecordCompareInt': ('C-20','int',[('int','nKey1',None),('const void *','pKey1','malloc(16)'),('UnpackedRecord *','pPKey2','malloc(sizeof(UnpackedRecord))')]),
}
BOUNDARY = {'sqlite3DbMallocRaw', 'vdbeCompareMemString', 'sqlite3CorruptError'}
CALLEES = {  # direct callees from evidence/checkpoint1/callgraph.txt, less memcpy/memcmp and C-13's unreached callee
 'sqlite3PutVarint': ['putVarint64'], 'sqlite3GetVarint32': ['sqlite3GetVarint'], 'sqlite3VdbeSerialGet': ['serialGet'],
 'sqlite3IntFloatCompare': ['sqlite3IsNaN'], 'sqlite3VdbeAllocUnpackedRecord': ['sqlite3DbMallocRaw'],
 'sqlite3VdbeRecordUnpack': ['sqlite3GetVarint32', 'sqlite3VdbeMemSetNull', 'sqlite3VdbeSerialGet', 'sqlite3VdbeSerialTypeLen'],
 'sqlite3VdbeRecordCompareWithSkip': ['isAllZero', 'serialGet7', 'sqlite3CorruptError', 'sqlite3GetVarint32', 'sqlite3IntFloatCompare',
     'sqlite3VarintLen', 'sqlite3VdbeSerialGet', 'sqlite3VdbeSerialTypeLen', 'vdbeCompareMemString', 'vdbeRecordDecodeInt'],
 'sqlite3VdbeRecordCompare': ['sqlite3VdbeRecordCompareWithSkip'],
 'vdbeRecordCompareString': ['sqlite3CorruptError', 'sqlite3GetVarint32', 'sqlite3VdbeRecordCompareWithSkip'],
 'vdbeRecordCompareInt': ['sqlite3VdbeRecordCompare', 'sqlite3VdbeRecordCompareWithSkip'],
}
LOOPS = {'putVarint64': 3, 'sqlite3VarintLen': 1, 'isAllZero': 1, 'sqlite3VdbeRecordUnpack': 1, 'sqlite3VdbeRecordCompareWithSkip': 1,
         'vdbeRecordCompareString': 1}
MEMCMP = {'sqlite3VdbeRecordCompareWithSkip', 'vdbeRecordCompareString'}   # CBMC's memcmp model loops over its length
def contract(fn):
    card, rt, args = P[fn]
    return '%s contract_%s(%s)\n  __CPROVER_ensures(1);\n' % (rt, fn, ', '.join('%s%s%s' % (t, '' if t.endswith('*') else ' ', n) for t, n, _ in args))
bycard = {}
for fn, (card, _, _) in P.items():
    bycard.setdefault(card, []).append(fn)
for card, fns in bycard.items():
    d = os.path.join(OUT, card); os.makedirs(d, exist_ok=True)
    h = ['#include "sqlite3.c"']
    needed = set(fns)
    for f in fns:
        needed |= set(CALLEES.get(f, []))
    for b in sorted(needed & BOUNDARY):
        h.append('#include "contracts/%s.h"' % b)
    for f in sorted(needed - BOUNDARY):
        h.append(contract(f))
    mk = ['CARD := %s' % card, 'PROOFS := %s' % ' '.join('p%d' % i for i in range(len(fns)))]
    for i, f in enumerate(fns):
        _, rt, args = P[f]
        body = ['void harness_%s(void){' % f]
        for t, n, init in args:
            body.append('  %s%s%s;' % (t, '' if t.endswith('*') else ' ', n))
        body.append('  /* SETUP */')
        for t, n, init in args:
            if init:
                body.append('  %s = %s;' % (n, init))
        body.append('  /* END SETUP */')
        body.append('  %s(%s);' % (f, ', '.join(n for _, n, _ in args)))
        body.append('}')
        h.append('\n'.join(body))
        mk.append('p%d_ENTRY := harness_%s' % (i, f))
        mk.append('p%d_ENFORCE := %s/contract_%s' % (i, f, f))
        rep = CALLEES.get(f, [])
        if rep:
            mk.append('p%d_REPLACE := %s' % (i, ' '.join('%s/contract_%s' % (c, c) for c in rep)))
        if f in LOOPS:
            mk.append('p%d_LOOPS := unwind' % i)
            mk.append('p%d_UNWINDSET := %s' % (i, ','.join(['%s_wrapped_for_contract_checking.%d:2' % (f, k) for k in range(LOOPS[f])]
                                                         + (['memcmp.0:17'] if f in MEMCMP else []))))
    mk.append('include ../Makefile.common')
    open(os.path.join(d, 'harness.c'), 'w').write('\n'.join(h) + '\n')
    open(os.path.join(d, 'Makefile'), 'w').write('\n'.join(mk) + '\n')
print(len(P), 'functions in', len(bycard), 'card dirs')
