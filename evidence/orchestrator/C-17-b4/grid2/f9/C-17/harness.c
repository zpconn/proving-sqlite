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

/* C-17 round 4, bounded measurement harness: one proof per (bSkip, nField), nField <= 2; string/blob lengths unbounded. */

void harness_b0n1(void){
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
  size_t a0;
  CollSeq *c0;

  /* SETUP */
  __CPROVER_assume(nKey1 >= 0);
  __CPROVER_assume(bSkip == 0);
  ext = (size_t)(nKey1 > 9 + (bSkip != 0) ? nKey1 : 9 + (bSkip != 0)) + 8;
  pKey1 = malloc(ext);
  __CPROVER_assume(nField == 1 && nAllField >= 1);
  nA = nField < nAllField ? nField : nAllField;
  pPKey2 = malloc(sizeof(UnpackedRecord));
  mem = malloc(sizeof(Mem) * 1);
  ki = malloc(sizeof(KeyInfo) + sizeof(CollSeq *) * nA);
  sf = malloc(1);
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
  a0 = nA > 0 ? 0 : 0;
  c0 = malloc(sizeof(CollSeq));
  ki->aColl[a0] = c0;
  /* END SETUP */

  sqlite3VdbeRecordCompareWithSkip(nKey1, pKey1, pPKey2, bSkip);
}

void harness_b0n2(void){
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
  size_t a1;
  CollSeq *c1;
  size_t a0;
  CollSeq *c0;

  /* SETUP */
  __CPROVER_assume(nKey1 >= 0);
  __CPROVER_assume(bSkip == 0);
  ext = (size_t)(nKey1 > 9 + (bSkip != 0) ? nKey1 : 9 + (bSkip != 0)) + 8;
  pKey1 = malloc(ext);
  __CPROVER_assume(nField == 2 && nAllField >= 1);
  nA = nField < nAllField ? nField : nAllField;
  pPKey2 = malloc(sizeof(UnpackedRecord));
  mem = malloc(sizeof(Mem) * 2);
  ki = malloc(sizeof(KeyInfo) + sizeof(CollSeq *) * nA);
  sf = malloc(2);
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
  a1 = nA > 1 ? 1 : 0;
  c1 = malloc(sizeof(CollSeq));
  ki->aColl[a1] = c1;
  a0 = nA > 0 ? 0 : 0;
  c0 = malloc(sizeof(CollSeq));
  ki->aColl[a0] = c0;
  /* END SETUP */

  sqlite3VdbeRecordCompareWithSkip(nKey1, pKey1, pPKey2, bSkip);
}

void harness_b1n2(void){
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
  size_t a1;
  CollSeq *c1;
  size_t a0;
  CollSeq *c0;

  /* SETUP */
  __CPROVER_assume(nKey1 >= 0);
  __CPROVER_assume(bSkip != 0);
  ext = (size_t)(nKey1 > 9 + (bSkip != 0) ? nKey1 : 9 + (bSkip != 0)) + 8;
  pKey1 = malloc(ext);
  __CPROVER_assume(nField == 2 && nAllField >= 1);
  nA = nField < nAllField ? nField : nAllField;
  pPKey2 = malloc(sizeof(UnpackedRecord));
  mem = malloc(sizeof(Mem) * 2);
  ki = malloc(sizeof(KeyInfo) + sizeof(CollSeq *) * nA);
  sf = malloc(2);
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
  a1 = nA > 1 ? 1 : 0;
  c1 = malloc(sizeof(CollSeq));
  ki->aColl[a1] = c1;
  a0 = nA > 0 ? 0 : 0;
  c0 = malloc(sizeof(CollSeq));
  ki->aColl[a0] = c0;
  /* END SETUP */

  sqlite3VdbeRecordCompareWithSkip(nKey1, pKey1, pPKey2, bSkip);
}
