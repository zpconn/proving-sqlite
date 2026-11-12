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

void harness_b1n8(void){
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
  size_t k4;
  Mem *m4;
  char *z4;
  int n4;
  size_t k5;
  Mem *m5;
  char *z5;
  int n5;
  size_t k6;
  Mem *m6;
  char *z6;
  int n6;
  size_t k7;
  Mem *m7;
  char *z7;
  int n7;
  size_t a7;
  CollSeq *c7;
  size_t a6;
  CollSeq *c6;
  size_t a5;
  CollSeq *c5;
  size_t a4;
  CollSeq *c4;
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
  bSkip = 1;
  ext = (size_t)(nKey1 > 10 + (bSkip != 0) ? nKey1 : 10 + (bSkip != 0)) + 8;
  pKey1 = malloc(ext);
  nField = 8;
  __CPROVER_assume(nAllField >= 1);
  nA = nField < nAllField ? nField : nAllField;
  pPKey2 = malloc(sizeof(UnpackedRecord));
  mem = malloc(sizeof(Mem) * 8);
  ki = malloc(sizeof(KeyInfo) + sizeof(CollSeq *) * nA);
  sf = malloc(8);
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
  k4 = 4;
  __CPROVER_assume(n4 >= 0);
  z4 = malloc(n4);
  m4 = mem + k4;
  m4->z = z4;
  m4->n = n4;
  k5 = 5;
  __CPROVER_assume(n5 >= 0);
  z5 = malloc(n5);
  m5 = mem + k5;
  m5->z = z5;
  m5->n = n5;
  k6 = 6;
  __CPROVER_assume(n6 >= 0);
  z6 = malloc(n6);
  m6 = mem + k6;
  m6->z = z6;
  m6->n = n6;
  k7 = 7;
  __CPROVER_assume(n7 >= 0);
  z7 = malloc(n7);
  m7 = mem + k7;
  m7->z = z7;
  m7->n = n7;
  a7 = nA > 7 ? 7 : 0;
  c7 = malloc(sizeof(CollSeq));
  ki->aColl[a7] = c7;
  a6 = nA > 6 ? 6 : 0;
  c6 = malloc(sizeof(CollSeq));
  ki->aColl[a6] = c6;
  a5 = nA > 5 ? 5 : 0;
  c5 = malloc(sizeof(CollSeq));
  ki->aColl[a5] = c5;
  a4 = nA > 4 ? 4 : 0;
  c4 = malloc(sizeof(CollSeq));
  ki->aColl[a4] = c4;
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
