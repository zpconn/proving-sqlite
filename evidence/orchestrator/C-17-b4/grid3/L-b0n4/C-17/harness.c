#include "sqlite3.c"
#include "contracts/sqlite3VdbeRecordCompareWithSkip.h"
#include "contracts/sqlite3GetVarint32.h"
#include "contracts/sqlite3VdbeSerialGet.h"
#include "contracts/serialGet7.h"
#include "contracts/sqlite3VdbeSerialTypeLen.h"
#include "contracts/sqlite3VarintLen.h"
#include "contracts/vdbeRecordDecodeInt.h"
#include "contracts/sqlite3IntFloatCompare.h"
#include "contracts/isAllZero.h"
#include "contracts/vdbeCompareMemString.h"
#include "contracts/sqlite3CorruptError.h"
#include "contracts/memcmp.h"
#include <stdlib.h>

/* C-17 round 4, bounded measurement harness: one proof per (bSkip, nField), nField <= 1; string/blob lengths unbounded. */

void harness_b0n4(void){
  int nKey1;
  const void *pKey1;
  UnpackedRecord *pPKey2;
  int bSkip;
  size_t ext, nA;
  u16 nField, nAllField;
  KeyInfo *ki;
  Mem *mem;
  u8 *sf;
  size_t k0;
  Mem *m0;
  char *z0;
  int n0;
  size_t k1;
  Mem *m1;
  char *z1;
  int n1;
  size_t k2;
  Mem *m2;
  char *z2;
  int n2;
  size_t k3;
  Mem *m3;
  char *z3;
  int n3;
  size_t a3;
  CollSeq *c3;
  size_t a2;
  CollSeq *c2;
  size_t a1;
  CollSeq *c1;
  size_t a0;
  CollSeq *c0;

  /* SETUP */
  __CPROVER_assume(nKey1 >= 0);
  __CPROVER_assume(bSkip == 0);
  ext = (size_t)(nKey1 > 10 + (bSkip != 0) ? nKey1 : 10 + (bSkip != 0)) + 8;
  pKey1 = malloc(ext);
  __CPROVER_assume(nField == 4 && nAllField >= 1);
  nA = nField < nAllField ? nField : nAllField;
  pPKey2 = malloc(sizeof(UnpackedRecord));
  mem = malloc(sizeof(Mem) * 4);
  ki = malloc(sizeof(KeyInfo) + sizeof(CollSeq *) * nA);
  sf = malloc(4);
  __CPROVER_assume(pKey1 != 0 && pPKey2 != 0 && mem != 0 && ki != 0 && sf != 0);
  pPKey2->pKeyInfo = ki;
  pPKey2->aMem = mem;
  pPKey2->nField = nField;
  ki->nAllField = nAllField;
  ki->aSortFlags = sf;
  k0 = 0;
  __CPROVER_assume(n0 >= 0);
  z0 = malloc(n0);
  m0 = mem + k0;
  m0->z = z0;
  m0->n = n0;
  k1 = 1;
  __CPROVER_assume(n1 >= 0);
  z1 = malloc(n1);
  m1 = mem + k1;
  m1->z = z1;
  m1->n = n1;
  k2 = 2;
  __CPROVER_assume(n2 >= 0);
  z2 = malloc(n2);
  m2 = mem + k2;
  m2->z = z2;
  m2->n = n2;
  k3 = 3;
  __CPROVER_assume(n3 >= 0);
  z3 = malloc(n3);
  m3 = mem + k3;
  m3->z = z3;
  m3->n = n3;
  a3 = nA > 3 ? 3 : 0;
  c3 = malloc(sizeof(CollSeq));
  ki->aColl[a3] = c3;
  a2 = nA > 2 ? 2 : 0;
  c2 = malloc(sizeof(CollSeq));
  ki->aColl[a2] = c2;
  a1 = nA > 1 ? 1 : 0;
  c1 = malloc(sizeof(CollSeq));
  ki->aColl[a1] = c1;
  a0 = nA > 0 ? 0 : 0;
  c0 = malloc(sizeof(CollSeq));
  ki->aColl[a0] = c0;
  /* END SETUP */

  sqlite3VdbeRecordCompareWithSkip(nKey1, pKey1, pPKey2, bSkip);
}
